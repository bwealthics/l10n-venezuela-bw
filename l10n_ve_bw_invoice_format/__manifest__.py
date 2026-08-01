# Part of l10n_ve_bw_invoice_format. License LGPL-3.
{
    "name": "Venezuela — Formato Legal del Comprobante",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations",
    "countries": ["ve"],
    "summary": "Requisitos de forma de la factura: Nº de control, marca (E) de "
               "exentos, fecha/hora legal y datos de la imprenta autorizada",
    "description": """
Formato legal del comprobante (Venezuela)
=========================================
Añade al PDF de factura los requisitos de forma que exigen la Providencia
SNAT/2011/00071 y la SNAT/2024/000102:

- Fecha (y hora, cuando el régimen la exige) en el formato del art. 7.6 de la
  PA 000102: DDMMAAAA y HH.MM.SS con a.m./p.m. En UNA sola línea: ambos
  artículos admiten separadores, así que no hace falta duplicar la fecha.
- Marca "(E)" junto a la descripción de las líneas exentas, exoneradas o no
  sujetas (PA 0071 arts. 13.8, 14.5 y 32.2; PA 000102 art. 7.8).
- Nº de control y su fecha de asignación (art. 7.15).
- Datos de la imprenta autorizada: razón social, RIF y número y fecha de su
  Providencia de autorización (art. 7.14).
- Etiqueta "RIF" en el país Venezuela, para que el RIF del comprador no salga
  rotulado como "Tax ID".

No depende del conector de imprenta digital: los datos de la imprenta son
texto libre, idénticos bajo el régimen de imprenta física y el digital.
""",
    "depends": ["l10n_ve_bw_fiscal_books"],
    "data": [
        "data/res_country_data.xml",
        "views/res_config_settings_views.xml",
        "report/report_invoice_ve.xml",
    ],
    "installable": True,
}
