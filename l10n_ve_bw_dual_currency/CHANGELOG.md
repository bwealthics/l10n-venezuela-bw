# Changelog: Venezuela · Doble Moneda (USD / Bs)

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.1.0] - 2026-10-10

### Cambiado

- **Hora de corte de la tasa BCV** (`res.company.l10n_ve_bs_rate_cutoff`, por
  defecto 9:15, en Ajustes): el BCV publica la tasa del día a las 9:00 y el n8n
  la carga a las 9:15. Antes de esa hora (zona de la compañía, por defecto
  Caracas) una factura de HOY se confirma con la tasa del día anterior sin
  pedir nada; después se exige la del día. Para cualquier otra fecha se sigue
  exigiendo la tasa exacta de esa fecha. Helpers nuevos en `res.company`:
  `_l10n_ve_bs_min_rate_date`, `_l10n_ve_bs_rate_acceptable_for`,
  `_l10n_ve_bs_rate_valid_until`, `_l10n_ve_bs_local_today`.
- Las facturas confirmadas antes de la hora de corte quedan con la tasa del día
  anterior y su fecha registrada (`l10n_ve_bs_rate_date`); no se re-tasan al
  cargarse la del día.

## [19.0.1.0.0] - 2026-10-09

Versión inicial. La compañía lleva su contabilidad en USD y el bolívar de
referencia (VES, a tasa BCV) se guarda por asiento: una sola regla de conversión
alimenta la pantalla, el PDF de la factura, los Libros IVA y los libros
contables. No cambia la moneda de la compañía ni crea asientos de
revalorización.

Requiere `l10n_ve_bw_fiscal_books` 19.0.1.5.0 o posterior (los tres hooks de
conversión que este módulo sobreescribe) y `l10n_ve_bw_invoice_format` (moneda Bs
de referencia y base del PDF). Necesita la librería Python `xlsxwriter`.

### Añadido

- **Tasa congelada por asiento** (`account.move`):
  - `l10n_ve_bs_rate` (Bs por 1 unidad de la moneda de la compañía, 6
    decimales), `l10n_ve_bs_rate_date` (fecha del registro de tasa usado) y
    `l10n_ve_bs_rate_missing`, los tres almacenados y de solo lectura.
  - La tasa depende solo de la fecha del documento, de la tasa manual y de la
    factura de origen en las reversiones, no de la tabla de tasas: editar una
    tasa vieja no mueve los Bs de lo ya confirmado.
  - Fecha del documento: la fecha de factura en facturas y recibos; la fecha
    contable en los demás asientos; hoy si no hay ninguna.
  - Búsqueda de la tasa: última tasa de la moneda Bs con fecha menor o igual a la
    del documento, con el mismo dominio y orden de `res.currency._get_rates`
    (tasas de la compañía raíz antes que las globales). Si no existe ninguna, el
    asiento queda marcado y no se inventa una paridad. Se evita adrede el
    `COALESCE(..., 1.0)` del core, que convierte a la par en silencio.
  - Versión por lote (`res.company._l10n_ve_bs_rates_at`, con bisección) para que
    la instalación sobre miles de asientos no haga una consulta por asiento.
  - Al confirmar (`_post`), los borradores sin tasa manual recalculan la tasa con
    la tabla vigente en ese momento. Nunca bloquea.
- **Notas de crédito con la tasa de su factura**: una reversión hereda tasa y
  fecha de tasa de `reversed_entry_id` si el origen tiene tasa, no la del día de
  emisión. La nota de crédito total anula la factura también en Bs.
- **Tasa Bs manual** (`l10n_ve_bs_rate_override`, con seguimiento en el chatter).
  Solo se cambia en borrador: en un asiento confirmado se rechaza cualquier
  valor distinto, y se permite reescribir el mismo valor o pasar a borrador en la
  misma escritura. Exime de pedir la tasa del día. El botón "Recalcular tasa"
  (`action_l10n_ve_bs_refresh_rate`) la limpia y vuelve a la tabla.
