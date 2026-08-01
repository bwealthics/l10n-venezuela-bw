# Changelog — Venezuela · Conector de Imprenta Digital

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

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
