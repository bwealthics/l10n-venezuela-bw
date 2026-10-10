# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
"""Pruebas de los libros contables (Diario, Mayor y Balance de Comprobación).

Se prueban los métodos de CÁLCULO del asistente (`_compute_*`, que devuelven
listas y diccionarios), no solo el archivo: así un descuadre se ve como un
número y no como una celda de Excel.

Aislamiento: las cifras exactas se afirman solo sobre cuentas creadas aquí
(códigos 9911xx a 9914xx), porque la base de pruebas puede traer asientos de
demostración sobre las cuentas del plan. Los totales del Balance se afirman
como invariantes (Σ debe = Σ haber, Σ saldos = 0), que valen con cualquier
dato de fondo, y el único dato que depende del resto de la base (la fila de
resultados de ejercicios anteriores) se compara contra una línea base tomada
antes de crear los asientos de la prueba.

Datos (tasas del módulo común: 2025-06-10 = 400, 2025-12-15 = 450,
2026-07-25 = 610,5, 2026-07-27 = 611,37; ejercicio = año natural):

* E0  2025-01-15  A2 / A3 por 7 USD, fecha SIN tasa (Bs = 0).
* E1  2025-06-10  activo A debe 100 / ingreso I haber 100 (ejercicio anterior).
* E2  2026-03-02  A debe 20 / I haber 20 (mismo ejercicio, antes del período).
* E3  2026-07-25  A debe 30 / I haber 30 (período).
* E5  2026-07-27  gasto X debe 10,01 / A haber 10,01 (período, con redondeo).
* E4  2026-08-01  A debe 5 / I haber 5 (posterior al período: no cuenta).
* E6  borrador en el período, A debe 999: un borrador no es registro contable.
* Mixto 2026-07-25: línea VES de 100 USD con 61.000 Bs y líneas USD por 100
  (a 610,5 son 61.050 Bs): descuadre real de 50 Bs que debe quedar a la vista.
* Una factura de cliente del 2026-07-25 (100 con IVA 16 % + 50 exentos).
"""
import base64
import io
import zipfile
from datetime import date

from odoo import Command
from odoo.tests import tagged

from .test_dual_currency import DualCurrencyCommon

try:
    import openpyxl
except ImportError:  # el XLSX también se verifica por el zip, sin openpyxl
    openpyxl = None

SHEETS = (
    "Libro Diario", "Libro Mayor", "Balance de Comprobación", "Advertencias")


