# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_l10n_ve_machine_serial = fields.Char(
        related="pos_config_id.l10n_ve_machine_serial",
        readonly=False,
        string="Nº de registro de máquina fiscal",
    )
