# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_einvoice. License LGPL-3.
from odoo import _, models
from odoo.exceptions import UserError


class L10nVeEdocProvider(models.AbstractModel):
    """Contrato con la imprenta digital. CUATRO métodos, ni uno más.

    Toda la lógica fiscal vive fuera de aquí, en
    `account.move._l10n_ve_edoc_document_vals()`, que produce un dict neutro.
    El adaptador solo traduce ese dict al dialecto del proveedor y devuelve el
    resultado en el formato de abajo. Así el proveedor se cambia escribiendo
    un archivo, sin tocar nada fiscal.

    Los dos candidatos investigados difieren justo en lo que este contrato
    abstrae: The Factory HKA devuelve el Nº de control SÍNCRONO en la
    respuesta de emisión, mientras que Unidigital lo asigna de forma asíncrona
    y hay que consultarlo después. Por eso `_edoc_send` puede devolver
    control_number vacío y existe `_edoc_fetch`.
    """

    _name = "l10n.ve.edoc.provider"
    _description = "Contrato de la imprenta digital (Venezuela)"

    def _edoc_send(self, move, vals):
        """Emite el documento. Devuelve:

        {'external_id': str,            # identificador del proveedor
         'control_number': str | None,  # None si el proveedor es asíncrono
         'control_date': date | None}
        """
        raise UserError(_("El proveedor de imprenta digital no implementa el envío."))

    def _edoc_fetch(self, move):
        """Consulta el Nº de control de un documento ya enviado.

        Solo lo llaman los proveedores asíncronos. Mismo formato de retorno
        que `_edoc_send`; control_number None significa "aún no asignado".
        """
        raise UserError(_("El proveedor de imprenta digital no implementa la consulta."))

    def _edoc_cancel(self, move, reason):
        """Anula el documento ante el proveedor. Devuelve True si se anuló."""
        raise UserError(_("El proveedor de imprenta digital no implementa la anulación."))

    def _edoc_test_connection(self):
        """Autentica contra el proveedor sin emitir nada. Devuelve un mensaje
        legible para el usuario."""
        raise UserError(_("El proveedor de imprenta digital no implementa la prueba."))
