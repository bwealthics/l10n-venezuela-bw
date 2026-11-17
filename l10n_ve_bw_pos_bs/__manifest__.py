# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_bs. License LGPL-3.
{
    "name": "Venezuela — Cobros POS en Bolívares (Bs)",
    "version": "19.0.1.4.1",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Accounting/Localizations/Point of Sale",
    "countries": ["ve"],
    "summary": "Captura los Bs exactos y la referencia del pago móvil/punto de venta, "
    "y denomina en VES el cobro del cierre POS para conciliar 1:1 contra el banco",
    "description": """
Cobros en Bolívares para un POS que opera en la moneda de la compañía (USD)
============================================================================
El POS de Odoo 19 exige que los diarios de los métodos de pago estén en la
moneda del POS (pos.config._check_currencies), así que los tenders en Bs
(Pago Móvil, Punto de Venta) registran su equivalente USD en un diario puente.
Este módulo repara la trazabilidad del bolívar:

- En la pantalla de pago, los métodos marcados "Cobro en Bolívares" piden el
  monto EXACTO en Bs recibido (propuesto a tasa BCV del día, editable) y —si
  el método lo exige— el número de referencia de la transacción, que se
  guarda en el campo core pos.payment.payment_ref_no.
- Si el método además marca "Exigir datos del pagador (P2C)", pide el teléfono
  del pagador (04XXXXXXXXX) y el banco emisor (lista SUDEBAN) — solo en cobros,
  no en reembolsos. Ambos salen del comprobante del cliente y son obligatorios
  para el API Conciliación de BDV (getMovement), que un verificador
  externo (p. ej. un workflow n8n) usa a diario para verificar cada pago y
  construir el extracto bancario automático.
- Al cerrar la sesión, la línea de liquidez del pago combinado (cuenta puente,
  p.ej. 101406 CBSL) se denomina en VES: currency_id=VES y amount_currency =
  suma de los Bs capturados, con el balance USD intacto.
- Resultado: la línea del extracto bancario en Bs (BANCAMIGA/BDV) concilia
  contra el apunte del puente casando los Bs 1:1; Odoo postea solo el
  diferencial cambiario USD en el diario de Exchange de la compañía.
- Banco DESTINO del pago móvil: si el método lista varias cuentas del
  comercio ("Bancos destino (P2C)", p.ej. 0172,0102), el POS pregunta a cuál
  llegó el pago. El verificador BDV solo consulta los cobros a BDV (0102):
  los de Bancamiga no los ve el API y antes salían como falsos "comprobante
  falso" (auditoría 2026-10-17).
- Las referencias capturadas se anexan al ref del asiento del pago para que
  el contador las vea desde la conciliación.
- La tasa BCV propuesta sale de l10n_ve_bw_pos_paper (getVesRate, con cache
  de la última tasa si la caja pierde conexión); este módulo ya no depende
  del módulo de impresora fiscal.
- Pago por pago (split): con "Identify Customer" en el método, cada pago
  genera su propio asiento en la cuenta puente (en VES) y concilia 1:1 contra
  su línea del banco. "Cliente por defecto (split)" evita que la caja exija
  cliente: los pagos de órdenes sin cliente se contabilizan a ese contacto.
- Estado de verificación BDV por pago (l10n_ve_bdv_state + nota): el workflow
  n8n lo escribe tras consultar el API Conciliación BDV — verificado /
  rechazado (posible comprobante falso) / no verificable / cobrado en otro
  banco. Filtro en la vista
  de pagos para detectar rechazados antes de que salga de la ventana de
  reintento (auditoría 2026-09-14, caso pago 426).

Requisitos de configuración (no los hace el módulo — se instala inerte):

- Método de pago POS: marcar "Cobro en Bolívares (Bs)" (+ "Exigir referencia"
  y "Exigir datos del pagador (P2C)" para pago móvil) y fijar su Cuenta de
  Pagos Pendientes en la cuenta puente.
- La cuenta puente debe tener "Permitir conciliación" activo.
- Compañía con diario de diferencias de cambio y cuentas de ganancia/pérdida
  cambiaria configurados.
""",
    "depends": ["point_of_sale", "l10n_ve_bw_pos_paper"],
    "data": [
        "views/pos_payment_method_views.xml",
        "views/pos_payment_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "l10n_ve_bw_pos_bs/static/src/app/**/*",
        ],
    },
    "installable": True,
}
