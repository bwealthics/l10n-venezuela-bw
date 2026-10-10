## Antes de empezar

- La compañía debe tener la moneda Bs de referencia (VES). Se elige en
  Contabilidad > Configuración > Ajustes, bloque "Localización Venezuela"
  (Comprobante), opción "Equivalente en bolívares", campo "Moneda".
- Las tasas BCV se cargan como tasas de la moneda VES (en MISOYMASA las carga
  n8n cada día). La tasa es "Bs por 1 USD".
- Si la moneda Bs es la de la compañía, o la factura está emitida en Bs, el
  módulo no muestra nada en doble moneda.

## Factura y asiento (formulario)

- **Cabecera, fila "Tasa BCV".** Debajo del diario y la moneda, en una sola
  línea: la tasa en Bs por USD y su fecha, por ejemplo `875,6505 Bs por USD ·
  09-10-2026`. El símbolo es el de la moneda Bs. Solo se ve si hay tasa.
- **Banner amarillo** (borrador). Dice que la tasa guardada ya no coincide con
  la vigente para la fecha del documento. Pasa cuando se cargó la tasa del día
  después de crear el borrador. El botón "Recalcular tasa" la actualiza. Al
  confirmar se congela la vigente de todos modos.
- **Banner rojo.** No existe ninguna tasa para la fecha: los Bs no se calculan.
  Hay que cargarla en Contabilidad > Configuración > Monedas.
- **Totales.** El widget de totales gana una columna Bs a la derecha de cada
  subtotal, de cada grupo de impuesto, del redondeo (si hay) y del total. Junto
  al saldo pendiente aparece "Saldo Bs".
  - En un borrador, la columna convierte los montos del widget a la tasa del
    borrador, porque Odoo aún no generó las líneas de impuesto y de cobro. Al
    confirmar pasa a leer los Bs almacenados. La diferencia posible es de
    céntimos de redondeo.
- **Líneas de factura.** Dos columnas de solo lectura: "Subtotal Bs" (visible) y
  "Precio Bs" (oculta, se activa en el selector de columnas).
- **Apuntes contables.** Columnas "Debe Bs" y "Haber Bs" con su total al pie.
- **Pestaña "Otra información".** En facturas y en asientos varios: "Tasa Bs"
  (solo lectura, 4 decimales), "Fecha de la tasa", "Ajuste Bs" y "Tasa Bs
  manual". Esta última solo es editable en borrador.

### Tasa manual

Escriba la tasa en "Tasa Bs manual" mientras la factura está en borrador. Esa
factura no pide tasa del día al confirmar. El botón "Recalcular tasa" borra la
tasa manual y vuelve a la tabla. Confirmada, la tasa manual no se puede cambiar.

### Confirmar una factura

- Con la tasa del día cargada, se confirma como siempre y queda congelada.
- Sin ella, el botón Confirmar y la confirmación masiva desde la lista muestran
  "Falta la tasa BCV del dd-mm-aaaa". El botón "Cargar la tasa" abre las tasas
  de la moneda Bs con la fecha prellenada. Cargada la tasa, se vuelve a
  confirmar. La alternativa es escribir una "Tasa Bs manual".
- Una nota de crédito por reversión no pide tasa: usa la de su factura de
  origen.

## Listas y búsquedas

- **Facturas** (clientes, proveedores, notas de crédito): "Total Bs" visible;
  "Saldo Bs" y "Tasa Bs" ocultas. No llevan suma al pie: los montos Bs son
  siempre positivos y el total del core lleva signo, así que sumarlos mezclaría
  notas de crédito con facturas.
- **Apuntes contables.** "Debe Bs" y "Haber Bs" visibles con suma al pie. "Saldo
  Bs" oculta, también con suma. Las variantes agrupadas de la lista las heredan.
- **Pivot de apuntes.** "Saldo Bs" disponible como medida.
- **Pagos.** El formulario muestra "Tasa Bs" y "Monto Bs" cuando el pago tiene
  asiento y hay tasa. La lista tiene "Monto Bs" oculto. No es un campo
  almacenado, por eso no se suma ni se ordena.
  - Pago en Bs: su monto. Otro caso: los Bs de las líneas de liquidez de su
    asiento, que son los que verá el Mayor del banco. Un pago sin asiento se
    convierte con la tabla a la fecha del pago, solo para mostrar.
