# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo import Command

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..hooks import map_rule_accounts


class PayslipVeCommon(AccountTestInvoicingCommon):
    """Compañía VE de prueba: chart genérico + cuentas ve_bw por código,
    tasa 100 Bs/USD, empleado mensual de 500 USD con ingreso 2026-01-15."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref("hr_payroll.group_hr_payroll_manager")
        cls.company = cls.company_data["company"]
        cls.company.country_id = cls.env.ref("base.ve")
        cls.company.l10n_ve_ivss_risk = "min"
        cls.company.l10n_ve_utilidades_days = 30

        cls.ves = cls.env.ref("base.VES")
        cls.ves.active = True
        # 1 unidad de moneda de compañía = 100 Bs
        cls.env["res.currency.rate"].create({
            "currency_id": cls.ves.id,
            "name": "2026-01-01",
            "rate": 100.0,
            "company_id": cls.company.id,
        })

        # Cuentas del chart ve_bw usadas por reglas y provisiones
        Account = cls.env["account.account"].with_company(cls.company)
        for code, name, atype in [
            ("610101", "Sueldos y Salarios", "expense"),
            ("610102", "Bono Nocturno", "expense"),
            ("610103", "Horas Extras", "expense"),
            ("610104", "Feriados Trabajados", "expense"),
            ("610105", "Bonificaciones", "expense"),
            ("610201", "Cesta Ticket", "expense"),
            ("610301", "Aporte IVSS", "expense"),
            ("610302", "Aporte FAOV", "expense"),
            ("610303", "Aporte RPE", "expense"),
            ("610304", "Aporte INCES", "expense"),
            ("610305", "Aporte CEPP", "expense"),
            ("610401", "Gasto Prestaciones", "expense"),
            ("610402", "Gasto Intereses Prestaciones", "expense"),
            ("610403", "Gasto Utilidades", "expense"),
            ("610404", "Gasto Vacaciones", "expense"),
            ("610405", "Gasto Bono Vacacional", "expense"),
            ("210501", "Sueldos por Pagar", "liability_current"),
            ("210502", "Cesta Ticket por Pagar", "liability_current"),
            ("210503", "IVSS por Pagar", "liability_current"),
            ("210504", "FAOV por Pagar", "liability_current"),
            ("210505", "RPE por Pagar", "liability_current"),
            ("210506", "INCES por Pagar", "liability_current"),
            ("210507", "ISLR Empleados por Pagar", "liability_current"),
            ("210508", "Liquidaciones por Pagar", "liability_current"),
            ("210510", "CEPP por Pagar", "liability_current"),
            ("210601", "Provisión Utilidades", "liability_current"),
            ("210602", "Provisión Vacaciones", "liability_current"),
            ("210603", "Provisión Bono Vacacional", "liability_current"),
            ("220101", "Provisión Prestaciones", "liability_non_current"),
            ("220102", "Provisión Intereses Prestaciones", "liability_non_current"),
            ("210704", "Otras CxP", "liability_current"),
            ("430105", "Redondeo Nómina", "income_other"),
        ]:
            Account.create({
                "code": code, "name": name, "account_type": atype,
                "company_ids": [(6, 0, [cls.company.id])],
            })
        map_rule_accounts(cls.env, cls.company)

        # Diario de nómina con cuenta por defecto (ajustes de redondeo)
        rounding = cls.env["account.account"].with_company(cls.company).search([
            ("code", "=", "430105"), ("company_ids", "in", cls.company.id)], limit=1)
        cls.payroll_journal = cls.env["account.journal"].create({
            "name": "Nómina VE", "code": "NOMI", "type": "general",
            "company_id": cls.company.id,
            "default_account_id": rounding.id,
        })
        cls.struct_regular = cls.env.ref("l10n_ve_bw_payroll.structure_ve_regular")
        cls.struct_util = cls.env.ref("l10n_ve_bw_payroll.structure_ve_utilidades")
        cls.struct_vac = cls.env.ref("l10n_ve_bw_payroll.structure_ve_vacaciones")
        cls.struct_liq = cls.env.ref("l10n_ve_bw_payroll.structure_ve_liquidacion")
        for struct in (cls.struct_regular, cls.struct_util, cls.struct_vac, cls.struct_liq):
            struct.journal_id = cls.payroll_journal

        cls.employee = cls.env["hr.employee"].create({
            "name": "Trabajador de Prueba",
            "company_id": cls.company.id,
        })
        cls.version = cls.employee.version_id
        cls.version.write({
            "wage": 500.0,
            "contract_date_start": "2026-01-15",
            "structure_type_id": cls.env.ref(
                "l10n_ve_bw_payroll.structure_type_employee_ve").id,
            "schedule_pay": "monthly",
            "l10n_ve_ari_percentage": 10.0,
        })

    def _make_payslip(self, struct=None, date_from="2026-07-01",
                      date_to="2026-07-31", inputs=None, employee=None):
        slip = self.env["hr.payslip"].create({
            "name": "Test",
            "employee_id": (employee or self.employee).id,
            "company_id": self.company.id,
            "struct_id": (struct or self.struct_regular).id,
            "date_from": date_from,
            "date_to": date_to,
        })
        if inputs:
            slip.write({"input_line_ids": [
                Command.create({
                    "input_type_id": self.env.ref(
                        "l10n_ve_bw_payroll.input_type_%s" % xmlid).id,
                    "amount": amount,
                }) for xmlid, amount in inputs.items()
            ]})
        slip.compute_sheet()
        return slip

    def _line(self, slip, code):
        return sum(slip.line_ids.filtered(lambda l: l.code == code).mapped("total"))
