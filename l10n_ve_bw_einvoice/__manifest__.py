# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_einvoice. License LGPL-3.
{
    "name": "Venezuela — Conector de Imprenta Digital",
    "version": "19.0.1.1.0",
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

**Estado**: se entrega el núcleo y el proveedor SIMULADO. El adaptador real
está pendiente de contratar la imprenta y recibir su documentación,
credenciales de QA y URL de producción. El cron viene DESACTIVADO.
""",
    "depends": ["l10n_ve_bw_invoice_format"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/account_move_views.xml",
        "views/edoc_log_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
}
