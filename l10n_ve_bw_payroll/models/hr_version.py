# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo import fields, models


class HrVersion(models.Model):
    _inherit = "hr.version"

    # hr.version ya versiona por fecha en Odoo 19: cambiar el % del AR-I en
    # marzo/junio/septiembre/diciembre crea una versión nueva con su vigencia.
    l10n_ve_ari_percentage = fields.Float(
        string="% Retención ISLR (AR-I)", digits=(5, 2), tracking=True,
        groups="hr_payroll.group_hr_payroll_user",
        help="Porcentaje de retención autodeterminado por el trabajador en su "
             "AR-I vigente (Decreto 1.808). En 0, no se retiene ISLR.")
    l10n_ve_ivss_contributor = fields.Boolean(
        string="Cotiza IVSS/RPE", default=True, tracking=True,
        groups="hr_payroll.group_hr_payroll_user",
        help="Desmarcar solo para trabajadores no sujetos a cotización "
             "(p. ej. pensionados del IVSS reincorporados).")
    l10n_ve_cesta_ticket = fields.Boolean(
        string="Recibe cesta ticket", default=True, tracking=True,
        groups="hr_payroll.group_hr_payroll_user",
        help="Beneficio de alimentación (cesta ticket socialista) indexado "
             "en USD a la tasa BCV de la fecha de pago.")
