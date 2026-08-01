# Cómo contribuir

Este documento describe lo que el repositorio ya hace, no lo que nos gustaría que
hiciera: si una regla está aquí es porque el árbol la cumple hoy y se puede
verificar. El marco que fija el [README](README.md) no cambia por contribuir:
esto es una herramienta de apoyo, **no está certificada ni avalada por el
SENIAT**, no es asesoría fiscal y se publica tal cual, sin compromiso de tiempo
de respuesta. Aceptar un PR no valida el criterio fiscal de nadie.

## 1. Qué encaja aquí

- **Lo más valioso: avisar de un cambio normativo**, con la plantilla
  [reporte de cambio normativo](.github/ISSUE_TEMPLATE/cambio-normativo.yml).
  Pide norma, Gaceta Oficial, vigencia, módulos afectados y fuente oficial: es lo
  que permite actuar sin investigar de cero. Vale tanto como un PR y no exige
  escribir código.
- Errores reproducibles sobre una base limpia, con traceback recortado.
- Tests que fijen un número o un byte que hoy no está cubierto.
- Correcciones de [docs/BASAMENTO-LEGAL.md](docs/BASAMENTO-LEGAL.md) y del
  [manual](docs/MANUAL-LOCALIZACION-VE.md).
- Adaptadores nuevos (imprenta digital, otra máquina fiscal) con proveedor
  simulado y sin red en los tests.

No se pide firmar ningún CLA ni ceder copyright (§10).

## 2. Qué puedes probar y qué no

| Módulo | Requisito para instalarlo y probarlo |
|---|---|
| `chart`, `igtf`, `wh_iva`, `wh_islr`, `municipal` | Odoo 19 Community |
| `fiscal_books` | Community + `xlsxwriter`. Arrastra `point_of_sale` |
| `invoice_format` | Community (vía `fiscal_books`) |
| `einvoice` | Community. Solo trae proveedor **simulado** (`l10n.ve.edoc.provider.dummy`); no hay adaptador de una imprenta real |
| `fiscal_printer` | Community + `pos_restaurant`. Sus tests de servidor corren, pero el circuito completo necesita máquina fiscal HKA y el bridge local de la caja: **no es reproducible sin hardware** |
| `compliance` | `OCA/server-tools` rama 19.0 en el `addons_path` (`auditlog`). **No tiene `tests/`**: `--test-tags /l10n_ve_bw_compliance` no ejecuta nada |
| `payroll` | **Odoo 19 Enterprise** (`hr_payroll_account`) + `xlsxwriter`. No instala sobre Community |

Si no puedes probar un módulo, **dilo en el PR**. Se acepta un PR con la
limitación declarada; no uno que la oculta.

## 3. Montar el entorno

Odoo 19 desde fuente, PostgreSQL y:

```bash
pip install xlsxwriter   # obligatorio: sin él fiscal_books y payroll no instalan
pip install openpyxl     # solo tests: sin él, las aserciones sobre el XLSX se SALTAN
```

Basta con clonar este repositorio dentro del `addons_path`; no hay instalación
por pip. Añade el directorio de Enterprise solo si vas a tocar `payroll`.

```ini
[options]
addons_path = /ruta/odoo/addons,/ruta/l10n-venezuela-bw,/ruta/OCA/server-tools
```

## 4. Correr los tests

Sobre una base **desechable**, nunca contra producción ni contra una base con
datos de un contribuyente. Las 13 clases de test llevan
`@tagged("post_install", "-at_install")` y corren en el proceso que hace el `-i`:
por eso `--workers=0` y `--stop-after-init` no son cosméticos. `pytest` a secas
no sirve.

