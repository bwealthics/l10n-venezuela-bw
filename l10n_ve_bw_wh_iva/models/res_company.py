# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw. License LGPL-3.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ve_iva_wh_agent_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta Retenciones de IVA por Enterar (Agente)",
        help="Cuenta pasiva donde se acredita el IVA retenido a proveedores "
             "cuando la compañía actúa como agente de retención (ej. 210303).",
    )
    l10n_ve_iva_wh_received_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta Retenciones de IVA Recibidas de Clientes",
        help="Cuenta activa donde se registran los comprobantes de retención "
             "recibidos de clientes SPE (ej. 110302, Forma 30 casilla 66).",
    )
