# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ve_is_spe = fields.Boolean(
        string="Sujeto Pasivo Especial (SPE)",
        help="Marque si la compañía fue designada Sujeto Pasivo Especial por el "
             "SENIAT. Activa la retención de IVA como agente y la percepción de "
             "IGTF en los módulos de la localización.",
    )
    l10n_ve_spe_date = fields.Date(
        string="Fecha de Designación SPE",
        help="Fecha de inicio como Sujeto Pasivo Especial según la notificación "
             "del SENIAT.",
    )
