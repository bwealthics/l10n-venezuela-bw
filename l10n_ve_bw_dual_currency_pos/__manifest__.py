# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency_pos. License LGPL-3.
{
    "name": "Venezuela — Doble Moneda en el POS",
    "version": "19.0.1.1.0",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Sales/Point of Sale",
    "countries": ["ve"],
    "summary": "Pide la tasa BCV del día antes de cobrar y añade el total en "
               "Bs y la tasa al recibo del POS",
    "depends": ["l10n_ve_bw_dual_currency", "point_of_sale"],
    "data": [],
    "assets": {
        "point_of_sale._assets_pos": [
            "l10n_ve_bw_dual_currency_pos/static/src/**/*",
        ],
    },
    "auto_install": True,
    "installable": True,
}