- **Bs almacenados por apunte** (`account.move.line`): `l10n_ve_balance_bs`,
  `l10n_ve_debit_bs`, `l10n_ve_credit_bs` y `l10n_ve_bs_adjustment`, calculados
  por asiento completo:
  1. Línea en VES: su `amount_currency`, exacto. Los bancos en VES cuadran con
     su extracto.
  2. Bolívar igual a la moneda de la compañía: el `balance`.
  3. Otra moneda (USD, VEB, EUR): `balance × tasa`, redondeado a la precisión
     del Bs. VEB no es Bs. Sin tasa, cero.
  4. Recuadre: el residuo para que el asiento sume cero en Bs lo absorbe una
     sola línea. Candidatas: líneas en moneda distinta de Bs; si no hay, las que
     no son de liquidez; si tampoco, todas. Prioridad: línea de cobro o pago,
     luego mayor monto, luego la más antigua. Queda registrado en "Ajuste Bs".
  - Sin tasa no se recuadra (sería inventar bolívares). Tampoco se recuadra un
    borrador que aún no cuadra en la moneda de la compañía: es el formulario
    antes de que Odoo genere las líneas de impuesto y de cobro.
  - Las dependencias incluyen cuenta, tipo de línea y diario de las líneas
    hermanas, porque la línea que absorbe el ajuste se elige con esos datos.
  - Las diferencias de cambio con ambas líneas en VES y `amount_currency` en cero
    quedan en Bs 0, sin caso especial.
- **Totales Bs de la factura** (`account.move`): base imponible, impuestos,
  total, saldo y ajuste, almacenados y sumados desde los apuntes. El total es
  base más impuestos (más otras líneas que no son de cobro, si las hay). El saldo
  es el del documento si la factura está en Bs; si no, el total Bs por la
  proporción saldo sobre total. En asientos varios, el total es la suma de los
  saldos positivos.
- **Columnas Bs por línea de producto**: `l10n_ve_price_subtotal_bs` y
  `l10n_ve_price_total_bs` (almacenados) y `l10n_ve_price_unit_bs` (calculado, no
  almacenado). El precio sale del importe de la línea y no de `precio × tasa`:
  cantidad por precio cuadra con el importe, incluso con precios con IVA
  incluido.
- **Base e impuesto por grupo de impuesto** en la moneda del documento y en Bs
  (`_l10n_ve_bs_tax_groups`), con los impuestos aplanados como hace el core. Lo
  usan el widget y el PDF.
- **Pedir la tasa del día al confirmar**:
  - El botón Confirmar y la confirmación masiva desde la lista (override de
    `validate.account.move`, que va directo a `_post`) lanzan un aviso con
    acción "Cargar la tasa", que abre las tasas de la moneda Bs con la fecha
    prellenada.
  - Solo rige para compañías con país fiscal Venezuela
    (`res.company._l10n_ve_bs_requires_daily_rate`). Fuera de VE la tasa se
    congela igual, pero no se bloquea nada.
  - No se exige con tasa manual, en reversiones con tasa en el origen ni en
    facturas sin líneas fuera de Bs. Sin fecha de factura se evalúa hoy.
  - Se puede saltar con el contexto `l10n_ve_bs_skip_rate_check`.
  - Los flujos automáticos (cierre del POS, extractos, diferencias de cambio,
    `_post()` directo) no se bloquean: usan la última tasa menor o igual a la
    fecha y dejan su fecha en "Fecha de la tasa".
- **Protección de tasas** (`res.currency.rate`): no se puede borrar una tasa de
  la moneda Bs de alguna compañía si hay asientos posteados con esa fecha de tasa
  y sin tasa manual. El mensaje cuenta los asientos y da ejemplos. Editar la tasa
  sí se permite, porque cada asiento guarda su valor. Si queda otra tasa de la
  misma moneda y día, el borrado procede.
- **Formulario de factura y asiento**:
  - Fila "Tasa BCV" (`l10n_ve_bs_rate_label`) bajo el diario y la moneda, por
    ejemplo `875,6505 Bs por USD · 09-10-2026`.
  - Banner amarillo en borrador con la tasa desactualizada
    (`l10n_ve_bs_rate_outdated`, no almacenado) y botón "Recalcular tasa". Banner
    rojo si no hay ninguna tasa.
  - "Saldo Bs" junto al saldo pendiente.
  - Columnas "Subtotal Bs" (visible) y "Precio Bs" (oculta) en las líneas de
    factura, y "Debe Bs" y "Haber Bs" con total en los apuntes contables.
  - En "Otra información", de facturas y de asientos varios: tasa, fecha de la
    tasa, ajuste y tasa manual (esta, editable solo en borrador).
- **Widget de totales** (`account.TaxTotalsField`, OWL): columna Bs a la derecha
  de cada subtotal, grupo de impuesto, fila de redondeo y total, desde
  `tax_totals['l10n_ve_bs']`. En borrador convierte los montos del widget a la
  tasa del borrador, porque Odoo aún no generó las líneas de impuesto y de cobro;
  confirmada, lee los Bs almacenados. No se muestra si no hay tasa o si el
  documento ya está en Bs.
