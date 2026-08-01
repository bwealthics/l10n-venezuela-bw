# Changelog — Venezuela — Impresora Fiscal POS (The Factory HKA)

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.2.1] - 2026-08-01

### Corregido

- `_prepare_invoice_vals` lanzaba `ValueError` de singleton al facturar desde el
  backend un consolidado de varias órdenes POS: en Odoo 19 el asistente
  `pos.make.invoice` llama `_generate_pos_order_invoice` sobre un recordset
  **multi-orden** (el core es multi-aware, `is_single_order = len(self) == 1`) y
  el override leía los campos fiscales sin guard. Ahora, con `len(self) != 1`,
  el consolidado sin datos fiscales pasa limpio y sin Nº de control; con una
  sola orden el comportamiento queda intacto.

### Añadido

- Bloqueo con `UserError` —nombrando las órdenes— cuando el consolidado incluye
  alguna orden que ya tiene ticket de máquina fiscal (`l10n_ve_fiscal_number`) o
  Nº de control del talonario (`l10n_ve_contingency_control`): un solo
  `account.move` no puede llevar el correlativo de varios tickets, y
  consolidarlos los dejaría fuera del Libro de Ventas (Reglamento LIVA arts. 76
  y 77) descuadrando contra el Reporte Z.
- Override de `pos.order._create_invoice` que declara el contexto
  `l10n_ve_control_writeback` cuando los vals traen `l10n_ve_control_number`. Sin
  él, el guard de `create` de `l10n_ve_bw_fiscal_books` bloqueaba la facturación
  de una orden cuyo ticket fiscal YA se había impreso, si el diario de
  facturación de la caja está marcado con canal de emisión `mf`.
- Pruebas de los tres casos: consolidado sin datos fiscales, consolidado
  bloqueado (por máquina y por talonario) y write-back del Nº de control al
  facturar en un diario de canal `mf`.

## [19.0.1.1.0] - 2026-07-31

Primera versión publicada del módulo.

### Añadido

#### Impresión fiscal en el POS

- Bloqueo de la validación de la orden POS hasta obtener número fiscal: patch de
  `OrderPaymentValidation.shouldHideValidationBehindFeedbackScreen` que, si el
  bridge falla, **no llama a `super()`** — la orden se queda en la pantalla de
  pago para reintentar, porque sin número fiscal no hay venta legal.
- Comunicación con un bridge local por HTTP (`callBridge`) con cabecera
  `X-Bridge-Token` y timeout propio de 90 s implementado con `AbortController`
  (no `AbortSignal.timeout`, que exige Chrome 103+ y las cajas suelen correr
  Chromium kiosk viejos). El fetch sale del **navegador de la caja**: el
  servidor Odoo nunca toca la impresora.
- Distinción explícita entre *timeout* (`FiscalBridgeError.ambiguous = true`: el
  ticket PUDO imprimirse) y *conexión rechazada* (seguro NO imprimió), que es lo
  que habilita el flujo anti-duplicados.
- Anti-duplicados tras un intento ambiguo: marca de incertidumbre en
  `order.uiState` y en `localStorage` por `uuid` (sobrevive una recarga del POS)
  y consulta a `/check-last-invoice` con orden de decisión — el bridge ecoa el
  `uuid` propio → se adopta ese número; `uuid` ajeno → reimprimir; sin `uuid`
  (bridge reiniciado) y total distinto → reimprimir; total igual → lo decide el
  cajero mirando el ticket físico.
- `/claim-terminal` y `/release-terminal` alrededor de cada impresión, para que
  dos cajas no hablen a la vez con la misma máquina.
- Bitácora de incidencias por orden en campos **planos** de `pos.order`
  (`l10n_ve_fiscal_event` con los códigos `adopt_uuid`, `adopt_manual`,
  `reprint`, `contingency`, `blocked`, y `l10n_ve_fiscal_event_note` con las
  últimas 10 líneas: hora, cajero y detalle). Se escriben desde el frontend y no
  por RPC, porque una llamada al servidor falla justo cuando importa —con la
  caja sin conexión— y el registro debe sobrevivir hasta el sync.
