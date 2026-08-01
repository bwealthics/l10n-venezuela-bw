# Basamento legal de la suite `l10n_ve_bw`

Norma por norma: qué dice, qué decisión de diseño produjo en el código y qué
queda abierto. Investigación consolidada al **2026-07**, contrastada contra
fuentes primarias (Gaceta Oficial / SENIAT) y secundarias profesionales (KPMG
Ostos Velázquez, PwC, Grant Thornton, MOORE Venezuela, VenAmCham, Acceso a la
Justicia, IVECOFI).

> Este documento describe el criterio con el que se construyó el software. **No
> es asesoría fiscal.** La normativa venezolana cambia con frecuencia y por
> instrumentos de rango distinto (leyes, decretos de alícuota, providencias,
> exoneraciones anuales renovables). Antes de configurar producción, verificar
> la vigencia en Gaceta Oficial.

---

## 1. IVA — libros, forma y declaración

| Norma | Contenido usado | Efecto en el código |
|---|---|---|
| Reglamento de la LIVA, **arts. 70–78** | Obligación de llevar Libros de Compras y Ventas y su contenido | `fiscal_books`: generación XLSX |
| Art. **76** | Ventas a contribuyentes: una fila por documento | Detalle documento a documento en el Libro de Ventas |
| Art. **77** | Ventas a **no** contribuyentes: asiento **diario** resumido | Fila tipo Reporte Z por sesión de POS |
| Art. **72** | Resumen mensual por alícuota | Hoja de resumen para cruzar con la Forma 30 |
| Art. **75** | Contenido del Libro de Compras | Libro de Compras |

**Decisión de diseño**: los montos se expresan en bolívares a la **tasa BCV de
la fecha de cada documento**, no a la del día de impresión del libro. Reimprimir
un libro de un período cerrado tiene que dar exactamente el mismo resultado.

---

## 2. Facturación y Nº de control

### 2.1 Providencia SNAT/2011/00071 (G.O. 39.795 del 08/11/2011)

Régimen general de emisión de facturas: denominación «Factura», numeración única
y consecutiva, datos del emisor (razón social, RIF, domicilio fiscal),
descripción, monto e IVA discriminado, **Nº de control** asignado por imprenta
autorizada. Las notas de crédito y débito deben referenciar fecha, número y
monto de la factura afectada.

- Art. **11**: régimen de **contingencia** (talonario durante fallas).
- Arts. **13.8, 14.5 y 32.2**: marca de las operaciones exentas, exoneradas o no
  sujetas.
- Máquinas fiscales: siguen vigentes, con reporte global diario (Z).

**Efecto**: campo de Nº de control con **canal de emisión por diario** —quién lo
asigna determina si el campo es editable—; diario de contingencia **sin cadena
de hash**, porque replica un documento que ya existe en papel; nota de crédito
fiscal del POS referenciando la factura original.

### 2.2 Providencia SNAT/2024/000102 (G.O. 43.032 del 19/12/2024)

Emisión por **medios digitales**. Corrección importante frente a la lectura
difundida: **la obligación no es general y las máquinas fiscales no fueron
eliminadas** — la 000102 las preserva expresamente.

- **Obligados**: quienes operan exclusivamente por medios electrónicos/portales
  web; y usuarios de máquina fiscal con ventas en línea simultáneas (solo para
  esas operaciones, con **Libro de Ventas separado**).
- **Voluntario** para el resto de personas jurídicas, previa autorización del
  SENIAT (30 días hábiles para resolver).
- Documentos cubiertos: facturas, notas de débito y crédito, guías de despacho y
  **comprobantes de retención**. La imprenta digital autorizada asigna el Nº de
  control.
- Plazo para obligados: primer día del tercer mes calendario tras la vigencia
  (≈ 01/03/2025).
