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
