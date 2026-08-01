# Changelog — Venezuela · Impuesto Municipal (Patente de Industria y Comercio)

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.1.0] - 2026-07-31

Primera versión publicada en el repositorio. Módulo LGPL-3, dependiente de
`l10n_ve_bw_chart`, restringido al país `ve`.

### Añadido

- Configuración por compañía (`res.company`) de la patente de industria y
  comercio: municipio, alícuota sobre ingresos brutos, mínimo tributable fijo
  mensual, mínimo en **veces MMV**, **TCMMV** en bolívares, cuenta de gasto,
  cuenta por pagar y diario misceláneo. Alícuota y mínimo son configuración
  —no código— porque los fija la **ordenanza de cada municipio** al amparo de
  la **LOPPM**.
- Ayudas de campo con los topes legales de referencia: alícuota hasta **3 %**
  general y hasta **6,5 %** en las excepciones previstas; mínimo tributable de
  hasta **30 veces MMV** en el sector alimentos. El TCMMV es el Tipo de Cambio
  de la Moneda de Mayor Valor publicado por el **BCV** (normalmente el euro),
  de carga manual o por integración.
- Bloque «Localización Venezuela — Impuesto Municipal» en Ajustes ›
  Contabilidad (`res.config.settings`), con los ocho ajustes expuestos como
  campos `related` editables en un `setting` marcado `company_dependent`.
- Asistente mensual `l10n.ve.municipal.tax.wizard` con menú «Impuesto
  Municipal (VE)» en Contabilidad, y período por defecto en **mes vencido**
  (el mes ya cerrado al abrir el asistente).
- Base imponible: suma `haber − debe` de los apuntes **posteados** del período
  cuya cuenta es de tipo `income`. Quedan fuera los asientos en borrador y las
  cuentas `income_other`, de modo que los otros ingresos no engrosan los
  ingresos brutos gravables.
- Liquidación `max(base × alícuota, mínimo tributable)`, donde el mínimo es el
  **mayor** entre el fijo configurado y `veces MMV × TCMMV` convertido a la
  moneda de la compañía a la tasa de cierre del período. Un **mes sin ventas
  provisiona el mínimo**, no cero.
- Equivalente en bolívares del monto a pagar, calculado a la tasa de fin de
  mes y mostrado solo cuando existe una tasa VES real cargada.
- Generación del asiento borrador `Dr Gasto / Cr Impuesto Municipal por Pagar`
  en el diario misceláneo configurado, fechado el último día del período. Las
  cuentas son las que se configuren; la ayuda de campo sugiere las del catálogo
  VE (gasto `660102`, pasivo `210403`).
- Referencia de asiento estable `MUNI-AAAA-MM`, independiente de datos
  editables: el municipio y el período legible van en la narración y en la
  etiqueta de las líneas, no en la referencia.
- Guard de duplicados por prefijo de referencia: no se genera una segunda
  provisión del mismo período aunque después se renombre el municipio o se
  edite la fecha del asiento. Un asiento **cancelado** sí permite regenerar.
- Validaciones que abortan con `UserError` en lugar de producir un asiento
  incorrecto: alícuota sin configurar; año fuera del rango 2000–2100; mínimo
  en veces MMV sin TCMMV cargado; mínimo en veces MMV sin tasa VES real hasta
  el cierre del período; cuentas o diario sin configurar; e impuesto calculado
  en cero.
- Protección contra el fallback 1:1 de `res.currency`: sin una tasa VES
  distinta de 1.0 cargada hasta el cierre del período, el equivalente en Bs
  queda en cero y su campo se oculta, para no mostrar nunca un importe en
  moneda de la compañía rotulado como bolívares.
- Reglas de acceso (`ir.model.access.csv`) del asistente para
  `account.group_account_invoice` y `account.group_account_manager`.
- Menú colgado de `account.menu_finance` —y no de `account.menu_finance_entries`—
  porque en la serie 19.0 este último exige `group_account_readonly`, grupo que
  `group_account_invoice` no implica y que ocultaba el asistente justamente al
  grupo al que la ACL le da acceso.
- Soporte multicompañía: `check_company` en cuentas y diario, creación del
  asiento con `with_company` y selector de compañía visible solo en entornos
  multicompañía.
- Suite de 17 pruebas (`tests/test_municipal_tax.py`, `post_install`) sobre una
  compañía aislada en USD: cálculo de base y alícuota, exclusiones de la base,
  prelación entre mínimo fijo y mínimo MMV, mes sin ventas, conversión a Bs,
  errores de configuración, estabilidad de la referencia frente a renombrado y
  reedición, regeneración tras cancelar y visibilidad del menú para el grupo de
  la ACL.
