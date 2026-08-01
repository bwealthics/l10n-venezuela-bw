# Part of l10n_ve_bw_payroll. License LGPL-3.
"""Re-mapea las cuentas de las reglas salariales en el upgrade v1→v2.

post_init_hook solo corre al INSTALAR; este script corre en el -u después de
cargar los data XML (las reglas nuevas de vacaciones/liquidación ya existen).
Regla del módulo: cada versión que cambie RULE_ACCOUNTS trae su propia
carpeta migrations/<versión>/ con este mismo patrón.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.l10n_ve_bw_payroll.hooks import post_init_hook


def migrate(cr, version):
    post_init_hook(api.Environment(cr, SUPERUSER_ID, {}))