- Art. **7.6**: formato de fecha `DDMMAAAA` y hora `HH.MM.SS` con a.m./p.m.
- Art. **7.8**: marca de exentos. Art. **7.14**: datos de la imprenta
  autorizada (razón social, RIF, nº y fecha de su Providencia).
  Art. **7.15**: Nº de control y su fecha de asignación.
- Art. **18.7**: conservación de los documentos **10 años**.
- Deroga la PA SNAT/2014/0032, manteniendo sus autorizaciones.
- **PA SNAT/2024/000121** (misma Gaceta): requisitos para proveedores de sistemas
  informáticos de facturación.

**Efecto**: `invoice_format` imprime fecha y hora en **una sola línea** —ambos
artículos admiten separadores, así que no hace falta duplicar la fecha—, la
marca «(E)» y los datos de imprenta como texto libre (idénticos bajo régimen
físico y digital, por eso ese módulo **no** depende del conector). `einvoice`
implementa el flujo de asignación de Nº de control con estados síncrono y
asíncrono. El cron de auto-vacuum del audit log se deja **desactivado** por el
art. 18.7.

---

## 3. Retenciones de IVA — PA SNAT/2025/000054

**G.O. 43.171 del 16/07/2025, vigente desde el 01/08/2025. Deroga la PA
SNAT/2015/0049.** Cualquier implementación que siga citando la 0049 está
desactualizada.

- Retención general del **75 %** del impuesto causado; **100 %** cuando el IVA no
  está discriminado, la factura no cumple los requisitos legales, o el proveedor
  aparece sujeto a 100 % en el Portal Fiscal.
- Art. **3**: **exclusión de las operaciones entre agentes de retención**.
- Art. **16**: comprobante con numeración de **14 caracteres** (`AAAAMM` + 8
  dígitos), emitido dentro de los **2 primeros días hábiles del período
  siguiente**.
- Declaración y entero **quincenales**, por calendario de Sujetos Pasivos
  Especiales (PA SNAT/2025/000091 para el ejercicio 2026).
- Archivo **TXT forma 99035**, 16 columnas delimitadas por tabulaciones.

**Efecto**: `wh_iva` implementa las dos direcciones —agente y sujeto retenido—
porque una empresa venezolana normalmente es ambas cosas a la vez; el rol de
agente se activa por el flag SPE de la compañía. El RIF va al TXT en formato del
portal, sin guiones.

---

## 4. Retenciones de ISLR — Decreto 1.808

**Decreto 1.808 del 23/04/1997, G.O. 36.203 del 12/05/1997.** Base: 100 % del
pago.

Correcciones frente a errores frecuentes:

1. **Las compras de bienes no llevan retención de ISLR.** El «2 % compras» no
   existe: el 2 % es **servicios** pagados a personas jurídicas domiciliadas. Si
   la factura mezcla bienes con servicios, se retiene sobre el total.
2. El XML mensual no lo rige la PA SNAT/2011/0113 (no se pudo confirmar su
   existencia ni su objeto), sino la **Providencia Nº 0095 del 22/09/2009, G.O.
   39.269**, con el **Manual Técnico SENIAT v3.1**.

| Concepto (art. 9) | PN residente | PJ domiciliada |
|---|---|---|
| Honorarios profesionales | 3 % | 5 % |
| Comisiones | 3 % | 5 % |
| Servicios (obras y prestación de servicios) | 1 % | 2 % |
| Fletes / transporte | 1 % | 3 % |
| Arrendamiento de inmuebles | 3 % | 5 % |
| Arrendamiento de muebles | 3 % | 5 % |
| Publicidad y propaganda | 3 % | 5 % |
| Fondos de comercio | 3 % | 5 % |
| Primas a aseguradoras no domiciliadas | 10 % sobre el 30 % | 10 % sobre el 30 % |

- Personas naturales residentes: **sustraendo = UT × % × 83,3334**, con umbral
  mínimo por pago. Las sociedades de personas retienen como PN.