- **Listas, pivot y búsquedas**:
  - Facturas: "Total Bs" (visible), "Saldo Bs" y "Tasa Bs" (ocultas). Sin suma al
    pie: los montos Bs son siempre positivos y el total del core lleva signo.
  - Apuntes contables: "Debe Bs" y "Haber Bs" visibles y "Saldo Bs" oculta, con
    suma. El pivot de apuntes recibe "Saldo Bs" como medida.
  - Filtros "Sin tasa Bs" y "Ajuste Bs > 1" (ajuste mayor a 1 o menor a -1) en
    la búsqueda de asientos y en la de facturas.
- **Pagos** (`account.payment`): `l10n_ve_bs_rate` (la del asiento del pago) y
  `l10n_ve_amount_bs`, no almacenado. Pago en Bs: su monto. Si no, los Bs de las
  líneas de liquidez de su asiento. Un pago sin asiento se convierte con la tabla
  a la fecha del pago, solo para mostrar. Visible en el formulario y, oculto, en
  la lista.
- **Ajustes por compañía**: bloque "Localización Venezuela" (Doble moneda) con
  `l10n_ve_show_line_amount_bs` (Importe Bs por línea, activo por defecto) y
  `l10n_ve_show_line_price_bs` (Precio Bs por línea, apagado por defecto).
- **PDF de la factura** (hereda `account.report_invoice_document` después de
  `l10n_ve_bw_invoice_format`; cubre la factura normal y la de contingencia).
  `account.move._l10n_ve_bs_amounts()` se sobreescribe para devolver los Bs
  almacenados con `dual: True`, el desglose por grupo de impuesto y la fecha de
  la tasa. Con ellos:
  - Tabla de totales de tres columnas (concepto, moneda del documento, Bs):
    Subtotal, por grupo "B.I. <grupo>" e impuesto, Redondeo, Total y Saldo
    pendiente. Reemplaza al `t-call` de totales del core y oculta las cuatro
    filas Bs de `invoice_format`.
  - Saldo pendiente solo si dice algo y solo si el core no imprime ya su "Amount
    Due". En las filas de pagos la celda Bs queda vacía; el "Amount Due" lleva su
    saldo en Bs.
  - Columna "Importe Bs" por línea, con el mismo criterio que la del core
    (subtotal, o total con impuestos si `company_price_include` es
    `tax_included`), y columna "Precio Bs" junto al precio unitario. En
    secciones y subsecciones, la suma Bs de sus líneas; ajustes de `colspan` en
    la rama normal y en la agrupada.
  - Fila "Tasa BCV" en el bloque de información: `1 USD = X VES` y su fecha.
  - Nota legal con la tasa a 4 decimales y su fecha, citando la PA
    SNAT/2011/0071 (art. 13, num. 14), la Ley del IVA (art. 25) y la Ley del BCV
    (art. 128). Reemplaza el texto genérico de `invoice_format`.
  - Sin tasa, o con el documento ya emitido en Bs, no se imprime ninguna cifra
    en Bs.
- **Libros IVA** (`l10n.ve.fiscal.book.wizard`): override de los tres hooks de
  `l10n_ve_bw_fiscal_books` 19.0.1.5.0. Base por alícuota, exento e IVA salen de
  `l10n_ve_balance_bs`; el total, de `l10n_ve_amount_total_bs`; y el IVA
  retenido se convierte a la tasa congelada del asiento, para que siga siendo el
  75 % o el 100 % del IVA de la fila. Antes de armar el archivo, el libro se
  detiene con un `UserError` si algún documento del período tiene líneas en otra
  moneda sin convertir (sin tasa): lista el conteo y hasta 10 ejemplos. Un
  documento sin tasa con todas sus líneas en Bs no bloquea. Si el libro se pide
  en una moneda distinta de la Bs de la compañía, se conserva la conversión
  original.
