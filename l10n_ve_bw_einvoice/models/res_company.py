# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_einvoice. License LGPL-3.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Selection extensible: un adaptador externo puede añadir su clave con
    # selection_add. Los dos de este módulo van directo en la lista.
    l10n_ve_edoc_provider = fields.Selection(
        [("l10n.ve.edoc.provider.hka", "The Factory HKA"),
         ("l10n.ve.edoc.provider.dummy", "Simulado (solo pruebas)")],
        string="Proveedor de imprenta digital")
    l10n_ve_edoc_url = fields.Char(
        string="URL del proveedor (producción)",
        help="URL base del ambiente de PRODUCCIÓN, sin ruta (la entrega el "
             "proveedor con el contrato). Mientras «Ambiente de pruebas» esté "
             "marcado se ignora: el adaptador usa la URL demo documentada del "
             "proveedor, así no puede haber pruebas contra producción.")
    l10n_ve_edoc_user = fields.Char(string="Usuario del proveedor")
    l10n_ve_edoc_password = fields.Char(string="Clave del proveedor")
    # Serie y sucursal por separado: la imprenta los trata como dos campos
    # distintos del documento (una empresa puede tener varias sucursales y
    # varias series por sucursal).
    l10n_ve_edoc_serie = fields.Char(string="Serie")
    l10n_ve_edoc_sucursal = fields.Char(string="Sucursal")
    l10n_ve_edoc_test = fields.Boolean(
        string="Ambiente de pruebas", default=True,
        help="Mientras esté marcado se usa el ambiente demo del proveedor "
             "(con The Factory HKA, demoemisionv2.thefactoryhka.com.ve). "
             "Desmarcarlo solo cuando el SENIAT haya autorizado al emisor.")
