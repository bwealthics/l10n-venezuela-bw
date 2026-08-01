# Part of l10n_ve_bw_igtf. License LGPL-3.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_ve_igtf_pct = fields.Float(
        related="company_id.l10n_ve_igtf_pct",
        readonly=False,
    )
    l10n_ve_igtf_expense_account_id = fields.Many2one(
        related="company_id.l10n_ve_igtf_expense_account_id",
        readonly=False,
    )
    l10n_ve_igtf_perception_account_id = fields.Many2one(
        related="company_id.l10n_ve_igtf_perception_account_id",
        readonly=False,
    )
