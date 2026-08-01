# Manual de la localización venezolana `l10n_ve_bw` (Odoo 19)

Este manual describe qué hace cada módulo, qué hay que configurar antes de
operar y cuál es la rutina mensual. El detalle normativo que justifica cada
comportamiento está en [BASAMENTO-LEGAL.md](BASAMENTO-LEGAL.md).

> No sustituye el criterio del contador. Hay decisiones —activar el hash de
> diarios, fijar el canal de emisión, elegir la alícuota municipal— que el
> software deliberadamente **no** toma por su cuenta porque son irreversibles o
> son criterio profesional.

---

## 1. Orden de instalación

```
l10n_ve_bw_chart            ← primero siempre (plan de cuentas + SPE)
├── l10n_ve_bw_igtf
├── l10n_ve_bw_wh_iva
├── l10n_ve_bw_wh_islr
├── l10n_ve_bw_municipal
├── l10n_ve_bw_payroll          (requiere Enterprise: hr_payroll_account)
└── l10n_ve_bw_fiscal_books
    ├── l10n_ve_bw_invoice_format
    │   └── l10n_ve_bw_einvoice
    └── l10n_ve_bw_fiscal_printer   (requiere pos_restaurant + igtf)

l10n_ve_bw_compliance  ← paraguas: instala todo lo fiscal + OCA auditlog
```

Instalar `l10n_ve_bw_compliance` arrastra la suite fiscal completa y, además,
**crea y suscribe** las reglas de auditoría. Crear la regla sin suscribirla no
audita nada: es el paso que más se olvida, por eso vive en el hook y no en la
documentación.

Requisitos: Python `xlsxwriter`; y `OCA/server-tools` rama 19.0 en el
`addons_path` si se instala el paraguas.

---

## 2. Configuración inicial (una sola vez)

### 2.1 Compañía

| Ajuste | Dónde | Nota |
|---|---|---|
| Plan de cuentas `ve_bw` | Contabilidad → Ajustes → Paquete de localización | 167 cuentas imputables, 6 dígitos, grupos de 1/2/4 dígitos |
| Sujeto Pasivo Especial + fecha de designación | Contabilidad → Ajustes | Enciende la percepción de IGTF y el rol de agente de retención de IVA. La fecha importa: antes de ella no se percibe |
| Moneda y tasa BCV | Contabilidad → Monedas | Todo lo que se expresa en Bs usa la tasa de la fecha del documento, no la del día de impresión |
| Datos de la imprenta autorizada | Contabilidad → Ajustes | Razón social, RIF, número y fecha de su Providencia |
| Alícuota IGTF y cuentas | Contabilidad → Ajustes | 3 % por defecto; cuenta de gasto y cuenta de percepción por enterar |
| Municipio, alícuota y mínimo tributable | Contabilidad → Ajustes | El mínimo es el mayor entre el fijo y `veces MMV × TCMMV` |

### 2.2 Contactos

- **Tipo de contribuyente** (`l10n_ve_taxpayer_type`) en la ficha: determina si
  el cliente retiene IVA y si la venta va al libro como contribuyente o como
  resumen diario.
- RIF en el campo `vat`. La etiqueta del país Venezuela se cambia a «RIF» para
  que no salga rotulada como «Tax ID» en el PDF.

### 2.3 Diarios — canal de emisión (decisión deliberada)

Campo **Canal de emisión (VE)** en cada diario. Fija quién asigna el Nº de
control y si puede escribirse a mano:

| Canal | Asigna el Nº de control | Campo en Odoo |
|---|---|---|
| Máquina fiscal | la impresora, al imprimir | bloqueado |
| Imprenta digital | el proveedor autorizado, por API | bloqueado |
| Forma libre | se transcribe del talonario | se escribe **una sola vez** |
| Contingencia | se transcribe del talonario | editable |
| *(vacío)* | — | libre (caso normal de compras) |

Los diarios se entregan **sin canal**, comportándose como antes. En cuanto se
fija, el Nº de control deja de poder corregirse a mano en ese diario.

### 2.4 Inalterabilidad (hash) — leer antes de activar

Contabilidad → Diarios → *(diario de ventas)* → Ajustes avanzados →
**Comprobación de integridad**.

