# Part of l10n_ve_bw. License LGPL-3.
{
    "name": "Venezuela — Impuesto Municipal (Patente de Industria y Comercio)",
    "summary": "Cálculo mensual del impuesto municipal sobre ingresos brutos y "
               "generación del asiento de provisión",
    "description": """
Impuesto municipal (patente de industria y comercio) para Venezuela:

* Configuración por compañía: municipio, alícuota sobre ingresos brutos,
  mínimo tributable (fijo y/o en veces MMV — múltiplo del TCMMV del BCV,
  sector alimentos hasta 30 veces), cuentas y diario.
* Asistente mensual: calcula la base imponible (ingresos brutos posteados
  del período), aplica max(base × alícuota, mínimo tributable) — el mínimo
  es el mayor entre el fijo y veces MMV × TCMMV convertido a la moneda de
  la compañía —, muestra el equivalente en Bs a la tasa de fin de mes y
  genera el asiento borrador Dr Gasto / Cr Impuesto Municipal por Pagar.
  Un mes sin ventas provisiona el mínimo.
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
        "views/res_config_settings_views.xml",
        "wizards/municipal_tax_wizard_views.xml",
    ],
    "installable": True,
}
