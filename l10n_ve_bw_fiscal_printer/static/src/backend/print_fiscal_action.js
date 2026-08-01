import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

// Client action del botón "Imprimir fiscal" en facturas: el fetch al bridge
// sale del NAVEGADOR, así que solo funciona en la PC donde corre el bridge.
registry.category("actions").add(
    "l10n_ve_bw_fiscal_printer.print_fiscal",
    async (env, action) => {
        const p = action.params || {};
        try {
            let resp;
            let timedOut = false;
            const ctrl = new AbortController();
            const timer = setTimeout(() => {
                timedOut = true;
                ctrl.abort();
            }, 90000);
            try {
                resp = await fetch(p.bridge_url.replace(/\/$/, "") + p.endpoint, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-Bridge-Token": p.bridge_token || "",
                    },
                    body: JSON.stringify(p.payload),
                    signal: ctrl.signal,
                });
            } catch {
                throw new Error(
                    timedOut
                        ? _t(
                              "La impresora no respondió a tiempo: verifique en el " +
                                  "ticket físico si imprimió ANTES de reintentar."
                          )
                        : _t(
                              "Sin conexión con el bridge fiscal: este botón solo " +
                                  "funciona en la PC de la caja donde corre el bridge."
                          )
                );
            } finally {
                clearTimeout(timer);
            }
            const data = await resp.json().catch(() => ({}));
            if (data.estado !== "exito") {
                throw new Error(data.mensaje || _t("Error de la impresora fiscal."));
            }
            await env.services.orm.call("account.move", "l10n_ve_set_fiscal_result", [
                [p.move_id],
                data.numero_factura_fiscal,
                data.serial || p.machine_serial, // preferir el serial REAL reportado
                p.doc_type,
            ]);
            env.services.notification.add(
                _t("Documento fiscal Nº %s impreso.", data.numero_factura_fiscal),
                { type: "success" }
            );
            await env.services.action.doAction({
                type: "ir.actions.client",
                tag: "soft_reload",
            });
        } catch (e) {
            env.services.notification.add(e.message || String(e), {
                title: _t("Impresora fiscal"),
                type: "danger",
                sticky: true,
            });
        }
    }
);
