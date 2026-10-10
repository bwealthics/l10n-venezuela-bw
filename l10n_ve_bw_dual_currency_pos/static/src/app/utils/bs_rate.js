// Copyright 2026 BWEALTHICS LLC
// Part of l10n_ve_bw_dual_currency_pos. License LGPL-3.

/** "2026-10-09" -> "09-10-2026" (formato venezolano del recibo). */
export const l10nVeBsDmy = (iso) => {
    if (!iso) {
        return "";
    }
    const [y, m, d] = String(iso).slice(0, 10).split("-");
    return y && m && d ? `${d}-${m}-${y}` : String(iso);
};
