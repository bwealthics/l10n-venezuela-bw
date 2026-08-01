# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_igtf. License LGPL-3.
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    l10n_ve_igtf_applies = fields.Boolean(
        string="Sujeto a IGTF",
        help="Marque esta casilla en los diarios de banco o efectivo en divisas "
        "(ej. Zelle, efectivo USD, USDT): los pagos y cobros por estos diarios "
        "causan IGTF según la Ley IGTF. Los diarios en bolívares no se marcan.",
    )