```bash
createdb ve_test
odoo-bin -c odoo.conf -d ve_test --without-demo=all \
  -i l10n_ve_bw_chart,l10n_ve_bw_igtf,l10n_ve_bw_wh_iva,l10n_ve_bw_wh_islr,l10n_ve_bw_municipal,l10n_ve_bw_fiscal_books,l10n_ve_bw_invoice_format,l10n_ve_bw_einvoice,l10n_ve_bw_fiscal_printer \
  --test-enable \
  --test-tags /l10n_ve_bw_chart,/l10n_ve_bw_igtf,/l10n_ve_bw_wh_iva,/l10n_ve_bw_wh_islr,/l10n_ve_bw_municipal,/l10n_ve_bw_fiscal_books,/l10n_ve_bw_invoice_format,/l10n_ve_bw_einvoice,/l10n_ve_bw_fiscal_printer \
  --stop-after-init --workers=0
```

Un módulo suelto, y un solo test (la sintaxis es
`[-][etiqueta][/módulo][:Clase][.método]`):

```bash
odoo-bin -c odoo.conf -d ve_test -i l10n_ve_bw_igtf --test-enable \
  --test-tags /l10n_ve_bw_igtf --stop-after-init --workers=0

odoo-bin -c odoo.conf -d ve_test -u l10n_ve_bw_igtf --test-enable \
  --test-tags /l10n_ve_bw_igtf:TestIgtf.test_outbound_igtf_posts_expense_move \
  --stop-after-init --workers=0
```

**Correr módulo por módulo miente por omisión**: seis `skipTest` condicionales se
saltan en silencio cuando falta la otra pieza (`stock_account`,
`account_debit_note`, `wh_iva` —dos veces—, `wh_islr`, `fiscal_printer`), y sin
`openpyxl` las aserciones sobre el contenido del XLSX ni siquiera llegan a
correrse; la corrida aislada dice «0 failed» sin haber probado la integración.
La corrida que vale para un PR es la de la suite completa en una sola base, con
`openpyxl` instalado. Pega la línea final del tipo `0 failed, 0 error(s)`. Al
terminar, `dropdb ve_test`: la base de tests se tira y se rehace, nunca se
reutiliza.

## 5. Reglas de un PR

1. Una rama por cambio, commits atómicos, un módulo por commit. Título con el
   prefijo del módulo (`l10n_ve_bw_wh_iva: …`); cuerpo en español.
2. Cabecera de licencia en cada archivo nuevo (§8).
3. **Sube la versión del manifest y añade la entrada del `CHANGELOG.md` del
   módulo en el mismo PR.** PATCH corrección, MINOR comportamiento nuevo
   compatible, MAJOR cambio de modelo de datos — y en ese caso además
   `migrations/<versión>/post-migration.py` (precedentes:
   `l10n_ve_bw_fiscal_books/migrations/19.0.1.1.0/`,
   `l10n_ve_bw_payroll/migrations/19.0.2.0.0/`). Invariante que se revisa de un
   vistazo, hoy cierto en los 11 módulos: la versión del manifest es idéntica a
   la primera entrada del CHANGELOG (Keep a Changelog en español: *Añadido*,
   *Cambiado*, *Corregido*). Nunca reescribas una entrada ya publicada.
4. Test que fije el número o el byte si hay cambio de comportamiento fiscal (§6).
5. Nada de reformateos ni renombres mezclados con un cambio de comportamiento: un
   PR de estilo va aparte.

La descripción responde siempre: qué cambia, qué norma lo obliga, módulos
tocados, versión nueva, entrada de CHANGELOG, salida literal de los tests y —si
toca UI o PDF— captura con datos ficticios.

## 6. Cambios normativos

Aquí la unidad de cambio no es la «feature» sino la **norma**. Es *cambio de
comportamiento fiscal*, y exige test, cualquier cosa de esta lista: alícuotas y
porcentajes de retención; bases imponibles y su clasificación en los libros;
topes, mínimos y unidades de referencia (UT, MMV, salario mínimo); redondeos y
conversión a bolívares; correlativos y formato de comprobante (AAAAMM+8, Nº de
control); bytes de los archivos de declaración (TXT 99035, XML de ISLR, XLSX de
los libros); requisitos de forma del PDF; cuentas donde se asienta; parámetros de
nómina. En una frase: **si cambia un número que el contribuyente declara o un
byte de un archivo que ingiere el SENIAT, el PR trae test.**

