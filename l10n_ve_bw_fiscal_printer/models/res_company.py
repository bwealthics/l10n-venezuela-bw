# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_printer. License LGPL-3.
from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model
    def _load_pos_data_fields(self, config):
        # SPE (l10n_ve_bw_chart) + % IGTF (l10n_ve_bw_igtf) gatean la rama
        # IGTF del payload en el frontend.
        return super()._load_pos_data_fields(config) + [
            "l10n_ve_is_spe", "l10n_ve_igtf_pct"]
