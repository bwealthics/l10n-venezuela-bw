// Copyright 2026 BWEALTHICS LLC
import { AlertDialog, ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import {
    FiscalBridgeError,
    buildInvoicePayload,
    callBridge,
    clearUncertain,
    getVesRate,
    isUncertain,
    markUncertain,
    toVes,
} from "@l10n_ve_bw_fiscal_printer/app/utils/fiscal_bridge";

patch(OrderPaymentValidation.prototype, {
    /** Modo papel permanente (caja SIN bridge): captura de los números de la
     *  papelería de imprenta autorizada ANTES de isOrderValid, para que el
     *  chequeo de cliente del core corra ya con el partner asignado. */
    async askBeforeValidation() {
        if ((await super.askBeforeValidation(...arguments)) === false) {
            return false;
        }
        return await this._l10nVePaperCapture();
    },

    /** Flujo sostenido de talonario (contingencia) o formas libres.
     *
     *  A diferencia de _l10nVeContingency (respaldo cuando el bridge FALLA),
     *  aquí no hay máquina fiscal: TODA venta se factura sobre papel, así
     *  que se piden los números en cada cobro y se fuerza la factura, que
     *  _prepare_invoice_vals enruta al diario del canal. La propuesta del
     *  siguiente correlativo sale del lote registrado (l10n.ve.paper.batch);
     *  el dato manda el PAPEL: el cajero confirma o corrige lo propuesto.
     */
    async _l10nVePaperCapture() {
        const config = this.pos.config;
        const order = this.order;
        const mode = config.l10n_ve_paper_mode;
        if (!mode || config.l10n_ve_bridge_url) {
            // Caja con máquina fiscal (o sin salida en papel): flujo clásico.
            return true;
        }
        if (order.l10n_ve_contingency_control) {
            // Reintento tras un fallo de sync: números ya capturados.
            order.setToInvoice(true);
            return true;
        }
        if (mode === "contingencia" && !this.pos.session.l10n_ve_contingency_start) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Contingencia no activada"),
                body: _t(
                    "Un gerente debe activar el modo Contingencia (menú de " +
                        "acciones) antes de cobrar: cada venta se factura a " +
                        "mano en el talonario autorizado."
                ),
            });
            return false;
        }
        // Art. 13.7 PA 0071: la factura sobre formatos identifica al
        // adquirente (nombre y cédula/RIF) — igual que en el papel.
        if (!order.getPartner()) {
            await this.pos.selectPartner(order);
            if (!order.getPartner()) {
                return false;
            }
        }
        const batchId =
            config.l10n_ve_paper_batch_id?.id ??
            config.raw?.l10n_ve_paper_batch_id ??
            config.l10n_ve_paper_batch_id;
        let proposal = {};
        if (batchId) {
            try {
                proposal = await this.pos.data.call(
                    "l10n.ve.paper.batch", "next_numbers", [[batchId]]
                );
            } catch {
                proposal = {}; // sin red: el papel manda, se digita a mano
            }
        }
        if (proposal.error) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Papelería agotada"),
                body: proposal.error,
            });
            return false;
        }
        let invoiceNumber = "";
        if (mode === "contingencia") {
            invoiceNumber = (
                (await makeAwaitable(this.pos.dialog, TextInputPopup, {
                    title: _t("Talonario — Nº de FACTURA del formato"),
                    placeholder: _t("Nº de factura preimpreso"),
                    startingValue: proposal.invoice || "",
                })) || ""
            ).trim();
            if (!invoiceNumber) {
                return false;
            }
        }
        const controlNumber = (
            (await makeAwaitable(this.pos.dialog, TextInputPopup, {
                title:
                    mode === "contingencia"
                        ? _t("Talonario — Nº de CONTROL del formato")
                        : _t("Forma libre — Nº de control de la hoja"),
                placeholder: _t("Nº de control preimpreso"),
                startingValue: proposal.control || "",
            })) || ""
        ).trim();
        if (!controlNumber) {
            return false;
        }
        // Duplicados contra las órdenes en memoria (multi-sesión lo cierra
        // el constraint del servidor y check_numbers del lote).
        const clash = this.pos.models["pos.order"]
            .getAll()
            .find(
                (o) =>
                    o !== order &&
                    (o.l10n_ve_contingency_control === controlNumber ||
                        (invoiceNumber &&
                            o.l10n_ve_contingency_invoice_number === invoiceNumber))
            );
        if (clash) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Número repetido"),
                body: _t("Ese Nº ya se usó en otra orden de esta sesión."),
            });
            return false;
        }
        if (batchId) {
            try {
                const problem = await this.pos.data.call(
                    "l10n.ve.paper.batch",
                    "check_numbers",
                    [[batchId], invoiceNumber || false, controlNumber]
                );
                if (problem) {
                    this.pos.dialog.add(AlertDialog, {
                        title: _t("Papelería fiscal"),
                        body: problem,
                    });
                    return false;
                }
            } catch {
                // Sin red: validan el constraint del servidor al sincronizar
                // y el propio talonario físico.
            }
        }
        order.l10n_ve_contingency_control = controlNumber;
        if (invoiceNumber) {
            order.l10n_ve_contingency_invoice_number = invoiceNumber;
        }
        this._l10nVeLogEvent(
            "contingency",
            mode === "contingencia"
                ? _t("Talonario: factura %s, control %s", invoiceNumber, controlNumber)
                : _t("Forma libre: control %s", controlNumber)
        );
        if (proposal.warning) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Papelería por agotarse"),
                body: proposal.warning,
            });
        }
        // Fuerza la factura: _prepare_invoice_vals la enruta al diario del
        // canal (contingencia o libre) con los números del papel.
        order.setToInvoice(true);
        return true;
    },

    async shouldHideValidationBehindFeedbackScreen() {
        const config = this.pos.config;
        // Guard idempotente: una orden ya estampada (reintento tras fallo de
        // sync con la nube) NO se reimprime. Una orden ya registrada en
        // contingencia tampoco vuelve a intentar la máquina.
        if (
            config.l10n_ve_bridge_url &&
            !this.order.l10n_ve_fiscal_number &&
            !this.order.l10n_ve_contingency_control
        ) {
            try {
                await this._l10nVePrintFiscal();
            } catch (e) {
                if (await this._l10nVeContingency(e)) {
                    return super.shouldHideValidationBehindFeedbackScreen(...arguments);
                }
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Impresora fiscal"),
                    body: e.message || _t("Error desconocido del bridge fiscal."),
                });
                // Sin super(): ni se finaliza ni se navega. La orden queda en
                // la pantalla de pago para reintentar — sin número fiscal no
                // hay venta legal.
                return;
            }
        }
        return super.shouldHideValidationBehindFeedbackScreen(...arguments);
    },

    /** Salida de contingencia (PA 0071 art. 11): registrar el Nº de control
     *  del talonario cuando la máquina no pudo emitir.
     *
     *  Dos candados deliberados:
     *  1) Solo aparece DESPUÉS de un fallo real de la máquina, así que el
     *     cajero no gana nada usándola cuando la impresora funciona.
     *  2) Queda VETADA si el error es ambiguo (timeout): ahí la máquina PUDO
     *     haber impreso, y sumarle un formato manual declararía dos veces el
     *     mismo hecho imponible. Para ese caso ya existe _l10nVeTryAdoptLast.
     */
    async _l10nVeContingency(error) {
        const session = this.pos.session;
        if (!session.l10n_ve_contingency_start) {
            return false;
        }
        if ((error && error.ambiguous) || isUncertain(this.order)) {
            return false;
        }
        // Odoo 19 TextInputPopup: sin prop `body`.
        const number = await makeAwaitable(this.pos.dialog, TextInputPopup, {
            title: _t(
                "Contingencia: facture en el talonario y capture el Nº de Control"
            ),
            placeholder: _t("Nº de Control del talonario"),
        });
        const clean = (number || "").trim();
        if (!clean) {
            return false;
        }
        const taken = this.pos.models["pos.order"]
            .getAll()
            .some((o) => o !== this.order && o.l10n_ve_contingency_control === clean);
        if (taken) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Nº de Control repetido"),
                body: _t("Ese Nº de Control ya se usó en otra orden de esta sesión."),
            });
            return false;
        }
        this.order.l10n_ve_contingency_control = clean;
        this._l10nVeLogEvent(
            "contingency",
            _t("Contingencia: Nº de Control %s del talonario", clean)
        );
        return true;
    },

    /** Bitácora en campos PLANOS de la orden, no por RPC: una llamada al
     *  servidor falla exactamente cuando importa (caja sin conexión), y el
     *  registro debe sobrevivir hasta el sync. */
    _l10nVeLogEvent(code, detail) {
        const order = this.order;
        const stamp = luxon.DateTime.now().toFormat("HH:mm:ss");
        const cashier =
            (this.pos.getCashier && this.pos.getCashier()?.name) ||
            this.pos.user?.name ||
            "";
        const entry = `${stamp} · ${cashier} · ${detail}`;
        const previous = order.l10n_ve_fiscal_event_note || "";
        order.l10n_ve_fiscal_event = code;
        // Se conservan las últimas 10 líneas: es una bitácora de incidencias
        // de UNA orden, no un log de aplicación.
        order.l10n_ve_fiscal_event_note = (previous ? previous + "\n" : "")
            .concat(entry)
            .split("\n")
            .slice(-10)
            .join("\n");
    },

    async _l10nVePrintFiscal() {
        const order = this.order;
        const config = this.pos.config;
        const rate = await getVesRate(this.pos);
        const refundLine = order.lines.find((l) => l.refunded_orderline_id);
        const original = refundLine && refundLine.refunded_orderline_id.order_id;
        if (refundLine && !(original && original.l10n_ve_fiscal_number)) {
            throw new FiscalBridgeError(
                _t(
                    "La orden original no tiene factura fiscal registrada: " +
                        "emita la nota de crédito manualmente en la máquina."
                )
            );
        }
        await callBridge(config, "/claim-terminal", { uuid: order.uuid });
        try {
            if (order.uiState.l10nVeUncertain || isUncertain(order)) {
                if (original) {
                    // El correlativo de NC no es verificable vía S1: no se
                    // reintenta a ciegas una NC que pudo haberse impreso.
                    throw new FiscalBridgeError(
                        _t(
                            "El intento anterior de nota de crédito no confirmó. " +
                                "Verifique el último ticket de la máquina: si la NC ya " +
                                "salió impresa NO reintente; regístrela con soporte."
                        )
                    );
                }
                if (await this._l10nVeTryAdoptLast(rate)) {
                    return;
                }
            }
            const payload = buildInvoicePayload(this.pos, order, rate);
            let res;
            if (original) {
                const fecha = String(original.l10n_ve_fiscal_date || "").slice(0, 10);
                res = await callBridge(config, "/print-credit-note", {
                    ...payload,
                    numero_factura_afectada: original.l10n_ve_fiscal_number,
                    serial_afectada: original.l10n_ve_fiscal_machine_serial || "",
                    fecha_afectada: fecha ? fecha.split("-").reverse().join("") : "",
                });
            } else {
                res = await callBridge(config, "/print-invoice", payload);
            }
            this._l10nVeStamp(
                res.numero_factura_fiscal,
                original ? "credit_note" : "invoice",
                res.serial
            );
        } catch (e) {
            if (e instanceof FiscalBridgeError && e.ambiguous) {
                // uiState + localStorage: la marca sobrevive un reload del POS
                order.uiState.l10nVeUncertain = true;
                markUncertain(order);
            }
            throw e;
        } finally {
            await callBridge(config, "/release-terminal", { uuid: order.uuid }).catch(
                () => {}
            );
        }
    },

    /** Anti-duplicados tras un timeout. Orden de decisión:
     *  1) el bridge ecoa el uuid de la última orden impresa → prueba dura;
     *  2) uuid ajeno → nuestra impresión NO completó → reimprimir;
     *  3) sin uuid (bridge reiniciado): total distinto → reimprimir;
     *     total igual o desconocido → decide el cajero mirando el ticket. */
    async _l10nVeTryAdoptLast(rate) {
        const order = this.order;
        const last = await callBridge(this.pos.config, "/check-last-invoice", {});
        if (last.uuid && last.uuid === order.uuid) {
            this._l10nVeStamp(last.numero_factura_fiscal, "invoice", last.serial);
            this._l10nVeLogEvent(
                "adopt_uuid",
                _t("Nº %s adoptado: el bridge ecoó el uuid de esta orden",
                    last.numero_factura_fiscal)
            );
            return true;
        }
        if (last.uuid && last.uuid !== order.uuid) {
            this._l10nVeLogEvent("reprint", _t("Reimpresión: el último ticket era de otra orden"));
            return false; // la última impresión fue de OTRA orden: imprimir normal
        }
        const totalVes = toVes(Math.abs(order.priceIncl), rate);
        if (last.monto_total != null && Math.abs(last.monto_total - totalVes) >= 0.011) {
            this._l10nVeLogEvent("reprint", _t("Reimpresión: el total del último ticket no coincide"));
            return false;
        }
        return await new Promise((resolve) => {
            this.pos.dialog.add(ConfirmationDialog, {
                title: _t("Impresora fiscal"),
                body: _t(
                    "El intento anterior no confirmó la impresión. ¿Salió impreso " +
                        "el ticket Nº %s por Bs %s? Confirme para usar ese número sin " +
                        "reimprimir; cancele para imprimir de nuevo.",
                    last.numero_factura_fiscal,
                    totalVes.toFixed(2)
                ),
                confirm: () => {
                    this._l10nVeStamp(last.numero_factura_fiscal, "invoice", last.serial);
                    // LA decisión humana peligrosa: el cajero afirma que ese
                    // ticket salió. Queda con hora y nombre.
                    this._l10nVeLogEvent(
                        "adopt_manual",
                        _t("El cajero confirmó que el ticket Nº %s ya salió impreso",
                            last.numero_factura_fiscal)
                    );
                    resolve(true);
                },
                cancel: () => {
                    this._l10nVeLogEvent("reprint", _t("El cajero indicó que el ticket NO salió"));
                    resolve(false);
                },
            });
        });
    },

    _l10nVeStamp(number, docType, serial) {
        const order = this.order;
        // Campos planos de pos.order: viajan al servidor en el primer sync.
        order.l10n_ve_fiscal_number = number;
        order.l10n_ve_fiscal_machine_serial =
            serial || this.pos.config.l10n_ve_machine_serial || "";
        // Hora LOCAL de la caja a propósito (sello legal del ticket físico);
        // el campo es Char, no Datetime — sin conversión UTC.
        order.l10n_ve_fiscal_date = luxon.DateTime.now().toFormat("yyyy-MM-dd HH:mm:ss");
        order.l10n_ve_fiscal_doc_type = docType;
        order.uiState.l10nVeUncertain = false;
        clearUncertain(order);
    },
});
