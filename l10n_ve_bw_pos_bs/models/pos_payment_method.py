# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_bs. License LGPL-3.
from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    l10n_ve_bs_tender = fields.Boolean(
        string="Cobro en Bolívares (Bs)",
        help="El cliente paga en VES aunque el POS opere en la moneda de la "
        "compañía. El POS captura los Bs exactos recibidos y, al cerrar la "
        "sesión, la línea de liquidez del pago combinado se denomina en VES "
        "(amount_currency = Bs capturados) para conciliarla 1:1 contra el "
        "extracto bancario en bolívares.",
    )
    l10n_ve_bs_require_ref = fields.Boolean(
        string="Exigir referencia",
        help="Pide y exige el número de referencia de la transacción "
        "(pago móvil / voucher del punto de venta) antes de validar la orden. "
        "Se guarda en el pago del POS (payment_ref_no).",
    )
    l10n_ve_bs_payer_data = fields.Boolean(
        string="Exigir datos del pagador (P2C)",
        help="Pide además el teléfono del pagador (04XXXXXXXXX) y el banco "
        "emisor (lista SUDEBAN) — ambos salen del comprobante del cliente. "
        "Los exige el API Conciliación de Banco de Venezuela (getMovement) "
        "para verificar el pago móvil y construir el extracto bancario "
        "automático. Solo aplica a cobros (no a reembolsos).",
    )

    l10n_ve_bs_dest_banks = fields.Char(
        string="Bancos destino (P2C)",
        help="Códigos SUDEBAN de las cuentas del comercio que reciben este "
        "cobro, separados por coma; el primero es el predeterminado (p.ej. "
        "'0172,0102' = Bancamiga o Banco de Venezuela). Con más de uno, el POS "
        "pregunta a qué banco llegó el pago (según el comprobante) y lo guarda "
        "en el pago. El verificador BDV solo consulta los cobros con destino "
        "0102: los demás no los puede ver el API de BDV y se concilian contra "
        "el extracto de su banco. Vacío = todo va a BDV (comportamiento "
        "anterior).",
    )

    l10n_ve_split_partner_id = fields.Many2one(
        "res.partner",
        string="Cliente por defecto (split)",
        help="Con \"Identify Customer\" (split_transactions) activo, cada "
        "pago genera su propio asiento y Odoo exige cliente en la orden. Con "
        "este campo la caja NO pide cliente: los pagos de órdenes sin cliente "
        "se contabilizan a nombre de este contacto (p.ej. CONSUMIDOR FINAL). "
        "La orden no recibe el cliente, así que no cambia la facturación. "
        "Sirve para conciliar cada pago móvil 1:1 contra su línea del banco.",
    )
    l10n_ve_split_no_customer = fields.Boolean(
        compute="_compute_l10n_ve_split_no_customer",
    )

    @api.depends("split_transactions", "l10n_ve_split_partner_id")
    def _compute_l10n_ve_split_no_customer(self):
        for method in self:
            method.l10n_ve_split_no_customer = bool(
                method.split_transactions and method.l10n_ve_split_partner_id
            )

    @api.model
    def _load_pos_data_fields(self, config):
        # pos.payment.method restringe la lista de campos que viajan al POS
        # (a diferencia de pos.payment, que carga todos): sin esto el
        # frontend nunca vería los flags.
        return super()._load_pos_data_fields(config) + [
            "l10n_ve_bs_tender",
            "l10n_ve_bs_require_ref",
            "l10n_ve_bs_payer_data",
            "l10n_ve_bs_dest_banks",
            "l10n_ve_split_no_customer",
        ]
