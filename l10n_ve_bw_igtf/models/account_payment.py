# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_igtf. License LGPL-3.
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    l10n_ve_igtf_applies = fields.Boolean(
        related="journal_id.l10n_ve_igtf_applies",
        string="Diario sujeto a IGTF",
    )
    l10n_ve_igtf_amount = fields.Monetary(
        string="Monto IGTF",
        currency_field="currency_id",
        compute="_compute_l10n_ve_igtf_amount",
        inverse="_inverse_l10n_ve_igtf_amount",
        store=True,
        readonly=False,
        help="IGTF causado por este pago. Editable: póngalo en 0 si el pago no "
        "causa IGTF (ej. efectivo o Zelle a un proveedor no sujeto, art. 4 "
        "num. 5/6 de la Ley IGTF). Al editarlo queda fijado: corregir luego "
        "el monto o la fecha del pago ya no lo recalcula.",
    )
    l10n_ve_igtf_manual = fields.Boolean(
        string="IGTF fijado a mano",
        copy=False,
        help="Se marca solo al editar el Monto IGTF: congela el valor frente "
        "al recálculo automático (cambios de monto/fecha/diario del pago en "
        "borrador). Desmárquelo para volver al cálculo automático.",
    )
    l10n_ve_igtf_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento IGTF",
        readonly=True,
        copy=False,
    )

    def _l10n_ve_igtf_qualifies(self):
        """Whether this payment triggers IGTF accounting.

        Outbound on a flagged journal always qualifies (own debit). Inbound
        (perception) only qualifies for Special Taxpayers (SPE) from the SENIAT
        designation date on; with the SPE flag off there is zero inbound logic.
        A flag without date means the perception applies from the flag on.
        """
        self.ensure_one()
        if not self.journal_id.l10n_ve_igtf_applies:
            return False
        if self.payment_type == "outbound":
            return True
        company = self.company_id
        return bool(
            self.payment_type == "inbound"
            and company.l10n_ve_is_spe
            and (not company.l10n_ve_spe_date or (self.date and self.date >= company.l10n_ve_spe_date))
        )

    def _l10n_ve_igtf_auto_amount(self):
        """Monto IGTF automático del pago (pct de la compañía si aplica)."""
        self.ensure_one()
        if not self._l10n_ve_igtf_qualifies():
            return 0.0
        amount = self.amount * self.company_id.l10n_ve_igtf_pct / 100.0
        return self.currency_id.round(amount) if self.currency_id else amount

    def _inverse_l10n_ve_igtf_amount(self):
        # El cliente web REENVÍA el valor computado al guardar (echo-back del
        # onchange), así que "el campo vino en vals" no basta para detectar
        # una edición: se congela SOLO si lo escrito difiere del automático.
        # Ventaja extra: desmarcar el check pega a la primera (el echo trae
        # ya el valor recalculado, que coincide y deja manual en False).
        for payment in self:
            expected = payment._l10n_ve_igtf_auto_amount()
            if payment.currency_id:
                deviates = payment.currency_id.compare_amounts(
                    payment.l10n_ve_igtf_amount, expected) != 0
            else:
                deviates = payment.l10n_ve_igtf_amount != expected
            payment.l10n_ve_igtf_manual = deviates

    @api.depends(
        "journal_id.l10n_ve_igtf_applies",
        "amount",
        "payment_type",
        "date",
        "currency_id",
        "l10n_ve_igtf_manual",
    )
    def _compute_l10n_ve_igtf_amount(self):
        # Only fields immutable once the payment is posted drive this compute
        # (amount / journal / type / date). The company IGTF rate and SPE
        # flags are deliberately NOT dependencies: a posted payment keeps the
        # amount computed at its time, and the field is editable, so later
        # configuration changes never rewrite historical payments. This also
        # removes the old state-based freezing branch, which misfired when the
        # stored compute was first evaluated (deferred by the payment-register
        # flow) only after the state had already left 'draft', persisting 0.0.
        for payment in self:
            if payment.l10n_ve_igtf_manual:
                # Valor fijado por el usuario (p. ej. 0 por exención art. 4):
                # un cambio de monto/fecha en borrador no debe pisarlo.
                payment.l10n_ve_igtf_amount = payment.l10n_ve_igtf_amount
            else:
                payment.l10n_ve_igtf_amount = payment._l10n_ve_igtf_auto_amount()

    def action_post(self):
        res = super().action_post()
        self._l10n_ve_igtf_create_moves()
        return res

    def action_draft(self):
        res = super().action_draft()
        self._l10n_ve_igtf_remove_moves()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        self._l10n_ve_igtf_remove_moves()
        return res

    def _l10n_ve_igtf_create_moves(self):
        for payment in self:
            if payment.l10n_ve_igtf_move_id or payment.state not in ("in_process", "paid"):
                continue
            if not payment._l10n_ve_igtf_qualifies():
                continue
            if payment.currency_id.compare_amounts(payment.l10n_ve_igtf_amount, 0.0) <= 0:
                continue
            payment.l10n_ve_igtf_move_id = payment._l10n_ve_igtf_generate_move()

    def _l10n_ve_igtf_generate_move(self):
        self.ensure_one()
        company = self.company_id
        journal = self.journal_id
        liquidity_account = journal.default_account_id
        if not liquidity_account:
            raise UserError(_(
                "El diario %(journal)s no tiene cuenta por defecto configurada; "
                "es necesaria para registrar el IGTF del pago %(payment)s.",
                journal=journal.display_name,
                payment=self.display_name,
            ))
        if self.payment_type == "outbound":
            counterpart_account = company.l10n_ve_igtf_expense_account_id
            if not counterpart_account:
                raise UserError(_(
                    "Configure la Cuenta de Gasto IGTF de la compañía %(company)s en "
                    "Ajustes > Contabilidad > Localización Venezuela — IGTF antes de "
                    "confirmar pagos en divisas.",
                    company=company.display_name,
                ))
            debit_account, credit_account = counterpart_account, liquidity_account
        else:
            counterpart_account = company.l10n_ve_igtf_perception_account_id
            if not counterpart_account:
                raise UserError(_(
                    "Configure la Cuenta de Percepción IGTF de la compañía %(company)s en "
                    "Ajustes > Contabilidad > Localización Venezuela — IGTF antes de "
                    "confirmar cobros en divisas como Sujeto Pasivo Especial.",
                    company=company.display_name,
                ))
            debit_account, credit_account = liquidity_account, counterpart_account

        amount_currency = self.l10n_ve_igtf_amount
        balance = self.currency_id._convert(
            amount_currency, company.currency_id, company, self.date
        )
        ref = "IGTF %g%% - %s" % (company.l10n_ve_igtf_pct, self.name or self.display_name)
        common_line_vals = {
            "name": ref,
            "partner_id": self.partner_id.id,
            "currency_id": self.currency_id.id,
        }
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "company_id": company.id,
            "date": self.date,
            "ref": ref,
            "currency_id": self.currency_id.id,
            "partner_id": self.partner_id.id,
            "line_ids": [
                Command.create({
                    **common_line_vals,
                    "account_id": debit_account.id,
                    "amount_currency": amount_currency,
                    "balance": balance,
                }),
                Command.create({
                    **common_line_vals,
                    "account_id": credit_account.id,
                    "amount_currency": -amount_currency,
                    "balance": -balance,
                }),
            ],
        })
        move.action_post()
        return move

    def _l10n_ve_igtf_remove_moves(self):
        """Neutralize the linked IGTF entry when the payment leaves posted.

        Posted entries are REVERSED (``_reverse_moves(cancel=True)``), never
        deleted: the IGTF entry consumes the sequence of the bank journal, so
        unlinking it would raise for non-manager accountants (sequence-chain
        protection of account.move) and, for managers, would leave a numbering
        gap in a legal journal (SENIAT books). Entries still in draft are
        simply deleted. In every case the link is cleared, so re-posting the
        payment regenerates a fresh IGTF entry without duplicating.
        """
        moves = self.l10n_ve_igtf_move_id
        if not moves:
            return
        self.write({"l10n_ve_igtf_move_id": False})
        posted_moves = moves.filtered(lambda move: move.state == "posted")
        if posted_moves:
            posted_moves._reverse_moves(
                default_values_list=[
                    {
                        "ref": _("Reversa: %s", move.ref or move.name),
                        "date": move.date,
                    }
                    for move in posted_moves
                ],
                cancel=True,
            )
        moves.filtered(lambda move: move.state == "draft").unlink()

    def button_open_l10n_ve_igtf_move(self):
        self.ensure_one()
        return {
            "name": _("Asiento IGTF"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "context": {"create": False},
            "view_mode": "form",
            "res_id": self.l10n_ve_igtf_move_id.id,
        }