- Es **irreversible** desde la primera factura publicada.
- Se pierde para siempre «Restablecer a borrador» y «Cancelar» en facturas de
  **venta**: la única corrección pasa a ser la nota de crédito. Compras, nómina
  y misceláneos no se ven afectados.
- **Trampa silenciosa**: publicar en lote desde la vista de lista **excluye** los
  diarios con hash salvo que se marque «Forzar hash», y no muestra ningún error.
  Publicar desde el formulario de la factura.
- Un hueco en la secuencia hace fallar la publicación; si ocurre al cerrar una
  sesión del POS, **la sesión no cierra**. Nunca borrar ni renumerar una factura
  de venta en borrador que ya tenga número.
- El **diario de contingencia no lleva hash, a propósito**: replica un documento
  que ya existe en papel y tiene que poder corregirse.

Complemento: **Audit Trail** (Contabilidad → Ajustes) impide borrar los
registros contables rastreados; solo cancelar o archivar.

---

## 3. Operación diaria

### 3.1 Facturación

El PDF incorpora automáticamente los requisitos de forma: fecha `DDMMAAAA` y
hora `HH.MM.SS` con a.m./p.m. en una sola línea, marca **(E)** junto a las
líneas exentas/exoneradas/no sujetas, Nº de control con su fecha de asignación y
los datos de la imprenta autorizada.

Según el canal del diario:

- **Máquina fiscal (POS)**: la validación de la orden queda **bloqueada** hasta
  obtener número fiscal de la impresora. El navegador de la caja habla por HTTP
  con un bridge local; el servidor Odoo nunca toca la impresora. Botones
  Reporte X y Cierre Z en el POS; el Nº Z se guarda en la sesión. Las
  devoluciones emiten nota de crédito fiscal referenciando la factura original.
- **Imprenta digital**: al publicar, el documento se envía al proveedor
  autorizado, que asigna el Nº de control. Hay proveedores síncronos (devuelven
  el número en la emisión) y asíncronos (hay que consultarlo después): de ahí el
  estado intermedio «Enviado, sin Nº de control» y el cron de consulta, que se
  entrega **desactivado**. Cada llamada queda en bitácora.
- **Contingencia**: se transcriben a mano los documentos emitidos en talonario
  durante la falla, en su propio diario, sin hash.

### 3.2 Pagos e IGTF

Marcar como sujetos a IGTF los diarios en divisas (efectivo USD, Zelle, USDT).

- **Pagos salientes** por esos diarios: asiento automático `Dr Gasto por IGTF /
  Cr cuenta del diario`. El monto es editable y **anulable por pago** — no toda
  operación en divisas causa IGTF.
- **Cobros en divisas**: solo si la compañía es SPE y solo desde la fecha de
  designación, asiento de percepción `Dr cuenta del diario / Cr IGTF Percibido
  por Enterar`.

### 3.3 Retenciones

- **IVA, como sujeto retenido**: al cobrar de un cliente SPE se registra el
  comprobante recibido (write-off a Retenciones de IVA Recibidas de Clientes,
  casilla 66 de la Forma 30).
- **IVA, como agente** (requiere el flag SPE): al pagar facturas de proveedor se
  retiene 75 % o 100 %, con comprobante propio numerado `AAAAMM` + 8 dígitos.
- **ISLR**: la retención se calcula al **registrar el pago** de la factura de
  proveedor (write-off a 210401), según el concepto del art. 9 del Decreto 1.808
  y el % del contacto. Para personas naturales se aplica el sustraendo con la
  Unidad Tributaria vigente a la fecha, tomada del formulario de UT histórica.

---

## 4. Rutina mensual