- **Filtros** en la búsqueda de asientos y de facturas:
  - "Sin tasa Bs": asientos marcados sin tasa.
  - "Ajuste Bs > 1": asientos cuyo recuadre pasa de 1 Bs en cualquier sentido.
    Son diferencias cambiarias reales, no redondeo. Por ejemplo, los cobros en
    Bs del POS cuya contrapartida está en USD.

## Ajustes del PDF

Contabilidad > Configuración > Ajustes, bloque "Localización Venezuela" (Doble
moneda), debajo del de Comprobante. Son dos interruptores por compañía:

- **Mostrar Importe Bs por línea en la factura:** activo por defecto.
- **Mostrar Precio Bs por línea en la factura:** apagado por defecto. Con
  precios de varios decimales la columna confunde más de lo que aclara.

Ambas columnas solo salen si el documento tiene tasa y su moneda no es la Bs.

## PDF de la factura

Aplica a la factura normal y a la de contingencia, que comparten plantilla.

- **Bloque de información.** "Tasa BCV": `1 USD = X VES` y "del dd-mm-aaaa".
- **Tabla de totales de tres columnas** (concepto, moneda del documento, Bs):
  Subtotal (si hay impuestos); por cada grupo de impuesto, "B.I. <grupo>" y
  "<grupo>"; Redondeo si existe; Total; y Saldo pendiente.
  - El saldo pendiente se imprime solo si dice algo (ni factura recién emitida
    ni ya cobrada) y solo cuando el core no imprime ya su "Amount Due", que es el
    caso de las facturas con pagos listados.
  - En las filas de pagos la celda Bs queda vacía. El pago pudo hacerse a otra
    tasa y convertirlo con la del documento sería inventar una cifra. El "Amount
    Due" sí lleva su saldo en Bs.
  - Solo se contempla el primer subtotal (la base imponible).
- **Columnas por línea.**
  - "Importe Bs" repite lo que muestra la columna de importe del core: el
    subtotal, o el total con impuestos si la compañía trabaja con precios con
    impuestos incluidos.
  - "Precio Bs" va junto al precio unitario.
  - En secciones y subsecciones, el total en Bs es la suma de sus líneas. En
    filas agrupadas, la primera es la suma exacta y las demás se prorratean.
    Pueden diferir un céntimo de la suma de líneas.
- **Nota legal.** Equivalente en bolívares a la tasa del BCV, con la tasa a 4
  decimales y su fecha. Cita la PA SNAT/2011/0071 (art. 13, num. 14), la Ley del
  IVA (art. 25) y la Ley del BCV (art. 128).
- Sin tasa, o con la factura emitida en Bs, el PDF sale sin ninguna cifra en Bs.

## Libros IVA

Contabilidad > Reporting > Libros Fiscales (VE) > Libro de Ventas o Libro de
Compras. El procedimiento no cambia. Lo que cambia es el origen de los Bs:

- Base por alícuota, exento e IVA salen de los Bs almacenados por apunte.
- El total del documento sale de "Total Bs" y las notas de crédito conservan la
  tasa de su factura.
- El IVA retenido se convierte a la tasa congelada del asiento, para que siga
  siendo el 75 % o el 100 % del IVA de la misma fila.
- Si algún documento del período tiene líneas en otra moneda sin convertir (sin
  tasa), el libro no se genera. El mensaje cuenta los documentos y lista hasta
  10. Se carga la tasa en Monedas y se vuelve a generar.
- Si el libro se pidiera en otra moneda que la Bs de la compañía, se conserva la
  conversión original.

## Libros contables (Diario, Mayor, Balance)

Contabilidad > Reporting > "Libros contables (Diario, Mayor, Balance)". Lo ven
los grupos de solo lectura, facturación y administrador de contabilidad.

1. Elija la compañía y el período (Desde, Hasta). Por defecto: del día 1 del mes
   a hoy.
