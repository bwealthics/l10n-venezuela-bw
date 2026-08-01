# Part of l10n_ve_bw_einvoice. License LGPL-3.
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_ve_edoc_state = fields.Selection(
        [("to_send", "Por enviar"),
         ("sent", "Enviado, sin Nº de control"),
         ("assigned", "Nº de control asignado"),
         ("error", "Error"),
         ("cancelled", "Anulado ante la imprenta")],
        string="Estado ante la imprenta digital",
        copy=False, readonly=True, tracking=True,
    )
    l10n_ve_edoc_external_id = fields.Char(
        string="Identificador en la imprenta", copy=False, readonly=True)
    l10n_ve_edoc_error = fields.Text(
        string="Último error de la imprenta", copy=False, readonly=True)

    # ------------------------------------------------------------------
    # Lógica fiscal — 100% escribible sin conocer al proveedor
    # ------------------------------------------------------------------
    def _l10n_ve_edoc_document_vals(self):
        """Documento en un dict NEUTRO, independiente del proveedor.

        Aquí vive todo lo fiscal: qué es base y qué es exento, cómo se parte
        el IVA por alícuota, qué lleva una nota de crédito. El adaptador solo
        renombra campos. Si algún día se cambia de imprenta, esto no se toca.
        """
        self.ensure_one()
        company = self.company_id
        partner = self.commercial_partner_id
        lines = []
        for line in self.invoice_line_ids.filtered(
                lambda ln: ln.display_type == "product"):
            rate = next((tax.amount for tax in line.tax_ids if tax.amount), 0.0)
            lines.append({
                "descripcion": line.name or "",
                "cantidad": line.quantity,
                "precio_unitario": line.price_unit,
                "descuento": line.discount,
                "base": line.price_subtotal,
                "alicuota": rate,
                "exento": line._l10n_ve_is_exempt(),
            })
        vals = {
            "tipo_documento": self._l10n_ve_edoc_doc_type(),
            "numero": self.name,
            "fecha": self.invoice_date,
            "moneda": self.currency_id.name,
            "emisor": {
                "rif": company.vat or "",
                "razon_social": company.name,
                "domicilio": company.street or "",
            },
            "comprador": {
                "rif": partner.vat or "",
                "razon_social": partner.name or "",
                "domicilio": partner.street or "",
                "correo": partner.email or "",
            },
            "lineas": lines,
            "total_exento": sum(
                ln["base"] for ln in lines if ln["exento"]),
            "total_base": sum(
                ln["base"] for ln in lines if not ln["exento"]),
            "total_iva": self.amount_tax,
            "total": self.amount_total,
        }
        # La NC/ND debe referenciar fecha, número y monto del documento
        # afectado (PA 0071 art. 143 y PA 102). La ND es un out_invoice con
        # debit_origin_id — sin esta rama saldría sin la referencia.
        origin = None
        if self.move_type == "out_refund" and self.reversed_entry_id:
            origin = self.reversed_entry_id
        elif "debit_origin_id" in self._fields and self.debit_origin_id:
            origin = self.debit_origin_id
        if origin:
            vals["documento_afectado"] = {
                "numero": origin.name,
                "numero_control": origin.l10n_ve_control_number or "",
                "fecha": origin.invoice_date,
                "monto": origin.amount_total,
            }
        return vals

    def _l10n_ve_edoc_doc_type(self):
        self.ensure_one()
        if self.move_type == "out_refund":
            return "nota_credito"
        if "debit_origin_id" in self._fields and self.debit_origin_id:
            return "nota_debito"
        return "factura"

    # ------------------------------------------------------------------
    # Máquina de estados
    # ------------------------------------------------------------------
    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        # Encolar para la imprenta digital: sin esto ningún documento llega
        # jamás a "to_send" y la rama de envío del cron sería código muerto.
        # Solo con proveedor configurado, para que el cron no reviente.
        for move in posted:
            if (move.is_sale_document(include_receipts=True)
                    and move.journal_id.l10n_ve_emission_channel == "digital"
                    and not move.l10n_ve_edoc_state
                    and move.company_id.l10n_ve_edoc_provider):
                move.l10n_ve_edoc_state = "to_send"
        return posted

    def _l10n_ve_edoc_provider(self):
        self.ensure_one()
        provider = self.company_id.l10n_ve_edoc_provider
        if not provider:
            raise UserError(_(
                "La compañía %s no tiene proveedor de imprenta digital "
                "configurado.", self.company_id.display_name))
        return self.env[provider]

    def action_l10n_ve_edoc_send(self):
        for move in self:
            if move.journal_id.l10n_ve_emission_channel != "digital":
                raise UserError(_(
                    "%s no está en un diario del canal de imprenta digital.",
                    move.display_name))
            if move.state != "posted":
                raise UserError(_("Solo se envían documentos publicados."))
            if move.l10n_ve_edoc_state in ("sent", "assigned"):
                raise UserError(_(
                    "%s ya fue enviado a la imprenta digital.",
                    move.display_name))
            move._l10n_ve_edoc_do_send()
        return True

    def _l10n_ve_edoc_do_send(self):
        self.ensure_one()
        provider = self._l10n_ve_edoc_provider()
        vals = self._l10n_ve_edoc_document_vals()
        try:
            result = provider._edoc_send(self, vals)
        except Exception as error:  # noqa: BLE001 — el error del proveedor se
            # registra y se muestra; nunca debe tumbar la transacción contable.
            self._l10n_ve_edoc_log("send", vals, str(error), ok=False)
            self.write({
                "l10n_ve_edoc_state": "error",
                "l10n_ve_edoc_error": str(error),
            })
            return False
        self._l10n_ve_edoc_log("send", vals, result, ok=True)
        self._l10n_ve_edoc_apply(result)
        return True

    def _l10n_ve_edoc_apply(self, result):
        """Aplica la respuesta del proveedor. El Nº de control se escribe con
        el contexto de write-back: la imprenta es un origen legítimo y el
        guard de l10n_ve_bw_fiscal_books lo exige explícito."""
        self.ensure_one()
        number = result.get("control_number")
        values = {
            "l10n_ve_edoc_external_id": result.get("external_id"),
            "l10n_ve_edoc_error": False,
            "l10n_ve_edoc_state": "assigned" if number else "sent",
        }
        if number:
            values["l10n_ve_control_number"] = number
            values["l10n_ve_control_date"] = (
                result.get("control_date") or fields.Date.context_today(self))
        self.with_context(l10n_ve_control_writeback=True).write(values)

    def action_l10n_ve_edoc_fetch(self):
        """Consulta el Nº de control de los documentos ya enviados.

        Solo hace falta con proveedores asíncronos. Con The Factory HKA, que
        devuelve el número en la propia emisión, esto no llega a usarse.
        """
        for move in self.filtered(lambda m: m.l10n_ve_edoc_state == "sent"):
            provider = move._l10n_ve_edoc_provider()
            try:
                result = provider._edoc_fetch(move)
            except Exception as error:  # noqa: BLE001
                move._l10n_ve_edoc_log("fetch", {}, str(error), ok=False)
                continue
            move._l10n_ve_edoc_log("fetch", {}, result, ok=True)
            if result.get("control_number"):
                move._l10n_ve_edoc_apply(result)
        return True

    def _l10n_ve_edoc_log(self, endpoint, request, response, ok):
        self.ensure_one()
        self.env["l10n.ve.edoc.log"].sudo().create({
            "move_id": self.id,
            "endpoint": endpoint,
            "request": repr(request),
            "response": repr(response),
            "ok": ok,
        })

    def _l10n_ve_edoc_cron(self):
        """Envía los pendientes y consulta los asíncronos. UN solo cron para
        las dos cosas: la mitad de código y ningún problema de orden."""
        moves = self.search([("l10n_ve_edoc_state", "in", ("to_send", "sent"))])
        for move in moves.filtered(
                lambda m: m.l10n_ve_edoc_state == "to_send"
                and m.company_id.l10n_ve_edoc_provider):
            move._l10n_ve_edoc_do_send()
        moves.filtered(
            lambda m: m.l10n_ve_edoc_state == "sent").action_l10n_ve_edoc_fetch()
