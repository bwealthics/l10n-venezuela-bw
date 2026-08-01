# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
"""v3 agrega rule_ve_vac_inces_pat a RULE_ACCOUNTS → re-mapear en upgrade."""
from odoo import SUPERUSER_ID, api

from odoo.addons.l10n_ve_bw_payroll.hooks import post_init_hook


def migrate(cr, version):
    post_init_hook(api.Environment(cr, SUPERUSER_ID, {}))
