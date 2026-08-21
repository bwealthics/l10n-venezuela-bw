# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_invoice_format. License LGPL-3.
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_ve_control_date = fields.Date(
        string="Fecha de asignación del Nº de Control",
        copy=False,
        help="Fecha en que la imprenta autorizada asignó el Nº de control "
             "(PA SNAT/2024/000102 art. 7.15). La rellena el conector de "
             "imprenta digital; bajo forma libre se transcribe del talonario.",
    )

    def _l10n_ve_bs_amounts(self):
        """Totales del documento expresados en bolívares, y la tasa aplicada.

        Devuelve un dict vacío —y el QWeb no imprime nada— cuando no hay
        moneda de referencia configurada, cuando el comprobante YA está en esa
        moneda, o cuando no hay tasa a la fecha del documento. Preferible a
        imprimir un cero: un comprobante fiscal con un equivalente en Bs mal
        calculado es peor que uno sin él.

        La fecha de conversión es la del documento (`invoice_date`), nunca
        "hoy": el equivalente en Bs de una factura de julio no puede moverse
        porque se reimprima en agosto. Por eso también se guarda `date` en el
        resultado, que es lo que se rotula en la nota de la tasa.
        """
        self.ensure_one()
        bs = self.company_id.l10n_ve_bs_currency_id
        if not bs or bs == self.currency_id:
            return {}
        date = self.invoice_date or self.date or fields.Date.context_today(self)
        company = self.company_id
        # `res.currency._get_rates` termina en COALESCE(..., 1.0): una moneda
        # SIN ninguna tasa cargada convierte a la par y en silencio. Sobre un
        # comprobante fiscal eso imprime el total en dólares rotulado como
        # bolívares, así que la ausencia de tasa se comprueba aparte —el valor
        # de `rate` no la distingue de una paridad legítima 1:1—. El dominio de
        # compañía es el mismo del core para no divergir de lo que él resuelve.
        has_rate = self.env["res.currency.rate"].sudo().search_count([
            ("currency_id", "=", bs.id),
            ("company_id", "in", (False, company.root_id.id)),
        ], limit=1)
        if not has_rate:
            return {}
        # round=False: la tasa se rotula con sus decimales, no redondeada a los
        # dos del bolívar.
        rate = self.currency_id._convert(1.0, bs, company, date, round=False)
        if not rate:
            return {}

        def to_bs(amount):
            return self.currency_id._convert(amount, bs, company, date)

        total = to_bs(self.amount_total)
        residual = to_bs(self.amount_residual)
        return {
            "currency": bs,
            "rate": rate,
            "date": date,
            "untaxed": to_bs(self.amount_untaxed),
            "tax": to_bs(self.amount_tax),
            "total": total,
            "residual": residual,
            # El saldo solo se imprime si de verdad dice algo: ni en la factura
            # recién emitida (saldo == total) ni en la ya cobrada (saldo 0).
            "show_residual": bool(
                bs.compare_amounts(residual, total)
                and bs.compare_amounts(residual, 0.0)
            ),
        }

    def _l10n_ve_legal_datetime(self):
        """Fecha —y hora, cuando se conoce— en el formato del art. 7.6 de la
        PA SNAT/2024/000102.

        El artículo pide DDMMAAAA y HH.MM.SS con a.m./p.m., pero admite
        separadores (igual que el art. 34 de la PA 0071), así que se emite UNA
        sola línea legible en vez de duplicar la fecha del documento.
        """
        self.ensure_one()
        if not self.invoice_date:
            return ""
        legal_date = self.invoice_date.strftime("%d-%m-%Y")
        hour = self._l10n_ve_emission_time()
        return "%s %s" % (legal_date, hour) if hour else legal_date

    def _l10n_ve_emission_time(self):
        """Hora de emisión en HH.MM.SS con a.m./p.m., o cadena vacía.

        Solo se imprime cuando de verdad se conoce: hoy la sella la máquina
        fiscal en l10n_ve_fiscal_date, y mañana la aportará el conector de
        imprenta digital por la misma vía. Nunca se inventa una hora — un
        documento fiscal con una hora aproximada es peor que sin ella.
        La comprobación por _fields evita una dependencia dura de
        l10n_ve_bw_fiscal_printer (mismo patrón que el wizard de los libros).
        """
        self.ensure_one()
        if "l10n_ve_fiscal_date" not in self._fields:
            return ""
        raw = self.l10n_ve_fiscal_date or ""
        stamp = fields.Datetime.to_datetime(raw) if len(raw) >= 19 else None
        if not stamp:
            return ""
        # %p da AM/PM; la norma escribe "a.m"/"p.m".
        return stamp.strftime("%I.%M.%S %p").replace(
            "AM", "a.m").replace("PM", "p.m")
