// Copyright 2026 BWEALTHICS LLC
// Part of l10n_ve_bw_dual_currency_pos. License LGPL-3.
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    /** Se parchea validateOrder (y no askBeforeValidation) a propósito:
     *  l10n_ve_bw_pos_bs y l10n_ve_bw_fiscal_printer ya encadenan
     *  askBeforeValidation para capturar los Bs recibidos, y el orden entre
     *  parches de módulos distintos no está garantizado. validateOrder corre
     *  ANTES de toda esa captura, así la tasa del día queda cargada primero.
     *
     *  Sin la tasa de hoy (y con conexión) la orden no se valida: la regla
     *  de negocio es pedirla, no cobrar con la de otro día en silencio. */
    async validateOrder() {
        if (!(await this.pos.l10nVeBsEnsureRate())) {
            return false;
        }
        const order = this.order;
        const info = this.pos.l10nVeBsRate;
        const rate = info?.rate;
        if (order && rate > 0) {
            // Con la tasa de HOY confirmada se sobrescribe siempre: en
            // restaurante la orden ya se sincronizó como borrador y puede traer
            // la tasa de otro día; sin esto el recibo y el backend la
            // conservarían en silencio. Es idempotente en los reintentos del
            // mismo día. Sin conexión (no confirmada) solo se rellena si falta.
            if (info.is_today || !order.l10n_ve_bs_rate) {
                order.l10n_ve_bs_rate = rate;
                order.l10n_ve_bs_rate_date = info.date || false;
            }
        }
        return await super.validateOrder(...arguments);
    },
});