- **Sin fuente no se mezcla**: instrumento + artículo + número y fecha de Gaceta
  Oficial + fecha de vigencia. La Gaceta manda; los resúmenes de firmas
  profesionales, las notas de prensa y las capturas de mensajería sirven de
  apoyo, nunca de fundamento. Un porcentaje no se cambia «porque sí».
- **Los valores con vigencia se AÑADEN fechados, no se editan en sitio.** Sigue
  los patrones existentes: `l10n_ve_bw_wh_islr/data/ut_data.xml` (registro
  `ut_2025_06_02`, con `date_from` y el campo `gaceta`) y
  `l10n_ve_bw_payroll/data/hr_rule_parameter_data.xml` (`rule_parameter_imi_2026`).
  El porqué es doble: esos bloques son `noupdate="1"`, así que editar el valor
  **no llega a las bases ya instaladas**, y reimprimir un libro o recalcular una
  nómina de un período cerrado tiene que dar el mismo resultado. Editar en sitio
  consigue lo peor de los dos mundos.
- Corregir un valor mal cargado sí exige script en
  `migrations/<versión>/post-migration.py` y subida de versión. Para datos sin
  vigencia (tarifas de `l10n.ve.islr.concept`), el PR dice explícitamente qué
  pasa con los comprobantes ya emitidos.
- **El test cubre los dos lados de la fecha de vigencia** cuando la hay.
  Plantillas: `test_agent_spe_date_in_future_no_withholding` en
  `l10n_ve_bw_wh_iva/tests/test_wh_iva.py` y `test_ut_value_selection` en
  `l10n_ve_bw_wh_islr/tests/test_islr.py`.
- Si la norma no está en [docs/BASAMENTO-LEGAL.md](docs/BASAMENTO-LEGAL.md), el
  PR añade su fila (norma → contenido usado → efecto en el código). La
  trazabilidad norma → código es el activo del proyecto.

## 7. Nada real entra al repo

Regla número uno: un «dato de prueba» aquí puede ser el RIF, el monto y el nombre
de un contribuyente real. RIF ficticios canónicos, los que ya usan los tests (no
inventes otra convención): compañía `J-12345678-9`; contraparte jurídica
`J-98765432-1`; persona natural `V-98765432-1` y `V-11222333-4`; terceros
`J-11122233-4`, `J-44555666-7`, `J-55566677-8`; placeholder de plantilla
`J-00000000-0`; sin guiones, para el formato del portal, `J123456789` y
`V987654321`. La validación del código es de **patrón** (letra V/E/J/P/G + 9
dígitos), no de dígito verificador: un RIF secuencial pasa igual, así que nunca
hace falta uno de aspecto real. Nombres de fixture: fantasía + «Prueba»/«Demo» +
C.A./S.A.; correos en `example.com`.

**Adjuntos prohibidos** en issues y PRs: Libro de Compras o de Ventas real en
XLSX, TXT de la forma 99035, XML mensual de ISLR, comprobantes de retención,
recibos de pago y ARC, reporte Z de máquina fiscal, y registros de la bitácora
`l10n.ve.edoc.log` (sus campos `request`/`response` traen la factura íntegra
enviada a la imprenta). En su lugar: reproduce sobre una base nueva con datos
ficticios y adjunta *ese* archivo, o pega solo la estructura con los importes en
cero.

**Credenciales e infraestructura**: nada de URL de la instancia, IP, nombre de la
base, token ni nombre de cliente. Ojo con las capturas de Ajustes de Contabilidad
(URL y clave del proveedor de imprenta) y de Ajustes del POS (URL y token del
bridge). Si ya se filtró, lo único que sirve es **rotar la credencial**: editar un
comentario en GitHub deja historial y el correo de notificación ya salió.

