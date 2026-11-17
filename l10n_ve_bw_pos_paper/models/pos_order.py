# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_paper. License LGPL-3.
from odoo import _, fields, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    # Bitácora de las decisiones HUMANAS sobre el correlativo fiscal de la
    # orden. La captura del talonario escribe "contingency" en cada venta en
    # papel, así que es dato de ESTE módulo. Campos planos que escribe el
    # frontend: una RPC fallaría justo cuando importa (caja sin conexión).
    # Se conservan los valores de máquina del módulo de origen: quitar un
    # valor de una Selection hace que Odoo vacíe los registros que lo usan
    # (ir.model.fields.selection._process_ondelete).
    l10n_ve_fiscal_event = fields.Selection(
        [("adopt_uuid", "Nº adoptado por UUID"),
         ("adopt_manual", "Nº adoptado por confirmación del cajero"),
         ("reprint", "Reimpresión tras intento fallido"),
         ("contingency", "Emitida en contingencia"),
         ("blocked", "Venta bloqueada por la máquina")],
        string="Incidencia fiscal", copy=False, readonly=True)
    l10n_ve_fiscal_event_note = fields.Text(
        string="Bitácora de la incidencia", copy=False, readonly=True)

    def _l10n_ve_has_fiscal_document(self):
        """True si la orden ya tiene correlativo fiscal propio. Punto de
        extensión: un módulo de máquina fiscal añade su número."""
        self.ensure_one()
        return bool(self.l10n_ve_contingency_control)

    def _create_invoice(self, move_vals):
        # El Nº de control de estos vals lo puso ESTE módulo (o el de máquina
        # fiscal que encadena _l10n_ve_paper_invoice_vals) desde el papel
        # preimpreso: origen de confianza. Sin el contexto, el guard de create
        # de l10n_ve_bw_fiscal_books bloquearía la facturación de una venta
        # cuyo documento fiscal YA existe.
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
            # varios documentos. Si alguna orden ya tiene documento fiscal,
            # consolidarla la dejaría fuera del Libro de Ventas: cada una
            # debe facturarse por separado con su propio Nº.
            fiscal_orders = self.filtered(
                lambda o: o._l10n_ve_has_fiscal_document())
            if fiscal_orders:
                raise UserError(_(
                    "No se puede emitir una factura consolidada: las órdenes "
                    "%(orders)s ya tienen documento fiscal (ticket de máquina "
                    "fiscal o talonario de contingencia). Facture cada una por "
                    "separado para conservar su Nº de control.",
                    orders=", ".join(fiscal_orders.mapped("name")),
                ))
            return vals
        return self._l10n_ve_paper_invoice_vals(vals)

    def _l10n_ve_paper_invoice_vals(self, vals):
        """Completa los vals de la factura de UNA orden con su papelería
        fiscal. Punto de extensión: un módulo de máquina fiscal encadena aquí
        su rama (número de la máquina → Nº de control) y llama a super()."""
        self.ensure_one()
        config = self.session_id.config_id
        control = self.l10n_ve_contingency_control
        if not control:
            return vals
        if config.l10n_ve_paper_mode == "libre":
            # Formas libres: el control preimpreso de la hoja viaja en el
            # mismo campo plano de la orden (es el único slot que sincroniza
            # desde el POS), pero la factura va al diario NORMAL de la caja
            # (canal libre, write-once) y el Nº de factura lo asigna la
            # secuencia del diario.
            vals.update({
                "l10n_ve_control_number": control,
                "ref": "Forma libre C-%s" % control,
            })
            return vals
        # Venta facturada a mano en el talonario: va a su propio diario, que
        # no lleva cadena de hash porque replica un papel que ya existe.
        # Nº de control y Nº de factura son los del formato preimpreso; el
        # Libro de Ventas usa el segundo como Nº de documento.
        paper = self.l10n_ve_contingency_invoice_number
        ref = ("Contingencia F-%s C-%s" % (paper, control)
               if paper else "Contingencia %s" % control)
        vals.update({
            "journal_id": config.l10n_ve_contingency_journal_id.id,
            "l10n_ve_control_number": control,
            "l10n_ve_paper_number": paper or False,
            "ref": ref,
        })
        return vals
