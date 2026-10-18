# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
"""v4 (SCS 523/2025) agrega rule_ve_reg_cesta_comp y rule_ve_liq_comp a
RULE_ACCOUNTS → re-mapear en upgrade. post_init_hook cubre desde v4 también
las compañías con chart ≠ ve_bw ya mapeadas a mano (p. ej. generic_coa):
detecta la regla básica con cuenta de débito y les corre map_rule_accounts
(que además crea 110202 vía MISSING_ACCOUNTS y la marca conciliable)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.l10n_ve_bw_payroll.hooks import post_init_hook


def migrate(cr, version):
    post_init_hook(api.Environment(cr, SUPERUSER_ID, {}))
