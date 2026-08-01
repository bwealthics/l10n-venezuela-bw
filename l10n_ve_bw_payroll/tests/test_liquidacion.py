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
