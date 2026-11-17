# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_bs. License LGPL-3.
from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _find_accounting_partner(self, partner):
        # pos.session inyecta este contexto al contabilizar un pago split
        # de una orden sin cliente (ver pos.payment.method
        # l10n_ve_split_partner_id); el core lanza UserError sin partner.
        fallback_id = self.env.context.get("l10n_ve_split_fallback_partner_id")
        if not partner and fallback_id:
            partner = self.browse(fallback_id)
        return super()._find_accounting_partner(partner)
