# Part of l10n_ve_bw. License LGPL-3.
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template("ve_bw")
    def _get_ve_bw_template_data(self):
        return {
            "name": "Plan 6 dígitos (VEN-NIF, BW)",
            "code_digits": "6",
            "property_account_receivable_id": "ve_bw_110101",
            "property_account_payable_id": "ve_bw_210101",
        }

    @template("ve_bw", "res.company")
    def _get_ve_bw_res_company(self):
        return {
            self.env.company.id: {
                "account_fiscal_country_id": "base.ve",
                "bank_account_code_prefix": "1014",
                "cash_account_code_prefix": "1015",
                "transfer_account_code_prefix": "1013",
                "transfer_account_id": "ve_bw_101301",
                "account_default_pos_receivable_account_id": "ve_bw_110102",
                "income_currency_exchange_account_id": "ve_bw_430101",
                "expense_currency_exchange_account_id": "ve_bw_650104",
                "account_journal_suspense_account_id": "ve_bw_101201",
                "account_journal_early_pay_discount_gain_account_id": "ve_bw_430104",
                "account_journal_early_pay_discount_loss_account_id": "ve_bw_650106",
                "default_cash_difference_income_account_id": "ve_bw_430103",
                "default_cash_difference_expense_account_id": "ve_bw_650105",
                "account_sale_tax_id": "ve_bw_tax_iva16_sale",
                "account_purchase_tax_id": "ve_bw_tax_iva16_purchase",
                "expense_account_id": "ve_bw_510101",
                "income_account_id": "ve_bw_410101",
                "account_stock_journal_id": "inventory_valuation",
                "account_stock_valuation_id": "ve_bw_120101",
                "account_production_wip_account_id": "ve_bw_120503",
            },
        }

    @template("ve_bw", "account.account")
    def _get_ve_bw_account_account(self):
        return {
            "ve_bw_120101": {
                "account_stock_variation_id": "ve_bw_520102",
                "account_stock_expense_id": "ve_bw_510101",
            },
        }

    def _post_load_data(self, template_code, company, template_data):
        res = super()._post_load_data(template_code, company, template_data)
        if template_code == "ve_bw":
            self._l10n_ve_bw_wire_cross_module_defaults(company or self.env.company)
        return res

    def _l10n_ve_bw_wire_cross_module_defaults(self, company):
        """Set company defaults from add-on modules (point_of_sale, stock_account).

        The core chart_template loader only resolves ``res.company`` account
        references for fields it can dereference during load; cross-module
        m2o defaults fall back to the (empty) company value. We wire them here
        by code, once the accounts exist, and only when their module (hence
        their field) is installed.
        """
        # account.account.code is company-dependent in Odoo 19: read it under
        # the target company or the lookup silently misses.
        Account = self.env["account.account"].with_company(company)
        company_accounts = Account.search(Account._check_company_domain(company.id))

        def by_code(code):
            return company_accounts.filtered(lambda account: account.code == code)[:1]

        mapping = {
            "account_default_pos_receivable_account_id": "110102",
            "account_stock_valuation_id": "120101",
            "account_production_wip_account_id": "120503",
        }
        vals = {}
        for fname, code in mapping.items():
            if fname in company._fields and not company[fname]:
                account = by_code(code)
                if account:
                    vals[fname] = account.id
        if vals:
            # These m2o defaults carry check_company=True: the write only
            # passes (and persists) under the target company's context.
            company.with_company(company).write(vals)
