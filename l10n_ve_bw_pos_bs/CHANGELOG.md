# Changelog — Venezuela — Cobros POS en Bolívares (Bs)

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.4.1] - 2026-11-17

### Corregido

- Pagos split (Pago Móvil Bs) en **VES** y con `l10n_ve_split_ap_id`. En Odoo 19 el
  cierre de sesión crea los pagos split en lote con `_create_split_account_payments`;
  el override estaba en el singular `_create_split_account_payment`, que el cierre no
  llama, y desde 2026-10-25 todos los PCBSL de pago móvil salían en USD y sin id. El
  override pasa al método en lote y crea de a uno los tenders Bs (cada uno con su
  contexto de denominación); el resto sigue en lote.

## [19.0.1.4.0] - 2026-10-24

### Agregado

- `pos.payment.method.l10n_ve_split_partner_id` ("Cliente por defecto
  (split)"). Con `split_transactions` activo la caja ya no exige cliente: los
  pagos de órdenes sin cliente se contabilizan a ese contacto vía contexto
  `l10n_ve_split_fallback_partner_id` en `res.partner._find_accounting_partner`.
  La orden NO recibe el cliente (no cambia `to_invoice` ni la factura MF).
- `pos.payment.l10n_ve_split_ap_id`: id del `account.payment` propio del pago
  (split), escrito al cerrar la sesión. Lo usa el flujo n8n P2C.
- Patches POS: `PosOrder.isCustomerRequired` y
  `OrderPaymentValidation._askForCustomerIfRequired` ignoran los pagos split de
  métodos con cliente por defecto.

### Motivo

En producción, el pago móvil se consolidaba en un PCBSL por sesión que había que
conciliar parcialmente contra varias líneas del banco. Con split cada pago
tiene su asiento en 101406 (en VES) y concilia 1:1.

## [19.0.1.3.0] - 2026-10-17

### Agregado

- Banco DESTINO del pago móvil: campo `pos.payment.l10n_ve_dest_bank` y, en
  el método de pago, `l10n_ve_bs_dest_banks` (códigos SUDEBAN separados por
  coma, el primero es el predeterminado). Con más de uno, el POS pregunta
  "¿A qué banco llegó el pago?" después de la referencia; con uno, lo fija sin
  preguntar; vacío = comportamiento anterior. Solo cobros.
- Estado `otro_banco` ("Cobrado en otro banco") en `l10n_ve_bdv_state` y
  filtro en la vista de pagos. El workflow n8n BDV lo escribe para los cobros
  cuyo destino no es BDV (0102) en vez de consultarlos al API y alertar.

### Motivo

Auditoría 2026-10-17: desde ~25-sep casi todo pago móvil del restaurante
entra a BANCAMIGA; el API Conciliación BDV solo ve la cuenta BDV y respondía
"Registro solicitado no existe", disparando alertas falsas de comprobante
falso (49 de 50 rechazados de oct 01-14 estaban en el extracto BCA).

## [19.0.1.2.1] - 2026-10-15

### Cambiado

- `depends`: `l10n_ve_bw_fiscal_printer` → `l10n_ve_bw_pos_paper`. La tasa BCV
  (`getVesRate`, `toVes`) se importa de
  `@l10n_ve_bw_pos_paper/app/utils/ves_rate`, extraída sin cambios del
  `fiscal_bridge.js` del módulo de impresora fiscal, que se retira. Sin
  cambios de modelo ni de comportamiento.

### Corregido

- Descripción del manifest: línea en blanco antes de la lista de requisitos
  (docutils avisaba `Unexpected indentation` al instalar).
