# Part of l10n_ve_bw_payroll. License LGPL-3.
"""Soportes de declaraciones institucionales VE en un XLSX multi-hoja.

ponytail: los portales (TIUNA, FAOV en Línea, SIGAT, RNET) cambian sus
formatos sin aviso y no publican spec estable — se genera el soporte con los
montos exactos para transcribir/cargar; los TXT oficiales se agregarán
cuando haya una planilla real del cliente para validar el layout.
"""
import base64
import io

import xlsxwriter

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class L10nVeDeclaracionesWizard(models.TransientModel):
    _name = "l10n.ve.declaraciones.wizard"
    _description = "Soportes de declaraciones de nómina (Venezuela)"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    date_from = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1)
        + relativedelta(months=1, days=-1))
    file = fields.Binary(string="Archivo generado", readonly=True)
    filename = fields.Char()

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wiz in self:
            if wiz.date_from > wiz.date_to:
                raise ValidationError(_("El período es inválido."))

    # ------------------------------------------------------------------
    # Fuentes
    # ------------------------------------------------------------------

    def _slips(self, payment_period=False):
        """Recibos validados/pagados del período (por período del recibo, o
        por fecha de PAGO para las declaraciones que agregan por mes pagado)."""
        self.ensure_one()
        field = "l10n_ve_payment_date" if payment_period else "date_to"
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "in", ("validated", "paid")),
        ]
        if payment_period:
            # Fallback por date_to para recibos sin fecha de pago congelada
            domain += ["|",
                       "&", (field, ">=", self.date_from), (field, "<=", self.date_to),
                       "&", "&", (field, "=", False),
                       ("date_to", ">=", self.date_from),
                       ("date_to", "<=", self.date_to)]
        else:
            # Contención por date_to: cada recibo se atribuye a UN período
            # (un VEVAC que cruza de mes iría a dos corridas con solape).
            domain += [("date_to", ">=", self.date_from),
                       ("date_to", "<=", self.date_to)]
        return self.env["hr.payslip"].search(domain, order="employee_id, date_from")

    @staticmethod
    def _sum(slip, code=None, flag=None):
        return sum(
            line.total for line in slip.line_ids
            if (code and line.code == code)
            or (flag and line.salary_rule_id[flag]))

    @staticmethod
    def _rate(slip):
        if not slip.l10n_ve_bcv_rate:
            raise UserError(_(
                "El recibo %s no tiene tasa BCV congelada.", slip.name))
        return slip.l10n_ve_bcv_rate

    # ------------------------------------------------------------------
    # Filas por declaración (separadas del XLSX para poder testearlas)
    # ------------------------------------------------------------------

    def _tiuna_rows(self):
        """IVSS/RPE por trabajador: cotizaciones de recibos regulares Y de
        vacaciones (VEVAC también cotiza); lunes solo del recibo regular (el
        VEVAC solapa las mismas semanas). semanal_bs se reconstruye de los
        agregados de la fila: semanal × 4% × lunes == IVSS retenido."""
        rows = {}
        for slip in self._slips().filtered(
                lambda s: s.struct_id.code in ("VEREG", "VEVAC")):
            emp, rate = slip.employee_id, self._rate(slip)
            r = rows.setdefault(emp.id, {
                "cedula": emp.identification_id or "", "nombre": emp.name,
                "semanal_bs": 0.0, "lunes": 0, "ivss_emp_bs": 0.0,
                "ivss_pat_bs": 0.0, "rpe_emp_bs": 0.0, "rpe_pat_bs": 0.0,
            })
            r["ivss_emp_bs"] += -self._sum(slip, code="VE_IVSS_EMP") * rate
            r["ivss_pat_bs"] += self._sum(slip, code="VE_IVSS_PAT") * rate
            r["rpe_emp_bs"] += -self._sum(slip, code="VE_RPE_EMP") * rate
            r["rpe_pat_bs"] += self._sum(slip, code="VE_RPE_PAT") * rate
            if slip.struct_id.code == "VEREG":
                r["lunes"] += slip._ve_mondays()
            emp_rate = slip._ve_param("l10n_ve_ivss_emp_rate")
            if emp_rate and r["lunes"]:
                r["semanal_bs"] = r["ivss_emp_bs"] / emp_rate / r["lunes"]
        return list(rows.values())

    def _faov_rows(self):
        """FAOV por trabajador: salario integral Bs y ahorro 3%."""
        rows = {}
        for slip in self._slips():
            emp, rate = slip.employee_id, self._rate(slip)
            faov_emp = -self._sum(slip, code="VE_FAOV_EMP")
            faov_pat = self._sum(slip, code="VE_FAOV_PAT")
            if not (faov_emp or faov_pat):
                continue
            r = rows.setdefault(emp.id, {
                "cedula": emp.identification_id or "", "nombre": emp.name,
                "integral_bs": 0.0, "emp_1_bs": 0.0, "pat_2_bs": 0.0, "total_bs": 0.0,
            })
            emp_pct = slip._ve_param("l10n_ve_faov_emp_rate")
            r["integral_bs"] += (faov_emp / emp_pct if emp_pct else 0.0) * rate
            r["emp_1_bs"] += faov_emp * rate
            r["pat_2_bs"] += faov_pat * rate
            r["total_bs"] = r["emp_1_bs"] + r["pat_2_bs"]
        return list(rows.values())

    def _inces_rows(self):
        """INCES por mes: base normal, 2% patronal y ½% sobre utilidades."""
        rows = {}
        for slip in self._slips():
            rate = self._rate(slip)
            key = slip.date_to.replace(day=1)
            r = rows.setdefault(key, {
                "mes": key.strftime("%Y-%m"), "base_usd": 0.0, "base_bs": 0.0,
                "pat_2_usd": 0.0, "pat_2_bs": 0.0, "ret_medio_usd": 0.0,
                "ret_medio_bs": 0.0,
            })
            base = self._sum(slip, flag="l10n_ve_in_inces_base")
            pat = self._sum(slip, code="VE_INCES_PAT")
            medio = -(self._sum(slip, code="VE_INCES_UTIL")
                      + self._sum(slip, code="VE_LIQ_INCES_UTIL"))
            r["base_usd"] += base
            r["base_bs"] += base * rate
            r["pat_2_usd"] += pat
            r["pat_2_bs"] += pat * rate
            r["ret_medio_usd"] += medio
            r["ret_medio_bs"] += medio * rate
        return [rows[k] for k in sorted(rows)]

    def _cepp_rows(self):
        """Forma 19 DPP: agregación EXACTA por trabajador-mes de pago, con
        piso IMI aplicado una sola vez por mes; la columna diferencia muestra
        el ajuste vs lo devengado por recibo (VE_CEPP_PAT)."""
        Param = self.env["hr.rule.parameter"]
        buckets = {}
        for slip in self._slips(payment_period=True):
            month = (slip.l10n_ve_payment_date or slip.date_to).replace(day=1)
            buckets.setdefault((slip.employee_id, month), []).append(slip)
        rows = []
        for (emp, month), slips in sorted(
                buckets.items(), key=lambda i: (i[0][1], i[0][0].name)):
            month_end = month + relativedelta(months=1, days=-1)
            base = sum(self._sum(s, flag="l10n_ve_in_pension_base") for s in slips)
            devengado = sum(self._sum(s, code="VE_CEPP_PAT") for s in slips)
            floor = Param._get_parameter_from_code(
                "l10n_ve_imi_cepp_floor_usd", month_end)
            pct = Param._get_parameter_from_code(
                "l10n_ve_cepp_pat_rate", month_end)
            cuota = max(base, floor) * pct
            rate = self._rate(slips[-1])
            rows.append({
                "cedula": emp.identification_id or "", "nombre": emp.name,
                "mes": month.strftime("%Y-%m"), "base_usd": base,
                "piso_usd": floor, "cuota_usd": cuota, "cuota_bs": cuota * rate,
                "devengado_usd": devengado, "diferencia_usd": cuota - devengado,
            })
        return rows

    def _headcount_rows(self):
        """Informe trimestral CEPP: trabajadores activos por mes."""
        rows = []
        month = self.date_from.replace(day=1)
        Provision = self.env["l10n.ve.payroll.provision"]
        ve_type = self.env.ref("l10n_ve_bw_payroll.structure_type_employee_ve")
        employees = self.env["hr.employee"].with_context(active_test=False).search(
            [("company_id", "=", self.company_id.id)])
        while month <= self.date_to:
            month_end = month + relativedelta(months=1, days=-1)
            count = len(employees.filtered(
                lambda e: e.version_id.structure_type_id == ve_type
                and (start := Provision._employee_start_date(e))
                and start <= month_end
                and (not e.version_id.contract_date_end
                     or e.version_id.contract_date_end >= month)))
            rows.append({"mes": month.strftime("%Y-%m"), "trabajadores": count})
            month += relativedelta(months=1)
        return rows

    def _rnet_rows(self):
        """Declaración trimestral RNET: nómina con altas y bajas del período."""
        Provision = self.env["l10n.ve.payroll.provision"]
        ve_type = self.env.ref("l10n_ve_bw_payroll.structure_type_employee_ve")
        rows = []
        for emp in self.env["hr.employee"].with_context(active_test=False).search(
                [("company_id", "=", self.company_id.id)]):
            if emp.version_id.structure_type_id != ve_type:
                continue
            start = Provision._employee_start_date(emp)
            end = emp.version_id.contract_date_end
            if not start or start > self.date_to or (end and end < self.date_from):
                continue
            # No sub-declarar por recibos prorrateados (ausencias/egreso):
            # al menos el salario contractual mensualizado
            ratio = {"monthly": 1.0, "semi-monthly": 0.5}.get(
                emp.version_id.schedule_pay or "monthly", 1.0)
            monthly = max(
                Provision._employee_monthly_normal(emp, self.date_to),
                (emp.version_id.wage or 0.0) / ratio)
            estados = []
            if start >= self.date_from:
                estados.append("alta")
            if end and end <= self.date_to:
                estados.append("baja")
            estado = " y ".join(estados) or "activo"
            rows.append({
                "cedula": emp.identification_id or "", "nombre": emp.name,
                "cargo": emp.job_title or "", "ingreso": str(start),
                "egreso": str(end or ""), "estado": estado,
                "salario_usd": monthly,
            })
        return rows

    def _he_rows(self):
        """Libro de horas extra (art. 183): horas por mes + acumulado anual
        con alerta del límite de 100 h/año. ponytail: el límite semanal de
        10 h no es derivable de inputs mensuales — controlarlo al capturar."""
        year_start = self.date_from.replace(month=1, day=1)
        slips = self.env["hr.payslip"].search([
            ("company_id", "=", self.company_id.id),
            ("state", "in", ("validated", "paid")),
            ("date_to", ">=", year_start), ("date_to", "<=", self.date_to),
        ])
        rows = {}
        for slip in slips:
            hours = sum(line.amount for line in slip.input_line_ids
                        if line.code in ("HED_H", "HEN_H"))
            if not hours:
                continue
            emp = slip.employee_id
            r = rows.setdefault((emp.id, slip.date_to.year), {
                "cedula": emp.identification_id or "", "nombre": emp.name,
                "horas_periodo": 0.0, "horas_anual": 0.0,
            })
            r["horas_anual"] += hours
            if slip.date_to >= self.date_from:
                r["horas_periodo"] += hours
        result = list(rows.values())
        for r in result:
            r["alerta"] = "> 100 h/año (art. 178 LOTTT)" if r["horas_anual"] > 100 else ""
        return result

    # ------------------------------------------------------------------
    # XLSX
    # ------------------------------------------------------------------

    SHEETS = (
        ("IVSS-TIUNA", "_tiuna_rows",
         ("Cédula", "Nombre", "Salario semanal Bs", "Lunes", "IVSS 4% Bs",
          "IVSS patronal Bs", "RPE 0,5% Bs", "RPE 2% Bs"),
         ("cedula", "nombre", "semanal_bs", "lunes", "ivss_emp_bs",
          "ivss_pat_bs", "rpe_emp_bs", "rpe_pat_bs")),
        ("FAOV", "_faov_rows",
         ("Cédula", "Nombre", "Salario integral Bs", "Ahorro 1% Bs",
          "Aporte patronal 2% Bs", "Total 3% Bs"),
         ("cedula", "nombre", "integral_bs", "emp_1_bs", "pat_2_bs", "total_bs")),
        ("INCES", "_inces_rows",
         ("Mes", "Base salario normal USD", "Base Bs", "Aporte 2% USD",
          "Aporte 2% Bs", "Retención ½% utilidades USD", "Retención ½% Bs"),
         ("mes", "base_usd", "base_bs", "pat_2_usd", "pat_2_bs",
          "ret_medio_usd", "ret_medio_bs")),
        ("CEPP Forma 19", "_cepp_rows",
         ("Cédula", "Nombre", "Mes de pago", "Base total USD", "Piso IMI USD",
          "Cuota 9% USD", "Cuota Bs", "Devengado en nómina USD", "Diferencia USD"),
         ("cedula", "nombre", "mes", "base_usd", "piso_usd", "cuota_usd",
          "cuota_bs", "devengado_usd", "diferencia_usd")),
        ("Headcount CEPP", "_headcount_rows",
         ("Mes", "Trabajadores activos"), ("mes", "trabajadores")),
        ("RNET", "_rnet_rows",
         ("Cédula", "Nombre", "Cargo", "Ingreso", "Egreso", "Estado",
          "Salario mensual USD"),
         ("cedula", "nombre", "cargo", "ingreso", "egreso", "estado",
          "salario_usd")),
        ("Horas Extra", "_he_rows",
         ("Cédula", "Nombre", "Horas del período", "Acumulado anual", "Alerta"),
         ("cedula", "nombre", "horas_periodo", "horas_anual", "alerta")),
    )

    def action_generate(self):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        try:
            bold = workbook.add_format({"bold": True})
            num = workbook.add_format({"num_format": "#,##0.00"})
            for name, method, headers, keys in self.SHEETS:
                sheet = workbook.add_worksheet(name)
                sheet.write_row(0, 0, headers, bold)
                for i, row in enumerate(getattr(self, method)(), start=1):
                    for j, key in enumerate(keys):
                        value = row.get(key)
                        if isinstance(value, float):
                            sheet.write_number(i, j, value, num)
                        else:
                            sheet.write(i, j, value if value is not None else "")
                sheet.set_column(0, len(headers) - 1, 18)
        finally:
            workbook.close()
        self.write({
            "file": base64.b64encode(output.getvalue()),
            "filename": "declaraciones_ve_%s_%s.xlsx" % (self.date_from, self.date_to),
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
