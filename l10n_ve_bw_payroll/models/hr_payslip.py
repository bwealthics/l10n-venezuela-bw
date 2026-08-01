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
        # no 24 — soportarlo requiere ratio 12/26 y prorrateos documentados).
        sched = self._ve_version().schedule_pay or "monthly"
        ratios = {"monthly": 1.0, "semi-monthly": 0.5}
        if sched not in ratios:
            raise UserError(_(
                "Frecuencia de pago '%s' no soportada por la nómina VE: use "
                "mensual o quincenal (semi-monthly).", sched))
        return ratios[sched]

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

    def _ve_basic_wage(self):
        self.ensure_one()
        # Con worked days delega en el motor (prorratea ausencias); sin worked
        # days (cálculo manual, tests) paga el wage del período completo.
        if self.worked_days_line_ids:
            return self._get_paid_amount()
        return self._ve_version().wage or 0.0

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
        return self._ve_param("l10n_ve_cesta_ticket_usd") * self._ve_period_ratio()

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
        monthly = self._ve_monthly_base("pension", result_rules)
        base = max(monthly, floor_usd)
        return base * rate * self._ve_period_ratio()
