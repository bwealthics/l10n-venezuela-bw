# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Frecuencias soportadas (mismo fail-loud que hr_payslip._ve_period_ratio)
PERIOD_RATIOS = {"monthly": 1.0, "semi-monthly": 0.5}

# Alícuotas mensuales LOTTT (localizacion_venezuela_odoo.md §6):
# utilidades 2,5 d/mes (art. 131) · vacaciones 1,25 (art. 190) ·
# bono vacacional 1,25 (art. 192) — sobre salario NORMAL diario.
# Prestaciones: 15 d/trimestre de servicio + 2 d/año desde el 2° año,
# sobre salario INTEGRAL diario (art. 142).
MONTHLY_DAYS = {"utilidades": 2.5, "vacaciones": 1.25, "bono_vacacional": 1.25}

CONCEPT_ACCOUNTS = {
    "utilidades": ("610403", "210601"),
    "vacaciones": ("610404", "210602"),
    "bono_vacacional": ("610405", "210603"),
    "prestaciones": ("610401", "220101"),
    "adicionales": ("610401", "220101"),
    "intereses": ("610402", "220102"),
}


class L10nVePayrollProvision(models.Model):
    _name = "l10n.ve.payroll.provision"
    _description = "Corrida mensual de provisiones laborales (LOTTT)"
    _order = "date_to desc"

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_from = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1)
        + relativedelta(months=1, days=-1))
    state = fields.Selection(
        [("draft", "Borrador"), ("posted", "Contabilizada"), ("cancel", "Cancelada")],
        default="draft", required=True, copy=False)
    line_ids = fields.One2many(
        "l10n.ve.payroll.provision.line", "provision_id")
    move_id = fields.Many2one("account.move", string="Asiento", readonly=True, copy=False)
    total = fields.Monetary(compute="_compute_total")

    _date_check = models.Constraint(
        "CHECK (date_from <= date_to)", "El período de la provisión es inválido.")

    @api.constrains("company_id", "date_from", "date_to", "state")
    def _check_period(self):
        # MONTHLY_DAYS devenga alícuotas de UN mes por corrida: el período
        # debe ser un mes calendario exacto y sin solapes por compañía
        # (incluye reactivar canceladas vía action_draft).
        for rec in self:
            if rec.state == "cancel":
                continue
            if (rec.date_from.day != 1
                    or rec.date_to != rec.date_from + relativedelta(months=1, days=-1)):
                raise ValidationError(_(
                    "El período de la provisión debe ser un mes calendario "
                    "completo (del 1 al último día del mes)."))
            if self.search_count([
                    ("id", "!=", rec.id),
                    ("company_id", "=", rec.company_id.id),
                    ("state", "!=", "cancel"),
                    ("date_from", "<=", rec.date_to),
                    ("date_to", ">=", rec.date_from)], limit=1):
                raise ValidationError(_(
                    "Ya existe otra provisión de %s con período solapado: "
                    "cancélela antes de crear o reactivar esta.",
                    rec.company_id.name))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_posted(self):
        if any(rec.state == "posted" for rec in self):
            raise UserError(_(
                "No se puede eliminar una provisión contabilizada: cancélela "
                "primero (Cancelar elimina el asiento borrador y las líneas "
                "del libro de garantía)."))

    @api.depends("date_to", "company_id")
    def _compute_name(self):
        for rec in self:
            rec.name = _("Provisiones LOTTT %s", rec.date_to.strftime("%Y-%m") if rec.date_to else "")

    @api.depends("line_ids.amount")
    def _compute_total(self):
        for rec in self:
            rec.total = sum(rec.line_ids.mapped("amount"))

    # ------------------------------------------------------------------
    # Bases por empleado
    # ------------------------------------------------------------------

    @api.model
    def _employee_monthly_base(self, employee, date_to, flag):
        """Base MENSUAL del último recibo regular validado, sumando las
        líneas cuyas reglas tienen `flag` (incluye variables como
        comisiones); sin historial, el wage mensualizado (puro normal)."""
        slip = self.env["hr.payslip"].search([
            ("employee_id", "=", employee.id),
            ("state", "in", ("validated", "paid")),
            ("struct_id.code", "=", "VEREG"),
            ("date_to", "<=", date_to),
        ], order="date_to desc", limit=1)
        if slip:
            base = sum(line.total for line in slip.line_ids
                       if line.salary_rule_id[flag])
            return base / slip._ve_period_ratio()
        version = employee.version_id
        sched = version.schedule_pay or "monthly"
        if sched not in PERIOD_RATIOS:
            raise UserError(_(
                "Frecuencia de pago '%s' no soportada por la nómina VE "
                "(empleado %s).", sched, employee.name))
        return (version.wage or 0.0) / PERIOD_RATIOS[sched]

    @api.model
    def _employee_monthly_normal(self, employee, date_to):
        """Salario NORMAL mensual (base de las alícuotas de utilidades,
        vacaciones y bono vacacional — excluye HE y accidentales)."""
        return self._employee_monthly_base(
            employee, date_to, "l10n_ve_in_salario_normal")

    @api.model
    def _employee_start_date(self, employee):
        return (employee.version_id.contract_date_start
                or employee._get_first_contract_date())

    @api.model
    def _employee_integral_daily(self, employee, date_to):
        """Salario integral diario (art. 122): salario devengado (cotizable,
        incluye HE) + alícuotas de utilidades y bono vacacional calculadas
        sobre el salario NORMAL."""
        salarial = self._employee_monthly_base(
            employee, date_to, "l10n_ve_salarial")
        normal = self._employee_monthly_normal(employee, date_to)
        util_days = employee.company_id.l10n_ve_utilidades_days or 30
        start = self._employee_start_date(employee)
        years = relativedelta(date_to, start).years if start else 0
        # Año de servicio EN CURSO: 15 + years (art. 192), igual que
        # hr_payslip._ve_bono_vacacional_days y el finiquito.
        bvac_days = min(15 + years, 30)
        return (salarial / 30.0
                + (normal / 30.0) * util_days / 360.0
                + (normal / 30.0) * bvac_days / 360.0)

    @staticmethod
    def _anniversaries_in_period(start, date_from, date_to, step_months):
        """[(n, fecha)] de aniversarios start + n×step dentro del período."""
        res, n = [], 1
        while True:
            d = start + relativedelta(months=step_months * n)
            if d > date_to:
                break
            if d >= date_from:
                res.append((n, d))
            n += 1
        return res

    # ------------------------------------------------------------------
    # Flujo
    # ------------------------------------------------------------------

    def _get_employees(self):
        self.ensure_one()
        ve_type = self.env.ref("l10n_ve_bw_payroll.structure_type_employee_ve")
        # Empleados ya liquidados en su empleo actual no se provisionan: el
        # finiquito pagó fracciones, trimestre en curso e intereses hasta el
        # egreso (una re-corrida posterior dejaría saldos huérfanos).
        struct_liq = self.env.ref(
            "l10n_ve_bw_payroll.structure_ve_liquidacion",
            raise_if_not_found=False)
        liq_dates = {}
        if struct_liq:
            for slip in self.env["hr.payslip"].search([
                    ("struct_id", "=", struct_liq.id),
                    ("state", "!=", "cancel"),
                    ("company_id", "=", self.company_id.id)]):
                prev = liq_dates.get(slip.employee_id.id)
                if not prev or slip.date_to > prev:
                    liq_dates[slip.employee_id.id] = slip.date_to

        def _active_in_period(e):
            start = self._employee_start_date(e)
            end = e.version_id.contract_date_end
            if not (e.version_id.structure_type_id == ve_type
                    and start and start <= self.date_to
                    and (not end or end >= self.date_from)):
                return False
            liq = liq_dates.get(e.id)
            return not liq or liq < start  # re-ingreso posterior sí cuenta

        return self.env["hr.employee"].search([
            ("company_id", "=", self.company_id.id),
        ]).filtered(_active_in_period)

    def action_compute(self):
        Ledger = self.env["l10n.ve.prestaciones.line"]
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Solo se recalcula una provisión en borrador."))
            rec.line_ids.unlink()
            vals_list = []
            interna = rec.company_id.l10n_ve_prestaciones_mode != "fideicomiso"
            rate_annual = self.env["hr.rule.parameter"]._get_parameter_from_code(
                "l10n_ve_prestaciones_bcv_rate", rec.date_to) if interna else 0.0
            for emp in rec._get_employees():
                normal_daily = rec._employee_monthly_normal(emp, rec.date_to) / 30.0
                integral_daily = rec._employee_integral_daily(emp, rec.date_to)
                start = rec._employee_start_date(emp)
                for concept, days in MONTHLY_DAYS.items():
                    vals_list.append({
                        "provision_id": rec.id, "employee_id": emp.id,
                        "concept": concept, "days": days,
                        "amount": days * normal_daily,
                    })
                # Aniversarios posteriores al egreso no devengan: el
                # finiquito cubre el trimestre iniciado (art. 142.a).
                end = emp.version_id.contract_date_end
                accrual_to = min(rec.date_to, end) if end else rec.date_to
                for n, d in rec._anniversaries_in_period(
                        start, rec.date_from, accrual_to, 3):
                    vals_list.append({
                        "provision_id": rec.id, "employee_id": emp.id,
                        "concept": "prestaciones", "days": 15,
                        "amount": 15 * integral_daily,
                        "date": d,
                    })
                for n, d in rec._anniversaries_in_period(
                        start, rec.date_from, accrual_to, 12):
                    if n >= 2:
                        # ponytail: adicionales al integral ACTUAL, no al
                        # "promedio del año" (informe fila 11); sobre-
                        # provisiona con aumentos (pro-trabajador).
                        days = min(2 * (n - 1), 30)
                        vals_list.append({
                            "provision_id": rec.id, "employee_id": emp.id,
                            "concept": "adicionales", "days": days,
                            "amount": days * integral_daily,
                            "date": d,
                        })
                if interna:
                    # ponytail: interés sobre el saldo al INICIO del mes
                    # (date_from), sin prorrateo de movimientos intra-mes.
                    balance = Ledger._garantia_balance(emp, rec.date_from)
                    if balance > 0:
                        vals_list.append({
                            "provision_id": rec.id, "employee_id": emp.id,
                            "concept": "intereses", "days": 0,
                            "amount": balance * rate_annual / 100.0 / 12.0,
                        })
            self.env["l10n.ve.payroll.provision.line"].create(vals_list)
        return True

    def _account_by_code(self, code):
        self.ensure_one()
        account = self.env["account.account"].with_company(self.company_id).search([
            ("code", "=", code), ("company_ids", "in", self.company_id.id)], limit=1)
        if not account:
            raise UserError(_(
                "No existe la cuenta %s en la compañía %s (chart ve_bw).",
                code, self.company_id.name))
        return account

    def action_post(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("La provisión ya fue contabilizada."))
            if not rec.line_ids:
                rec.action_compute()
            # Un finiquito pudo cerrar a un empleado DESPUÉS de calcular el
            # borrador (el cron computa el día 1): re-filtrar al postear, o
            # sus líneas dejarían saldos huérfanos en el libro de garantía
            # sobre montos que la liquidación ya pagó en efectivo.
            employees = rec._get_employees()
            rec.line_ids.filtered(
                lambda l: l.employee_id not in employees).unlink()
            if not rec.line_ids:
                raise UserError(_("No hay empleados venezolanos activos que provisionar."))
            journal = self.env.ref(
                "l10n_ve_bw_payroll.structure_ve_regular").with_company(
                rec.company_id).journal_id
            if not journal:
                raise UserError(_(
                    "Configure el diario en la estructura 'Venezuela: Nómina "
                    "Regular' antes de contabilizar provisiones."))
            totals = {}
            for line in rec.line_ids:
                totals[line.concept] = totals.get(line.concept, 0.0) + line.amount
            move_lines = []
            for concept, amount in totals.items():
                if rec.currency_id.is_zero(amount):
                    continue
                debit_code, credit_code = CONCEPT_ACCOUNTS[concept]
                label = dict(rec.line_ids._fields["concept"].selection)[concept]
                move_lines += [
                    (0, 0, {"account_id": rec._account_by_code(debit_code).id,
                            "name": "%s — %s" % (rec.name, label), "debit": amount}),
                    (0, 0, {"account_id": rec._account_by_code(credit_code).id,
                            "name": "%s — %s" % (rec.name, label), "credit": amount}),
                ]
            rec.move_id = self.env["account.move"].create({
                "journal_id": journal.id,
                "date": rec.date_to,
                "ref": rec.name,
                "line_ids": move_lines,
            })
            # Alimentar el libro de garantía (solo conceptos de prestaciones).
            # Los depósitos trimestrales/adicionales llevan la fecha del
            # aniversario que los causa: el corte del finiquito (egreso
            # intra-mes) los incluye solo si se cumplieron antes del egreso.
            ledger_vals = [{
                "employee_id": line.employee_id.id,
                "date": line.date or rec.date_to,
                "concept": "garantia" if line.concept == "prestaciones" else line.concept,
                "days": line.days,
                "daily_integral": line.amount / line.days if line.days else 0.0,
                "amount": line.amount,
                "provision_id": rec.id,
            } for line in rec.line_ids
                if line.concept in ("prestaciones", "adicionales", "intereses")]
            self.env["l10n.ve.prestaciones.line"].create(ledger_vals)
            rec.state = "posted"
        return True

    def action_cancel(self):
        for rec in self:
            move = rec.move_id
            if move:
                if move.state == "draft":
                    move.unlink()
                elif move.state == "cancel" or move.reversal_move_ids.filtered(
                        lambda m: m.state == "posted"):
                    # Efecto contable neto cero: solo desvincular
                    rec.move_id = False
                else:
                    raise UserError(_(
                        "El asiento %s está publicado: revérselo (o "
                        "restablézcalo a borrador) antes de cancelar la "
                        "provisión.", move.name))
            self.env["l10n.ve.prestaciones.line"].search(
                [("provision_id", "=", rec.id)]).unlink()
            rec.state = "cancel"
        return True

    def action_draft(self):
        self.filtered(lambda r: r.state == "cancel").state = "draft"
        return True

    @api.model
    def _cron_generate(self):
        """Crea (en borrador) la provisión del mes corriente por compañía VE.
        No contabiliza: un humano revisa y postea."""
        today = fields.Date.context_today(self)
        date_from = today.replace(day=1)
        date_to = date_from + relativedelta(months=1, days=-1)
        for company in self.env["res.company"].search(
                [("chart_template", "=", "ve_bw")]):
            if self.search_count([
                    ("company_id", "=", company.id),
                    ("date_from", "=", date_from), ("state", "!=", "cancel")]):
                continue
            self.create({
                "company_id": company.id,
                "date_from": date_from, "date_to": date_to,
            }).action_compute()


class L10nVePayrollProvisionLine(models.Model):
    _name = "l10n.ve.payroll.provision.line"
    _description = "Línea de provisión laboral"
    _order = "employee_id, concept"

    provision_id = fields.Many2one(
        "l10n.ve.payroll.provision", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="provision_id.company_id", store=True)
    currency_id = fields.Many2one(related="provision_id.currency_id")
    employee_id = fields.Many2one("hr.employee", required=True)
    concept = fields.Selection([
        ("utilidades", "Utilidades (2,5 d/mes)"),
        ("vacaciones", "Vacaciones (1,25 d/mes)"),
        ("bono_vacacional", "Bono vacacional (1,25 d/mes)"),
        ("prestaciones", "Prestaciones — garantía trimestral"),
        ("adicionales", "Prestaciones — días adicionales"),
        ("intereses", "Intereses sobre prestaciones"),
    ], required=True)
    date = fields.Date(
        help="Fecha del aniversario que causa el abono (garantía trimestral "
             "y días adicionales); vacía = fin del mes de la corrida.")
    days = fields.Float(digits=(6, 2))
    amount = fields.Monetary(required=True)