| # | Tarea | Módulo | Salida |
|---|---|---|---|
| 1 | Libro de Ventas y Libro de Compras del período | `fiscal_books` | XLSX en Bs a la tasa BCV de cada documento |
| 2 | Cotejar el resumen por alícuota contra la Forma 30 | `fiscal_books` | Resumen mensual del art. 72 |
| 3 | Exportar TXT de retenciones de IVA (forma 99035, 16 columnas, tabulado) | `wh_iva` | TXT para el Portal Fiscal |
| 4 | Exportar XML de retenciones de ISLR | `wh_islr` | `RelacionRetencionesISLR` |
| 5 | Emitir comprobantes de retención pendientes | `wh_iva` / `wh_islr` | PDF |
| 6 | Provisión de impuesto municipal | `municipal` | Asiento borrador `Dr Gasto / Cr Impuesto Municipal por Pagar` |
| 7 | Nómina del período y aportes patronales | `payroll` | Recibos art. 106 LOTTT + asiento |

Notas:

- El Libro de Ventas incluye una fila tipo **Reporte Z** por sesión de POS para
  las ventas a no contribuyentes (asiento diario resumido).
- El XML de ISLR aplica la **regla de totalidad** (incluye pagos con retención 0)
  y genera la **declaración sin operaciones** cuando el período no tiene
  comprobantes.
- La provisión municipal de un mes sin ventas es el **mínimo tributable**, no
  cero.

---

## 5. Nómina (requiere Enterprise)

- Estructuras: **Nómina Regular** y **Utilidades**.
- Deducciones del trabajador: IVSS 4 % (tope 5 SM, lunes del período), RPE 0,5 %
  (tope 10 SM), FAOV 1 % (salario integral, sin tope), ISLR según % del AR-I,
  INCES 0,5 % sobre utilidades, retención judicial.
- Aportes patronales: IVSS 9/10/11 % por clase de riesgo, RPE 2 %, FAOV 2 %,
  INCES 2 %, Contribución Especial de Pensiones 9 % con piso IMI en USD.
- **Cesta ticket** indexado en USD: no salarial, fuera del neto, pero base de la
  CEPP.
- **Bimoneda**: el recibo calcula y contabiliza en la moneda de la compañía y
  muestra el contravalor en Bs a la tasa BCV de la fecha de pago.
- **Ninguna tasa está en el código**: todas viven como `hr.rule.parameter`
  versionados por fecha. Cuando cambia el salario mínimo o una alícuota, se
  agrega una versión nueva del parámetro; no se toca Python ni se hace deploy.

---

## 6. Qué NO hace esta suite

Decirlo por adelantado evita sorpresas en una fiscalización:

- **No enciende el hash de diarios.** Es irreversible y es decisión del contador.
- **No audita lecturas.** El registro de lecturas de OCA `auditlog` no funciona
  en todos los modelos; se dejó desactivado en vez de dar cobertura falsa.
- **No audita `account.move.line`** por volumen (cada cierre de caja son cientos
  de líneas). Sus importes quedan protegidos por la cadena de hash. Si hace
  falta, se añade a `AUDITED_MODELS` en `hooks.py` y se re-ejecuta.
- **No protege del acceso directo a PostgreSQL o al sistema operativo.** Ningún
  log de aplicación resiste eso; es control de infraestructura.
- **No es retroactivo.** El registro empieza el día de la instalación: conviene
  anotar la fecha del despliegue y guardar un respaldo como línea base.
- **No incluye un adaptador real de imprenta digital.** Se entrega el núcleo y un
  proveedor **simulado**; el adaptador concreto depende de contratar la imprenta
  y recibir su documentación y credenciales.
- **No borra los logs de auditoría.** El cron «Auto-vacuum audit logs» de OCA
  viene desactivado a propósito: la PA SNAT/2024/000102 art. 18.7 exige conservar
  10 años. A cambio la tabla crece; conviene vigilar su tamaño.

---

## 7. Arquitectura, para quien quiera extender

- **Imprenta digital**: toda la lógica fiscal vive en
  `account.move._l10n_ve_edoc_document_vals()`, que produce un dict **neutro**.
  El proveedor concreto solo traduce ese dict a su dialecto implementando cuatro
  métodos del modelo abstracto `l10n.ve.edoc.provider`. Cambiar de imprenta es
  escribir un archivo.
- **Máquina fiscal**: el bridge es un proceso local independiente; Odoo se
  comunica con él desde el navegador de la caja con un token compartido. Cambiar
  de marca de impresora es reimplementar el bridge, no el módulo.
- **Nómina**: tasas y montos legales como `hr.rule.parameter` versionados por
  fecha.
