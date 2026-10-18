# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import PayslipVeCommon

# Escenario: ingreso 2026-01-15, egreso 2026-09-30 (8 meses 15 días).
#   integral diario 18,75 · normal diario 16,6667
#   retroactivo: fracción > 6 meses = 1 año → 30 × 18,75 = 562,50
#   trimestre en curso (iniciado, no completado): 15 × 18,75 = 281,25
#   vac/bono frac: 15 d/año × 8/12 × 16,6667 = 166,67 c/u
#   utilidades frac: 30 d × 8/12 × 16,6667 = 333,33
#   ISLR 10% sobre (166,67+166,67+333,33) = −66,67 · INCES ½% util = −1,67
#   CEPP 9% sobre las fracciones (666,67) = 60,00 (patronal, no toca el neto)


@tagged("post_install", "-at_install")
class TestLiquidacionVe(PayslipVeCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Ledger = cls.env["l10n.ve.prestaciones.line"]

    def _wizard(self, end_date="2026-09-30"):
        return self.env["l10n.ve.liquidacion.wizard"].create({
            "employee_id": self.employee.id,
            "end_date": end_date,
        })

    def test_wizard_amounts(self):
        self.Ledger.create({
            "employee_id": self.employee.id, "date": "2026-07-31",
            "concept": "garantia", "amount": 100.0,
        })
        wiz = self._wizard()
        self.assertAlmostEqual(wiz.garantia, 100.0, delta=0.01)
        self.assertAlmostEqual(wiz.intereses, 0.0, places=2)
        self.assertAlmostEqual(wiz.prest_trim, 281.25, delta=0.01)
        self.assertAlmostEqual(wiz.retroactivo, 562.50, delta=0.01)
        # 142.d: retroactivo − (garantía + trimestre en curso)
        self.assertAlmostEqual(wiz.prest_extra, 181.25, delta=0.01)
        self.assertAlmostEqual(wiz.vac_frac, 166.67, delta=0.01)
        self.assertAlmostEqual(wiz.bvac_frac, 166.67, delta=0.01)
        self.assertAlmostEqual(wiz.util_frac, 333.33, delta=0.01)

    def test_wizard_garantia_wins(self):
        # Garantía + trimestre en curso > retroactivo → sin diferencia
        self.Ledger.create({
            "employee_id": self.employee.id, "date": "2026-07-31",
            "concept": "garantia", "amount": 600.0,
        })
        wiz = self._wizard()
        self.assertAlmostEqual(wiz.prest_trim, 281.25, delta=0.01)
        self.assertAlmostEqual(wiz.prest_extra, 0.0, places=2)

    def test_retro_boundary_six_months(self):
        # Egreso a EXACTAMENTE 6 meses (2026-07-15): la fracción no supera
        # los 6 meses → retroactivo 0. El aniversario trimestral cae EN el
        # mes de egreso y el libro no tiene su abono (la corrida de julio no
        # se posteó) → se paga como garantía no depositada (15 × 18,75); no
        # hay trimestre iniciado (aniversario exacto).
        wiz = self._wizard(end_date="2026-07-15")
        self.assertAlmostEqual(wiz.retroactivo, 0.0, places=2)
        self.assertAlmostEqual(wiz.prest_trim, 281.25, delta=0.01)
        self.assertAlmostEqual(wiz.vac_frac, 125.0, delta=0.01)

    def test_compensacion_523(self):
        # SCS/TSJ 523 del 13-11-2025: la bonificación especial/anticipo pagado
        # al cese es compensable contra el finiquito hasta su concurrencia.
        # Escenario de referencia con garantía 100 (ver cabecera del archivo):
        # bruto conceptos 1.229,17 − ISLR 66,67 − INCES 1,67 = neto 1.160,83.
        self.Ledger.create({
            "employee_id": self.employee.id, "date": "2026-07-31",
            "concept": "garantia", "amount": 100.0,
        })
        wiz = self._wizard()
        bruto = wiz.total
        wiz.compensacion = 200.0
        self.assertAlmostEqual(wiz.total, bruto - 200.0, delta=0.01)
        action = wiz.action_create_payslip()
        slip = self.env["hr.payslip"].browse(action["res_id"])
        self.assertAlmostEqual(self._line(slip, "VE_LIQ_COMP"), -200.0, places=2)
        # La compensación no toca las bases: ISLR e INCES iguales al escenario
        self.assertAlmostEqual(self._line(slip, "VE_ISLR"), -66.67, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "NET"), 960.83, delta=0.03)
        # Contabilidad: acredita 110202 (limpia el anticipo debitado allí)
        slip.action_payslip_done()
        cxc = slip.move_id.line_ids.filtered(
            lambda l: l.account_id.code == "110202")
        self.assertAlmostEqual(sum(cxc.mapped("credit")), 200.0, delta=0.01)
        self.assertEqual(sum(cxc.mapped("debit")), 0.0)

    def test_compensacion_bounds(self):
        wiz = self._wizard()
        bruto = wiz.total
        wiz.compensacion = bruto + 10000.0
        with self.assertRaises(UserError):
            wiz.action_create_payslip()
        wiz.compensacion = -5.0
        with self.assertRaises(UserError):
            wiz.action_create_payslip()

    def test_compensacion_net_negativo_raises(self):
        # comp < bruto pero > neto disponible tras ISLR/INCES: el corte real
        # es NET >= 0 (bruto 1.229,17; neto disponible 1.160,83).
        self.Ledger.create({
            "employee_id": self.employee.id, "date": "2026-07-31",
            "concept": "garantia", "amount": 100.0,
        })
        wiz = self._wizard()
        wiz.compensacion = 1200.0
        with self.assertRaises(UserError):
            wiz.action_create_payslip()

    def test_compensacion_sin_fecha_ingreso_raises(self):
        # Sin fecha de ingreso el compute deja todo en 0 sin restar la
        # compensación: el wizard debe cortar antes de crear nada.
        emp = self.env["hr.employee"].create({
            "name": "Sin Fecha de Ingreso", "company_id": self.company.id})
        wiz = self.env["l10n.ve.liquidacion.wizard"].create({
            "employee_id": emp.id, "end_date": "2026-09-30",
            "compensacion": 100.0,
        })
        with self.assertRaises(UserError):
            wiz.action_create_payslip()

    def test_liq_comp_input_directo(self):
        # Input directo en el recibo (sin wizard): un monto negativo se
        # ignora (sería un pago que debita 110202)…
        slip = self._make_payslip(struct=self.struct_liq,
                                  inputs={"liq_vac": 100, "liq_comp": -50})
        self.assertEqual(self._line(slip, "VE_LIQ_COMP"), 0.0)
        # …y un comp mayor que lo pagadero deja NET < 0: la validación del
        # recibo VELIQ lo bloquea aunque no haya pasado por el wizard.
        slip2 = self._make_payslip(struct=self.struct_liq,
                                   inputs={"liq_vac": 100, "liq_comp": 500})
        self.assertLess(self._line(slip2, "NET"), 0.0)
        with self.assertRaises(UserError):
            slip2.action_payslip_done()

    def test_payslip_ledger_close_and_accounting(self):
        self.Ledger.create({
            "employee_id": self.employee.id, "date": "2026-07-31",
            "concept": "garantia", "amount": 281.25,
        })
        self.Ledger.create({
            "employee_id": self.employee.id, "date": "2026-07-31",
            "concept": "intereses", "amount": 39.63,
        })
        wiz = self._wizard()
        self.assertAlmostEqual(wiz.intereses, 39.63, delta=0.01)
        action = wiz.action_create_payslip()
        slip = self.env["hr.payslip"].browse(action["res_id"])
        self.assertEqual(slip.struct_id.code, "VELIQ")
        self.assertAlmostEqual(self._line(slip, "VE_LIQ_PREST_GAR"), 281.25, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_LIQ_PREST_TRIM"), 281.25, delta=0.01)
        # 562,50 de retroactivo quedan cubiertos por garantía + trimestre
        self.assertEqual(self._line(slip, "VE_LIQ_PREST_EXTRA"), 0.0)
        self.assertAlmostEqual(self._line(slip, "VE_LIQ_INT"), 39.63, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_LIQ_VAC"), 166.67, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_LIQ_BVAC"), 166.67, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_LIQ_UTIL"), 333.33, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_LIQ_INCES_UTIL"), -1.67, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_ISLR"), -66.67, delta=0.01)
        self.assertAlmostEqual(self._line(slip, "VE_CEPP_PAT"), 60.0, delta=0.02)
        expected_net = (281.25 + 281.25 + 39.63 + 166.67 + 166.67 + 333.33
                        - 1.67 - 66.67)
        self.assertAlmostEqual(self._line(slip, "NET"), expected_net, delta=0.05)
        # Libro cerrado (garantía E intereses) y contrato terminado
        self.assertAlmostEqual(
            self.Ledger._garantia_balance(self.employee), 0.0, places=2)
        self.assertAlmostEqual(
            self.Ledger._intereses_balance(self.employee), 0.0, places=2)
        self.assertEqual(str(self.version.contract_date_end), "2026-09-30")

        slip.action_payslip_done()
        move = slip.move_id
        self.assertTrue(move)

        def side(code):
            lines = move.line_ids.filtered(lambda l: l.account_id.code == code)
            return sum(lines.mapped("debit")), sum(lines.mapped("credit"))

        self.assertAlmostEqual(side("220101")[0], 281.25, delta=0.01)   # garantía
        self.assertAlmostEqual(side("610401")[0], 281.25, delta=0.01)   # trimestre
        self.assertAlmostEqual(side("220102")[0], 39.63, delta=0.01)    # intereses
        self.assertAlmostEqual(side("210601")[0], 333.33, delta=0.01)   # util frac
        self.assertAlmostEqual(side("210602")[0], 166.67, delta=0.01)
        self.assertAlmostEqual(side("210603")[0], 166.67, delta=0.01)
        self.assertAlmostEqual(side("610305")[0], 60.0, delta=0.02)     # CEPP
        self.assertAlmostEqual(side("210510")[1], 60.0, delta=0.02)
        self.assertAlmostEqual(side("210508")[1], self._line(slip, "NET"), delta=0.02)
        adjust = move.line_ids.filtered(lambda l: l.name == "Adjustment Entry")
        self.assertTrue(all(abs(l.balance) <= 0.05 for l in adjust))

    def test_double_run_guard(self):
        self.Ledger.create({
            "employee_id": self.employee.id, "date": "2026-07-31",
            "concept": "garantia", "amount": 281.25,
        })
        self._wizard().action_create_payslip()
        with self.assertRaises(UserError):
            self._wizard().action_create_payslip()

    def test_base_salario_minimo_bs(self):
        # Sueldo base Bs 130 a 100 Bs/USD = 1,30 USD/mes → normal diario
        # 0,043333; integral = normal × (1 + 30/360 + 15/360) = 0,04875.
        self.company.l10n_ve_benefits_base = "minimum_wage"
        wiz = self._wizard()
        self.assertAlmostEqual(wiz.prest_trim, 15 * 0.04875, delta=0.005)
        self.assertAlmostEqual(wiz.retroactivo, 30 * 0.04875, delta=0.005)
        # 15 d/año × 8/12 × 0,043333 = 0,4333
        self.assertAlmostEqual(wiz.vac_frac, 0.4333, delta=0.005)
        self.assertAlmostEqual(wiz.util_frac, 30 * 8 / 12 * 1.30 / 30, delta=0.005)



    def test_dias_y_cesta_pendientes(self):
        # 25 días de sueldo base Bs 130 (100 Bs/USD) y 25 de cesta (40/30)
        self.company.l10n_ve_benefits_base = "minimum_wage"
        slip = self._make_payslip(
            struct=self.struct_liq, date_from="2026-10-01",
            date_to="2026-10-22",
            inputs={"liq_dias_d": 25, "liq_cesta_d": 25})
        dias = self._line(slip, "VE_LIQ_DIAS")
        cesta = self._line(slip, "VE_LIQ_CESTA")
        self.assertAlmostEqual(dias, 25 * 1.30 / 30, delta=0.01)
        self.assertAlmostEqual(cesta, 25 * 40 / 30, delta=0.01)
        # Los días pendientes son salario: pagan ISLR (AR-I 10 % del empleado
        # de prueba); la cesta no.
        ded = sum(slip.line_ids.filtered(
            lambda l: l.category_id.code == "DED").mapped("total"))
        self.assertAlmostEqual(ded, -dias * 0.10, delta=0.01)
        self.assertAlmostEqual(
            self._line(slip, "NET"), dias + cesta + ded, delta=0.02)
        slip.action_payslip_done()
        move = slip.move_id
        side = lambda code, f: sum(move.line_ids.filtered(
            lambda l: l.account_id.code == code).mapped(f))
        self.assertAlmostEqual(side("610201", "debit"), cesta, delta=0.01)
        self.assertAlmostEqual(
            side("210508", "credit"), self._line(slip, "NET"), delta=0.02)
        adjust = move.line_ids.filtered(lambda l: l.name == "Adjustment Entry")
        self.assertTrue(all(abs(l.balance) <= 0.05 for l in adjust))
