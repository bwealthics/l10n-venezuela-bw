# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_igtf. License LGPL-3.
{
    "name": "Venezuela — IGTF",
    "summary": "IGTF: débito propio en pagos en divisas y percepción como Sujeto Pasivo Especial",
    "description": """
Impuesto a las Grandes Transacciones Financieras (IGTF) — Ley IGTF (reforma 2022).

- Diarios en divisas marcables como sujetos a IGTF (ej. Zelle, efectivo USD, USDT).
- Pagos salientes por diarios marcados: asiento automático de gasto IGTF
  (Debe Gasto por IGTF / Haber cuenta del diario), con monto editable y anulable
  por pago (efectivo o Zelle a proveedor no sujeto no causa IGTF).
- Cobros en divisas, solo como Sujeto Pasivo Especial y desde la fecha de
  designación: asiento de percepción (Debe cuenta del diario / Haber IGTF
  Percibido por Enterar).
- Configuración en Ajustes: alícuota (3%% por defecto) y cuentas de gasto y
  de percepción.
""",
    "version": "19.0.1.1.0",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations",
    "countries": ["ve"],
    "depends": ["l10n_ve_bw_chart"],
    "data": [
        "views/account_journal_views.xml",
        "views/account_payment_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
