# Changelog — Venezuela: Nómina (BWEALTHICS)

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.3.1.0] - 2026-08-01

Correcciones de los pasivos laborales en el borde del egreso: la fracción del
finiquito y el devengo mensual daban resultados distintos para el mismo
trabajador.

### Añadido

- Campo `date` en la línea de provisión (`l10n.ve.payroll.provision.line`): los
  abonos de garantía trimestral y de días adicionales se asientan en el libro
  con la **fecha del aniversario que los causa**, no con el último día de la
  corrida. Sin fecha, se mantiene el fin de mes. Es lo que permite que un
  egreso intramensual incluya solo los depósitos ya cumplidos.

### Cambiado

- El campo del asistente de finiquito «Garantía trimestre en curso» pasa a
  llamarse **«Garantía no depositada»** y suma dos cosas: los 15 días del
  trimestre iniciado y no completado (el derecho al depósito nace al iniciar el
  trimestre, art. 142.a LOTTT) **más** los abonos del mes de egreso —trimestral
  y días adicionales— que todavía no tengan línea en el libro, porque el
  finiquito se paga dentro de los cinco días del egreso (art. 142.f) y la
  corrida del mes suele postearse después. El barrido se limita **a propósito**
  al mes de egreso: los saldos de apertura se cargan como una línea manual
  única, y contar trimestres de toda la antigüedad contra el libro pagaría dos
  veces.
- El saldo de garantía e intereses del finiquito se corta a **fin del mes de
  egreso** y no a la fecha exacta: las corridas anteriores a esta versión
  fechan sus depósitos al último día del mes, y el cierre del libro que hace
  `action_create_payslip` los compensa igual.

### Corregido

- **Días de bono vacacional del año de servicio en curso**: son `15 + años
  cumplidos` con tope 30 (art. 192 LOTTT), no `15 + (años − 1)`. La fórmula
  anterior subestimaba en un día la alícuota del bono vacacional, y con ella la
  base integral del FAOV (`_ve_bono_vacacional_days`) y el salario integral
  diario de las provisiones (`_employee_integral_daily`). Ambos quedan alineados
  con la fracción que ya calculaba el asistente de finiquito.
- La corrida de provisiones **excluye a los trabajadores ya liquidados**: si
  existe un recibo de liquidación (`VELIQ`) no cancelado dentro del empleo
  vigente, el trabajador no se provisiona; el finiquito ya pagó en efectivo
  fracciones, trimestre en curso e intereses, y volver a devengarlos dejaba
  saldos huérfanos en el libro de garantía. Un reingreso posterior a la
  liquidación sí vuelve a contar.
- Los **aniversarios posteriores a la fecha de egreso ya no devengan**: el
  cómputo de garantía trimestral y de días adicionales se corta en
  `contract_date_end` en lugar del fin del período de la corrida.
- `action_post` **vuelve a filtrar los empleados al contabilizar** y elimina las
  líneas de quien dejó de calificar. El cron genera el borrador el día 1, así
  que un finiquito firmado a mitad de mes cerraba al trabajador después del
  cálculo y sus líneas se posteaban igual.
- Pruebas actualizadas al nuevo criterio: días adicionales del segundo año con
  bono vacacional de 17 días, y egreso a exactamente seis meses cuando el
  aniversario trimestral cae en el mes de egreso y aún no está depositado.

## [19.0.3.0.0] - 2026-07-31

Primera versión publicada en el repositorio (commit `e10a611`); el árbol nace
ya en `19.0.3.0.0`. Lo que sigue es el delta frente a `19.0.2.0.0`, reconstruido
del comentario del script de migración de esta versión y de la sección «v3» del
README.

### Añadido

