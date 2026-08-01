# Part of l10n_ve_bw. License LGPL-3.
import base64
import calendar
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class L10nVeIvaWhTxtExport(models.TransientModel):
    _name = "l10n.ve.iva.wh.txt.export"
    _description = "Exportar TXT de Retenciones de IVA (Forma 99035)"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string="Desde",
        required=True,
        default=lambda self: self._default_date_from(),
    )
    date_to = fields.Date(
        string="Hasta",
        required=True,
        default=lambda self: self._default_date_to(),
    )
    file_data = fields.Binary(string="Archivo TXT", readonly=True)
    file_name = fields.Char()

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return today.replace(day=1) if today.day <= 15 else today.replace(day=16)

    @api.model
    def _default_date_to(self):
        today = fields.Date.context_today(self)
        if today.day <= 15:
            return today.replace(day=15)
        return today.replace(day=calendar.monthrange(today.year, today.month)[1])

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_(
                    "La fecha inicial de la quincena no puede ser posterior a la final."
                ))

    @api.model
    def _sanitize(self, value, size=20):
        return re.sub(r"[\t\r\n]", " ", value or "").strip()[:size]

    def action_generate(self):
        self.ensure_one()
        company = self.company_id
        Voucher = self.env["l10n.ve.iva.wh.voucher"]
        rif_agent = Voucher._l10n_ve_format_rif(company.vat)
        if not rif_agent:
            raise UserError(_(
                "Configure el RIF de la compañía %s (campo NIF) antes de exportar.",
                company.display_name,
            ))
        ves = Voucher._l10n_ve_get_ves_currency()
        vouchers = Voucher.search([
            ("company_id", "=", company.id),
            ("state", "=", "posted"),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ], order="number")
        if not vouchers:
            raise UserError(_(
                "No hay comprobantes de retención de IVA emitidos entre %(date_from)s "
                "y %(date_to)s.",
                date_from=self.date_from, date_to=self.date_to,
            ))
        rows = []
        for voucher in vouchers:
            period = voucher.date.strftime("%Y%m")
            rif_partner = Voucher._l10n_ve_format_rif(voucher.partner_id.vat)
            if not rif_partner:
                raise UserError(_(
                    "El proveedor %s no tiene RIF configurado (campo NIF).",
                    voucher.partner_id.display_name,
                ))
            for line in voucher._l10n_ve_get_report_lines():
                doc_date = line["date"]

                def to_ves(amount, _date=doc_date):
                    # Montos del documento en bolívares a la tasa BCV de la
                    # fecha del documento.
                    return company.currency_id._convert(amount, ves, company, _date)

                def to_ves_wh(amount, _date=voucher.date):
                    # El IVA retenido (col. 11) se practicó en el pago: se
                    # expresa en Bs a la tasa BCV de la fecha del COMPROBANTE,
                    # no de la factura.
                    return company.currency_id._convert(amount, ves, company, _date)

                # 16 columnas exactas de la spec SENIAT §5.3, tab-delimited.
                columns = [
                    rif_agent,                                    # 1 RIF agente
                    period,                                       # 2 período AAAAMM
                    doc_date.strftime("%Y-%m-%d"),                # 3 fecha factura
                    "C",                                          # 4 tipo operación
                    line["doc_type"],                             # 5 tipo documento
                    rif_partner,                                  # 6 RIF retenido
                    self._sanitize(line["doc_number"]) or "0",    # 7 nº documento
                    self._sanitize(line["control_number"]) or "0",  # 8 nº control
                    "%.2f" % to_ves(line["total"]),               # 9 monto total
                    "%.2f" % to_ves(line["base"]),                # 10 base imponible
                    "%.2f" % to_ves_wh(line["withheld"]),         # 11 IVA retenido
                    self._sanitize(line["affected"]) or "0",      # 12 doc afectado
                    voucher.number,                               # 13 nº comprobante
                    "%.2f" % to_ves(line["exempt"]),              # 14 monto exento
                    "%.2f" % line["rate"],                        # 15 alícuota
                    "0",                                          # 16 nº expediente
                ]
                rows.append("\t".join(columns))
        content = "\r\n".join(rows) + "\r\n"
        self.file_data = base64.b64encode(content.encode("utf-8"))
        self.file_name = "IVA_99035_%s_%s_%s.txt" % (
            rif_agent,
            self.date_from.strftime("%Y%m%d"),
            self.date_to.strftime("%Y%m%d"),
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Exportar TXT Retenciones IVA (99035)"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
