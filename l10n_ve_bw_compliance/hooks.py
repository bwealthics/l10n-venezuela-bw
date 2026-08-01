# Part of l10n_ve_bw_compliance. License AGPL-3.
"""Reglas de auditoría sobre los modelos fiscales, creadas Y CONFIRMADAS.

Crear la regla no audita nada: OCA auditlog solo engancha los modelos cuyas
reglas están en estado 'confirmed' (auditlog_rule.py:241 y :269). Ese paso se
olvida siempre, así que va aquí y no en la documentación.

Se resuelven los modelos por NOMBRE y no por XML-ID a propósito: los ir.model
de los modelos heredados viven en el módulo que los define (account, base...)
y adivinar esos identificadores es una fuente de fallos de instalación.

Para re-ejecutarlo desde odoo-bin shell:

    from odoo.addons.l10n_ve_bw_compliance.hooks import ensure_audit_rules
    ensure_audit_rules(env)
"""
import logging

_logger = logging.getLogger(__name__)

# Modelos con relevancia fiscal. Se deja FUERA account.move.line a propósito:
# es el modelo de mayor volumen con diferencia (cada cierre de caja del POS
# genera cientos de líneas) y sus importes ya están protegidos por la cadena
# de hash del diario, que detecta cualquier alteración posterior. Si algún día
# hace falta, se añade aquí y se re-ejecuta.
AUDITED_MODELS = (
    "account.move",
    "account.journal",
    "account.tax",
    "res.company",
    "res.partner",
    "l10n.ve.islr.voucher",
    "l10n.ve.iva.wh.voucher",
)


def ensure_audit_rules(env):
    Rule = env["auditlog.rule"]
    IrModel = env["ir.model"]
    for model_name in AUDITED_MODELS:
        model = IrModel.sudo().search([("model", "=", model_name)], limit=1)
        if not model:
            _logger.warning(
                "l10n_ve_bw_compliance: el modelo %s no existe; sin regla de "
                "auditoría.", model_name)
            continue
        rule = Rule.search([("model_id", "=", model.id)], limit=1)
        if not rule:
            rule = Rule.create({
                "name": "VE Cumplimiento — %s" % model_name,
                "model_id": model.id,
                "log_create": True,
                "log_write": True,
                "log_unlink": True,
                # El propio README de OCA declara que el log de LECTURAS no
                # funciona en todos los modelos y "necesita investigación":
                # activarlo daría una falsa sensación de cobertura.
                "log_read": False,
                # 'full' guarda el valor ANTERIOR de cada campo, que es
                # justamente lo que un fiscalizador viene a ver.
                "log_type": "full",
            })
        if rule.state != "confirmed":
            rule.set_to_confirmed()
    _logger.info(
        "l10n_ve_bw_compliance: %s reglas de auditoría activas.",
        Rule.search_count([("state", "=", "confirmed")]))


def post_init_hook(env):
    ensure_audit_rules(env)
