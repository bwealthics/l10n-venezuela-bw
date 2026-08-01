# Venezuela — Nómina (BWEALTHICS) · `l10n_ve_bw_payroll`

Séptimo módulo de la suite `l10n_ve_bw_*` (Odoo 19 Enterprise). Nómina
venezolana completa sobre `hr_payroll_account`.

**Fuente normativa** (tasas, bases, topes, gacetas, fuentes verificadas):
`Odoo/Localización VE/Nomina-VE-Requerimientos-2026.md` en la bóveda.

## Qué cubre (v1)

| Concepto | Regla | Base | Nota |
|---|---|---|---|
| IVSS 4% / 9-11% | `VE_IVSS_EMP/PAT` | cotizable, tope 5 SM, **lunes del período** | clase de riesgo en Ajustes |
| RPE 0,5% / 2% | `VE_RPE_EMP/PAT` | cotizable, tope 10 SM | ver ponytail: base del período, no mes anterior |
| FAOV 1% / 2% | `VE_FAOV_EMP/PAT` | **integral** (normal + alícuotas), sin tope | días de utilidades en Ajustes |
| INCES 2% / ½% | `VE_INCES_PAT` / `VE_INCES_UTIL` | normal sin HE / utilidades pagadas | devengo mensual, pago trimestral SIGAT |
| ISLR | `VE_ISLR` | gravable × % AR-I | % en la ficha del empleado (hr.version, versionado por fecha) |
| CEPP 9% | `VE_CEPP_PAT` | **todo pago** + cesta, piso IMI USD | Forma 19 DPP |
| Cesta ticket | `VE_CESTA` | USD 40/mes indexado | fuera del NET, categoría propia |
| HE/bono nocturno/feriados/comisiones/bonos/embargos | inputs | — | `Otras entradas` del payslip |
| Utilidades | estructura `VEUTIL` | días compañía o input `UTIL_D` | v1 debita gasto 610403; v2 debitará la provisión |

- **Bimoneda**: todo se calcula y contabiliza en la moneda de la compañía
  (USD); `l10n_ve_bcv_rate` (tasa BCV a la fecha de pago, congelada en el
  recibo) convierte los montos legales en Bs y alimenta el contravalor del
  recibo art. 106. Sin tasa cargada → `UserError`, nunca 1:1.
- **Parámetros legales** = `hr.rule.parameter(.value)` versionados por fecha
  (Nómina > Configuración > Parámetros de reglas). Ninguna tasa vive en el
  código. Los cambios normativos los aplica un humano: por diseño, ningún
  proceso automático escribe parámetros legales.
- **Cuentas**: mapeadas por código del chart `ve_bw` en el `post_init_hook`.
  Para una compañía VE creada después de instalar:
  `from odoo.addons.l10n_ve_bw_payroll.hooks import map_rule_accounts;
  map_rule_accounts(env, company)`.

## Decisiones (ponytail)

- **`hr.version.wage` es el monto POR PERÍODO de pago** (semántica del motor
  Odoo 19: los worked days reparten el wage íntegro en cada recibo y el costo
  anual usa 24 pagos semi-monthly). Empleado quincenal de $500/mes → cargar
  **wage = 250**. Los helpers mensualizan con `_ve_monthly_wage()`.
- Sueldo **solo en moneda de compañía (USD)** — el usuario eligió USD como
  moneda de cuenta; agregar `wage_mode` VES cuando exista un contrato pactado
  en Bs.
- RPE sobre la base del período (no "mes anterior"): con tope Bs 1.300 la
  diferencia es < Bs 7 y solo en meses de aumento.
- INCES: gate por compañía `l10n_ve_inces_contributor` (5+ trabajadores,
  art. 49 Decreto-Ley 2014); con menos, desmarcar y declarar en cero.
- CEPP: el piso IMI se aplica por recibo prorrateado; en un mes con nómina
  regular bajo el piso Y pago de utilidades se sobre-declara (dirección
  conservadora). La agregación exacta por trabajador-mes llega con la Forma
  19 DPP (v3).
- Frecuencias soportadas: mensual y quincenal — cualquier otra lanza
  UserError (nada de defaults silenciosos).
- La cuenta 210501 se marca conciliable en el hook (exigencia de
  hr_payroll_account para registrar pagos desde el payslip).
- **Configurar el diario de nómina** (en la estructura salarial) **con cuenta
  por defecto** (p. ej. 430105 Ganancia por Redondeo): el core ajusta ahí los
  centavos de redondeo por línea del asiento.
- Motor OCA (`payroll` community): **camino soportado, no implementado** —
  OCA 19.0 aún no porta `payroll_account`. Toda la lógica VE está en helpers
  engine-neutral de `hr_payslip` (las reglas son one-liners), así que un
  adapter futuro solo duplica el XML de reglas.
- Jornada 8 h para la hora extra; leer del calendario si un cliente pacta
  jornadas menores.