- Asistente **«Declaraciones VE»** (`l10n.ve.declaraciones.wizard`): un XLSX de
  siete hojas calculado desde los recibos validados del período, con los montos
  en bolívares a la **tasa BCV congelada de cada recibo** (no a la del día de
  impresión), de modo que reimprimir un período cerrado da el mismo resultado.
  Cada recibo se atribuye a un solo período por contención de `date_to`, y un
  recibo sin tasa congelada aborta la generación con `UserError` en vez de
  declarar un cero.
  - **IVSS-TIUNA**: por trabajador, con las cotizaciones de los recibos
    regulares **y** de los de vacaciones (el pago de vacaciones también cotiza),
    contando los lunes solo del recibo regular porque el de vacaciones solapa
    las mismas semanas. El salario semanal se reconstruye de los propios
    agregados de la fila, de forma que semanal × 4 % × lunes reproduce el IVSS
    retenido.
  - **FAOV**: salario integral en Bs, ahorro obligatorio del 1 % del trabajador,
    aporte patronal del 2 % y el 3 % total.
  - **INCES**: por mes, base de salario normal, 2 % patronal y ½ % retenido
    sobre utilidades, incluida la retención practicada en un finiquito.
  - **CEPP Forma 19 DPP**: agregación exacta por **trabajador y mes de pago**,
    con el piso IMI aplicado una sola vez al mes y una columna de diferencia
    contra lo devengado recibo a recibo. Cierra el hueco que dejaba el cálculo
    por recibo, que aplica el piso prorrateado y sobre-declara en un mes con
    nómina regular bajo el piso más pago de utilidades.
  - **Headcount CEPP** mensual para el informe trimestral y **RNET** con altas y
    bajas del período; el salario del RNET nunca baja del contractual
    mensualizado, para no sub-declarar por recibos prorrateados por ausencias o
    por egreso a mitad de mes.
  - **Libro de horas extra** por trabajador y año, con acumulado y alerta al
    superar las 100 h anuales (art. 178 LOTTT). El límite semanal de diez horas
    no es derivable de inputs mensuales y se controla al capturar.
- **AR-C anual** (Decreto 1.808 art. 24): informe PDF por trabajador con las
  remuneraciones gravables y el ISLR retenido mes a mes, en bolívares y en
  moneda de la compañía, para entregarlo antes del 31 de enero. Sigue el
  criterio de lo **pagado** —el ejercicio es el de `l10n_ve_payment_date`, que
  es cuando se retiene— y el asistente, sin selección explícita, toma a todos
  los trabajadores con nómina en el ejercicio.
- Aporte patronal **INCES del 2 % en la estructura de Vacaciones**
  (`rule_ve_vac_inces_pat`), mapeado a 610304 / 210506.
- `migrations/19.0.3.0.0/post-migration.py`, que reejecuta el mapeo de cuentas
  en el upgrade porque el `post_init_hook` solo corre al instalar. Es la regla
  del módulo: todo cambio de `RULE_ACCOUNTS` exige subir la versión y traer su
  script de migración.
- ACL de ambos asistentes para el grupo de usuario de nómina, con sus menús bajo
  Nómina › Venezuela.
- Pruebas de las siete hojas: filas de TIUNA, FAOV, INCES y CEPP, agregación del
  piso IMI por trabajador-mes, inclusión del recibo de vacaciones en TIUNA,
  atribución única de un recibo que cruza de mes, headcount y RNET, libro de
  horas extra, generación del XLSX y valores del AR-C.

**Alcance**: no se generan los TXT oficiales de los portales (Banavih/TIUNA).
Los portales cambian de formato sin aviso, así que se emite el soporte con los
montos exactos para transcribir; los TXT se añadirán cuando haya una planilla
real contra la cual validar el layout.

## [19.0.2.0.0]

Pasivos laborales. Versión anterior a la publicación del repositorio, sin fecha
de release registrada; se documenta a partir del script
`migrations/19.0.2.0.0/post-migration.py` —cuyo comentario la identifica como el
«upgrade v1→v2»— y de la sección «v2» del README.

### Añadido

- **Corrida mensual de provisiones** (`l10n.ve.payroll.provision` y sus líneas),
  restringida a un mes calendario exacto y sin solapes por compañía, incluso al
  reactivar una corrida cancelada. Devenga por mes las alícuotas de utilidades
  (2,5 días, art. 131), vacaciones (1,25 días, art. 190) y bono vacacional
  (1,25 días, art. 192) sobre el salario **normal** diario; la garantía de
  prestaciones de 15 días por trimestre de servicio —contado desde el
  aniversario de ingreso, no por trimestre natural— y los 2 días por año desde
  el segundo, sobre el salario **integral** diario (art. 142).
- **Intereses mensuales sobre prestaciones** (art. 143) con la tasa
  `l10n_ve_prestaciones_bcv_rate`, calculados sobre el saldo de garantía al
  **inicio** del mes y sin prorrateo intramensual. Solo se acumulan en el modo
  «contabilidad del patrono»: en fideicomiso los genera el fondo, así que la
  corrida no los devenga.
