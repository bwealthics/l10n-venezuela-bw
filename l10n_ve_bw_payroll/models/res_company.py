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
    l10n_ve_utilidades_days = fields.Integer(
        string="Días de utilidades", default=30,
        help="Días de utilidades por convención o política de la compañía "
             "(mínimo legal 30, máximo 120 — art. 131-132 LOTTT). Alimenta la "
             "alícuota del salario integral (FAOV, prestaciones).")

    @api.constrains("l10n_ve_utilidades_days")
    def _check_l10n_ve_utilidades_days(self):
        for company in self:
            if company.chart_template == "ve_bw" and not 30 <= company.l10n_ve_utilidades_days <= 120:
                raise ValidationError(_(
                    "Los días de utilidades deben estar entre 30 y 120 (art. 131-132 LOTTT)."))
