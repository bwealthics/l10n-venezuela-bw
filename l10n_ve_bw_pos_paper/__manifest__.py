# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_paper. License LGPL-3.
{
    "name": "Venezuela — POS en papel (talonario / formas libres)",
    "version": "19.0.1.0.1",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations/Point of Sale",
    "countries": ["ve"],
    "summary": "Facturación del POS sobre papelería de imprenta autorizada "
               "(talonario o formas libres) y modo contingencia por sesión",
    "description": """
Facturación en papel para el POS de Odoo 19 (Venezuela)
=======================================================
Extracción, sin cambios funcionales, del modo papel que vivía en
l10n_ve_bw_fiscal_printer, para que la caja en talonario no dependa del
módulo de impresora fiscal. Mismos nombres de campo: los datos existentes se
conservan al desinstalar el módulo viejo.

- Caja en modo talonario (PA 0071 art. 11) o formas libres: el POS pide el
  Nº de factura y/o el Nº de control preimpresos, propuestos desde el lote de
  papelería (l10n.ve.paper.batch), valida duplicados y rango y fuerza la
  factura en el diario del canal.
- Modo contingencia por sesión, autorizado por un gerente con motivo; el
  rótulo rojo queda visible toda la jornada y muere al cerrar la caja.
- La factura de papel exige cliente identificado (art. 13.7) y no puede
  consolidarse con otras órdenes.
- Tasa BCV del día para el frontend (getVesRate / toVes), que reutilizan
  otros módulos del POS.
- Puntos de extensión para un módulo de máquina fiscal:
  _l10n_ve_paper_invoice_vals y _l10n_ve_has_fiscal_document (Python),
  _l10nVeHasFiscalMachine y _l10nVeContingency (JS).
""",
    "depends": ["point_of_sale", "l10n_ve_bw_fiscal_books"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "l10n_ve_bw_pos_paper/static/src/app/**/*",
        ],
    },
    "installable": True,
}
