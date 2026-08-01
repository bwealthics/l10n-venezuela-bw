# Part of l10n_ve_bw_wh_islr. License LGPL-3.
{
    "name": "Venezuela — Retenciones de ISLR (BWEALTHICS)",
    "summary": "Retenciones de ISLR (Decreto 1.808): conceptos, Unidad Tributaria, "
               "comprobantes de retención y XML mensual SENIAT",
    "description": """
Retenciones de Impuesto sobre la Renta para Venezuela
=====================================================
* Conceptos de retención del art. 9 del Decreto 1.808 con tarifas PJ domiciliada / PN residente.
* Formulario de Unidad Tributaria (histórico por Gaceta Oficial) para el cálculo del sustraendo.
* Retención automática al registrar el pago de facturas de proveedor (write-off a la cuenta 210401).
* Comprobante de retención (art. 24) con correlativo AAAAMM+8 y reporte PDF.
* Exportación del XML mensual RelacionRetencionesISLR (Manual Técnico SENIAT v3.1, PA 0095/2009),
  incluyendo la regla de totalidad (pagos con retención 0) y la declaración sin
  operaciones (código 000 del anexo 6.1) cuando el período no tiene comprobantes.
""",
    "version": "19.0.1.1.0",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations",
    "countries": ["ve"],
    "depends": ["l10n_ve_bw_chart"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "data/ut_data.xml",
        "data/islr_concepts.xml",
        "views/ut_views.xml",
        "views/islr_concept_views.xml",
        "views/islr_voucher_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "views/account_payment_register_views.xml",
        "wizards/islr_xml_export_views.xml",
        "reports/arc_islr_report.xml",
    ],
    "installable": True,
}
