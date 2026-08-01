# Changelog — Venezuela: Retenciones de IVA

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.1.0] - 2026-08-01

### Corregido

- Las notas de crédito ahora **restan** en los totales del comprobante
  (`base_amount`, `exempt_amount`, `tax_amount`). La retención ya se calculaba
  sobre el IVA causado **neto** en `_l10n_ve_get_iva_wh_agent_amount`, pero el
  comprobante sumaba las NC en positivo: el comprobante y la Forma 99035
  quedaban sobredeclarados.
- `_l10n_ve_get_amount_for_move` —la interfaz pública que consumen los libros
  fiscales— devuelve el impuesto retenido **con signo** (negativo para
  `in_refund` / `out_refund`) y prorratea sobre el IVA causado **neto** de cada
  documento. Así la factura declara su retención plena (tasa × su IVA), la NC la
  resta, y la suma por documento reproduce el total retenido. Antes el resultado
  se truncaba con `max(0.0, …)`, lo que rompía esa identidad.
- Las líneas del comprobante PDF y del TXT 99035 (`_l10n_ve_get_report_lines`)
  emiten base imponible, monto exento, impuesto causado, monto total e impuesto
  retenido con signo negativo para las notas de crédito: el archivo netea por
  documento y el total declarado reproduce `withheld_amount` en lugar de sumar
  las notas de crédito en positivo.
- El prorrateo interno compara el IVA causado total con
  `currency_id.is_zero()` en lugar de un test booleano. Con el neteo de NC el
  total puede quedar en un residuo de redondeo no significativo, que antes
  pasaba el test y producía un reparto sobre una base espuria.

## [19.0.1.0.0] - 2026-07-31

Publicación inicial del módulo: retención de IVA venezolana en las **dos
direcciones** (sujeto retenido y agente de retención), conforme a la
Providencia Administrativa **SNAT/2025/000054** (G.O. 43.171 del 16/07/2025,
vigente desde el 01/08/2025, que deroga la PA SNAT/2015/0049).

### Añadido

- Modelo `l10n.ve.iva.wh.voucher` (Comprobante de Retención de IVA) con estados
  borrador / emitido / anulado, período fiscal `AAAAMM` calculado desde la fecha
  de emisión, documentos retenidos en `move_ids` y bloqueo de borrado de
  comprobantes emitidos (`_unlink_except_posted`): el correlativo fiscal debe
  conservarse, un comprobante se anula, no se elimina.
- **Numeración del art. 16**: 14 caracteres, `AAAAMM` + secuencial de 8 dígitos,
  validado por `ValidationError`. La `ir.sequence` es `no_gap`, se resuelve
  *get-or-create* **por compañía** (el correlativo del agente de retención no
  puede compartirse entre compañías) y crea rangos de fecha **mensuales**
  explícitos para que el secuencial reinicie en `00000001` cada período; sin
  ellos `ir.sequence` genera rangos anuales.
- **Dirección sujeto retenido**: campos en el asistente de registro de pagos
  para el IVA que un cliente Sujeto Pasivo Especial retuvo sobre el cobro y el
  número del comprobante recibido (14 dígitos validados). El monto se descuenta
  del cobro contra la cuenta de Retenciones de IVA Recibidas de Clientes
  (Forma 30, casilla 66) y se persiste en `account.payment`
  (`l10n_ve_iva_wh_received_amount` / `l10n_ve_iva_wh_received_number`) para que
  los libros fiscales reporten la retención recibida por factura.
- **Dirección agente de retención**, activada por el flag SPE de la compañía:
  cálculo automático de la retención sobre el IVA causado de las facturas de
  proveedor **publicadas**, editable en el asistente.
  - Exclusión del **art. 3**: no se retiene a proveedores cuyo tipo de
    contribuyente es «especial» (operaciones entre agentes de retención).
  - No se retiene antes de la fecha de designación SPE de la compañía, sin RIF
    del proveedor, con porcentaje 0 %, ni sobre documentos en borrador (el flujo
    core `is_register_payment_on_draft` queda libre).
  - Pagos parciales: la retención se prorratea por el total **original** de los
    documentos (no el residual) y descuenta lo ya retenido en comprobantes
    emitidos previos de los mismos documentos, de modo que pagos sucesivos nunca
    retengan de más.
