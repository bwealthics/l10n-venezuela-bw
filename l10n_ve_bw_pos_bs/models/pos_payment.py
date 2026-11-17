# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_bs. License LGPL-3.
import logging
import threading

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PosPayment(models.Model):
    _inherit = "pos.payment"

    # pos.payment no restringe _load_pos_data_fields (default del mixin = []):
    # estos campos viajan al POS y regresan por sync_from_ui sin más código.
    # No son required a propósito (el POS v19 serializa TODOS los campos del
    # modelo; un required rompería los flujos que crean pagos por código,
    # p.ej. pedidos por chat).
    l10n_ve_amount_bs = fields.Float(
        string="Monto Bs",
        digits=(16, 2),
        help="Bolívares EXACTOS recibidos del cliente (capturados en la caja). "
        "Con signo: negativo en reembolsos. Es el monto que debe aparecer en "
        "el extracto bancario.",
    )
    # Integer y no Many2one a propósito: pos.payment viaja entero al POS y
    # account.payment no es un modelo cargado en la caja.
    l10n_ve_split_ap_id = fields.Integer(
        string="Pago contable (split)",
        readonly=True,
        copy=False,
        index="btree_not_null",
        help="Id del account.payment propio de este pago cuando el método usa "
        "split_transactions. Lo escribe el cierre de sesión; el flujo n8n "
        "P2C lo usa para conciliar 1:1 contra la línea del banco.",
    )
    l10n_ve_rate = fields.Float(
        string="Tasa Bs/USD",
        digits=(16, 6),
        help="Tasa BCV usada como referencia al capturar el monto.",
    )
    l10n_ve_amount_usd = fields.Float(
        string="Importe al capturar",
        digits=(16, 2),
        help="Importe del pago (moneda del POS) en el momento de la captura. "
        "Si el cajero cambia luego el importe de la línea, el POS detecta el "
        "desfase y vuelve a pedir los Bs.",
    )
    l10n_ve_payer_phone = fields.Char(
        string="Teléfono del pagador",
        size=11,
        help="Celular desde el que el cliente envió el pago móvil "
        "(04XXXXXXXXX, según el comprobante). Obligatorio para verificar el "
        "pago contra el API Conciliación BDV (getMovement).",
    )
    l10n_ve_payer_bank = fields.Char(
        string="Banco origen",
        size=4,
        help="Código SUDEBAN del banco emisor del pago móvil (p.ej. 0102 "
        "Banco de Venezuela, 0134 Banesco). Obligatorio para verificar el "
        "pago contra el API Conciliación BDV.",
    )
    l10n_ve_dest_bank = fields.Char(
        string="Banco destino",
        size=4,
        help="Código SUDEBAN de la cuenta del comercio que recibió el pago "
        "móvil (según el comprobante), p.ej. 0172 Bancamiga o 0102 Banco de "
        "Venezuela. Vacío = Banco de Venezuela (pagos anteriores a 19.0.1.3.0 "
        "y prepagos del chatbot). El API Conciliación BDV solo ve los cobros "
        "con destino 0102.",
    )
    l10n_ve_bdv_state = fields.Selection(
        string="Verificación BDV",
        selection=[
            ("pendiente", "Pendiente de verificar"),
            ("verificado", "Verificado por BDV"),
            ("rechazado", "Rechazado por BDV"),
            ("no_verificable", "No verificable"),
            ("otro_banco", "Cobrado en otro banco"),
        ],
        default="pendiente",
        copy=False,
        index=True,
        help="Estado de la verificación contra el API Conciliación BDV "
        "(getMovement), escrito por el verificador externo (workflow n8n): "
        "verificado = el movimiento existe en BDV (o se concilió "
        "por extracto real); rechazado = BDV respondió que NO existe — "
        "posible comprobante falso, revisar con el cajero antes de dar por "
        "cobrada la orden; no_verificable = faltan datos del pagador o la "
        "respuesta fue dudosa (monto que no coincide, tupla duplicada); "
        "otro_banco = el pago llegó a una cuenta que no es BDV (p.ej. "
        "Bancamiga): el API no lo puede ver y se concilia contra el extracto "
        "de ese banco.",
    )
    l10n_ve_bdv_note = fields.Char(
        string="Nota verificación BDV",
        copy=False,
        help="Motivo del último resultado de la verificación BDV (p.ej. el "
        "mensaje de rechazo del API).",
    )

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        payments._l10n_ve_bs_notify_verifier()
        return payments

    def _l10n_ve_bs_notify_verifier(self):
        """Ping best-effort al verificador externo (workflow n8n) para
        conciliar el pago móvil contra el API BDV en tiempo real.

        Inerte sin el parámetro de sistema
        ``l10n_ve_bw_pos_bs.bdv_trigger_url``. El POST corre POST-COMMIT (el
        pago ya es visible para el verificador; un rollback de la orden nunca
        dispara) y cualquier fallo solo se loguea: el cron diario del
        workflow barre lo que se pierda aquí.
        """
        relevant = self.filtered(
            lambda p: p.payment_method_id.l10n_ve_bs_payer_data
            and p.amount > 0
            and (p.payment_ref_no or "").strip()
        )
        if not relevant:
            return
        url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("l10n_ve_bw_pos_bs.bdv_trigger_url")
        )
        if not url:
            return
        payment_ids = relevant.ids

        def _post():
            try:
                import requests

                requests.post(
                    url,
                    json={"_model": "pos.payment", "ids": payment_ids},
                    timeout=3,
                )
            except Exception:
                _logger.warning(
                    "l10n_ve_bw_pos_bs: fallo el ping al verificador BDV "
                    "(el cron de n8n lo recupera). ids=%s",
                    payment_ids,
                    exc_info=True,
                )

        def _ping():
            # hilo daemon: postcommit.run() corre DENTRO de commit(), antes de
            # responderle al POS — un n8n caido en blackhole bloquearia al
            # cajero hasta 6s por pago; el hilo desacopla esa latencia
            threading.Thread(target=_post, daemon=True).start()

        self.env.cr.postcommit.add(_ping)
