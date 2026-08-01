# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_printer. License LGPL-3.
{
    "name": "Venezuela — Impresora Fiscal POS (The Factory HKA)",
    "version": "19.0.1.2.1",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations/Point of Sale",
    "countries": ["ve"],
    "summary": "Factura fiscal, NC, Reporte X y Cierre Z en máquinas HKA (ACLAS PP9 Plus) vía bridge local",
    "description": """
Impresora fiscal Venezuela para el POS de Odoo 19
=================================================
El navegador de la caja habla por HTTP con un bridge local (Windows) que
controla la máquina fiscal por el protocolo HKA de The Factory. El servidor
Odoo nunca toca la impresora.

- La validación de la orden POS queda BLOQUEADA hasta obtener número fiscal.
- Devoluciones POS emiten nota de crédito fiscal referenciando la factura original.
- Botones Reporte X y Cierre Z en el POS (el Nº Z se guarda en la sesión).
- Botón "Imprimir fiscal" en facturas/NC de cliente del backend (requiere que
  el navegador corra en la PC del bridge).
- El número fiscal se propaga a la factura (Nº de control del Libro de Ventas).
""",
    "depends": ["pos_restaurant", "l10n_ve_bw_fiscal_books", "l10n_ve_bw_igtf"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/pos_order_views.xml",
        "views/pos_payment_method_views.xml",
        "views/account_move_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "l10n_ve_bw_fiscal_printer/static/src/app/**/*",
        ],
        "web.assets_backend": [
            "l10n_ve_bw_fiscal_printer/static/src/backend/**/*",
        ],
    },
    "installable": True,
}