- Art. **24**: comprobante de retención.
- Declaración **mensual** con archivo XML `RelacionRetencionesISLR`, incluida la
  **regla de totalidad** (se relacionan también los pagos con retención 0) y la
  **declaración sin operaciones** (código 000 del anexo 6.1).

**Efecto**: `wh_islr` modela la Unidad Tributaria como **histórico por Gaceta
Oficial**, no como constante — el sustraendo de un pago viejo debe recalcularse
con la UT que estaba vigente ese día. La retención se dispara al **pagar**, no
al facturar, que es cuando la norma la exige.

---

## 5. IGTF

Historia legislativa correcta (aquí se acumulan los errores de cita):

- **Ley original**: Decreto 2.103, G.O.E. 6.210 (2015).
- **Ley de Reforma Parcial: G.O.E. 6.687 del 25/02/2022**, vigente a los 30 días
  (28/03/2022). Nuevo art. 4 de sujetos pasivos (6 numerales), art. 8 de
  exenciones, art. 13 de rangos, art. 16 (declaración diaria para débitos
  bancarios; calendario de retenciones de IVA de especiales para pagos sin
  mediación), art. 23 (potestad de exonerar) y art. 24 (alícuotas transitorias
  2 %/3 %).
- **Decreto 4.972, G.O.E. 6.821 del 12/07/2024**, vigente desde el 15/07/2024:
  alícuota **0 %** para los numerales 1 al 4 (pagos en moneda nacional). Art. 2:
  los numerales 5 y 6 (**divisas y criptoactivos**) siguen al **3 %** del art. 24.
- **No existe** ninguna reforma de la Ley de IGTF en la G.O.E. 6.865 ni con
  fecha 25/07/2024. En julio de 2024 hubo un decreto de alícuota, no una reforma.

Puntos que suelen entenderse mal:

- Las operaciones en bolívares **no fueron derogadas ni exoneradas**: siguen
  siendo hecho imponible, con alícuota 0 %.
- El sujeto pasivo **no es solo el SPE**: es contribuyente cualquier persona,
  natural o jurídica, que pague en divisas o cripto, incluido quien paga a un
  SPE.
- Los **SPE que reciben pagos en divisas sin mediación bancaria** actúan como
  **agentes de percepción** (PA SNAT/2022/000013, G.O. 42.339 del 17/03/2022) y
  declaran **quincenalmente** por el Portal Fiscal. La banca entera diariamente.
- El no pago de IGTF con **tarjetas internacionales en punto de venta** no es una
  exención de la ley: es una **exoneración anual renovable** (art. 23). Último
  decreto confirmado: **4.924, G.O. 42.823 del 21/02/2024**, vigente hasta el
  26/02/2025.

**Efecto**: el IGTF se modela por **diario**, no por moneda —lo que determina el
hecho imponible es el medio de pago— y el monto es **editable y anulable por
pago**, porque hay operaciones en divisas que no lo causan. La percepción exige
el flag SPE **y** que la fecha del cobro sea posterior a la de designación.

---

## 6. Impuesto municipal (patente de industria y comercio)

Base: **LOPPM** y la **ordenanza del municipio** donde se ejerce la actividad —
por eso alícuota, mínimo tributable y clasificador son **configuración**, no
código. El mínimo tributable se expresa habitualmente en **veces MMV** (múltiplo
del TCMMV publicado por el BCV; hasta 30 veces en el sector alimentos).

**Efecto**: el asistente calcula `max(ingresos brutos × alícuota, mínimo
tributable)`, donde el mínimo es el mayor entre el fijo y `veces MMV × TCMMV`
convertido a la moneda de la compañía. **Un mes sin ventas provisiona el
mínimo**, no cero.

---

## 7. Contabilidad y plan de cuentas

**No existe en Venezuela un plan de cuentas único obligatorio.** El marco
contable son las **VEN-NIF** (BA VEN-NIF Nº 0, adopción de NIIF, FCCPV); cada
empresa estructura su catálogo. La estructura 1 Activos / 2 Pasivos /
3 Patrimonio / 4 Ingresos / 5 Costos / 6 Gastos es una **convención difundida**,
no una norma.

