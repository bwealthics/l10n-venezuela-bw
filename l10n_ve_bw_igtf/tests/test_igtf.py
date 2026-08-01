# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_igtf. License LGPL-3.
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestIgtf(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.igtf_expense_account = cls.env["account.account"].create({
            "code": "660101",
            "name": "Gasto por IGTF",
            "account_type": "expense",
        })
        cls.igtf_perception_account = cls.env["account.account"].create({
            "code": "210304",
            "name": "IGTF Percibido por Enterar",
            "account_type": "liability_current",
        })
        cls.company.write({
            "l10n_ve_igtf_expense_account_id": cls.igtf_expense_account.id,
            "l10n_ve_igtf_perception_account_id": cls.igtf_perception_account.id,
        })
        cls.journal_igtf = cls.company_data["default_journal_bank"]
        cls.journal_igtf.l10n_ve_igtf_applies = True
        cls.journal_no_igtf = cls.env["account.journal"].create({
            "name": "Banco Bolívares Prueba",
            "type": "bank",
            "code": "TVES",
        })

    def _create_payment(self, payment_type, journal=None, amount=100.0, date="2026-07-10"):
        return self.env["account.payment"].create({
            "payment_type": payment_type,
            "partner_type": "supplier" if payment_type == "outbound" else "customer",
            "partner_id": self.partner_a.id,
            "amount": amount,
            "date": date,
            "journal_id": (journal or self.journal_igtf).id,
        })

    def test_outbound_igtf_posts_expense_move(self):
        payment = self._create_payment("outbound", amount=100.0)
        self.assertAlmostEqual(payment.l10n_ve_igtf_amount, 3.0)
        payment.action_post()
        move = payment.l10n_ve_igtf_move_id
        self.assertTrue(move, "Un pago saliente por diario IGTF debe generar el asiento de gasto")
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.journal_id, self.journal_igtf)
        self.assertEqual(move.date, payment.date)
        self.assertIn("IGTF 3%", move.ref)
        expense_line = move.line_ids.filtered(
            lambda line: line.account_id == self.igtf_expense_account
        )
        self.assertAlmostEqual(expense_line.debit, 3.0)
        liquidity_line = move.line_ids.filtered(
            lambda line: line.account_id == self.journal_igtf.default_account_id
        )
        self.assertAlmostEqual(liquidity_line.credit, 3.0)

    def test_outbound_igtf_amount_edited(self):
        payment = self._create_payment("outbound", amount=100.0)
        payment.l10n_ve_igtf_amount = 5.0
        payment.action_post()
        expense_line = payment.l10n_ve_igtf_move_id.line_ids.filtered(
            lambda line: line.account_id == self.igtf_expense_account
        )
        self.assertAlmostEqual(expense_line.debit, 5.0)

    def test_outbound_igtf_amount_zeroed(self):
        payment = self._create_payment("outbound", amount=100.0)
        payment.l10n_ve_igtf_amount = 0.0
        payment.action_post()
        self.assertFalse(
            payment.l10n_ve_igtf_move_id,
            "Con el monto IGTF anulado no debe generarse asiento",
        )

    def _assert_igtf_move_reversed(self, move):
        """The posted IGTF entry must survive (sequence chain) and be
        neutralized by exactly one posted reversal linked to it."""
        self.assertTrue(
            move.exists(),
            "El asiento IGTF posteado NO debe eliminarse (protección de cadena "
            "de secuencia y libros SENIAT): debe revertirse",
        )
        self.assertEqual(move.state, "posted")
        reversal = self.env["account.move"].search([("reversed_entry_id", "=", move.id)])
        self.assertEqual(len(reversal), 1, "Debe existir exactamente UNA reversa del asiento IGTF")
        self.assertEqual(reversal.state, "posted")
        self.assertEqual(reversal.date, move.date)
        self.assertAlmostEqual(sum((move + reversal).line_ids.mapped("balance")), 0.0)
        return reversal

    def test_reset_to_draft_reverses_move(self):
        payment = self._create_payment("outbound", amount=100.0)
        payment.action_post()
        move = payment.l10n_ve_igtf_move_id
        self.assertTrue(move)
        payment.action_draft()
        self.assertFalse(payment.l10n_ve_igtf_move_id)
        self._assert_igtf_move_reversed(move)
        # Re-posting must regenerate a FRESH entry, not duplicate on the old one.
        payment.action_post()
        new_move = payment.l10n_ve_igtf_move_id
        self.assertTrue(new_move, "Re-postear el pago debe regenerar el asiento IGTF")
        self.assertNotEqual(new_move, move)
        self.assertEqual(new_move.state, "posted")
        expense_line = new_move.line_ids.filtered(
            lambda line: line.account_id == self.igtf_expense_account
        )
        self.assertAlmostEqual(expense_line.debit, 3.0)

    def test_cancel_reverses_move(self):
        payment = self._create_payment("outbound", amount=100.0)
        payment.action_post()
        move = payment.l10n_ve_igtf_move_id
        self.assertTrue(move)
        payment.action_cancel()
        self.assertFalse(payment.l10n_ve_igtf_move_id)
        self._assert_igtf_move_reversed(move)

    def test_journal_without_flag_does_nothing(self):
        payment = self._create_payment("outbound", journal=self.journal_no_igtf, amount=100.0)
        self.assertAlmostEqual(payment.l10n_ve_igtf_amount, 0.0)
        payment.action_post()
        self.assertFalse(payment.l10n_ve_igtf_move_id)

    def test_inbound_without_spe_does_nothing(self):
        self.assertFalse(self.company.l10n_ve_is_spe)
        payment = self._create_payment("inbound", amount=100.0)
        self.assertAlmostEqual(payment.l10n_ve_igtf_amount, 0.0)
        payment.action_post()
        self.assertFalse(payment.l10n_ve_igtf_move_id)

    def test_inbound_spe_posts_perception_move(self):
        self.company.write({
            "l10n_ve_is_spe": True,
            "l10n_ve_spe_date": "2026-01-01",
        })
        payment = self._create_payment("inbound", amount=100.0, date="2026-07-10")
        self.assertAlmostEqual(payment.l10n_ve_igtf_amount, 3.0)
        payment.action_post()
        move = payment.l10n_ve_igtf_move_id
        self.assertTrue(move, "Como SPE, un cobro en divisas debe generar la percepción IGTF")
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.journal_id, self.journal_igtf)
        liquidity_line = move.line_ids.filtered(
            lambda line: line.account_id == self.journal_igtf.default_account_id
        )
        self.assertAlmostEqual(liquidity_line.debit, 3.0)
        perception_line = move.line_ids.filtered(
            lambda line: line.account_id == self.igtf_perception_account
        )
        self.assertAlmostEqual(perception_line.credit, 3.0)

    def test_inbound_spe_before_date_does_nothing(self):
        self.company.write({
            "l10n_ve_is_spe": True,
            "l10n_ve_spe_date": "2026-01-01",
        })
        payment = self._create_payment("inbound", amount=100.0, date="2025-12-15")
        self.assertAlmostEqual(payment.l10n_ve_igtf_amount, 0.0)
        payment.action_post()
        self.assertFalse(payment.l10n_ve_igtf_move_id)

    def _create_posted_invoice(self, move_type, amount=100.0, date="2026-07-10"):
        invoice = self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": self.partner_a.id,
            "invoice_date": date,
            "date": date,
            "invoice_line_ids": [Command.create({
                "name": "Servicio de prueba",
                "quantity": 1.0,
                "price_unit": amount,
                "tax_ids": [],
            })],
        })
        invoice.action_post()
        return invoice

    def _register_payment(self, invoice, date="2026-07-10"):
        return self.env["account.payment.register"].with_context(
            active_model="account.move",
            active_ids=invoice.ids,
        ).create({
            "journal_id": self.journal_igtf.id,
            "payment_date": date,
        })._create_payments()

    def test_payment_register_single_flow_outbound(self):
        """Regresión (blocker): un pago creado Y posteado en un solo flujo
        (wizard Registrar Pago / RPC) debe computar el IGTF estando aún en
        borrador y generar el asiento del 3%. Antes del fix, el compute corría
        por primera vez con state='in_process', congelaba el NULL de la BD
        (0.0) y no se creaba ningún asiento IGTF."""
        bill = self._create_posted_invoice("in_invoice")
        payments = self._register_payment(bill)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments.payment_type, "outbound")
        self.assertAlmostEqual(
            payments.l10n_ve_igtf_amount, 3.0,
            msg="El IGTF debe computarse aunque nadie leyera el campo antes de postear",
        )
        move = payments.l10n_ve_igtf_move_id
        self.assertTrue(move, "El flujo wizard crear+postear debe generar el asiento IGTF")
        self.assertEqual(move.state, "posted")
        expense_line = move.line_ids.filtered(
            lambda line: line.account_id == self.igtf_expense_account
        )
        self.assertAlmostEqual(expense_line.debit, 3.0)

    def test_payment_register_single_flow_inbound_spe(self):
        """Regresión (blocker), variante percepción: mismo flujo de un solo
        paso para un cobro como Sujeto Pasivo Especial."""
        self.company.write({
            "l10n_ve_is_spe": True,
            "l10n_ve_spe_date": "2026-01-01",
        })
        invoice = self._create_posted_invoice("out_invoice")
        payments = self._register_payment(invoice)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments.payment_type, "inbound")
        self.assertAlmostEqual(payments.l10n_ve_igtf_amount, 3.0)
        move = payments.l10n_ve_igtf_move_id
        self.assertTrue(move, "El cobro SPE vía wizard debe generar la percepción IGTF")
        self.assertEqual(move.state, "posted")
        perception_line = move.line_ids.filtered(
            lambda line: line.account_id == self.igtf_perception_account
        )
        self.assertAlmostEqual(perception_line.credit, 3.0)

    def test_missing_expense_account_raises(self):
        self.company.l10n_ve_igtf_expense_account_id = False
        payment = self._create_payment("outbound", amount=100.0)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            payment.action_post()

    def test_missing_perception_account_raises(self):
        self.company.write({
            "l10n_ve_is_spe": True,
            "l10n_ve_spe_date": "2026-01-01",
            "l10n_ve_igtf_perception_account_id": False,
        })
        payment = self._create_payment("inbound", amount=100.0, date="2026-07-10")
        with self.assertRaises(UserError), self.env.cr.savepoint():
            payment.action_post()
