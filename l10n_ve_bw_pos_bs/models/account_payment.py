# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_bs. License LGPL-3.
from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _prepare_move_liquidity_lines(self, default_values):
        """Denomina en VES la línea de liquidez del pago del cierre POS.

        pos.session inyecta por contexto los Bs exactos capturados en caja
        (l10n_ve_bs_amount, siempre positivo) y la moneda (l10n_ve_bs_currency_id).
        Solo se cambia la denominación (currency_id + amount_currency); el
        balance en moneda compañía que calculó el core queda intacto, así el
        asiento sigue cuadrando centavo a centavo contra el receivable del POS.

        En Odoo 19 no existe _synchronize_from_moves y _synchronize_to_moves
        salta los asientos posteados, de modo que el payment permanece en la
        moneda del diario (USD) sin pelear con esta línea.
        """
        vals_list = super()._prepare_move_liquidity_lines(default_values)
        bs_amount = self.env.context.get("l10n_ve_bs_amount")
        bs_currency_id = self.env.context.get("l10n_ve_bs_currency_id")
        if (
            bs_amount
            and bs_currency_id
            and bs_currency_id != self.company_id.currency_id.id
            # El core retorna UNA línea de liquidez; si otro módulo la parte
            # en varias, denominar cada una con el total duplicaría los Bs —
            # en ese caso se respeta el flujo del otro módulo (USD).
            and len(vals_list) == 1
        ):
            sign = -1.0 if default_values.get("amount_currency", 0.0) < 0 else 1.0
            vals_list[0].update(
                {
                    "currency_id": bs_currency_id,
                    "amount_currency": sign * abs(bs_amount),
                }
            )
        return vals_list
