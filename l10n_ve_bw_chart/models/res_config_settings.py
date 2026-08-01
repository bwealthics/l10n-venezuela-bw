# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_ve_is_spe = fields.Boolean(
        related="company_id.l10n_ve_is_spe",
        readonly=False,
    )
    l10n_ve_spe_date = fields.Date(
        related="company_id.l10n_ve_spe_date",
        readonly=False,
    )
