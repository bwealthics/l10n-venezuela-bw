# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo import fields, models


class HrSalaryRule(models.Model):
    _inherit = "hr.salary.rule"

    # Cada flag define la pertenencia del concepto a una base legal
    # venezolana. Agregar un concepto nuevo = marcar sus flags; ninguna
    # regla de deducción se toca (ver hr_payslip._ve_base).
    l10n_ve_salarial = fields.Boolean(
        string="Salarial (cotiza IVSS/RPE/FAOV)",
        help="Percepción de carácter salarial (art. 104 LOTTT): integra la "
             "base de cotización de IVSS, RPE y FAOV.")
    # ponytail: sin consumidor en v1 — semilla para vacaciones/bono
    # vacacional (v2); _ve_base('normal') aún no se llama.
    l10n_ve_in_salario_normal = fields.Boolean(
        string="Salario normal",
        help="Integra el salario normal (base de vacaciones, bono vacacional "
             "y referencia del art. 104 LOTTT).")
    l10n_ve_in_inces_base = fields.Boolean(
        string="Base INCES 2%",
        help="Integra la base del aporte patronal INCES (salario normal sin "
             "horas extras ni remuneraciones accidentales).")
    l10n_ve_in_islr_base = fields.Boolean(
        string="Gravable ISLR",
        help="Integra la base de la retención de ISLR según el % del AR-I.")
    l10n_ve_in_pension_base = fields.Boolean(
        string="Base CEPP 9%",
        help="Integra la base de la Contribución Especial de Protección de "
             "las Pensiones (todo pago, salarial o no, incluida la cesta ticket).")
