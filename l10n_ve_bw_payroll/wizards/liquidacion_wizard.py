# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from datetime import date as dt_date

from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class L10nVeLiquidacionWizard(models.TransientModel):
    _name = "l10n.ve.liquidacion.wizard"
    _description = "Finiquito / liquidación de prestaciones (art. 142 LOTTT)"

    employee_id = fields.Many2one("hr.employee", required=True)
    company_id = fields.Many2one(related="employee_id.company_id")
    currency_id = fields.Many2one(related="company_id.currency_id")
    end_date = fields.Date(
        string="Fecha de egreso", required=True,
        default=fields.Date.context_today)
    # Vista previa (el pago debe hacerse dentro de los 5 días del término)
    garantia = fields.Monetary(compute="_compute_amounts")
    intereses = fields.Monetary(
        compute="_compute_amounts",
        help="Intereses acumulados (art. 143): se pagan ADEMÁS del monto "
             "mayor del art. 142.d.")
    prest_trim = fields.Monetary(
        compute="_compute_amounts", string="Garantía no depositada",
        help="15 días del trimestre iniciado y no completado al egreso (el "
             "derecho al depósito nace al iniciar el trimestre, art. 142.a) "
             "+ los abonos del MES DE EGRESO (trimestre y días adicionales) "
             "que aún no tengan línea en el libro: la corrida del mes suele "
             "postearse después del finiquito. No fue provisionado, va a "
             "gasto directo.")
    retroactivo = fields.Monetary(
        compute="_compute_amounts",
        help="30 días por año de servicio (fracción SUPERIOR a 6 meses = año "
             "completo) × último salario integral diario (art. 142.c).")
    prest_extra = fields.Monetary(
        compute="_compute_amounts",
        help="Exceso a pagar cuando el retroactivo supera la garantía "
             "depositada + trimestre en curso (art. 142.d: se paga el monto "
             "MAYOR; los intereses van aparte).")
    vac_frac = fields.Monetary(compute="_compute_amounts", string="Vacaciones fraccionadas")
    bvac_frac = fields.Monetary(compute="_compute_amounts", string="Bono vacacional fraccionado")
    util_frac = fields.Monetary(compute="_compute_amounts", string="Utilidades fraccionadas")
    total = fields.Monetary(compute="_compute_amounts")

    @api.depends("employee_id", "end_date")
    def _compute_amounts(self):
        Provision = self.env["l10n.ve.payroll.provision"]
        Ledger = self.env["l10n.ve.prestaciones.line"]
        for wiz in self:
            wiz.update({f: 0.0 for f in (
                "garantia", "intereses", "prest_trim", "retroactivo",
                "prest_extra", "vac_frac", "bvac_frac", "util_frac", "total")})
            if not wiz.employee_id or not wiz.end_date:
                continue
            start = Provision._employee_start_date(wiz.employee_id)
            if not start:
                continue
            delta = relativedelta(wiz.end_date, start)
            years, months, days = delta.years, delta.months, delta.days
            daily_int = Provision._employee_integral_daily(wiz.employee_id, wiz.end_date)
            daily_normal = Provision._employee_monthly_normal(
                wiz.employee_id, wiz.end_date) / 30.0

            # Corte a FIN del mes de egreso: las corridas históricas fechan
            # depósitos e intereses al último día del mes (después de un
            # egreso intra-mes); el cierre de action_create_payslip los
            # compensa igual. Las corridas nuevas fechan al aniversario.
            month_end = wiz.end_date + relativedelta(day=31)
            month_start = wiz.end_date.replace(day=1)
            wiz.garantia = Ledger._garantia_balance(wiz.employee_id, month_end)
            wiz.intereses = Ledger._intereses_balance(wiz.employee_id, month_end)
            # Abonos del MES DE EGRESO aún sin depositar (el finiquito se
            # paga dentro de los 5 días del egreso — art. 142.f — y la
            # corrida del mes suele postearse después): a gasto directo.
            # A PROPÓSITO se limita al mes de egreso: los saldos de apertura
            # (una línea manual por N trimestres históricos) y los meses sin
            # corrida son dominio del contador; contar trimestres de toda la
            # antigüedad contra líneas del libro pagaría doble.
            missing = 0.0
            if Provision._anniversaries_in_period(
                    start, month_start, wiz.end_date, 3) and not \
                    Ledger.search_count([
                        ("employee_id", "=", wiz.employee_id.id),
                        ("concept", "=", "garantia"),
                        ("date", ">=", month_start),
                        ("date", "<=", month_end)]):
                missing += 15 * daily_int
            # Mismo hueco para los días adicionales del aniversario ANUAL
            # (coincide siempre con uno trimestral) del mes de egreso.
            for n, _d in Provision._anniversaries_in_period(
                    start, month_start, wiz.end_date, 12):
                if n >= 2 and not Ledger.search_count([
                        ("employee_id", "=", wiz.employee_id.id),
                        ("concept", "=", "adicionales"),
                        ("date", ">=", month_start),
                        ("date", "<=", month_end)]):
                    missing += min(2 * (n - 1), 30) * daily_int
            wiz.prest_trim = missing
            # Trimestre iniciado y no completado (no cae en aniversario exacto)
            if months % 3 != 0 or days > 0:
                wiz.prest_trim += 15 * daily_int
            # Retroactivo: fracción SUPERIOR a 6 meses = año completo (142.c)
            retro_years = years + (1 if (months > 6 or (months == 6 and days > 0)) else 0)
            wiz.retroactivo = 30 * retro_years * daily_int
            # Art. 142.d literal: MAX contra la garantía depositada (+ el
            # trimestre en curso); los intereses se pagan aparte.
            wiz.prest_extra = max(
                0.0, wiz.retroactivo - wiz.garantia - wiz.prest_trim)

            # Fracciones del año de servicio en curso (arts. 190/192/196):
            # proporcionales a los meses COMPLETOS desde el aniversario
            vac_days_year = min(15 + years, 30)
            wiz.vac_frac = vac_days_year * months / 12.0 * daily_normal
            wiz.bvac_frac = vac_days_year * months / 12.0 * daily_normal
            # Utilidades fraccionadas: meses completos del ejercicio (año
            # calendario), conteo inclusivo del último día (art. 131)
            base = max(start, dt_date(wiz.end_date.year, 1, 1))
            d2 = relativedelta(wiz.end_date + relativedelta(days=1), base)
            months_worked = d2.years * 12 + d2.months
            util_days = wiz.employee_id.company_id.l10n_ve_utilidades_days or 30
            wiz.util_frac = util_days * months_worked / 12.0 * daily_normal
            wiz.total = (wiz.garantia + wiz.prest_trim + wiz.prest_extra
                         + wiz.intereses + wiz.vac_frac + wiz.bvac_frac
                         + wiz.util_frac)

    def action_create_payslip(self):
        self.ensure_one()
        if not self.total:
            raise UserError(_("No hay montos que liquidar (¿fecha de ingreso cargada?)."))
        # Guard de doble ejecución: un recibo VELIQ vigente o un cierre de
        # libro previo del período de empleo actual bloquean la re-corrida.
        start = self.env["l10n.ve.payroll.provision"]._employee_start_date(
            self.employee_id)
        struct_liq = self.env.ref("l10n_ve_bw_payroll.structure_ve_liquidacion")
        if self.env["hr.payslip"].search_count([
                ("employee_id", "=", self.employee_id.id),
                ("struct_id", "=", struct_liq.id),
                ("state", "!=", "cancel"),
                ("date_to", ">=", start)], limit=1):
            raise UserError(_(
                "Ya existe un recibo de liquidación vigente para %s: "
                "cancélelo antes de recalcular el finiquito.",
                self.employee_id.name))
        if self.env["l10n.ve.prestaciones.line"].search_count([
                ("employee_id", "=", self.employee_id.id),
                ("concept", "=", "liquidacion"),
                ("date", ">=", start)], limit=1):
            raise UserError(_(
                "El libro de garantía de %s ya tiene un cierre de liquidación "
                "en este período de empleo: si descartó el recibo anterior, "
                "elimine las líneas de cierre (liquidación e intereses "
                "negativos) antes de re-ejecutar.", self.employee_id.name))

        inputs = {
            "liq_prest_gar": self.garantia,
            "liq_prest_trim": self.prest_trim,
            "liq_prest_extra": self.prest_extra,
            "liq_int": self.intereses,
            "liq_vac": self.vac_frac,
            "liq_bvac": self.bvac_frac,
            "liq_util": self.util_frac,
        }
        slip = self.env["hr.payslip"].create({
            "name": _("Liquidación — %s", self.employee_id.name),
            "employee_id": self.employee_id.id,
            "company_id": self.employee_id.company_id.id,
            "struct_id": struct_liq.id,
            "date_from": self.end_date.replace(day=1),
            "date_to": self.end_date,
            "l10n_ve_payment_date": self.end_date,
            "input_line_ids": [
                Command.create({
                    "input_type_id": self.env.ref(
                        "l10n_ve_bw_payroll.input_type_%s" % xmlid).id,
                    "amount": amount,
                }) for xmlid, amount in inputs.items() if amount
            ],
        })
        slip.compute_sheet()
        # Cerrar contrato y libro. ponytail: el cierre ocurre al CREAR el
        # recibo; si el borrador se descarta, borrar a mano las líneas de
        # cierre (el guard de arriba lo recuerda).
        version = self.employee_id.version_id
        if not version.contract_date_end:
            version.contract_date_end = self.end_date
        Ledger = self.env["l10n.ve.prestaciones.line"]
        if self.garantia:
            Ledger.create({
                "employee_id": self.employee_id.id, "date": self.end_date,
                "concept": "liquidacion", "amount": -self.garantia,
                "note": slip.name,
            })
        if self.intereses:
            Ledger.create({
                "employee_id": self.employee_id.id, "date": self.end_date,
                "concept": "intereses", "amount": -self.intereses,
                "note": _("Pago en liquidación — %s", slip.name),
            })
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.payslip",
            "res_id": slip.id,
            "view_mode": "form",
        }