**Logs y capturas**: traceback recortado, no el log completo (con
`--log-level=debug` Odoo imprime SQL con valores); sustituye nombres de compañía
y de partner; recorta la barra de direcciones y el selector de compañía. Antes de
abrir el PR, revisa una a una las líneas que devuelva:

```bash
git diff | grep -nEi '[VEJPG]-?[0-9]{8}|https?://|token|password|apikey|@[a-z0-9.-]+\.[a-z]{2,}'
```

## 8. Estilo del código

**No hay linter ni formateador en este repositorio.** No existen
`.pre-commit-config.yaml`, `pyproject.toml`, `setup.cfg`, `.flake8`, `.pylintrc`,
`ruff.toml`, `.isort.cfg`, `.editorconfig` ni `tox.ini`, ni workflows de CI. El
estilo es convención humana y no está verificado por herramienta; es un pendiente
conocido (sería requisito para la OCA, §12). Por eso: **mantén el estilo del
archivo que tocas** y no envíes reformateos.

Estilo de facto, medido sobre las ~10.400 líneas Python del árbol: línea de
~79-80 caracteres (p95 = 79, p99 = 88, máximo 108) — **no es Black**, hay 97
líneas por encima de 88, así que no apliques `black` ni `ruff-format`; comilla
doble casi absoluta (solo 3 literales con comilla simple en todo el árbol);
`%`-format y no f-strings (apenas 11 f-strings, cero `.format()`), obligatorio el
`%`-perezoso en logs (`_logger.info("...%s...", var)`); cero type hints; imports
en tres bloques separados por línea en blanco (stdlib, terceros, odoo), y
dentro de odoo `from odoo import Command, _, api, fields, models`, luego
`from odoo.exceptions` y luego `from odoo.addons.<x>`. Traducción estilo Odoo
17+ con argumentos perezosos, nunca interpolando antes:
`_("El año %s no es válido.", self.year)` o
`_("...%(journal)s...", journal=...)`. Los atributos `string=` y `help=` de los
campos van en español literal **sin** `_()` — Odoo ya los traduce; hay 0
apariciones de `string=_(` en toda la suite.

**Cabecera**, con la forma real por tipo de archivo:

```python
# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_igtf. License LGPL-3.
```

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- Copyright 2026 BWEALTHICS LLC -->
```

En `.js`, `// Copyright 2026 BWEALTHICS LLC`. Los `.xml` y los `.js` llevan hoy
solo la línea de copyright. En `l10n_ve_bw_compliance` la licencia es AGPL-3. Los
`.csv` de ACL van **sin cabecera a propósito**: rompería el parser de
`ir.model.access`. Lo más seguro es copiar la cabecera del archivo vecino.

**Nombres**, en tres niveles: campo añadido a un modelo del núcleo
(`account.move`, `res.company`, `pos.config`…) lleva prefijo `l10n_ve_` siempre
(`l10n_ve_control_number`); campo de un modelo propio va **sin** prefijo
(`l10n.ve.iva.wh.voucher` declara `number`, `base_amount`, `state`); modelo propio
`l10n.ve.<algo>` sin marca de empresa, con clase `L10nVe...`, y las herencias del
núcleo con el CamelCase del modelo heredado. Helpers privados `_l10n_ve_*`. XML
IDs `<modelo>_view_<tipo>` para los propios y
`view_<core>_form_l10n_ve_<tema>` para los heredados.

**Anatomía del módulo**: `models/` un archivo por modelo con el nombre del modelo;
`wizards/` con el `.py` y su `_views.xml` juntos; `views/` con sufijo `_views.xml`;
`data/`; `security/` solo si el módulo declara modelos propios (6 de 11: einvoice,
fiscal_books, municipal, payroll, wh_islr, wh_iva); `tests/`;
`migrations/19.0.X.Y.Z/post-migration.py`; `hooks.py` en la raíz del módulo;
`static/` solo en fiscal_printer.

