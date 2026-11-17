Facturación del punto de venta sobre papelería fiscal de imprenta autorizada,
para cajas que no tienen máquina fiscal o cuya máquina está caída.

- **Talonario** (PA 0071 art. 11): factura manuscrita. En cada cobro el POS
  pide el Nº de factura y el Nº de control preimpresos y genera la factura en
  el diario de contingencia.
- **Formas libres**: el POS pide el Nº de control de la hoja y factura en el
  diario de la caja (canal libre); el contenido se imprime desde Odoo.
- **Contingencia por sesión**: un gerente la activa con un motivo; queda
  registrado quién y cuándo, el botón queda en rojo toda la jornada y se
  desactiva al cerrar la caja.

Los números propuestos salen del lote de papelería activo
(`l10n.ve.paper.batch`, de `l10n_ve_bw_fiscal_books`), que también valida
rango, duplicados y aviso de agotamiento. La factura en papel exige cliente
identificado y no se puede consolidar con otras órdenes.

El módulo también expone la tasa BCV del día al frontend (`getVesRate`,
`toVes`), que reutiliza `l10n_ve_bw_pos_bs`.
