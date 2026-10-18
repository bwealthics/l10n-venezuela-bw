# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
"""v4.5: rule_ve_liq_dias y rule_ve_liq_cesta entran a RULE_ACCOUNTS ->
re-mapear las cuentas en las compañías VE ya instaladas."""
from odoo import SUPERUSER_ID, api

from odoo.addons.l10n_ve_bw_payroll.hooks import post_init_hook


def migrate(cr, version):
    post_init_hook(api.Environment(cr, SUPERUSER_ID, {}))