**Efecto**: `l10n_ve_bw_chart` ofrece esa convención en 6 dígitos como plantilla
razonable y auditable, no como imposición; el `l10n_ve` oficial de Odoo usa 7
dígitos y llega hasta el 9 en grupos de resultado y orden. Son alternativas, no
competidores.

---

## 8. Nómina

| Concepto | Base legal | Parámetro |
|---|---|---|
| Recibo de pago | **LOTTT art. 106** | PDF bimonetario |
| IVSS trabajador | Ley del Seguro Social | 4 %, tope 5 salarios mínimos, lunes del período |
| IVSS patrono | Ley del Seguro Social | 9/10/11 % según clase de riesgo |
| RPE (paro forzoso) | LRPE | 0,5 % trabajador (tope 10 SM) / 2 % patrono |
| FAOV | Ley del Régimen Prestacional de Vivienda y Hábitat | 1 % trabajador sobre salario integral, sin tope / 2 % patrono |
| INCES | Ley INCES | 0,5 % sobre utilidades / 2 % patrono |
| ISLR | LISLR — formulario **AR-I** | % declarado por el trabajador |
| Contribución Especial de Pensiones | Ley de Protección de las Pensiones | 9 %, piso IMI en USD |
| Cesta ticket | Ley de Alimentación | No salarial, fuera del neto, **sí** base de la CEPP |

**Decisión de diseño central**: ninguna tasa ni monto legal está en el código.
Todos son `hr.rule.parameter` **versionados por fecha de vigencia**. En un país
donde el salario mínimo y las alícuotas cambian por Gaceta varias veces al año,
poner una tasa en Python garantiza que un recálculo de un período viejo salga
mal.

---

## 9. Sanciones que motivan controles del software

**COT 2020**: no llevar los libros, llevarlos con atraso o no conservarlos, no
emitir comprobantes de retención en plazo y no enterar lo retenido acarrean
multas y, en el caso del enteramiento tardío o la apropiación de lo retenido,
consecuencias penales. Ese riesgo es la razón de tres decisiones:

1. La validación del POS se **bloquea** hasta obtener número fiscal.
2. El Nº de control se vuelve **no editable** en cuanto el diario declara un
   canal de emisión automático.
3. El audit log se entrega **suscrito**, no solo creado.

---

## 10. Puntos abiertos — verificar antes de configurar producción

1. **Prórroga 2025 y 2026 de la exoneración del IGTF** (tarjetas internacionales,
   remesas, pagos en divisas a no SPE). El último lapso confirmado venció el
   **26/02/2025** (Decreto 4.924). No se encontró evidencia de renovación.
2. **PA SNAT/2011/0113**: citada habitualmente para el XML de ISLR; no se pudo
   confirmar su existencia ni su objeto. La norma verificada es la **0095/2009**.
3. **Unidad Tributaria vigente**: última confirmada Bs. 43 (G.O. 43.140 del
   02/06/2025). Verificar antes de calcular sustraendos.
4. **Calendario de SPE del ejercicio corriente** (PA SNAT/2025/000091 para 2026):
   se publica anualmente.

---

## 11. Fuentes

Textos primarios (Gaceta Oficial, Asamblea Nacional, SENIAT) y notas técnicas de
Grant Thornton Venezuela, KPMG Ostos Velázquez, MOORE Venezuela, PwC, VenAmCham,
Acceso a la Justicia, Finanzas Digital e IVECOFI. Las URL de cada instrumento
están registradas junto a su sección en las notas de investigación del proyecto;
se omiten aquí porque los repositorios secundarios cambian de dirección con
frecuencia — el criterio es citar **instrumento, Gaceta y fecha**, que es lo que
permite localizarlo en cualquier fuente.
