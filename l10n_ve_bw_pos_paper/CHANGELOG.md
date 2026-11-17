# Changelog — Venezuela — POS en papel (talonario / formas libres)

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.0.1] - 2026-10-17

### Corregido

- `pos.config._compute_local_data_integrity` hereda con `@api.depends` sobre
  `l10n_ve_paper_mode`, `l10n_ve_paper_batch_id` y
  `l10n_ve_contingency_journal_id` (patrón de `pos_restaurant`): un write sobre
  esos campos actualiza `last_data_change` y el POS descarta su caché IndexedDB
  la próxima vez que carga datos del servidor (abrir la caja desde el backend,
  sesión nueva o ☰ → Volver a cargar datos). Ojo: con la sesión `opened`, un F5
  simple NO pide datos al servidor en Odoo 19 (`data_service.js`
  `loadInitialData`), así que no basta con recargar la pestaña. Test
  `test_paper_change_invalidates_pos_cache`.

## [19.0.1.0.0] - 2026-10-15

### Añadido

- Módulo nuevo extraído de `l10n_ve_bw_fiscal_printer` 19.0.1.3.1, sin cambios
  funcionales y con los mismos nombres de campo, para retirar el módulo de
  impresora fiscal por bridge sin perder la caja en papel:
  - `pos.config`: `l10n_ve_paper_mode`, `l10n_ve_paper_batch_id`,
    `l10n_ve_contingency_journal_id`, sus constraints y
    `l10n_ve_get_ves_rate()`, con sus ajustes en `res.config.settings`.
  - `pos.session`: `l10n_ve_contingency_reason`,
    `l10n_ve_contingency_user_id`, `l10n_ve_contingency_start` y
    `l10n_ve_contingency_open()`.
  - `pos.order`: bitácora `l10n_ve_fiscal_event` / `l10n_ve_fiscal_event_note`
    (la escribe la captura del talonario en cada venta), ramas de talonario y
    formas libres de `_prepare_invoice_vals`, bloqueo de consolidados con
    papelería, cliente obligatorio en modo papel y `_create_invoice` con el
    contexto `l10n_ve_control_writeback`.
  - POS: `ves_rate.js` (`getVesRate`, `toVes`, `round2`, cache de la última
    tasa), captura de papelería en `askBeforeValidation`, captura de control
    en contingencia de sesión y botón **Contingencia**.
- Puntos de extensión para un módulo de máquina fiscal:
  `_l10n_ve_paper_invoice_vals` y `_l10n_ve_has_fiscal_document` en
  `pos.order`; `_l10nVeHasFiscalMachine` en la validación de pago y
  `l10nVeHasFiscalMachine` en `ControlButtons`.

### Cambiado

- Respecto al módulo de origen, sin `pos_restaurant` en `depends`: la opción
  de ocultar la pre-cuenta (`l10n_ve_hide_precuenta`) no se migra.