@tagged("post_install", "-at_install")
class TestLegalBooks(DualCurrencyCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ejercicio fiscal = año natural: las cifras de abajo lo suponen.
        cls.company.write({
            "fiscalyear_last_day": 31, "fiscalyear_last_month": "12"})
        Account = cls.env["account.account"]

        def account(code, name, account_type):
            return Account.create({
                "code": code,
                "name": name,
                "account_type": account_type,
                "company_ids": [Command.set(cls.company.ids)],
            })

        cls.acc_a = account("991100", "Prueba A (activo)", "asset_current")
        cls.acc_a2 = account("991101", "Prueba A2 (activo)", "asset_current")
        cls.acc_a3 = account("991102", "Prueba A3 (activo)", "asset_current")
        cls.acc_i = account("991200", "Prueba I (ingreso)", "income")
        cls.acc_i2 = account("991201", "Prueba I2 (ingreso)", "income")
        cls.acc_x = account("991300", "Prueba X (gasto)", "expense")
        cls.acc_r = account("991400", "Prueba R (por cobrar)", "asset_receivable")

        # Línea base de «resultados de ejercicios anteriores» ANTES de crear
        # los asientos de la prueba (la base puede traer datos propios).
        cls.baseline_prior = cls._prior_results(cls._wizard()._compute_trial_balance())

        partner = {"partner_id": cls.partner.id}
        cls.e0 = cls._entry("2025-01-15", [
            (cls.acc_a2, 7.0, 0.0), (cls.acc_a3, 0.0, 7.0)])
        cls.e1 = cls._entry("2025-06-10", [
            (cls.acc_a, 100.0, 0.0), (cls.acc_i, 0.0, 100.0)])
        cls.e2 = cls._entry("2026-03-02", [
            (cls.acc_a, 20.0, 0.0), (cls.acc_i, 0.0, 20.0)])
        cls.e3 = cls._entry("2026-07-25", [
            (cls.acc_a, 30.0, 0.0), (cls.acc_i, 0.0, 30.0)])
        cls.e5 = cls._entry("2026-07-27", [
            (cls.acc_x, 10.01, 0.0), (cls.acc_a, 0.0, 10.01)])
        cls.e4 = cls._entry("2026-08-01", [
            (cls.acc_a, 5.0, 0.0), (cls.acc_i, 0.0, 5.0)])
        cls.mixed = cls._entry("2026-07-25", [
            (cls.acc_a2, 100.0, 0.0, {
                "currency_id": cls.bs.id, "amount_currency": 61000.0,
                **partner}),
            (cls.acc_r, 0.0, 60.0, partner),
            (cls.acc_i2, 0.0, 40.0, partner),
        ])
        # Borrador: no se postea.
        cls.draft = cls.env["account.move"].create({
            "move_type": "entry",
            "journal_id": cls.company_data["default_journal_misc"].id,
            "date": "2026-07-26",
            "line_ids": [
                Command.create({"account_id": cls.acc_a.id, "debit": 999.0,
                                "credit": 0.0, "name": "borrador"}),
                Command.create({"account_id": cls.acc_i.id, "debit": 0.0,
                                "credit": 999.0, "name": "borrador"}),
            ],
        })
        cls.invoice = cls._invoice("2026-07-25")
        cls.test_moves = (
            cls.e0 | cls.e1 | cls.e2 | cls.e3 | cls.e4 | cls.e5 | cls.mixed
            | cls.invoice)
        cls.wizard = cls._wizard()

    # ------------------------------------------------------------------
    @classmethod
    def _wizard(cls, date_from="2026-07-01", date_to="2026-07-31", **vals):
        return cls.env["l10n.ve.legal.books.wizard"].create({
            "company_id": cls.company.id,
            "date_from": date_from,
            "date_to": date_to,
            **vals,
        })

    @staticmethod
    def _prior_results(trial):
        """(USD, Bs) de la fila de resultados anteriores; (0, 0) si no hay."""
        rows = [r for r in trial["rows"] if r["prior_results"]]
        if not rows:
            return 0.0, 0.0
        return rows[0]["initial_usd"], rows[0]["initial_bs"]

    def _row(self, trial, code):
        rows = [r for r in trial["rows"] if r["code"] == code]
        self.assertEqual(len(rows), 1, "Fila de la cuenta %s" % code)
        return rows[0]

    def assertRow(self, row, **expected):
        """Compara los campos pedidos de una fila (USD a 2 decimales y Bs a 2)."""
        for key, value in expected.items():
            self.assertAlmostEqual(
                row[key], value, places=2,
                msg="%s de %s" % (key, row["code"]))

    # --- Balance de comprobación ----------------------------------------

    def test_trial_balance_account_rows(self):
        trial = self.wizard._compute_trial_balance()
        # A: todo lo anterior al período, en ambos ejercicios.
        self.assertRow(
            self._row(trial, "991100"),
            initial_usd=120.0, initial_bs=49000.0,       # 100×400 + 20×450
            debit_usd=30.0, debit_bs=18315.0,            # 30×610,5
            credit_usd=10.01, credit_bs=6119.81,         # 10,01×611,37
            final_usd=139.99, final_bs=61195.19)
        # I (resultado): el saldo inicial arranca en el ejercicio, no antes.
        self.assertRow(
            self._row(trial, "991200"),
            initial_usd=-20.0, initial_bs=-9000.0,       # solo E2 (E1 es 2025)
            debit_usd=0.0, credit_usd=30.0, credit_bs=18315.0,
            final_usd=-50.0, final_bs=-27315.0)
        # X: gasto sin saldo inicial.
        self.assertRow(
            self._row(trial, "991300"),
            initial_usd=0.0, initial_bs=0.0,
            debit_usd=10.01, debit_bs=6119.81, credit_usd=0.0,
            final_usd=10.01, final_bs=6119.81)

    def test_trial_balance_excludes_drafts_and_later_dates(self):
        """Ni el borrador (999) ni el asiento posterior al período (5) cuentan."""
        trial = self.wizard._compute_trial_balance()
        row_a = self._row(trial, "991100")
        self.assertAlmostEqual(row_a["debit_usd"], 30.0, places=2)
        self.assertAlmostEqual(row_a["final_usd"], 139.99, places=2)

    def test_trial_balance_is_balanced_in_both_currencies(self):
        trial = self.wizard._compute_trial_balance()
        totals = trial["totals"]
        usd, bs = self.company.currency_id, self.bs
        # Σ debe = Σ haber del período.
        self.assertTrue(usd.is_zero(totals["debit_usd"] - totals["credit_usd"]))
        self.assertTrue(bs.is_zero(totals["debit_bs"] - totals["credit_bs"]))
        # Σ saldos iniciales y finales = 0 (la fila de resultados anteriores
        # es lo que hace que los iniciales sumen cero).
        self.assertTrue(usd.is_zero(totals["initial_usd"]))
        self.assertTrue(bs.is_zero(totals["initial_bs"]))
        self.assertTrue(usd.is_zero(totals["final_usd"]))
        self.assertTrue(bs.is_zero(totals["final_bs"]))
        # Las verificaciones del asistente lo confirman, una por una.
        self.assertEqual(len(trial["checks"]), 6)
        for check in trial["checks"]:
            self.assertTrue(check["ok"], check["label"])
            self.assertEqual(check["value"], 0.0, check["label"])

    def test_income_accounts_start_at_fiscal_year(self):
        """Saldo inicial de resultados desde el ejercicio; lo previo, aparte."""
        trial = self.wizard._compute_trial_balance()
        self.assertEqual(trial["fy_start"], date(2026, 1, 1))
        # El ingreso de 2025 (E1: 100 USD, 40.000 Bs) no está en la cuenta I
        # (ver test_trial_balance_account_rows) sino en la fila de resultados
        # anteriores, asignada a equity_unaffected.
        prior_rows = [r for r in trial["rows"] if r["prior_results"]]
        self.assertEqual(len(prior_rows), 1)
        self.assertEqual(prior_rows[0]["type"], "equity_unaffected")
        self.assertFalse(prior_rows[0]["debit_usd"])
        self.assertFalse(prior_rows[0]["credit_usd"])
        base_usd, base_bs = self.baseline_prior
        usd, bs = self._prior_results(trial)
        self.assertAlmostEqual(usd - base_usd, -100.0, places=2)
        self.assertAlmostEqual(bs - base_bs, -40000.0, places=2)
        # Contraprueba: pidiendo un período de 2025 posterior a E1, el ingreso
        # SÍ es saldo inicial de la cuenta I, porque es del mismo ejercicio.
        trial_2025 = self._wizard("2025-07-01", "2025-12-31")._compute_trial_balance()
        self.assertEqual(trial_2025["fy_start"], date(2025, 1, 1))
        self.assertRow(
            self._row(trial_2025, "991200"),
            initial_usd=-100.0, initial_bs=-40000.0)

    # --- Libro mayor ----------------------------------------------------

    def test_ledger_matches_trial_balance(self):
        wizard = self.wizard
        trial = wizard._compute_trial_balance()
        ledger = wizard._compute_ledger(trial, wizard._get_period_lines())
        self.assertEqual(len(ledger), len(trial["rows"]))
        for account in ledger:
            if account["lines"]:
                last = account["lines"][-1]
                # El saldo corrido termina en el saldo final del Balance.
                self.assertAlmostEqual(
                    last["balance_usd"], account["final_usd"], places=2,
                    msg=account["code"])
                self.assertAlmostEqual(
                    last["balance_bs"], account["final_bs"], places=2,
                    msg=account["code"])
            else:
                self.assertAlmostEqual(
                    account["initial_usd"], account["final_usd"], places=2)
                self.assertAlmostEqual(
                    account["initial_bs"], account["final_bs"], places=2)
        # Cuenta A: dos movimientos en el período, con saldo corrido.
        account_a = next(a for a in ledger if a["code"] == "991100")
        self.assertEqual(len(account_a["lines"]), 2)
        first, second = account_a["lines"]
        self.assertAlmostEqual(first["balance_usd"], 150.0, places=2)
        self.assertAlmostEqual(first["balance_bs"], 67315.0, places=2)
        self.assertAlmostEqual(second["balance_usd"], 139.99, places=2)
        self.assertAlmostEqual(second["balance_bs"], 61195.19, places=2)

    # --- Libro diario ---------------------------------------------------

    def test_journal_is_balanced_per_move_and_in_total(self):
        journal = self.wizard._compute_journal()
        usd, bs = self.company.currency_id, self.bs
        move_ids = {move["id"] for move in journal["moves"]}
        # Asientos del período; no el de 2025/2026-03, el posterior ni el borrador.
        for move in (self.e3, self.e5, self.mixed, self.invoice):
            self.assertIn(move.id, move_ids, move.display_name)
        for move in (self.e0, self.e1, self.e2, self.e4, self.draft):
            self.assertNotIn(move.id, move_ids, move.display_name)
        for move in journal["moves"]:
            self.assertTrue(
                usd.is_zero(move["debit_usd"] - move["credit_usd"]),
                "%s no cuadra en USD" % move["name"])
            self.assertTrue(
                bs.is_zero(move["debit_bs"] - move["credit_bs"]),
                "%s no cuadra en Bs" % move["name"])
        totals = journal["totals"]
        self.assertTrue(usd.is_zero(totals["debit_usd"] - totals["credit_usd"]))
        self.assertTrue(bs.is_zero(totals["debit_bs"] - totals["credit_bs"]))
        # El asiento mixto cuadra en Bs gracias al recuadre: 61.000 en VES y
        # 61.000 repartidos en las líneas USD (36.580 + 24.420).
        mixed = next(m for m in journal["moves"] if m["id"] == self.mixed.id)
        self.assertAlmostEqual(mixed["debit_bs"], 61000.0, places=2)
        self.assertAlmostEqual(mixed["credit_bs"], 61000.0, places=2)

    def test_journal_filter_only_affects_the_journal(self):
        wizard = self.wizard
        trial_before = wizard._compute_trial_balance()
        misc = self.company_data["default_journal_misc"]
        wizard.journal_ids = [Command.set(misc.ids)]
        journal = wizard._compute_journal()
        move_ids = {move["id"] for move in journal["moves"]}
        self.assertIn(self.e3.id, move_ids)
        self.assertNotIn(self.invoice.id, move_ids)  # diario de ventas
        self.assertEqual(
            {move["journal"] for move in journal["moves"]}, {misc.name})
        # El Balance y el Mayor siguen con todos los diarios.
        self.assertEqual(
            wizard._compute_trial_balance()["totals"], trial_before["totals"])

    # --- Advertencias ---------------------------------------------------

    def test_warnings(self):
        wizard = self.wizard
        warnings = wizard._compute_warnings(wizard._compute_trial_balance())
        by_type = {}
        for item in warnings:
            by_type.setdefault(item["type"], []).append(item)

        # Asiento sin tasa (anterior al período: distorsiona saldos iniciales).
        missing = [w for w in by_type.get("Sin tasa Bs", [])
                   if w["move_id"] == self.e0.id]
        self.assertEqual(len(missing), 1)
        self.assertIn("anterior al período", missing[0]["detail"])

        # Asiento mixto: 50 Bs de recuadre, más de 1.
        adjusted = [w for w in by_type.get("Ajuste Bs mayor a 1", [])
                    if w["move_id"] == self.mixed.id]
        self.assertEqual(len(adjusted), 1)
        self.assertAlmostEqual(adjusted[0]["value"], 50.0, places=2)

        # Ningún asiento de la prueba aparece como descuadrado en Bs.
        ours = set(self.test_moves.ids)
        unbalanced = [
            w for w in warnings
            if w["type"].startswith("Asiento descuadrado") and w["move_id"] in ours]
        self.assertFalse(unbalanced)
        # Y los asientos con rate correcta no están marcados sin tasa.
        flagged = {w["move_id"] for w in by_type.get("Sin tasa Bs", [])}
        for move in self.test_moves - self.e0:
            self.assertNotIn(move.id, flagged, move.display_name)

    # --- XLSX -----------------------------------------------------------

    def test_generate_xlsx(self):
        wizard = self.wizard
        action = wizard.action_generate()
        self.assertEqual(action["res_model"], "l10n.ve.legal.books.wizard")
        self.assertEqual(action["res_id"], wizard.id)
        self.assertTrue(wizard.file)
        self.assertTrue(wizard.filename.endswith(".xlsx"))
        self.assertIn("20260701", wizard.filename)

        data = base64.b64decode(wizard.file)
        self.assertTrue(data)
        # Un XLSX es un zip: la lista de hojas está en xl/workbook.xml.
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        for name in SHEETS:
            self.assertIn(name, workbook_xml)
        if openpyxl:
            book = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
            self.assertEqual(tuple(book.sheetnames), SHEETS)
            book.close()
