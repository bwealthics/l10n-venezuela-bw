# Part of l10n_ve_bw_igtf. License LGPL-3.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ve_igtf_pct = fields.Float(
        string="Alícuota IGTF (%)",
        default=3.0,
        help="Alícuota del Impuesto a las Grandes Transacciones Financieras "
        "aplicada a pagos y cobros por diarios en divisas.",
    )
    l10n_ve_igtf_expense_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de Gasto IGTF",
        check_company=True,
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost'))]",
        help="Cuenta de gasto donde se registra el IGTF causado por los pagos "
        "propios en divisas (ej. 660101 Gasto por IGTF).",
    )
    l10n_ve_igtf_perception_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de Percepción IGTF",
        check_company=True,
        domain="[('account_type', 'in', ('liability_current', 'liability_non_current'))]",
        help="Cuenta de pasivo donde se acumula el IGTF percibido a clientes "
        "como Sujeto Pasivo Especial (ej. 210304 IGTF Percibido por Enterar).",
    )
