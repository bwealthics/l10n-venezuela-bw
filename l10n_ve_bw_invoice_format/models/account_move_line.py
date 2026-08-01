# Part of l10n_ve_bw_invoice_format. License LGPL-3.
from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _l10n_ve_is_exempt(self):
        """Línea exenta, exonerada o no sujeta al IVA.

        La norma las marca a todas con la MISMA letra "(E)" —no existe una
        letra distinta por concepto ni una "G" para las gravadas— así que un
        solo predicado basta (PA 0071 arts. 13.8, 14.5 y 32.2; PA 000102
        art. 7.8).

        El criterio es el mismo que usa el Libro de Ventas para su columna de
        exentos (l10n_ve_bw_fiscal_books): ningún impuesto con alícuota. Si
        divergieran, el PDF y el libro se contradirían ante un fiscalizador.
        """
        self.ensure_one()
        return self.display_type == "product" and not any(
            tax.amount for tax in self.tax_ids)
