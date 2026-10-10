# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    l10n_ve_bs_currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.l10n_ve_bs_currency_id",
        string="Moneda Bs",
    )
    # La tasa es la del asiento del pago (congelada al confirmarlo), no una
    # propia: el pago y su asiento no pueden contar dos historias en Bs.
    l10n_ve_bs_rate = fields.Float(
        string="Tasa Bs",
        related="move_id.l10n_ve_bs_rate",
        digits=(16, 6),
    )
    l10n_ve_amount_bs = fields.Monetary(
        string="Monto Bs",
        currency_field="l10n_ve_bs_currency_id",
        compute="_compute_l10n_ve_amount_bs",
    )

    @api.depends(
        "amount", "currency_id", "date", "company_id",
        "move_id.line_ids.l10n_ve_balance_bs",
    )
    def _compute_l10n_ve_amount_bs(self):
        """Monto del pago en Bs.

        Pago en Bs: su monto, exacto. Si no, los Bs ALMACENADOS de las líneas
        de liquidez de su asiento (`_seek_for_lines` del core), que son los
        mismos que verá el Mayor del banco. Los pagos de Odoo 19 sin asiento
        (sin cuenta de pendientes en el diario) se convierten con la tabla a
        la fecha del pago, solo para mostrar.
        """
        for payment in self:
            bs = payment.company_id.l10n_ve_bs_currency_id
            amount = 0.0
            if not bs:
                pass
            elif payment.currency_id == bs:
                amount = payment.amount
            elif payment.move_id:
                liquidity_lines = payment._seek_for_lines()[0]
                amount = abs(sum(liquidity_lines.mapped("l10n_ve_balance_bs")))
            elif payment.amount and payment.currency_id:
                company = payment.company_id
                rate, _rate_date = company._l10n_ve_bs_rate_at(payment.date)
                in_company = payment.currency_id._convert(
                    payment.amount, company.currency_id, company,
                    payment.date or fields.Date.context_today(payment))
                amount = bs.round(in_company * rate)
            payment.l10n_ve_amount_bs = amount
