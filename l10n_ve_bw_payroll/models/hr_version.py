# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    l10n_ve_cesta_complement_usd = fields.Float(
        string="Complemento de cestaticket (USD/mes)", digits=(16, 2),
        tracking=True, groups="hr_payroll.group_hr_payroll_user",
        help="Complemento MENSUAL del beneficio de alimentación pactado por "
             "la empresa, adicional a la cesta ticket legal. Carácter social "
             "NO remunerativo (art. 105.2 LOTTT, SCS/TSJ N° 523 del "
             "13-11-2025): no cotiza IVSS/RPE/FAOV, no integra el salario "
             "normal ni las prestaciones, no grava ISLR; sí integra la base "
             "de la Contribución Especial de Pensiones. Se prorratea por "
             "período de pago.")

    @api.constrains("l10n_ve_cesta_complement_usd")
    def _check_l10n_ve_cesta_complement_usd(self):
        # Un signo equivocado pasaría inadvertido: la categoría CESTA no toca
        # el NET y reduciría 610201/210502 y la base CEPP en silencio.
        for version in self:
            if version.l10n_ve_cesta_complement_usd < 0:
                raise ValidationError(_(
                    "El complemento de cestaticket no puede ser negativo."))
