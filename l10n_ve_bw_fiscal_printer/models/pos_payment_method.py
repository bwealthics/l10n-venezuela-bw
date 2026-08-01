# Part of l10n_ve_bw_fiscal_printer. License LGPL-3.
from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    l10n_ve_fiscal_payment_code = fields.Char(
        string="Código de pago máquina fiscal",
        default="01",
        help="Slot de medio de pago en la impresora fiscal (01-24, protocolo "
             "HKA). Retención = 16.",
    )
    # related: solo baja al POS (los métodos de pago nunca se sincronizan
    # de vuelta), marca los pagos en divisas para el IGTF.
    l10n_ve_igtf_applies = fields.Boolean(
        related="journal_id.l10n_ve_igtf_applies")

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "l10n_ve_fiscal_payment_code", "l10n_ve_igtf_applies"]
