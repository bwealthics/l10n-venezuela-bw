# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
"""Siembra del diario de contingencia (PA 0071 art. 11).

Va en un hook y no en un data XML porque en Odoo 19 `default_account_id` de
account.journal es un Many2one PLANO —sin compute ni default—, así que un
diario sembrado por XML quedaría sin cuenta de ingreso. Aquí se copia la del
diario de ventas que ya usa la compañía, que es la que el contador eligió.

Para re-ejecutarlo (p. ej. tras crear una compañía VE nueva) desde
odoo-bin shell:

    from odoo.addons.l10n_ve_bw_fiscal_books.hooks import create_contingency_journals
    create_contingency_journals(env)
"""
import logging

_logger = logging.getLogger(__name__)

CONTINGENCY_CODE = "CONT"


def create_contingency_journals(env):
    """Un diario de ventas SIN hash por compañía VE, para transcribir los
    documentos emitidos a mano en el talonario durante una falla.

    Sin hash a propósito: replica un documento que ya existe en papel, así que
    tiene que poder corregirse. Por eso vive en su propio diario y no contamina
    la cadena inalterable del diario fiscal.
    """
    Journal = env["account.journal"]
    companies = env["res.company"].search(
        [("account_fiscal_country_id.code", "=", "VE")])
    if not companies:
        _logger.warning(
            "l10n_ve_bw_fiscal_books: ninguna compañía con país fiscal VE; "
            "no se creó el diario de contingencia.")
        return
    for company in companies:
        existing = Journal.search([
            ("company_id", "=", company.id),
            ("l10n_ve_emission_channel", "=", "contingencia"),
        ], limit=1)
        if existing:
            continue
        model = Journal.search([
            ("company_id", "=", company.id),
            ("type", "=", "sale"),
        ], order="id", limit=1)
        if not model:
            _logger.warning(
                "l10n_ve_bw_fiscal_books: la compañía %s no tiene diario de "
                "ventas del que copiar la cuenta; cree el diario de "
                "contingencia a mano.", company.display_name)
            continue
        code = CONTINGENCY_CODE
        if Journal.search_count([("company_id", "=", company.id),
                                 ("code", "=", code)]):
            code = "CONTG"
        journal = Journal.create({
            "name": "Ventas en Contingencia",
            "code": code,
            "type": "sale",
            "company_id": company.id,
            "default_account_id": model.default_account_id.id,
            "currency_id": model.currency_id.id,
            "l10n_ve_emission_channel": "contingencia",
        })
        _logger.info(
            "l10n_ve_bw_fiscal_books: diario de contingencia %s creado para %s",
            journal.code, company.display_name)


def post_init_hook(env):
    create_contingency_journals(env)
