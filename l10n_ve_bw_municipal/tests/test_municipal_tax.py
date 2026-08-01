# Part of l10n_ve_bw. License LGPL-3.
from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestL10nVeMunicipalTax(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Compañía nueva y aislada: la base imponible del período solo puede
        # provenir de los movimientos creados aquí. Moneda fija (USD) para que
        # las aserciones de conversión a Bs sean deterministas.
        cls.company = cls.env["res.company"].create({
            "name": "Municipal Test VE",
            "currency_id": cls.env.ref("base.USD").id,
        })
        cls.env.user.company_ids |= cls.company
        cls.env.user.company_id = cls.company
        cls.ves = cls.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "VES")], limit=1
        )

        Account = cls.env["account.account"].with_company(cls.company)
        cls.income_account = Account.create({
            "name": "Ventas de Bienes y Servicios",
            "code": "410101",
            "account_type": "income",
        })
        cls.income_other_account = Account.create({
            "name": "Otros Ingresos",
            "code": "430106",
            "account_type": "income_other",
        })
        cls.counterpart_account = Account.create({
            "name": "Banco de Prueba",
            "code": "101401",
            "account_type": "asset_current",
        })
        cls.expense_account = Account.create({
            "name": "Impuesto Municipal (Patente)",
            "code": "660102",
            "account_type": "expense",
        })
        cls.payable_account = Account.create({
            "name": "Impuesto Municipal por Pagar",
            "code": "210403",
            "account_type": "liability_current",
        })
        cls.journal = cls.env["account.journal"].create({
            "name": "Miscelánea de Prueba",
            "code": "MISC",
            "type": "general",
            "company_id": cls.company.id,
        })
        cls.company.write({
            "l10n_ve_municipal_name": "Valencia",
            "l10n_ve_municipal_rate": 3.0,
            "l10n_ve_municipal_minimum": 10.0,
            "l10n_ve_municipal_expense_account_id": cls.expense_account.id,
            "l10n_ve_municipal_payable_account_id": cls.payable_account.id,
            "l10n_ve_municipal_journal_id": cls.journal.id,
        })

        # Período bajo prueba: junio 2025.
        # Base esperada = 1000 + 500 - 100 (devolución) = 1400.
        cls._create_move(1000.0, date(2025, 6, 15))
        cls._create_move(500.0, date(2025, 6, 20))
        cls._create_move(-100.0, date(2025, 6, 25))
        # Excluidos: income_other, borrador, fuera de período.
        cls._create_move(300.0, date(2025, 6, 10), account=cls.income_other_account)
        cls._create_move(800.0, date(2025, 6, 12), post=False)
        cls._create_move(900.0, date(2025, 5, 15))

    @classmethod
    def _create_move(cls, amount, move_date, account=None, post=True):
        credit, debit = (amount, 0.0) if amount >= 0 else (0.0, -amount)
        move = cls.env["account.move"].with_company(cls.company).create({
            "move_type": "entry",
            "journal_id": cls.journal.id,
            "date": move_date,
            "line_ids": [
                Command.create({
                    "name": "ingreso de prueba",
                    "account_id": (account or cls.income_account).id,
                    "credit": credit,
                    "debit": debit,
                }),
                Command.create({
                    "name": "contrapartida",
                    "account_id": cls.counterpart_account.id,
                    "credit": debit,
                    "debit": credit,
                }),
            ],
        })
        if post:
            move.action_post()
        return move

    def _create_wizard(self, year=2025, month="6"):
        return self.env["l10n.ve.municipal.tax.wizard"].with_company(self.company).create({
            "company_id": self.company.id,
            "year": year,
            "month": month,
        })

    def _set_ves_rate(self, rate=None, rate_date=date(2025, 6, 30)):
        """Deja el entorno de tasas determinista: purga las tasas de VES y de
        la moneda de compañía y, si se pide, crea UNA tasa VES."""
        Rate = self.env["res.currency.rate"].sudo()
        Rate.search([
            ("currency_id", "in", (self.ves.id, self.company.currency_id.id)),
        ]).unlink()
        if rate:
            Rate.create({
                "currency_id": self.ves.id,
                "name": rate_date,
                "rate": rate,
                "company_id": self.company.id,
            })

    def test_01_base_and_tax_computation(self):
        wizard = self._create_wizard()
        wizard.action_compute()
        self.assertTrue(wizard.is_computed)
        self.assertAlmostEqual(wizard.base_amount, 1400.0, places=2)
        self.assertAlmostEqual(wizard.computed_tax, 42.0, places=2)
        self.assertAlmostEqual(wizard.tax_amount, 42.0, places=2)

    def test_02_minimum_applies_when_higher(self):
        self.company.l10n_ve_municipal_minimum = 100.0
        wizard = self._create_wizard()
        wizard.action_compute()
        self.assertAlmostEqual(wizard.computed_tax, 42.0, places=2)
        self.assertAlmostEqual(wizard.tax_amount, 100.0, places=2)

    def test_02b_mmv_minimum_applies_when_higher(self):
        # Mínimo por ordenanza: 30 veces × TCMMV 120 Bs = 3.600 Bs → 100 USD
        # a tasa 36. Mayor que el calculado (42) → aplica el mínimo.
        self._set_ves_rate(rate=36.0)
        self.company.write({
            "l10n_ve_municipal_minimum": 0.0,
            "l10n_ve_municipal_minimum_mmv": 30.0,
            "l10n_ve_municipal_tcmmv": 120.0,
        })
        wizard = self._create_wizard()
        wizard.action_compute()
        self.assertAlmostEqual(wizard.computed_tax, 42.0, places=2)
        self.assertAlmostEqual(wizard.minimum_amount, 100.0, places=2)
        self.assertAlmostEqual(wizard.tax_amount, 100.0, places=2)

    def test_02c_mmv_minimum_zero_sales_month(self):
        # Mes sin ventas (restaurante cerrado): se provisiona el mínimo MMV.
        self._set_ves_rate(rate=36.0)
        self.company.write({
            "l10n_ve_municipal_minimum": 0.0,
            "l10n_ve_municipal_minimum_mmv": 30.0,
            "l10n_ve_municipal_tcmmv": 120.0,
        })
        wizard = self._create_wizard(year=2025, month="7")  # sin movimientos
        action = wizard.action_generate_entry()
        self.assertAlmostEqual(wizard.base_amount, 0.0, places=2)
        self.assertAlmostEqual(wizard.computed_tax, 0.0, places=2)
        self.assertAlmostEqual(wizard.tax_amount, 100.0, places=2)
        move = self.env["account.move"].browse(action["res_id"])
        debit_line = move.line_ids.filtered(lambda line: line.debit)
        self.assertAlmostEqual(debit_line.debit, 100.0, places=2)

    def test_02d_minimum_is_greater_of_fixed_and_mmv(self):
        self._set_ves_rate(rate=36.0)
        self.company.write({
            "l10n_ve_municipal_minimum": 150.0,
            "l10n_ve_municipal_minimum_mmv": 30.0,
            "l10n_ve_municipal_tcmmv": 120.0,
        })
        wizard = self._create_wizard()
        wizard.action_compute()
        self.assertAlmostEqual(wizard.minimum_amount, 150.0, places=2)
        self.assertAlmostEqual(wizard.tax_amount, 150.0, places=2)

    def test_02e_mmv_without_tcmmv_raises(self):
        self.company.write({
            "l10n_ve_municipal_minimum_mmv": 30.0,
            "l10n_ve_municipal_tcmmv": 0.0,
        })
        wizard = self._create_wizard()
        with self.assertRaises(UserError):
            wizard.action_compute()

    def test_02f_mmv_without_ves_rate_raises(self):
        # Sin tasa VES real no se puede convertir el mínimo MMV a USD: error,
        # nunca el fallback 1:1.
        self._set_ves_rate(rate=None)
        self.company.write({
            "l10n_ve_municipal_minimum_mmv": 30.0,
            "l10n_ve_municipal_tcmmv": 120.0,
        })
        wizard = self._create_wizard()
        with self.assertRaises(UserError):
            wizard.action_compute()

    def test_03_generate_draft_entry(self):
        wizard = self._create_wizard()
        action = wizard.action_generate_entry()
        move = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(move.state, "draft")
        self.assertEqual(move.journal_id, self.journal)
        self.assertEqual(move.date, date(2025, 6, 30))
        # Ref estable (sin municipio): el guard de duplicados depende de ella.
        self.assertEqual(move.ref, "MUNI-2025-06")
        # El municipio va en la etiqueta de las líneas y en la narration.
        self.assertIn("Valencia", str(move.narration))
        debit_line = move.line_ids.filtered(lambda line: line.debit)
        credit_line = move.line_ids.filtered(lambda line: line.credit)
        self.assertEqual(debit_line.name, "Impuesto municipal 06/2025 Valencia")
        self.assertEqual(credit_line.name, "Impuesto municipal 06/2025 Valencia")
        self.assertEqual(debit_line.account_id, self.expense_account)
        self.assertEqual(credit_line.account_id, self.payable_account)
        self.assertAlmostEqual(debit_line.debit, 42.0, places=2)
        self.assertAlmostEqual(credit_line.credit, 42.0, places=2)

    def test_04_duplicate_period_raises(self):
        wizard = self._create_wizard()
        wizard.action_generate_entry()
        second = self._create_wizard()
        with self.assertRaises(UserError):
            second.action_generate_entry()

    def test_04b_duplicate_survives_municipality_rename_and_date_edit(self):
        # Regresión: la ref es estable — renombrar el municipio o editar la
        # fecha del asiento NO debe permitir una segunda provisión del período.
        wizard = self._create_wizard()
        action = wizard.action_generate_entry()
        move = self.env["account.move"].browse(action["res_id"])
        self.company.l10n_ve_municipal_name = "Naguanagua"
        move.date = date(2025, 7, 5)
        second = self._create_wizard()
        with self.assertRaises(UserError):
            second.action_generate_entry()

    def test_04c_cancelled_entry_allows_regeneration(self):
        wizard = self._create_wizard()
        action = wizard.action_generate_entry()
        move = self.env["account.move"].browse(action["res_id"])
        move.button_cancel()
        second = self._create_wizard()
        action2 = second.action_generate_entry()
        move2 = self.env["account.move"].browse(action2["res_id"])
        self.assertNotEqual(move2, move)
        self.assertEqual(move2.ref, "MUNI-2025-06")

    def test_05_missing_rate_raises(self):
        self.company.l10n_ve_municipal_rate = 0.0
        wizard = self._create_wizard()
        with self.assertRaises(UserError):
            wizard.action_compute()

    def test_06_missing_journal_raises(self):
        self.company.l10n_ve_municipal_journal_id = False
        wizard = self._create_wizard()
        with self.assertRaises(UserError):
            wizard.action_generate_entry()

    def test_07_amount_bs_zero_without_ves_rate(self):
        # Regresión: sin ninguna res.currency.rate de VES, _convert caería al
        # fallback 1.0 y mostraría el monto USD etiquetado como Bs.
        self._set_ves_rate(rate=None)
        wizard = self._create_wizard()
        wizard.action_compute()
        self.assertAlmostEqual(wizard.tax_amount, 42.0, places=2)
        self.assertEqual(wizard.amount_bs, 0.0)

    def test_07b_amount_bs_zero_with_default_one_to_one_rate(self):
        # Regresión: una tasa 1:1 (valor por defecto al crear el registro) no
        # es una tasa BCV real — amount_bs debe quedar en 0.
        self._set_ves_rate(rate=1.0)
        wizard = self._create_wizard()
        wizard.action_compute()
        self.assertEqual(wizard.amount_bs, 0.0)

    def test_08_amount_bs_converted_with_real_rate(self):
        self._set_ves_rate(rate=36.0)
        wizard = self._create_wizard()
        wizard.action_compute()
        self.assertAlmostEqual(wizard.tax_amount, 42.0, places=2)
        self.assertAlmostEqual(wizard.amount_bs, 1512.0, places=2)

    def test_09_menu_and_action_visible_for_acl_group(self):
        # Regresión: el menú/action deben ser visibles para el MISMO grupo al
        # que la ACL da acceso (account.group_account_invoice); el padre no
        # puede exigir un grupo que invoice no implica.
        invoice_group = self.env.ref("account.group_account_invoice")
        menu = self.env.ref("l10n_ve_bw_municipal.menu_l10n_ve_municipal_tax_wizard")
        action = self.env.ref("l10n_ve_bw_municipal.action_l10n_ve_municipal_tax_wizard")
        self.assertIn(invoice_group, menu.group_ids)
        self.assertIn(invoice_group, action.group_ids)
        parent = menu.parent_id
        while parent:
            self.assertTrue(
                not parent.group_ids or invoice_group in parent.group_ids,
                "El menú padre %s exige grupos que ocultan el wizard a %s"
                % (parent.complete_name, invoice_group.display_name),
            )
            parent = parent.parent_id
