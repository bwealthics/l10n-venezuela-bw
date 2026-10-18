# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ve_ivss_employer_number = fields.Char(
        string="N° Patronal IVSS", help="Número patronal asignado por el IVSS (Forma 14-01).")
    # ponytail: los números FAOV/INCES se capturan desde v1 (dato de registro
    # patronal) pero solo los explotan los exports de v3.
    l10n_ve_faov_employer_number = fields.Char(
        string="N° Patronal FAOV/BANAVIH")
    l10n_ve_inces_employer_number = fields.Char(
        string="N° Aportante INCES")
    l10n_ve_inces_contributor = fields.Boolean(
        string="Aportante INCES (5+ trabajadores)", default=True,
        help="El aporte INCES (2% patronal y ½% sobre utilidades) aplica a "
             "entidades con 5 o más trabajadores (art. 49 Decreto-Ley INCES "
             "2014). Con menos, desmarcar: se declara en cero en SIGAT.")
    l10n_ve_ivss_risk = fields.Selection(
        [("min", "Mínimo (9%)"), ("med", "Medio (10%)"), ("max", "Máximo (11%)")],
        string="Clase de riesgo IVSS", default="min",
        help="Clase de riesgo asignada por el IVSS al inscribir la entidad de "
             "trabajo; determina la tasa del aporte patronal.")
    l10n_ve_prestaciones_mode = fields.Selection(
        [("interna", "Contabilidad del patrono (intereses tasa BCV)"),
         ("fideicomiso", "Fideicomiso bancario (rendimiento del fondo)")],
        string="Depósito de la garantía", default="interna",
        help="Dónde se deposita la garantía de prestaciones (elección escrita "
             "del trabajador, art. 143 LOTTT). En fideicomiso los intereses "
             "los genera el fondo: la corrida de provisiones no los acumula.")
    l10n_ve_cepp_include_nonsalarial = fields.Boolean(
        string="CEPP sobre pagos no salariales", default=True,
        help="Si está marcado, la base de la Contribución Especial de "
             "Pensiones (9%) incluye los pagos NO salariales (bonos, ayuda "
             "complementaria, cesta ticket): lectura conservadora de la Ley de "
             "Protección de las Pensiones (2024). Al desmarcarlo el CEPP se "
             "calcula solo sobre conceptos salariales (art. 104 LOTTT), igual "
             "base que IVSS/RPE/FAOV. Es una interpretación legal: confírmela "
             "con su asesor laboral.")
    l10n_ve_utilidades_days = fields.Integer(
        string="Días de utilidades", default=30,
        help="Días de utilidades por convención o política de la compañía "
             "(mínimo legal 30, máximo 120 — art. 131-132 LOTTT). Alimenta la "
             "alícuota del salario integral (FAOV, prestaciones).")

    l10n_ve_benefits_base = fields.Selection(
        [("wage", "Sueldo del contrato"),
         ("minimum_wage", "Sueldo base en Bs (salario mínimo)")],
        string="Base de prestaciones y liquidación", default="wage",
        required=True,
        help="Salario sobre el que se calculan las prestaciones sociales, "
             "vacaciones, bono vacacional y utilidades (provisiones y "
             "finiquito). «Sueldo base en Bs» usa el salario mínimo vigente "
             "(parámetro de nómina) a la tasa BCV de la fecha: aplica cuando "
             "el salario pactado es el sueldo base y los pagos en divisas son "
             "bonos no salariales (SCS/TSJ N° 523 del 13-11-2025). Es una "
             "decisión legal de la empresa: confírmela con su asesor.")
    l10n_ve_cesta_in_net = fields.Boolean(
        string="Cesta ticket pagada con el sueldo",
        help="Marcar si la cesta ticket se transfiere junto con el sueldo. El "
             "Neto a Pagar del recibo incluye la cesta (lo que se transfiere) "
             "y su pasivo va a Sueldos por Pagar (210501) en vez de Cesta "
             "Ticket por Pagar (210502). La cesta sigue fuera del salario "
             "bruto: no es salario (art. 105 LOTTT, Ley del Cestaticket).")

    def write(self, vals):
        res = super().write(vals)
        if "l10n_ve_cesta_in_net" in vals:
            # El pasivo de la cesta cambia de cuenta: re-mapear las reglas.
            from ..hooks import map_rule_accounts
            basic = self.env.ref("l10n_ve_bw_payroll.rule_ve_reg_basic",
                                 raise_if_not_found=False)
            for company in self:
                if company.chart_template == "ve_bw" or (
                        basic and basic.with_company(company).account_debit):
                    map_rule_accounts(self.env, company)
        return res

    @api.constrains("l10n_ve_utilidades_days")
    def _check_l10n_ve_utilidades_days(self):
        for company in self:
            if company.chart_template == "ve_bw" and not 30 <= company.l10n_ve_utilidades_days <= 120:
                raise ValidationError(_(
                    "Los días de utilidades deben estar entre 30 y 120 (art. 131-132 LOTTT)."))
