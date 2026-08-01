# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

RECEIVED_VOUCHER_RE = re.compile(r"^\d{4}(0[1-9]|1[0-2])\d{8}$")


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    l10n_ve_company_is_spe = fields.Boolean(
        related="company_id.l10n_ve_is_spe",
    )
    # --- A) Sujeto retenido: un cliente SPE nos retiene IVA al pagarnos ---
    l10n_ve_iva_wh_received_amount = fields.Monetary(
        string="IVA Retenido por el Cliente",
        currency_field="currency_id",
        default=0.0,
        help="Monto de IVA que el cliente (agente de retención) retuvo según "
             "el comprobante entregado. Se descuenta del cobro y se registra "
             "en la cuenta de Retenciones de IVA Recibidas de Clientes.",
    )
    l10n_ve_iva_wh_voucher_number = fields.Char(
        string="Número de Comprobante Recibido",
        size=14,
        help="Numeración de 14 caracteres del comprobante de retención del "
             "cliente: AAAAMM + secuencial de 8 dígitos.",
    )
    # --- B) Agente de retención: retenemos IVA al pagar a proveedores ---
    l10n_ve_iva_wh_amount = fields.Monetary(
        string="IVA a Retener al Proveedor",
        currency_field="currency_id",
        compute="_compute_l10n_ve_iva_wh_amount",
        store=True,
        readonly=False,
        help="Retención de IVA (PA SNAT/2025/000054) calculada sobre el IVA "
             "de las facturas publicadas según el porcentaje del proveedor. "
             "Se prorratea en pagos parciales y descuenta lo ya retenido en "
             "comprobantes previos de los mismos documentos. Editable.",
    )

    @api.constrains("l10n_ve_iva_wh_voucher_number")
    def _check_l10n_ve_iva_wh_voucher_number(self):
        for wizard in self:
            number = wizard.l10n_ve_iva_wh_voucher_number
            if number and not RECEIVED_VOUCHER_RE.match(number):
                raise ValidationError(_(
                    "El número de comprobante de retención debe tener 14 dígitos: "
                    "AAAAMM + secuencial de 8 dígitos (ej. 20260700000001)."
                ))

    @api.depends(
        "line_ids", "amount", "currency_id", "payment_date",
        "partner_id", "company_id", "can_edit_wizard", "group_payment",
    )
    def _compute_l10n_ve_iva_wh_amount(self):
        for wizard in self:
            wizard.l10n_ve_iva_wh_amount = wizard._l10n_ve_get_iva_wh_agent_amount()

    def _l10n_ve_get_iva_wh_agent_amount(self):
        """IVA a retener en este pago, en la moneda del wizard.

        Se calcula sobre ``self.amount`` tal cual (nunca se muta el monto del
        wizard) para que la base sea correcta e independiente de otros módulos
        de retención instalados. Prorratea por el total ORIGINAL de los
        documentos (no el residual) y descuenta lo ya retenido en comprobantes
        publicados previos de los mismos documentos, de modo que pagos
        parciales sucesivos nunca retengan de más.
        """
        self.ensure_one()
        company = self.company_id
        partner = self.partner_id.commercial_partner_id
        if (
            self.payment_type != "outbound"
            or self.partner_type != "supplier"
            or not self.can_edit_wizard
            or not partner
            or not company.l10n_ve_is_spe
        ):
            return 0.0
        # Solo aplica en modo editable real (un documento o pago agrupado):
        # es el único caso donde el write-off del wizard llega al pago.
        batches = self.batches
        if not batches or (len(batches[0]["lines"]) > 1 and not self.group_payment):
            return 0.0
        if (
            company.l10n_ve_spe_date
            and self.payment_date
            and self.payment_date < company.l10n_ve_spe_date
        ):
            return 0.0
        # Exclusión art. 3: operaciones entre agentes de retención designados.
        if partner.l10n_ve_taxpayer_type == "especial":
            return 0.0
        # Sin RIF no puede emitirse el comprobante ni declararse la 99035.
        if not partner.vat:
            return 0.0
        rate = float(partner.l10n_ve_wh_iva_rate or "0")
        if not rate:
            return 0.0
        # Solo facturas PUBLICADAS: el flujo core de pago sobre borradores
        # (is_register_payment_on_draft) sigue libre, sin retención.
        moves = self.line_ids.move_id.filtered(
            lambda m: m.is_invoice(include_receipts=True) and m.state == "posted"
        )
        if not moves or not self.currency_id:
            return 0.0
        company_currency = company.currency_id
        Voucher = self.env["l10n.ve.iva.wh.voucher"]
        tax_total = 0.0      # IVA causado neto (NC restan), moneda compañía
        pending_total = 0.0  # IVA pendiente de retener, moneda compañía
        for move in moves:
            tax = Voucher._l10n_ve_move_iva_amounts(move)["tax"]
            if company_currency.is_zero(tax):
                continue
            if move.move_type in ("in_refund", "out_refund"):
                tax_total -= tax
                continue
            tax_total += tax
            theoretical = company_currency.round(tax * rate / 100.0)
            previous_vouchers = Voucher.search([
                ("company_id", "=", company.id),
                ("state", "=", "posted"),
                ("move_ids", "in", move.id),
            ])
            already_withheld = sum(
                voucher._l10n_ve_get_amount_for_move(move)
                for voucher in previous_vouchers
            )
            pending_total += max(0.0, theoretical - already_withheld)
        if company_currency.compare_amounts(tax_total, 0.0) <= 0:
            return 0.0
        date = self.payment_date or fields.Date.context_today(self)
        tax_total_wc = company_currency._convert(
            tax_total, self.currency_id, company, date,
        )
        pending_wc = company_currency._convert(
            pending_total, self.currency_id, company, date,
        )
        total_docs_wc = self._l10n_ve_get_docs_total_in_wizard_currency(moves, date)
        if not total_docs_wc:
            return 0.0
        factor = min(1.0, max(0.0, self.amount / total_docs_wc))
        wh = min(tax_total_wc * rate / 100.0 * factor, pending_wc)
        return max(0.0, self.currency_id.round(wh))

    def _l10n_ve_get_docs_total_in_wizard_currency(self, moves, date):
        """Total ORIGINAL (neto de NC) de los documentos, en moneda del wizard."""
        self.ensure_one()
        total_cc = abs(sum(moves.mapped("amount_total_signed")))
        if self.currency_id == self.company_currency_id:
            return total_cc
        return self.company_currency_id._convert(
            total_cc, self.currency_id, self.company_id, date,
        )

    # -------------------------------------------------------------------------
    # CONFIRMACIÓN
    # -------------------------------------------------------------------------

    def _l10n_ve_iva_wh_get_values(self):
        """Retención de IVA aplicable a este pago, validada y SIN efectos
        secundarios (no muta el wizard ni consume secuencias).

        Devuelve {} si no aplica, o un dict con:
        - direction: 'received' (cliente SPE nos retuvo) o 'agent' (retenemos)
        - wh: monto de la retención en la moneda del wizard (> 0)
        - account: cuenta contable del write-off
        - label: etiqueta de la línea de write-off
        """
        self.ensure_one()
        received = self.l10n_ve_iva_wh_received_amount
        agent_wh = self.l10n_ve_iva_wh_amount
        is_received_case = (
            self.payment_type == "inbound"
            and self.partner_type == "customer"
            and received
        )
        is_agent_case = (
            self.payment_type == "outbound"
            and self.partner_type == "supplier"
            and agent_wh
        )
        if not is_received_case and not is_agent_case:
            return {}

        edit_mode = self.can_edit_wizard and (
            len(self.batches[0]["lines"]) == 1 or self.group_payment
        )
        if not edit_mode:
            raise UserError(_(
                "Para aplicar retención de IVA registre un solo pago agrupado "
                "(active «Agrupar pagos» o pague las facturas una a una)."
            ))
        if self.is_register_payment_on_draft:
            raise UserError(_(
                "No se puede aplicar retención de IVA sobre documentos en borrador: "
                "publique las facturas antes de registrar el pago."
            ))

        if is_received_case:
            if received < 0:
                raise UserError(_("El IVA retenido por el cliente no puede ser negativo."))
            if not self.l10n_ve_iva_wh_voucher_number:
                raise UserError(_(
                    "Indique el número del comprobante de retención recibido "
                    "(14 dígitos: AAAAMM + 8)."
                ))
            account = self.company_id.l10n_ve_iva_wh_received_account_id
            if not account:
                raise UserError(_(
                    "Configure la cuenta de Retenciones de IVA Recibidas de Clientes "
                    "en Ajustes > Contabilidad > Localización Venezuela."
                ))
            wh = self.currency_id.round(received)
            label = _("Ret. IVA recibida comprobante %s", self.l10n_ve_iva_wh_voucher_number)
            direction = "received"
        else:
            if agent_wh < 0:
                raise UserError(_("La retención de IVA al proveedor no puede ser negativa."))
            account = self.company_id.l10n_ve_iva_wh_agent_account_id
            if not account:
                raise UserError(_(
                    "Configure la cuenta de Retenciones de IVA por Enterar (Agente) "
                    "en Ajustes > Contabilidad > Localización Venezuela."
                ))
            partner = self.partner_id.commercial_partner_id
            if not partner.vat:
                raise UserError(_(
                    "El proveedor %s no tiene RIF configurado (campo NIF): "
                    "no puede practicarse la retención de IVA ni emitirse el "
                    "comprobante (Forma 99035).",
                    partner.display_name,
                ))
            wh = self.currency_id.round(agent_wh)
            label = _(
                "Ret. IVA %(rate)s%% %(partner)s",
                rate=partner.l10n_ve_wh_iva_rate or "0",
                partner=partner.name,
            )
            direction = "agent"

        if self.currency_id.compare_amounts(wh, self.amount) >= 0:
            raise UserError(_(
                "La retención de IVA (%(wh)s) no puede ser mayor o igual al monto "
                "del pago (%(amount)s).",
                wh=wh, amount=self.amount,
            ))
        if self.currency_id.is_zero(wh):
            return {}
        return {"direction": direction, "wh": wh, "account": account, "label": label}

    def _create_payment_vals_from_wizard(self, batch_result):
        """Inyecta la retención como línea PROPIA de write-off del pago.

        No se muta ``self.amount`` ni se tocan ``payment_difference_handling``
        / ``writeoff_account_id`` / ``writeoff_label``: así este módulo puede
        convivir con otros módulos de retención sobre el mismo pago (cada uno
        aporta su línea) y en pagos parciales el resto de la factura queda
        abierto de forma natural (handling 'open' del core).
        """
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        wh_values = self._l10n_ve_iva_wh_get_values()
        if not wh_values:
            return payment_vals
        wh = wh_values["wh"]
        payment_vals["amount"] -= wh
        # Guard cruzado (orden de super() indiferente): otras retenciones ya
        # pudieron reducir el monto del dict; la suma no puede agotar el pago.
        if self.currency_id.compare_amounts(payment_vals["amount"], 0.0) <= 0:
            raise UserError(_(
                "Las retenciones combinadas del pago agotan o exceden su monto "
                "(monto restante: %(amount)s). Revise los montos de retención "
                "editados manualmente.", amount=payment_vals["amount"]))
        # Misma lógica de signos que el write-off del core cuando
        # payment_difference_handling == 'reconcile' (account_payment_register).
        if self.payment_type == "inbound":
            # Receive money.
            write_off_amount_currency = wh
        else:  # if self.payment_type == 'outbound':
            # Send money.
            write_off_amount_currency = -wh
        payment_vals.setdefault("write_off_line_vals", []).append({
            "name": wh_values["label"],
            "account_id": wh_values["account"].id,
            "partner_id": self.partner_id.commercial_partner_id.id,
            "currency_id": self.currency_id.id,
            "amount_currency": write_off_amount_currency,
            "balance": self.currency_id._convert(
                write_off_amount_currency,
                self.company_id.currency_id,
                self.company_id,
                self.payment_date,
            ),
        })
        if wh_values["direction"] == "received":
            # Persistidos en el pago para que los libros fiscales reporten la
            # retención recibida por factura.
            payment_vals["l10n_ve_iva_wh_received_amount"] = wh
            payment_vals["l10n_ve_iva_wh_received_number"] = (
                self.l10n_ve_iva_wh_voucher_number
            )
        return payment_vals

    def _create_payments(self):
        self.ensure_one()
        # Validación temprana (la misma que aplicará el builder de vals),
        # sin efectos secundarios sobre el wizard.
        wh_values = self._l10n_ve_iva_wh_get_values()
        payments = super()._create_payments()
        if wh_values and wh_values["direction"] == "agent":
            self._l10n_ve_create_iva_wh_voucher(payments, wh_values)
        return payments

    def _l10n_ve_create_iva_wh_voucher(self, payments, wh_values):
        self.ensure_one()
        company = self.company_id
        Voucher = self.env["l10n.ve.iva.wh.voucher"]
        moves = self.line_ids.move_id.filtered(
            lambda m: m.is_invoice(include_receipts=True) and m.state == "posted"
        )
        base = exempt = tax = 0.0
        for move in moves:
            amounts = Voucher._l10n_ve_move_iva_amounts(move)
            # Las NC restan: la retención se calculó sobre el IVA NETO
            # (_l10n_ve_get_iva_wh_agent_amount), así que los totales del
            # comprobante deben netear igual o el 99035 queda sobredeclarado.
            sign = -1.0 if move.move_type in ("in_refund", "out_refund") else 1.0
            base += sign * amounts["base"]
            exempt += sign * amounts["exempt"]
            tax += sign * amounts["tax"]
        withheld_company = self.currency_id._convert(
            wh_values["wh"], company.currency_id, company, self.payment_date,
        )
        partner = self.partner_id.commercial_partner_id
        number = Voucher._l10n_ve_next_voucher_number(
            self.payment_date, company=company,
        )
        return Voucher.create({
            "number": number,
            "date": self.payment_date,
            "company_id": company.id,
            "partner_id": partner.id,
            "payment_id": payments[:1].id,
            "move_ids": [Command.set(moves.ids)],
            "base_amount": base,
            "tax_amount": tax,
            "withheld_amount": withheld_company,
            "exempt_amount": exempt,
            "wh_rate": float(partner.l10n_ve_wh_iva_rate or "0"),
            "state": "posted",
        })
