# Changelog — Venezuela — IGTF

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.1.0] - 2026-08-01

### Añadido

- Campo `l10n_ve_igtf_manual` («IGTF fijado a mano») en `account.payment`, que
  congela el monto frente al recálculo automático. Se muestra en el grupo IGTF
  del formulario del pago solo cuando está marcado, y es editable en borrador.
- Inverse `_inverse_l10n_ve_igtf_amount`: detecta la edición real comparando lo
  escrito contra el monto automático con `currency_id.compare_amounts`. Hacía
  falta porque el cliente web reenvía el valor computado al guardar (echo-back
  del onchange), de modo que la mera presencia del campo en `vals` no distingue
  una edición del usuario. Como efecto colateral deseado, desmarcar la casilla
  devuelve el campo al cálculo automático en un solo guardado.
- Helper `_l10n_ve_igtf_auto_amount()`, que aísla el cálculo
  `amount × alícuota / 100` redondeado a la moneda del pago y lo deja
  disponible tanto para el compute como para el inverse.

### Corregido

- Un IGTF fijado a mano —típicamente puesto en 0 por una operación en divisas
  que no causa el impuesto, art. 4 num. 5/6 de la Ley IGTF— se perdía al
  corregir después el monto, la fecha o el diario del pago en borrador, porque
  el compute almacenado volvía a pisarlo. Ahora `_compute_l10n_ve_igtf_amount`
  depende también de `l10n_ve_igtf_manual` y respeta el valor fijado.

## [19.0.1.0.0] - 2026-07-31

Versión inicial publicada del módulo.

### Añadido

- Casilla `l10n_ve_igtf_applies` («Sujeto a IGTF») en `account.journal`,
  visible en diarios de tipo banco, efectivo y crédito. El hecho imponible se
  modela **por medio de pago y no por moneda**: se marcan los diarios en
  divisas (Zelle, efectivo USD, USDT) y se dejan sin marcar los diarios en
  bolívares, cuya alícuota es 0 % desde el Decreto 4.972 (G.O.E. 6.821 del
  12/07/2024) para los numerales 1 al 4 del art. 4 de la Ley IGTF.
- Débito propio: al confirmar un pago saliente por un diario marcado se genera
  y postea automáticamente un asiento **Debe Cuenta de Gasto IGTF / Haber
  cuenta por defecto del diario**, en el mismo diario del pago, con su fecha y
  con referencia `IGTF <alícuota>% - <pago>`.
- Percepción como Sujeto Pasivo Especial: los cobros por un diario marcado
  generan el asiento inverso **Debe cuenta del diario / Haber Cuenta de
  Percepción IGTF**, pero solo si la compañía tiene activa la marca
  `l10n_ve_is_spe` y la fecha del cobro es igual o posterior a
  `l10n_ve_spe_date` (designación por el SENIAT); con la marca activa y la
  fecha vacía, la percepción aplica desde que se activa la marca. Con la marca
  SPE desactivada no se ejecuta ninguna lógica de cobro. Corresponde al rol de agente de
  percepción de los SPE que reciben pagos en divisas sin mediación bancaria
  (PA SNAT/2022/000013, G.O. 42.339 del 17/03/2022).
- Monto `l10n_ve_igtf_amount` editable y anulable pago por pago: con el monto
  en 0 no se genera ningún asiento, para las operaciones en divisas que no
  causan el impuesto (art. 4 num. 5/6 de la Ley IGTF).
- Configuración por compañía en Ajustes › Contabilidad › «Localización
  Venezuela — IGTF»: alícuota `l10n_ve_igtf_pct` (3 % por defecto, art. 24 de
  la Ley IGTF reformada en G.O.E. 6.687 del 25/02/2022, ratificado para
  divisas y criptoactivos por el art. 2 del Decreto 4.972),
  `l10n_ve_igtf_expense_account_id` (restringida por dominio a cuentas de
  gasto, p. ej. 660101 Gasto por IGTF) y `l10n_ve_igtf_perception_account_id`
  (restringida a pasivo, p. ej. 210304 IGTF Percibido por Enterar). Ambas
  cuentas con `check_company`.
- Botón estadístico «Asiento IGTF» en el formulario del pago, que abre el
  asiento vinculado en `l10n_ve_igtf_move_id`, para los grupos de contabilidad.
- Reversa en lugar de borrado: al pasar el pago a borrador o cancelarlo, el
  asiento IGTF ya posteado se revierte con `_reverse_moves(cancel=True)`
  conservando la fecha original, y nunca se elimina, porque consume la
  secuencia del diario de banco (protección de la cadena de secuencia de
  `account.move` y continuidad de la numeración en los libros del SENIAT). Los
  asientos aún en borrador sí se eliminan. En ambos casos se limpia el vínculo,
  de modo que repostear el pago regenera un asiento nuevo sin duplicar.
- Errores de configuración explícitos (`UserError`) cuando falta la cuenta por
  defecto del diario, la cuenta de gasto IGTF o la cuenta de percepción.
- Conversión del asiento con `currency_id._convert` a la moneda de la compañía
  usando la fecha del pago: las líneas quedan en la divisa del pago con su
  contravalor en moneda funcional.
- El compute del monto depende únicamente de campos que quedan inmutables tras
  el posteo (monto, moneda, diario, tipo de pago, fecha). La alícuota y las marcas SPE
  de la compañía se excluyen deliberadamente de `@api.depends` para que un
  cambio posterior de configuración no reescriba pagos históricos.
- Dependencia de `l10n_ve_bw_chart`, de donde se toman la marca de Sujeto
  Pasivo Especial y su fecha de designación.
- Batería de pruebas en `tests/test_igtf.py`: débito propio, percepción SPE,
  monto editado y monto anulado, diario sin la marca, cobro anterior a la fecha
  de designación, reversa al pasar a borrador y al cancelar con regeneración al
  repostear, cuentas de configuración faltantes, y regresión del flujo del
  asistente «Registrar Pago», que crea y postea en un solo paso.
