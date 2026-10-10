# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
from odoo import api, fields, models

# Líneas de maquetación de la factura: no son apuntes contables (no tienen
# cuenta ni saldo) y no entran ni en la conversión ni en el recuadre.
_LAYOUT_TYPES = ("line_section", "line_subsection", "line_note")


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    l10n_ve_bs_currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.l10n_ve_bs_currency_id",
        string="Moneda Bs",
    )

    # Montos en Bs ALMACENADOS por apunte: los libros legales (Diario, Mayor,
    # Balance, Libros IVA) se arman sumando estos campos, nunca reconvirtiendo
    # al vuelo, para que un reporte de hoy diga lo mismo que el de ayer aunque
    # alguien edite la tabla de tasas.
    l10n_ve_balance_bs = fields.Monetary(
        string="Saldo Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_bs", store=True, copy=False,
        aggregator="sum",
    )
    l10n_ve_debit_bs = fields.Monetary(
        string="Debe Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_bs", store=True, copy=False,
        aggregator="sum",
    )
    l10n_ve_credit_bs = fields.Monetary(
        string="Haber Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_bs", store=True, copy=False,
        aggregator="sum",
    )
    l10n_ve_bs_adjustment = fields.Monetary(
        string="Ajuste Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_bs", store=True, copy=False,
        aggregator="sum",
        help="Bolívares que esta línea absorbió para que el asiento cuadre en "
             "Bs (redondeos, o la diferencia de cambio real cuando el asiento "
             "mezcla líneas en Bs y en otra moneda).",
    )
    l10n_ve_price_subtotal_bs = fields.Monetary(
        string="Subtotal Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_price_bs", store=True, copy=False,
        aggregator="sum",
    )
    l10n_ve_price_total_bs = fields.Monetary(
        string="Total Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_price_bs", store=True, copy=False,
        aggregator="sum",
    )
    l10n_ve_price_unit_bs = fields.Monetary(
        string="Precio Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_price_unit_bs",
    )

    # ------------------------------------------------------------------
    # Conversión por asiento
    # ------------------------------------------------------------------
    # Las dependencias de las líneas HERMANAS incluyen cuenta, tipo de línea
    # y diario: el recuadre elige la línea que absorbe el residuo por esos
    # datos de TODO el asiento (ver `_l10n_ve_bs_adjustment_line`). Sin ellas,
    # cambiar la cuenta de otra línea movería el destino del ajuste a una
    # línea que no se recalcula y el asiento dejaría de cuadrar en Bs.
    @api.depends(
        "balance", "amount_currency", "currency_id", "display_type",
        "account_id", "company_id",
        "move_id.l10n_ve_bs_rate",
        "move_id.journal_id",
        "move_id.line_ids.balance",
        "move_id.line_ids.amount_currency",
        "move_id.line_ids.currency_id",
        "move_id.line_ids.account_id",
        "move_id.line_ids.display_type",
    )
    def _compute_l10n_ve_bs(self):
        """Bs de cada apunte, calculados por asiento COMPLETO.

        El recuadre necesita ver todas las líneas del asiento (incluidas las
        NewId del onchange), así que se calcula el asiento entero y solo se
        asigna a las líneas de `self`: asignar a una línea ajena fuera del
        contexto protegido del compute dispararía un write() por línea.
        Agrupar por asiento evita el N+1 en el `-i` (~12.000 apuntes).
        """
        values = {}
        for move in self.grouped("move_id"):
            if move:
                values.update(self._l10n_ve_bs_move_values(move))
        for line in self:
            amount, adjustment = values.get(line.id, (0.0, 0.0))
            line.l10n_ve_balance_bs = amount
            line.l10n_ve_debit_bs = amount if amount > 0.0 else 0.0
            line.l10n_ve_credit_bs = -amount if amount < 0.0 else 0.0
            line.l10n_ve_bs_adjustment = adjustment

    @api.model
    def _l10n_ve_bs_move_values(self, move):
        """Regla de conversión del asiento `move`.

        :return: ``{line.id: (bs, ajuste)}`` para cada línea del asiento.

        1. Línea en Bs: su `amount_currency` tal cual — los bancos en VES
           cuadran así con su extracto, sin pasar por la tasa.
        2. Bs es la moneda de la compañía: el `balance` ya está en Bs.
        3. Otra moneda (USD, VEB, EUR…): `balance` × tasa del asiento; sin
           tasa, 0 (y el asiento queda marcado como sin tasa).
        4. Recuadre: lo que falte para que el asiento sume cero en Bs lo
           absorbe UNA línea, elegida por `_l10n_ve_bs_adjustment_line`, y
           queda a la vista en `l10n_ve_bs_adjustment`.
        """
        lines = move.line_ids.filtered(
            lambda l: l.display_type not in _LAYOUT_TYPES)
        company = move.company_id
        bs = company.l10n_ve_bs_currency_id
        if not bs or not lines:
            return {line.id: (0.0, 0.0) for line in move.line_ids}
        company_currency = company.currency_id
        bs_is_company = bs == company_currency
        rate = move.l10n_ve_bs_rate

        amounts = {}
        unconverted = False
        for line in lines:
            if line.currency_id == bs:
                amount = line.amount_currency
            elif bs_is_company:
                amount = line.balance
            elif rate:
                amount = line.balance * rate
            else:
                amount = 0.0
                if not company_currency.is_zero(line.balance):
                    unconverted = True
            amounts[line.id] = bs.round(amount)

        adjustments = {}
        residual = bs.round(-sum(amounts.values()))
        # Sin tasa no se recuadra: repartir el total del asiento sobre una
        # línea sería inventar bolívares. El asiento queda marcado
        # (`l10n_ve_bs_rate_missing`) y aparece en las advertencias.
        # Tampoco se recuadra un asiento que aún no cuadra en la moneda de la
        # compañía: es el borrador del formulario antes de que Odoo genere las
        # líneas de impuesto y de cobro. Ahí el "residuo" no es redondeo ni
        # diferencia de cambio sino medio asiento ausente, y absorberlo dejaría
        # en cero el Bs de la única línea de producto.
        balanced = company_currency.is_zero(sum(lines.mapped("balance")))
        if not bs.is_zero(residual) and not unconverted and balanced:
            target = self._l10n_ve_bs_adjustment_line(move, lines, bs)
            amounts[target.id] = bs.round(amounts[target.id] + residual)
            adjustments[target.id] = residual

        result = {line.id: (0.0, 0.0) for line in move.line_ids}
        for line_id, amount in amounts.items():
            result[line_id] = (amount, adjustments.get(line_id, 0.0))
        return result

    @api.model
    def _l10n_ve_bs_adjustment_line(self, move, lines, bs):
        """Línea que absorbe el residuo en Bs del asiento.

        Candidatas, en orden de preferencia:
        - Líneas en una moneda distinta de Bs: su Bs sale de una tasa, así que
          un céntimo de redondeo (o la diferencia de cambio real de los
          asientos mixtos del diario CBSL) es legítimo ahí; una línea en Bs
          trae el monto exacto del banco y no se toca.
        - Si todas están en Bs: las que no son de liquidez, para que el banco
          siga cuadrando con su extracto.
        - Si no queda ninguna: todas.
        Entre candidatas manda la cuenta por cobrar/pagar (es la que se
        concilia contra el pago y define el saldo Bs del documento), luego el
        monto más grande (el residuo pesa menos en proporción) y por último
        el orden de creación, para que el resultado sea estable.
        """
        company_currency = move.company_id.currency_id
        candidates = lines.filtered(
            lambda l: l.currency_id != bs
            and not company_currency.is_zero(l.balance))
        if not candidates:
            liquidity_account = move.journal_id.default_account_id
            candidates = lines.filtered(
                lambda l: l.account_id.account_type != "asset_cash"
                and l.account_id != liquidity_account)
        if not candidates:
            candidates = lines
        in_bs = all(line.currency_id == bs for line in candidates)
        position = {line.id: idx for idx, line in enumerate(move.line_ids)}

        def sort_key(line):
            preferred = (
                line.display_type == "payment_term"
                or line.account_id.account_type in (
                    "asset_receivable", "liability_payable")
            )
            size = abs(line.amount_currency if in_bs else line.balance)
            # Los NewId del onchange no tienen id comparable: se usa el id de
            # origen si lo hay y, si no, el orden dentro de move.line_ids.
            origin_id = line._origin.id
            order = (0, origin_id) if origin_id else (1, position[line.id])
            return (0 if preferred else 1, -size, order)

        return min(candidates, key=sort_key)

    # ------------------------------------------------------------------
    # Columnas Bs de la factura
    # ------------------------------------------------------------------
    @api.depends(
        "display_type", "l10n_ve_balance_bs", "move_id.move_type",
        "price_subtotal", "price_total", "currency_id",
    )
    def _compute_l10n_ve_price_bs(self):
        """Subtotal y total Bs de las líneas de producto.

        El subtotal es el saldo Bs del apunte con el signo de la factura, así
        la suma de las líneas cuadra al céntimo con la base imponible Bs del
        documento. El total aplica a ese subtotal la misma proporción
        total/subtotal de la línea en la moneda del documento.
        """
        for line in self:
            bs = line.company_id.l10n_ve_bs_currency_id
            if not bs or line.display_type != "product":
                line.l10n_ve_price_subtotal_bs = 0.0
                line.l10n_ve_price_total_bs = 0.0
                continue
            subtotal = bs.round(
                line.move_id.direction_sign * line.l10n_ve_balance_bs)
            if line.currency_id == bs:
                total = line.price_total
            elif line.price_subtotal:
                total = bs.round(
                    subtotal * line.price_total / line.price_subtotal)
            else:
                total = 0.0
            line.l10n_ve_price_subtotal_bs = subtotal
            line.l10n_ve_price_total_bs = total

    @api.depends(
        "price_unit", "price_subtotal", "currency_id",
        "l10n_ve_price_subtotal_bs",
        "move_id.l10n_ve_bs_rate", "move_id.invoice_currency_rate",
    )
    def _compute_l10n_ve_price_unit_bs(self):
        """Precio unitario en Bs (no almacenado: solo se muestra).

        Con precios IVA incluido el precio unitario lleva el IVA dentro, así
        que se convierte con el factor EFECTIVO de la línea (subtotal Bs /
        subtotal) y cantidad × precio Bs cuadra con el importe Bs impreso.
        Sin subtotal (cantidad 0, descuento 100 %) se usa la tasa del asiento
        llevando antes el precio a la moneda de la compañía.
        """
        for line in self:
            bs = line.company_id.l10n_ve_bs_currency_id
            if not bs:
                line.l10n_ve_price_unit_bs = 0.0
            elif line.currency_id == bs:
                line.l10n_ve_price_unit_bs = line.price_unit
            elif line.price_subtotal:
                line.l10n_ve_price_unit_bs = bs.round(
                    line.price_unit * line.l10n_ve_price_subtotal_bs
                    / line.price_subtotal)
            else:
                move = line.move_id
                line.l10n_ve_price_unit_bs = bs.round(
                    line.price_unit * move.l10n_ve_bs_rate
                    / (move.invoice_currency_rate or 1.0))
