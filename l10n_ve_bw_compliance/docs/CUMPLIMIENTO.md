# Cumplimiento SENIAT — procedimiento operativo

Este módulo deja el ERP preparado, pero **hay tres cosas que se activan a mano**
porque son decisiones del contador, no del software.

---

## 1. Inalterabilidad de los asientos (hash por diario)

**Qué hace**: Odoo encadena criptográficamente los asientos publicados del
diario. A partir de ahí, ese diario ya no admite "Restablecer a borrador" ni
borrado, y cualquier alteración posterior queda detectable.

**Dónde**: Contabilidad → Configuración → Diarios → *(abrir el diario de
ventas)* → pestaña Ajustes Avanzados → **Comprobación de integridad**.

**Antes de activarlo, hay que saber:**

- Es **irreversible** desde la primera factura publicada. Odoo impide
  desmarcarlo después.
- El contador **pierde para siempre** el "Restablecer a borrador" y el
  "Cancelar" de las facturas de **venta**. La única corrección pasa a ser la
  **Nota de Crédito**. Compras, nómina y misceláneos no se ven afectados.
- **Trampa que no da error**: publicar en lote desde la vista de lista usa un
  asistente que **excluye** los diarios con hash salvo que se marque la casilla
  "Forzar hash". No se publica nada y **no aparece ningún mensaje de error**.
  Recomendación: publicar desde el formulario de la factura.
- Un **hueco en la secuencia** hace fallar la publicación. Si eso ocurre al
  cerrar una sesión del POS, **la sesión no cierra**. Por eso: nunca borrar ni
  renumerar una factura de venta en borrador que ya tenga número asignado.

**El diario de contingencia NO lleva hash, y es a propósito**: replica un
documento que ya existe en papel en el talonario, así que tiene que poder
corregirse. Por eso vive en su propio diario y no contamina la cadena del
diario fiscal.

---

## 2. Audit Trail restrictivo de contabilidad

**Dónde**: Contabilidad → Configuración → Ajustes → **Audit Trail**.

Impide **borrar** los registros contables rastreados: solo se pueden cancelar o
archivar. Complementa al hash, no lo sustituye.

---

## 3. Canal de emisión de cada diario

**Dónde**: Contabilidad → Configuración → Diarios → campo **Canal de emisión (VE)**.

Determina quién asigna el Nº de control y si puede escribirse a mano:

| Canal | Quién asigna el Nº de control | El campo en Odoo |
|---|---|---|
| Máquina fiscal | la ACLAS, al imprimir | bloqueado |
| Imprenta digital | el proveedor autorizado, por API | bloqueado |
| Forma libre | se transcribe del talonario | se escribe **una sola vez** |
| Contingencia | se transcribe del talonario | editable |
| *(vacío)* | — | libre (es el caso de las compras) |

Los diarios se entregan **sin canal**, que se comporta exactamente como antes.
Fijarlo es una decisión deliberada: en cuanto se pone, el Nº de control deja de
poder corregirse a mano en ese diario.

---

## Lo que el audit log SÍ y NO cubre

El módulo instala OCA `auditlog` y deja activas las reglas sobre los modelos
fiscales, registrando **creación, modificación y borrado** con fecha, hora,
usuario y valor anterior de cada campo.

**No cubre**, y conviene decirlo antes de que lo pregunte un fiscalizador:

- **Las lecturas.** El propio OCA declara que el registro de lecturas no
  funciona en todos los modelos, así que se dejó desactivado en vez de dar una
  cobertura falsa.
- **`account.move.line`**, por volumen: cada cierre de caja genera cientos de
  líneas. Sus importes están protegidos por la cadena de hash, que detecta
  cualquier alteración. Si se necesita, se añade a `AUDITED_MODELS` en
  `hooks.py` y se re-ejecuta.
- **El acceso directo a PostgreSQL o al sistema operativo.** Ningún log de
  aplicación resiste eso; es control de infraestructura, no de Odoo.
- **Lo anterior a la instalación.** El registro no es retroactivo: conviene
  anotar la fecha del despliegue y guardar un respaldo de la base como línea
  base.

**Retención**: el cron "Auto-vacuum audit logs" de OCA viene **desactivado** y
borraría a los 180 días. Se deja desactivado a propósito: la PA SNAT/2024/000102
art. 18.7 habla de conservar los documentos **10 años**. A cambio, la tabla
crece; conviene revisar su tamaño cada cierto tiempo.