- Construcción del payload de la máquina: descripción recortada a 40 caracteres,
  precio unitario convertido a bolívares a la tasa BCV, alícuota redondeada al
  slot soportado por la máquina (0, 8, 16 o 31) tomando los impuestos **después
  de la posición fiscal** —un cliente exento cuya FP mapea 16 % → exento imprime
  0, igual que contabiliza Odoo—, y cantidades con el signo de la devolución.
- El total declarado se calcula con la aritmética de la máquina
  (Σ precio × cantidad con los precios **ya redondeados** a 2 decimales) y el
  delta de redondeo por línea se absorbe en el último pago; de lo contrario el
  cierre falla por centavos.
- IGTF en el payload (`monto_igtf`): solo cuando la compañía tiene la marca
  `l10n_ve_is_spe` y hay pagos por diarios marcados `l10n_ve_igtf_applies`,
  aplicando `l10n_ve_igtf_pct` (3 % por defecto). Corresponde a la percepción del
  Sujeto Pasivo Especial que cobra en divisas sin mediación bancaria.
- Notas de crédito fiscales desde el POS: la devolución referencia número,
  serial y fecha (`DDMMAAAA`) de la factura original, tal como exige la PA 0071
  para las notas de crédito. Si la orden original no tiene número fiscal
  registrado, se bloquea y se indica emitirla a mano en la máquina.
- Tras un intento **ambiguo** de nota de crédito no se reintenta a ciegas: el
  correlativo de NC no es verificable por `/check-last-invoice`, así que se pide
  verificar el último ticket antes de repetir.

#### Reporte X, Cierre Z y contingencia

- Botones **Reporte X** y **Cierre Z** en `ControlButtons`, visibles solo si la
  caja tiene bridge configurado. El Cierre Z pide confirmación (cierra el día
  fiscal y no se puede repetir) y guarda `l10n_ve_z_number` en `pos.session`, que
  es la fila diaria resumida del Libro de Ventas para no contribuyentes
  (Reglamento LIVA art. 77).
- Modo contingencia de la PA 0071 art. 11, autorizado **por sesión de caja**
  (`l10n_ve_contingency_reason`, `l10n_ve_contingency_user_id`,
  `l10n_ve_contingency_start`, con `tracking`): muere al cerrar el turno, sin
  código de expiración. El control de grupo se valida en el **servidor**
  (`point_of_sale.group_pos_manager`, `AccessError`), el motivo exige un mínimo
  de 5 caracteres y reabrirlo no pisa quién ni cuándo lo autorizó.
- Rótulo rojo permanente «CONTINGENCIA ACTIVA» en el botón mientras el modo esté
  abierto, como control anti-abuso visible toda la jornada.
- Captura del Nº de Control del talonario cuando la máquina no pudo emitir, con
  dos candados deliberados: solo aparece **después de un fallo real** de la
  máquina, y queda **vetada si el error es ambiguo** (timeout), porque sumar un
  formato manual a un ticket que pudo haber salido declararía dos veces el mismo
  hecho imponible. Se rechaza además un Nº de Control ya usado en otra orden de
  la sesión.
- La factura de una orden en contingencia se emite en el diario
  `l10n_ve_contingency_journal_id` (dominio restringido al canal de emisión
  `contingencia`), con el Nº de control del formato preimpreso y `ref`
  «Contingencia \<Nº\>». Ese diario no lleva cadena de hash a propósito: replica
  un documento que ya existe en papel.

#### Puente con el Libro de Ventas y el backend

- Propagación del número fiscal de la orden POS a la factura como
  `l10n_ve_control_number` —el slot que lee el Libro de Ventas de
  `l10n_ve_bw_fiscal_books`—, con `ref` «MF \<serial\> Nº \<número\>» y copia
  íntegra de serial, sello de fecha/hora y tipo de documento, para que una NC de
  backend encuentre allí los datos de la máquina.
- Botón **«Imprimir fiscal»** en el header del formulario de facturas y notas de
  crédito de cliente publicadas que aún no tienen número fiscal. Devuelve una
  `ir.actions.client` (`l10n_ve_bw_fiscal_printer.print_fiscal`) porque el fetch
  al bridge tiene que salir del navegador de la PC donde corre el bridge.
