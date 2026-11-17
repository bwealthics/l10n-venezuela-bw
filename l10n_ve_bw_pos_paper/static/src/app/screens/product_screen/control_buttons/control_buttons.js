// Copyright 2026 BWEALTHICS LLC
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(ControlButtons.prototype, {
    setup() {
        super.setup(...arguments);
        // Servicio propio: no depender de que el core defina this.dialog.
        this.l10nVeDialog = useService("dialog");
    },

    /** Punto de extensión: un módulo de máquina fiscal devuelve true cuando
     *  la caja imprime en máquina (contingencia por falla de la máquina). */
    l10nVeHasFiscalMachine() {
        return false;
    },

    /** El botón aparece solo si la caja tiene diario de contingencia: con
     *  máquina fiscal (contingencia por falla) o en modo talonario
     *  permanente (caja sin máquina fiscal). */
    l10nVeShowContingency() {
        const config = this.pos.config;
        return (
            (this.l10nVeHasFiscalMachine() ||
                config.l10n_ve_paper_mode === "contingencia") &&
            !!config.l10n_ve_contingency_journal_id
        );
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
        // Caja sin máquina en modo talonario: la activación es el arranque
        // diario del turno, no el reporte de una avería.
        const permanent =
            !this.l10nVeHasFiscalMachine() &&
            this.pos.config.l10n_ve_paper_mode === "contingencia";
        // Odoo 19 TextInputPopup no acepta prop `body` (solo title/placeholder/rows/…).
        // La instrucción va en title + placeholder.
        const reason = await makeAwaitable(this.l10nVeDialog, TextInputPopup, {
            title: permanent
                ? _t("Activar contingencia (caja sin máquina fiscal)")
                : _t("Activar contingencia (falla de la máquina fiscal)"),
            placeholder: permanent
                ? _t("Motivo, ej. máquina fiscal no instalada")
                : _t("Motivo de la falla, ej. sin energía / avería"),
            rows: 3,
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
            // sin recargar el POS.
            session.l10n_ve_contingency_reason = state.reason;
            session.l10n_ve_contingency_start = state.start;
            this.l10nVeDialog.add(AlertDialog, {
                title: _t("Contingencia activa"),
                body: permanent
                    ? _t(
                          "A partir de ahora, en cada cobro el sistema pedirá " +
                              "los números del formato del talonario. Al cerrar " +
                              "la caja se desactiva sola."
                      )
                    : _t(
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
