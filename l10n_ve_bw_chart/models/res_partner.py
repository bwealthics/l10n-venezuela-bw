# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    l10n_ve_taxpayer_type = fields.Selection(
        selection=[
            ("ordinario", "Contribuyente Ordinario"),
            ("especial", "Sujeto Pasivo Especial (SPE)"),
            ("formal", "Contribuyente Formal"),
            ("no_sujeto", "No Sujeto"),
        ],
        string="Tipo de Contribuyente",
        default="ordinario",
        help="Calificación del contribuyente ante el SENIAT. Los Sujetos Pasivos "
             "Especiales retienen IVA en sus pagos.",
    )
