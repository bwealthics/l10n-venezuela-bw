# Part of l10n_ve_bw. License LGPL-3.
import base64
from datetime import date

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestL10nVeWhIva(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.vat = "J-12345678-9"

        cls.agent_account = cls.env["account.account"].create({
            "name": "Retenciones de IVA por Enterar (test)",
            "code": "T210303",
            "account_type": "liability_current",
        })
        cls.received_account = cls.env["account.account"].create({
            "name": "Retenciones de IVA Recibidas de Clientes (test)",
            "code": "T110302",
            "account_type": "asset_current",
        })
        cls.company.l10n_ve_iva_wh_agent_account_id = cls.agent_account
        cls.company.l10n_ve_iva_wh_received_account_id = cls.received_account

        cls.vendor = cls.env["res.partner"].create({
            "name": "Proveedor Ordinario VE",
            "vat": "V-98765432-1",
            "l10n_ve_wh_iva_rate": "75",
        })
        cls.vendor_spe = cls.env["res.partner"].create({
            "name": "Proveedor SPE VE",
            "vat": "J-11122233-4",
            "l10n_ve_wh_iva_rate": "75",
            "l10n_ve_taxpayer_type": "especial",
        })
        cls.customer = cls.env["res.partner"].create({
            "name": "Cliente SPE VE",
            "vat": "J-55566677-8",
        })

        ves = cls.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "VES")], limit=1,
        )
        if not ves:
            ves = cls.env["res.currency"].create({
                "name": "VES", "symbol": "Bs.", "rounding": 0.01,
            })
        elif not ves.active:
            ves.active = True
        cls.ves = ves

    @classmethod
    def _create_bill(cls, partner, price_unit=1000.0, move_type="in_invoice",
                     post=True, ref=False):
        move = cls.env["account.move"].create({
            "move_type": move_type,
            "partner_id": partner.id,
            "invoice_date": "2026-01-10",
            "date": "2026-01-10",
            "ref": ref or False,
            "invoice_line_ids": [Command.create({
                "name": "Servicio de prueba",
                "quantity": 1.0,
                "price_unit": price_unit,
                "tax_ids": [Command.set(cls.company_data["default_tax_purchase"].ids)],
            })],
        })
        if post:
            move.action_post()
        return move

    @classmethod
    def _create_customer_invoice(cls, partner, price_unit=1000.0):
        move = cls.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": "2026-01-10",
            "date": "2026-01-10",
            "invoice_line_ids": [Command.create({
                "name": "Venta de prueba",
                "quantity": 1.0,
                "price_unit": price_unit,
                "tax_ids": [Command.set(cls.company_data["default_tax_sale"].ids)],
            })],
        })
        move.action_post()
        return move

    def _register_wizard(self, moves, **values):
        return self.env["account.payment.register"].with_context(
            active_model="account.move",
            active_ids=moves.ids,
        ).create({"payment_date": "2026-01-15", **values})

    def _enable_spe(self, spe_date="2026-01-01"):
        self.company.l10n_ve_is_spe = True
        self.company.l10n_ve_spe_date = spe_date

    def _agent_writeoff_lines(self, payment):
        return payment.move_id.line_ids.filtered(
            lambda l: l.account_id == self.agent_account,
        )

    # -------------------------------------------------------------------------
    # Gates del cálculo (agente)
    # -------------------------------------------------------------------------

    def test_agent_disabled_no_withholding(self):
        self.company.l10n_ve_is_spe = False
        bill = self._create_bill(self.vendor)
        wizard = self._register_wizard(bill)
        self.assertEqual(wizard.l10n_ve_iva_wh_amount, 0.0)

    def test_agent_spe_date_in_future_no_withholding(self):
        self._enable_spe(spe_date="2030-01-01")
        bill = self._create_bill(self.vendor)
        wizard = self._register_wizard(bill)
        self.assertEqual(wizard.l10n_ve_iva_wh_amount, 0.0)

    def test_agent_supplier_spe_excluded(self):
        # Exclusión art. 3 PA SNAT/2025/000054: proveedor también SPE.
        self._enable_spe()
        bill = self._create_bill(self.vendor_spe)
        wizard = self._register_wizard(bill)
        self.assertEqual(wizard.l10n_ve_iva_wh_amount, 0.0)

    def test_agent_partner_rate_zero_no_withholding(self):
        self._enable_spe()
        self.vendor.l10n_ve_wh_iva_rate = "0"
        bill = self._create_bill(self.vendor)
        wizard = self._register_wizard(bill)
        self.assertEqual(wizard.l10n_ve_iva_wh_amount, 0.0)
        self.vendor.l10n_ve_wh_iva_rate = "75"

    def test_agent_no_rif_no_withholding(self):
        # Sin RIF no puede emitirse el comprobante ni declararse la 99035:
        # la retención automática debe ser 0 aunque el default sea 75%.
        self._enable_spe()
        vendor_no_rif = self.env["res.partner"].create({
            "name": "Proveedor sin RIF",
        })
        bill = self._create_bill(vendor_no_rif)
        wizard = self._register_wizard(bill)
        self.assertEqual(wizard.l10n_ve_iva_wh_amount, 0.0)

    def test_agent_draft_invoice_no_withholding_flow_open(self):
        # El flujo core de "registrar pago sobre borrador" no debe bloquearse:
        # la retención solo se calcula sobre facturas publicadas.
        self._enable_spe()
        bill = self._create_bill(self.vendor, post=False)
        wizard = self._register_wizard(bill)
        self.assertEqual(wizard.l10n_ve_iva_wh_amount, 0.0)
        action = wizard.action_create_payments()
        payment = self.env["account.payment"].browse(action["res_id"])
        self.assertTrue(payment.exists())
        self.assertFalse(self.env["l10n.ve.iva.wh.voucher"].search([
            ("move_ids", "in", bill.id),
        ]))

    # -------------------------------------------------------------------------
    # Flujo agente: pago completo
    # -------------------------------------------------------------------------

    def test_agent_withholding_75_full_flow(self):
        self._enable_spe()
        bill = self._create_bill(self.vendor)
        expected_wh = self.company.currency_id.round(bill.amount_tax * 0.75)
        self.assertGreater(expected_wh, 0.0)

        wizard = self._register_wizard(bill)
        self.assertAlmostEqual(wizard.l10n_ve_iva_wh_amount, expected_wh, places=2)

        action = wizard.action_create_payments()
        payment = self.env["account.payment"].browse(action["res_id"])
        self.assertAlmostEqual(payment.amount, bill.amount_total - expected_wh, places=2)

        # La factura queda 100% saldada: banco por el neto + write-off por la retención.
        self.assertEqual(bill.amount_residual, 0.0)
        writeoff_lines = self._agent_writeoff_lines(payment)
        self.assertEqual(len(writeoff_lines), 1)
        self.assertAlmostEqual(writeoff_lines.credit, expected_wh, places=2)

        voucher = self.env["l10n.ve.iva.wh.voucher"].search([
            ("payment_id", "=", payment.id),
        ])
        self.assertEqual(len(voucher), 1)
        self.assertEqual(voucher.state, "posted")
        self.assertEqual(len(voucher.number), 14)
        self.assertTrue(voucher.number.isdigit())
        self.assertTrue(voucher.number.startswith("202601"))
        self.assertAlmostEqual(voucher.withheld_amount, expected_wh, places=2)
        self.assertAlmostEqual(voucher.tax_amount, bill.amount_tax, places=2)
        self.assertAlmostEqual(voucher.base_amount, bill.amount_untaxed, places=2)
        self.assertEqual(voucher.wh_rate, 75.0)
        # Interfaz pública para los libros fiscales.
        self.assertAlmostEqual(
            voucher._l10n_ve_get_amount_for_move(bill), expected_wh, places=2,
        )
        other_move = self._create_bill(self.vendor, price_unit=50.0)
        self.assertEqual(voucher._l10n_ve_get_amount_for_move(other_move), 0.0)

    # -------------------------------------------------------------------------
    # Flujo agente: pagos parciales (regresión blockers)
    # -------------------------------------------------------------------------

    def test_agent_partial_payment_prorated(self):
        """Pago parcial: la retención se prorratea por el total del documento,
        el write-off es EXACTAMENTE la retención y la factura queda PARCIAL
        (el resto abierto), sin inflar la cuenta de retenciones."""
        self._enable_spe()
        bill = self._create_bill(self.vendor)
        total = bill.amount_total
        expected_full_wh = self.company.currency_id.round(bill.amount_tax * 0.75)

        wizard = self._register_wizard(bill)
        self.assertAlmostEqual(wizard.l10n_ve_iva_wh_amount, expected_full_wh, places=2)

        wizard.amount = total / 2.0
        expected_wh = self.company.currency_id.round(expected_full_wh / 2.0)
        self.assertAlmostEqual(wizard.l10n_ve_iva_wh_amount, expected_wh, places=2)

        action = wizard.action_create_payments()
        payment = self.env["account.payment"].browse(action["res_id"])
        # Banco por el neto del pago parcial.
        self.assertAlmostEqual(payment.amount, total / 2.0 - expected_wh, places=2)
        # Write-off EXACTO por la retención (no por toda la diferencia).
        writeoff_lines = self._agent_writeoff_lines(payment)
        self.assertEqual(len(writeoff_lines), 1)
        self.assertAlmostEqual(writeoff_lines.credit, expected_wh, places=2)
        # La factura NO queda saldada: el resto sigue abierto.
        self.assertAlmostEqual(bill.amount_residual, total / 2.0, places=2)
        self.assertEqual(bill.payment_state, "partial")

        voucher = self.env["l10n.ve.iva.wh.voucher"].search([
            ("payment_id", "=", payment.id),
        ])
        self.assertAlmostEqual(voucher.withheld_amount, expected_wh, places=2)

    def test_agent_second_payment_not_rewithheld(self):
        """El segundo pago parcial no vuelve a retener lo ya retenido: solo el
        IVA pendiente (total por tasa menos comprobantes 'posted' previos)."""
        self._enable_spe()
        bill = self._create_bill(self.vendor)
        total = bill.amount_total
        theoretical_wh = self.company.currency_id.round(bill.amount_tax * 0.75)

        wizard = self._register_wizard(bill)
        wizard.amount = total / 2.0
        first_wh = wizard.l10n_ve_iva_wh_amount
        wizard.action_create_payments()
        self.assertAlmostEqual(bill.amount_residual, total / 2.0, places=2)

        wizard2 = self._register_wizard(bill)
        expected_pending = theoretical_wh - first_wh
        self.assertAlmostEqual(wizard2.l10n_ve_iva_wh_amount, expected_pending, places=2)

        action = wizard2.action_create_payments()
        payment2 = self.env["account.payment"].browse(action["res_id"])
        self.assertAlmostEqual(
            payment2.amount, total / 2.0 - expected_pending, places=2,
        )
        self.assertEqual(bill.amount_residual, 0.0)

        vouchers = self.env["l10n.ve.iva.wh.voucher"].search([
            ("move_ids", "in", bill.id),
        ])
        self.assertEqual(len(vouchers), 2)
        # La retención acumulada nunca supera el 75% del IVA causado.
        self.assertAlmostEqual(
            sum(vouchers.mapped("withheld_amount")), theoretical_wh, places=2,
        )

    # -------------------------------------------------------------------------
    # Flujo sujeto retenido (cliente SPE nos retiene)
    # -------------------------------------------------------------------------

    def test_received_withholding_flow(self):
        invoice = self._create_customer_invoice(self.customer)
        wh_received = self.company.currency_id.round(invoice.amount_tax * 0.75)
        wizard = self._register_wizard(
            invoice,
            l10n_ve_iva_wh_received_amount=wh_received,
            l10n_ve_iva_wh_voucher_number="20260100000001",
        )
        action = wizard.action_create_payments()
        payment = self.env["account.payment"].browse(action["res_id"])
        self.assertAlmostEqual(payment.amount, invoice.amount_total - wh_received, places=2)
        self.assertEqual(invoice.amount_residual, 0.0)
        writeoff_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id == self.received_account,
        )
        self.assertEqual(len(writeoff_lines), 1)
        self.assertAlmostEqual(writeoff_lines.debit, wh_received, places=2)
        # Campos persistidos en el pago (interfaz para los libros fiscales).
        self.assertAlmostEqual(
            payment.l10n_ve_iva_wh_received_amount, wh_received, places=2,
        )
        self.assertEqual(payment.l10n_ve_iva_wh_received_number, "20260100000001")

    def test_received_voucher_number_format(self):
        invoice = self._create_customer_invoice(self.customer)
        with self.assertRaises(ValidationError):
            self._register_wizard(
                invoice,
                l10n_ve_iva_wh_received_amount=10.0,
                l10n_ve_iva_wh_voucher_number="MAL-FORMATO-14",
            )

    # -------------------------------------------------------------------------
    # Exportación TXT 99035
    # -------------------------------------------------------------------------

    def test_txt_export_16_columns(self):
        self._enable_spe()
        bill = self._create_bill(self.vendor)
        wizard = self._register_wizard(bill)
        wizard.action_create_payments()

        export = self.env["l10n.ve.iva.wh.txt.export"].create({
            "company_id": self.company.id,
            "date_from": "2026-01-01",
            "date_to": "2026-01-15",
        })
        export.action_generate()
        self.assertTrue(export.file_data)
        content = base64.b64decode(export.file_data).decode("utf-8")
        lines = [line for line in content.splitlines() if line]
        self.assertEqual(len(lines), 1)
        for line in lines:
            columns = line.split("\t")
            self.assertEqual(len(columns), 16)
            self.assertEqual(columns[0], "J123456789")   # RIF agente sin guiones
            self.assertEqual(columns[1], "202601")       # período AAAAMM
            self.assertEqual(columns[2], "2026-01-10")   # fecha factura AAAA-MM-DD
            self.assertEqual(columns[3], "C")            # tipo de operación
            self.assertEqual(columns[4], "01")           # tipo de documento factura
            self.assertEqual(columns[5], "V987654321")   # RIF retenido
            self.assertEqual(columns[7], "0")            # nº control ausente -> 0
            self.assertEqual(len(columns[12]), 14)       # nº comprobante 14 dígitos
            self.assertEqual(columns[11], "0")           # sin doc afectado
            self.assertEqual(columns[15], "0")           # nº expediente
            for idx in (8, 9, 10, 13, 14):               # montos 15,2 con punto
                self.assertRegex(columns[idx], r"^\d+\.\d{2}$")

    def test_txt_export_multi_rate_one_line_per_rate(self):
        """Factura con dos alícuotas (16% y 8%): el TXT emite UNA línea por
        alícuota por documento, con la alícuota LEGAL en la col. 15 (no una
        tasa mezclada) y base/retención por alícuota. La col. 11 (IVA
        retenido) se expresa en Bs a la tasa de la fecha del COMPROBANTE."""
        self._enable_spe()
        tax16 = self.env["account.tax"].create({
            "name": "IVA 16% (Compras) test",
            "amount": 16.0,
            "amount_type": "percent",
            "type_tax_use": "purchase",
        })
        tax8 = self.env["account.tax"].create({
            "name": "IVA 8% (Compras) test",
            "amount": 8.0,
            "amount_type": "percent",
            "type_tax_use": "purchase",
        })
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.vendor.id,
            "invoice_date": "2026-01-10",
            "date": "2026-01-10",
            "invoice_line_ids": [
                Command.create({
                    "name": "Línea 16%",
                    "quantity": 1.0,
                    "price_unit": 1000.0,
                    "tax_ids": [Command.set(tax16.ids)],
                }),
                Command.create({
                    "name": "Línea 8%",
                    "quantity": 1.0,
                    "price_unit": 500.0,
                    "tax_ids": [Command.set(tax8.ids)],
                }),
            ],
        })
        bill.action_post()
        # IVA causado: 160 (16%) + 40 (8%) = 200 -> retención 75% = 150.
        self.assertAlmostEqual(bill.amount_tax, 200.0, places=2)

        wizard = self._register_wizard(bill)
        self.assertAlmostEqual(wizard.l10n_ve_iva_wh_amount, 150.0, places=2)
        wizard.action_create_payments()

        export = self.env["l10n.ve.iva.wh.txt.export"].create({
            "company_id": self.company.id,
            "date_from": "2026-01-01",
            "date_to": "2026-01-15",
        })
        export.action_generate()
        content = base64.b64decode(export.file_data).decode("utf-8")
        lines = [line for line in content.splitlines() if line]
        self.assertEqual(len(lines), 2)

        def to_ves(amount, conv_date):
            return self.company.currency_id._convert(
                amount, self.ves, self.company, conv_date,
            )

        doc_date = date(2026, 1, 10)
        voucher_date = date(2026, 1, 15)
        by_rate = {}
        for line in lines:
            columns = line.split("\t")
            self.assertEqual(len(columns), 16)
            self.assertEqual(len(columns[12]), 14)  # mismo comprobante en ambas
            by_rate[columns[14]] = columns
        # Alícuotas LEGALES, no una tasa mezclada (p.ej. 13.33).
        self.assertEqual(set(by_rate), {"8.00", "16.00"})
        # Base por alícuota (Bs a la fecha del documento).
        self.assertAlmostEqual(
            float(by_rate["16.00"][9]), to_ves(1000.0, doc_date), places=2,
        )
        self.assertAlmostEqual(
            float(by_rate["8.00"][9]), to_ves(500.0, doc_date), places=2,
        )
        # IVA retenido por alícuota (Bs a la fecha del COMPROBANTE/pago):
        # 150 * 160/200 = 120 y 150 * 40/200 = 30.
        self.assertAlmostEqual(
            float(by_rate["16.00"][10]), to_ves(120.0, voucher_date), places=2,
        )
        self.assertAlmostEqual(
            float(by_rate["8.00"][10]), to_ves(30.0, voucher_date), places=2,
        )

    def test_report_lines_credit_note_affected_uses_ref(self):
        """Col. 12 del TXT (documento afectado de una NC): mismo criterio que
        la col. 7, es decir la ref del proveedor, no el nombre interno."""
        self._enable_spe()
        bill = self._create_bill(self.vendor, ref="FAC-00123")
        refund = self.env["account.move"].create({
            "move_type": "in_refund",
            "partner_id": self.vendor.id,
            "invoice_date": "2026-01-12",
            "date": "2026-01-12",
            "ref": "NC-00777",
            "reversed_entry_id": bill.id,
            "invoice_line_ids": [Command.create({
                "name": "Devolución parcial",
                "quantity": 1.0,
                "price_unit": 100.0,
                "tax_ids": [Command.set(self.company_data["default_tax_purchase"].ids)],
            })],
        })
        refund.action_post()
        voucher = self.env["l10n.ve.iva.wh.voucher"].create({
            "date": "2026-01-15",
            "company_id": self.company.id,
            "partner_id": self.vendor.id,
            "move_ids": [Command.set(refund.ids)],
            "withheld_amount": 0.0,
        })
        line = voucher._l10n_ve_get_report_lines()[0]
        self.assertEqual(line["doc_type"], "03")
        self.assertEqual(line["doc_number"], "NC-00777")
        self.assertEqual(line["affected"], "FAC-00123")

    # -------------------------------------------------------------------------
    # Secuencia del comprobante
    # -------------------------------------------------------------------------

    def test_voucher_sequence_monthly_reset_and_per_company(self):
        """El correlativo AAAAMM+8 reinicia en 00000001 cada mes (use_date_range
        con rangos mensuales) y es independiente por compañía."""
        Voucher = self.env["l10n.ve.iva.wh.voucher"]
        n1 = Voucher._l10n_ve_next_voucher_number("2026-03-05", company=self.company)
        n2 = Voucher._l10n_ve_next_voucher_number("2026-03-20", company=self.company)
        n3 = Voucher._l10n_ve_next_voucher_number("2026-04-02", company=self.company)
        self.assertEqual(n1, "20260300000001")
        self.assertEqual(n2, "20260300000002")
        self.assertEqual(n3, "20260400000001")

        other_company = self.env["res.company"].create({"name": "Otra Compañía VE"})
        m1 = Voucher._l10n_ve_next_voucher_number("2026-03-25", company=other_company)
        self.assertEqual(m1, "20260300000001")

        sequences = self.env["ir.sequence"].sudo().search([
            ("code", "=", "l10n.ve.iva.wh.voucher"),
            ("company_id", "in", [self.company.id, other_company.id]),
        ])
        self.assertEqual(
            set(sequences.mapped("company_id").ids),
            {self.company.id, other_company.id},
        )
        self.assertTrue(all(sequences.mapped("use_date_range")))

    # -------------------------------------------------------------------------
    # Integración con l10n_ve_bw_wh_islr: ambas retenciones en el MISMO pago
    # -------------------------------------------------------------------------

    def test_combined_iva_and_islr_withholding_same_payment(self):
        """Retención de IVA (75%) + retención de ISLR (2% servicios PJ) aplicadas
        en el mismo pago: cada módulo aporta SU línea de write-off a su cuenta,
        las bases no se contaminan entre sí y la factura queda saldada."""
        if "l10n.ve.islr.concept" not in self.env:
            self.skipTest("l10n_ve_bw_wh_islr no está instalado")
        self._enable_spe()

        islr_account = self.env["account.account"].create({
            "name": "Retenciones de ISLR por Enterar (test)",
            "code": "T210401",
            "account_type": "liability_current",
        })
        self.company.l10n_ve_islr_wh_account_id = islr_account
        concept = self.env["l10n.ve.islr.concept"].create({
            "name": "Servicios (test integración)",
            "seniat_code_pj": "055",
            "seniat_code_pn": "053",
            "rate_pj_dom": 2.0,
            "rate_pn_res": 1.0,
            "apply_subtrahend": False,
        })
        self.vendor.l10n_ve_person_type = "pj_dom"
        self.vendor.l10n_ve_islr_concept_id = concept

        bill = self._create_bill(self.vendor)
        currency = self.company.currency_id
        expected_iva_wh = currency.round(bill.amount_tax * 0.75)
        # Base ISLR = porción SIN IVA del pago (pago total => base = untaxed).
        expected_islr_wh = currency.round(bill.amount_untaxed * 0.02)
        self.assertGreater(expected_iva_wh, 0.0)
        self.assertGreater(expected_islr_wh, 0.0)

        wizard = self._register_wizard(bill)
        self.assertAlmostEqual(wizard.l10n_ve_iva_wh_amount, expected_iva_wh, places=2)
        self.assertAlmostEqual(wizard.l10n_ve_islr_amount, expected_islr_wh, places=2)

        action = wizard.action_create_payments()
        payment = self.env["account.payment"].browse(action["res_id"])
        # Liquidez por el neto de AMBAS retenciones.
        self.assertAlmostEqual(
            payment.amount,
            bill.amount_total - expected_iva_wh - expected_islr_wh,
            places=2,
        )
        # Una línea de write-off POR CADA retención, cada una en SU cuenta.
        iva_lines = self._agent_writeoff_lines(payment)
        islr_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id == islr_account,
        )
        self.assertEqual(len(iva_lines), 1)
        self.assertEqual(len(islr_lines), 1)
        self.assertAlmostEqual(iva_lines.credit, expected_iva_wh, places=2)
        self.assertAlmostEqual(islr_lines.credit, expected_islr_wh, places=2)
        # Factura 100% saldada (pago completo) y un comprobante de cada tipo.
        self.assertEqual(bill.amount_residual, 0.0)
        iva_voucher = self.env["l10n.ve.iva.wh.voucher"].search(
            [("payment_id", "=", payment.id)],
        )
        islr_voucher = self.env["l10n.ve.islr.voucher"].search(
            [("payment_id", "=", payment.id)],
        )
        self.assertEqual(len(iva_voucher), 1)
        self.assertEqual(len(islr_voucher), 1)
        self.assertAlmostEqual(iva_voucher.withheld_amount, expected_iva_wh, places=2)
