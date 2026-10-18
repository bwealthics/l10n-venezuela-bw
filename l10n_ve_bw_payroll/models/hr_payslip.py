# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Flag de hr.salary.rule que define cada base legal venezolana.
VE_BASE_FLAGS = {
    "cotizable": "l10n_ve_salarial",           # IVSS / RPE / FAOV (salario, art. 104 LOTTT)
    "normal": "l10n_ve_in_salario_normal",     # vacaciones, bono vacacional, referencia general
    "inces": "l10n_ve_in_inces_base",          # INCES 2% (normal sin HE ni accidentales)
    "islr": "l10n_ve_in_islr_base",            # retención ISLR (AR-I)
    "pension": "l10n_ve_in_pension_base",      # CEPP 9% (todo pago, salarial o no)
}

# Fracción de mes que aporta cada período de pago: ratio = 12 / pagos_al_año.
# Así ratio × pagos_al_año == 12 y los topes legales, la cesta y el CEPP
# mensualizados cierran el año exacto. Semanal son 52 pagos → 12/52, NO 7/30:
# el 7/30 anualiza 12,13 meses y sobrepaga ~1,1 %.
PERIOD_RATIOS = {
    "monthly": 1.0,        # 12 pagos/año
    "semi-monthly": 0.5,   # 24 pagos/año
    "weekly": 12.0 / 52,   # 52 pagos/año
}


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_ve_payment_date = fields.Date(
        string="Fecha de pago (VE)",
        compute="_compute_l10n_ve_payment_date", store=True, readonly=False,
        help="Fecha prevista de pago: su tasa BCV rige todos los montos "
             "legales en Bs y el contravalor del recibo.")
    l10n_ve_bcv_rate = fields.Float(
        string="Tasa BCV (Bs/moneda cía.)", digits=(16, 6),
        compute="_compute_l10n_ve_bcv_rate", store=True, readonly=False,
        help="Bolívares por unidad de la moneda de la compañía a la fecha de "
             "pago. Se congela al almacenarse; el gerente de nómina puede "
             "corregirla manualmente.")
    l10n_ve_total_ves = fields.Float(
        string="Neto en Bs", digits=(16, 2),
        compute="_compute_l10n_ve_total_ves")

    @api.depends("date_to")
    def _compute_l10n_ve_payment_date(self):
        for slip in self:
            if not slip.l10n_ve_payment_date:
                slip.l10n_ve_payment_date = slip.date_to

    @api.depends("l10n_ve_payment_date", "company_id")
    def _compute_l10n_ve_bcv_rate(self):
        Currency = self.env["res.currency"]
        ves = self.env.ref("base.VES", raise_if_not_found=False)
        for slip in self:
            date = slip.l10n_ve_payment_date or slip.date_to
            rate = 0.0
            if ves and date:
                # res.currency._convert cae en silencio a 1:1 sin tasa cargada;
                # aquí eso sería un recibo errado, así que solo se acepta una
                # tasa real (mismo guard que l10n.ve.ut._require_ves_rate).
                has_rate = self.env["res.currency.rate"].sudo().search_count([
                    ("currency_id", "=", ves.id),
                    ("company_id", "in", [slip.company_id.id, False]),
                    ("name", "<=", date),
                ], limit=1)
                if has_rate:
                    rate = Currency._get_conversion_rate(
                        slip.company_id.currency_id, ves, slip.company_id, date)
            slip.l10n_ve_bcv_rate = rate

    @api.depends("line_ids.total", "l10n_ve_bcv_rate")
    def _compute_l10n_ve_total_ves(self):
        for slip in self:
            net = sum(slip.line_ids.filtered(lambda l: l.code == "NET").mapped("total"))
            slip.l10n_ve_total_ves = net * (slip.l10n_ve_bcv_rate or 0.0)

    def action_payslip_done(self):
        # SCS 523/2025 / art. 19 LOTTT: un finiquito con neto negativo cobra
        # al trabajador por nómina (210508 quedaría deudora). El wizard ya lo
        # valida; este guard cubre el camino del input LIQ_COMP cargado a
        # mano en el recibo.
        for slip in self.filtered(lambda s: s.struct_id.code == "VELIQ"):
            net = sum(slip.line_ids.filtered(
                lambda l: l.code == "NET").mapped("total"))
            if slip.currency_id.compare_amounts(net, 0.0) < 0:
                raise UserError(_(
                    "El finiquito de %(employee)s tiene neto negativo "
                    "(%(net)s): la compensación u otras deducciones exceden "
                    "lo pagadero (SCS 523/2025, irrenunciabilidad art. 19 "
                    "LOTTT).",
                    employee=slip.employee_id.name,
                    net=slip.currency_id.round(net)))
        return super().action_payslip_done()

    # ------------------------------------------------------------------
    # Helpers de cálculo — las reglas salariales son one-liners sobre esto.
    # Solo usan la intersección de APIs Enterprise/OCA (date_from/date_to,
    # employee, versión vía _ve_version) para portabilidad futura.
    # ------------------------------------------------------------------

    def _ve_version(self):
        """Contrato vigente del recibo (hr.version en 18/19; en un futuro
        adapter OCA sería el contract)."""
        self.ensure_one()
        return self.version_id

    def _ve_rate(self):
        self.ensure_one()
        if not self.l10n_ve_bcv_rate:
            # La tasa pudo cargarse en res.currency.rate DESPUÉS de crear el
            # recibo; el compute no depende de ese modelo, así que se reintenta
            # (nunca pisa un override manual: solo corre con el campo en 0).
            self._compute_l10n_ve_bcv_rate()
        if not self.l10n_ve_bcv_rate:
            raise UserError(_(
                "No hay tasa BCV (Bs) cargada al %s: cargue la tasa en "
                "Contabilidad > Monedas antes de "
                "calcular la nómina.", self.l10n_ve_payment_date or self.date_to))
        return self.l10n_ve_bcv_rate

    def _ve_require_usd(self):
        """Los parámetros indexados (cesta ticket, piso IMI del CEPP) están
        fijados en USD; convertirlos a otra moneda funcional exigiría
        triangular USD→VES→cía. con guard de tasa propio. Ambos clientes VE
        operan en USD — fail loud si eso cambia."""
        self.ensure_one()
        if self.company_id.currency_id.name != "USD":
            raise UserError(_(
                "Los parámetros de nómina VE indexados están en USD y la "
                "moneda de la compañía es %s: agregue la conversión en "
                "l10n_ve_bw_payroll.", self.company_id.currency_id.name))

    def _ve_param(self, code):
        """Parámetro legal vigente a la fecha del recibo (hr.rule.parameter)."""
        self.ensure_one()
        return self.env["hr.rule.parameter"]._get_parameter_from_code(
            code, self.date_to)

    def _ve_period_ratio(self):
        # Fail loud ante frecuencias no soportadas: un default silencioso
        # desmensualizaría topes y cesta (p. ej. bi-weekly son 26 pagos/año,
        # no 24 — añadirlo es una línea en PERIOD_RATIOS: 12/26).
        sched = self._ve_version().schedule_pay or "monthly"
        if sched not in PERIOD_RATIOS:
            raise UserError(_(
                "Frecuencia de pago '%s' no soportada por la nómina VE: use "
                "mensual, quincenal (semi-monthly) o semanal (weekly).", sched))
        return PERIOD_RATIOS[sched]

    def _ve_mondays(self):
        """Lunes contenidos en [date_from, date_to] (semanas cotizadas IVSS)."""
        self.ensure_one()
        first = self.date_from + timedelta(days=(0 - self.date_from.weekday()) % 7)
        if first > self.date_to:
            return 0
        return (self.date_to - first).days // 7 + 1

    # Semántica Odoo 19: hr.version.wage es el monto POR PERÍODO de pago (el
    # motor de worked days reparte el wage íntegro en cada recibo; el costo
    # anual usa 24 pagos semi-monthly). Quincenal → cargar la mitad del
    # sueldo mensual en el contrato.

    def _ve_monthly_wage(self):
        self.ensure_one()
        return (self._ve_version().wage or 0.0) / self._ve_period_ratio()

    def _ve_period_days(self):
        """Días base del período (LOTTT: mes de 30 días, quincena de 15)."""
        self.ensure_one()
        return {1.0: 30, 0.5: 15}.get(self._ve_period_ratio(), 7)

    def _ve_covered_days(self):
        """Días base del período cubiertos por el contrato, sin descontar
        ausencias: la quincena completa vale 15 aunque tenga 13 o 16 días;
        ingreso o egreso a mitad de período = días del contrato en él."""
        self.ensure_one()
        version = self._ve_version()
        base = self._ve_period_days()
        start = max(self.date_from, version.contract_date_start or self.date_from)
        end = min(self.date_to, version.contract_date_end or self.date_to)
        if end < start:
            return 0
        if start == self.date_from and end == self.date_to:
            return base
        return min((end - start).days + 1, base)

    def _ve_day_ratio(self):
        """Fracción del período devengada, por DÍAS CALENDARIO: en Venezuela
        el salario se causa por día (diario = mensual / 30), no por horas del
        calendario de trabajo. Contrato que cubre el período = 1 (aunque la
        quincena tenga 16 o 13 días); ingreso o egreso a mitad de período =
        días del contrato en el período / días base. Las ausencias no
        remuneradas (worked days sin pago) descuentan días."""
        self.ensure_one()
        unpaid = sum(wd.number_of_days for wd in self.worked_days_line_ids
                     if not wd.is_paid and wd.code != "OUT")
        return max(self._ve_covered_days() - unpaid, 0.0) / self._ve_period_days()

    def _ve_liq_daily_salary(self):
        """Salario diario de los días pendientes del finiquito: misma base
        que las prestaciones (res.company.l10n_ve_benefits_base)."""
        self.ensure_one()
        if self.company_id.l10n_ve_benefits_base == "minimum_wage":
            return (self._ve_param("l10n_ve_minimum_wage_ves")
                    / self._ve_rate() / 30.0)
        return self._ve_daily_wage()

    def _ve_cesta_daily(self):
        self.ensure_one()
        self._ve_require_usd()
        return self._ve_param("l10n_ve_cesta_ticket_usd") / 30.0

    # --- Descanso semanal remunerado (art. 173 LOTTT) ---

    def _get_worked_day_lines(self, domain=None, check_out_of_version=True):
        res = super()._get_worked_day_lines(
            domain=domain, check_out_of_version=check_out_of_version)
        if check_out_of_version:
            rest = self._ve_rest_day_line(res)
            if rest:
                res.append(rest)
        return res

    def _ve_rest_day_line(self, lines):
        """Los días de descanso semanal son remunerados (art. 173 LOTTT) y el
        sueldo mensual ya los incluye: la quincena paga 15 días. Las entradas
        de trabajo solo traen los días laborados, así que el recibo mostraba
        11-13 días aunque el BASIC pagara los 15. Esta línea completa los días
        cubiertos por el contrato; no cambia el monto (el BASIC se calcula
        por días en _ve_basic_wage, y el core reparte el sueldo entre las
        líneas pagadas). Contrato por hora: no aplica, ahí el descanso se
        paga aparte por semana cumplida y el complemento sobrepagaría."""
        self.ensure_one()
        if (self.struct_id.code != "VEREG" or self.wage_type == "hourly"
                or self.company_id.country_id.code != "VE"):
            return None
        rest_type = self.env.ref(
            "l10n_ve_bw_payroll.work_entry_type_ve_descanso",
            raise_if_not_found=False)
        if not rest_type:
            return None
        out_type = self.env.ref(
            "hr_work_entry.hr_work_entry_type_out_of_contract",
            raise_if_not_found=False)
        counted = sum(line["number_of_days"] for line in lines
                      if not out_type or line["work_entry_type_id"] != out_type.id)
        days = round(self._ve_covered_days() - counted, 5)
        # ponytail: si se laboró más que lo cubierto (trabajo en día de
        # descanso, art. 120) no hay complemento; el recargo del 50 % y el
        # descanso compensatorio van por input, no se infieren aquí.
        if days <= 0:
            return None
        return {
            "sequence": rest_type.sequence,
            "work_entry_type_id": rest_type.id,
            "number_of_days": days,
            "number_of_hours": days * (self._get_worked_day_lines_hours_per_day() or 8.0),
        }

    def _ve_basic_wage(self):
        self.ensure_one()
        # No delega en el motor de worked days: Odoo prorratea por horas del
        # calendario (sueldo × horas / horas del período), que en ingresos a
        # mitad de quincena o jornadas rotativas no da el salario por días.
        # Contrato por hora: no hay sueldo fijo que prorratear (wage = 0), el
        # devengo son las horas trabajadas → se mantiene el motor.
        if self.wage_type == "hourly":
            return self._get_paid_amount()
        return (self._ve_version().wage or 0.0) * self._ve_day_ratio()

    def _ve_daily_wage(self):
        """Salario diario LOTTT: sueldo MENSUAL / 30 (base de HE y feriados),
        independiente de la frecuencia de pago."""
        return self._ve_monthly_wage() / 30.0

    def _ve_monthly_base_from_history(self, flag, before_date):
        """Base MENSUAL real desde el último recibo regular validado antes de
        la fecha dada (suma de líneas cuyas reglas tienen `flag`, incluye
        variables); sin historial, el wage mensualizado."""
        self.ensure_one()
        slip = self.env["hr.payslip"].search([
            ("employee_id", "=", self.employee_id.id),
            ("state", "in", ("validated", "paid")),
            ("struct_id.code", "=", "VEREG"),
            ("date_to", "<=", before_date),
        ], order="date_to desc", limit=1)
        if slip:
            base = sum(line.total for line in slip.line_ids
                       if line.salary_rule_id[flag])
            # ponytail: en quincenal mensualiza dividiendo por el ratio del
            # último recibo; una comisión pagada UNA vez al mes se duplicaría
            # — aceptable mientras las variables se paguen por quincena.
            return base / slip._ve_period_ratio()
        return self._ve_monthly_wage()

    def _ve_monthly_normal_prev(self):
        """Salario NORMAL del mes anterior al período (art. 121 LOTTT): base
        del pago de vacaciones y bono vacacional."""
        return self._ve_monthly_base_from_history(
            "l10n_ve_in_salario_normal", self.date_from)

    def _ve_util_average_daily(self):
        """Promedio diario del salario normal del ejercicio (art. 131 LOTTT):
        base del pago de utilidades. Agrupa los recibos regulares validados
        del año calendario por mes; sin historial, el sueldo del contrato."""
        self.ensure_one()
        slips = self.env["hr.payslip"].search([
            ("employee_id", "=", self.employee_id.id),
            ("state", "in", ("validated", "paid")),
            ("struct_id.code", "=", "VEREG"),
            ("date_from", ">=", self.date_to.replace(month=1, day=1)),
            ("date_to", "<=", self.date_to),
        ])
        if not slips:
            return self._ve_monthly_wage() / 30.0
        months = {}
        for slip in slips:
            key = (slip.date_to.year, slip.date_to.month)
            months[key] = months.get(key, 0.0) + sum(
                line.total for line in slip.line_ids
                if line.salary_rule_id.l10n_ve_in_salario_normal)
        return sum(months.values()) / len(months) / 30.0

    def _ve_hourly_wage(self):
        # ponytail: jornada diurna estándar de 8 h (art. 173 LOTTT); si un
        # cliente pacta jornadas menores, leer del calendario laboral.
        return self._ve_daily_wage() / 8.0

    def _ve_base(self, kind, result_rules):
        """Suma de las líneas ya calculadas cuyas reglas integran la base
        `kind` (ver VE_BASE_FLAGS). result_rules viene del localdict."""
        self.ensure_one()
        flag = VE_BASE_FLAGS[kind]
        total = 0.0
        for rule in self.struct_id.rule_ids.filtered(lambda r: r[flag]):
            total += result_rules[rule.code]["total"]
        return total

    def _ve_monthly_base(self, kind, result_rules):
        """Base mensualizada: los topes legales son mensuales aunque el
        recibo sea quincenal."""
        ratio = self._ve_period_ratio()
        return self._ve_base(kind, result_rules) / ratio if ratio else 0.0

    def _ve_capped_monthly_base(self, result_rules, cap_code):
        """Base cotizable mensual topada en N salarios mínimos (convertidos
        de Bs a moneda de compañía a la tasa BCV del recibo)."""
        sm_ves = self._ve_param("l10n_ve_minimum_wage_ves")
        cap_sm = self._ve_param(cap_code)
        cap = (cap_sm * sm_ves) / self._ve_rate()
        return min(self._ve_monthly_base("cotizable", result_rules), cap)

    # --- IVSS (LSS art. 66: cotización semanal por lunes del mes) ---

    def _ve_ivss_weekly(self, result_rules):
        base = self._ve_capped_monthly_base(result_rules, "l10n_ve_ivss_cap_sm")
        return base * 12.0 / 52.0

    def _ve_ivss_employee(self, result_rules):
        rate = self._ve_param("l10n_ve_ivss_emp_rate")
        return -(self._ve_ivss_weekly(result_rules) * rate * self._ve_mondays())

    def _ve_ivss_employer(self, result_rules):
        rates = self._ve_param("l10n_ve_ivss_pat_rates")
        rate = rates.get(self.company_id.l10n_ve_ivss_risk or "min")
        return self._ve_ivss_weekly(result_rules) * rate * self._ve_mondays()

    # --- RPE / Paro Forzoso (LRPE art. 46: 2,5% mensual, tope 10 SM) ---
    # ponytail: base legal = salario normal del mes ANTERIOR; se usa el del
    # período (solo difiere el mes de un aumento y el tope Bs 1.300 hace la
    # diferencia < Bs 7). Cambiar a mes anterior si un auditor lo exige.

    def _ve_rpe_employee(self, result_rules):
        base = self._ve_capped_monthly_base(result_rules, "l10n_ve_rpe_cap_sm")
        rate = self._ve_param("l10n_ve_rpe_emp_rate")
        return -(base * rate * self._ve_period_ratio())

    def _ve_rpe_employer(self, result_rules):
        base = self._ve_capped_monthly_base(result_rules, "l10n_ve_rpe_cap_sm")
        rate = self._ve_param("l10n_ve_rpe_pat_rate")
        return base * rate * self._ve_period_ratio()

    # --- FAOV (LRPVH art. 30-33: 3% del salario integral, sin tope) ---

    def _ve_bono_vacacional_days(self):
        """Días de bono vacacional del año de servicio EN CURSO: 15 el primer
        año + 1 por año adicional, tope 30 (art. 192 LOTTT). El año en curso
        tras `years` cumplidos devenga 15 + years — misma fórmula que la
        fracción del finiquito (liquidacion_wizard)."""
        self.ensure_one()
        version = self._ve_version()
        start = version.contract_date_start or self.employee_id._get_first_contract_date()
        years = relativedelta(self.date_to, start).years if start else 0
        return min(15 + years, 30)

    def _ve_faov_base(self, result_rules):
        """Salario integral del período: normal + alícuotas de utilidades y
        bono vacacional (art. 122 LOTTT)."""
        normal = self._ve_base("cotizable", result_rules)
        util_days = self.company_id.l10n_ve_utilidades_days or 30
        return normal * (1 + util_days / 360.0 + self._ve_bono_vacacional_days() / 360.0)

    def _ve_faov_employee(self, result_rules):
        rate = self._ve_param("l10n_ve_faov_emp_rate")
        return -(self._ve_faov_base(result_rules) * rate)

    def _ve_faov_employer(self, result_rules):
        rate = self._ve_param("l10n_ve_faov_pat_rate")
        return self._ve_faov_base(result_rules) * rate

    # --- ISLR sobre sueldos (Decreto 1.808: % autodeterminado en el AR-I) ---

    def _ve_islr(self, result_rules):
        pct = self._ve_version().l10n_ve_ari_percentage
        if not pct:
            return 0.0
        return -(self._ve_base("islr", result_rules) * pct / 100.0)

    # --- INCES ---

    def _ve_inces_employer(self, result_rules):
        rate = self._ve_param("l10n_ve_inces_pat_rate")
        return self._ve_base("inces", result_rules) * rate

    def _ve_inces_utilidades(self, result_rules):
        """½% sobre utilidades pagadas, retenido al trabajador (art. 50
        Decreto-Ley INCES 2014). Solo en la estructura de Utilidades."""
        rate = self._ve_param("l10n_ve_inces_emp_rate")
        return -(self._ve_base("cotizable", result_rules) * rate)

    # --- Cesta ticket socialista (indexado en USD, criterio SCS 712/2024) ---

    def _ve_cesta_ticket(self):
        self.ensure_one()
        if not self._ve_version().l10n_ve_cesta_ticket:
            return 0.0
        self._ve_require_usd()
        # Se causa por día como el salario: ingreso a mitad de período o días
        # sin goce reducen la cesta en la misma proporción.
        return (self._ve_param("l10n_ve_cesta_ticket_usd") * self._ve_period_ratio()
                * self._ve_day_ratio())

    def _ve_cesta_complement(self):
        """Complemento mensual del beneficio de alimentación pactado en el
        contrato: no remunerativo (art. 105.2 LOTTT, SCS 523 del 13-11-2025),
        mismo tratamiento contable y de bases que la cesta legal."""
        self.ensure_one()
        amount = self._ve_version().l10n_ve_cesta_complement_usd or 0.0
        if not amount:
            return 0.0
        self._ve_require_usd()
        return amount * self._ve_period_ratio() * self._ve_day_ratio()

    # --- CEPP (Ley de Protección de las Pensiones 2024, 9% con piso IMI) ---

    def _ve_cepp_employer(self, result_rules):
        # ponytail: el piso IMI se aplica por recibo (prorrateado); la Forma
        # 19 DPP es por trabajador-MES, así que en un mes donde la nómina
        # regular quede bajo el piso Y se paguen utilidades, se sobre-declara
        # rate × (piso − base_regular). Dirección conservadora; la agregación
        # mensual exacta llega con el reporte Forma 19 DPP (v3).
        self._ve_require_usd()
        rate = self._ve_param("l10n_ve_cepp_pat_rate")
        floor_usd = self._ve_param("l10n_ve_imi_cepp_floor_usd")
        # La inclusión de pagos no salariales (bonos, ayuda complementaria,
        # cesta) en la base es una lectura legal que cada empresa decide con
        # su asesor: ver res.company.l10n_ve_cepp_include_nonsalarial.
        kind = ("pension" if self.company_id.l10n_ve_cepp_include_nonsalarial
                else "cotizable")
        monthly = self._ve_monthly_base(kind, result_rules)
        base = max(monthly, floor_usd)
        return base * rate * self._ve_period_ratio()
