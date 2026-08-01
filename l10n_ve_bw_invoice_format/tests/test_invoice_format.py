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
