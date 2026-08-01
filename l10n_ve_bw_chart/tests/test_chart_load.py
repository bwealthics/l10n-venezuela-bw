# Part of l10n_ve_bw. License LGPL-3.
from collections import Counter

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

EXPECTED_TAX_XMLIDS = [
    "ve_bw_tax_iva16_sale",
    "ve_bw_tax_iva8_sale",
    "ve_bw_tax_iva31_sale",
    "ve_bw_tax_iva0_export_sale",
    "ve_bw_tax_exento_sale",
    "ve_bw_tax_iva16_purchase",
    "ve_bw_tax_iva8_purchase",
    "ve_bw_tax_iva31_purchase",
    "ve_bw_tax_exento_purchase",
]


@tagged("post_install", "-at_install")
class TestVeBwChartLoad(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({
            "name": "Compañía de Prueba VE BW",
            "country_id": cls.env.ref("base.ve").id,
        })
        cls.env.user.company_ids |= cls.company
        cls.env["account.chart.template"].try_loading(
            "ve_bw", cls.company, install_demo=False,
        )
        cls.company_accounts = cls.env["account.account"].with_company(cls.company).search(
            cls.env["account.account"]._check_company_domain(cls.company.id),
        )

    def _account(self, code):
        account = self.company_accounts.filtered(lambda a: a.code == code)
        self.assertEqual(len(account), 1, "Debe existir exactamente una cuenta %s" % code)
        return account

    def test_template_loaded_with_six_digits(self):
        self.assertEqual(self.company.chart_template, "ve_bw")
        template_data = self.env["account.chart.template"]._get_ve_bw_template_data()
        self.assertEqual(template_data["code_digits"], "6")
        for account in self.company_accounts:
            self.assertEqual(
                len(account.code), 6,
                "La cuenta %s (%s) no tiene 6 dígitos" % (account.code, account.name),
            )

    def test_company_default_accounts(self):
        # These default-account m2o fields carry check_company=True, so they
        # only read back under the target company's own context.
        company = self.company.with_company(self.company)
        self.assertEqual(company.account_default_pos_receivable_account_id.code, "110102")
        self.assertEqual(company.income_account_id.code, "410101")
        self.assertEqual(company.expense_account_id.code, "510101")
        partner = self.env["res.partner"].with_company(self.company).create(
            {"name": "Contacto de Prueba VE"},
        )
        self.assertEqual(partner.property_account_receivable_id.code, "110101")
        self.assertEqual(partner.property_account_payable_id.code, "210101")

    def test_taxes_created(self):
        taxes = self.env["account.tax"].search([("company_id", "=", self.company.id)])
        self.assertEqual(len(taxes), 9)
        for xmlid in EXPECTED_TAX_XMLIDS:
            tax = self.env.ref("account.%s_%s" % (self.company.id, xmlid), raise_if_not_found=False)
            self.assertTrue(tax, "Impuesto %s no fue creado" % xmlid)
        self.assertEqual(self.company.account_sale_tax_id.amount, 16.0)
        self.assertEqual(self.company.account_purchase_tax_id.amount, 16.0)

    def test_no_duplicate_account_codes(self):
        duplicates = [
            code for code, count in Counter(self.company_accounts.mapped("code")).items()
            if count > 1
        ]
        self.assertFalse(duplicates, "Códigos de cuenta duplicados: %s" % duplicates)

    def test_single_equity_unaffected(self):
        unaffected = self.company_accounts.filtered(
            lambda a: a.account_type == "equity_unaffected",
        )
        self.assertEqual(len(unaffected), 1)
        self.assertEqual(unaffected.code, "330102")

    def test_stock_valuation_account_links(self):
        # Los campos de stock existen solo con stock_account instalado; el
        # template los declara igual y el loader los tolera.
        if "account_stock_variation_id" not in self.env["account.account"]._fields:
            self.skipTest("stock_account no está instalado")
        valuation = self._account("120101")
        self.assertEqual(valuation.account_stock_variation_id.code, "520102")
        self.assertEqual(valuation.account_stock_expense_id.code, "510101")
        # account_stock_valuation_id carries check_company=True: read it under
        # the target company's context.
        self.assertEqual(
            self.company.with_company(self.company).account_stock_valuation_id.code,
            "120101",
        )
