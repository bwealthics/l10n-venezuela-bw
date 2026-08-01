# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
import calendar
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Numeración art. 16 PA SNAT/2025/000054: AAAAMM + secuencial de 8 dígitos.
VOUCHER_NUMBER_RE = re.compile(r"^\d{4}(0[1-9]|1[0-2])\d{8}$")


class L10nVeIvaWhVoucher(models.Model):
    _name = "l10n.ve.iva.wh.voucher"
    _description = "Comprobante de Retención de IVA"
    _order = "date desc, number desc, id desc"
    _rec_name = "number"
    _check_company_auto = True

    number = fields.Char(
        string="Número de Comprobante",
        copy=False,
        readonly=True,
        index=True,
        help="Numeración consecutiva de 14 caracteres: AAAAMM + secuencial "
             "de 8 dígitos (art. 16, PA SNAT/2025/000054).",
    )
    date = fields.Date(
        string="Fecha de Emisión",
        required=True,
        default=fields.Date.context_today,
    )
    fiscal_period = fields.Char(
        string="Período Fiscal",
        compute="_compute_fiscal_period",
        help="Período de imposición en formato AAAAMM.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Sujeto Retenido",
        required=True,
    )
    payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Pago",
        copy=False,
        check_company=True,
    )
    move_ids = fields.Many2many(
        comodel_name="account.move",
        string="Documentos Retenidos",
    )
    base_amount = fields.Monetary(string="Base Imponible")
    tax_amount = fields.Monetary(string="Impuesto Causado (IVA)")
    withheld_amount = fields.Monetary(string="Impuesto Retenido")
    exempt_amount = fields.Monetary(string="Monto Exento")
    wh_rate = fields.Float(string="Porcentaje de Retención (%)")
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("posted", "Emitido"),
            ("cancel", "Anulado"),
        ],
        string="Estado",
        default="draft",
        copy=False,
        required=True,
    )

    @api.depends("date")
    def _compute_fiscal_period(self):
        for voucher in self:
            voucher.fiscal_period = voucher.date and voucher.date.strftime("%Y%m") or False

    @api.constrains("number")
    def _check_number(self):
        for voucher in self:
            if voucher.number and not VOUCHER_NUMBER_RE.match(voucher.number):
                raise ValidationError(_(
                    "El número de comprobante de retención debe tener 14 dígitos: "
                    "AAAAMM + secuencial de 8 dígitos (ej. 20260700000001)."
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("number"):
                company = (
                    self.env["res.company"].browse(vals["company_id"])
                    if vals.get("company_id") else self.env.company
                )
                vals["number"] = self._l10n_ve_next_voucher_number(
                    vals.get("date"), company=company,
                )
        return super().create(vals_list)

    @api.model
    def _l10n_ve_next_voucher_number(self, seq_date=None, company=None):
        """Siguiente correlativo fiscal AAAAMM + 8 dígitos.

        La secuencia es POR COMPAÑÍA (get-or-create con company_id: el
        correlativo del agente de retención no puede compartirse entre
        compañías) y usa rangos de fecha MENSUALES para que el secuencial
        reinicie en 00000001 cada período AAAAMM (art. 16,
        PA SNAT/2025/000054).
        """
        company = company or self.env.company
        seq_date = fields.Date.to_date(seq_date) or fields.Date.context_today(self)
        Sequence = self.env["ir.sequence"].sudo()
        sequence = Sequence.search([
            ("code", "=", "l10n.ve.iva.wh.voucher"),
            ("company_id", "=", company.id),
        ], limit=1)
        if not sequence:
            sequence = Sequence.create({
                "name": _("Comprobante de Retención de IVA (%s)", company.name),
                "code": "l10n.ve.iva.wh.voucher",
                "prefix": "%(year)s%(month)s",
                "padding": 8,
                "implementation": "no_gap",
                "use_date_range": True,
                "company_id": company.id,
            })
        elif not sequence.use_date_range:
            sequence.use_date_range = True
        # Rango mensual explícito: sin él, ir.sequence crea rangos anuales y
        # el secuencial no reiniciaría cada mes.
        DateRange = self.env["ir.sequence.date_range"].sudo()
        if not DateRange.search_count([
            ("sequence_id", "=", sequence.id),
            ("date_from", "<=", seq_date),
            ("date_to", ">=", seq_date),
        ]):
            DateRange.create({
                "sequence_id": sequence.id,
                "date_from": seq_date.replace(day=1),
                "date_to": seq_date.replace(
                    day=calendar.monthrange(seq_date.year, seq_date.month)[1],
                ),
            })
        number = sequence.next_by_id(sequence_date=seq_date)
        if not number:
            raise UserError(_(
                "No se pudo generar el correlativo de comprobantes de retención "
                "de IVA (código l10n.ve.iva.wh.voucher) para la compañía %s.",
                company.display_name,
            ))
        return number

    @api.ondelete(at_uninstall=False)
    def _unlink_except_posted(self):
        if any(voucher.state == "posted" for voucher in self):
            raise UserError(_(
                "No se puede eliminar un comprobante de retención emitido: "
                "anúlelo primero (el correlativo fiscal debe conservarse)."
            ))

    def action_post(self):
        self.write({"state": "posted"})

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_draft(self):
        self.write({"state": "draft"})

    # -------------------------------------------------------------------------
    # HELPERS compartidos (comprobante PDF, wizard de pago y export TXT)
    # -------------------------------------------------------------------------

    @api.model
    def _l10n_ve_format_rif(self, vat):
        """J-12345678-9 -> J123456789 (formato del portal, sin guiones)."""
        return re.sub(r"[^A-Z0-9]", "", (vat or "").upper())

    @api.model
    def _l10n_ve_get_ves_currency(self):
        ves = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "VES")], limit=1,
        )
        if not ves:
            raise UserError(_(
                "No existe la moneda VES (Bolívar) en la base de datos; "
                "es necesaria para expresar los montos en bolívares."
            ))
        return ves

    @api.model
    def _l10n_ve_doc_type(self, move):
        """Tipo de documento SENIAT: 01 factura, 02 nota de débito, 03 nota de crédito."""
        if move.move_type == "in_refund":
            return "03"
        if "debit_origin_id" in move._fields and move.debit_origin_id:
            return "02"
        return "01"

    @api.model
    def _l10n_ve_move_iva_buckets(self, move):
        """Bases gravadas e IVA causado POR ALÍCUOTA legal (16/8/31...) de un
        documento, en moneda de la compañía.

        Devuelve ``(buckets, exempt)`` donde ``buckets`` es
        ``{alicuota: {"base": x, "tax": y}}``. Asume impuestos IVA de tipo
        porcentaje con una alícuota por línea, como los define el plan ve_bw.
        """
        buckets = {}
        exempt = 0.0
        for line in move.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
            amount = abs(line.balance)
            leaf_taxes = line.tax_ids
            group_taxes = leaf_taxes.filtered(lambda t: t.amount_type == "group")
            leaf_taxes = (leaf_taxes - group_taxes) | group_taxes.children_tax_ids
            rate = round(sum(t.amount for t in leaf_taxes), 2)
            if rate:
                bucket = buckets.setdefault(rate, {"base": 0.0, "tax": 0.0})
                bucket["base"] += amount
            else:
                exempt += amount
        for tax_line in move.line_ids.filtered("tax_line_id"):
            rate = round(tax_line.tax_line_id.amount, 2)
            if not rate:
                continue
            bucket = buckets.setdefault(rate, {"base": 0.0, "tax": 0.0})
            bucket["tax"] += abs(tax_line.balance)
        return buckets, exempt

    @api.model
    def _l10n_ve_move_iva_amounts(self, move):
        """Agregado por documento (todas las alícuotas): base gravada, monto
        exento, IVA causado y alícuota efectiva, en moneda de la compañía."""
        buckets, exempt = self._l10n_ve_move_iva_buckets(move)
        base = sum(bucket["base"] for bucket in buckets.values())
        tax = sum(bucket["tax"] for bucket in buckets.values())
        rate = round(tax / base * 100.0, 2) if base else 0.0
        return {"base": base, "exempt": exempt, "tax": tax, "rate": rate}

    def _l10n_ve_get_amount_for_move(self, move):
        """Interfaz pública (usada por los libros fiscales): IVA retenido de
        ESTE comprobante atribuible a ``move``, en moneda de la compañía y
        CON SIGNO (negativo para notas de crédito), según el prorrateo
        interno del comprobante: proporcional al IVA causado NETO de cada
        documento. Así la factura declara su retención plena (tasa × su IVA)
        y la NC la resta, y la suma por documento reproduce el total retenido."""
        self.ensure_one()
        if not move or move not in self.move_ids:
            return 0.0
        taxes = {}
        for m in self.move_ids:
            tax = self._l10n_ve_move_iva_amounts(m)["tax"]
            if m.move_type in ("in_refund", "out_refund"):
                tax = -tax
            taxes[m.id] = tax
        total_tax = sum(taxes.values())
        if not self.currency_id.is_zero(total_tax):
            share = taxes[move.id] / total_tax
        else:
            share = 1.0 / len(self.move_ids)
        return self.currency_id.round(self.withheld_amount * share)

    def _l10n_ve_get_report_lines(self):
        """Detalle del comprobante en moneda de la compañía: UNA línea por
        documento y POR ALÍCUOTA (formato TXT 99035). El impuesto retenido se
        distribuye proporcionalmente al IVA causado de cada documento y,
        dentro del documento, al IVA de cada alícuota (el residuo de redondeo
        se asigna a la última alícuota para conservar el total exacto)."""
        self.ensure_one()
        lines = []
        for move in self.move_ids:
            buckets, exempt = self._l10n_ve_move_iva_buckets(move)
            move_withheld = self._l10n_ve_get_amount_for_move(move)
            move_tax = sum(bucket["tax"] for bucket in buckets.values())
            # NC con signo negativo en base/IVA/retenido/total: el TXT netea
            # por documento y el total declarado = withheld_amount exacto.
            sign = -1.0 if move.move_type in ("in_refund", "out_refund") else 1.0
            control_number = (
                move.l10n_ve_control_number
                if "l10n_ve_control_number" in move._fields else False
            )
            common = {
                "move": move,
                "doc_type": self._l10n_ve_doc_type(move),
                "doc_number": move.ref or move.name or "",
                "control_number": control_number or "",
                # Mismo criterio que el nº de documento (col. 7 del TXT): el
                # documento afectado por la NC se declara por su ref (número
                # de factura del proveedor), no por el nombre interno de Odoo.
                "affected": (
                    move.reversed_entry_id.ref
                    or move.reversed_entry_id.name
                    or ""
                ),
                "date": move.invoice_date or move.date,
                "total": sign * abs(move.amount_total_signed),
            }
            if not buckets:
                lines.append({
                    **common,
                    "base": 0.0,
                    "exempt": sign * exempt,
                    "tax": 0.0,
                    "rate": 0.0,
                    "withheld": 0.0,
                })
                continue
            sorted_rates = sorted(buckets)
            remaining = move_withheld
            for index, rate in enumerate(sorted_rates):
                bucket = buckets[rate]
                if index == len(sorted_rates) - 1:
                    withheld = remaining
                else:
                    withheld = self.currency_id.round(
                        move_withheld * (bucket["tax"] / move_tax) if move_tax else 0.0
                    )
                    remaining -= withheld
                lines.append({
                    **common,
                    "base": sign * bucket["base"],
                    "exempt": sign * exempt if index == 0 else 0.0,
                    "tax": sign * bucket["tax"],
                    "rate": rate,
                    "withheld": withheld,
                })
        return lines
