# Part of l10n_ve_bw. License LGPL-3.
from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # Interfaz para el módulo de libros fiscales (dirección "sujeto retenido"):
    # la retención de IVA que un cliente SPE practicó sobre este cobro, copiada
    # desde el wizard de pago vía _create_payment_vals_from_wizard.
    l10n_ve_iva_wh_received_amount = fields.Monetary(
        string="IVA Retenido por el Cliente",
        currency_field="currency_id",
        copy=False,
        help="Monto de IVA retenido por el cliente (agente de retención) sobre "
             "este cobro, según el comprobante recibido. Los libros fiscales lo "
             "usan para reportar la retención recibida por factura.",
    )
    l10n_ve_iva_wh_received_number = fields.Char(
        string="Nº de Comprobante de Retención Recibido",
        size=14,
        copy=False,
        help="Numeración de 14 caracteres del comprobante de retención "
             "entregado por el cliente: AAAAMM + secuencial de 8 dígitos.",
    )
