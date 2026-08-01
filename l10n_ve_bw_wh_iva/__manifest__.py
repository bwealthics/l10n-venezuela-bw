# Part of l10n_ve_bw. License LGPL-3.
{
    "name": "Venezuela — Retenciones de IVA",
    "summary": "Retención de IVA venezolana en ambas direcciones: "
               "sujeto retenido y agente de retención (PA SNAT/2025/000054)",
    "description": """
Retenciones de IVA para Venezuela (Providencia Administrativa SNAT/2025/000054)
===============================================================================

* Sujeto retenido: registro del comprobante de retención recibido de clientes
  Sujetos Pasivos Especiales al momento del cobro (write-off a la cuenta de
  Retenciones de IVA Recibidas de Clientes, Forma 30 casilla 66).
* Agente de retención (activado por el flag SPE de la compañía): retención
  75%/100% del IVA al pagar facturas de proveedor, comprobante propio con
  numeración AAAAMM + 8 dígitos (art. 16), reporte PDF y exportación del
  archivo TXT de la Forma 99035 (16 columnas, delimitado por tabulaciones).
""",
    "version": "19.0.1.1.0",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "countries": ["ve"],
    "depends": ["l10n_ve_bw_chart"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/iva_wh_voucher_views.xml",
        "views/account_payment_register_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/iva_txt_export_views.xml",
        "report/iva_wh_voucher_report.xml",
    ],
    "installable": True,
}
