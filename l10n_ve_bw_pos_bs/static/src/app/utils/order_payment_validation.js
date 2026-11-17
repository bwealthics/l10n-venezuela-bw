// Copyright 2026 BWEALTHICS LLC
// Part of l10n_ve_bw_pos_bs. License LGPL-3.
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { getVesRate, toVes } from "@l10n_ve_bw_pos_paper/app/utils/ves_rate";
import { splitNeedsCustomer } from "@l10n_ve_bw_pos_bs/app/models/pos_order";

const round2 = (x) => Math.round(x * 100) / 100;

// Bancos emisores de pago móvil (códigos SUDEBAN), los más usados primero.
// El código se guarda en pos.payment.l10n_ve_payer_bank y es el bancoOrigen
// que exige el API Conciliación BDV (getMovement).
const VE_BANKS = [
    ["0102", "Banco de Venezuela"],
    ["0134", "Banesco"],
    ["0105", "Mercantil"],
    ["0108", "BBVA Provincial"],
    ["0114", "Bancaribe"],
    ["0191", "BNC Banco Nacional de Crédito"],
    ["0172", "Bancamiga"],
    ["0163", "Banco del Tesoro"],
    ["0175", "Bicentenario del Pueblo"],
    ["0151", "BFC Banco Fondo Común"],
    ["0104", "Venezolano de Crédito"],
    ["0115", "Banco Exterior"],
    ["0128", "Banco Caroní"],
    ["0137", "Sofitasa"],
    ["0138", "Banco Plaza"],
    ["0156", "100% Banco"],
    ["0157", "DelSur"],
    ["0166", "Banco Agrícola de Venezuela"],
    ["0168", "Bancrecer"],
    ["0169", "Mi Banco"],
    ["0171", "Banco Activo"],
    ["0174", "Banplus"],
    ["0177", "Banfanb"],
];

const VE_BANK_NAMES = Object.fromEntries(VE_BANKS);

// Cuentas del comercio que reciben el cobro (pos.payment.method
// l10n_ve_bs_dest_banks, "0172,0102"; el primero es el predeterminado).
// Auditoría 2026-10-17: desde fines de sept casi todo pago móvil llega a
// Bancamiga, que el API de BDV no ve; sin el destino el verificador lo daba
// por "comprobante falso".
const destBanksOf = (method) =>
    String(method?.l10n_ve_bs_dest_banks || "")
        .split(",")
        .map((c) => c.trim())
        .filter((c) => /^\d{4}$/.test(c));

// Normaliza a 04XXXXXXXXX (11 dígitos); "" si no es un celular VE válido.
const normPhoneVe = (t) => {
    const d = String(t || "").replace(/\D/g, "");
    if (d.length === 12 && d.startsWith("58")) {
        return "0" + d.slice(2);
    }
    if (d.length === 11 && d.startsWith("04")) {
        return d;
    }
    if (d.length === 10 && d.startsWith("4")) {
        return "0" + d;
    }
    return "";
};

