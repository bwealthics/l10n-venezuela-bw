# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosOrder(models.Model):
    _inherit = "pos.order"

    # Viven en fiscal_books, con el Libro que los lee: si estuvieran en
    # fiscal_printer el wizard necesitaría guardas defensivas por si ese
    # módulo no está instalado. Campos PLANOS por la misma razón documentada
    # en l10n_ve_bw_fiscal_printer/models/pos_order.py: solo los almacenados
    # no compute viajan al servidor en el sync del POS.
    l10n_ve_contingency_control = fields.Char(
        string="Nº de control (contingencia)",
        copy=False,
        readonly=True,
        index="btree_not_null",
        help="Nº de control del formato preimpreso del talonario autorizado "
             "que se usó para facturar esta orden mientras la máquina fiscal "
             "estaba caída (PA 0071 art. 11).",
    )
    l10n_ve_contingency_invoice_number = fields.Char(
        string="Nº de factura (talonario)",
        copy=False,
        readonly=True,
        index="btree_not_null",
        help="Nº de factura preimpreso del formato del talonario autorizado. "
             "El Libro de Ventas lo usa como Nº de documento de esta venta.",
    )

    @api.constrains("l10n_ve_contingency_control",
                    "l10n_ve_contingency_invoice_number")
    def _check_l10n_ve_contingency_unique(self):
        """Un formato del talonario = un solo documento.

        El POS ya valida contra las órdenes en memoria de la sesión; este es
        el cierre en servidor (multi-caja, multi-sesión). Char no requerido:
        no interfiere con el sync de órdenes sin contingencia.
        """
        for order in self:
            for field, label in (
                    ("l10n_ve_contingency_control", _("Nº de control")),
                    ("l10n_ve_contingency_invoice_number", _("Nº de factura"))):
                value = order[field]
                if not value:
                    continue
                dup = self.search([
                    ("id", "!=", order.id),
                    ("company_id", "=", order.company_id.id),
                    (field, "=", value),
                ], limit=1)
                if dup:
                    raise ValidationError(_(
                        "El %(label)s del talonario '%(value)s' ya está "
                        "registrado en la orden %(order)s.",
                        label=label, value=value, order=dup.display_name))
