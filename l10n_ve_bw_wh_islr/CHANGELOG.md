# Changelog — Venezuela — Retenciones de ISLR (BWEALTHICS)

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.1.0] - 2026-07-31

Primera versión publicada del módulo en el repositorio (commit `f99a14a`), que
incorpora de una sola vez todo el alcance descrito abajo.

### Añadido

- Modelo `l10n.ve.islr.concept`: conceptos de retención del art. 9 del Decreto
  1.808, con tarifas independientes para persona jurídica domiciliada y persona
  natural residente, código SENIAT de 3 dígitos por tipo de persona (anexo 6.1
  del Manual Técnico XML v3.1) y bandera «Aplica Sustraendo (PN)».
- Datos: 17 conceptos precargados (honorarios, comisiones, ejecución de obras y
  prestación de servicios, intereses, arrendamiento de muebles e inmuebles,
  cánones y regalías, fletes nacionales e internacionales, publicidad, corredores
  de seguros, primas de seguro y reaseguros, tarjetas de crédito, premios de
  loterías e hipódromos, otros premios, fondos de comercio). El concepto 080
  «Adquisición de Bienes a PJD (Entes Públicos)» se instala archivado por ser
  exclusivo de agentes de retención públicos.
- Modelo `l10n.ve.ut`: Unidad Tributaria como histórico por Gaceta Oficial
  (`date_from`, valor en Bs, gaceta). `get_ut_value()`
  resuelve la UT vigente a la fecha del pago y falla con `UserError` si no hay
  ninguna cargada; `_check_value` exige valor mayor que cero. Semilla: Bs 43,00
  vigente desde el 02/06/2025 (G.O. 43.140).
- Retención automática al registrar el pago (`account.payment.register`), con
  concepto, tarifa, base, sustraendo y monto visibles en el wizard; concepto,
  base y monto admiten override manual (tarifa y sustraendo son calculados).
  Solo aplica a pagos de proveedor (`outbound` / `supplier`) sobre facturas
  posteadas con wizard editable, en lote de una factura o con `group_payment`.
- Base de retención **sin IVA**: se prorratea el monto pagado por la proporción
  sin impuesto de las facturas, ya que el IVA no forma parte de la base del
  Decreto 1.808. Vale también para pagos parciales.
- Sustraendo de persona natural residente: UT vigente a la fecha del pago ×
  tarifa × 83,3334, convertido de Bs a la moneda del pago; solo en conceptos con
  `apply_subtrahend`. La retención nunca baja de cero.
- `_require_ves_rate()`: exige tasa de cambio VES cargada a la fecha antes de
  calcular el sustraendo o exportar el XML, en vez de caer en el fallback 1:1
  silencioso de `res.currency._convert`.
- Asiento de la retención como línea propia en `write_off_line_vals`, sin mutar
  `amount` ni `payment_difference_handling` del wizard, de modo que varios
  módulos de retención puedan convivir en el mismo pago. Guard cruzado que
  bloquea el pago si las retenciones combinadas agotan o exceden su monto.
- Validación del override manual: la retención editada a mano no puede ser
  negativa ni igual o superior al monto del pago.
- Modelo `l10n.ve.islr.voucher`: comprobante de retención del art. 24 del
  Decreto 1.808, con estados borrador/emitido/anulado, período `AAAAMM`
  calculado, RIF del agente y del retenido, y bloqueo de borrado de comprobantes
  emitidos (deben anularse primero).
- Correlativo `AAAAMM` + 8 dígitos que reinicia cada mes: secuencia `no_gap` con
  `use_date_range` y rangos mensuales creados al emitir. La secuencia es por
  compañía (agente de retención), con get-or-create; el XML de datos siembra la
  de la compañía principal.
- Un comprobante **por factura**: en pagos agrupados multi-factura la base, el
  sustraendo y la retención se prorratean por el monto sin IVA de cada factura y
  la última toma el remanente para que la suma cierre exacta.
- Regla de totalidad: con concepto asignado se emite comprobante aunque la
  retención calculada sea 0 (por ejemplo cuando el sustraendo supera la
  retención bruta).
- Reporte PDF del comprobante (art. 24) con datos del agente y del retenido,
  facturas afectadas, base, tarifa, sustraendo y monto retenido, y la referencia
  al Decreto N° 1.808 (G.O. 36.203 del 12/05/1997).
- Wizard `l10n.ve.islr.xml.export`: genera el XML mensual
  `RelacionRetencionesISLR` (Manual Técnico SENIAT v3.1, PA 0095/2009) por
  compañía y período, codificado en ISO-8859-1, con un `DetalleRetencion` por
  factura y nombre de archivo `RelacionRetencionesISLR_<RIF>_<AAAAMM>.xml`.
  `MontoOperacion` va en Bs (base convertida a VES a la tasa de la fecha) y
  `PorcentajeRetencion` se declara en 0,00 cuando no hubo retención efectiva.
- Normalización de datos para el XML: RIF validado contra `^[VEJPG]\d{9}$`,
  `NumeroFactura` con los últimos 10 dígitos de la referencia o el número de la
  factura (`0` si no hay dígitos), y `NumeroControl` tomado de
  `l10n_ve_control_number` cuando el campo existe en `account.move`, reducido a
  su secuencial numérico (`NA` si no hay).
- Declaración sin operaciones: si el período no tiene comprobantes emitidos, el
  export emite el detalle en cero del código 000 del anexo 6.1, con el RIF del
  propio agente y el último día del mes.
- Gate del anexo 6.1: el export bloquea con `UserError` los períodos que
  contengan comprobantes cuyo concepto tenga código SENIAT vacío o `000`, ya que
  ese código está reservado a la declaración sin operaciones.
- Campos en `res.partner`: tipo de persona (PJ domiciliada / PN residente),
  concepto de retención por defecto y porcentaje calculado. Sin concepto no se
  retiene ISLR (caso de las compras de bienes).
- Cuenta de Retenciones de ISLR por Enterar por compañía (p. ej. 210401),
  configurable desde Ajustes de Contabilidad; el pago falla con `UserError` si
  no está definida al momento de retener.
- Menús de Comprobantes ISLR y XML Retenciones ISLR (SENIAT) bajo Cuentas por
  Pagar, y de Unidad Tributaria y Conceptos de Retención ISLR bajo la
  configuración de Contabilidad.
- Reglas de acceso para los cuatro modelos: lectura/escritura para
  `account.group_account_invoice` (control total en el wizard de exportación) y
  control total para `account.group_account_manager`.
- Suite de 16 tests (`tests/test_islr.py`) que cubre selección de UT vigente,
  retención de 5 % a PJ, sustraendo de PN, exclusión del IVA de la base, pago
  parcial prorrateado, comprobante por factura en pagos agrupados, límites del
  override manual, bloqueo por falta de tasa VES o de cuenta configurada,
  reinicio mensual del correlativo por compañía, y generación del XML incluidas
  la regla de totalidad y la declaración sin operaciones.

---

El repositorio público del módulo arranca en esta versión: no hay commits,
etiquetas ni scripts de migración anteriores de los que documentar cambios.
