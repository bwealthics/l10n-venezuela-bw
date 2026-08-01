# Part of l10n_ve_bw. License LGPL-3.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ve_municipal_name = fields.Char(
        string="Municipio",
        help="Municipio donde la compañía tributa la patente de industria y comercio.",
    )
    l10n_ve_municipal_rate = fields.Float(
        string="Alícuota municipal (%)",
        help="Porcentaje sobre los ingresos brutos según el Clasificador de "
             "Actividades Económicas de la ordenanza municipal. "
             "Tope legal: 3% general / hasta 6,5% en las excepciones previstas.",
    )
    l10n_ve_municipal_minimum = fields.Monetary(
        string="Mínimo tributable fijo mensual",
        currency_field="currency_id",
        help="Monto mínimo fijo mensual en la moneda de la compañía. Si también "
             "se configura el mínimo en veces MMV, aplica el MAYOR de los dos.",
    )
    l10n_ve_municipal_minimum_mmv = fields.Float(
        string="Mínimo tributable (veces MMV)",
        help="Múltiplo del TCMMV que la ordenanza fija como mínimo tributable "
             "mensual: mínimo (Bs) = veces × TCMMV. Sector alimentos/restaurantes: "
             "tope legal hasta 30 veces.",
    )
    l10n_ve_municipal_tcmmv = fields.Float(
        string="TCMMV (Bs)",
        help="Tipo de Cambio de la Moneda de Mayor Valor publicado por el BCV "
             "(normalmente el Euro), en bolívares. Se usa para calcular el mínimo "
             "tributable (veces MMV × TCMMV): actualizarlo antes de liquidar el mes, "
             "a mano o alimentado por integración (API).",
    )
    l10n_ve_municipal_expense_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de gasto por impuesto municipal",
        check_company=True,
        domain=[("internal_group", "=", "expense")],
        help="Cuenta de gasto del asiento mensual (catálogo VE: 660102).",
    )
    l10n_ve_municipal_payable_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de impuesto municipal por pagar",
        check_company=True,
        domain=[("internal_group", "=", "liability")],
        help="Cuenta de pasivo del asiento mensual (catálogo VE: 210403).",
    )
    l10n_ve_municipal_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario del impuesto municipal",
        check_company=True,
        domain=[("type", "=", "general")],
        help="Diario misceláneo donde se genera el asiento borrador mensual.",
    )
