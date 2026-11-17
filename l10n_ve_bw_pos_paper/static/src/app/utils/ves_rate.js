// Copyright 2026 BWEALTHICS LLC
import { _t } from "@web/core/l10n/translation";

export const round2 = (x) => Math.round(x * 100) / 100;

export function toVes(amount, rate) {
    return Math.round(amount * rate * 100) / 100;
}

// Cache de la última tasa buena, por pestaña: sin nube se sigue facturando
// con la última tasa BCV conocida.
let lastGoodRate = null;

export async function getVesRate(pos) {
    try {
        const rate = await pos.data.call("pos.config", "l10n_ve_get_ves_rate", [
            [pos.config.id],
        ]);
        if (rate > 0) {
            lastGoodRate = rate;
        }
    } catch {
        // Sin conexión: se usa la última tasa conocida.
    }
    if (!lastGoodRate) {
        throw new Error(
            _t("No hay tasa BCV disponible (cargue la tasa VES del día en Odoo).")
        );
    }
    return lastGoodRate;
}
