# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
from odoo import fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    # Vive en fiscal_books, con el Libro que lo lee: si estuviera en
    # fiscal_printer el wizard necesitaría guardas defensivas por si ese
    # módulo no está instalado. Campo PLANO por la misma razón documentada en
    # l10n_ve_bw_fiscal_printer/models/pos_order.py: solo los almacenados no
    # compute viajan al servidor en el sync del POS.
    l10n_ve_contingency_control = fields.Char(
        string="Nº de control (contingencia)",
        copy=False,
        readonly=True,
        index="btree_not_null",
        help="Nº de control del formato preimpreso del talonario autorizado "
             "que se usó para facturar esta orden mientras la máquina fiscal "
             "estaba caída (PA 0071 art. 11).",
    )
