// Copyright 2026 BWEALTHICS LLC
import { _t } from "@web/core/l10n/translation";

export class FiscalBridgeError extends Error {
    constructor(message, ambiguous = false) {
        super(message);
        // true = el comando pudo llegar a la impresora sin respuesta (timeout):
        // el documento PUDO imprimirse; activa el flujo anti-duplicados.
        this.ambiguous = ambiguous;
    }
}

const RATES = [0, 8, 16, 31];

export function ivaPct(line) {
    // Impuestos DESPUÉS de la posición fiscal: un cliente exento cuya FP
    // mapea 16% → exento debe imprimir 0, igual que contabiliza Odoo.
    let taxes = line.tax_ids || [];
    const fp = line.order_id && line.order_id.fiscal_position_id;
    if (fp && fp.getTaxesAfterFiscalPosition) {
        taxes = fp.getTaxesAfterFiscalPosition(taxes) || [];
    }
    const iva = (taxes.find && taxes.find((t) => typeof t.amount === "number")) || null;
    const amount = (iva && iva.amount) || 0;
    return RATES.reduce((a, b) => (Math.abs(b - amount) < Math.abs(a - amount) ? b : a));
}

export function toVes(amount, rate) {
    return Math.round(amount * rate * 100) / 100;
}

// Timeout manual (AbortSignal.timeout requiere Chrome 103+; las cajas suelen
// correr Chromium kiosk viejos). Distinguir timeout (ambiguo: pudo imprimir)
// de connection-refused (seguro NO imprimió) es crítico para el anti-duplicados.
async function fetchWithTimeout(url, options, ms) {
    let timedOut = false;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
        timedOut = true;
        ctrl.abort();
    }, ms);
    try {
        return await fetch(url, { ...options, signal: ctrl.signal });
    } catch (e) {
        const err = e || new Error("fetch failed");
        err.l10nVeTimeout = timedOut;
        throw err;
    } finally {
        clearTimeout(timer);
    }
}

export async function callBridge(config, endpoint, payload = {}) {
    let resp;
    try {
        resp = await fetchWithTimeout(
            config.l10n_ve_bridge_url.replace(/\/$/, "") + endpoint,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Bridge-Token": config.l10n_ve_bridge_token || "",
                },
                body: JSON.stringify(payload),
            },
            90000
        );
    } catch (e) {
        throw new FiscalBridgeError(
            e && e.l10nVeTimeout
                ? _t("La impresora fiscal no respondió a tiempo (el ticket PUDO haberse impreso).")
                : _t("Sin conexión con el bridge fiscal (¿está corriendo en esta PC?)."),
            !!(e && e.l10nVeTimeout)
        );
    }
    const data = await resp.json().catch(() => ({}));
    if (data.estado !== "exito") {
        throw new FiscalBridgeError(
            data.mensaje || _t("Error de la impresora fiscal (HTTP %s).", resp.status)
        );
    }
    return data;
}

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
        // Sin nube se sigue facturando con la última tasa BCV conocida.
    }
    if (!lastGoodRate) {
        throw new FiscalBridgeError(
            _t("No hay tasa BCV disponible (cargue la tasa VES del día en Odoo).")
        );
    }
    return lastGoodRate;
}

// Marca anti-duplicados persistente (sobrevive un reload del POS, que borra
// order.uiState). Clave por uuid de la orden.
const UNCERTAIN_PREFIX = "l10nVeUncertain:";
export function markUncertain(order) {
    try {
        localStorage.setItem(UNCERTAIN_PREFIX + order.uuid, "1");
    } catch {
        /* modo incógnito: queda el uiState */
    }
}
export function clearUncertain(order) {
    try {
        localStorage.removeItem(UNCERTAIN_PREFIX + order.uuid);
    } catch {
        /* noop */
    }
}
export function isUncertain(order) {
    try {
        return !!localStorage.getItem(UNCERTAIN_PREFIX + order.uuid);
    } catch {
        return false;
    }
}

export function buildInvoicePayload(pos, order, rate) {
    const isRefund = order.lines.some((l) => l.refunded_orderline_id);
    const sign = isRefund ? -1 : 1; // la máquina recibe montos positivos
    const round2 = (x) => Math.round(x * 100) / 100;
    const items = order.lines
        .filter((l) => l.qty)
        .map((l) => ({
            // API 19.0 verificada: line.prices.total_included (crudo, con el
            // signo de la línea — NO usar priceIncl, que multiplica orderSign)
            descripcion: (l.getFullProductName() || "").slice(0, 40),
            precio: round2(toVes(l.prices.total_included / l.qty, rate)),
            cantidad: sign * l.qty,
            iva_porcentaje: ivaPct(l),
        }));
    // La máquina calcula el total como Σ(precio × cantidad) con los precios
    // YA redondeados a 2 decimales: el total y los pagos declarados deben
    // salir de ESA aritmética o el cierre falla por centavos.
    const machineTotal = round2(items.reduce((s, it) => s + it.precio * it.cantidad, 0));
    const pagos = order.payment_ids
        .map((p) => ({
            metodo:
                (p.payment_method_id && p.payment_method_id.l10n_ve_fiscal_payment_code) ||
                "01",
            monto: round2(toVes(sign * p.amount, rate)),
            divisa: !!(p.payment_method_id && p.payment_method_id.l10n_ve_igtf_applies),
        }))
        .filter((p) => p.monto > 0);
    // Absorber el delta de redondeo por-línea en el último pago (solo deltas
    // chicos; un delta grande — p.ej. vuelto de efectivo — pasa tal cual y lo
    // resuelve el cierre directo de la máquina).
    const paid = round2(pagos.reduce((s, p) => s + p.monto, 0));
    const delta = round2(machineTotal - paid);
    if (pagos.length && Math.abs(delta) <= 0.02 * items.length + 0.03) {
        pagos[pagos.length - 1].monto = round2(pagos[pagos.length - 1].monto + delta);
    }
    const company = pos.company;
    const igtfBase = pagos.filter((p) => p.divisa).reduce((s, p) => s + p.monto, 0);
    const partner = order.getPartner();
    return {
        uuid: order.uuid, // el bridge lo memoriza y lo ecoa en /check-last-invoice
        cliente_nombre: (partner && partner.name) || "CONSUMIDOR FINAL",
        cliente_rif: ((partner && partner.vat) || "").replace(/-/g, "").toUpperCase(),
        serial_impresora: pos.config.l10n_ve_machine_serial || "",
        tasa_dolar: rate,
        monto_total: machineTotal,
        monto_igtf:
            company.l10n_ve_is_spe && igtfBase > 0
                ? Math.round(igtfBase * (company.l10n_ve_igtf_pct || 3.0)) / 100
                : 0,
        items,
        pagos,
    };
}
