# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
from odoo import api, models
from odoo.exceptions import UserError


class ResCurrencyRate(models.Model):
    _inherit = "res.currency.rate"

    @api.ondelete(at_uninstall=False)
    def _unlink_except_l10n_ve_bs_rate_in_use(self):
        """No se puede borrar una tasa Bs que respalda asientos confirmados.

        Los asientos congelan su tasa al confirmar y guardan la FECHA del
        registro usado (`l10n_ve_bs_rate_date`): borrar ese registro dejaría
        libros cuyos Bs ya no se pueden rastrear hasta una tasa publicada.
        Editar sí se permite (a diferencia de localizaciones que leen la tabla
        al imprimir): el valor ya está congelado en cada asiento, y n8n solo
        escribe la tasa de hoy. Los asientos con tasa manual no dependen de
        la tabla y no cuentan.
        """
        bs_currencies = self.env["res.company"].sudo().search([
            ("l10n_ve_bs_currency_id", "in", self.currency_id.ids),
        ]).l10n_ve_bs_currency_id
        rates = self.filtered(lambda r: r.currency_id in bs_currencies)
        if not rates:
            return
        Move = self.env["account.move"].sudo()
        Rate = self.sudo()
        for rate in rates:
            # Si queda otra tasa de la misma moneda y día (global y de la
            # compañía a la vez), los asientos siguen respaldados.
            if Rate.search_count([
                ("id", "not in", self.ids),
                ("currency_id", "=", rate.currency_id.id),
                ("name", "=", rate.name),
            ], limit=1):
                continue
            domain = [
                ("state", "=", "posted"),
                ("l10n_ve_bs_rate_date", "=", rate.name),
                # Columna nueva: los asientos previos a la instalación la
                # tienen en NULL, no en 0.
                "|", ("l10n_ve_bs_rate_override", "=", False),
                ("l10n_ve_bs_rate_override", "=", 0.0),
                ("company_id.l10n_ve_bs_currency_id", "=", rate.currency_id.id),
            ]
            if rate.company_id:
                domain.append(("company_id", "child_of", rate.company_id.id))
            count = Move.search_count(domain)
            if not count:
                continue
            examples = Move.search(domain, limit=5, order="date desc, id desc")
            raise UserError(self.env._(
                "No se puede borrar la tasa %(currency)s del %(date)s: "
                "%(count)s asiento(s) confirmado(s) la usan como tasa Bs "
                "(p. ej. %(examples)s). Corrija el valor de la tasa en lugar "
                "de borrarla, o restablezca esos asientos a borrador.",
                currency=rate.currency_id.name,
                date=rate.name.strftime("%d-%m-%Y"),
                count=count,
                examples=", ".join(examples.mapped("display_name")),
            ))
