# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_compliance. License AGPL-3.
{
    "name": "Venezuela — Paraguas de Cumplimiento Fiscal",
    "version": "19.0.1.0.0",
    # AGPL-3 NO es una elección: depende de OCA auditlog, que es AGPL-3, y en
    # Odoo un módulo que depende de un AGPL debe serlo también. Por eso el
    # audit log vive aislado aquí y no dentro de la suite, que sigue LGPL-3.
    "license": "AGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations",
    "countries": ["ve"],
    "summary": "Instala la suite fiscal VE completa más el audit log, y deja "
               "las reglas de auditoría creadas Y SUSCRITAS",
    "description": """
Paraguas de cumplimiento (Venezuela)
====================================
Un solo módulo a instalar para dejar el ERP en condiciones de cumplimiento:

- Arrastra la suite fiscal VE completa y el **audit log** (OCA `auditlog`).
- Crea las reglas de auditoría sobre los modelos fiscales **y las suscribe**:
  crear la regla no audita nada si no se suscribe, y es el paso que más se
  olvida — por eso va en el hook y no en la documentación.
- Documenta el procedimiento MANUAL de inalterabilidad (`docs/CUMPLIMIENTO.md`).
  Los módulos no encienden el hash: es una decisión irreversible del contador.

Requiere que `OCA/server-tools` (rama 19.0) esté en el `addons_path`.
""",
    "depends": [
        "auditlog",
        "l10n_ve_bw_chart",
        "l10n_ve_bw_fiscal_books",
        "l10n_ve_bw_invoice_format",
        "l10n_ve_bw_igtf",
        "l10n_ve_bw_wh_iva",
        "l10n_ve_bw_wh_islr",
        "l10n_ve_bw_municipal",
    ],
    # Sin data XML: las reglas se crean en el hook, que además las CONFIRMA
    # (una regla en borrador no audita nada) y resuelve los ir.model por
    # nombre, sin depender de XML-IDs de módulos ajenos.
    "post_init_hook": "post_init_hook",
    "installable": True,
}
