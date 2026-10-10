# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
"""Recupera las cuentas de tránsito que Odoo autocreó en inglés.

Hasta la 19.0.1.1.0 la plantilla no declaraba
``account_journal_payment_debit_account_id`` ni
``account_journal_payment_credit_account_id``, así que al instalar el plan
``_create_outstanding_accounts`` creaba "Outstanding Receipts" y "Outstanding
Payments" bajo el prefijo de banco, en inglés, y las líneas de método de pago
de los diarios bancarios quedaban apuntando a ellas.

Desde la 19.0.1.2.0 esas dos cuentas son las 101202 y 101203 del plan. En una
base ya instalada el CSV no se recarga (los registros llevan noupdate), así
que este script hace el traspaso:

1. repunta el xmlid a la cuenta correcta del plan;
2. mueve las líneas de método de pago de los diarios a esa cuenta;
3. archiva la cuenta autocreada **solo si nunca se usó**. Si tiene apuntes se
   deja activa y se avisa en el log, porque archivarla escondería saldo.

Es idempotente: si ya se corrió, no encuentra nada que mover.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# xmlid que espera el core  ->  código de la cuenta del plan que lo sustituye
MAPPING = {
    "account_journal_payment_debit_account_id": "101202",
    "account_journal_payment_credit_account_id": "101203",
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env["res.company"].search([("chart_template", "=", "ve_bw")])
    if not companies:
        return

    for company in companies:
        env_c = env["account.account"].with_company(company)
        accounts = env_c.search(env_c._check_company_domain(company.id))

        for xmlid, code in MAPPING.items():
            target = accounts.filtered(lambda a: a.code == code)[:1]
            if not target:
                _logger.warning(
                    "l10n_ve_bw_chart: la compañía %s no tiene la cuenta %s; "
                    "se omite el traspaso de %s",
                    company.name, code, xmlid,
                )
                continue

            full_xmlid = f"account.{company.id}_{xmlid}"
            data = env["ir.model.data"].search(
                [("complete_name", "=", full_xmlid)], limit=1
            )
            legacy = None
            if data and data.model == "account.account" and data.res_id != target.id:
                legacy = env["account.account"].browse(data.res_id).exists()
                data.res_id = target.id
                _logger.info(
                    "l10n_ve_bw_chart: %s repuntado a %s (%s) en %s",
                    xmlid, target.code, target.name, company.name,
                )
            elif not data:
                env["ir.model.data"].create({
                    "module": "account",
                    "name": f"{company.id}_{xmlid}",
                    "model": "account.account",
                    "res_id": target.id,
                    "noupdate": True,
                })

            # Las líneas de método de pago que apuntaban a la cuenta vieja.
            if legacy:
                lines = env["account.payment.method.line"].search([
                    ("payment_account_id", "=", legacy.id),
                    ("journal_id.company_id", "=", company.id),
                ])
                if lines:
                    lines.payment_account_id = target
                    _logger.info(
                        "l10n_ve_bw_chart: %s línea(s) de método de pago movidas "
                        "de %s a %s en %s",
                        len(lines), legacy.code, target.code, company.name,
                    )

                has_entries = bool(env["account.move.line"].search_count(
                    [("account_id", "=", legacy.id)]
                ))
                if has_entries:
                    _logger.warning(
                        "l10n_ve_bw_chart: la cuenta %s (%s) de %s tiene apuntes "
                        "y se deja activa. Revísela y concíliela a mano antes de "
                        "archivarla.",
                        legacy.code, legacy.name, company.name,
                    )
                else:
                    legacy.active = False
                    _logger.info(
                        "l10n_ve_bw_chart: cuenta %s (%s) archivada en %s por no "
                        "tener apuntes",
                        legacy.code, legacy.name, company.name,
                    )
