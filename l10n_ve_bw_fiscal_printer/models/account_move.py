# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_printer. License LGPL-3.
from odoo import _, fields, models
from odoo.exceptions import UserError

SUPPORTED_RATES = (0, 8, 16, 31)


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_ve_fiscal_number = fields.Char(
        string="Nº factura fiscal", copy=False, readonly=True)
    l10n_ve_fiscal_machine_serial = fields.Char(
        string="Serial máquina fiscal", copy=False, readonly=True)
    l10n_ve_fiscal_date = fields.Char(
        string="Fecha/hora fiscal", copy=False, readonly=True)
    l10n_ve_fiscal_doc_type = fields.Selection(
        [("invoice", "Factura"), ("credit_note", "Nota de crédito")],
        string="Tipo de documento fiscal", copy=False, readonly=True)

    @staticmethod
    def _l10n_ve_rate_pct(taxes):
        """Alícuota de máquina (0/8/16/31) más cercana al total de impuestos
        de la línea — espejo de _rate_key del Libro de Ventas."""
        amount = sum(taxes.mapped("amount")) if taxes else 0.0
        return min(SUPPORTED_RATES, key=lambda r: abs(r - amount))

    def _l10n_ve_get_bridge_config(self):
        configs = self.env["pos.config"].search([
            ("l10n_ve_bridge_url", "!=", False),
            ("company_id", "=", self.company_id.id)])
        if not configs:
            raise UserError(_(
                "Ninguna caja de esta compañía tiene configurado el bridge "
                "fiscal (Punto de Venta > Ajustes > Localización Venezuela)."))
        if len(configs) > 1:
            # Todas las URLs son "localhost": con varias cajas no se sabe qué
            # máquina imprimirá; el serial registrado quedaría equivocado.
            raise UserError(_(
                "Hay varias cajas con bridge fiscal (%s): imprima desde el POS "
                "de la caja correspondiente o deje una sola configurada.")
                % ", ".join(configs.mapped("name")))
        return configs

    def _l10n_ve_build_payload(self, config):
        self.ensure_one()
        ves = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "VES")], limit=1)
        if not ves:
            raise UserError(_("No existe la moneda VES en el sistema."))
        if config.l10n_ve_get_ves_rate() <= 0:
            raise UserError(_(
                "No hay tasa BCV cargada para VES: sin tasa del día no se "
                "puede imprimir fiscal."))
        company, today = self.company_id, fields.Date.context_today(self)

        def to_ves(amount):
            return round(self.currency_id._convert(amount, ves, company, today), 2)

        items = []
        for line in self.invoice_line_ids.filtered(
                lambda l: l.display_type == "product" and l.quantity):
            if line.price_total < 0:
                raise UserError(_(
                    "La máquina fiscal no imprime líneas negativas (%s): "
                    "aplique el descuento en el precio de las líneas.")
                    % (line.name or line.product_id.name))
            qty = line.quantity
            items.append({
                "descripcion": (line.product_id.name or line.name or "")[:40],
                "precio": round(to_ves(line.price_total) / qty, 2),
                "cantidad": qty,
                "iva_porcentaje": self._l10n_ve_rate_pct(line.tax_ids),
            })
        if not items:
            raise UserError(_("El documento no tiene líneas de producto."))
        # La máquina totaliza Σ(precio × cantidad) con los precios YA
        # redondeados: total y pago declarado deben salir de ESA aritmética
        # o el cierre falla por centavos.
        total = round(sum(it["precio"] * it["cantidad"] for it in items), 2)
        expected = to_ves(self.amount_total)
        if abs(total - expected) > 0.01 * len(items) + 0.02:
            raise UserError(_(
                "El total según la máquina (Bs %(maquina)s) difiere del de la "
                "factura (Bs %(odoo)s): revise líneas con descuentos o "
                "cantidades fraccionadas.",
                maquina=total, odoo=expected))
        payload = {
            "uuid": "move-%s" % self.id,
            "cliente_nombre": (self.partner_id.name or "CONSUMIDOR FINAL")[:38],
            "cliente_rif": (self.partner_id.vat or "").replace("-", "").upper(),
            "serial_impresora": config.l10n_ve_machine_serial or "",
            "tasa_dolar": config.l10n_ve_get_ves_rate(),
            "monto_total": total,
            # ponytail: al facturar aún no se conocen los pagos; IGTF de
            # percepción aplica en cobros POS, no en esta impresión backend.
            "monto_igtf": 0,
            "items": items,
            "pagos": [{"metodo": config.l10n_ve_default_payment_code or "01",
                       "monto": total}],
        }
        if self.move_type == "out_refund":
            origin = self.reversed_entry_id
            if not origin or not origin.l10n_ve_fiscal_number:
                raise UserError(_(
                    "La factura original no tiene número fiscal registrado; "
                    "la nota de crédito debe emitirse manualmente en la máquina."))
            raw = (origin.l10n_ve_fiscal_date or "")[:10]
            date_orig = fields.Date.to_date(raw) if raw else origin.invoice_date
            payload.update({
                "numero_factura_afectada": origin.l10n_ve_fiscal_number,
                "serial_afectada": origin.l10n_ve_fiscal_machine_serial or "",
                "fecha_afectada": date_orig.strftime("%d%m%Y") if date_orig else "",
            })
        return payload

    def action_l10n_ve_print_fiscal(self):
        """Devuelve la client action que hace el fetch al bridge DESDE EL
        NAVEGADOR (solo funciona en la PC donde corre el bridge)."""
        self.ensure_one()
        if self.move_type not in ("out_invoice", "out_refund") or self.state != "posted":
            raise UserError(_("Solo facturas o notas de crédito de cliente publicadas."))
        if self.l10n_ve_fiscal_number:
            raise UserError(_("Este documento ya tiene número fiscal (%s).")
                            % self.l10n_ve_fiscal_number)
        config = self._l10n_ve_get_bridge_config()
        doc_type = "credit_note" if self.move_type == "out_refund" else "invoice"
        return {
            "type": "ir.actions.client",
            "tag": "l10n_ve_bw_fiscal_printer.print_fiscal",
            "params": {
                "move_id": self.id,
                "doc_type": doc_type,
                "endpoint": "/print-credit-note" if doc_type == "credit_note"
                            else "/print-invoice",
                "bridge_url": config.l10n_ve_bridge_url,
                "bridge_token": config.l10n_ve_bridge_token or "",
                "machine_serial": config.l10n_ve_machine_serial or "",
                "payload": self._l10n_ve_build_payload(config),
            },
        }

    def l10n_ve_set_fiscal_result(self, number, serial, doc_type):
        """Write-back del resultado del bridge (lo llama la client action)."""
        self.ensure_one()
        if self.l10n_ve_fiscal_number and self.l10n_ve_fiscal_number != number:
            # Doble impresión (dos usuarios / action re-disparada): nunca
            # pisar un correlativo ya registrado — quedaría un número de
            # máquina sin rastro en Odoo.
            raise UserError(_(
                "Este documento ya tiene el número fiscal %(actual)s; el nuevo "
                "%(nuevo)s NO se registró — verifique la máquina y repórtelo.",
                actual=self.l10n_ve_fiscal_number, nuevo=number))
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        # La máquina es un origen legítimo del Nº de control: el contexto lo
        # declara y así el guard de l10n_ve_bw_fiscal_books no lo bloquea
        # cuando el diario está marcado con canal 'mf'.
        self.with_context(l10n_ve_control_writeback=True).write({
            "l10n_ve_fiscal_number": number,
            "l10n_ve_fiscal_machine_serial": serial,
            "l10n_ve_fiscal_date": stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "l10n_ve_fiscal_doc_type": doc_type,
            "l10n_ve_control_number": self.l10n_ve_control_number or number,
        })
        self.message_post(body=_(
            "Documento fiscal impreso: Nº %(num)s, máquina %(serial)s.",
            num=number, serial=serial))
        return True
