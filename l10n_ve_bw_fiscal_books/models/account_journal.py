# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
from odoo import fields, models

# El canal de emisión vive en el DIARIO y no en el asiento: la norma ya obliga
# a separar las series por medio de emisión (PA SNAT/2024/000102 art. 6), así
# que el diario ya es el eje natural y el Libro de Ventas puede segregar sin
# campos nuevos en account.move.
EMISSION_CHANNELS = [
    ("mf", "Máquina fiscal (PA 0071)"),
    ("digital", "Imprenta digital (PA SNAT/2024/000102)"),
    ("libre", "Forma libre — imprenta autorizada"),
    ("contingencia", "Contingencia — talonario de imprenta autorizada"),
]


class AccountJournal(models.Model):
    _inherit = "account.journal"

    l10n_ve_emission_channel = fields.Selection(
        selection=EMISSION_CHANNELS,
        string="Canal de emisión (VE)",
        help="Medio de emisión de los documentos de este diario. Determina "
             "quién asigna el Nº de control y si puede escribirse a mano:\n"
             "• Máquina fiscal / Imprenta digital: lo asigna el equipo o el "
             "proveedor autorizado; el campo queda bloqueado.\n"
             "• Forma libre: se transcribe del talonario UNA sola vez.\n"
             "• Contingencia: editable, porque replica un documento emitido a "
             "mano durante una falla.\n"
             "Vacío (compras y misceláneos): sin restricción.",
    )