## v2 — Pasivos laborales (Nómina > Venezuela)

- **Provisiones LOTTT** (`l10n.ve.payroll.provision`): corrida por mes
  calendario exacto (constraint anti-solape por compañía) — utilidades 2,5 d
  + vacaciones 1,25 d + bono vacacional 1,25 d sobre salario **normal**
  diario; garantía **15 d en el trimestre de servicio** (aniversario del
  ingreso) + **2 d/año desde el 2° año** sobre **integral** diario (salario
  cotizable + alícuotas sobre normal); intereses mensuales (tasa
  `l10n_ve_prestaciones_bcv_rate`, actualizar cada mes del aviso BCV) sobre
  el saldo de garantía **al inicio del mes** (sin prorrateo intra-mes).
  Postear crea UN asiento borrador (Dr 6104xx / Cr 2106xx-2201xx) y alimenta
  el libro. Cron mensual INACTIVO (solo crea borradores).
- **Libro de garantía** (`l10n.ve.prestaciones.line`, art. 142-144): abonos,
  adicionales, intereses (negativos = pago), anticipos (constraint 75%) y
  liquidación. Estado de cuenta imprimible desde la ficha del empleado.
  **Saldos iniciales** (historia pre-Odoo): cargarlos como líneas `garantia`
  manuales antes de la primera corrida.
- **Bases legales**: vacaciones/bono pagan sobre el salario **normal del mes
  anterior** al disfrute (art. 121, último recibo validado); utilidades sobre
  el **promedio del ejercicio** (art. 131); sin historial de recibos, todo
  cae al sueldo del contrato. El residual de las provisiones 2106xx vs el
  pago real se reclasifica al cierre del ejercicio contra 6104xx.
- **Estructura Vacaciones** (inputs VAC_D/BVAC_D, pago antes del disfrute,
  debita provisiones 210602/210603). ⚠️ Registrar la ausencia en el período
  regular para no duplicar sueldo.
- **Finiquito** (wizard): art. 142.d literal — MAX(garantía depositada +
  **trimestre en curso** [nace al iniciarlo, art. 142.a → gasto directo],
  retroactivo 30 d/año con fracción **superior** a 6 meses) + **intereses
  aparte** + fracciones de vacaciones/bono/utilidades. Crea el recibo VELIQ
  (neto a **210508**), cierra contrato y libro **al crear el recibo** (si se
  descarta el borrador, borrar a mano las líneas de cierre — hay guard
  anti-doble-corrida que lo recuerda). Prestaciones e intereses exentos de
  ISLR y fuera de CEPP; fracciones gravables (ISLR + CEPP 9% + INCES ½%).
- El pago de utilidades **debita la provisión 210601** (el gasto se devenga
  mensualmente). Si pagas utilidades sin provisiones corridas, la cuenta
  queda temporalmente deudora hasta la corrida de diciembre.
- ⚙️ Upgrade v1→v2: `migrations/19.0.2.0.0/post-migration.py` re-mapea las
  cuentas (post_init_hook NO corre en -u). Regla del módulo: todo cambio de
  RULE_ACCOUNTS = bump de versión + script de migración.

## v3 — Declaraciones institucionales (Nómina > Venezuela)

- **Declaraciones VE (soportes)**: un XLSX multi-hoja por período, calculado
  desde los recibos validados (Bs a la tasa BCV congelada de cada recibo):
  IVSS-TIUNA (semanal topado + lunes), FAOV (integral, 1%+2%), INCES
  (2% mensual + ½% utilidades), **CEPP Forma 19 DPP** (agregación exacta por
  trabajador-mes de PAGO con piso IMI una sola vez y columna de diferencia
  vs lo devengado por recibo), headcount trimestral, RNET (altas/bajas) y
  libro de horas extra (alerta > 100 h/año; el límite semanal de 10 h se
  controla al capturar, no es derivable de inputs mensuales).
- **AR-C anual** (PDF por trabajador, Decreto 1.808 art. 24): remuneraciones
  gravables e ISLR retenido por mes, en Bs y USD — entregar antes del 31-ene.
- ponytail: los portales cambian formato sin aviso — se generan soportes con
  montos exactos para transcribir; los TXT oficiales (Banavih/TIUNA) se
  agregarán cuando haya una planilla real del cliente para validar layout.

## Automatización de la carga de tasas

Las tasas y topes legales se cargan como `hr.rule.parameter.value` versionados
por fecha. La automatización de su carga (scraping del BCV, alertas de cambio
normativo) queda **fuera del alcance de este módulo**: se resuelve con la
herramienta de orquestación que cada implantación prefiera. El criterio de
diseño es que ningún proceso automático escriba parámetros legales — siempre
hay un humano en el loop.

## Tests

`--test-enable -i l10n_ve_bw_payroll` — escenario de referencia: sueldo
500 USD, tasa 100 Bs/USD, julio 2026 (ver `tests/test_payslip_ve.py`).
