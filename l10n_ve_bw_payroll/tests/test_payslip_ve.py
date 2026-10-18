# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import PayslipVeCommon

# Escenario de referencia (validable a mano):
#   sueldo 500 USD/mes (mensual) · tasa 100 Bs/USD · SM Bs 130 · julio 2026 (4 lunes)
#   antigüedad < 1 año → bono vacacional 15 días → integral = normal × 1.125
#   tope IVSS 5 SM = Bs 650 = 6.50 USD  → semanal 1.50 → 4% × 4 lunes = -0.24
#   tope RPE 10 SM = Bs 1.300 = 13 USD  → 0.5% mensual = -0.065
#   FAOV: 562.50 → 1% = -5.625 / 2% = 11.25 · ISLR AR-I 10% = -50
#   Cesta 40 USD · CEPP 9% × max(500+40, 240) = 48.60


@tagged("post_install", "-at_install")
class TestPayslipVe(PayslipVeCommon):

    def test_bcv_rate_and_deductions(self):
        slip = self._make_payslip()
        self.assertAlmostEqual(slip.l10n_ve_bcv_rate, 100.0, places=4)
        self.assertAlmostEqual(self._line(slip, "BASIC"), 500.0, places=2)
        # IVSS: tope 6.5 → semanal 1.5 → 4% × 4 lunes de julio 2026
        self.assertAlmostEqual(self._line(slip, "VE_IVSS_EMP"), -0.24, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_RPE_EMP"), -0.065, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_FAOV_EMP"), -5.625, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_ISLR"), -50.0, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_CESTA"), 40.0, places=2)
        # La cesta (40) NO entra en el neto
        expected_net = 500.0 - 0.24 - 0.065 - 5.625 - 50.0
        self.assertAlmostEqual(self._line(slip, "NET"), expected_net, delta=0.03)
        self.assertAlmostEqual(slip.l10n_ve_total_ves, self._line(slip, "NET") * 100, delta=1.0)

    def test_employer_contributions(self):
        slip = self._make_payslip()
        self.assertAlmostEqual(self._line(slip, "VE_IVSS_PAT"), 0.54, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_RPE_PAT"), 0.26, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_FAOV_PAT"), 11.25, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_INCES_PAT"), 10.0, delta=0.01)
        # CEPP: base 500 + cesta 40 = 540 (> piso 240) × 9%
        self.assertAlmostEqual(self._line(slip, "VE_CEPP_PAT"), 48.60, delta=0.02)

    def test_cepp_floor(self):
        # Sueldo bajo: la base CEPP se eleva al IMI (240 USD desde may-2026)
        self.version.write({"wage": 100.0, "l10n_ve_cesta_ticket": False,
                            "l10n_ve_ari_percentage": 0.0})
        slip = self._make_payslip()
        self.assertAlmostEqual(self._line(slip, "VE_CEPP_PAT"), 240 * 0.09, delta=0.02)

    def test_non_contributor_and_no_ari(self):
        self.version.write({"l10n_ve_ivss_contributor": False,
                            "l10n_ve_ari_percentage": 0.0})
        slip = self._make_payslip()
        self.assertEqual(self._line(slip, "VE_IVSS_EMP"), 0.0)
        self.assertEqual(self._line(slip, "VE_RPE_EMP"), 0.0)
        self.assertEqual(self._line(slip, "VE_ISLR"), 0.0)
        self.assertEqual(self._line(slip, "VE_IVSS_PAT"), 0.0)

    def test_inces_non_contributor_company(self):
        self.company.l10n_ve_inces_contributor = False
        slip = self._make_payslip()
        self.assertEqual(self._line(slip, "VE_INCES_PAT"), 0.0)
        slip_util = self._make_payslip(struct=self.struct_util,
                                       date_from="2026-12-01", date_to="2026-12-15")
        self.assertEqual(self._line(slip_util, "VE_INCES_UTIL"), 0.0)

    def test_input_allowances_and_embargo(self):
        # hourly = 500/30/8 = 2.0833 · daily = 16.667
        slip = self._make_payslip(inputs={
            "bnoct_h": 10, "hed_h": 10, "hen_h": 10,
            "feriado_d": 2, "comis": 100, "embargo": 25,
        })
        self.assertAlmostEqual(self._line(slip, "VE_BNOCT"), 6.25, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_HED"), 31.25, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_HEN"), 40.63, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_FERIADO"), 50.0, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_COMIS"), 100.0, places=2)
        self.assertAlmostEqual(self._line(slip, "VE_EMBARGO"), -25.0, places=2)

    def test_bono_no_salarial(self):
        # No cotiza (FAOV intacto) pero SÍ grava ISLR y CEPP
        slip = self._make_payslip(inputs={"bono_ns": 100})
        self.assertAlmostEqual(self._line(slip, "VE_BONO_NS"), 100.0, places=2)
        self.assertAlmostEqual(self._line(slip, "VE_FAOV_EMP"), -5.625, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_ISLR"), -60.0, delta=0.01)
        # CEPP: (500 + 100 + 40) × 9%
        self.assertAlmostEqual(self._line(slip, "VE_CEPP_PAT"), 57.60, delta=0.02)

    def test_cesta_complement_recurring(self):
        # SCS 523/2025 (art. 105.2 LOTTT): complemento en USD del beneficio
        # de alimentación — no cotiza, no grava ISLR, fuera del NET; solo
        # integra la base CEPP. Escenario INDULAC: 530 USD/mes.
        self.version.l10n_ve_cesta_complement_usd = 530.0
        slip = self._make_payslip()
        self.assertAlmostEqual(self._line(slip, "VE_CESTA_COMP"), 530.0, places=2)
        # Bases salariales intactas (mismos valores del escenario base)
        self.assertAlmostEqual(self._line(slip, "VE_FAOV_EMP"), -5.625, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_ISLR"), -50.0, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_INCES_PAT"), 10.0, delta=0.01)
        expected_net = 500.0 - 0.24 - 0.065 - 5.625 - 50.0
        self.assertAlmostEqual(self._line(slip, "NET"), expected_net, delta=0.03)
        # CEPP: (500 + cesta 40 + complemento 530) × 9%
        self.assertAlmostEqual(self._line(slip, "VE_CEPP_PAT"), 96.30, delta=0.02)
        # Contabilidad: mismo par que la cesta (610201 / 210502), 40 + 530
        slip.action_payslip_done()
        move = slip.move_id

        def side(code):
            lines = move.line_ids.filtered(lambda l: l.account_id.code == code)
            return sum(lines.mapped("debit")), sum(lines.mapped("credit"))

        self.assertAlmostEqual(side("610201")[0], 570.0, delta=0.02)
        self.assertAlmostEqual(side("210502")[1], 570.0, delta=0.02)

    def test_cesta_complement_input_oneoff(self):
        slip = self._make_payslip(inputs={"cesta_comp": 100})
        self.assertAlmostEqual(self._line(slip, "VE_CESTA_COMP"), 100.0, places=2)
        # CEPP: (500 + 40 + 100) × 9%
        self.assertAlmostEqual(self._line(slip, "VE_CEPP_PAT"), 57.60, delta=0.02)

    def test_cesta_complement_cepp_salarial_base(self):
        # Con la base CEPP restringida a lo salarial, el complemento sale
        self.company.l10n_ve_cepp_include_nonsalarial = False
        self.version.l10n_ve_cesta_complement_usd = 530.0
        slip = self._make_payslip()
        self.assertAlmostEqual(self._line(slip, "VE_CEPP_PAT"), 45.0, delta=0.02)

    def test_cesta_complement_negative_raises(self):
        with self.assertRaises(ValidationError):
            self.version.l10n_ve_cesta_complement_usd = -10.0

    def test_cesta_complement_quincenal(self):
        # Monto MENSUAL prorrateado por período (mismo criterio que la cesta)
        self.version.write({"schedule_pay": "semi-monthly", "wage": 250.0,
                            "l10n_ve_cesta_complement_usd": 530.0})
        q1 = self._make_payslip(date_from="2026-07-01", date_to="2026-07-15")
        self.assertAlmostEqual(self._line(q1, "VE_CESTA_COMP"), 265.0, places=2)

    def test_missing_bcv_rate_raises(self):
        slip = self.env["hr.payslip"].create({
            "name": "Sin tasa",
            "employee_id": self.employee.id,
            "company_id": self.company.id,
            "struct_id": self.struct_regular.id,
            "date_from": "2025-01-01",
            "date_to": "2025-01-31",
        })
        # payment date anterior a la primera tasa VES cargada (2026-01-01)
        slip.l10n_ve_payment_date = "2025-01-31"
        self.assertFalse(slip.l10n_ve_bcv_rate)
        with self.assertRaises(UserError):
            slip.compute_sheet()

    def test_rate_loaded_after_slip(self):
        slip = self.env["hr.payslip"].create({
            "name": "Tasa tardía",
            "employee_id": self.employee.id,
            "company_id": self.company.id,
            "struct_id": self.struct_regular.id,
            "date_from": "2025-06-01",
            "date_to": "2025-06-30",
        })
        slip.l10n_ve_payment_date = "2025-06-30"
        self.assertFalse(slip.l10n_ve_bcv_rate)
        self.env["res.currency.rate"].create({
            "currency_id": self.ves.id, "name": "2025-06-01",
            "rate": 50.0, "company_id": self.company.id,
        })
        slip.compute_sheet()  # _ve_rate reintenta el compute y encuentra 50
        self.assertAlmostEqual(slip.l10n_ve_bcv_rate, 50.0, places=4)

    def test_mondays_of_month(self):
        slip = self._make_payslip()
        self.assertEqual(slip._ve_mondays(), 4)   # julio 2026: 6, 13, 20, 27
        slip_jun = self._make_payslip(date_from="2026-06-01", date_to="2026-06-30")
        self.assertEqual(slip_jun._ve_mondays(), 5)  # junio 2026: 1, 8, 15, 22, 29

    def test_quincena_halves(self):
        # Semántica Odoo 19: wage POR PERÍODO → quincenal carga 250 (= 500/mes)
        self.version.write({"schedule_pay": "semi-monthly", "wage": 250.0})
        q1 = self._make_payslip(date_from="2026-07-01", date_to="2026-07-15")
        q2 = self._make_payslip(date_from="2026-07-16", date_to="2026-07-31")
        self.assertAlmostEqual(self._line(q1, "BASIC"), 250.0, places=2)
        self.assertAlmostEqual(self._line(q2, "BASIC"), 250.0, places=2)
        # Cesta mensual (40) partida por quincena
        self.assertAlmostEqual(self._line(q1, "VE_CESTA"), 20.0, places=2)
        # IVSS del mes = suma de las quincenas (lunes 4 = 2 + 2)
        total_ivss = self._line(q1, "VE_IVSS_EMP") + self._line(q2, "VE_IVSS_EMP")
        self.assertAlmostEqual(total_ivss, -0.24, delta=0.01)
        # FAOV mensual completo = suma de quincenas (integral 562.50 × 1%)
        total_faov = self._line(q1, "VE_FAOV_EMP") + self._line(q2, "VE_FAOV_EMP")
        self.assertAlmostEqual(total_faov, -5.625, delta=0.02)

    def test_ingreso_a_mitad_de_quincena_prorratea_por_dias(self):
        # LOTTT: salario diario = mensual / 30; NO por horas del calendario.
        # Ingreso el 20/07 → 16-31 jul devenga 12 días de 15 (incluye el 31).
        self.version.write({"schedule_pay": "semi-monthly", "wage": 150.0,
                            "contract_date_start": "2026-07-20"})
        q2 = self._make_payslip(date_from="2026-07-16", date_to="2026-07-31")
        self.assertAlmostEqual(self._line(q2, "BASIC"), 120.0, places=2)
        self.assertAlmostEqual(self._line(q2, "VE_CESTA"), 16.0, places=2)
        # Quincena completa de 16 días: sueldo íntegro, no 16/15
        full = self._make_payslip(date_from="2026-08-16", date_to="2026-08-31")
        self.assertAlmostEqual(self._line(full, "BASIC"), 150.0, places=2)
        self.assertAlmostEqual(self._line(full, "VE_CESTA"), 20.0, places=2)

    def test_egreso_a_mitad_de_quincena(self):
        # Egreso el 13/08 con 420/mes (210 por quincena): 13 días × 14 = 182
        self.version.write({"schedule_pay": "semi-monthly", "wage": 210.0,
                            "contract_date_end": "2026-08-13"})
        q1 = self._make_payslip(date_from="2026-08-01", date_to="2026-08-15")
        self.assertAlmostEqual(self._line(q1, "BASIC"), 182.0, places=2)

    def _rest(self, slip):
        return slip.worked_days_line_ids.filtered(lambda l: l.code == "VEDESC")

    def _days_paid(self, slip):
        return sum(slip.worked_days_line_ids.filtered(
            lambda l: l.code != "OUT").mapped("number_of_days"))

    def test_descanso_semanal_completa_la_quincena(self):
        # Art. 173 LOTTT: 1-15 jul 2026 tiene 11 días hábiles (L-V) y 4 de
        # descanso; el recibo muestra 15 días y el sueldo no cambia.
        self.version.write({"schedule_pay": "semi-monthly", "wage": 250.0})
        slip = self._make_payslip(date_from="2026-07-01", date_to="2026-07-15")
        self.assertAlmostEqual(self._rest(slip).number_of_days, 4.0, places=4)
        self.assertTrue(self._rest(slip).is_paid)
        self.assertAlmostEqual(self._days_paid(slip), 15.0, places=4)
        self.assertAlmostEqual(self._line(slip, "BASIC"), 250.0, places=2)
        self.assertAlmostEqual(
            sum(slip.worked_days_line_ids.mapped("amount")), 250.0, places=2)

    def test_descanso_con_egreso_a_mitad_de_quincena(self):
        # Egreso el 13/08: 9 hábiles + 4 descanso = 13 días cubiertos.
        self.version.write({"schedule_pay": "semi-monthly", "wage": 210.0,
                            "contract_date_end": "2026-08-13"})
        slip = self._make_payslip(date_from="2026-08-01", date_to="2026-08-15")
        self.assertAlmostEqual(self._days_paid(slip), 13.0, places=4)
        self.assertAlmostEqual(self._line(slip, "BASIC"), 182.0, places=2)

    def test_descanso_no_aplica_a_contrato_por_hora(self):
        self.version.write({"wage_type": "hourly", "hourly_wage": 5.0, "wage": 0.0})
        self.assertFalse(self._rest(self._make_payslip()))

    def test_contrato_por_hora_usa_horas_trabajadas(self):
        # Sin sueldo fijo el prorrateo por días daría 0: el BASIC sigue al
        # motor de worked days (tarifa × horas).
        self.version.write({"wage_type": "hourly", "hourly_wage": 5.0, "wage": 0.0})
        slip = self._make_payslip()
        paid = sum(slip.worked_days_line_ids.mapped("amount"))
        self.assertGreater(paid, 0.0)
        self.assertAlmostEqual(self._line(slip, "BASIC"), paid, places=2)

    def test_utilidades_structure(self):
        slip = self._make_payslip(struct=self.struct_util,
                                  date_from="2026-12-01", date_to="2026-12-15")
        # 30 días de utilidades × (500/30) = 500; INCES ½% = -2.50; ISLR 10%
        self.assertAlmostEqual(self._line(slip, "VE_UTIL"), 500.0, places=2)
        self.assertAlmostEqual(self._line(slip, "VE_INCES_UTIL"), -2.50, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_ISLR"), -50.0, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_CEPP_PAT"), 45.0, delta=0.02)

    def test_utilidades_input_days(self):
        slip = self._make_payslip(struct=self.struct_util,
                                  date_from="2026-12-01", date_to="2026-12-15",
                                  inputs={"util_d": 60})
        self.assertAlmostEqual(self._line(slip, "VE_UTIL"), 1000.0, delta=0.03)
        self.assertAlmostEqual(self._line(slip, "VE_INCES_UTIL"), -5.0, delta=0.01)

    def test_vacaciones_structure(self):
        # 15 días de disfrute + 16 de bono, sobre salario normal diario 16.667
        slip = self._make_payslip(struct=self.struct_vac,
                                  date_from="2026-08-01", date_to="2026-08-31",
                                  inputs={"vac_d": 15, "bvac_d": 16})
        self.assertAlmostEqual(self._line(slip, "VE_VAC"), 250.0, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_BVAC"), 266.67, delta=0.01)
        # Solo VE_VAC cotiza: FAOV = 1% × (250 × 1.125)
        self.assertAlmostEqual(self._line(slip, "VE_FAOV_EMP"), -2.8125, delta=0.01)
        # ISLR grava ambos: 10% × 516.67
        self.assertAlmostEqual(self._line(slip, "VE_ISLR"), -51.67, delta=0.01)
        # INCES patronal sobre el disfrute (salario normal): 2% × 250
        self.assertAlmostEqual(self._line(slip, "VE_INCES_PAT"), 5.0, delta=0.01)

    def test_full_payslip_accounting(self):
        slip = self._make_payslip()
        slip.action_payslip_done()
        move = slip.move_id
        self.assertTrue(move, "El payslip validado debe generar asiento")
        # Solo se admite ajuste de REDONDEO (centavos); un ajuste grande
        # delata cuentas mal mapeadas (p. ej. deducciones debitadas).
        adjust = move.line_ids.filtered(lambda l: l.name == "Adjustment Entry")
        self.assertTrue(
            all(abs(l.balance) <= 0.05 for l in adjust),
            f"Línea de ajuste excesiva: {adjust.mapped('balance')} — cuentas mal mapeadas")

        def side(code):
            lines = move.line_ids.filtered(lambda l: l.account_id.code == code)
            return sum(lines.mapped("debit")), sum(lines.mapped("credit"))

        # Gasto de sueldo debitado; pasivos de deducciones ACREDITADOS
        self.assertAlmostEqual(side("610101")[0], 500.0, delta=0.03)
        for code in ("210503", "210504", "210505", "210507"):
            debit, credit = side(code)
            self.assertEqual(debit, 0.0, f"{code} no debe debitarse")
            self.assertGreater(credit, 0.0, f"{code} debe acreditarse")
        # 210503 = 0.24 trabajador + 0.54 patrono
        self.assertAlmostEqual(side("210503")[1], 0.78, delta=0.02)
        # Neto por pagar completo (la cesta NO se resta dos veces)
        self.assertAlmostEqual(side("210501")[1], self._line(slip, "NET"), delta=0.02)
        # Cesta con su par propio
        self.assertAlmostEqual(side("610201")[0], 40.0, delta=0.01)
        self.assertAlmostEqual(side("210502")[1], 40.0, delta=0.01)
        # CEPP patronal
        self.assertAlmostEqual(side("610305")[0], 48.60, delta=0.02)
        self.assertAlmostEqual(side("210510")[1], 48.60, delta=0.02)
        self.assertAlmostEqual(
            sum(move.line_ids.mapped("debit")),
            sum(move.line_ids.mapped("credit")), places=2)

    def test_cesta_pagada_con_el_sueldo(self):
        # Opción de compañía: el neto es lo transferido (incluye la cesta)
        # y el pasivo completo va a 210501; 210502 no se toca.
        self.company.l10n_ve_cesta_in_net = True
        slip = self._make_payslip()
        net = self._line(slip, "NET")
        gross = self._line(slip, "GROSS")
        ded = sum(slip.line_ids.filtered(
            lambda l: l.category_id.code == "DED").mapped("total"))
        self.assertAlmostEqual(gross, 500.0, places=2)
        # Cada línea se redondea por separado; el NET suma categorías sin redondear.
        self.assertAlmostEqual(net, gross + 40.0 + ded, delta=0.02)
        slip.action_payslip_done()
        move = slip.move_id
        credit = lambda code: sum(move.line_ids.filtered(
            lambda l: l.account_id.code == code).mapped("credit"))
        self.assertAlmostEqual(credit("210501"), net, delta=0.02)
        self.assertEqual(credit("210502"), 0.0)
        adjust = move.line_ids.filtered(lambda l: l.name == "Adjustment Entry")
        self.assertTrue(all(abs(l.balance) <= 0.05 for l in adjust))

    def test_costo_empleador(self):
        # Bruto + cesta + aportes patronales (dashboard y lote de nómina)
        slip = self._make_payslip()
        comp = sum(slip.line_ids.filtered(
            lambda l: l.category_id.code == "COMP").mapped("total"))
        self.assertAlmostEqual(
            slip.employer_cost, 500.0 + 40.0 + comp, places=2)
