// Copyright 2026 BWEALTHICS LLC
import { AlertDialog, ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { callBridge } from "@l10n_ve_bw_fiscal_printer/app/utils/fiscal_bridge";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(ControlButtons.prototype, {
    setup() {
        super.setup(...arguments);
        // Servicio propio: no depender de que el core defina this.dialog.
        this.l10nVeDialog = useService("dialog");
    },

    async clickReporteX() {
        try {
            await callBridge(this.pos.config, "/report-x", {});
            this.l10nVeDialog.add(AlertDialog, {
                title: _t("Impresora fiscal"),
                body: _t("Reporte X impreso."),
            });
        } catch (e) {
            this.l10nVeDialog.add(AlertDialog, {
                title: _t("Impresora fiscal"),
                body: e.message,
            });
        }
    },

    clickCierreZ() {
        this.l10nVeDialog.add(ConfirmationDialog, {
            title: _t("Cierre Z"),
            body: _t("El Cierre Z cierra el día fiscal y no se puede repetir. ¿Continuar?"),
            confirm: async () => {
                try {
                    const res = await callBridge(this.pos.config, "/report-z", {});
                    await this.pos.data.call("pos.session", "write", [
                        [this.pos.session.id],
                        { l10n_ve_z_number: res.numero_reporte_z || "" },
                    ]);
                    this.l10nVeDialog.add(AlertDialog, {
                        title: _t("Impresora fiscal"),
                        body: _t("Cierre Z Nº %s impreso.", res.numero_reporte_z || "—"),
                    });
                } catch (e) {
                    this.l10nVeDialog.add(AlertDialog, {
                        title: _t("Impresora fiscal"),
                        body: e.message,
                    });
                }
            },
            cancel: () => {},
        });
    },

    /** Autoriza el modo contingencia para la sesión de caja. El permiso lo
     *  valida el SERVIDOR (solo gerente de PdV): aquí solo se pinta. */
    async clickContingencia() {
        const session = this.pos.session;
        if (session.l10n_ve_contingency_start) {
            this.l10nVeDialog.add(AlertDialog, {
                title: _t("Contingencia"),
                body: _t(
                    "El modo contingencia ya está activo desde %s. Se desactiva " +
                        "solo al cerrar la caja.",
                    session.l10n_ve_contingency_start
                ),
            });
            return;
        }
        const reason = await makeAwaitable(this.l10nVeDialog, TextInputPopup, {
            title: _t("Activar contingencia"),
            body: _t(
                "Solo para cuando la máquina fiscal está averiada o sin " +
                    "energía. Las ventas se facturarán a mano en el talonario " +
                    "autorizado. Indique el motivo de la falla."
            ),
            placeholder: _t("Motivo de la falla"),
        });
        if (!reason) {
            return;
        }
        try {
            const state = await this.pos.data.call(
                "pos.session",
                "l10n_ve_contingency_open",
                [[session.id], reason]
            );
            // Se refresca el registro local para que el rótulo rojo aparezca
            // sin recargar el POS (mismo truco que _l10nVeStamp).
            session.l10n_ve_contingency_reason = state.reason;
            session.l10n_ve_contingency_start = state.start;
            this.l10nVeDialog.add(AlertDialog, {
                title: _t("Contingencia activa"),
                body: _t(
                    "A partir de ahora, si la máquina falla el sistema pedirá " +
                        "el Nº de Control del talonario. Al cerrar la caja se " +
                        "desactiva sola."
                ),
            });
        } catch (e) {
            this.l10nVeDialog.add(AlertDialog, {
                title: _t("Contingencia"),
                body: e.message || _t("No se pudo activar el modo contingencia."),
            });
        }
    },
});
