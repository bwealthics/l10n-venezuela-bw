# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_printer. License LGPL-3.
from odoo import _, fields, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    # Campos almacenados PLANOS: pos.order no define _load_pos_data_fields
    # (carga todos) y la serialización del POS 19 solo devuelve al servidor
    # campos almacenados no compute/related — así viajan en el primer sync.
    l10n_ve_fiscal_number = fields.Char(
        string="Nº factura fiscal", copy=False, readonly=True)
    l10n_ve_fiscal_machine_serial = fields.Char(
        string="Serial máquina fiscal", copy=False, readonly=True)
    # Char: sello textual local del momento de impresión (dato legal, sin
    # ambigüedad de zona horaria al reconstruir una NC).
    l10n_ve_fiscal_date = fields.Char(
        string="Fecha/hora fiscal", copy=False, readonly=True)
    l10n_ve_fiscal_doc_type = fields.Selection(
        [("invoice", "Factura"), ("credit_note", "Nota de crédito")],
        string="Tipo de documento fiscal", copy=False, readonly=True)
    # Bitácora de las decisiones HUMANAS que reasignan un correlativo fiscal
    # (adoptar el último ticket tras un timeout, reimprimir, ir a
    # contingencia). Son campos planos y los escribe el frontend: una RPC
    # fallaría justo cuando importa, que es con la caja sin conexión.
    l10n_ve_fiscal_event = fields.Selection(
        [("adopt_uuid", "Nº adoptado por UUID"),
         ("adopt_manual", "Nº adoptado por confirmación del cajero"),
         ("reprint", "Reimpresión tras intento fallido"),
         ("contingency", "Emitida en contingencia"),
         ("blocked", "Venta bloqueada por la máquina")],
        string="Incidencia fiscal", copy=False, readonly=True)
    l10n_ve_fiscal_event_note = fields.Text(
        string="Bitácora de la incidencia", copy=False, readonly=True)

    def _create_invoice(self, move_vals):
        # El Nº de control de estos vals lo puso ESTE módulo desde la máquina
        # fiscal o el talonario de contingencia (_prepare_invoice_vals):
        # mismo origen de confianza que l10n_ve_set_fiscal_result. Sin el
        # contexto, el guard de create de l10n_ve_bw_fiscal_books bloquearía
        # la facturación de una orden cuyo ticket fiscal YA se imprimió.
        if move_vals.get("l10n_ve_control_number"):
            order = self.with_context(l10n_ve_control_writeback=True)
            return super(PosOrder, order)._create_invoice(move_vals)
        return super()._create_invoice(move_vals)

    def _prepare_invoice_vals(self):
        # Guard ANTES del super: sin partner, el core revienta en
        # address_get() con un error críptico. Aplica solo a cajas en modo
        # papel (art. 13.7 PA 0071: la factura sobre formatos identifica al
        # adquirente como mínimo con su cédula — no existe el genérico
        # "consumidor final" de los tickets de máquina fiscal). Cubre órdenes
        # que llegan por IndexedDB sin pasar por la captura del frontend.
        if (len(self) == 1 and not self.partner_id
                and self.session_id.config_id.l10n_ve_paper_mode):
            raise UserError(_(
                "La factura en papel exige identificar al adquirente con "
                "nombre y cédula o RIF (PA 0071 art. 13): asigne el cliente "
                "a la orden %s antes de facturar.", self.name))
        vals = super()._prepare_invoice_vals()
        if len(self) != 1:
            # Factura consolidada (pos.make.invoice sobre varias órdenes): un
            # solo account.move no puede llevar el correlativo fiscal de
            # varios tickets. Si alguna orden ya tiene documento fiscal
            # (máquina o talonario), consolidarla lo dejaría fuera del Libro
            # de Ventas y descuadraría contra el Reporte Z: cada una debe
            # facturarse por separado con su propio Nº.
            fiscal_orders = self.filtered(
                lambda o: o.l10n_ve_fiscal_number
                or o.l10n_ve_contingency_control)
            if fiscal_orders:
                raise UserError(_(
                    "No se puede emitir una factura consolidada: las órdenes "
                    "%(orders)s ya tienen documento fiscal (ticket de máquina "
                    "fiscal o talonario de contingencia). Facture cada una por "
                    "separado para conservar su Nº de control.",
                    orders=", ".join(fiscal_orders.mapped("name")),
                ))
            return vals
        config = self.session_id.config_id
        if self.l10n_ve_contingency_control and config.l10n_ve_paper_mode == "libre":
            # Formas libres: el control preimpreso de la hoja viaja en el
            # mismo campo plano de la orden (es el único slot que sincroniza
            # desde el POS), pero la factura va al diario NORMAL de la caja
            # (canal libre, write-once) y el Nº de factura lo asigna la
            # secuencia del diario.
            vals.update({
                "l10n_ve_control_number": self.l10n_ve_contingency_control,
                "ref": "Forma libre C-%s" % self.l10n_ve_contingency_control,
            })
            return vals
        if self.l10n_ve_contingency_control:
            # Venta facturada a mano en el talonario: va a su propio diario,
            # que no lleva cadena de hash porque replica un papel que ya
            # existe. Nº de control y Nº de factura son los del formato
            # preimpreso; el Libro de Ventas usa el segundo como Nº de
            # documento.
            journal = config.l10n_ve_contingency_journal_id
            paper = self.l10n_ve_contingency_invoice_number
            ref = ("Contingencia F-%s C-%s"
                   % (paper, self.l10n_ve_contingency_control)
                   if paper
                   else "Contingencia %s" % self.l10n_ve_contingency_control)
            vals.update({
                "journal_id": journal.id,
                "l10n_ve_control_number": self.l10n_ve_contingency_control,
                "l10n_ve_paper_number": paper or False,
                "ref": ref,
            })
            return vals
        if self.l10n_ve_fiscal_number:
            # Slot que ya lee el Libro de Ventas (l10n_ve_bw_fiscal_books)
            vals["l10n_ve_control_number"] = self.l10n_ve_fiscal_number
            vals["ref"] = "MF %s Nº %s" % (
                self.l10n_ve_fiscal_machine_serial or "", self.l10n_ve_fiscal_number)
            # Copia íntegra a la factura: una NC backend de esta factura
            # encuentra aquí los datos de la máquina.
            vals.update({
                "l10n_ve_fiscal_number": self.l10n_ve_fiscal_number,
                "l10n_ve_fiscal_machine_serial": self.l10n_ve_fiscal_machine_serial,
                "l10n_ve_fiscal_date": self.l10n_ve_fiscal_date,
                "l10n_ve_fiscal_doc_type": self.l10n_ve_fiscal_doc_type,
            })
        return vals
