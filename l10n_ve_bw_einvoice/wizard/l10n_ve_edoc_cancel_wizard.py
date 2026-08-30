# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_einvoice. License LGPL-3.
from odoo import _, fields, models
from odoo.exceptions import UserError


class L10nVeEdocCancelWizard(models.TransientModel):
    """Anulación ante la imprenta digital.

    Existe porque la anulación exige un MOTIVO (The Factory HKA lo pide como
    motivoAnulacion) y porque anular ante la imprenta no anula el asiento:
    la nota de crédito o la cancelación contable siguen siendo decisión del
    contador, este wizard solo habla con el proveedor.
    """

    _name = "l10n.ve.edoc.cancel.wizard"
    _description = "Anular documento ante la imprenta digital"

    move_id = fields.Many2one(
        comodel_name="account.move", string="Documento",
        required=True, readonly=True)
    reason = fields.Text(string="Motivo de la anulación", required=True)

    def action_confirm(self):
        self.ensure_one()
        move = self.move_id
        if move.l10n_ve_edoc_state not in ("sent", "assigned"):
            raise UserError(_(
                "%s no está emitido ante la imprenta digital.",
                move.display_name))
        # _l10n_ve_edoc_do_cancel nunca lanza: si lanzara, el rollback se
        # llevaría la bitácora. El fallo se muestra como notificación y el
        # detalle queda en el documento y en el log.
        if move._l10n_ve_edoc_do_cancel(self.reason):
            return {"type": "ir.actions.act_window_close"}
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "danger",
                "title": _("La imprenta no aceptó la anulación"),
                "message": move.l10n_ve_edoc_error
                or _("Revisa la bitácora de la imprenta digital."),
                "sticky": True,
            },
        }
