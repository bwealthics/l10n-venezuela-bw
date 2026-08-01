# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
{
    "name": "Venezuela — Plan de Cuentas BWEALTHICS (6 dígitos)",
    "version": "19.0.1.1.0",
    "category": "Accounting/Localizations/Account Charts",
    "summary": "Plan de cuentas venezolano de 6 dígitos (VEN-NIF) con impuestos de IVA y base SPE",
    "description": """
Localización de Venezuela — Plan de Cuentas BWEALTHICS
======================================================

- Plan de cuentas de 6 dígitos (169 cuentas, clases 1-6) alineado a VEN-NIF.
- Jerarquía de grupos de cuenta (1, 2 y 4 dígitos).
- Impuestos de IVA: 16%, 8%, 31%, 0% exportación y Exento (ventas y compras).
- Configuración de Sujeto Pasivo Especial (SPE) en la compañía.
- Tipo de contribuyente en la ficha del contacto.
""",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "countries": ["ve"],
    "depends": [
        "account",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
}
