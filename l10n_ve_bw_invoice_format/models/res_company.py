# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_invoice_format. License LGPL-3.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Texto libre a propósito: son los datos que el contador copia del contrato
    # con la imprenta, y son los MISMOS bajo imprenta física (PA 0071 arts.
    # 30-31) y bajo imprenta digital (PA 000102 art. 7.14). Por eso este módulo
    # no depende del conector: sirve a los dos regímenes.
    l10n_ve_printer_name = fields.Char(
        string="Imprenta autorizada — Razón social")
    l10n_ve_printer_vat = fields.Char(
        string="Imprenta autorizada — RIF")
    l10n_ve_printer_auth_number = fields.Char(
        string="Imprenta autorizada — Nº de Providencia",
        help="Número de la Providencia Administrativa del SENIAT que autoriza "
             "a la imprenta. Es obligatorio imprimirlo en cada comprobante.")
    l10n_ve_printer_auth_date = fields.Date(
        string="Imprenta autorizada — Fecha de la Providencia")
    l10n_ve_control_range_from = fields.Char(
        string="Rango de Nº de control — Desde")
    l10n_ve_control_range_to = fields.Char(
        string="Rango de Nº de control — Hasta")

    # La moneda es un CAMPO y no la constante "VES" porque la base puede llevar
    # más de un bolívar (es habitual mantener VES a tasa BCV y otra moneda a
    # tasa de mercado) y cuál es el de referencia legal es decisión del
    # contribuyente, no del código. El valor por defecto es VES: es la tasa del
    # BCV la que exige el art. 25 de la Ley del IVA para expresar en bolívares
    # un comprobante emitido en moneda extranjera.
    l10n_ve_bs_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda de referencia en Bs",
        default=lambda self: self._l10n_ve_default_bs_currency(),
        help="Moneda en la que se expresa el equivalente en bolívares al pie "
             "del comprobante, con la tasa vigente a la fecha del documento. "
             "Vacío: no se imprime el bloque en Bs.",
    )
    l10n_ve_show_line_tax_detail = fields.Boolean(
        string="Detallar monto sin impuestos e impuesto por línea",
        default=True,
        help="Añade al cuerpo del comprobante dos columnas por ítem: el monto "
             "sin impuestos y el impuesto que le corresponde. Útil con precios "
             "IVA incluido, donde el importe de la línea ya trae el impuesto "
             "dentro.",
    )

    def _l10n_ve_default_bs_currency(self):
        """VES si existe en la base, aunque esté archivada.

        `active_test=False` a propósito: en una base recién creada el bolívar
        viene desactivado como todas las monedas distintas de la de la
        compañía, y el valor por defecto debe quedar puesto igual —activarlo es
        parte de la configuración de la localización, no de este campo.
        """
        return self.env["res.currency"].with_context(
            active_test=False).search([("name", "=", "VES")], limit=1)
