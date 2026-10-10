/** Copyright 2026 BWEALTHICS LLC. Part of l10n_ve_bw_dual_currency. License LGPL-3.
 *
 * Parche del widget de totales de impuestos (account-tax-totals-field).
 * El servidor agrega `totals.l10n_ve_bs` (ver account.move._compute_tax_totals)
 * con los montos ya convertidos y congelados a la tasa del documento. Aquí NO se
 * recalcula nada: solo se leen y se formatean con la moneda Bs, de modo que la
 * pantalla, el PDF y los libros muestren exactamente las mismas cifras.
 * Si el documento no trae `l10n_ve_bs` (ventas, compras, moneda Bs == documento)
 * el widget se comporta igual que en el core.
 */
import { formatMonetary } from "@web/views/fields/formatters";
import { patch } from "@web/core/utils/patch";
import { TaxTotalsComponent } from "@account/components/tax_totals/tax_totals";

// TaxGroupComponent no se exporta en el core, pero queda registrado en
// TaxTotalsComponent.components: se parchea desde ahí.
const TaxGroupComponent = TaxTotalsComponent.components.TaxGroupComponent;

function formatBs(bs, value) {
    return formatMonetary(value || 0, { currencyId: bs.currency_id });
}

patch(TaxTotalsComponent.prototype, {
    /** Datos Bs del documento actual, o undefined si no aplica. */
    get l10nVeBs() {
        return this.totals && this.totals.l10n_ve_bs;
    },

    formatBs(value) {
        return formatBs(this.l10nVeBs, value);
    },

    /** Subtotal en Bs; la clave es el nombre del subtotal, igual que en el core. */
    bsSubtotal(subtotal) {
        return this.formatBs(this.l10nVeBs.subtotals[subtotal.name]);
    },

    bsTotal() {
        return this.formatBs(this.l10nVeBs.total_amount);
    },

    /**
     * Redondeo de efectivo en Bs (fila "Rounding" del core, solo con la
     * estrategia de línea de factura). El servidor no lo manda por separado:
     * es lo que falta para que la columna Bs sume: total - último subtotal -
     * impuestos de los grupos de ese último subtotal. Así la columna Bs
     * cuadra con el "Total Bs" aunque haya redondeo.
     */
    bsRounding() {
        const bs = this.l10nVeBs;
        // El servidor manda el redondeo de caja ya en Bs (borrador: delta del
        // core × tasa; posteado: Bs de las líneas de redondeo). El cálculo por
        // diferencia de abajo queda solo como respaldo.
        if (typeof bs.cash_rounding === "number") {
            return this.formatBs(Math.abs(bs.cash_rounding) < 0.005 ? 0 : bs.cash_rounding);
        }
        const subtotals = this.totals.subtotals || [];
        const last = subtotals[subtotals.length - 1];
        if (!last) {
            return this.formatBs(0);
        }
        let taxes = 0;
        for (const group of last.tax_groups || []) {
            const bsGroup = bs.tax_groups[String(group.id)];
            taxes += (bsGroup && bsGroup.tax_amount) || 0;
        }
        const rounding = bs.total_amount - (bs.subtotals[last.name] || 0) - taxes;
        // Evita "-0,00" por ruido de coma flotante cuando no hay diferencia.
        return this.formatBs(Math.abs(rounding) < 0.005 ? 0 : rounding);
    },
});

patch(TaxGroupComponent.prototype, {
    get l10nVeBs() {
        return this.props.totals && this.props.totals.l10n_ve_bs;
    },

    /** Impuesto del grupo en Bs (las claves de tax_groups son el id como texto). */
    bsTaxGroup() {
        const group = this.l10nVeBs.tax_groups[String(this.props.taxGroup.id)];
        return formatBs(this.l10nVeBs, group && group.tax_amount);
    },
});
