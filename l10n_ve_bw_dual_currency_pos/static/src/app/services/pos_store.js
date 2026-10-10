// Copyright 2026 BWEALTHICS LLC
// Part of l10n_ve_bw_dual_currency_pos. License LGPL-3.
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { ConnectionLostError } from "@web/core/network/rpc";
import { formatFloat } from "@web/core/utils/numbers";
import { nbsp } from "@web/core/utils/strings";
import { patch } from "@web/core/utils/patch";
import { parseFloat } from "@web/views/fields/parsers";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { l10nVeBsDmy } from "@l10n_ve_bw_dual_currency_pos/app/utils/bs_rate";

// Promesa en curso del popup de tasa: la pantalla de pago (al entrar) y la
// validación (al cobrar) pueden pedir la tasa casi a la vez; sin esto el
// cajero vería dos popups encimados.
let asking = null;

const cacheKey = (config) => `l10nVeBsRate:${config.id}`;

const safeParse = (raw) => {
    try {
        const n = parseFloat(String(raw ?? ""));
        return Number.isFinite(n) ? n : NaN;
    } catch {
        return NaN;
    }
};

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        // Sin await: precargar la tasa nunca debe retrasar ni romper el
        // arranque del POS (sin conexión se usa la última guardada).
        this.l10nVeBsRestoreCache();
        this.l10nVeBsLoadRate();
        return result;
    },

    /** Última tasa conocida guardada en el navegador: sirve al recibo y a la
     *  orden cuando el POS arranca sin conexión. Solo es un respaldo. */
    l10nVeBsRestoreCache() {
        try {
            const raw = localStorage.getItem(cacheKey(this.config));
            if (raw && !this.l10nVeBsRate) {
                // Lo guardado puede ser de otro día: sin el servidor no se
                // puede confirmar que sea la tasa de HOY, así que nunca se
                // restaura como tal (validateOrder solo rellena una orden sin
                // tasa en ese caso y no pisa la que ya traiga).
                this.l10nVeBsRate = { ...JSON.parse(raw), is_today: false };
            }
        } catch {
            /* modo incógnito o JSON dañado: se ignora */
        }
    },

    l10nVeBsStore(info) {
        this.l10nVeBsRate = info;
        try {
            localStorage.setItem(cacheKey(this.config), JSON.stringify(info));
        } catch {
            /* sin storage: queda en memoria */
        }
    },

    /** Pide al servidor la tasa vigente y si existe la de hoy. Devuelve true
     *  si pudo leerla; false si no hay conexión o el servidor falló (en ese
     *  caso se conserva lo que haya y NO se bloquea la venta). */
    async l10nVeBsLoadRate() {
        try {
            const info = await this.data.call("pos.config", "l10n_ve_bs_get_today_rate", [
                [this.config.id],
            ]);
            if (info && typeof info === "object") {
                this.l10nVeBsStore(info);
                return true;
            }
        } catch {
            /* sin conexión o error de servidor: se conserva la última */
        }
        return false;
    },

    l10nVeBsFormatRate(rate) {
        return formatFloat(rate, { digits: [69, 4] });
    },

    /** Monto en Bs con símbolo, sin depender de que res.currency de Bs esté
     *  cargada en el POS (solo carga la moneda de la compañía). */
    l10nVeBsFormat(amount) {
        const cur = this.l10nVeBsRate?.currency || {
            symbol: "Bs",
            decimal_places: 2,
            position: "after",
        };
        const text = formatFloat(amount, { digits: [69, cur.decimal_places ?? 2] });
        return cur.position === "before" ? [cur.symbol, text].join(nbsp) : [text, cur.symbol].join(nbsp);
    },

    /** Garantiza que exista la tasa BCV de HOY antes de cobrar.
     *  Devuelve true si se puede seguir y false si el cajero canceló (la
     *  orden no debe validarse mientras falte la tasa). Sin conexión o con
     *  el servidor caído no se bloquea: se usa la última tasa conocida. */
    async l10nVeBsEnsureRate() {
        if (!asking) {
            asking = this._l10nVeBsEnsureRate().finally(() => {
                asking = null;
            });
        }
        return asking;
    },

    async _l10nVeBsEnsureRate() {
        if (!(await this.l10nVeBsLoadRate())) {
            return true;
        }
        let info = this.l10nVeBsRate;
        if (!info?.currency || info.is_today) {
            return true;
        }
        const companyCur = this.config.currency_id?.name || "USD";
        for (;;) {
            const subtitle = info.rate
                ? _t(
                      "Última tasa cargada: %(rate)s (%(date)s). Digite la tasa BCV de hoy.",
                      { rate: this.l10nVeBsFormatRate(info.rate), date: l10nVeBsDmy(info.date) }
                  )
                : _t("No hay ninguna tasa cargada. Digite la tasa BCV de hoy.");
            const raw = await makeAwaitable(this.dialog, NumberPopup, {
                title: _t("Tasa BCV de hoy: Bs por 1 %s", companyCur),
                subtitle,
                placeholder: _t("Ej. 140,25"),
                confirmButtonLabel: _t("Guardar tasa"),
                isValid: (buffer) => safeParse(buffer) > 0,
            });
            if (raw === undefined) {
                return false; // canceló: no se puede cobrar sin la tasa del día
            }
            const rate = safeParse(raw);
            if (!(rate > 0)) {
                continue;
            }
            const ok = await ask(this.dialog, {
                title: _t("Confirmar tasa"),
                body: _t("¿Confirma que 1 %(cur)s = %(rate)s Bs es la tasa BCV de hoy?", {
                    cur: companyCur,
                    rate: this.l10nVeBsFormatRate(rate),
                }),
            });
            if (!ok) {
                continue;
            }
            try {
                info = await this.data.call("pos.config", "l10n_ve_bs_set_today_rate", [
                    [this.config.id],
                    rate,
                ]);
            } catch (error) {
                if (error instanceof ConnectionLostError) {
                    return true; // se cayó la conexión: se sigue con la última tasa
                }
                // UserError del servidor (fuera de ±15 %, ya existe, etc.)
                await ask(
                    this.dialog,
                    {
                        title: _t("No se pudo guardar la tasa"),
                        body: error?.data?.message || error?.message || String(error),
                    },
                    {},
                    AlertDialog
                );
                info = this.l10nVeBsRate;
                continue;
            }
            this.l10nVeBsStore(info);
            if (info.is_today) {
                return true;
            }
        }
    },
});
