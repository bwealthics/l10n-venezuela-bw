# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
{
    "name": "Venezuela — Libros Fiscales de Compras y Ventas",
    "version": "19.0.1.3.0",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations",
    "countries": ["ve"],
    "summary": "Libros de Compras y Ventas del IVA (Reglamento LIVA arts. 70-78) en XLSX",
    "description": """
Libros Fiscales de Venezuela
============================
Genera el Libro de Ventas (arts. 72, 76, 77 y 78 del Reglamento de la Ley de
IVA) y el Libro de Compras (art. 75) en formato XLSX, con montos expresados en
bolívares a la tasa BCV de la fecha de cada documento.

- Nº de control fiscal en facturas de cliente y proveedor, con canal de
  emisión por diario (máquina fiscal / imprenta digital / forma libre /
  contingencia) que determina quién lo asigna y si puede escribirse a mano.
- Diario de contingencia sin cadena de hash, para transcribir los documentos
  emitidos en talonario durante una falla (PA 0071 art. 11).
- Nº de registro de máquina fiscal por punto de venta.
- Ventas a no contribuyentes: resumen diario por sesión POS (fila tipo
  Reporte Z, art. 77).
- Resumen mensual por alícuota (art. 72) para cruzar con la Forma 30.
""",
    "depends": ["account", "point_of_sale"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "views/account_move_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/fiscal_book_wizard_views.xml",
        "views/account_journal_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
