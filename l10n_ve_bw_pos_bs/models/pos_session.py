# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_bs. License LGPL-3.
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    def _l10n_ve_bs_total(self, payments):
        """Bs exactos de un lote de pagos de un tender en bolívares.

        Prioriza lo capturado en caja (l10n_ve_amount_bs, con signo). Para
        pagos sin captura (chatbot, flujos por código, histórico previo al
        módulo) convierte el importe a VES a la tasa BCV de la fecha del pago —
        SOLO si existe una tasa cargada: sin tasa, _convert degrada a 1.0 en
        silencio y contaminaría la denominación, así que se devuelve 0.0 y el
        cierre sigue el flujo core intacto (USD).
        Devuelve (total_bs, ves).
        """
        company = self.company_id
        ves = self.env["res.currency"].search([("name", "=", "VES")], limit=1)
        if not ves or ves == company.currency_id:
            return 0.0, ves
        total = 0.0
        for payment in payments:
            if payment.l10n_ve_amount_bs:
                total += payment.l10n_ve_amount_bs
            else:
                date = (payment.payment_date or fields.Datetime.now()).date()
                has_rate = self.env["res.currency.rate"].search_count(
                    [
                        ("currency_id", "=", ves.id),
                        ("name", "<=", date),
                        ("company_id", "in", (False, company.id)),
                    ],
                    limit=1,
                )
                if not has_rate:
                    _logger.warning(
                        "l10n_ve_bw_pos_bs: sin tasa VES <= %s para el pago %s "
                        "de %s; la sesión %s cierra sin denominación en Bs.",
                        date, payment.id, payment.payment_method_id.name, self.name,
                    )
                    return 0.0, ves
                total += company.currency_id._convert(
                    payment.amount, ves, company, date
                )
        return ves.round(total), ves

    def _l10n_ve_bs_annotate_refs(self, receivable_line, payments):
        """Anexa las referencias capturadas al ref del asiento del pago para
        que el contador las vea desde la conciliación bancaria. 'ref' no es
        un campo contable protegido: es escribible en el asiento posteado."""
        refs = [
            ref.strip()
            for ref in payments.mapped("payment_ref_no")
            if ref and ref.strip()
        ]
        if refs and receivable_line:
            move = receivable_line.move_id
            move.ref = f"{move.ref or ''} · Ref: {', '.join(refs)}"[:500]

    def _l10n_ve_bs_context_for(self, payments, session_amount, diff_amount=0.0):
        """Contexto de denominación VES, o None si no aplica.

        Guardas (verificadas contra el core v19):
        - diff_amount != 0: _apply_diff_on_account_payment_move reescribe
          debit/credit SIN tocar amount_currency → desincronizaría los Bs (y
          un flip de signo violaría _check_amount_currency_balance_sign).
          Con diferencia declarada en el cierre se cae al flujo core en USD.
        - neto USD cero o signo Bs opuesto al signo USD: la línea de liquidez
          no puede llevar amount_currency de signo contrario a su balance.
        """
        if not self.currency_id.is_zero(diff_amount):
            _logger.warning(
                "l10n_ve_bw_pos_bs: la sesión %s declaró una diferencia de "
                "cierre (%.2f) en un tender Bs; el pago queda en USD sin "
                "denominación VES.", self.name, diff_amount,
            )
            return None
        if self.currency_id.is_zero(session_amount):
            return None
        bs_total, ves = self._l10n_ve_bs_total(payments)
        if not bs_total or not ves:
            return None
        if (bs_total > 0) != (session_amount > 0):
            _logger.warning(
                "l10n_ve_bw_pos_bs: sesión %s con signo Bs (%.2f) opuesto al "
                "neto USD (%.2f); el pago queda en USD sin denominación VES.",
                self.name, bs_total, session_amount,
            )
            return None
        return {
            "l10n_ve_bs_amount": abs(bs_total),
            "l10n_ve_bs_currency_id": ves.id,
        }

    def _create_combine_account_payment(self, payment_method, amounts, diff_amount):
        # Tender en Bs: inyectar los Bs exactos por contexto para que
        # account.payment._prepare_move_liquidity_lines denomine en VES la
        # línea de la cuenta puente. El contexto viaja por self.env hasta el
        # create/action_post del payment dentro del método core.
        if payment_method.l10n_ve_bs_tender:
            payments = self.env["pos.payment"].search(
                [
                    ("session_id", "=", self.id),
                    ("payment_method_id", "=", payment_method.id),
                ]
            )
            ctx = self._l10n_ve_bs_context_for(
                payments, amounts["amount"], diff_amount
            )
            if ctx:
                receivable_line = super(
                    PosSession, self.with_context(**ctx)
                )._create_combine_account_payment(payment_method, amounts, diff_amount)
                self._l10n_ve_bs_annotate_refs(receivable_line, payments)
                return receivable_line
        return super()._create_combine_account_payment(
            payment_method, amounts, diff_amount
        )

    def _l10n_ve_split_ctx(self, payment):
        """Contexto con el cliente por defecto del método para pagos split de
        órdenes sin cliente (res.partner._find_accounting_partner lo lee)."""
        fallback = payment.payment_method_id.l10n_ve_split_partner_id
        if fallback and not payment.partner_id:
            return {"l10n_ve_split_fallback_partner_id": fallback.id}
        return {}

    def _get_split_receivable_vals(self, payment, amount, amount_converted):
        ctx = self._l10n_ve_split_ctx(payment)
        return super(PosSession, self.with_context(**ctx))._get_split_receivable_vals(
            payment, amount, amount_converted
        )

    def _create_split_account_payments(self, payment_amounts_list):
        # Un account.payment por pos.payment (split_transactions): la línea de
        # la cuenta puente se denomina en VES con los Bs de ESE pago, y así
        # concilia 1:1 contra su línea del extracto.
        # En v19 el cierre (_create_bank_payment_moves) llama a este método en
        # LOTE; el singular _create_split_account_payment solo lo envuelve y el
        # cierre no lo usa (por eso el override anterior nunca corría y los
        # pagos móviles salían en USD sin l10n_ve_split_ap_id, 2026-10-25 →
        # 2026-11-17). El contexto de denominación es distinto por pago, así
        # que los tenders Bs se crean de a uno; el resto sigue en lote.
        result = {}
        plain = []
        for payment, amounts in payment_amounts_list:
            payment_method = payment.payment_method_id
            ctx = {}
            if payment_method.l10n_ve_bs_tender and payment_method.journal_id:
                ctx = self._l10n_ve_bs_context_for(payment, amounts["amount"]) or {}
            split_ctx = self._l10n_ve_split_ctx(payment)
            if not ctx and not split_ctx:
                plain.append((payment, amounts))
                continue
            lines = super(
                PosSession, self.with_context(**ctx, **split_ctx)
            )._create_split_account_payments([(payment, amounts)])
            receivable_line = lines.get(payment, self.env["account.move.line"])
            if ctx:
                self._l10n_ve_bs_annotate_refs(receivable_line, payment)
            account_payment = receivable_line.move_id.origin_payment_id[:1]
            if account_payment:
                payment.l10n_ve_split_ap_id = account_payment.id
            result.update(lines)
        if plain:
            result.update(super()._create_split_account_payments(plain))
        return result
