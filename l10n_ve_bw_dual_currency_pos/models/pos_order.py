# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency_pos. License LGPL-3.
from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    # Campo almacenado PLANO y sin required: el POS 19 carga y serializa todos
    # los campos de pos.order (no define _load_pos_data_fields), así que viaja
    # en el sync de la orden; un required rompería órdenes antiguas o creadas
    # desde el backend (ver memoria "campos custom en pos.order").
    l10n_ve_bs_rate = fields.Float(
        string="Tasa Bs del ticket", digits=(16, 6), copy=False,
        help="Bs por 1 unidad de la moneda de la compañía con la que el POS "
             "mostró el total en Bs en el recibo. La fija la caja al validar; "
             "si la orden llega sin ella (sync sin conexión, flujos por "
             "código) se rellena con la última tasa ≤ fecha de la orden.")

    l10n_ve_bs_rate_date = fields.Date(
        string="Fecha de la tasa Bs", copy=False,
        help="Fecha de la tasa BCV con la que se fijó l10n_ve_bs_rate. El "
             "recibo imprime esta fecha (y no la de la orden): la tasa puede "
             "repetirse varios días (fin de semana) o venir de un día previo "
             "cuando la orden se sincroniza sin conexión.")

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            # Un borrador (p. ej. la orden de mesa que pos_restaurant sincroniza
            # al enviar a cocina) NO recibe tasa por defecto: la de la fecha de
            # creación puede ser la de ayer si el n8n aún no cargó la de hoy, y
            # luego el cobro no la pisaría. La tasa se fija al validar (caja) o,
            # si llega sin ella, en write() al pasar a pagada.
            if vals.get("state", "draft") == "draft":
                continue
            if not vals.get("l10n_ve_bs_rate"):
                rate, rate_date = self._l10n_ve_bs_default_rate(vals)
                if rate:
                    vals["l10n_ve_bs_rate"] = rate
                    vals["l10n_ve_bs_rate_date"] = rate_date
        return super().create(vals_list)

    def write(self, vals):
        # Flujo automático (sync sin tasa, código): al pasar a pagada/hecha/
        # facturada una orden que sigue sin tasa se rellena con la última ≤ su
        # fecha, y se registra la fecha de esa tasa.
        if vals.get("state") in ("paid", "done", "invoiced") \
                and not vals.get("l10n_ve_bs_rate"):
            for order in self.filtered(lambda o: not o.l10n_ve_bs_rate):
                rate, rate_date = self._l10n_ve_bs_default_rate({
                    "session_id": order.session_id.id,
                    "company_id": order.company_id.id,
                    "date_order": order.date_order,
                })
                if rate:
                    order.l10n_ve_bs_rate = rate
                    order.l10n_ve_bs_rate_date = rate_date
        return super().write(vals)

    @api.model
    def _l10n_ve_bs_default_rate(self, vals):
        """``(tasa, fecha_de_la_tasa)`` Bs ≤ fecha de la orden, para órdenes que
        llegan sin tasa. Es un flujo automático: no se bloquea ni se pide
        nada, usa la última tasa disponible (regla 2 del contrato) y devuelve
        ``(0.0, False)`` si no hay ninguna (mejor sin dato que una tasa
        inventada)."""
        session = self.env["pos.session"].browse(vals.get("session_id"))
        company = (
            session.company_id if session.exists()
            else self.env["res.company"].browse(vals.get("company_id"))
        ) or self.env.company
        date_order = fields.Datetime.to_datetime(
            vals.get("date_order")) or fields.Datetime.now()
        # La fecha de la tasa es la del día local de la orden, no la UTC.
        local_date = fields.Datetime.context_timestamp(self, date_order).date()
        return company.sudo()._l10n_ve_bs_rate_at(local_date)
