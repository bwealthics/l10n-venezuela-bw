# Changelog — Venezuela — Paraguas de Cumplimiento Fiscal

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.0.0] - 2026-08-01

Versión inicial publicada del módulo.

### Añadido

- Módulo paraguas sin modelos ni vistas propias: instalarlo arrastra la suite
  fiscal VE (`l10n_ve_bw_chart`, `l10n_ve_bw_fiscal_books`,
  `l10n_ve_bw_invoice_format`, `l10n_ve_bw_igtf`, `l10n_ve_bw_wh_iva`,
  `l10n_ve_bw_wh_islr`, `l10n_ve_bw_municipal`) más el `auditlog` de OCA, que
  exige tener `OCA/server-tools` rama 19.0 en el `addons_path`.
- Licencia **AGPL-3**, impuesta por la dependencia de OCA `auditlog` (AGPL-3).
  El audit log se aísla en este módulo precisamente para que el resto de la
  suite pueda mantenerse LGPL-3.
- `post_init_hook` → `hooks.ensure_audit_rules(env)`: crea las reglas de
  auditoría **y las confirma** con `set_to_confirmed()`. Es el punto central del
  módulo: OCA `auditlog` solo engancha los modelos cuyas reglas están en estado
  `confirmed`, de modo que una regla creada pero no suscrita no registra nada.
  Responde al riesgo sancionatorio del COT 2020 por libros no llevados o no
  conservados: el audit log se entrega **suscrito**, no solo creado.
- Constante `AUDITED_MODELS` con los siete modelos de relevancia fiscal que se
  auditan: `account.move`, `account.journal`, `account.tax`, `res.company`,
  `res.partner`, `l10n.ve.islr.voucher` y `l10n.ve.iva.wh.voucher`.
- Reglas creadas con `log_create`, `log_write` y `log_unlink` activos y
  `log_type = "full"`, que guarda el valor **anterior** de cada campo. El
  `log_read` se deja desactivado a propósito: el propio OCA documenta que el
  registro de lecturas no funciona en todos los modelos, y activarlo daría una
  cobertura falsa ante un fiscalizador.
- `account.move.line` queda deliberadamente fuera de la auditoría por volumen
  (cada cierre de caja del POS genera cientos de líneas); sus importes ya están
  protegidos por la cadena de hash del diario.
- El hook resuelve los `ir.model` buscando por nombre de modelo en lugar de por
  XML-ID, porque los `ir.model` de los modelos heredados pertenecen a los
  módulos que los definen (`account`, `base`) y adivinar esos identificadores
  rompe la instalación. Si un modelo no existe, deja un *warning* en el log y
  continúa en vez de abortar.
- Ejecución idempotente: si ya existe una regla para el modelo se reutiliza y
  solo se confirma, sin duplicarla. `ensure_audit_rules` es reinvocable desde
  `odoo-bin shell` para añadir modelos a `AUDITED_MODELS` a posteriori.
- Sin datos XML: las reglas se crean por código para poder confirmarlas en el
  mismo paso y no depender de XML-IDs ajenos.
- `docs/CUMPLIMIENTO.md`, procedimiento operativo de los tres controles que
  quedan en manos del contador porque son decisiones irreversibles del negocio,
  no del software:
  - **Inalterabilidad por diario** (comprobación de integridad / hash), con sus
    consecuencias: pérdida definitiva de «Restablecer a borrador» y «Cancelar»
    en ventas —la corrección pasa a ser la nota de crédito—, el fallo silencioso
    del posteo en lote desde la vista de lista sin marcar «Forzar hash», y el
    bloqueo del cierre de sesión del POS si hay un hueco en la secuencia. Se
    documenta por qué el diario de contingencia **no** lleva hash: replica un
    documento que ya existe en el talonario y tiene que poder corregirse.
  - **Audit Trail** de contabilidad, que impide borrar los registros rastreados.
  - **Canal de emisión (VE)** por diario y su efecto sobre la editabilidad del
    Nº de control (máquina fiscal e imprenta digital lo bloquean, forma libre
    permite escribirlo una sola vez, contingencia lo deja editable, sin canal se
    comporta como antes).
- Documentación explícita de los límites de la cobertura: lecturas,
  `account.move.line`, acceso directo a PostgreSQL o al sistema operativo, y la
  no retroactividad del registro (conviene anotar la fecha de despliegue y
  guardar un respaldo como línea base).
- Criterio de retención documentado: el cron «Auto-vacuum audit logs» de OCA,
  que borraría a los 180 días, viene desactivado y **debe quedarse así** por el
  art. 18.7 de la PA SNAT/2024/000102, que obliga a conservar los documentos
  10 años; a cambio hay que vigilar el crecimiento de la tabla. Es un criterio
  de `docs/CUMPLIMIENTO.md`, no algo que el módulo fuerce por código.
