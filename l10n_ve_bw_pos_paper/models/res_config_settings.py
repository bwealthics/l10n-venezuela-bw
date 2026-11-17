# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_paper. License LGPL-3.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_l10n_ve_paper_mode = fields.Selection(
        related="pos_config_id.l10n_ve_paper_mode", readonly=False)
    pos_l10n_ve_paper_batch_id = fields.Many2one(
        related="pos_config_id.l10n_ve_paper_batch_id", readonly=False)
    pos_l10n_ve_contingency_journal_id = fields.Many2one(
        related="pos_config_id.l10n_ve_contingency_journal_id", readonly=False)
