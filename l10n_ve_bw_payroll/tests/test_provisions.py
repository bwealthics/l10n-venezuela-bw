# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import PayslipVeCommon

# Escenario: sueldo 500 USD/mes → normal diario 16,6667; ingreso 2026-01-15
# (antigüedad < 1 año → bono vac. 15 d → integral diario 18,75).
# Alícuotas mensuales: utilidades 2,5 d = 41,67 · vacaciones 1,25 d = 20,83 ·
# bono vacacional 1,25 d = 20,83. Garantía trimestral: 15 × 18,75 = 281,25.


@tagged("post_install", "-at_install")
class TestProvisionsVe(PayslipVeCommon):

    def _provision(self, date_from, date_to):
        prov = self.env["l10n.ve.payroll.provision"].create({
            "company_id": self.company.id,
            "date_from": date_from,
            "date_to": date_to,
        })
        prov.action_compute()
        return prov

    def _emp_lines(self, prov, concept, employee=None):
        return prov.line_ids.filtered(
            lambda l: l.concept == concept
            and l.employee_id == (employee or self.employee))

    def test_provision_month_with_quarter(self):
        # Julio 2026 contiene el aniversario trimestral 2026-07-15 (6 meses)
        prov = self._provision("2026-07-01", "2026-07-31")
        self.assertAlmostEqual(
            sum(self._emp_lines(prov, "utilidades").mapped("amount")), 41.67, delta=0.01)
        self.assertAlmostEqual(
            sum(self._emp_lines(prov, "vacaciones").mapped("amount")), 20.83, delta=0.01)
        self.assertAlmostEqual(
            sum(self._emp_lines(prov, "bono_vacacional").mapped("amount")), 20.83, delta=0.01)
        self.assertAlmostEqual(
            sum(self._emp_lines(prov, "prestaciones").mapped("amount")), 281.25, delta=0.01)
        self.assertFalse(self._emp_lines(prov, "intereses"),
                         "Sin saldo previo no hay intereses")

        prov.action_post()
        self.assertEqual(prov.state, "posted")
        self.assertTrue(prov.move_id)
        self.assertEqual(prov.move_id.state, "draft")
        self.assertAlmostEqual(
            sum(prov.move_id.line_ids.mapped("debit")),
            sum(prov.move_id.line_ids.mapped("credit")), places=2)
        # Débito de gasto de prestaciones y crédito de la provisión
        deb_prest = sum(prov.move_id.line_ids.filtered(
            lambda l: l.account_id.code == "610401").mapped("debit"))
        cred_prest = sum(prov.move_id.line_ids.filtered(
            lambda l: l.account_id.code == "220101").mapped("credit"))
        self.assertAlmostEqual(deb_prest, 281.25, delta=0.01)
        self.assertAlmostEqual(cred_prest, 281.25, delta=0.01)
        # El libro de garantía recibió el abono trimestral
        ledger = self.env["l10n.ve.prestaciones.line"].search(
            [("provision_id", "=", prov.id)])
        garantia = ledger.filtered(lambda l: l.concept == "garantia")
        self.assertEqual(len(garantia), 1)
        self.assertAlmostEqual(garantia.amount, 281.25, delta=0.01)
        self.assertEqual(garantia.days, 15)

    def test_provision_month_without_quarter(self):
        # Junio 2026: sin aniversario trimestral (04-15 pasado, 07-15 futuro)
        prov = self._provision("2026-06-01", "2026-06-30")
        self.assertFalse(self._emp_lines(prov, "prestaciones"))
        self.assertEqual(len(prov.line_ids), 3)  # solo alícuotas mensuales

    def test_provision_interest_and_fideicomiso(self):
        self.env["l10n.ve.prestaciones.line"].create({
            "employee_id": self.employee.id, "date": "2026-05-31",
            "concept": "garantia", "amount": 1000.0,
        })
        prov = self._provision("2026-06-01", "2026-06-30")
        interes = self._emp_lines(prov, "intereses")
        # 1000 × 47,56% anual / 12
        self.assertAlmostEqual(sum(interes.mapped("amount")), 39.63, delta=0.01)
        # En fideicomiso los intereses los genera el fondo, no la provisión
        self.company.l10n_ve_prestaciones_mode = "fideicomiso"
        prov.action_compute()
        self.assertFalse(self._emp_lines(prov, "intereses"))

    def test_additional_days_second_year(self):
        emp2 = self.env["hr.employee"].create({
            "name": "Antiguo", "company_id": self.company.id})
        emp2.version_id.write({
            "wage": 500.0, "contract_date_start": "2024-03-10",
            "structure_type_id": self.env.ref(
                "l10n_ve_bw_payroll.structure_type_employee_ve").id,
            "schedule_pay": "monthly",
        })
        prov = self._provision("2026-03-01", "2026-03-31")
        # 2° aniversario (2026-03-10): bono vac. del año EN CURSO = 17 d
        # (15 + 2, art. 192) → integral diario
        # = 500 × (1 + 30/360 + 17/360) / 30 = 18,8426
        garantia = self._emp_lines(prov, "prestaciones", emp2)
        adicionales = self._emp_lines(prov, "adicionales", emp2)
        self.assertAlmostEqual(sum(garantia.mapped("amount")), 282.64, delta=0.05)
        self.assertEqual(sum(adicionales.mapped("days")), 2)
        self.assertAlmostEqual(sum(adicionales.mapped("amount")), 37.69, delta=0.05)

    def test_period_constraints(self):
        from odoo.exceptions import ValidationError as VE
        # Período que no es mes calendario exacto
        with self.assertRaises(VE):
            self.env["l10n.ve.payroll.provision"].create({
                "company_id": self.company.id,
                "date_from": "2026-07-01", "date_to": "2026-08-31",
            })
        # Solape del mismo mes
        self._provision("2026-07-01", "2026-07-31")
        with self.assertRaises(VE):
            self.env["l10n.ve.payroll.provision"].create({
                "company_id": self.company.id,
                "date_from": "2026-07-01", "date_to": "2026-07-31",
            })

    def test_anticipo_cap(self):
        Ledger = self.env["l10n.ve.prestaciones.line"]
        Ledger.create({
            "employee_id": self.employee.id, "date": "2026-06-30",
            "concept": "garantia", "amount": 1000.0,
        })
        with self.assertRaises(ValidationError):
            Ledger.create({
                "employee_id": self.employee.id, "date": "2026-07-01",
                "concept": "anticipo", "amount": -800.0,
            })
        Ledger.create({
            "employee_id": self.employee.id, "date": "2026-07-01",
            "concept": "anticipo", "amount": -700.0,
        })
        self.assertAlmostEqual(
            Ledger._garantia_balance(self.employee), 300.0, places=2)
        with self.assertRaises(ValidationError):
            Ledger.create({
                "employee_id": self.employee.id, "date": "2026-07-02",
                "concept": "anticipo", "amount": -300.0,
            })
