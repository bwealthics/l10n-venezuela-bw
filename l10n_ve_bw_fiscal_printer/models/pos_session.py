# Part of l10n_ve_bw_fiscal_printer. License LGPL-3.
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class PosSession(models.Model):
    _inherit = "pos.session"

    l10n_ve_z_number = fields.Char(
        string="Nº Reporte Z", copy=False, tracking=True,
        help="Número del cierre Z impreso desde esta sesión (fila diaria del "
             "Libro de Ventas, art. 77).")
    # La autorización vive en la SESIÓN, no en la caja: así muere al cerrar el
    # turno y hay que volver a pedirla cada día. Cero código de expiración.
    l10n_ve_contingency_reason = fields.Char(
        string="Motivo de la contingencia", copy=False, readonly=True,
        tracking=True)
    l10n_ve_contingency_user_id = fields.Many2one(
        "res.users", string="Contingencia autorizada por", copy=False,
        readonly=True, tracking=True)
    l10n_ve_contingency_start = fields.Datetime(
        string="Contingencia activa desde", copy=False, readonly=True,
        tracking=True)

    @api.model
    def _load_pos_data_fields(self, config):
        # El m2o del autorizante NO viaja al POS: arrastraría res.users al
        # payload sin que el frontend lo necesite para nada.
        return super()._load_pos_data_fields(config) + [
            "l10n_ve_contingency_reason", "l10n_ve_contingency_start"]

    def l10n_ve_contingency_open(self, reason):
        """Autoriza el modo contingencia para esta sesión de caja.

        El control de grupo se hace AQUÍ, en el servidor: el botón del POS
        solo pinta, y un cajero puede llamar este método por RPC.
        """
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_manager"):
            raise AccessError(_(
                "Solo un gerente del punto de venta puede activar el modo "
                "contingencia."))
        if not self.config_id.l10n_ve_contingency_journal_id:
            raise UserError(_(
                "Esta caja no tiene diario de contingencia configurado: "
                "asígnelo en Punto de Venta › Ajustes antes de continuar."))
        reason = (reason or "").strip()
        if len(reason) < 5:
            raise UserError(_(
                "Indique el motivo de la falla (mínimo 5 caracteres): queda "
                "registrado como justificación de la contingencia."))
        if self.l10n_ve_contingency_start:
            # Ya autorizada: se devuelve el estado sin re-escribir, para no
            # perder quién y cuándo la abrió.
            return {
                "reason": self.l10n_ve_contingency_reason,
                "start": self.l10n_ve_contingency_start,
            }
        self.write({
            "l10n_ve_contingency_reason": reason,
            "l10n_ve_contingency_user_id": self.env.user.id,
            "l10n_ve_contingency_start": fields.Datetime.now(),
        })
        # Escalares serializables: el JS refresca su registro local sin
        # recargar la sesión del POS.
        return {
            "reason": self.l10n_ve_contingency_reason,
            "start": self.l10n_ve_contingency_start,
        }