2. Opcional: "Diarios (solo Libro Diario)". Recorta únicamente el Libro Diario.
   El Mayor y el Balance incluyen siempre todos los diarios, porque el saldo de
   una cuenta no tiene sentido sin parte de sus movimientos.
3. Pulse "Generar". Descargue el archivo `libros_contables_AAAAMMDD_AAAAMMDD.xlsx`.

Solo entran asientos confirmados. La compañía debe tener moneda Bs. Si el
período supera 1.000.000 de apuntes, el asistente pide un rango menor en lugar
de truncar el archivo.

El XLSX trae cuatro hojas. Cada una lleva en la cabecera la empresa, el RIF y el
período. Diario, Mayor y Balance muestran la moneda de la compañía y Bs lado a
lado.

- **Libro Diario.** Un renglón por apunte, por fecha y número de asiento: Fecha,
  Asiento, Diario, Cuenta, Nombre de la cuenta, Tercero, Descripción (o la
  referencia del asiento si el apunte no tiene), Debe y Haber en cada moneda.
  Fila de totales al pie.
- **Libro Mayor.** Una sección por cuenta: saldo inicial, movimientos con saldo
  corrido en cada moneda y fila "TOTAL CUENTA" con el saldo final. Los saldos
  inicial y final de cada cuenta son los del Balance.
- **Balance de Comprobación.** Por cuenta: saldo inicial, Debe, Haber y saldo
  final en cada moneda. Positivo es deudor y negativo es acreedor. Al pie, los
  totales y la "Verificación de cuadre".
- **Advertencias.** Las mismas verificaciones de cuadre y la lista de asientos a
  revisar.

### Saldos iniciales

- Cuentas que arrastran saldo (activo, pasivo, patrimonio): todo lo anterior a
  la fecha "Desde".
- Cuentas de resultado: solo desde el inicio del ejercicio fiscal hasta "Desde".
  El inicio del ejercicio aparece en la hoja del Balance.
- El resultado de ejercicios anteriores va aparte, en una fila "Resultados no
  distribuidos de ejercicios anteriores". Se asigna a la cuenta de resultados no
  distribuidos de la compañía (la de menor código) o queda como fila virtual sin
  cuenta. Sin esa fila el balance no sumaría cero. No tiene movimientos.
- Las cuentas sin saldo inicial ni movimientos no se listan.

### Cuadres

La hoja del Balance y la de Advertencias muestran seis verificaciones. Cada una
debe dar cero y se marca OK, o DESCUADRE en el Balance y FALLA en Advertencias:

- Σ Debe menos Σ Haber del período, en la moneda de la compañía y en Bs.
- Σ de saldos iniciales, en ambas monedas.
- Σ de saldos finales, en ambas monedas.

### Asientos a revisar

La hoja Advertencias lista, hasta 500 por tipo, con una fila final de conteo si
hay más:

- **Sin tasa Bs:** hasta la fecha "Hasta". Se indica si el asiento es del
  período o anterior, porque uno anterior también distorsiona los saldos
  iniciales.
- **Ajuste Bs mayor a 1:** asientos del período con recuadre de más de 1 Bs en
  cualquier sentido. Posible diferencia cambiaria real.
- **Asiento descuadrado en Bs (o en la moneda de la compañía):** hasta la fecha
  "Hasta", incluidos los anteriores al período. Los asientos sin tasa no se
  repiten aquí.

Si no hay nada que listar y todos los cuadres dan cero, la hoja dice "Sin
advertencias". Si un cuadre falla y ningún asiento lo explica, lo indica y pide
revisar saldos de apertura o asientos de otras compañías o ejercicios.

## Instalación y actualización

Al instalar, Odoo calcula la tasa y los Bs de todos los asientos existentes. Los
asientos anteriores a la primera tasa cargada quedan marcados "Sin tasa Bs" (si
todas sus líneas están en VES, sus Bs son exactos y no bloquean los Libros IVA).
Para revisar el resultado use los filtros "Sin tasa Bs" y "Ajuste Bs > 1".
