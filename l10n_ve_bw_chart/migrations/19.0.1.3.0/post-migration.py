# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
"""Marca como noupdate los xmlid del plan ve_bw que quedaron sin la bandera.

El cargador de plantillas registra cada registro del plan como
``account.<company_id>_ve_bw_*`` con ``noupdate=True``. En una base en producción, 12 de ellos
(7 cuentas, 4 impuestos y el grupo IVA 16 %) quedaron con ``noupdate=False``.
Como el xmlid vive en el módulo ``account``, al actualizar ``account`` Odoo los
trata como huérfanos e intenta borrarlos al final del ``-u``; el grupo IVA 16 %
está referenciado por los impuestos y el ``DELETE`` aborta la actualización.

Este script corre dentro del mismo ``-u`` antes de esa limpieza. Es idempotente.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        r"""
        UPDATE ir_model_data
           SET noupdate = TRUE
         WHERE module = 'account'
           AND name ~ '^[0-9]+_ve_bw_'
           AND NOT noupdate
     RETURNING model, name
        """
    )
    rows = cr.fetchall()
    for model, name in rows:
        _logger.info("l10n_ve_bw_chart: noupdate=True en account.%s (%s)", name, model)
    if rows:
        _logger.info("l10n_ve_bw_chart: %s xmlid del plan marcados noupdate", len(rows))
