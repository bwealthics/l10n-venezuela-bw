# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
import base64

from odoo.tests import tagged

from .common import PayslipVeCommon

# Escenario: recibo regular de julio validado (500 USD, tasa 100 Bs/USD):
#   IVSS 4% = 0,24 USD → 24 Bs · semanal topado 1,50 USD → 150 Bs · 4 lunes
#   FAOV: integral 562,50 USD → 56.250 Bs; 1% 562,50 Bs; 2% 1.125 Bs
#   INCES: base normal 500 USD; 2% = 10 USD
#   CEPP: base 540 (>piso 240) → cuota 48,60 = devengado → diferencia 0
#   ISLR: remuneraciones gravables 500; retenido 50 (AR-C)


@tagged("post_install", "-at_install")
class TestDeclaracionesVe(PayslipVeCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slip = cls._make_payslip(cls)
        cls.slip.action_payslip_done()
        cls.wizard = cls.env["l10n.ve.declaraciones.wizard"].create({
            "company_id": cls.company.id,
            "date_from": "2026-07-01",
            "date_to": "2026-07-31",
        })

    def test_tiuna_rows(self):
        rows = self.wizard._tiuna_rows()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["lunes"], 4)
        self.assertAlmostEqual(r["semanal_bs"], 150.0, delta=0.5)
        self.assertAlmostEqual(r["ivss_emp_bs"], 24.0, delta=0.5)
        self.assertAlmostEqual(r["ivss_pat_bs"], 54.0, delta=0.5)

    def test_faov_rows(self):
        rows = self.wizard._faov_rows()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        # El integral se reconstruye de la línea FAOV 1% redondeada a
        # centavos: el medio centavo se amplifica ×100 (±50 Bs a tasa 100) —
        # inmaterial para el soporte (0,09%)
        self.assertAlmostEqual(r["integral_bs"], 56250.0, delta=60.0)
        self.assertAlmostEqual(r["emp_1_bs"], 562.5, delta=1.0)
        self.assertAlmostEqual(r["pat_2_bs"], 1125.0, delta=1.0)

    def test_inces_rows(self):
        rows = self.wizard._inces_rows()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["base_usd"], 500.0, delta=0.01)
        self.assertAlmostEqual(rows[0]["pat_2_usd"], 10.0, delta=0.01)

    def test_cepp_rows(self):
        rows = self.wizard._cepp_rows()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertAlmostEqual(r["base_usd"], 540.0, delta=0.03)
        self.assertAlmostEqual(r["cuota_usd"], 48.60, delta=0.03)
        self.assertAlmostEqual(r["diferencia_usd"], 0.0, delta=0.05)

    def test_cepp_floor_aggregation(self):
        # Sueldo bajo pagado en quincenas: por recibo el piso se prorratea,
        # y la Forma 19 agrega el mes completo con el piso una sola vez.
        self.version.write({"schedule_pay": "semi-monthly", "wage": 50.0,
                            "l10n_ve_cesta_ticket": False,
                            "l10n_ve_ari_percentage": 0.0})
        q1 = self._make_payslip(date_from="2026-08-01", date_to="2026-08-15")
        q2 = self._make_payslip(date_from="2026-08-16", date_to="2026-08-31")
        (q1 + q2).action_payslip_done()
        wiz = self.env["l10n.ve.declaraciones.wizard"].create({
            "company_id": self.company.id,
            "date_from": "2026-08-01", "date_to": "2026-08-31",
        })
        rows = wiz._cepp_rows()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertAlmostEqual(r["base_usd"], 100.0, delta=0.03)
        # Piso 240 aplicado UNA vez al mes: cuota 21,60 = devengado (10,80×2)
        self.assertAlmostEqual(r["cuota_usd"], 21.60, delta=0.03)
        self.assertAlmostEqual(r["diferencia_usd"], 0.0, delta=0.05)

    def test_tiuna_includes_vacation_slip(self):
        # El recibo VEVAC también cotiza IVSS/RPE: sus cotizaciones entran al
        # soporte, pero los lunes solo cuentan del recibo regular.
        vac = self._make_payslip(struct=self.struct_vac,
                                 date_from="2026-07-01", date_to="2026-07-31",
                                 inputs={"vac_d": 15, "bvac_d": 16})
        vac.action_payslip_done()
        rows = self.wizard._tiuna_rows()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["lunes"], 4, "Los lunes del VEVAC no deben sumarse")
        # 24 Bs del regular + 24 Bs del VEVAC (base vacacional también topada)
        self.assertGreater(r["ivss_emp_bs"], 24.0)
        # Identidad de la hoja: semanal × 4% × lunes == IVSS retenido
        self.assertAlmostEqual(
            r["semanal_bs"] * 0.04 * r["lunes"], r["ivss_emp_bs"], delta=0.02)

    def test_cross_month_slip_single_attribution(self):
        # Un VEVAC que cruza de mes se atribuye SOLO al mes de su date_to
        vac = self._make_payslip(struct=self.struct_vac,
                                 date_from="2026-09-20", date_to="2026-10-05",
                                 inputs={"vac_d": 10, "bvac_d": 10})
        vac.action_payslip_done()
        wiz_sep = self.env["l10n.ve.declaraciones.wizard"].create({
            "company_id": self.company.id,
            "date_from": "2026-09-01", "date_to": "2026-09-30",
        })
        wiz_oct = self.env["l10n.ve.declaraciones.wizard"].create({
            "company_id": self.company.id,
            "date_from": "2026-10-01", "date_to": "2026-10-31",
        })
        self.assertFalse(wiz_sep._faov_rows(), "Septiembre no debe incluirlo")
        self.assertEqual(len(wiz_oct._faov_rows()), 1, "Octubre lo incluye una vez")

    def test_headcount_and_rnet(self):
        self.assertEqual(
            self.wizard._headcount_rows(), [{"mes": "2026-07", "trabajadores": 1}])
        rnet = self.wizard._rnet_rows()
        self.assertEqual(len(rnet), 1)
        self.assertEqual(rnet[0]["estado"], "activo")
        self.assertAlmostEqual(rnet[0]["salario_usd"], 500.0, delta=0.03)

    def test_he_rows(self):
        slip = self._make_payslip(date_from="2026-08-01", date_to="2026-08-31",
                                  inputs={"hed_h": 60, "hen_h": 50})
        slip.action_payslip_done()
        wiz = self.env["l10n.ve.declaraciones.wizard"].create({
            "company_id": self.company.id,
            "date_from": "2026-08-01", "date_to": "2026-08-31",
        })
        rows = wiz._he_rows()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["horas_periodo"], 110.0, places=2)
        self.assertIn("100 h", rows[0]["alerta"])

    def test_xlsx_generation(self):
        self.wizard.action_generate()
        self.assertTrue(self.wizard.file)
        content = base64.b64decode(self.wizard.file)
        self.assertEqual(content[:2], b"PK", "El XLSX debe ser un ZIP válido")

    def test_arc_report_values(self):
        parser = self.env["report.l10n_ve_bw_payroll.report_arc_employee"]
        values = parser._get_report_values(
            self.employee.ids, {"year": 2026, "company_id": self.company.id})
        row = values["table"][self.employee.id]
        self.assertAlmostEqual(row["months"][7]["rem_usd"], 500.0, delta=0.03)
        self.assertAlmostEqual(row["months"][7]["wh_usd"], 50.0, delta=0.03)
        self.assertAlmostEqual(row["total_wh_bs"], 5000.0, delta=5.0)
