# Changelog — Venezuela · Plan de Cuentas BWEALTHICS (`l10n_ve_bw_chart`)

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.1.0] - 2026-07-31

### Añadido

- Cuenta `210510` «Contribución Especial de Pensiones por Pagar»
  (`liability_current`) y cuenta `610305` «Aporte Contribución Especial de
  Pensiones» (`expense`), para el aporte patronal del 9 % de la Ley de
  Protección de las Pensiones que liquida `l10n_ve_bw_payroll` (Forma 19 DPP).
  El plan pasa de 167 a 169 cuentas.

### Cambiado

- La cuenta `210501` «Sueldos y Salarios por Pagar» pasa a `reconcile = True`:
  `hr_payroll_account` exige una cuenta conciliable para poder registrar el
  pago del recibo desde la nómina.

## [19.0.1.0.0]

Versión inicial del módulo. No tuvo publicación propia: el primer commit del
repositorio publica ya la `19.0.1.1.0`, por lo que esta entrada no lleva fecha.

### Añadido

- Chart template `ve_bw` — «Plan 6 dígitos (VEN-NIF, BW)», `code_digits = "6"`,
  país fiscal `base.ve`. En Venezuela **no existe un plan de cuentas único
  obligatorio**: el marco contable son las VEN-NIF (BA VEN-NIF Nº 0, FCCPV), y
  la estructura 1 Activo / 2 Pasivo / 3 Patrimonio / 4 Ingresos / 5 Costos /
  6 Gastos se ofrece como convención difundida, no como imposición. Es una
  alternativa al `l10n_ve` oficial de Odoo, que usa 7 dígitos.
- 167 cuentas imputables de 6 dígitos (clases 1 a 6) en
  `data/template/account.account-ve_bw.csv`, incluidas las cuentas que consume
  el resto de la suite: `110301` IVA Crédito Fiscal, `210301` IVA Débito
  Fiscal, `110302` Retenciones de IVA Recibidas de Clientes, `210303`
  Retenciones de IVA por Enterar, `110303`/`210401` ISLR retenido y por
  enterar, `210304` IGTF Percibido por Enterar, `660101` Gasto por IGTF,
  `660102`/`210403` Impuesto Municipal (patente de industria y comercio) y el
  bloque laboral `2105xx` / `2106xx` / `2201xx` / `6101xx`–`6104xx`.
- 79 grupos `account.group` en tres niveles (prefijos de 1, 2 y 4 dígitos), en
  `data/template/account.group-ve_bw.csv`.
- 9 impuestos de IVA sobre 5 grupos (`account.tax.group` con `country_id`
  `base.ve`): ventas al 16 % general, 8 % reducida, 31 % (general + alícuota
  adicional), 0 % exportación y Exento; compras al 16 %, 8 %, 31 % y Exento.
  La repartición carga el impuesto de ventas a `210301` y el de compras a
  `110301`, en factura y en rectificativa.
- Valores por defecto de la compañía al cargar el template: cuenta por cobrar
  `110101`, por pagar `210101`, prefijos de banco `1014`, caja `1015` y
  transferencia `1013` (cuenta `101301`), cuenta transitoria de diarios
  `101201`, diferencia en cambio `430101`/`650104`, descuento por pronto pago
  `430104`/`650106`, diferencias de caja `430103`/`650105`, ingreso `410101`,
  gasto `510101`, cuenta por cobrar del POS `110102`, valoración de inventario
  `120101`, producción en proceso `120503`, e IVA 16 % como impuesto de venta
  y de compra por defecto.
- Enlaces de valoración de existencias sobre `120101`: variación de inventario
  `520102` y gasto `510101`.
- Campos de compañía `l10n_ve_is_spe` y `l10n_ve_spe_date` (designación de
  Sujeto Pasivo Especial notificada por el SENIAT), expuestos en un bloque
  «Localización Venezuela» de Contabilidad → Ajustes. Son la llave que
  encienden `l10n_ve_bw_wh_iva` (rol de agente de retención, PA
  SNAT/2025/000054) y `l10n_ve_bw_igtf` (percepción del 3 % como SPE, PA
  SNAT/2022/000013); la fecha importa, porque antes de ella no se percibe.
- Campo de contacto `l10n_ve_taxpayer_type` — Contribuyente Ordinario, Sujeto
  Pasivo Especial, Contribuyente Formal o No Sujeto — añadido tras
  `property_account_position_id` en la ficha contable del partner. Registra la
  calificación del contribuyente ante el SENIAT; lo consume
  `l10n_ve_bw_wh_iva` para decidir la retención de IVA.
- Cableado de los defaults *cross-module* en `_post_load_data`: el cargador del
  core solo resuelve las referencias de cuenta de `res.company` que puede
  dereferenciar durante la carga, así que los m2o que aportan `point_of_sale` y
  `stock_account` se asignan después por código y bajo `with_company` —
  llevan `check_company=True` y no persisten fuera del contexto de la compañía
  destino. En Odoo 19 `account.account.code` es *company-dependent*: la
  búsqueda por código se hace bajo la compañía destino o falla en silencio.
- Manifest con `countries: ["ve"]` y categoría
  `Accounting/Localizations/Account Charts`, requisito para que Odoo descubra
  el paquete de localización en Ajustes.
- Tests `post_install` (`tests/test_chart_load.py`): carga del template sobre
  una compañía VE nueva, 6 dígitos en todas las cuentas, ausencia de códigos
  duplicados, una única cuenta `equity_unaffected` (`330102`), cuentas por
  defecto de compañía y de partner, creación de los 9 impuestos con IVA 16 %
  por defecto, y enlaces de valoración de inventario (se omite si
  `stock_account` no está instalado).

---

Nota sobre las fuentes de este registro: el repositorio del módulo contiene un
único commit (`912be08`, 2026-07-31), que publica la `19.0.1.1.0` ya vigente.
La entrada `19.0.1.0.0` describe el contenido de la versión inicial, anterior a
las cuentas de la Contribución Especial de Pensiones.
