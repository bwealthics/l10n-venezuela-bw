# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
"""El módulo YA está instalado en producción y `post_init_hook` solo corre al
INSTALAR: sin esta migración el diario de contingencia nunca se crearía.

Los diarios EXISTENTES se dejan a propósito sin canal. Fijar el canal bloquea
la edición manual del Nº de control, y eso es una decisión del contador —la
misma política que el hash de inalterabilidad, que también se activa a mano.
Sin canal el comportamiento es exactamente el de hoy, así que la migración no
cambia nada de lo que ya funciona.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.l10n_ve_bw_fiscal_books.hooks import create_contingency_journals


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    create_contingency_journals(env)
