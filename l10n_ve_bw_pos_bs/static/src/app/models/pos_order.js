// Copyright 2026 BWEALTHICS LLC
// Part of l10n_ve_bw_pos_bs. License LGPL-3.
import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

// Pagos split (Identify Customer) cuyo método trae "Cliente por defecto
// (split)": no exigen cliente en la orden; el servidor los contabiliza a ese
// contacto al cerrar la sesión (pos.session._l10n_ve_split_ctx).
export const splitNeedsCustomer = (payments) =>
    payments.some(
        (p) => p.payment_method_id?.split_transactions && !p.payment_method_id?.l10n_ve_split_no_customer
    );

patch(PosOrder.prototype, {
    get isCustomerRequired() {
        const hasSplit = this.payment_ids.some((p) => p.payment_method_id?.split_transactions);
        if (this.partner_id || !hasSplit || splitNeedsCustomer(this.payment_ids)) {
            return super.isCustomerRequired;
        }
        // Mismo cálculo del core sin la condición de split.
        const invalidPartnerPreset =
            (this.preset_id?.needsName && !this.floating_order_name) ||
            this.preset_id?.needsPartner;
        return Boolean(invalidPartnerPreset || this.isToInvoice());
    },
});
