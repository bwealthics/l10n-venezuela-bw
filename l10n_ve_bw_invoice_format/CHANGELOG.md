# Changelog — Venezuela · Formato Legal del Comprobante

Todas las modificaciones relevantes de este módulo. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es
el de Odoo: `19.0.MAJOR.MINOR.PATCH`, donde `19.0` es la serie de Odoo.

## [19.0.1.0.0] - 2026-08-01

Versión inicial. Añade al PDF de factura los requisitos de forma que exigen la
Providencia SNAT/2011/00071 y la Providencia SNAT/2024/000102, sin depender del
conector de imprenta digital.

### Añadido

- **Fecha y hora legales en una sola línea** (PA SNAT/2024/000102 art. 7.6):
  helper `account.move._l10n_ve_legal_datetime()` que emite la fecha del
  documento como `DD-MM-AAAA` y, cuando se conoce, la hora como `HH.MM.SS` con
  sufijo `a.m`/`p.m`. El artículo admite separadores —igual que el art. 34 de la
  PA 0071—, por eso no se duplica la fecha en dos campos.
- **Hora de emisión solo cuando existe sello real**: `_l10n_ve_emission_time()`
  lee `l10n_ve_fiscal_date` (la sella la máquina fiscal) mediante comprobación
  blanda en `self._fields`, de modo que no se crea una dependencia dura de
  `l10n_ve_bw_fiscal_printer`. Si no hay sello, se imprime solo la fecha: nunca
  se genera una hora aproximada en un documento fiscal.
- **Marca «(E)» en líneas exentas, exoneradas y no sujetas** (PA 0071
  arts. 13.8, 14.5 y 32.2; PA SNAT/2024/000102 art. 7.8): predicado
  `account.move.line._l10n_ve_is_exempt()`, verdadero para líneas de producto
  sin ningún impuesto con alícuota. Un único predicado porque la norma marca
  con la misma letra los tres supuestos y no define una letra para las
  gravadas.
- **Fecha de asignación del Nº de control** (PA SNAT/2024/000102 art. 7.15):
  campo `account.move.l10n_ve_control_date` (`copy=False`), rellenable por el
  conector de imprenta digital o transcrito del talonario bajo forma libre. El
  Nº de control en sí (`l10n_ve_control_number`) proviene de
  `l10n_ve_bw_fiscal_books`.
- **Datos de la imprenta autorizada** (PA 0071 arts. 30-31; PA SNAT/2024/000102
  art. 7.14): seis campos en `res.company` como texto libre —razón social
  (`l10n_ve_printer_name`), RIF (`l10n_ve_printer_vat`), número
  (`l10n_ve_printer_auth_number`) y fecha (`l10n_ve_printer_auth_date`) de la
  Providencia del SENIAT que la autoriza, y rango de Nº de control asignado
  (`l10n_ve_control_range_from` / `_to`). Son texto libre a propósito: los
  mismos datos sirven al régimen de imprenta física y al digital, y por eso el
  módulo no depende del conector.
- **Configuración en Contabilidad**: bloque «Localización Venezuela — Imprenta
  Autorizada» en `res.config.settings`, con los seis campos como `related`
  editables y marcado `company_dependent`.
- **Herencia del QWeb de factura** (`report_invoice_document_ve`, sobre
  `account.report_invoice_document`), toda por posición sobre nodos hoja y sin
  reemplazar bloques completos del core:
  - sustituye el nodo de `invoice_date` por la fecha/hora legal del art. 7.6,
    conservando rótulo y columna del core;
  - añade dentro de `#informations` el Nº de control y su fecha de asignación;
  - añade el `(E)` en negrita junto a la descripción de la línea —y no junto al
    precio— por ser la columna que no se corta en formatos angostos;
  - añade tras `#total` el bloque de imprenta autorizada y el rango de control a
    8 pt.
- **Etiqueta «RIF» para Venezuela**: `data/res_country_data.xml` fija
  `vat_label = RIF` en `base.ve`, porque viene vacío y el QWeb del core
  rotularía el RIF del comprador como «Tax ID».
- **Pruebas** (`tests/test_invoice_format.py`, `post_install`): etiqueta RIF del
  país; fecha legal sin hora cuando no hay sello fiscal; fecha legal con sello
  de máquina (se omite si `l10n_ve_bw_fiscal_printer` no está instalado);
  predicado de exención sobre línea gravada, línea con impuesto al 0 % y línea
  sin impuestos; y dos pruebas de renderizado del informe QWeb que verifican la
  marca «(E)», el Nº de control, la fecha y el bloque de imprenta.
