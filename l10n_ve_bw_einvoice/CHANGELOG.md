# Changelog — Venezuela · Conector de Imprenta Digital

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.2.0.0] - 2026-08-30

Adaptador real de **The Factory HKA** y cierre de las brechas detectadas al
validar el módulo contra la documentación pública del proveedor
(https://wiki.thefactoryhka.com.ve/doku.php?id=manual_de_integracion_venezuela).

### Añadido

- Proveedor `l10n.ve.edoc.provider.hka` («The Factory HKA»), escrito contra el
  wiki del proveedor: `POST /api/Autenticacion` (token Bearer con vigencia de
  12 h, cacheado por compañía en `ir.config_parameter` y renovado con margen
  de 10 min o tras un 401), `POST /api/Emision` (Nº de control síncrono en
  `resultado.numeroControl`) y `POST /api/Anular`. Montos como strings y
  fechas `dd/mm/yyyy`, como en los ejemplos del wiki; poda recursiva de campos
  vacíos antes de enviar. ⚠️ Los códigos de tipo de documento (01/02/03), de
  impuesto (G/R/A/E) y el valor de `tipoDeVenta` quedan por confirmar contra
  el catálogo que HKA entrega con las credenciales.
- En pruebas (`l10n_ve_edoc_test`) el adaptador usa SIEMPRE la URL demo
  documentada (`demoemisionv2.thefactoryhka.com.ve`); la URL configurada solo
  aplica en producción y es obligatoria al desmarcar el ambiente de pruebas.
- Dict neutro enriquecido con lo que la imprenta exige y el adaptador no puede
  inventar: `hora` de emisión (zona horaria del usuario), `tipo_venta`
  (contado/crédito según vencimiento), comprador con `tipo_identificacion` y
  `numero_identificacion` partidos del RIF, `telefono`, líneas con `codigo`
  (PLU), `unidad`, `descuento_monto`, `iva` y `total`, totales con `subtotal`
  y `nro_items`, `formas_pago` desde los cobros conciliados, y
  `tipo_cambio`/`totales_bs` (equivalente en la moneda de referencia de
  `l10n_ve_bw_invoice_format`, art. 25 LIVA) cuando el documento no está en
  bolívares. La NC/ND añade `comentario` (motivo) al documento afectado.
- Anulación cableada de punta a punta: botón «Anular ante la imprenta»
  (visible en estados enviado/asignado), wizard `l10n.ve.edoc.cancel.wizard`
  que exige el motivo, `_l10n_ve_edoc_do_cancel()` con la misma filosofía del
  envío (el fallo queda en bitácora y en el campo de error, nunca revienta la
  transacción) y paso al estado «Anulado ante la imprenta», hasta ahora
  inalcanzable.
- Campo `l10n_ve_edoc_sucursal`: serie y sucursal por separado, como los trata
  el proveedor en `identificacionDocumento`.
- Pruebas nuevas: dict enriquecido, guardas y flujo del wizard de anulación
  (éxito y fallo), resolución de URL demo/producción y traducción del payload
  HKA (factura y nota de crédito) sin red.

### Cambiado

- Ayudas de configuración: la URL se rotula «URL (producción)» y el ambiente
  de pruebas documenta que fuerza la URL demo del proveedor.
- `external_dependencies`: se declara `requests`.

## [19.0.1.1.0] - 2026-08-01

Primera versión publicada del módulo (commit `2eb7131`).

### Añadido

- Modelo abstracto `l10n.ve.edoc.provider`: contrato con la imprenta digital
  autorizada reducido a cuatro métodos — `_edoc_send`, `_edoc_fetch`,
  `_edoc_cancel` y `_edoc_test_connection`. Es la imprenta autorizada quien
  asigna el Nº de control (PA SNAT/2024/000102, art. 7.15).
- `account.move._l10n_ve_edoc_document_vals()`: construye el documento como un
  dict **neutro** independiente del proveedor (emisor y comprador con RIF,
  razón social y domicilio; líneas con cantidad, precio, descuento, base,
  alícuota y marca de exento; totales exento, base, IVA y total). Toda la
  lógica fiscal vive aquí, de modo que el adaptador solo renombra campos.
- Separación de base gravada y base exenta línea por línea, apoyada en
  `_l10n_ve_is_exempt()` de `l10n_ve_bw_invoice_format` — marca de las
  operaciones exentas de la PA SNAT/2024/000102 art. 7.8 y de la PA
  SNAT/2011/00071 arts. 13.8, 14.5 y 32.2.
- Bloque `documento_afectado` (número, Nº de control, fecha y monto del
  documento de origen) en notas de crédito (`reversed_entry_id`) y notas de
  débito (`debit_origin_id`), tal como exigen la PA SNAT/2011/00071 y la PA
  SNAT/2024/000102.
- `_l10n_ve_edoc_doc_type()`: tipifica el documento como `factura`,
  `nota_credito` o `nota_debito`; la nota de débito es un `out_invoice` con
  `debit_origin_id` y sin esta rama viajaría a la imprenta como factura.
- Máquina de estados en `account.move`: `l10n_ve_edoc_state` (Por enviar ·
  Enviado, sin Nº de control · Nº de control asignado · Error · Anulado ante la
  imprenta), más `l10n_ve_edoc_external_id` y `l10n_ve_edoc_error`.
- Encolado automático en `_post()`: los documentos de venta publicados en
  diarios cuyo canal de emisión es «Imprenta digital» y cuya compañía tiene
  proveedor configurado pasan a «Por enviar».
- Soporte simultáneo de proveedores **síncronos** (devuelven el Nº de control
  en la propia emisión, como The Factory HKA) y **asíncronos** (hay que
  consultarlo después, como Unidigital): `_edoc_send` puede devolver
  `control_number` vacío, el documento queda en «Enviado, sin Nº de control» y
  `action_l10n_ve_edoc_fetch()` completa la asignación.
- Write-back del Nº de control y de su fecha de asignación mediante el contexto
  `l10n_ve_control_writeback`, único origen que el guard de
  `l10n_ve_bw_fiscal_books` admite en los canales donde el número lo asigna un
  tercero (PA SNAT/2024/000102 art. 7.15).
- Modelo `l10n.ve.edoc.log`: bitácora de cada llamada (operación, petición,
  respuesta, resultado y compañía), que se escribe también —y sobre todo—
  cuando la llamada falla. Es la evidencia que la PA SNAT/2024/000121 exige al
  sistema de facturación. Incluye vistas de lista y formulario sin creación
  —el formulario tampoco permite edición—, menú bajo Contabilidad › Reportes y
  ACL de **solo lectura** para `account.group_account_invoice` y
  `account.group_account_manager`.
- Aislamiento de fallos: una excepción del proveedor se registra en la bitácora
  y deja el documento en estado «Error» con el mensaje, pero nunca revierte la
  factura ya contabilizada.
- Proveedor simulado `l10n.ve.edoc.provider.dummy` («Simulado (solo pruebas)»),
  con `_dummy_fetch_delay` para ejercitar el camino asíncrono sin contratar
  imprenta.
- Configuración por compañía en los Ajustes de Contabilidad: proveedor, URL,
  usuario, clave, serie/sucursal y «Ambiente de pruebas» — este último activo
  por defecto, para desmarcarlo solo cuando el SENIAT haya autorizado al
  emisor.
- Cron «Imprenta digital VE: enviar y consultar documentos», cada 5 minutos,
  que envía los pendientes y consulta los asíncronos en una sola pasada. Se
  entrega **desactivado de fábrica**, hasta que haya imprenta contratada y
  autorización del SENIAT.
- Botones en el formulario de factura, visibles solo en el canal digital:
  «Enviar a imprenta digital» y «Consultar Nº de control»; y campos de estado,
  identificador externo y último error junto al Nº de control.
- Pruebas en `tests/test_einvoice.py`: separación gravado/exento, nota de
  crédito y nota de débito con su documento afectado, write-back del Nº de
  control pese al guard del canal digital, rechazo de documentos fuera del
  canal digital, no repetibilidad del envío, proveedor asíncrono en dos pasos y
  fallo del proveedor sin tumbar la contabilidad.
- Alcance de la entrega: se publica el núcleo y el proveedor **simulado**. El
  adaptador de una imprenta real no se incluye — la selección de
  `l10n_ve_edoc_provider` solo ofrece el simulado — a la espera de contratar la
  imprenta y recibir su documentación, credenciales de QA y URL de producción.
