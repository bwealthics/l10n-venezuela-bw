Venezuela — Plan de Cuentas BWEALTHICS (6 dígitos)
==================================================

Chart template ``ve_bw`` para Odoo 19.0:

* 167 cuentas imputables de 6 dígitos (clases 1 Activo, 2 Pasivo, 3 Patrimonio,
  4 Ingresos, 5 Costos, 6 Gastos), alineadas a VEN-NIF.
* Grupos de cuenta en tres niveles (prefijos de 1, 2 y 4 dígitos).
* Impuestos de IVA para ventas y compras: 16% general, 8% reducida,
  31% (general + adicional), 0% exportación y Exento.
* Campos de compañía ``l10n_ve_is_spe`` / ``l10n_ve_spe_date`` (Sujeto Pasivo
  Especial) expuestos en Ajustes de Contabilidad — los consumen los módulos
  ``l10n_ve_bw_igtf`` y ``l10n_ve_bw_wh_iva``.
* Campo de contacto ``l10n_ve_taxpayer_type`` (tipo de contribuyente).

Instalación: se carga con
``env["account.chart.template"].try_loading("ve_bw", company, install_demo=False)``
o seleccionando el paquete de localización de Venezuela (BWEALTHICS) en Ajustes.

Autor: BWEALTHICS LLC — Licencia LGPL-3.