- **Asistente "Libros contables (Diario, Mayor, Balance)"**
  (`l10n.ve.legal.books.wizard`), menú en Reporting bajo Libros Fiscales
  (secuencia 91), con acceso para los grupos de solo lectura, facturación y
  administrador de contabilidad. Un archivo XLSX con montos en la moneda de la
  compañía y en Bs lado a lado, solo con asientos confirmados:
  - **Libro Diario**: un renglón por apunte, por fecha y asiento, con totales.
    El filtro de diarios solo actúa aquí.
  - **Libro Mayor**: por cuenta, saldo inicial, movimientos con saldo corrido y
    "TOTAL CUENTA". Parte de las filas del Balance, así que el saldo inicial y
    el final coinciden con él.
  - **Balance de Comprobación**: saldo inicial, Debe, Haber y saldo final por
    cuenta en ambas monedas, con la "Verificación de cuadre" de seis controles
    (Σ Debe menos Σ Haber del período, Σ saldos iniciales y Σ saldos finales,
    cada uno en ambas monedas).
  - **Advertencias**: los seis controles y los asientos a revisar, hasta 500 por
    tipo: sin tasa Bs (hasta la fecha final, también los anteriores al período),
    ajuste Bs mayor a 1 (del período) y asientos descuadrados en Bs o en la
    moneda de la compañía (hasta la fecha final, también los anteriores).
  - Saldos iniciales: las cuentas que arrastran saldo, todo lo anterior al
    período; las de resultado, desde el inicio del ejercicio fiscal. El resultado
    de ejercicios anteriores va en una fila aparte, "Resultados no distribuidos
    de ejercicios anteriores", asignada a la cuenta de resultados no
    distribuidos (o fila virtual si no existe). Sin ella el balance no sumaría
    cero.
  - Los Bs se leen de los campos almacenados, nunca se reconvierten. Cálculo
    (`_compute_*`) separado de la escritura del XLSX (`_write_*`). Si el período
    supera 1.000.000 de apuntes, pide un rango menor en lugar de truncar.
- **Pruebas** (`post_install`, cifras esperadas calculadas a mano): conversión
  por asiento (factura en USD con IVA y exento, residuo de redondeo a la cuenta
  por cobrar, factura de proveedor en VES, asiento mixto, asiento y factura sin
  tasa, bolívar igual a la moneda de la compañía), tasa del documento (nota de
  crédito, confirmación con y sin tasa exacta, confirmación masiva, tasa manual,
  borrador desactualizado y botón de recálculo), tabla de tasas (borrado
  protegido, preferencia de la tasa de la compañía sobre la global, versión por
  lote), pagos, widget y datos del PDF, borrador en el formulario, hooks y
  generación de los Libros IVA, render del PDF con sus interruptores y los
  cuatro libros contables (saldos iniciales, cuadres, filtro de diarios,
  advertencias y XLSX).

### Notas

Validado sobre una copia de la base de producción de MISOYMASA:

- Los 3.834 asientos posteados cuadran en Bs. Las líneas en VES quedan exactas y
  la tasa de cada asiento es la de la tabla.
- Libro de Compras de septiembre de 2026: ahora coincide al céntimo con el monto
  en VES de cada factura del proveedor. Antes se subestimaba en Bs 48.304,
  porque reconvertía el USD a la tasa de la tabla. El Libro de Ventas solo
  cambia en céntimos de redondeo.
- Los asientos mixtos del diario CBSL (línea de liquidez en VES y contrapartida
  en USD) absorben diferencias cambiarias reales en la línea en USD: 19 de ellos
  pasan de Bs 1 de ajuste, el mayor de Bs 38.560. Aparecen con el filtro "Ajuste
  Bs > 1" y en la hoja Advertencias de los libros contables. Son informativos: no
  se crean asientos de revalorización.


Ajustes tras la revisión adversarial final (2026-10-10):

- **Tasa congelada en asientos ya posteados**: `_l10n_ve_bs_frozen_rates` lee la
  tasa guardada en la base de datos y el cálculo no la cambia, aunque se
  re-postee la factura de origen de una nota de crédito o se escriba el mismo
  valor en una fecha (Odoo marca el recálculo sin comparar valores). Al
  confirmar, `_post` refresca la tasa con el contexto `l10n_ve_bs_refresh`.
- **Aviso sin permiso**: si el usuario no puede crear tasas, el aviso de "Falta
  la tasa BCV" es un error que indica la «Tasa Bs manual», sin el botón que lo
  llevaría a un error de acceso.
- **Retención de IVA en Bs** (Libros IVA): proporción del IVA Bs almacenado del
  documento, exacta también en facturas de proveedor en VES.
- **Redondeo de caja en Bs** en el widget de totales, calculado en el servidor.

Limitaciones conocidas:

- La tabla de totales del PDF solo contempla el primer subtotal (la base
  imponible).
- En las filas agrupadas del PDF (combos y secciones con precios colapsados), la
  primera fila es la suma exacta de sus líneas y las demás se prorratean con el
  factor efectivo de la sección. Pueden diferir un céntimo.
- En un borrador del formulario, la columna Bs del widget convierte los montos
  del widget a la tasa del borrador. Al confirmar pasa a leer los Bs
  almacenados, con una diferencia posible de céntimos de redondeo.
- Los montos Bs de las listas de facturas no se suman al pie.
- El pedido de la tasa del día aplica al botón Confirmar y a la confirmación
  masiva de la interfaz, no a `_post()`.