- Contabilización de la corrida en **un asiento borrador** por conceptos
  (Dr 6104xx / Cr 2106xx-2201xx) más la alimentación del libro de garantía.
  Cancelar elimina el asiento borrador y las líneas del libro que creó; si el
  asiento ya está publicado, exige reversarlo primero, y una corrida
  contabilizada no se puede eliminar.
- **Libro de garantía de prestaciones** (`l10n.ve.prestaciones.line`,
  arts. 142-144): garantía trimestral, días adicionales, intereses, anticipos y
  liquidación, con el saldo de garantía separado del de intereses porque estos
  se pagan aparte. Los anticipos deben ser negativos y no pueden exceder el
  **75 % del saldo** (art. 144); garantía y días adicionales no admiten montos
  negativos, pero los intereses sí, que es como se registra su pago anual o en
  el finiquito. Estado de cuenta imprimible desde la ficha del trabajador.
- Estructura **«Venezuela: Vacaciones»** (`VEVAC`) con los inputs de días de
  vacaciones y de bono vacacional, pagada sobre el **salario normal del mes
  anterior** al disfrute (art. 121, tomado del último recibo regular validado) y
  debitando las provisiones 210602 y 210603 en lugar de un gasto.
- Estructura **«Venezuela: Liquidación»** (`VELIQ`), con el neto a la cuenta
  210508 (Liquidaciones por Pagar) y sus inputs de finiquito.
- **Asistente de finiquito**, que aplica el art. 142.d de forma literal: el
  mayor entre la garantía depositada más el trimestre en curso y el retroactivo
  de 30 días por año —con la fracción **superior** a seis meses contada como año
  completo (art. 142.c)—, **más** los intereses, que se pagan además y no
  compiten en el máximo, más las fracciones de vacaciones, bono vacacional
  (arts. 190/192) y utilidades del ejercicio (art. 131). Crea el recibo `VELIQ`,
  cierra el contrato y el libro de garantía, y trae un guard que impide una
  segunda corrida cuando ya existe un recibo de liquidación vigente o un cierre
  de libro en el mismo período de empleo.
- **Utilidades sobre el promedio del salario normal del ejercicio** (art. 131),
  agrupando por mes los recibos regulares validados del año calendario; sin
  historial, cae al sueldo del contrato.
- **Cron mensual de provisiones, inactivo de fábrica**: solo crea el borrador
  del mes por compañía con chart `ve_bw`, nunca contabiliza. Lo activa el
  usuario cuando el flujo está validado.
- Reglas de registro multicompañía y ACL de los modelos nuevos (lectura para el
  usuario de nómina, escritura para el gerente).
- `migrations/19.0.2.0.0/post-migration.py`, que reejecuta el mapeo de cuentas
  del chart `ve_bw` sobre las reglas salariales tras cargar los XML nuevos de
  vacaciones y liquidación, porque el `post_init_hook` no corre en un `-u`.
- Pruebas de la corrida con y sin trimestre cumplido, intereses y modo
  fideicomiso, días adicionales del segundo año, las restricciones de período,
  el tope del anticipo, los montos del finiquito en sus dos ramas del art. 142.d,
  el borde de los seis meses, el cierre de libro con su contabilización y el
  guard de doble corrida.

### Cambiado

- El **pago de utilidades debita la provisión 210601** en vez del gasto 610403:
  el gasto ya se devengó mes a mes en la corrida. Si se pagan utilidades sin
  provisiones corridas, la cuenta queda temporalmente deudora hasta la corrida
  de diciembre.

---

Las versiones anteriores a la primera listada aquí no tienen registro detallado:
el módulo se desarrolló antes de adoptar este changelog. De la línea inicial
—«v1» en el README— no consta el número exacto de versión en ningún archivo
conservado; solo queda constancia indirecta en el comentario del script
`migrations/19.0.2.0.0/post-migration.py`, que la nombra como el punto de
partida del «upgrade v1→v2», y en la tabla «Qué cubre (v1)» del README:
estructuras de Nómina Regular y Utilidades, deducciones y aportes de IVSS, RPE,
FAOV e INCES, retención de ISLR según el porcentaje del AR-I (Decreto 1.808),
Contribución Especial de Protección de las Pensiones al 9 % con piso IMI, cesta
ticket indexado fuera del neto, los parámetros legales como `hr.rule.parameter`
versionados por fecha, el recibo bimonetario del art. 106 LOTTT y el
`post_init_hook` que mapea las cuentas del chart `ve_bw` por código.
