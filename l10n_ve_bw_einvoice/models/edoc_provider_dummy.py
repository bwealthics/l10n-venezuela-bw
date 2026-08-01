# Part of l10n_ve_bw_einvoice. License LGPL-3.
from odoo import _, fields, models


class L10nVeEdocProviderDummy(models.AbstractModel):
    """Proveedor de pruebas: no habla con nadie.

    Existe para poder escribir y probar TODO el conector —estados, reintentos,
    log, flujo síncrono y asíncrono— antes de tener contrato con una imprenta.
    Nunca debe seleccionarse en producción; el asistente de configuración lo
    marca como "solo pruebas".
    """

    _name = "l10n.ve.edoc.provider.dummy"
    _inherit = "l10n.ve.edoc.provider"
    _description = "Imprenta digital simulada (solo pruebas)"

    # Nº de llamadas a _edoc_fetch antes de "asignar" el número, para simular
    # la asincronía de proveedores como Unidigital.
    _dummy_fetch_delay = 0

    def _edoc_send(self, move, vals):
        external_id = "DUMMY-%s" % move.id
        if self._dummy_fetch_delay:
            return {"external_id": external_id,
                    "control_number": None,
                    "control_date": None}
        return {
            "external_id": external_id,
            "control_number": "00-%08d" % move.id,
            "control_date": fields.Date.context_today(self),
        }

    def _edoc_fetch(self, move):
        return {
            "external_id": move.l10n_ve_edoc_external_id,
            "control_number": "00-%08d" % move.id,
            "control_date": fields.Date.context_today(self),
        }

    def _edoc_cancel(self, move, reason):
        return True

    def _edoc_test_connection(self):
        return _("Proveedor simulado: no se contactó ninguna imprenta real.")
