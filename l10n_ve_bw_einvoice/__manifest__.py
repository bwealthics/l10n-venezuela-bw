# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_einvoice. License LGPL-3.
{
    "name": "Venezuela — Conector de Imprenta Digital",
    "version": "19.0.2.0.0",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations",
    "countries": ["ve"],
    "summary": "Emisión de facturas por imprenta digital autorizada "
               "(PA SNAT/2024/000102)",
    "description": """
Conector de imprenta digital (Venezuela)
========================================
Envía los documentos de los diarios con canal "Imprenta digital" al proveedor
autorizado, que es quien asigna el Nº de control, y guarda bitácora de cada
llamada.

Arquitectura: toda la lógica fiscal vive en
`account.move._l10n_ve_edoc_document_vals()`, que produce un dict NEUTRO. El
proveedor concreto solo traduce ese dict a su dialecto, implementando cuatro
métodos del modelo abstracto `l10n.ve.edoc.provider`. Cambiar de imprenta es
escribir un archivo.

Soporta proveedores síncronos (devuelven el Nº de control en la emisión, como
The Factory HKA) y asíncronos (hay que consultarlo después, como Unidigital):
de ahí el estado intermedio "Enviado, sin Nº de control" y el cron de consulta.

**Estado**: incluye el núcleo, el proveedor SIMULADO y el adaptador de
**The Factory HKA** (REST: /api/Autenticacion, /api/Emision, /api/Anular),
escrito contra su wiki pública. En pruebas apunta solo al ambiente demo del
proveedor; la URL de producción se configura al recibir el contrato. Quedan
por confirmar contra el catálogo de HKA los códigos de tipo de documento,
de impuesto y de tipo de venta. El cron viene DESACTIVADO.
""",
    "depends": ["l10n_ve_bw_invoice_format"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/account_move_views.xml",
        "views/edoc_log_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/l10n_ve_edoc_cancel_wizard_views.xml",
    ],
    "installable": True,
}