patch(OrderPaymentValidation.prototype, {
    /** Captura de tenders en bolívares ANTES de validar la orden: monto Bs
     *  exacto recibido (propuesto a tasa BCV, editable) y referencia de la
     *  transacción si el método la exige. Corre después de la captura de
     *  papelería fiscal (patch de l10n_ve_bw_pos_paper en este mismo
     *  método — ambos encadenan super). */
    async askBeforeValidation() {
        if ((await super.askBeforeValidation(...arguments)) === false) {
            return false;
        }
        return await this._l10nVeBsCapture();
    },

    async _askForCustomerIfRequired() {
        // El core pide cliente ante cualquier pago split; los métodos con
        // "Cliente por defecto (split)" no lo necesitan.
        if (!this.order.getPartner() && !splitNeedsCustomer(this.order.payment_ids)) {
            return;
        }
        return await super._askForCustomerIfRequired(...arguments);
    },

    async _l10nVeBsCapture() {
        const order = this.order;
        const lines = order.payment_ids.filter(
            (p) => p.payment_method_id?.l10n_ve_bs_tender && p.amount
        );
        if (!lines.length) {
            return true;
        }
        // Tasa BCV del día (RPC con cache offline de l10n_ve_bw_pos_paper).
        // Sin tasa se puede seguir: el cajero digita los Bs del comprobante.
        let rate = null;
        try {
            rate = await getVesRate(this.pos);
        } catch {
            rate = null;
        }
        for (const p of lines) {
            if (!(await this._l10nVeBsCaptureLine(p, rate))) {
                return false;
            }
        }
        return true;
    },

    /** Guard de idempotencia: en un reintento de validación (p.ej. fallo de
     *  sync) no se vuelve a preguntar, salvo que el cajero haya cambiado el
     *  importe de la línea después de capturar. */
    _l10nVeBsAlreadyCaptured(p) {
        // "datos del pagador" implica referencia: sin ella el pago no se
        // puede verificar contra BDV (y el backend ni dispararia el ping)
        const requireRef = !!(
            p.payment_method_id.l10n_ve_bs_require_ref ||
            p.payment_method_id.l10n_ve_bs_payer_data
        );
        const requirePayer = !!p.payment_method_id.l10n_ve_bs_payer_data && p.amount > 0;
        const requireDest = p.amount > 0 && destBanksOf(p.payment_method_id).length > 0;
        return (
            !!p.l10n_ve_amount_bs &&
            p.l10n_ve_amount_usd === round2(p.amount) &&
            (!requireRef || !!(p.payment_ref_no || "").trim()) &&
            (!requirePayer ||
                (!!normPhoneVe(p.l10n_ve_payer_phone) &&
                    !!(p.l10n_ve_payer_bank || "").trim())) &&
            (!requireDest || !!(p.l10n_ve_dest_bank || "").trim())
        );
    },

    async _l10nVeBsCaptureLine(p, rate) {
        if (this._l10nVeBsAlreadyCaptured(p)) {
            return true;
        }
        const method = p.payment_method_id;
        const sign = p.amount < 0 ? -1 : 1; // reembolso: Bs devueltos, con signo
        const usdAbs = Math.abs(p.amount);
        const expected = rate ? toVes(usdAbs, rate) : 0;

        // ── Monto Bs ─────────────────────────────────────────────────────
        let bs = 0;
        for (;;) {
            // Al reiterar (monto rechazado) se conserva lo digitado como base.
            const suggested = bs || Math.abs(p.l10n_ve_amount_bs) || expected;
            const raw = await makeAwaitable(this.pos.dialog, NumberPopup, {
                title: sign < 0
                    ? _t("%s — Bs DEVUELTOS al cliente", method.name)
                    : _t("%s — Bs recibidos", method.name),
                subtitle: rate
                    ? _t("Equivalente a tasa BCV %s: Bs %s", rate, expected.toFixed(2))
                    : _t("Sin tasa BCV disponible: digite los Bs del comprobante"),
                startingValue: suggested ? suggested.toFixed(2) : "",
            });
            if (raw === undefined) {
                return false; // cancelado: de vuelta a la pantalla de pago
            }
            bs = round2(parseFloat(String(raw).replace(",", ".")) || 0);
            if (!(bs > 0)) {
                // await: sin él, el popup re-abierto taparía el alert y cada
                // intento fallido acumularía un modal huérfano.
                await ask(
                    this.pos.dialog,
                    {
                        title: _t("Monto en Bs"),
                        body: _t("Capture los bolívares exactos del comprobante (mayor a cero)."),
                    },
                    {},
                    AlertDialog
                );
                continue;
            }
            // Cinturón anti-typo: >5% de desvío contra la tasa BCV pide
            // confirmación explícita (un dígito de menos = FX gigante falso).
            if (expected && Math.abs(bs - expected) / expected > 0.05) {
                const ok = await ask(this.pos.dialog, {
                    title: _t("Monto fuera de tasa"),
                    body: _t(
                        "Capturó Bs %s pero a tasa BCV del día serían Bs %s. " +
                            "¿Es correcto el monto del comprobante?",
                        bs.toFixed(2),
                        expected.toFixed(2)
                    ),
                });
                if (!ok) {
                    continue; // re-pedir, conservando lo digitado como base
                }
            }
            break;
        }

        // ── Referencia ───────────────────────────────────────────────────
        // obligatoria si el metodo la exige O si exige datos del pagador
        // (la verificacion BDV es imposible sin referencia)
        let ref = (p.payment_ref_no || "").trim();
        if (method.l10n_ve_bs_require_ref || method.l10n_ve_bs_payer_data) {
            for (;;) {
                const raw = await makeAwaitable(this.pos.dialog, TextInputPopup, {
                    title: _t("%s — Nº de referencia", method.name),
                    placeholder: _t("Referencia de la transacción (según el comprobante)"),
                    startingValue: ref,
                });
                if (raw === undefined) {
                    return false; // cancelado
                }
                ref = (raw || "").trim();
                if (!ref) {
                    await ask(
                        this.pos.dialog,
                        {
                            title: _t("Referencia obligatoria"),
                            body: _t(
                                "Sin la referencia no se puede conciliar el cobro " +
                                    "contra el banco. Cópiela del comprobante del cliente."
                            ),
                        },
                        {},
                        AlertDialog
                    );
                    continue;
                }
                // Referencia repetida en la sesión (cualquier tender Bs, no
                // solo este método): casi siempre es un comprobante reusado o
                // un typo — confirmación explícita.
                const clash = this.pos.models["pos.payment"]
                    .getAll()
                    .some(
                        (other) =>
                            other !== p &&
                            (other.payment_ref_no || "").trim() === ref &&
                            other.payment_method_id?.l10n_ve_bs_tender
                    );
                if (clash) {
                    const ok = await ask(this.pos.dialog, {
                        title: _t("Referencia repetida"),
                        body: _t(
                            "La referencia %s ya se usó en otro pago de esta " +
                                "sesión. ¿Seguro que es un comprobante distinto?",
                            ref
                        ),
                    });
                    if (!ok) {
                        continue;
                    }
                }
                break;
            }
        }

        // ── Banco destino (cuenta del comercio que recibió el pago) ──────
        // Solo cobros. Un solo banco configurado = sin pregunta. Con varios,
        // el cajero lo lee del comprobante; el primero viene marcado.
        let destBank = (p.l10n_ve_dest_bank || "").trim();
        const destBanks = sign > 0 ? destBanksOf(method) : [];
        if (destBanks.length === 1) {
            destBank = destBanks[0];
        } else if (destBanks.length > 1) {
            const current = destBanks.includes(destBank) ? destBank : destBanks[0];
            const picked = await makeAwaitable(this.pos.dialog, SelectionPopup, {
                title: _t("%s — ¿A qué banco llegó el pago?", method.name),
                list: destBanks.map((code, i) => ({
                    id: i,
                    label: code + " — " + (VE_BANK_NAMES[code] || code),
                    item: code,
                    isSelected: code === current,
                })),
            });
            if (picked === undefined) {
                return false; // cancelado
            }
            destBank = picked;
        }

        // ── Datos del pagador (los exige el API Conciliación BDV) ────────
        // Solo cobros: en un reembolso el pagador es el comercio. Teléfono y
        // banco emisor salen del mismo comprobante que ya muestra el cliente.
        let payerPhone = normPhoneVe(p.l10n_ve_payer_phone);
        let payerBank = (p.l10n_ve_payer_bank || "").trim();
        const needPayer = !!method.l10n_ve_bs_payer_data && sign > 0;
        if (needPayer) {
            for (;;) {
                const raw = await makeAwaitable(this.pos.dialog, TextInputPopup, {
                    title: _t("%s — Teléfono del pagador", method.name),
                    placeholder: _t("04XXXXXXXXX (según el comprobante)"),
                    startingValue:
                        payerPhone || normPhoneVe(this.order.partner_id?.phone) || "",
                });
                if (raw === undefined) {
                    return false; // cancelado
                }
                payerPhone = normPhoneVe(raw);
                if (payerPhone) {
                    break;
                }
                await ask(
                    this.pos.dialog,
                    {
                        title: _t("Teléfono inválido"),
                        body: _t(
                            "Debe ser el celular venezolano desde el que se hizo " +
                                "el pago móvil: 11 dígitos empezando por 04 " +
                                "(p.ej. 04141234567)."
                        ),
                    },
                    {},
                    AlertDialog
                );
            }
            const bank = await makeAwaitable(this.pos.dialog, SelectionPopup, {
                title: _t("%s — Banco emisor del pago", method.name),
                list: VE_BANKS.map(([code, name], i) => ({
                    id: i,
                    label: code + " — " + name,
                    item: code,
                    isSelected: code === payerBank,
                })),
            });
            if (bank === undefined) {
                return false; // cancelado (o cerró sin elegir banco)
            }
            payerBank = bank;
        }

        // Campos planos de pos.payment: viajan al backend en el sync de la
        // orden (pos.payment carga/serializa todos sus campos en v19).
        p.l10n_ve_amount_bs = sign * bs;
        p.l10n_ve_amount_usd = round2(p.amount);
        p.l10n_ve_rate = rate || 0;
        if (ref) {
            p.payment_ref_no = ref;
        }
        if (needPayer) {
            p.l10n_ve_payer_phone = payerPhone;
            p.l10n_ve_payer_bank = payerBank;
        }
        if (destBanks.length) {
            p.l10n_ve_dest_bank = destBank;
        }
        return true;
    },
});
