Venezuela · Doble Moneda en el POS
==================================

## Qué resuelve

Extiende `l10n_ve_bw_dual_currency` al punto de venta. Antes de cobrar, el POS
se asegura de que exista la tasa BCV de hoy. Al cobrar, guarda esa tasa y su
fecha en la orden. En el recibo imprime el total en bolívares y la tasa usada.

Se instala solo (`auto_install`) cuando están instalados el módulo de doble
moneda y `point_of_sale`.

## Cómo funciona

### La tasa de hoy

- **Precarga.** Al iniciar, el POS pide al servidor la última tasa Bs y si ya
  existe la de hoy. No retrasa ni rompe el arranque: sin conexión, o si el
  servidor falla, se queda con la última tasa guardada en el navegador (por
  caja). Esa tasa solo sirve de respaldo.
- **Popup al entrar a la pantalla de pago**, si falta la tasa de hoy. Pide
  "Tasa BCV de hoy: Bs por 1 USD", con la última tasa cargada y su fecha como
  referencia, y después una confirmación: "¿Confirma que 1 USD = X Bs es la tasa
  BCV de hoy?". Si el cajero no la confirma, el popup vuelve a salir.
- **Popup al validar**, si todavía falta. Si la pantalla de pago y la validación
  la piden casi a la vez, el cajero ve un solo popup.
- **Si el cajero cancela,** la orden no se puede validar mientras falte la tasa
  de hoy. La regla del negocio es pedirla, no cobrar con la de otro día en
  silencio.
- **Sin conexión no se bloquea.** Si el POS no puede leer la tasa del servidor, o
  se cae la conexión al guardarla, deja seguir con la última tasa conocida.
- **Solo donde aplica.** No se pide nada si la compañía no tiene moneda Bs
  de referencia, si esa moneda es la de la compañía, o si la compañía no tiene
  país fiscal Venezuela.

### Cómo se guarda la tasa digitada

El servidor (`pos.config.l10n_ve_bs_set_today_rate`) acepta la tasa solo si:

- **No existe ya la de hoy.** Si otra caja, o el n8n, la cargó un instante
  antes, la existente manda y no se pisa: se devuelve esa.
- Es un número mayor que cero.
- Está a ±15 % o menos de la última tasa conocida (si la hay). Es una defensa
  contra un dígito de más o de menos. Fuera de ese rango el POS muestra "No se
  pudo guardar la tasa" con el motivo y vuelve a pedirla.

Si la acepta, crea el registro de tasa de la moneda Bs, con fecha de hoy y en la
compañía raíz, y deja constancia en el chatter de la sesión del POS abierta, con
el usuario y el valor. Este camino es solo de emergencia, para cuando la tasa
automática de la mañana no quedó cargada.

### La orden

- Al validar con la tasa de hoy confirmada, la caja escribe en la orden
  `l10n_ve_bs_rate` y `l10n_ve_bs_rate_date`, y sobrescribe lo que hubiera. En
  restaurante la orden ya se había sincronizado como borrador y pudo traer la
  tasa de otro día. Sin conexión (tasa no confirmada) solo se rellena si la orden
  no tiene tasa.
- Las órdenes en borrador no reciben tasa por defecto: la tasa de la fecha de
  creación podría ser la de ayer.
- Si una orden llega al servidor sin tasa (sincronización sin conexión, flujos
  por código), se rellena con la última tasa menor o igual al día local de la
  orden, y se guarda la fecha de esa tasa. Ocurre al crearla, si no es borrador,
  o al pasarla a pagada, hecha o facturada. Es un flujo automático: nada se
  bloquea. Si no hay ninguna tasa, queda vacía en vez de inventar una.

### El recibo

Debajo del Total del recibo:

- **Total Bs:** el total con impuestos por la tasa, redondeado a 2 decimales y
  con el símbolo de la moneda Bs.
- **Tasa BCV:** la tasa con 4 decimales y su fecha, `dd-mm-aaaa`.

La tasa es la guardada en la orden, con su fecha. Si la orden no tiene tasa
propia, se usa la precargada, con su fecha. Sin tasa, el recibo queda idéntico
al del core. El bloque forma parte del de totales, que el POS no imprime en la
pre-cuenta.
