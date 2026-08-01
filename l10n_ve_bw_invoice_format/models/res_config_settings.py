# Part of l10n_ve_bw_invoice_format. License LGPL-3.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_ve_printer_name = fields.Char(
        related="company_id.l10n_ve_printer_name", readonly=False)
    l10n_ve_printer_vat = fields.Char(
        related="company_id.l10n_ve_printer_vat", readonly=False)
    l10n_ve_printer_auth_number = fields.Char(
        related="company_id.l10n_ve_printer_auth_number", readonly=False)
    l10n_ve_printer_auth_date = fields.Date(
        related="company_id.l10n_ve_printer_auth_date", readonly=False)
    l10n_ve_control_range_from = fields.Char(
        related="company_id.l10n_ve_control_range_from", readonly=False)
    l10n_ve_control_range_to = fields.Char(
        related="company_id.l10n_ve_control_range_to", readonly=False)