**Cómo se comenta — la marca de la casa.** Cerca del 10 % de las líneas Python
son comentarios, y es intencional. No describen lo que hace el código: justifican
el **porqué**, citando (a) el artículo de ley, (b) el comportamiento no obvio del
núcleo de Odoo, con archivo y línea cuando aplica, o (c) lo que se dejó fuera a
propósito. Tres ejemplos del árbol:

- `l10n_ve_bw_igtf/models/account_payment.py`: «El cliente web REENVÍA el valor
  computado al guardar (echo-back del onchange), así que "el campo vino en vals"
  no basta para detectar una edición».
- `l10n_ve_bw_compliance/hooks.py`: «Se deja FUERA `account.move.line` a
  propósito: es el modelo de mayor volumen con diferencia […] y sus importes ya
  están protegidos por la cadena de hash del diario».
- `l10n_ve_bw_payroll/hooks.py`: «ver `l10n_be_hr_payroll_account`: "this is a
  credit, but the amount is negative"».

Si tu cambio necesita esa clase de explicación, escríbela: aquí un comentario de
más es barato y uno de menos se paga en la próxima fiscalización.

**Tests**: hereda la base mínima que sirva — `AccountTestInvoicingCommon` cuando
hace falta el andamiaje contable, `TransactionCase` cuando no (chart,
fiscal_printer, municipal), `PayslipVeCommon` en payroll—, pon
`@tagged("post_install", "-at_install")`, y usa fechas fijas, RIF ficticios, tasa
creada en `setUpClass` y cero red. Para integraciones opcionales, `skipTest` con
mensaje en español en cualquiera de las tres variantes ya usadas: por campo
(`if "debit_origin_id" not in self.env["account.move"]._fields`), por modelo
(`if "l10n.ve.islr.concept" not in self.env`) o por modelo + interfaz
(`self.env.get(...)` más `hasattr`). Para librerías Python, `try/except
ImportError` a nivel de módulo, como hace `fiscal_books` con `openpyxl`.

**Divergencias que existen hoy** (no las repliques, pero tampoco te sorprendas):
la carpeta de informes se llama `report/` en invoice_format y wh_iva y `reports/`
en payroll y wh_islr; el sufijo `_data` en los XML de datos es intermitente
(`ir_sequence.xml` frente a `ir_sequence_data.xml`); 31 archivos de chart,
municipal y wh_iva llevan la cabecera genérica `# Part of l10n_ve_bw.`; y los
comentarios mezclan español e inglés dentro de un mismo archivo. El español es el
idioma del proyecto —código, comentarios, CHANGELOG y PRs— y no se aceptan
traducciones al inglés del código existente.

## 9. Qué no se va a mergear

- Alícuotas de un municipio concreto cargadas como dato: la patente es
  configuración por compañía (`l10n_ve_municipal_rate`,
  `l10n_ve_municipal_minimum_mmv`), no dato del módulo. Igual el 3 % del IGTF, que
  es un `default` configurable.
- Adaptadores de imprenta digital con endpoint o credenciales en el código,
  activados por defecto, o que solo se puedan probar teniendo contrato con esa
  imprenta.
- Renombrados de campos o de XML IDs sin migración; reformateos masivos;
  traducciones al inglés; dependencias Python nuevas sin justificar (hoy la única
  es `xlsxwriter`); cambios de comportamiento fiscal sin test.
- Cualquier texto —título de PR, CHANGELOG, interfaz, README— que diga
  «certificado», «homologado», «avalado por el SENIAT» o «cumple con». La
  formulación aceptable es «implementa lo que establece el art. N de <norma>,
  según la lectura citada». Tampoco logos ni sellos que sugieran afiliación
  oficial.

## 10. Licencias y titularidad

Diez módulos son **LGPL-3** ([LICENSE](LICENSE)) y `l10n_ve_bw_compliance` es
**AGPL-3** ([LICENSE.AGPL-3](LICENSE.AGPL-3)) porque depende de OCA `auditlog`. Al
enviar un PR aceptas que tu aporte se publique bajo la licencia del módulo que
tocas; conservas tu copyright y puedes añadir tu línea bajo la de BWEALTHICS.

