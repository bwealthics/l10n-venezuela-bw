# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Canales cuyo Nº de control lo asigna un tercero (la máquina fiscal o la
# imprenta digital): el usuario no lo escribe nunca, ni por interfaz ni por RPC.
ASSIGNED_CHANNELS = ("mf", "digital")


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_ve_control_number = fields.Char(
        string="Nº de Control",
        copy=False,
        tracking=True,
        index="btree_not_null",
        help="Número de control fiscal del documento (PA SNAT/2011/00071). "
             "Se refleja en los Libros de Compras y Ventas.",
    )
    l10n_ve_emission_channel = fields.Selection(
        related="journal_id.l10n_ve_emission_channel",
        string="Canal de emisión (VE)",
    )

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        # Cierre de la vía create (RPC directo, import CSV/XLSX, duplicación
        # con vals): en canales mf/digital el número solo puede venir del
        # write-back con contexto. En "libre" la PRIMERA transcripción al
        # crear es legítima (el guard de write bloquea re-escrituras).
        if not self.env.context.get("l10n_ve_control_writeback"):
            for move in moves.filtered("l10n_ve_control_number"):
                if move.journal_id.l10n_ve_emission_channel in ASSIGNED_CHANNELS:
                    move._l10n_ve_check_control_editable()
        return moves

    def write(self, vals):
        # El `in vals` sobre el dict va ANTES de recorrer nada: coste cero en
        # la práctica totalidad de los writes. El write-back de la máquina
        # fiscal y el del conector de imprenta digital pasan con el contexto
        # l10n_ve_control_writeback: son el origen legítimo del número.
        if "l10n_ve_control_number" in vals and not self.env.context.get(
                "l10n_ve_control_writeback"):
            for move in self:
                move._l10n_ve_check_control_editable()
        return super().write(vals)

    def _l10n_ve_check_control_editable(self):
        """Política de edición del Nº de control, derivada del canal del diario.

        La vista espeja esta misma regla en su atributo `readonly`; aquí se
        cierra también la vía RPC. Los diarios sin canal (compras,
        misceláneos) quedan libres: en una factura de proveedor el Nº de
        control lo transcribe el contador y se corrige con frecuencia.
        """
        self.ensure_one()
        channel = self.journal_id.l10n_ve_emission_channel
        if channel in ASSIGNED_CHANNELS:
            origin = (_("la máquina fiscal") if channel == "mf"
                      else _("la imprenta digital autorizada"))
            raise UserError(_(
                "El Nº de control de %(doc)s lo asigna %(origin)s: no puede "
                "escribirse a mano. Si el documento está errado, corríjalo "
                "mediante Nota de Crédito o Débito.",
                doc=self.display_name, origin=origin,
            ))
        if channel == "libre" and self.l10n_ve_control_number:
            raise UserError(_(
                "El Nº de control de %(doc)s ya está asignado (%(num)s). En "
                "forma libre se transcribe una sola vez del talonario "
                "autorizado; corríjalo mediante Nota de Crédito o Débito.",
                doc=self.display_name, num=self.l10n_ve_control_number,
            ))
