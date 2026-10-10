# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import RedirectWarning, UserError
from odoo.tools import float_compare, formatLang

# Líneas de maquetación: sin cuenta ni saldo, no cuentan en ningún total.
_LAYOUT_TYPES = ("line_section", "line_subsection", "line_note")
# Misma clasificación que `account.move._compute_amount` del core, para que la
# base imponible y el impuesto en Bs correspondan a amount_untaxed/amount_tax.
_TAX_TYPES = ("tax", "non_deductible_tax")
_UNTAXED_TYPES = (
    "product", "rounding", "non_deductible_product",
    "non_deductible_product_total",
)


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_ve_bs_currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.l10n_ve_bs_currency_id",
        string="Moneda Bs",
    )
    l10n_ve_bs_rate_override = fields.Float(
        string="Tasa Bs manual",
        digits=(16, 6),
        copy=False,
        tracking=True,
        help="Tasa que el usuario fija a mano en borrador (Bs por 1 unidad de "
             "la moneda de la compañía). 0 = usar la tabla de tasas BCV.",
    )
    # La tasa se CONGELA en el asiento: depende solo de la fecha del
    # documento (y del override / del origen en reversiones), no de la tabla
    # de tasas. Editar una tasa vieja no mueve los Bs de asientos ya
    # confirmados, y los libros legales no cambian al reimprimirse.
    # Sin tracking a propósito: en borradores se recalcula con cada cambio de
    # fecha y ensuciaría el chatter; lo que se rastrea es el override manual.
    # recursive=True: depende de la tasa del asiento de origen (reversiones),
    # es decir, de sí mismo a través de reversed_entry_id. Odoo lo calcula
    # registro a registro para respetar ese orden (si no, lo forzaría él con
    # un warning); por eso la búsqueda de un solo asiento es una sola
    # consulta (ver res.company._l10n_ve_bs_rates_at).
    l10n_ve_bs_rate = fields.Float(
        string="Tasa Bs",
        digits=(16, 6),
        compute="_compute_l10n_ve_bs_rate", store=True, readonly=True,
        copy=False, recursive=True,
        help="Bs por 1 unidad de la moneda de la compañía aplicados a este "
             "asiento.",
    )
    l10n_ve_bs_rate_date = fields.Date(
        string="Fecha de la tasa",
        compute="_compute_l10n_ve_bs_rate", store=True, readonly=True,
        copy=False, recursive=True,
        help="Fecha del registro de tasa usado (la última tasa cargada en o "
             "antes de la fecha del documento).",
    )
    l10n_ve_bs_rate_missing = fields.Boolean(
        string="Sin tasa Bs",
        compute="_compute_l10n_ve_bs_rate", store=True, readonly=True,
        copy=False, recursive=True,
        help="No existe ninguna tasa de la moneda Bs en o antes de la fecha "
             "del documento: los montos Bs de las líneas en otra moneda "
             "quedan en cero.",
    )
    l10n_ve_bs_rate_outdated = fields.Boolean(
        string="Tasa Bs desactualizada",
        compute="_compute_l10n_ve_bs_rate_outdated",
        help="Borrador cuya tasa guardada ya no es la que da hoy la tabla "
             "para la fecha del documento (p. ej. se cargó después la tasa "
             "del día).",
    )
    l10n_ve_bs_rate_label = fields.Char(
        string="Tasa BCV",
        compute="_compute_l10n_ve_bs_rate_label",
        help="Tasa aplicada al documento, en una sola línea legible para la "
             "cabecera del formulario.",
    )
    l10n_ve_amount_untaxed_bs = fields.Monetary(
        string="Base imponible Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_amounts_bs", store=True, aggregator="sum",
    )
    l10n_ve_amount_tax_bs = fields.Monetary(
        string="Impuestos Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_amounts_bs", store=True, aggregator="sum",
    )
    l10n_ve_amount_total_bs = fields.Monetary(
        string="Total Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_amounts_bs", store=True, aggregator="sum",
    )
    l10n_ve_amount_residual_bs = fields.Monetary(
        string="Saldo Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_amounts_bs", store=True, aggregator="sum",
    )
    l10n_ve_bs_adjustment = fields.Monetary(
        string="Ajuste Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_amounts_bs", store=True, aggregator="sum",
        help="Bolívares absorbidos por el recuadre del asiento (redondeos o "
             "diferencia de cambio real de asientos mixtos Bs/USD).",
    )

    # ------------------------------------------------------------------
    # Tasa del asiento
    # ------------------------------------------------------------------
    def _l10n_ve_bs_doc_date(self):
        """Fecha a la que se busca la tasa del documento.

        Facturas: `invoice_date` (la fecha fiscal que exige el art. 25 de la
        Ley del IVA); asientos y facturas sin fecha aún: `date`; y si tampoco
        hay, hoy.
        """
        self.ensure_one()
        if self.is_invoice(include_receipts=True) and self.invoice_date:
            return self.invoice_date
        return self.date or fields.Date.context_today(self)

    def _l10n_ve_bs_table_rates(self):
        """Tasas de la tabla para la fecha de documento de cada asiento.

        :return: ``{(company_id, fecha): (rate, rate_date)}``. Una consulta
            por compañía (ver `res.company._l10n_ve_bs_rates_at`), no una por
            asiento: en la instalación se resuelven miles de asientos.
        """
        dates_by_company = defaultdict(set)
        for move in self:
            if move.company_id:
                dates_by_company[move.company_id].add(
                    move._l10n_ve_bs_doc_date())
        result = {}
        for company, dates in dates_by_company.items():
            for date, value in company._l10n_ve_bs_rates_at(dates).items():
                result[(company.id, date)] = value
        return result

    def _l10n_ve_bs_origin_with_rate(self):
        """Asiento original de una reversión, si ya tiene tasa.

        Una nota de crédito expresa en Bs la MISMA operación que corrige, así
        que hereda la tasa de la factura de origen y no la del día en que se
        emite (de lo contrario la NC total no anularía la factura en Bs).
        """
        self.ensure_one()
        origin = self.reversed_entry_id
        return origin if origin and origin.l10n_ve_bs_rate > 0.0 else origin.browse()

    def _l10n_ve_bs_frozen_rates(self):
        """Tasa ya CONGELADA de los asientos posteados en la base de datos.

        Un asiento confirmado no se vuelve a tasar aunque algo dispare el
        recálculo: una escritura con el mismo valor (Odoo marca `modified`
        sin comparar), re-postear la factura de origen de una nota de crédito
        (la NC depende de la tasa del origen), o una importación. Se lee la
        BD y no la caché: durante `_post` los recálculos pendientes corren al
        hacer flush, ANTES de escribir `state='posted'`, así que la
        confirmación sí toma la tasa vigente. En la instalación la columna
        está vacía (NULL) y nada queda congelado.

        :return: ``{move_id: (rate, rate_date, missing)}``
        """
        if self.env.context.get("l10n_ve_bs_refresh"):
            return {}
        ids = [move_id for move_id in self._ids if isinstance(move_id, int)]
        if not ids:
            return {}
        self.env.cr.execute(
            """
            SELECT id, l10n_ve_bs_rate, l10n_ve_bs_rate_date,
                   l10n_ve_bs_rate_missing
              FROM account_move
             WHERE id = ANY(%s)
               AND state = 'posted'
               AND l10n_ve_bs_rate IS NOT NULL
            """,
            [ids],
        )
        return {
            row[0]: (row[1] or 0.0, row[2] or False, bool(row[3]))
            for row in self.env.cr.fetchall()
        }

    @api.depends(
        "date", "invoice_date", "move_type", "company_id",
        "l10n_ve_bs_rate_override",
        "reversed_entry_id", "reversed_entry_id.l10n_ve_bs_rate",
    )
    def _compute_l10n_ve_bs_rate(self):
        frozen = self._l10n_ve_bs_frozen_rates()
        from_table = self.filtered(
            lambda m: m.id not in frozen
            and m.company_id.l10n_ve_bs_currency_id
            and not m.l10n_ve_bs_rate_override > 0.0
            and not m._l10n_ve_bs_origin_with_rate())
        table = from_table._l10n_ve_bs_table_rates()
        for move in self:
            if move.id in frozen:
                (move.l10n_ve_bs_rate, move.l10n_ve_bs_rate_date,
                 move.l10n_ve_bs_rate_missing) = frozen[move.id]
                continue
            company = move.company_id
            bs = company.l10n_ve_bs_currency_id
            origin = move._l10n_ve_bs_origin_with_rate()
            missing = False
            if not bs:
                rate, rate_date = 0.0, False
            elif move.l10n_ve_bs_rate_override > 0.0:
                rate = move.l10n_ve_bs_rate_override
                rate_date = move._l10n_ve_bs_doc_date()
            elif origin:
                rate = origin.l10n_ve_bs_rate
                rate_date = (origin.l10n_ve_bs_rate_date
                             or origin._l10n_ve_bs_doc_date())
            else:
                rate, rate_date = table.get(
                    (company.id, move._l10n_ve_bs_doc_date()), (0.0, False))
                # Con Bs == moneda de compañía la tabla siempre da 1.0, así
                # que `not rate` solo ocurre cuando de verdad falta la tasa.
                missing = not rate
            # La tasa se asigna SIEMPRE (campo readonly calculado): nunca
            # queda el valor de un cálculo anterior.
            move.l10n_ve_bs_rate = rate
            move.l10n_ve_bs_rate_date = rate_date
            move.l10n_ve_bs_rate_missing = missing

    @api.depends(
        "state", "date", "invoice_date", "move_type", "company_id",
        "l10n_ve_bs_rate", "l10n_ve_bs_rate_date",
        "l10n_ve_bs_rate_override", "reversed_entry_id",
    )
    def _compute_l10n_ve_bs_rate_outdated(self):
        """Avisa cuando la tabla ya daría otra tasa para este borrador.

        Caso típico: la factura se creó antes de que n8n cargara la tasa del
        día y quedó con la de ayer. No se corrige sola (la tasa guardada solo
        cambia con la fecha del documento); el banner ofrece recalcularla y
        `_post` la refresca de todos modos al confirmar.
        """
        candidates = self.filtered(
            lambda m: m.state == "draft"
            and not m.l10n_ve_bs_rate_override
            and not m._l10n_ve_bs_origin_with_rate()
            and m.company_id.l10n_ve_bs_currency_id
            and m.company_id.l10n_ve_bs_currency_id != m.company_id.currency_id)
        table = candidates._l10n_ve_bs_table_rates()
        # `_ids` y no `ids`: en el onchange los asientos son NewId.
        candidate_ids = set(candidates._ids)
        for move in self:
            outdated = False
            if move.id in candidate_ids:
                rate, rate_date = table.get(
                    (move.company_id.id, move._l10n_ve_bs_doc_date()),
                    (0.0, False))
                outdated = bool(
                    rate_date != move.l10n_ve_bs_rate_date
                    or float_compare(rate, move.l10n_ve_bs_rate,
                                     precision_digits=6))
            move.l10n_ve_bs_rate_outdated = outdated

    @api.depends("l10n_ve_bs_rate", "l10n_ve_bs_rate_date",
                 "company_id.currency_id", "l10n_ve_bs_currency_id")
    @api.depends_context("lang")
    def _compute_l10n_ve_bs_rate_label(self):
        """"875,6505 Bs por USD · 09-10-2026": una fila propia en la cabecera.

        Antes eran campos sueltos dentro de la columna de la moneda y, en la
        cabecera angosta, la frase se partía palabra por palabra.
        """
        for move in self:
            bs = move.l10n_ve_bs_currency_id
            if not bs or not move.l10n_ve_bs_rate:
                move.l10n_ve_bs_rate_label = False
                continue
            label = "%s %s por %s" % (
                formatLang(self.env, move.l10n_ve_bs_rate, digits=4),
                bs.symbol or bs.name, move.company_id.currency_id.name)
            if move.l10n_ve_bs_rate_date:
                label += " · %s" % move.l10n_ve_bs_rate_date.strftime("%d-%m-%Y")
            move.l10n_ve_bs_rate_label = label

    def write(self, vals):
        """La tasa manual solo se cambia en borrador.

        La vista ya la pone readonly fuera de borrador, pero una importación,
        XML-RPC u otra vista podrían escribirla en un asiento confirmado: eso
        recalcularía la tasa, los Bs de cada apunte y los totales de un
        documento ya emitido, y cambiaría los libros legales. Se permite
        reescribir el mismo valor (guardar un formulario sin tocarla) y el
        paso a borrador en la misma escritura.
        """
        if ("l10n_ve_bs_rate_override" in vals
                and vals.get("state") != "draft"):
            new_rate = vals["l10n_ve_bs_rate_override"] or 0.0
            locked = self.filtered(
                lambda m: m.state != "draft"
                and float_compare(m.l10n_ve_bs_rate_override, new_rate,
                                  precision_digits=6))
            if locked:
                raise UserError(self.env._(
                    "La «Tasa Bs manual» solo se puede cambiar en borrador. "
                    "Pase a borrador antes: %(moves)s",
                    moves=", ".join(locked[:5].mapped("display_name")),
                ))
        return super().write(vals)

    def action_l10n_ve_bs_refresh_rate(self):
        """Botón del banner: vuelve a la tasa de la tabla (solo borradores).

        `modified` fuerza el recálculo aunque el override ya fuera 0: la tasa
        no depende de la tabla, así que sin esto no se movería.
        """
        drafts = self.filtered(lambda m: m.state == "draft")
        if drafts:
            drafts.write({"l10n_ve_bs_rate_override": 0.0})
            drafts.modified(["l10n_ve_bs_rate_override"])
        return True

    # ------------------------------------------------------------------
    # Totales en Bs
    # ------------------------------------------------------------------
    @api.depends(
        "move_type", "currency_id", "amount_total", "amount_residual",
        "line_ids.display_type", "line_ids.tax_repartition_line_id",
        "line_ids.l10n_ve_balance_bs", "line_ids.l10n_ve_bs_adjustment",
    )
    def _compute_l10n_ve_amounts_bs(self):
        """Totales Bs del documento, sumados desde los Bs de sus apuntes.

        Se suman los apuntes (no se convierte amount_total) para que el PDF,
        la pantalla y los libros digan exactamente lo mismo. Como el asiento
        cuadra en Bs, el total equivale a −signo × Σ líneas de vencimiento.
        """
        for move in self:
            bs = move.company_id.l10n_ve_bs_currency_id
            untaxed = tax = total = residual = adjustment = 0.0
            if bs:
                lines = move.line_ids
                adjustment = bs.round(
                    sum(lines.mapped("l10n_ve_bs_adjustment")))
                if move.is_invoice(include_receipts=True):
                    sign = move.direction_sign
                    other = 0.0
                    for line in lines:
                        dtype = line.display_type
                        if dtype in _LAYOUT_TYPES or dtype == "payment_term":
                            continue
                        if dtype in _TAX_TYPES or (
                                dtype == "rounding"
                                and line.tax_repartition_line_id):
                            tax += line.l10n_ve_balance_bs
                        elif dtype in _UNTAXED_TYPES:
                            untaxed += line.l10n_ve_balance_bs
                        else:
                            # epd, cogs, discount…: suelen venir en pares que
                            # se anulan, pero si no, forman parte del total.
                            other += line.l10n_ve_balance_bs
                    untaxed = bs.round(sign * untaxed)
                    tax = bs.round(sign * tax)
                    total = bs.round(untaxed + tax + sign * other)
                    if move.currency_id == bs:
                        residual = move.amount_residual
                    elif move.amount_total:
                        residual = bs.round(
                            total * move.amount_residual / move.amount_total)
                else:
                    total = bs.round(sum(
                        amount for amount in lines.mapped("l10n_ve_balance_bs")
                        if amount > 0.0))
            move.l10n_ve_amount_untaxed_bs = untaxed
            move.l10n_ve_amount_tax_bs = tax
            move.l10n_ve_amount_total_bs = total
            move.l10n_ve_amount_residual_bs = residual
            move.l10n_ve_bs_adjustment = adjustment

    def _l10n_ve_bs_dual_applies(self):
        """¿Se muestra el documento en doble moneda?

        Hace falta una moneda Bs distinta de la del documento (una factura
        emitida en Bs no se duplica) y una tasa: sin tasa es preferible no
        imprimir el bloque Bs que imprimir ceros.
        """
        self.ensure_one()
        bs = self.company_id.l10n_ve_bs_currency_id
        return bool(bs) and bs != self.currency_id \
            and not self.l10n_ve_bs_rate_missing

    def _l10n_ve_bs_tax_groups(self):
        """Base e impuesto por grupo de impuesto, en moneda del documento y
        en Bs, con el signo de la factura (positivo en facturas normales).

        La base Bs sale de los Bs almacenados de las líneas de producto que
        llevan algún impuesto del grupo (cada línea cuenta una vez por grupo,
        con los impuestos aplanados como hace el core); el impuesto Bs, de
        las líneas de impuesto del grupo. Así la suma por grupo cuadra con
        los totales Bs del documento.
        """
        self.ensure_one()
        sign = self.direction_sign
        bs = self.company_id.l10n_ve_bs_currency_id
        currency = self.currency_id
        groups = {}

        def bucket(group):
            if group not in groups:
                groups[group] = {
                    "tax_group_id": group.id,
                    "name": group.name,
                    "base": 0.0, "tax": 0.0, "base_bs": 0.0, "tax_bs": 0.0,
                }
            return groups[group]

        for line in self.line_ids:
            if line.display_type == "tax" and line.tax_line_id.tax_group_id:
                values = bucket(line.tax_line_id.tax_group_id)
                values["tax"] += sign * line.amount_currency
                values["tax_bs"] += sign * line.l10n_ve_balance_bs
            elif line.display_type == "product" and line.tax_ids:
                taxes = line.tax_ids.flatten_taxes_hierarchy()
                for group in taxes.tax_group_id:
                    values = bucket(group)
                    values["base"] += sign * line.amount_currency
                    values["base_bs"] += sign * line.l10n_ve_balance_bs

        result = []
        for group in sorted(groups, key=lambda g: (g.sequence, g.id)):
            values = groups[group]
            for key in ("base", "tax"):
                values[key] = currency.round(values[key])
            for key in ("base_bs", "tax_bs"):
                values[key] = bs.round(values[key]) if bs else 0.0
            result.append(values)
        return result

    def _l10n_ve_bs_amounts(self):
        """Override de `l10n_ve_bw_invoice_format`: totales Bs del PDF.

        Ya no se convierte al vuelo: se devuelven los montos ALMACENADOS del
        asiento (los mismos de los libros), con la tasa congelada al
        confirmar. Conserva las claves que usa el QWeb de invoice_format
        (`currency`, `rate`, `date`, `untaxed`, `tax`, `total`, `residual`,
        `show_residual`) y añade `dual`, `tax_groups` y `rate_date` para el
        PDF de doble moneda. Dict vacío = el PDF no imprime bloque Bs.
        """
        self.ensure_one()
        if not self._l10n_ve_bs_dual_applies():
            return {}
        bs = self.company_id.l10n_ve_bs_currency_id
        total = self.l10n_ve_amount_total_bs
        residual = self.l10n_ve_amount_residual_bs
        return {
            "currency": bs,
            "rate": self.l10n_ve_bs_rate,
            "date": self.l10n_ve_bs_rate_date or self._l10n_ve_bs_doc_date(),
            "untaxed": self.l10n_ve_amount_untaxed_bs,
            "tax": self.l10n_ve_amount_tax_bs,
            "total": total,
            "residual": residual,
            # Misma regla que invoice_format: el saldo solo se imprime si
            # dice algo (ni recién emitida, ni ya cobrada).
            "show_residual": bool(
                bs.compare_amounts(residual, total)
                and bs.compare_amounts(residual, 0.0)
            ),
            "dual": True,
            "tax_groups": self._l10n_ve_bs_tax_groups(),
            "rate_date": self.l10n_ve_bs_rate_date,
        }

    @api.depends(
        "l10n_ve_bs_rate", "l10n_ve_bs_rate_date", "l10n_ve_bs_rate_missing",
        "l10n_ve_amount_untaxed_bs", "l10n_ve_amount_tax_bs",
        "l10n_ve_amount_total_bs", "l10n_ve_amount_residual_bs",
        "line_ids.l10n_ve_balance_bs",
    )
    def _compute_tax_totals(self):
        """Añade al widget de totales la columna en Bs.

        Los subtotales Bs se acumulan igual que el core: el primero es la
        base imponible y cada siguiente suma los impuestos de los grupos del
        subtotal anterior. Se copia el dict antes de tocarlo para no mutar
        el valor que el core pudiera tener en caché.
        """
        super()._compute_tax_totals()
        for move in self:
            totals = move.tax_totals
            if not totals or not move._l10n_ve_bs_dual_applies():
                continue
            bs = move.company_id.l10n_ve_bs_currency_id
            if move.state == "draft":
                # Borrador: en el formulario Odoo aún no generó las líneas de
                # impuesto ni de cobro, así que los Bs almacenados no están
                # completos. Se convierten los montos del propio widget (en
                # moneda de la compañía) a la tasa del borrador; al confirmar,
                # la pantalla pasa a leer los Bs almacenados del asiento (la
                # diferencia posible es de céntimos de redondeo).
                groups, base_bs = move._l10n_ve_bs_draft_groups(totals, bs)
                tax_bs = bs.round(sum(g["tax_bs"] for g in groups.values()))
                total_bs = bs.round(base_bs + tax_bs)
                residual_bs = total_bs
            else:
                groups = {
                    values["tax_group_id"]: values
                    for values in move._l10n_ve_bs_tax_groups()
                }
                base_bs = move.l10n_ve_amount_untaxed_bs
                tax_bs = move.l10n_ve_amount_tax_bs
                total_bs = move.l10n_ve_amount_total_bs
                residual_bs = move.l10n_ve_amount_residual_bs
            subtotals = {}
            running = base_bs
            for subtotal in totals.get("subtotals", []):
                subtotals[subtotal["name"]] = bs.round(running)
                for tax_group in subtotal.get("tax_groups", []):
                    running += groups.get(tax_group["id"], {}).get(
                        "tax_bs", 0.0)
            rate_date = move.l10n_ve_bs_rate_date
            totals = dict(totals)
            totals["l10n_ve_bs"] = {
                "currency_id": bs.id,
                "rate": move.l10n_ve_bs_rate,
                "rate_date": fields.Date.to_string(rate_date)
                if rate_date else False,
                "base_amount": base_bs,
                "tax_amount": tax_bs,
                "total_amount": total_bs,
                "residual_amount": residual_bs,
                "cash_rounding": move._l10n_ve_bs_cash_rounding(totals, bs),
                "subtotals": subtotals,
                "tax_groups": {
                    str(group_id): {
                        "base_amount": values["base_bs"],
                        "tax_amount": values["tax_bs"],
                    }
                    for group_id, values in groups.items()
                },
            }
            move.tax_totals = totals

    def _l10n_ve_bs_cash_rounding(self, totals, bs):
        """Bs de la fila "Redondeo" del widget (redondeo de caja).

        Borrador: el delta del core (moneda de la compañía) × tasa.
        Posteado: los Bs almacenados de las líneas de redondeo.
        """
        self.ensure_one()
        if self.state == "draft":
            return bs.round(
                (totals.get("cash_rounding_base_amount") or 0.0)
                * self.l10n_ve_bs_rate)
        lines = self.line_ids.filtered(lambda l: l.display_type == "rounding")
        return bs.round(
            self.direction_sign * sum(lines.mapped("l10n_ve_balance_bs")))

    def _l10n_ve_bs_draft_groups(self, totals, bs):
        """Bs por grupo de impuesto de un borrador, desde el widget del core.

        `tax_totals` trae `base_amount`/`tax_amount` en la moneda de la
        compañía (los `*_currency` son de la moneda del documento), así que
        basta multiplicarlos por la tasa del asiento.

        :return: ``({tax_group_id: {'base_bs', 'tax_bs'}}, base imponible Bs)``
        """
        self.ensure_one()
        rate = self.l10n_ve_bs_rate
        groups = {}
        for subtotal in totals.get("subtotals", []):
            for tax_group in subtotal.get("tax_groups", []):
                groups[tax_group["id"]] = {
                    "base_bs": bs.round(
                        (tax_group.get("display_base_amount")
                         or tax_group.get("base_amount") or 0.0) * rate),
                    "tax_bs": bs.round(
                        (tax_group.get("tax_amount") or 0.0) * rate),
                }
        base_bs = bs.round((totals.get("base_amount") or 0.0) * rate)
        return groups, base_bs

    # ------------------------------------------------------------------
    # Confirmación
    # ------------------------------------------------------------------
    def _l10n_ve_bs_moves_without_today_rate(self):
        """Facturas que, de confirmarse ahora, usarían una tasa de otro día.

        :return: ``{fecha: (compañía, moneda Bs)}``.
        Se excluyen: asientos que no son factura, borradores con tasa
        manual, reversiones (heredan la tasa del origen) y facturas sin
        ninguna línea fuera de Bs (no hay nada que convertir). Sin
        `invoice_date` se evalúa hoy, que es la fecha que `_post` le pondrá.
        """
        missing = {}
        for move in self:
            company = move.company_id
            bs = company.l10n_ve_bs_currency_id
            if (
                move.state != "draft"
                or not move.is_invoice(include_receipts=True)
                or not bs or bs == company.currency_id
                or move.l10n_ve_bs_rate_override > 0.0
                or move._l10n_ve_bs_origin_with_rate()
                or not company._l10n_ve_bs_requires_daily_rate()
            ):
                continue
            if not move.line_ids.filtered(
                    lambda l: l.display_type not in _LAYOUT_TYPES
                    and l.currency_id != bs):
                continue
            date = move.invoice_date or company._l10n_ve_bs_local_today()
            if (date not in missing
                    and not company._l10n_ve_bs_rate_acceptable_for(date)):
                missing[date] = (company, bs)
        return missing

    def _l10n_ve_bs_check_today_rate(self):
        """Exige la tasa BCV del día antes de confirmar desde la interfaz.

        Regla del negocio: sin tasa del día se PIDE la tasa, no se usa la de
        otro día en silencio. Lo llaman los dos caminos de la interfaz: el
        botón (`action_post`) y la confirmación masiva desde la lista
        (`validate.account.move`, que va directo a `_post`). `_post` en sí
        no se bloquea: lo usan el POS, los extractos y las diferencias de
        cambio. Saltable con el contexto `l10n_ve_bs_skip_rate_check`.
        """
        if self.env.context.get("l10n_ve_bs_skip_rate_check"):
            return
        missing = self._l10n_ve_bs_moves_without_today_rate()
        if not missing:
            return
        date = min(missing)
        company, bs = missing[date]
        dates = ", ".join(d.strftime("%d-%m-%Y") for d in sorted(missing))
        action = {
            "type": "ir.actions.act_window",
            "name": self.env._("Tasas %(currency)s", currency=bs.name),
            "res_model": "res.currency.rate",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": [("currency_id", "=", bs.id)],
            "context": {
                "default_currency_id": bs.id,
                "default_name": fields.Date.to_string(date),
                "default_company_id": company.root_id.id,
            },
        }
        if not self.env["res.currency.rate"].has_access("create"):
            # Sin permiso para crear tasas el botón llevaría a un AccessError:
            # se indica el camino que SÍ tiene (la tasa manual en borrador).
            raise UserError(self.env._(
                "Falta la tasa BCV del %(dates)s (%(currency)s). Pida a "
                "contabilidad que la cargue, o escriba una «Tasa Bs manual» en "
                "la pestaña Otra información antes de confirmar.",
                dates=dates, currency=bs.name,
            ))
        raise RedirectWarning(
            self.env._(
                "Falta la tasa BCV del %(dates)s (%(currency)s). "
                "Cárguela antes de confirmar la factura, o escriba una "
                "«Tasa Bs manual» en la pestaña Otra información.",
                dates=dates, currency=bs.name,
            ),
            action,
            self.env._("Cargar la tasa"),
        )

    def action_post(self):
        """Confirmación desde el botón: exige la tasa BCV del día."""
        self._l10n_ve_bs_check_today_rate()
        return super().action_post()

    def _post(self, soft=True):
        """Congela la tasa vigente al confirmar, sin bloquear nunca.

        La tasa guardada no depende de la tabla: un borrador creado antes de
        que se cargara la tasa del día conserva la de ayer. Aquí se marca
        para recálculo (vía `modified`, que también arrastra los Bs de las
        líneas y los totales) y se calcula con la tabla de este momento. Si
        no hay tasa del día se usa la última anterior y queda registrada su
        fecha en `l10n_ve_bs_rate_date`.
        """
        to_refresh = self.filtered(
            lambda m: m.state == "draft" and not m.l10n_ve_bs_rate_override)
        if to_refresh:
            to_refresh.modified(["l10n_ve_bs_rate_override"])
        posted = super()._post(soft=soft)
        # Re-postear (borrador → confirmado otra vez) debe tomar la tasa
        # vigente a la fecha final del documento: `super` pudo fijar
        # `invoice_date` y el recálculo pendiente no debe tropezar con el
        # congelado de `_l10n_ve_bs_frozen_rates` si la BD aún dice "posted".
        refresh = (posted & to_refresh).with_context(l10n_ve_bs_refresh=True)
        if refresh:
            # Mecanismo estándar de recálculo (no asignación directa, que haría
            # un write() por campo sobre el asiento confirmado): `modified`
            # marca la tasa y, en cadena, los Bs de las líneas y los totales;
            # `_recompute_recordset` calcula la tasa YA con el contexto de
            # refresco, y el resto se resuelve en el flush.
            refresh.modified(["l10n_ve_bs_rate_override"])
            refresh._recompute_recordset([
                "l10n_ve_bs_rate", "l10n_ve_bs_rate_date",
                "l10n_ve_bs_rate_missing"])
        return posted


class ValidateAccountMove(models.TransientModel):
    """Confirmación masiva desde la lista de facturas.

    El asistente del core llama directo a `account.move._post`, sin pasar
    por `action_post`; sin este override la confirmación masiva usaría en
    silencio la tasa de otro día, contra la regla de pedir la tasa del día.
    Vive aquí y no en wizards/ porque es la misma regla de `account.move`.
    """

    _inherit = "validate.account.move"

    def validate_move(self):
        self.move_ids._l10n_ve_bs_check_today_rate()
        return super().validate_move()