- **El contagio va en un solo sentido**: que el módulo AGPL consuma los módulos
  LGPL es el diseño actual y es correcto. Lo prohibido es lo contrario — copiar
  código de `compliance` o de `auditlog` hacia un módulo LGPL, o añadir
  cualquiera de los dos a su `depends`. Eso lo vuelve AGPL de hecho y rompe la
  promesa de que el resto de la suite puede combinarse con addons propietarios.
- **Enterprise**: `payroll` *depende* de `hr_payroll_account`. Heredar sus
  modelos y llamar a su API es legítimo (el usuario tiene su licencia); copiar su
  fuente o sus reglas salariales —o las de cualquier `l10n_XX_hr_payroll` de
  Enterprise— al repositorio no lo es, y basta un fragmento para contaminarlo.
  Tampoco pegues código de Enterprise dentro de un issue.
- Al abrir el PR declaras: *este aporte es de mi autoría o tengo derecho a
  enviarlo bajo la licencia del módulo; no contiene código de Odoo Enterprise ni
  de ningún módulo propietario o bajo NDA; no contiene código copiado de un
  proyecto con licencia incompatible*. Se admite código asistido por IA si lo
  revisaste y respondes por su origen y por sus números.

## 11. Alcance y expectativas

No hay CI todavía: la salida de los tests pegada en el PR es la única evidencia
disponible y su ausencia es motivo suficiente para no revisar. No hay plazo de
respuesta. El mantenedor puede pedir dividir el PR o corregir la forma —versión,
CHANGELOG, cabecera— antes de mirar el fondo, y los issues sin fuente o con datos
reales se editan o se cierran.

Un fallo que permita alterar un libro fiscal, saltarse la numeración de control o
desactivar el audit log **no se abre como issue público**: repórtalo en privado
por GitHub Security Advisory, sin datos reales adjuntos.

## 12. Nota sobre portar módulos a la OCA

Ruta con requisitos y coste, no plan inminente: el desarrollo sigue ocurriendo
aquí y contribuir aquí **no exige firmar ningún CLA**. Candidatos: `chart`,
`igtf`, `wh_iva`, `wh_islr`, `municipal`, `fiscal_books`, `invoice_format`. No
candidatos: `payroll` (depende de Enterprise, que la OCA no acepta),
`fiscal_printer` (hardware y protocolo de un proveedor comercial), `einvoice`
mientras solo tenga proveedor simulado, y `compliance` (paraguas AGPL atado a
`auditlog`).

El port cuesta: renombrar `l10n_ve_bw_x` → `l10n_ve_x` (la OCA desaconseja la
marca de empresa); traducir al inglés cadenas, comentarios y docstrings —hoy todo
está en español y no hay `i18n/`— y añadir el `es.po`; convertir README y
CHANGELOG en fragmentos `readme/` que genera `oca-gen-addon-readme`; añadir
`, Odoo Community Association (OCA)` al autor; pasar el pre-commit de la rama
(`ruff`, `pylint-odoo`, `prettier`); y firmar el CLA (ICLA individual más ECLA de
la empresa). Conviene abrir antes un issue de intención: la rama 19.0 de
`OCA/l10n-venezuela` no tenía **ningún addon** la última vez que se revisó
—compruébalo—, así que portar sería estrenarla.

Qué puedes hacer hoy para que ese port siga siendo barato: fronteras de módulo
limpias e integraciones opcionales por `hasattr`/`skipTest`, como ya hace
`fiscal_books` con `wh_iva`; nada de marca de empresa en modelos ni campos; tests
dentro del módulo; una entrada de CHANGELOG por cambio (se convierte
mecánicamente en `readme/HISTORY.md`); e indica tu nombre y tu usuario de GitHub
en el PR, que es la lista de autores que la OCA pedirá.
