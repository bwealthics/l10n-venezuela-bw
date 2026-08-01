# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from datetime import date as dt_date

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class L10nVeArcWizard(models.TransientModel):
    _name = "l10n.ve.arc.wizard"
    _description = "AR-C: comprobante anual de retenciones de ISLR a asalariados"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    year = fields.Integer(
        required=True,
        default=lambda self: fields.Date.context_today(self).year - 1,
        help="Ejercicio fiscal; el AR-C se entrega antes del 31 de enero "
             "siguiente (Decreto 1.808 art. 24) y al cese del trabajador.")
    employee_ids = fields.Many2many(
        "hr.employee", string="Trabajadores",
        help="Vacío = todos los trabajadores con retenciones o "
             "remuneraciones en el ejercicio.")

    def action_print(self):
        self.ensure_one()
        if not 1900 <= self.year <= 9999:
            raise UserError(_(
                "Indique un ejercicio fiscal válido (p. ej. %s).",
                fields.Date.context_today(self).year - 1))
        employees = self.employee_ids
        if not employees:
            # Criterio de lo pagado: el ejercicio del AR-C es el de la fecha
            # de PAGO (Decreto 1.808 — se retiene al pagar o abonar en cuenta)
            slips = self.env["hr.payslip"].search([
                ("company_id", "=", self.company_id.id),
                ("state", "in", ("validated", "paid")),
                ("l10n_ve_payment_date", ">=", dt_date(self.year, 1, 1)),
                ("l10n_ve_payment_date", "<=", dt_date(self.year, 12, 31)),
            ])
            employees = slips.employee_id
        if not employees:
            raise UserError(_("No hay trabajadores con nómina en %s.", self.year))
        return self.env.ref(
            "l10n_ve_bw_payroll.action_report_arc_employee").report_action(
            employees, data={"year": self.year, "company_id": self.company_id.id})


class ArcEmployeeReport(models.AbstractModel):
    _name = "report.l10n_ve_bw_payroll.report_arc_employee"
    _description = "Parser AR-C anual de asalariados"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        year = data.get("year") or fields.Date.context_today(self).year - 1
        company = self.env["res.company"].browse(
            data.get("company_id") or self.env.company.id)
        employees = self.env["hr.employee"].browse(docids)
        table = {}
        for emp in employees:
            slips = self.env["hr.payslip"].search([
                ("employee_id", "=", emp.id),
                ("company_id", "=", company.id),
                ("state", "in", ("validated", "paid")),
                ("l10n_ve_payment_date", ">=", dt_date(year, 1, 1)),
                ("l10n_ve_payment_date", "<=", dt_date(year, 12, 31)),
            ], order="l10n_ve_payment_date, date_to")
            months = {m: {"rem_usd": 0.0, "rem_bs": 0.0, "wh_usd": 0.0, "wh_bs": 0.0}
                      for m in range(1, 13)}
            for slip in slips:
                rem = sum(line.total for line in slip.line_ids
                          if line.salary_rule_id.l10n_ve_in_islr_base)
                wh = -sum(line.total for line in slip.line_ids
                          if line.code == "VE_ISLR")
                rate = slip.l10n_ve_bcv_rate
                if not rate and (rem or wh):
                    # Fail-loud con auto-reintento (tasa cargada después)
                    rate = slip._ve_rate()
                rate = rate or 0.0
                m = (slip.l10n_ve_payment_date or slip.date_to).month
                months[m]["rem_usd"] += rem
                months[m]["rem_bs"] += rem * rate
                months[m]["wh_usd"] += wh
                months[m]["wh_bs"] += wh * rate
            table[emp.id] = {
                "months": months,
                "total_rem_bs": sum(v["rem_bs"] for v in months.values()),
                "total_wh_bs": sum(v["wh_bs"] for v in months.values()),
                "total_rem_usd": sum(v["rem_usd"] for v in months.values()),
                "total_wh_usd": sum(v["wh_usd"] for v in months.values()),
            }
        return {
            "doc_ids": docids,
            "doc_model": "hr.employee",
            "docs": employees,
            "year": year,
            "company": company,
            "table": table,
        }
