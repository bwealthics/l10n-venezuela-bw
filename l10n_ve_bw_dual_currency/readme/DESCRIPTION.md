Venezuela · Doble Moneda (USD / Bs)
===================================

## Qué resuelve

La compañía lleva su contabilidad en dólares (USD), pero en Venezuela la
factura, los libros y la contabilidad se leen en bolívares. Este módulo no
cambia la moneda de la compañía. Guarda en cada asiento la tasa BCV vigente y
en cada apunte su monto en Bs. La pantalla, el PDF de la factura y los libros
leen esos mismos campos, así que las tres salidas dicen lo mismo y cuadran al
céntimo.

Lo que añade:

- La tasa BCV congelada en cada asiento, con su fecha y el aviso de cuando
  falta.
- Debe, Haber y Saldo en Bs por apunte, y base, impuestos, total y saldo en Bs
  por factura.
- Una columna Bs en el widget de totales de la factura, columnas Bs en las
  líneas, en los apuntes, en las listas y en el pivot.
- El PDF de la factura con tabla de totales de tres columnas, importe Bs por
  línea, tasa y nota legal.
- Los Libros IVA leyendo los Bs almacenados.
- Un asistente que genera el Libro Diario, el Libro Mayor y el Balance de
  Comprobación en USD y Bs, en un solo archivo XLSX.

Depende de `l10n_ve_bw_invoice_format` (moneda Bs de referencia y PDF) y de
`l10n_ve_bw_fiscal_books` (Libros IVA). Necesita la librería Python
`xlsxwriter`.

## Regla de conversión

### La tasa del asiento

- La tasa es Bs por 1 unidad de la moneda de la compañía. Se guarda en
  `account.move.l10n_ve_bs_rate`, con 6 decimales, junto con la fecha del
  registro de tasa usado.
- La moneda Bs de referencia es `res.company.l10n_ve_bs_currency_id` (por
  defecto VES). Solo esa moneda es bolívar.
- Se usa la última tasa de esa moneda con fecha menor o igual a la del
  documento. Entre una tasa de la compañía y una global gana la de la compañía,
  igual que en el core.
- La fecha del documento es la fecha de factura en facturas y recibos, la fecha
  contable en los demás asientos y hoy si aún no hay ninguna.
- La tasa queda congelada al confirmar. Editar después la tabla de tasas no
  mueve los Bs de los asientos ya confirmados, y los libros no cambian al
  reimprimirse.
- Si no existe ninguna tasa anterior o igual a la fecha, no se inventa una
  paridad. El asiento queda marcado "Sin tasa Bs" y los Bs de sus líneas en otra
  moneda valen cero.
- Si la moneda Bs es la de la compañía, la tasa es 1 y no se muestra nada en
  doble moneda.

### Los Bs de cada apunte

Se calculan sobre el asiento completo:

1. Línea en VES: su `amount_currency`, exacto. Así los bancos en VES cuadran
   con su extracto.
2. Si el bolívar es la moneda de la compañía: el `balance`.
3. Línea en cualquier otra moneda (USD, VEB, EUR): `balance × tasa`, redondeado
   a la precisión del Bs. Sin tasa vale cero.
4. Recuadre: lo que falte para que el asiento sume cero en Bs lo absorbe una
   sola línea.
   - Candidatas, en este orden: las líneas en moneda distinta de Bs; si no hay,
     las que no son de liquidez; si tampoco, todas.
   - Entre las candidatas gana la línea de cobro o pago (cuenta por cobrar o
     por pagar), luego la de mayor monto y por último la más antigua.
   - Lo absorbido queda a la vista en "Ajuste Bs", por línea y por asiento.

Consecuencias:

- Una línea en VES nunca se toca. En un asiento mixto (línea en VES y líneas en
  USD, como los cobros en Bs del POS) la diferencia cambiaria real la absorbe la
  línea en USD de cobro o pago.
- Un asiento sin tasa no se recuadra: repartir el total sobre una línea sería
  inventar bolívares. Queda marcado y aparece en las advertencias de los libros.
