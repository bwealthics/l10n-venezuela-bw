# Part of l10n_ve_bw. License LGPL-3.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_ve_municipal_name = fields.Char(
        related="company_id.l10n_ve_municipal_name",
        readonly=False,
    )
    l10n_ve_municipal_rate = fields.Float(
        related="company_id.l10n_ve_municipal_rate",
        readonly=False,
    )
    l10n_ve_municipal_minimum = fields.Monetary(
        related="company_id.l10n_ve_municipal_minimum",
        readonly=False,
    )
    l10n_ve_municipal_minimum_mmv = fields.Float(
        related="company_id.l10n_ve_municipal_minimum_mmv",
        readonly=False,
    )
    l10n_ve_municipal_tcmmv = fields.Float(
        related="company_id.l10n_ve_municipal_tcmmv",
        readonly=False,
    )
    l10n_ve_municipal_expense_account_id = fields.Many2one(
        related="company_id.l10n_ve_municipal_expense_account_id",
        readonly=False,
    )
    l10n_ve_municipal_payable_account_id = fields.Many2one(
        related="company_id.l10n_ve_municipal_payable_account_id",
        readonly=False,
    )
    l10n_ve_municipal_journal_id = fields.Many2one(
        related="company_id.l10n_ve_municipal_journal_id",
        readonly=False,
    )
