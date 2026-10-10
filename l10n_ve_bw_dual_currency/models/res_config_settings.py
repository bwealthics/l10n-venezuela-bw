# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Interruptores por compañía (no parámetros del sistema): cada compañía de
    # una base multiempresa decide cómo se ve SU comprobante.
    l10n_ve_show_line_amount_bs = fields.Boolean(
        related="company_id.l10n_ve_show_line_amount_bs", readonly=False)
    l10n_ve_show_line_price_bs = fields.Boolean(
        related="company_id.l10n_ve_show_line_price_bs", readonly=False)
    l10n_ve_bs_rate_cutoff = fields.Float(
        related="company_id.l10n_ve_bs_rate_cutoff", readonly=False)
