# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_einvoice. License LGPL-3.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Selection extensible: cada adaptador añade su clave con selection_add.
    # Hoy solo está el simulado; el de The Factory HKA se incorpora cuando
    # lleguen las credenciales y la URL de producción.
    l10n_ve_edoc_provider = fields.Selection(
        [("l10n.ve.edoc.provider.dummy", "Simulado (solo pruebas)")],
        string="Proveedor de imprenta digital")
    l10n_ve_edoc_url = fields.Char(string="URL del proveedor")
    l10n_ve_edoc_user = fields.Char(string="Usuario del proveedor")
    l10n_ve_edoc_password = fields.Char(string="Clave del proveedor")
    l10n_ve_edoc_serie = fields.Char(string="Serie / sucursal")
    l10n_ve_edoc_test = fields.Boolean(
        string="Ambiente de pruebas", default=True,
        help="Mientras esté marcado se usa el ambiente de QA del proveedor. "
             "Desmarcarlo solo cuando el SENIAT haya autorizado al emisor.")