- `account.move.l10n_ve_set_fiscal_result`: write-back del número, el serial real
  reportado por la máquina y el sello de fecha/hora local. Es idempotente con el
  mismo número y lanza `UserError` si llega uno distinto —nunca pisa un
  correlativo ya registrado, que quedaría sin rastro en Odoo—, escribe con el
  contexto `l10n_ve_control_writeback` para pasar el guard del canal `mf` de
  `fiscal_books` y deja constancia en el chatter.
- Validaciones antes de imprimir desde el backend: una sola caja con bridge por
  compañía (con varias, todas apuntan a `localhost` y el serial registrado
  saldría equivocado), moneda VES existente, tasa BCV cargada, ninguna línea
  negativa (la máquina no las imprime) y cuadre del total de la máquina contra el
  total contable con tolerancia por línea.
- Notas de crédito de backend: exigen que la factura revertida
  (`reversed_entry_id`) tenga número fiscal y envían número, serial y fecha
  `DDMMAAAA` de la afectada.
- Campos fiscales en el formulario de factura anclados **después de**
  `l10n_ve_control_number`, heredando la vista de `l10n_ve_bw_fiscal_books` en vez
  de la base, para que el ancla exista siempre sin depender de la prioridad entre
  vistas hermanas; y grupo «Datos fiscales (máquina)» en el formulario de
  `pos.order`.

#### Configuración

- Campos en `pos.config`: `l10n_ve_bridge_url` (vacío = caja sin impresora
  fiscal, el POS valida normal; es el default seguro), `l10n_ve_bridge_token`,
  `l10n_ve_default_payment_code` (slot de pago usado al imprimir desde el
  backend, donde aún no hay pagos POS), `l10n_ve_contingency_journal_id` (vacío =
  esa caja no tiene salida de contingencia) y `l10n_ve_hide_precuenta`. El serial
  de la máquina se reusa de `l10n_ve_bw_fiscal_books`.
- `pos.payment.method.l10n_ve_fiscal_payment_code`: slot de medio de pago de la
  máquina (01–24 del protocolo HKA; retención = 16), más `l10n_ve_igtf_applies`
  como related del diario para marcar los pagos en divisas. Ambos bajan al POS.
- Opción de **ocultar la pre-cuenta** (botón *Bill* de `pos_restaurant`): el
  art. 49 de la PA 0071 prohíbe entregar notas de consumo o pre-cuentas con
  montos como documento sustitutivo de la factura fiscal.
- `pos.config.l10n_ve_get_ves_rate()`: bolívares por 1 unidad de la moneda de la
  compañía a la tasa BCV del día, **sin redondear** (una tasa truncada desviaría
  los totales Z contra el Libro de Ventas). Devuelve `0.0` si no existe ninguna
  fila de `res.currency.rate`, porque con la tasa implícita 1.0 toda factura
  saldría en Bs = USD; el frontend cachea la última tasa buena para seguir
  facturando sin nube y bloquea si nunca hubo ninguna.
- Bloques «Bridge de impresora fiscal» y «Pre-cuenta (art. 49 PA 0071)» en los
  ajustes del Punto de Venta, dentro del bloque de la localización venezolana.
- `res.company._load_pos_data_fields` añade `l10n_ve_is_spe` y
  `l10n_ve_igtf_pct`, que gatean la rama IGTF del payload en el frontend.
- Dependencias: `pos_restaurant`, `l10n_ve_bw_fiscal_books` y
  `l10n_ve_bw_igtf`.
- Batería de pruebas en `tests/test_fiscal_printer.py`: carga de campos al POS,
  tasa BCV presente y ausente, alícuota más cercana, payload de factura, línea
  negativa bloqueada, varias cajas con bridge, NC que exige origen fiscal,
  write-back idempotente y doble impresión rechazada, guards de la acción, y el
  ciclo completo de contingencia (permiso de gerente, motivo corto, diario
  faltante, campos que viajan al POS y factura en su propio diario).

---

Las versiones anteriores a la primera listada aquí no tienen registro detallado:
el módulo se desarrolló antes de adoptar este changelog y se publicó ya en
`19.0.1.1.0`. La `19.0.1.2.0` no existe como versión distribuida: el arreglo del
consolidado multi-orden se publicó directamente como `19.0.1.2.1`.
