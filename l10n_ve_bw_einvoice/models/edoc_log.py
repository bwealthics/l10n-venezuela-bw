# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_einvoice. License LGPL-3.
from odoo import fields, models


class L10nVeEdocLog(models.Model):
    """Bitácora de lo que se le mandó a la imprenta y lo que contestó.

    Es la evidencia que pediría un fiscalizador y la que exige la PA
    SNAT/2024/000121 al sistema de facturación. Se escribe siempre, también
    —y sobre todo— cuando la llamada falla.
    """

    _name = "l10n.ve.edoc.log"
    _description = "Bitácora de la imprenta digital"
    _order = "id desc"

    move_id = fields.Many2one(
        "account.move", string="Documento", required=True,
        ondelete="cascade", index=True)
    endpoint = fields.Char(string="Operación", required=True)
    request = fields.Text(string="Enviado")
    response = fields.Text(string="Respuesta")
    ok = fields.Boolean(string="Correcta")
    company_id = fields.Many2one(
        related="move_id.company_id", store=True, index=True)
