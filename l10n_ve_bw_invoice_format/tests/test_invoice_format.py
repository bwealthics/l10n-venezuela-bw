# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_invoice_format. License LGPL-3.
from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestInvoiceFormat(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        # El país fiscal de la compañía se deja como viene del common: nada de
        # lo que se prueba aquí depende de él, y moverlo a VE rompe el common
        # por dos vías (sin grupos fiscales VE el tax_group_id queda nulo, y
        # los impuestos ya creados dejan de casar con la posición fiscal).
        cls.tax_16 = cls.env["account.tax"].create({
            "name": "IVA 16% — prueba",
            "amount": 16.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.tax_exempt = cls.env["account.tax"].create({
            "name": "Exento (Ventas) — prueba",
            "amount": 0.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        partner = cls.env["res.partner"].with_context(
            no_vat_validation=True).create({
                "name": "Cliente VE, C.A.",
                "vat": "J-12345678-9",
                "country_id": cls.env.ref("base.ve").id,
            })
        cls.invoice = cls.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": fields.Date.to_date("2026-07-25"),
            "l10n_ve_control_number": "00-00001234",
            "invoice_line_ids": [
                Command.create({
                    "name": "Plato gravado",
                    "quantity": 1.0,
                    "price_unit": 100.0,
                    "tax_ids": [Command.set(cls.tax_16.ids)],
                }),
                Command.create({
                    "name": "Alimento exento",
                    "quantity": 1.0,
                    "price_unit": 50.0,
                    "tax_ids": [Command.set(cls.tax_exempt.ids)],
                }),
            ],
        })
        cls.invoice.action_post()

    def test_vat_label_is_rif(self):
        # Sin esto el PDF rotula el RIF del comprador como "Tax ID".
        self.assertEqual(self.env.ref("base.ve").vat_label, "RIF")

    def test_legal_datetime_without_hour(self):
        # Sin sello de la máquina no se conoce la hora: se emite solo la
        # fecha. Nunca se inventa una hora en un documento fiscal.
        self.assertEqual(self.invoice._l10n_ve_legal_datetime(), "25-07-2026")

    def test_legal_datetime_with_machine_stamp(self):
        if "l10n_ve_fiscal_date" not in self.env["account.move"]._fields:
            self.skipTest("l10n_ve_bw_fiscal_printer no instalado")
        self.invoice.with_context(
            l10n_ve_control_writeback=True,
        ).l10n_ve_fiscal_date = "2026-07-25 15:14:07"
        self.assertEqual(
            self.invoice._l10n_ve_legal_datetime(), "25-07-2026 03.14.07 p.m")

    def test_exempt_predicate(self):
        lines = self.invoice.invoice_line_ids
        taxed = lines.filtered(lambda line: line.tax_ids == self.tax_16)
        exempt = lines.filtered(lambda line: line.tax_ids == self.tax_exempt)
        self.assertFalse(taxed._l10n_ve_is_exempt())
        self.assertTrue(exempt._l10n_ve_is_exempt())
        # Una línea SIN impuestos también es "(E)": la norma marca igual a las
        # exentas, las exoneradas y las no sujetas. En borrador, porque una
        # línea contabilizada ya no admite tocarle los impuestos.
        draft = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.invoice.partner_id.id,
            "invoice_line_ids": [Command.create({
                "name": "Sin impuestos",
                "quantity": 1.0,
                "price_unit": 10.0,
                "tax_ids": [Command.clear()],
            })],
        })
        self.assertTrue(draft.invoice_line_ids._l10n_ve_is_exempt())

    def test_report_renders_legal_marks(self):
        html = self.env["ir.actions.report"]._render_qweb_html(
            "account.report_invoice", self.invoice.ids)[0].decode()
        self.assertIn("(E)", html)
        self.assertIn("00-00001234", html)
        self.assertIn("25-07-2026", html)

    # --- Equivalente en bolívares -------------------------------------

    def _setup_bs(self, rate=100.0):
        """Bolívar de referencia con una tasa conocida a la fecha de la factura.

        100 Bs/USD para que las cuentas del test se lean a simple vista:
        150 sin impuestos → 15.000, 16 de IVA → 1.600, 166 de total → 16.600.
        """
        bs = self.env["res.currency"].with_context(
            active_test=False).search([("name", "=", "VES")], limit=1)
        bs.active = True
        self.env["res.currency.rate"].create({
            "name": self.invoice.invoice_date,
            "currency_id": bs.id,
            "rate": rate,
            "company_id": self.company.id,
        })
        self.company.l10n_ve_bs_currency_id = bs
        return bs

    def test_bs_amounts_use_document_date(self):
        self._setup_bs()
        amounts = self.invoice._l10n_ve_bs_amounts()
        self.assertEqual(amounts["rate"], 100.0)
        self.assertEqual(amounts["date"], self.invoice.invoice_date)
        self.assertEqual(amounts["untaxed"], self.invoice.amount_untaxed * 100)
        self.assertEqual(amounts["tax"], self.invoice.amount_tax * 100)
        self.assertEqual(amounts["total"], self.invoice.amount_total * 100)
        # Factura emitida y sin cobrar: saldo == total, no aporta nada.
        self.assertFalse(amounts["show_residual"])

    def test_bs_amounts_empty_without_currency(self):
        # Sin moneda de referencia no se imprime nada.
        self.company.l10n_ve_bs_currency_id = False
        self.assertFalse(self.invoice._l10n_ve_bs_amounts())

    def test_bs_amounts_empty_when_document_already_in_bs(self):
        # Convertir un comprobante a su propia moneda no aporta nada.
        self.company.l10n_ve_bs_currency_id = self.invoice.currency_id
        self.assertFalse(self.invoice._l10n_ve_bs_amounts())

    def test_bs_amounts_empty_without_rate(self):
        """Sin tasa cargada NO se imprime el bloque.

        Es el caso que de verdad muerde: `_get_rates` acaba en
        COALESCE(..., 1.0), así que una moneda sin tasas convierte a la par y
        el comprobante saldría con el total en dólares rotulado «Bs».
        """
        bs = self.env["res.currency"].with_context(
            active_test=False).search([("name", "=", "VES")], limit=1)
        bs.rate_ids.unlink()
        self.company.l10n_ve_bs_currency_id = bs
        self.assertFalse(self.invoice._l10n_ve_bs_amounts())

    def test_report_renders_bs_block_and_rate_note(self):
        self._setup_bs()
        html = self.env["ir.actions.report"]._render_qweb_html(
            "account.report_invoice", self.invoice.ids)[0].decode()
        self.assertIn("Total en Bs", html)
        self.assertIn("Monto sin impuestos en Bs", html)
        # La nota de la tasa va SIEMPRE con el bloque: sin ella el equivalente
        # en bolívares no es verificable.
        self.assertIn("Tasa de cambio aplicada", html)
        self.assertIn("25-07-2026", html)

    # --- Detalle de impuesto por línea --------------------------------

    def test_report_line_tax_detail_toggle(self):
        self.assertTrue(self.company.l10n_ve_show_line_tax_detail)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "account.report_invoice", self.invoice.ids)[0].decode()
        self.assertIn("Sin impuestos", html)
        self.assertIn("Impuesto", html)

        self.company.l10n_ve_show_line_tax_detail = False
        html = self.env["ir.actions.report"]._render_qweb_html(
            "account.report_invoice", self.invoice.ids)[0].decode()
        self.assertNotIn("Sin impuestos", html)

    def test_report_renders_printer_block(self):
        self.company.write({
            "l10n_ve_printer_name": "Imprenta Digital de Prueba, C.A.",
            "l10n_ve_printer_vat": "J-30000000-1",
            "l10n_ve_printer_auth_number": "SNAT/2024/0099",
            "l10n_ve_printer_auth_date": fields.Date.to_date("2025-01-15"),
        })
        html = self.env["ir.actions.report"]._render_qweb_html(
            "account.report_invoice", self.invoice.ids)[0].decode()
        self.assertIn("Imprenta Digital de Prueba, C.A.", html)
        self.assertIn("SNAT/2024/0099", html)
        self.assertIn("15-01-2025", html)
