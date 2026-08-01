# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    l10n_ve_machine_serial = fields.Char(
        string="Nº de registro de máquina fiscal",
        help="Número de registro de la máquina fiscal asociada a este punto de "
             "venta. Se indica en la fila diaria del Libro de Ventas "
             "(Reglamento LIVA art. 77, Parágrafo Segundo).",
    )