- Un borrador que aún no cuadra en la moneda de la compañía tampoco se recuadra.
  Es el formulario antes de que Odoo genere las líneas de impuesto y de cobro, y
  ahí el residuo no es redondeo sino medio asiento ausente.
- Las diferencias de cambio con ambas líneas en VES y `amount_currency` en cero
  quedan en Bs 0, que es lo correcto: en bolívares no hubo evento.
- No se crean asientos de revalorización. El residuo cambiario en Bs de las
  cuentas en USD es solo informativo.

### Los totales de la factura

- Base imponible, impuestos y total en Bs se suman desde los apuntes. El total
  es base más impuestos y coincide con la línea de cobro o pago.
- El saldo Bs es el saldo del documento si la factura está en Bs. Si no, es el
  total Bs multiplicado por saldo y dividido por total.
- Por línea de producto: subtotal Bs, total Bs y precio unitario Bs. El precio
  se obtiene del importe de la línea, no de `precio × tasa`, para que cantidad
  por precio cuadre con el importe incluso con precios con IVA incluido.
- Por grupo de impuesto: base e impuesto en la moneda del documento y en Bs.
- En asientos que no son facturas, el total es la suma de los saldos positivos.

## Reglas de negocio

- **VEB no es Bs.** Lo denominado en VEB se convierte como cualquier otra
  moneda extranjera, a la tasa BCV.
- **Se pide la tasa del día al confirmar.** Si una factura de cliente o de
  proveedor en borrador no tiene la tasa exacta de su fecha, el botón Confirmar
  y la confirmación masiva desde la lista no avanzan. Muestran un aviso con el
  botón "Cargar la tasa", que abre las tasas de la moneda Bs con la fecha
  prellenada. No se usa la tasa de otro día en silencio.
  - Solo rige para compañías con país fiscal Venezuela. Fuera de VE la tasa se
    congela igual, pero nada se bloquea.
  - No se exige si la factura trae "Tasa Bs manual", si es la reversión de una
    factura que ya tiene tasa, o si no tiene ninguna línea fuera de Bs.
  - Sin fecha de factura se evalúa la fecha de hoy.
- **Los flujos automáticos no se bloquean.** El cierre del POS, los extractos
  bancarios, las diferencias de cambio y cualquier `_post()` directo usan la
  última tasa menor o igual a la fecha y registran la fecha de esa tasa en
  "Fecha de la tasa". Al confirmar, un borrador creado antes de que se cargara
  la tasa del día toma la vigente en ese momento.
- **Las notas de crédito heredan la tasa de la factura de origen**, con su fecha
  de tasa, no la del día en que se emiten. Así una nota de crédito total anula
  la factura también en Bs, y confirmarla no pide tasa.
- **La tasa manual solo se cambia en borrador.** Es la "Tasa Bs manual" y se
  rastrea en el chatter. En un asiento confirmado se rechaza cualquier valor
  distinto. Reescribir el mismo valor o pasar a borrador en la misma escritura sí
  se permite. El botón "Recalcular tasa" la limpia y vuelve a la tabla.
- **No se puede borrar una tasa usada por asientos confirmados.** Aplica a las
  tasas de la moneda Bs de alguna compañía cuando hay asientos posteados con esa
  fecha de tasa y sin tasa manual. Editarla sí se permite, porque cada asiento ya
  guarda su valor. Si queda otra tasa de la misma moneda y día, el borrado
  procede.
- **Una factura emitida en Bs no se duplica.** Sin tasa, o con el documento ya
  en la moneda Bs, no hay bloque Bs ni en pantalla ni en el PDF.
- **Los Libros IVA usan los Bs almacenados** cuando el libro se pide en la
  moneda Bs de la compañía. Si algún documento del período quedó con líneas en
  otra moneda sin convertir (sin tasa), el libro se detiene y lista ejemplos. Un
  documento sin tasa con todas sus líneas en Bs no bloquea.
- **Los libros contables solo incluyen asientos confirmados.**
