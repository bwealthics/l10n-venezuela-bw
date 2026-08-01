# Part of l10n_ve_bw_invoice_format. License LGPL-3.
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_ve_control_date = fields.Date(
        string="Fecha de asignación del Nº de Control",
        copy=False,
        help="Fecha en que la imprenta autorizada asignó el Nº de control "
             "(PA SNAT/2024/000102 art. 7.15). La rellena el conector de "
             "imprenta digital; bajo forma libre se transcribe del talonario.",
    )

    def _l10n_ve_legal_datetime(self):
        """Fecha —y hora, cuando se conoce— en el formato del art. 7.6 de la
        PA SNAT/2024/000102.

        El artículo pide DDMMAAAA y HH.MM.SS con a.m./p.m., pero admite
        separadores (igual que el art. 34 de la PA 0071), así que se emite UNA
        sola línea legible en vez de duplicar la fecha del documento.
        """
        self.ensure_one()
        if not self.invoice_date:
            return ""
        legal_date = self.invoice_date.strftime("%d-%m-%Y")
        hour = self._l10n_ve_emission_time()
        return "%s %s" % (legal_date, hour) if hour else legal_date

    def _l10n_ve_emission_time(self):
        """Hora de emisión en HH.MM.SS con a.m./p.m., o cadena vacía.

        Solo se imprime cuando de verdad se conoce: hoy la sella la máquina
        fiscal en l10n_ve_fiscal_date, y mañana la aportará el conector de
        imprenta digital por la misma vía. Nunca se inventa una hora — un
        documento fiscal con una hora aproximada es peor que sin ella.
        La comprobación por _fields evita una dependencia dura de
        l10n_ve_bw_fiscal_printer (mismo patrón que el wizard de los libros).
        """
        self.ensure_one()
        if "l10n_ve_fiscal_date" not in self._fields:
            return ""
        raw = self.l10n_ve_fiscal_date or ""
        stamp = fields.Datetime.to_datetime(raw) if len(raw) >= 19 else None
        if not stamp:
            return ""
        # %p da AM/PM; la norma escribe "a.m"/"p.m".
        return stamp.strftime("%I.%M.%S %p").replace(
            "AM", "a.m").replace("PM", "p.m")
