# Changelog — Venezuela: Libros Fiscales de Compras y Ventas

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.3.0] - 2026-08-01

### Añadido

- Cierre de la vía `create()` en `account.move`: en diarios cuyo canal de
  emisión es máquina fiscal (`mf`) o imprenta digital (`digital`), el Nº de
  control ya no puede colarse al crear el documento —RPC directo, importación
  CSV/XLSX o duplicación con `vals`—, solo con el contexto
  `l10n_ve_control_writeback` que usan el bridge de la máquina y el conector de
  imprenta. En forma libre la **primera** transcripción al crear sigue siendo
  legítima; el guard de `write` bloquea las re-escrituras.
- Pruebas de la alícuota combinada del 31 % (con dos impuestos en la línea y
  con un grupo de impuestos), del neteo de líneas negativas, y del cierre de la
  vía `create` en canal `mf` —incluido el caso de que crear sin Nº de control
  siga permitido, porque la factura nace primero y el número llega después con
  el write-back—.

### Corregido

- Las bases se clasifican por la alícuota **combinada** de cada línea: IVA 16 %
  más el adicional del 15 % de bienes suntuarios se registra en la columna del
  31 %, también cuando se aplica como grupo de impuestos (los hijos del grupo se
  expanden antes de sumar). Antes se recorrían las líneas de impuesto sumando
  `tax_base_amount`, lo que **duplicaba** la base cuando varios impuestos la
  compartían y mandaba el 15 % a la columna del 16 %.
- El IVA se sigue tomando de las líneas de impuesto (montos contabilizados
  exactos), pero se imputa a la columna de la alícuota combinada de sus líneas
  base; un impuesto usado en combinaciones distintas dentro del mismo documento
  se reparte proporcionalmente a la base de cada combinación.
- Las líneas negativas —típicamente la deducción de un anticipo— **netean** la
  base del documento en lugar de sumarse en valor absoluto: 100 − 20 dan 80 en
  la columna gravada y 12,80 de IVA, y la fila cuadra contra el total del
  documento. La dirección contable se toma de `is_sale_document`, con lo que las
  notas de crédito conservan su signo sin doble multiplicación.
- Bloque diario del POS (Reglamento LIVA art. 77): la alícuota de cada línea
  también se calcula combinada. Antes se tomaba «el primer impuesto con monto»,
  de modo que el adicional del 15 % caía entero en la columna del 16 % y una
  línea con un grupo de impuestos (cuyo `amount` propio es 0) se contaba como
  exenta.

## [19.0.1.2.0] - 2026-07-31

Primera versión publicada del módulo (commit `5cb578d`). El repositorio nace ya
en `19.0.1.2.0`, así que lo que sigue describe el **estado del árbol
publicado**, no un delta frente a `19.0.1.1.0`.

### Añadido

- **Libro de Ventas** en XLSX con tres bloques y su resumen:
  - I. Ventas a contribuyentes, una fila por documento (Reglamento LIVA
    art. 76), **partido por canal de emisión con subtotal por canal** cuando en
    el período hay más de uno, porque la PA SNAT/2024/000102 art. 6 obliga a
    registrar en forma separada las operaciones emitidas por medios
    electrónicos. Con un solo canal —o sin canal configurado— se escribe una
    sola tabla y el libro no cambia.
  - II. Ventas a no contribuyentes, resumen **diario por sesión de POS** tipo
    Reporte Z (art. 77), con Nº de registro de la máquina fiscal, sesión y
    primera/última orden del día. Solo sesiones cerradas.
  - III. Ventas facturadas a mano en el talonario autorizado durante una falla
    de la máquina (PA SNAT/2011/00071 art. 11), una fila **por orden** —cada
    formato del talonario es un documento con su propio Nº de control—, fuera
    del resumen del art. 77 pero dentro del total del período.
  - Resumen del período por alícuota (art. 72) para cruzar con la Forma 30, con
    línea aparte del IVA retenido por los agentes de retención.
- **Libro de Compras** en XLSX (art. 75): una fila por documento —factura o nota
  de crédito de proveedor, identificada por la `ref` del proveedor— con base y
  crédito fiscal por alícuota, exento/sin derecho a crédito, IVA retenido al
  proveedor y Nº de comprobante, más el mismo resumen del art. 72.
- Montos expresados en bolívares a la **tasa BCV de la fecha de cada
  documento**, no a la del día de impresión: reimprimir un período cerrado da
  exactamente el mismo resultado.
- Columnas de alícuota general 16 %, reducida 8 % y general + adicional 31 %;
  las alícuotas gravadas no estándar se agrupan en la general.
- Tipo de documento SENIAT derivado del asiento (`01` factura, `02` nota de
  débito vía `debit_origin_id` cuando `account_debit_note` está instalado, `03`
  nota de crédito) y Nº del documento afectado.
- Campo `l10n_ve_control_number` («Nº de Control», PA SNAT/2011/00071) en
  facturas de cliente y de proveedor: indexado, con seguimiento en el chatter y
  sin copia al duplicar. Se muestra en el formulario de factura junto a la
  referencia y se refleja en ambos libros.
