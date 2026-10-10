# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
{
    "name": "Venezuela — Doble Moneda (USD / Bs)",
    "version": "19.0.1.1.1",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations",
    "countries": ["ve"],
    "summary": "Tasa BCV congelada por asiento, montos en Bs almacenados por "
               "apunte, factura, pantalla y libros contables en USD y Bs",
    "depends": ["l10n_ve_bw_invoice_format", "l10n_ve_bw_fiscal_books"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "views/account_move_views.xml",
        "views/account_move_line_views.xml",
        "views/account_payment_views.xml",
        "views/res_config_settings_views.xml",
        "report/report_invoice_dual.xml",
        "wizards/legal_books_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "l10n_ve_bw_dual_currency/static/src/**/*",
        ],
    },
    "installable": True,
}
