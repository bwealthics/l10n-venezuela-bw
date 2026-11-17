// Copyright 2026 BWEALTHICS LLC
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(OrderPaymentValidation.prototype, {
    /** Modo papel permanente (caja SIN máquina fiscal): captura de los
     *  números de la papelería de imprenta autorizada ANTES de isOrderValid,
     *  para que el chequeo de cliente del core corra ya con el partner
     *  asignado. */
    async askBeforeValidation() {
        if ((await super.askBeforeValidation(...arguments)) === false) {
            return false;
        }
        return await this._l10nVePaperCapture();
    },

    /** Punto de extensión: un módulo de máquina fiscal devuelve true cuando
     *  la caja imprime en máquina, y entonces el modo papel se ignora. */
    _l10nVeHasFiscalMachine() {
        return false;
    },

    /** Flujo sostenido de talonario (contingencia) o formas libres.
     *
     *  A diferencia de _l10nVeContingency (respaldo cuando la máquina
     *  FALLA), aquí no hay máquina fiscal: TODA venta se factura sobre
     *  papel, así que se piden los números en cada cobro y se fuerza la
     *  factura, que _prepare_invoice_vals enruta al diario del canal. La
     *  propuesta del siguiente correlativo sale del lote registrado
     *  (l10n.ve.paper.batch); el dato manda el PAPEL: el cajero confirma o
     *  corrige lo propuesto.
     */
    async _l10nVePaperCapture() {
        const config = this.pos.config;
        const order = this.order;
        const mode = config.l10n_ve_paper_mode;
        if (!mode || this._l10nVeHasFiscalMachine()) {
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

    /** Salida de contingencia (PA 0071 art. 11): registrar el Nº de control
     *  del talonario cuando la máquina no pudo emitir. La llama el módulo de
     *  máquina fiscal tras un fallo de impresión.
     *
     *  Dos candados deliberados:
     *  1) Solo aplica DESPUÉS de un fallo real de la máquina, así que el
     *     cajero no gana nada usándola cuando la impresora funciona.
     *  2) Queda VETADA si el error es ambiguo (`error.ambiguous`): ahí la
     *     máquina PUDO haber impreso, y sumarle un formato manual declararía
     *     dos veces el mismo hecho imponible.
     */
    async _l10nVeContingency(error) {
        const session = this.pos.session;
        if (!session.l10n_ve_contingency_start) {
            return false;
        }
        if (error && error.ambiguous) {
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
});
