# Localización de Venezuela para Odoo 19 (suite `l10n_ve_bw`)

Suite modular de cumplimiento fiscal y laboral venezolano para **Odoo 19.0**,
desarrollada y mantenida por [BWEALTHICS LLC](https://www.bwealthics.com).

> ⚠️ **Aviso legal.** Este software es una herramienta de apoyo. No constituye
> asesoría fiscal ni contable, no está certificado ni avalado por el SENIAT ni
> por ningún organismo del Estado venezolano, y no garantiza por sí solo el
> cumplimiento de obligación tributaria alguna. La responsabilidad de las
> declaraciones, comprobantes y libros que se emitan con él es del contribuyente
> y de su profesional contable. Las referencias a SENIAT, Gaceta Oficial y a
> marcas de terceros (The Factory HKA, ACLAS, BCV) son descriptivas y no implican
> afiliación ni respaldo.

## Módulos

| Módulo | Qué resuelve | Norma base | Licencia |
|---|---|---|---|
| `l10n_ve_bw_chart` | Plan de cuentas de 6 dígitos (VEN-NIF), impuestos de IVA, marca de Sujeto Pasivo Especial y tipo de contribuyente | BA VEN-NIF Nº 0 · LIVA | LGPL-3 |
| `l10n_ve_bw_igtf` | IGTF: gasto propio al pagar en divisas y percepción del 3 % como SPE | Ley IGTF (reforma G.O.E. 6.687, 2022) · Decreto 4.972 | LGPL-3 |
| `l10n_ve_bw_wh_iva` | Retención de IVA en ambas direcciones, comprobante AAAAMM+8 y TXT forma 99035 | PA SNAT/2025/000054 | LGPL-3 |
| `l10n_ve_bw_wh_islr` | Retenciones de ISLR, Unidad Tributaria histórica, comprobante y XML mensual | Decreto 1.808 · PA 0095/2009 | LGPL-3 |
| `l10n_ve_bw_municipal` | Provisión mensual de patente de industria y comercio (alícuota, mínimo tributable en veces MMV) | Ordenanzas municipales · LOPPM | LGPL-3 |
| `l10n_ve_bw_fiscal_books` | Libros de Compras y Ventas en XLSX, Nº de control, canal de emisión por diario, contingencia | Reglamento LIVA arts. 70–78 · PA 0071 | LGPL-3 |
| `l10n_ve_bw_invoice_format` | Requisitos de forma del comprobante en el PDF (fecha/hora legal, marca «(E)», datos de imprenta) | PA 0071 · PA SNAT/2024/000102 | LGPL-3 |
| `l10n_ve_bw_einvoice` | Conector de imprenta digital autorizada (núcleo + proveedor simulado) | PA SNAT/2024/000102 · PA 000121 | LGPL-3 |
| `l10n_ve_bw_fiscal_printer` | Máquina fiscal en el POS vía bridge local (protocolo HKA) | PA 0071 (reporte Z) | LGPL-3 |
| `l10n_ve_bw_compliance` | Paraguas: instala la suite y deja el audit log **suscrito** | PA SNAT/2024/000102 art. 18.7 | **AGPL-3** |
| `l10n_ve_bw_payroll` | Nómina VE: IVSS, RPE, FAOV, INCES, ISLR (AR-I), CEPP, cesta ticket, recibo bimonetario | LOTTT · leyes de seguridad social | LGPL-3 |

### Dos advertencias sobre licencias y dependencias

- **`l10n_ve_bw_compliance` es AGPL-3 y no es una elección**: depende de OCA
  `auditlog` (AGPL-3). Por eso el audit log vive aislado en ese módulo y el resto
  de la suite se mantiene LGPL-3, para que pueda combinarse libremente con
  addons propietarios.
- **`l10n_ve_bw_payroll` requiere Odoo 19 Enterprise** (`hr_payroll_account`).
  El código publicado aquí es LGPL-3, pero no funciona sobre Odoo Community y no
  es candidato a los repositorios de la OCA, que solo aceptan módulos que
  instalen sobre Community.

## Instalación

```bash
git clone https://github.com/<org>/l10n-venezuela-bw.git
```

Añade el directorio al `addons_path`, reinicia Odoo y actualiza la lista de
aplicaciones. Para dejar el ERP en condiciones de cumplimiento en un paso,
instala `l10n_ve_bw_compliance` (requiere `OCA/server-tools` rama 19.0 en el
`addons_path`).

Dependencias Python: `xlsxwriter`.

## Documentación

- [Manual de la localización](docs/MANUAL-LOCALIZACION-VE.md) — qué hace cada
  módulo, cómo se configura y cómo se opera mes a mes.
- [Basamento legal](docs/BASAMENTO-LEGAL.md) — norma por norma, con la decisión
  de diseño que produjo en el código y los puntos abiertos.

## Estado y soporte

Este repositorio se publica **tal cual**, como aporte a la comunidad. Se aceptan
issues y pull requests, sin compromiso de tiempo de respuesta. Para
implementación asistida: [bwealthics.com](https://www.bwealthics.com).

## Cambios

Cada módulo lleva su propio `CHANGELOG.md`, con el versionado de Odoo
(`19.0.MAJOR.MINOR.PATCH`).

## Reportar un cambio normativo

Cuando el SENIAT, una ordenanza o una ley reforman algo que esta suite
implementa, ábrelo como
[reporte de cambio normativo](../../issues/new?template=cambio-normativo.yml):
la plantilla pide la Gaceta, la fecha de vigencia y los módulos afectados, que
es lo que hace falta para actuar sin investigar de cero.

## Licencia

Copyright 2026 BWEALTHICS LLC.

LGPL-3, salvo `l10n_ve_bw_compliance` (AGPL-3). Cada módulo declara su licencia
en su `__manifest__.py`. Ver [LICENSE](LICENSE) y
[LICENSE.AGPL-3](LICENSE.AGPL-3).
