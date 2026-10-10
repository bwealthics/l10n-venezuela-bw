// Copyright 2026 BWEALTHICS LLC
// Part of l10n_ve_bw_dual_currency_pos. License LGPL-3.
import { patch } from "@web/core/utils/patch";
/* global luxon */
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { l10nVeBsDmy } from "@l10n_ve_bw_dual_currency_pos/app/utils/bs_rate";

patch(OrderReceipt.prototype, {
    /** Datos del bloque "Total Bs / Tasa BCV" del recibo, o null si no hay
     *  tasa que mostrar (entonces el recibo queda idéntico al del core).
     *
     *  La tasa es la fijada en la orden al validar (l10n_ve_bs_rate); si la
     *  orden aún no la tiene (pre-cuenta, recibo previo a validar) se usa la
     *  precargada por el store. El total es el total CON impuestos × tasa,
     *  redondeado a 2 decimales (el mismo criterio de la máquina fiscal). */
    get l10nVeBsReceipt() {
        const order = this.order;
        const pos = this.env.services.pos;
        const info = pos?.l10nVeBsRate;
        const orderRate = order.l10n_ve_bs_rate || 0;
        if (!orderRate) {
            // Sin tasa propia (pre-cuenta de una mesa abierta) solo se usa la
            // precargada si es la tasa de HOY confirmada por el servidor y su
            // fecha es la de hoy (una caja abierta desde ayer no imprime Bs a
            // la tasa de ayer). Una orden ya cerrada sin tasa (anterior a este
            // módulo) no muestra el bloque: reimprimirla a la tasa de hoy
            // falsearía lo que se cobró.
            // "is_today" ya incluye la regla de la hora de corte (antes de las
            // 9:15 vale la tasa de ayer); valid_until (UTC) evita usarla
            // después de vencer si la caja quedó abierta.
            const validUntil = info?.valid_until
                ? luxon.DateTime.fromSQL(info.valid_until, { zone: "utc" })
                : null;
            if (order.finalized || !info?.currency || !info.is_today
                || (validUntil && validUntil.isValid && luxon.DateTime.utc() >= validUntil)) {
                return null;
            }
        }
        const rate = orderRate || info.rate;
        if (!(rate > 0)) {
            return null;
        }
        // Fecha de la tasa: la guardada en la orden junto con su tasa. Solo
        // si la orden no tiene tasa propia se usa la precargada (y su fecha).
        let date = "";
        if (orderRate) {
            const rd = order.l10n_ve_bs_rate_date;
            date = rd?.toFormat ? rd.toFormat("yyyy-MM-dd") : rd || "";
        } else {
            date = info?.date || "";
        }
        const total = Math.round(order.priceIncl * rate * 100) / 100;
        return {
            total: pos.l10nVeBsFormat(total),
            rate: pos.l10nVeBsFormatRate(rate),
            date: l10nVeBsDmy(date),
        };
    },
});
