# Part of l10n_ve_bw_einvoice. License LGPL-3.
from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestEinvoice(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.l10n_ve_edoc_provider = "l10n.ve.edoc.provider.dummy"
        cls.tax_16 = cls.env["account.tax"].create({
            "name": "IVA 16% — prueba edoc",
            "amount": 16.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.tax_exempt = cls.env["account.tax"].create({
            "name": "Exento — prueba edoc",
            "amount": 0.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.digital_journal = cls.env["account.journal"].create({
            "name": "Ventas por Imprenta Digital",
            "code": "DIGI",
            "type": "sale",
            "company_id": cls.company.id,
            "l10n_ve_emission_channel": "digital",
        })
        cls.partner = cls.env["res.partner"].with_context(
            no_vat_validation=True).create({
                "name": "Cliente Empresa, C.A.",
                "vat": "J-98765432-1",
                "street": "Av. Principal, Lechería",
            })

    def _invoice(self, journal=None):
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": fields.Date.to_date("2026-07-25"),
            "journal_id": (journal or self.digital_journal).id,
            "invoice_line_ids": [
                Command.create({
                    "name": "Servicio gravado",
                    "quantity": 1.0,
                    "price_unit": 100.0,
                    "tax_ids": [Command.set(self.tax_16.ids)],
                }),
                Command.create({
                    "name": "Insumo exento",
                    "quantity": 2.0,
                    "price_unit": 25.0,
                    "tax_ids": [Command.set(self.tax_exempt.ids)],
                }),
            ],
        })
        move.action_post()
        return move

    def test_document_vals_split_taxed_and_exempt(self):
        # Toda la lógica fiscal vive aquí y no en el adaptador: es lo que
        # permite cambiar de imprenta sin tocar nada fiscal.
        vals = self._invoice()._l10n_ve_edoc_document_vals()
        self.assertEqual(vals["tipo_documento"], "factura")
        self.assertEqual(vals["emisor"]["rif"], self.company.vat or "")
        self.assertEqual(vals["comprador"]["rif"], "J-98765432-1")
        self.assertAlmostEqual(vals["total_base"], 100.0, places=2)
        self.assertAlmostEqual(vals["total_exento"], 50.0, places=2)
        self.assertAlmostEqual(vals["total_iva"], 16.0, places=2)
        exempt_line = next(ln for ln in vals["lineas"] if ln["exento"])
        self.assertAlmostEqual(exempt_line["alicuota"], 0.0, places=2)

    def test_credit_note_references_affected_document(self):
        # La NC debe referenciar número, fecha y monto del documento afectado.
        invoice = self._invoice()
        reversal = self.env["account.move.reversal"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "journal_id": self.digital_journal.id,
            "reason": "prueba",
        })
        refund = self.env["account.move"].browse(
            reversal.reverse_moves()["res_id"])
        vals = refund._l10n_ve_edoc_document_vals()
        self.assertEqual(vals["tipo_documento"], "nota_credito")
        self.assertEqual(vals["documento_afectado"]["numero"], invoice.name)
        self.assertAlmostEqual(
            vals["documento_afectado"]["monto"], invoice.amount_total, places=2)

    def test_debit_note_references_affected_document(self):
        # La ND es un out_invoice con debit_origin_id: sin su rama saldría a
        # la imprenta como "factura" y sin la referencia (número, fecha y
        # monto del documento afectado) que exige la PA 0071.
        if "debit_origin_id" not in self.env["account.move"]._fields:
            self.skipTest("account_debit_note no está instalado")
        invoice = self._invoice()
        wizard = self.env["account.debit.note"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "reason": "Intereses de mora — prueba",
            "copy_lines": True,
        })
        debit = self.env["account.move"].browse(
            wizard.create_debit()["res_id"])
        debit.action_post()
        vals = debit._l10n_ve_edoc_document_vals()
        self.assertEqual(vals["tipo_documento"], "nota_debito")
        afectado = vals["documento_afectado"]
        self.assertEqual(afectado["numero"], invoice.name)
        self.assertEqual(afectado["fecha"], invoice.invoice_date)
        self.assertAlmostEqual(
            afectado["monto"], invoice.amount_total, places=2)

    def test_send_assigns_control_number_and_logs(self):
        move = self._invoice()
        move.action_l10n_ve_edoc_send()
        self.assertEqual(move.l10n_ve_edoc_state, "assigned")
        self.assertTrue(move.l10n_ve_control_number)
        self.assertTrue(move.l10n_ve_control_date)
        log = self.env["l10n.ve.edoc.log"].search([("move_id", "=", move.id)])
        self.assertTrue(log, "cada llamada al proveedor deja bitácora")
        self.assertTrue(log[0].ok)

    def test_control_number_written_despite_the_guard(self):
        # El diario es de canal 'digital', donde el Nº de control está
        # bloqueado para el usuario. El conector SÍ puede escribirlo: usa el
        # contexto de write-back. Si esto se rompe, no se puede facturar.
        move = self._invoice()
        with self.assertRaises(UserError):
            move.l10n_ve_control_number = "00-99999999"
        move.action_l10n_ve_edoc_send()
        self.assertTrue(move.l10n_ve_control_number)

    def test_send_rejects_wrong_channel(self):
        move = self._invoice(journal=self.company_data["default_journal_sale"])
        with self.assertRaises(UserError):
            move.action_l10n_ve_edoc_send()

    def test_send_is_not_repeatable(self):
        move = self._invoice()
        move.action_l10n_ve_edoc_send()
        with self.assertRaises(UserError):
            move.action_l10n_ve_edoc_send()

    def test_async_provider_needs_a_second_step(self):
        # Con un proveedor asíncrono (Unidigital) la emisión no trae el Nº de
        # control: el documento queda 'sent' y se consulta después.
        provider = self.env["l10n.ve.edoc.provider.dummy"]
        move = self._invoice()
        self.patch(type(provider), "_dummy_fetch_delay", 1)
        move.action_l10n_ve_edoc_send()
        self.assertEqual(move.l10n_ve_edoc_state, "sent")
        self.assertFalse(move.l10n_ve_control_number)
        move.action_l10n_ve_edoc_fetch()
        self.assertEqual(move.l10n_ve_edoc_state, "assigned")
        self.assertTrue(move.l10n_ve_control_number)

    def test_provider_failure_does_not_break_accounting(self):
        # Un fallo del proveedor deja el documento en 'error' con su bitácora,
        # pero NUNCA tumba la factura ya contabilizada.
        move = self._invoice()

        def boom(self, move, vals):
            raise ValueError("la imprenta no responde")

        self.patch(
            type(self.env["l10n.ve.edoc.provider.dummy"]), "_edoc_send", boom)
        move.action_l10n_ve_edoc_send()
        self.assertEqual(move.l10n_ve_edoc_state, "error")
        self.assertIn("no responde", move.l10n_ve_edoc_error)
        self.assertEqual(move.state, "posted")
        log = self.env["l10n.ve.edoc.log"].search([("move_id", "=", move.id)])
        self.assertFalse(log[0].ok)