- **Canal de emisión por diario** (`l10n_ve_emission_channel`): máquina fiscal
  (PA 0071), imprenta digital (PA SNAT/2024/000102), forma libre de imprenta
  autorizada y contingencia. Vive en el diario y no en el asiento porque la
  norma ya obliga a separar las series por medio de emisión (PA
  SNAT/2024/000102 art. 6). Determina la política de edición del Nº de control:
  bloqueado en `mf` y `digital` —lo asigna un tercero—, de una sola escritura en
  forma libre, editable en contingencia, y libre en los diarios sin canal
  (compras y misceláneos, donde el contador transcribe y corrige de rutina). La
  regla se aplica tanto en el `readonly` de la vista como en `write()`, para
  cerrar también la vía RPC.
- `post_init_hook` que siembra un diario «Ventas en Contingencia» por compañía
  con país fiscal VE, **sin cadena de hash** a propósito: replica un documento
  que ya existe en papel y tiene que poder corregirse, así que no debe
  contaminar la cadena inalterable del diario fiscal. Va en un hook y no en un
  XML porque en Odoo 19 `default_account_id` es un Many2one plano, y la cuenta
  se copia del diario de ventas que ya usa la compañía. Es idempotente y
  reejecutable desde `odoo-bin shell`.
- Integración **sin dependencia dura** con `l10n_ve_bw_wh_iva`:
  - Libro de Compras: IVA retenido al proveedor y Nº de comprobante leídos de
    `l10n.ve.iva.wh.voucher` (comprobantes emitidos) a través de su interfaz
    pública `_l10n_ve_get_amount_for_move`.
  - Libro de Ventas: IVA que nos retuvieron los clientes, leído de los pagos
    conciliados con el documento (`matched_payment_ids`). Un pago agrupado
    prorratea la retención por el total de cada factura para no duplicarla, y se
    expresa en Bs a la tasa de la **fecha del pago**, que es cuando se practicó
    la retención.
  - Sin el módulo instalado, los campos no existen y las columnas reportan 0.
- Campo `l10n_ve_machine_serial` en `pos.config` (Nº de registro de la máquina
  fiscal, art. 77 Parágrafo Segundo), configurable desde Ajustes › Punto de
  Venta, bloque «Localización Venezuela».
- Campo `l10n_ve_contingency_control` en `pos.order` (Nº de control del formato
  preimpreso usado con la máquina caída). Es un Char plano almacenado y de solo
  lectura: solo los campos almacenados no computados viajan al servidor en el
  sync del POS. Vive en este módulo, junto al libro que lo lee, para que el
  asistente no necesite guardas por si `l10n_ve_bw_fiscal_printer` no está
  instalado.
- Asistente `l10n.ve.fiscal.book.wizard` (tipo de libro, rango de fechas,
  restricción de fecha inicial ≤ final) que descarga el XLSX como
  `libro_<ventas|compras>_AAAAMMDD_AAAAMMDD.xlsx`, con menús «Libro de Ventas» y
  «Libro de Compras» bajo Contabilidad › Informes › Libros Fiscales (VE) y ACLs
  para los grupos de Facturación y Asesor contable.
- Corrección de zona horaria en los bloques del POS: `pos.order.date_order` es
  Datetime UTC naive, así que los límites del período se construyen en la zona
  del usuario y se convierten a UTC, la misma zona con la que se agrupa por día.
  Una venta de las 21:00 del último día entra al libro; una de las 22:00 de la
  víspera, no.
- Las órdenes POS **facturadas** se excluyen del resumen diario del art. 77 y se
  listan por documento en el bloque del art. 76, con su Nº de factura y de
  control; las de contingencia también salen del resumen, porque no pasaron por
  la máquina y descuadrarían contra el Reporte Z. Los asientos de cierre de
  sesión quedan fuera por el filtro de tipo de documento.
- Batería de pruebas sobre `AccountTestInvoicingCommon`: generación de ambos
  libros y verificación del contenido de las celdas con `openpyxl`, nota de
  crédito referenciada como tipo `03`, restricción de fechas, Nº de control no
  copiado al duplicar, zona horaria del bloque diario, orden POS facturada
  fuera del resumen, retención al proveedor y retención recibida (ambas se
  saltan si `l10n_ve_bw_wh_iva` no está instalado), las cuatro políticas de
  edición del Nº de control, el bypass por contexto de write-back, la creación
  idempotente del diario de contingencia sin hash y el partido del bloque I por
  canal.

## [19.0.1.1.0]

Versión anterior a la publicación del repositorio. Se documenta a partir del
único registro que dejó: el script `migrations/19.0.1.1.0/post-migration.py`,
que ya venía en el árbol de la publicación inicial. No hay fecha respaldada.

### Añadido

- Migración post-instalación que crea el diario de contingencia (PA 0071
  art. 11) en las bases donde el módulo **ya estaba instalado**: el
  `post_init_hook` que lo siembra solo corre al instalar, así que sin esta
  migración ese diario nunca aparecería en producción.
- Los diarios **existentes** se dejan deliberadamente sin canal de emisión: fijar
  el canal bloquea la edición manual del Nº de control, y esa es una decisión
  del contador —la misma política que el hash de inalterabilidad, que también se
  activa a mano—. Sin canal, el comportamiento es idéntico al previo y la
  migración no altera nada de lo que ya funcionaba.

---

No hay registro de versiones anteriores a `19.0.1.1.0`: el repositorio se
publicó ya en `19.0.1.2.0` y el árbol solo conserva el script de migración de
`19.0.1.1.0`.