- La retención se inyecta como línea **propia** de `write_off_line_vals` sin
  mutar `amount`, `payment_difference_handling` ni `writeoff_account_id` del
  asistente: el módulo convive con otras retenciones (p. ej. ISLR) sobre el mismo
  pago, cada una aportando su línea, y el resto de la factura queda abierto por
  el manejo `open` del core. Un guard cruzado impide que las retenciones
  combinadas agoten o excedan el monto del pago.
- Emisión automática del comprobante propio al confirmar el pago como agente,
  enlazado al pago y a los documentos retenidos, con la tasa aplicada y los
  montos en moneda de la compañía.
- Campo `l10n_ve_wh_iva_rate` en el contacto (arts. 4 y 5): 0 % (no retener),
  **75 %** (regla general) o **100 %** (IVA no discriminado / factura
  defectuosa), visible en la pestaña de contabilidad del partner.
- Cuentas configurables por compañía en Ajustes › Contabilidad › Localización
  Venezuela: Retenciones de IVA por Enterar (agente, p. ej. 210303) y
  Retenciones de IVA Recibidas de Clientes (p. ej. 110302).
- **Reporte PDF del comprobante** (art. 16) con datos del agente de retención y
  del sujeto retenido incluyendo RIF, una línea por documento y por alícuota
  (fecha, tipo de documento, nº de documento, nº de control, documento afectado,
  total, exento, base, alícuota, impuesto causado, impuesto retenido), totales y
  espacios de firma de ambas partes.
- **Exportación del TXT de la Forma 99035**: 16 columnas exactas delimitadas por
  tabulaciones y terminadas en CRLF, por quincena (por defecto 1–15 o 16–fin de
  mes según el día actual), sobre los comprobantes emitidos del período. El RIF
  del agente y del retenido va en formato del portal, sin guiones; el tipo de
  documento SENIAT se deriva del asiento (`01` factura, `02` nota de débito,
  `03` nota de crédito); el documento afectado de una NC se declara por la `ref`
  del proveedor, mismo criterio que el nº de documento (col. 7). Los montos se
  expresan en **VES**: los del documento a la tasa BCV de su fecha y el impuesto
  retenido (col. 11) a la tasa de la fecha del **comprobante**, que es cuando se
  practicó la retención.
- Desglose por **alícuota legal** (16 % / 8 % / 31 %…): el impuesto retenido se
  distribuye proporcionalmente al IVA causado de cada documento y, dentro del
  documento, al IVA de cada alícuota; el residuo de redondeo se asigna a la
  última alícuota para conservar el total exacto. Los impuestos de tipo grupo se
  expanden a sus hijos antes de agrupar.
- Menús bajo Contabilidad › Proveedores: «Comprobantes Retención IVA» y
  «Exportar TXT Retenciones IVA (99035)», con vistas lista/formulario/búsqueda
  (filtros por estado y fecha, agrupación por sujeto retenido y período) y ACLs
  para los grupos de Facturación y Asesor contable.
- Batería de tests sobre `AccountTestInvoicingCommon`: flujo completo de
  retención al 75 %, prorrateo en pago parcial, no re-retención en el segundo
  pago, cada una de las exclusiones (compañía no SPE, fecha SPE futura,
  proveedor especial, tasa 0 %, sin RIF, factura en borrador), flujo de
  retención recibida y formato de su número, 16 columnas del TXT, factura
  multi-alícuota con una línea por tasa, documento afectado de una NC por `ref`,
  reinicio mensual y aislamiento por compañía del correlativo, y coexistencia de
  retención de IVA e ISLR en un mismo pago sin contaminar las bases.
