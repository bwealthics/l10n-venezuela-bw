# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    l10n_ve_wh_iva_rate = fields.Selection(
        selection=[
            ("0", "0% (no retener)"),
            ("75", "75% (regla general)"),
            ("100", "100% (IVA no discriminado / factura defectuosa)"),
        ],
        string="Porcentaje Retención de IVA",
        default="75",
        help="Porcentaje del IVA causado a retener a este proveedor cuando la "
             "compañía actúa como agente de retención (arts. 4 y 5, "
             "PA SNAT/2025/000054). Para clientes SPE indica que ellos nos retienen.",
    )
