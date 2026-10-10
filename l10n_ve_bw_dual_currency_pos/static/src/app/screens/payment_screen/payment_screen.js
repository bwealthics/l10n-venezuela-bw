// Copyright 2026 BWEALTHICS LLC
// Part of l10n_ve_bw_dual_currency_pos. License LGPL-3.
import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    /** Al ENTRAR a la pantalla de pago se pide la tasa BCV de hoy si falta,
     *  antes de que el cajero elija métodos o capture Bs (l10n_ve_bw_pos_bs).
     *  Si cancela, el popup se vuelve a mostrar al intentar validar: la
     *  validación (patch de OrderPaymentValidation) no avanza sin tasa. */
    onMounted() {
        super.onMounted(...arguments);
        // Sin await: no se bloquea el montaje de la pantalla. La promesa de
        // l10nVeBsEnsureRate está deduplicada, no hay popups repetidos.
        this.pos.l10nVeBsEnsureRate();
    },
});
