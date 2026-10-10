# Changelog: Venezuela · Doble Moneda en el POS

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.1.0] - 2026-10-10

### Cambiado

- **Hora de corte**: el POS solo pide la tasa del día después de la hora de
  publicación configurada (9:15 Caracas). Antes vale la del día anterior.
  `l10n_ve_bs_get_today_rate` devuelve `valid_until` (UTC) y el recibo deja de
  imprimir Bs con una tasa vencida aunque la caja siga abierta.
- "Hoy" se calcula en la zona de la compañía, no en la del usuario del POS.

## [19.0.1.0.0] - 2026-10-09

Versión inicial. Lleva al POS la regla de `l10n_ve_bw_dual_currency`: no se cobra
con la tasa BCV de otro día en silencio. Depende de ese módulo y de
`point_of_sale`, y se instala solo (`auto_install`) cuando ambos están presentes.

### Añadido

- **Lectura de la tasa** (`pos.config.l10n_ve_bs_get_today_rate`): devuelve la
  última tasa Bs menor o igual a hoy (o 0 y sin fecha si no hay ninguna), su
  fecha, si existe la tasa exacta de hoy (`is_today`) y los datos mínimos de la
  moneda Bs (id, nombre, símbolo, decimales y posición), porque el POS solo
  carga la moneda de la compañía. Lee con `sudo`: el cajero no tiene permiso de
  lectura sobre las tasas ni sobre monedas inactivas. Sin moneda Bs, o con la Bs
  igual a la moneda de la compañía, o con una compañía sin país fiscal
  Venezuela, `is_today` es verdadero y el POS no pide nada.
- **Carga de la tasa de hoy desde la caja**
  (`pos.config.l10n_ve_bs_set_today_rate`). Camino de emergencia para cuando la
  tasa automática de la mañana no quedó cargada:
  - Solo crea. Si ya existe la tasa de hoy no la pisa (otra caja o el n8n pudo
    cargarla un instante antes) y devuelve la existente.
  - Acepta un número mayor que cero y finito. Rechaza texto, cero, negativos,
    `nan` e infinito.
  - Rechaza una tasa a más de ±15 % de la última conocida (si existe), para
    atrapar un dígito de más o de menos.
  - Crea el `res.currency.rate` con `sudo`, con fecha de hoy, en la compañía
    raíz y con el valor en `company_rate` (Bs por 1 unidad de la moneda de la
    compañía).
  - Deja constancia en el chatter de la sesión POS abierta, con el usuario y el
    valor.
  - Con una compañía sin moneda Bs distinta de la suya lanza un `UserError`: no
    hay tasa que cargar.
- **Precarga en el POS** (patch de `PosStore`): al iniciar lee la tasa sin
  esperar y sin romper el arranque. La última tasa conocida se guarda en el
  navegador, por caja, como respaldo cuando el POS arranca sin conexión.
- **Popup de la tasa**:
  - Se muestra al entrar a la pantalla de pago (patch de `PaymentScreen`), antes
    de que se elijan métodos o se capturen Bs, y de nuevo al validar si sigue
    faltando. Una sola promesa compartida evita dos popups encimados.
  - Teclado numérico "Tasa BCV de hoy: Bs por 1 USD", con la última tasa cargada
    y su fecha como referencia, y una confirmación explícita antes de guardar.
  - Errores del servidor (fuera de ±15 %, valor inválido) se muestran en un
    diálogo "No se pudo guardar la tasa" y se vuelve a pedir.
  - Si el cajero cancela el teclado, la orden no se valida mientras falte la
    tasa de hoy.
  - Sin conexión no bloquea: si no se puede leer la tasa, o se pierde la
    conexión al guardarla, sigue la venta con la última tasa conocida.
- **Tasa y fecha en la orden** (`pos.order`): `l10n_ve_bs_rate` (Bs por 1 unidad
  de la moneda de la compañía, 6 decimales) y `l10n_ve_bs_rate_date` (fecha de la
  tasa usada), planos y sin `required`, porque el POS 19 serializa todos los
  campos de `pos.order`.
  - Al validar con la tasa de hoy confirmada, la caja escribe ambos campos y
    sobrescribe lo que haya (en restaurante la orden se sincronizó antes como
    borrador y pudo traer la tasa de otro día). Sin confirmación (sin conexión)
    solo rellena si la orden no tiene tasa.
  - Las órdenes en borrador no reciben tasa por defecto.
  - Una orden no borrador que se crea sin tasa, o que pasa a pagada, hecha o
    facturada sin ella, recibe la última tasa menor o igual al día local de la
    orden y la fecha de esa tasa. No bloquea. Sin ninguna tasa, queda vacía.
- **Validación**: `validateOrder` de `OrderPaymentValidation` pide la tasa antes
  de nada. Se parchea ese método y no `askBeforeValidation` porque
  `l10n_ve_bw_pos_bs` y `l10n_ve_bw_fiscal_printer` ya encadenan
  `askBeforeValidation` para capturar los Bs recibidos, y el orden entre parches
  de módulos distintos no está garantizado. `validateOrder` corre antes de toda
  esa captura.
- **Recibo** (`OrderReceipt`): debajo del Total, "Total Bs" (total con impuestos
  por la tasa, redondeado a 2 decimales, con el símbolo de la moneda Bs) y "Tasa
  BCV: X (dd-mm-aaaa)" con 4 decimales. La tasa es la de la orden, con su fecha;
  si la orden no tiene tasa propia, la precargada, con su fecha. Sin tasa, el
  recibo queda igual al del core. El bloque forma parte del de totales, que el
  POS no imprime en la pre-cuenta.
- **Pruebas** (`tests/test_pos_rate.py`, `post_install`, con una moneda Bs de
  prueba sin tasas previas): lectura sin ninguna tasa, con la de hoy, con la de
  ayer (no cuenta como hoy) y sin moneda Bs; carga sin tasa previa, dentro de la
  tolerancia, fuera de ±15 %, con valores inválidos, sin pisar una tasa
  existente, sin moneda Bs y con constancia en la sesión; y la tasa por defecto
  de las órdenes, con el borrador sin tasa hasta que pasa a pagado.

### Notas

- **Pre-cuenta y reimpresiones** (ajuste 2026-10-10): sin tasa propia en la orden,
  el recibo solo muestra "Total Bs" con la tasa de HOY confirmada por el servidor
  y fechada hoy. Las órdenes ya cerradas sin tasa (anteriores al módulo) no
  muestran el bloque. Una tasa restaurada de la caché del navegador nunca se toma
  como la de hoy.
- **La factura de la orden usa la tabla de tasas**, no la tasa del ticket: es la
  fuente legal (tasa BCV del día) y en el mismo día coinciden. Sin conexión la
  caja puede cobrar con la última tasa conocida; la factura se tasa al
  sincronizar.
- **Salto de tasa mayor a 15 %**: el POS rechaza la tasa digitada (igual que el
  guard del n8n). En ese caso un usuario de contabilidad debe cargarla en
  Contabilidad > Configuración > Monedas.


- La tasa de la orden y el recibo no cambian los asientos contables: los Bs de
  los asientos del cierre del POS los calcula `l10n_ve_bw_dual_currency` con su
  propia regla.
- Las pruebas del navegador (popup, validación, recibo) no están cubiertas por
  las pruebas automáticas de este módulo: hay que verificarlas en una caja.
