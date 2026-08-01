# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_ve_iva_wh_agent_account_id = fields.Many2one(
        related="company_id.l10n_ve_iva_wh_agent_account_id",
        readonly=False,
    )
    l10n_ve_iva_wh_received_account_id = fields.Many2one(
        related="company_id.l10n_ve_iva_wh_received_account_id",
        readonly=False,
    )
