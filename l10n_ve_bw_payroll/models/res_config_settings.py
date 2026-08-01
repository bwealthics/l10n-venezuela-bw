# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_ve_ivss_employer_number = fields.Char(
        related="company_id.l10n_ve_ivss_employer_number", readonly=False)
    l10n_ve_faov_employer_number = fields.Char(
        related="company_id.l10n_ve_faov_employer_number", readonly=False)
    l10n_ve_inces_employer_number = fields.Char(
        related="company_id.l10n_ve_inces_employer_number", readonly=False)
    l10n_ve_inces_contributor = fields.Boolean(
        related="company_id.l10n_ve_inces_contributor", readonly=False)
    l10n_ve_ivss_risk = fields.Selection(
        related="company_id.l10n_ve_ivss_risk", readonly=False)
    l10n_ve_utilidades_days = fields.Integer(
        related="company_id.l10n_ve_utilidades_days", readonly=False)
    l10n_ve_prestaciones_mode = fields.Selection(
        related="company_id.l10n_ve_prestaciones_mode", readonly=False)
