# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
from bisect import bisect_right
from datetime import datetime, time, timedelta

import pytz

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ve_show_line_amount_bs = fields.Boolean(
        string="Mostrar Importe Bs por línea en la factura",
        default=True,
        help="Añade al cuerpo del comprobante una columna con el importe de "
             "cada ítem expresado en bolívares a la tasa del documento.",
    )
    l10n_ve_bs_rate_cutoff = fields.Float(
        string="Hora de publicación de la tasa BCV",
        default=9.25,
        help="Hora local (zona de la compañía, por defecto Caracas) a partir "
             "de la cual se exige la tasa BCV del día. Antes de esa hora vale "
             "la del día anterior: el BCV publica la tasa a las 9:00 y el n8n "
             "la carga a las 9:15.",
    )
    l10n_ve_show_line_price_bs = fields.Boolean(
        string="Mostrar Precio Bs por línea en la factura",
        default=False,
        help="Añade junto al precio unitario su equivalente en bolívares. "
             "Apagado por defecto: con precios de varios decimales la columna "
             "suele confundir más de lo que aclara.",
    )

    # ------------------------------------------------------------------
    # Búsqueda de la tasa del bolívar
    # ------------------------------------------------------------------
    # Mismo orden que `res.currency._get_rates` del core: primero las tasas
    # de la compañía raíz y, solo si no hay ninguna <= fecha, las globales
    # (company_id.id ASC deja los NULL al final en PostgreSQL). Con
    # `name desc` a secas, una tasa global más reciente ganaría la FECHA
    # mientras el VALOR (que sale de `_get_conversion_rate`) vendría de la
    # tasa de la compañía: fecha y valor de registros distintos.
    _L10N_VE_BS_RATE_ORDER = "company_id.id, name desc"

    def _l10n_ve_bs_rate_domain(self):
        """Dominio de las tasas de la moneda Bs que valen para esta compañía.

        Es el MISMO dominio de compañía que usa `res.currency._get_rates`
        (tasas globales o de la compañía raíz): las sucursales no tienen
        tasas propias en Odoo 19 y divergir del core haría que el Bs de un
        asiento no coincidiera con lo que el core resolvería para esa fecha.
        El orden también es el del core (`_L10N_VE_BS_RATE_ORDER`).
        """
        self.ensure_one()
        return [
            ("currency_id", "=", self.l10n_ve_bs_currency_id.id),
            ("company_id", "in", (False, self.root_id.id)),
        ]

    def _l10n_ve_bs_rate_value(self, rate_date):
        """Bs por 1 unidad de la moneda de la compañía a `rate_date`.

        Solo se llama DESPUÉS de comprobar que existe un registro de tasa en
        esa fecha: `_get_conversion_rate` termina en `_get_rates`, cuyo
        COALESCE(..., 1.0) convierte a la par en silencio cuando no hay tasa,
        y eso sobre un libro legal rotularía dólares como bolívares.
        """
        self.ensure_one()
        currency = self.currency_id
        rate = currency._get_conversion_rate(
            currency, self.l10n_ve_bs_currency_id, self, rate_date)
        return rate or 0.0

    def _l10n_ve_bs_rate_at(self, date):
        """Tasa Bs vigente a `date` según la tabla de tasas.

        :return: ``(rate, rate_date)``: Bs por 1 unidad de la moneda de la
            compañía y la fecha del registro de tasa usado (la última
            ``<= date``). ``(0.0, False)`` si no hay moneda Bs configurada o
            no existe NINGUNA tasa anterior o igual a la fecha: nunca se
            inventa una paridad. Si la moneda Bs es la de la compañía (otras
            bases, p. ej. SITELCA) la tasa es 1.0 a la misma fecha.
        """
        self.ensure_one()
        date = date or fields.Date.context_today(self)
        bs = self.l10n_ve_bs_currency_id
        if not bs:
            return 0.0, False
        if bs == self.currency_id:
            return 1.0, date
        rate_rec = self.env["res.currency.rate"].sudo().search(
            self._l10n_ve_bs_rate_domain() + [("name", "<=", date)],
            order=self._L10N_VE_BS_RATE_ORDER, limit=1)
        if not rate_rec:
            return 0.0, False
        return self._l10n_ve_bs_rate_value(rate_rec.name), rate_rec.name

    def _l10n_ve_bs_rates_at(self, dates):
        """Versión por lote de `_l10n_ve_bs_rate_at`.

        Existe por el rendimiento del `-i`: Odoo calcula la tasa de los
        ~3.800 asientos existentes de una vez, y una búsqueda por asiento
        serían miles de consultas. Aquí se leen UNA vez las fechas de tasa de
        la moneda Bs y se resuelve cada fecha con bisección; el valor se
        calcula una sola vez por fecha de tasa distinta.

        :return: ``{date: (rate, rate_date)}`` para cada fecha pedida.
        """
        self.ensure_one()
        dates = {d for d in dates if d}
        bs = self.l10n_ve_bs_currency_id
        if not dates:
            return {}
        if not bs:
            return {d: (0.0, False) for d in dates}
        if bs == self.currency_id:
            return {d: (1.0, d) for d in dates}
        if len(dates) == 1:
            # El compute de la tasa es recursivo (reversiones) y Odoo lo llama
            # asiento por asiento: con una sola fecha basta la búsqueda con
            # limit=1, no leer todas las fechas de tasa.
            date = next(iter(dates))
            return {date: self._l10n_ve_bs_rate_at(date)}
        rates = self.env["res.currency.rate"].sudo().search_fetch(
            self._l10n_ve_bs_rate_domain() + [("name", "<=", max(dates))],
            ["name", "company_id"], order="name asc")
        # Dos listas, porque el core prefiere SIEMPRE una tasa de la compañía
        # (aunque sea más vieja) sobre una global: se busca primero entre las
        # de la compañía y solo si no hay ninguna <= fecha, entre las
        # globales. Así la fecha elegida es la del registro que el core usará
        # para el valor. set(): una fecha por día en cada lista.
        company_dates = sorted({r.name for r in rates if r.company_id})
        global_dates = sorted({r.name for r in rates if not r.company_id})

        def last_on_or_before(rate_dates, date):
            idx = bisect_right(rate_dates, date) - 1
            return rate_dates[idx] if idx >= 0 else False

        values = {}
        result = {}
        for date in dates:
            rate_date = (last_on_or_before(company_dates, date)
                         or last_on_or_before(global_dates, date))
            if not rate_date:
                result[date] = (0.0, False)
                continue
            if rate_date not in values:
                values[rate_date] = self._l10n_ve_bs_rate_value(rate_date)
            result[date] = (values[rate_date], rate_date)
        return result

    def _l10n_ve_bs_requires_daily_rate(self):
        """¿Rige para esta compañía la regla de pedir la tasa BCV del día?

        Es una exigencia venezolana (art. 25 de la Ley del IVA: la tasa del
        día del hecho imponible), así que solo aplica a compañías con país
        fiscal Venezuela. Fuera de VE la tasa Bs se sigue congelando por
        asiento, pero no se bloquea la confirmación ni el cobro en el POS.
        """
        self.ensure_one()
        country = self.account_fiscal_country_id or self.country_id
        return country.code == "VE"

    # ------------------------------------------------------------------
    # Hora de corte: antes de publicarse la tasa del día vale la de ayer
    # ------------------------------------------------------------------
    def _l10n_ve_bs_tz(self):
        """Zona horaria de la regla de la tasa del día (la del BCV/n8n)."""
        self.ensure_one()
        return pytz.timezone(self.partner_id.tz or "America/Caracas")

    def _l10n_ve_bs_local_now(self):
        """Ahora en la zona de la compañía (`fields.Datetime.now` es UTC y
        lo congela `freeze_time` en las pruebas)."""
        self.ensure_one()
        return pytz.utc.localize(fields.Datetime.now()).astimezone(
            self._l10n_ve_bs_tz())

    def _l10n_ve_bs_local_today(self):
        self.ensure_one()
        return self._l10n_ve_bs_local_now().date()

    def _l10n_ve_bs_cutoff_at(self, date):
        """Momento (UTC, naive) en que `date` exige su propia tasa."""
        self.ensure_one()
        hours = self.l10n_ve_bs_rate_cutoff or 0.0
        minutes = int(round(hours * 60))
        local = self._l10n_ve_bs_tz().localize(
            datetime.combine(date, time(0, 0)) + timedelta(minutes=minutes))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _l10n_ve_bs_min_rate_date(self, date):
        """Fecha mínima de tasa aceptable para un documento de fecha `date`.

        Regla: el BCV publica la tasa del día a las 9:00 y el n8n la carga a
        la hora de corte (9:15). Para un documento de HOY confirmado antes de
        esa hora vale la tasa de AYER; después, o para cualquier otra fecha,
        se exige la tasa de esa misma fecha.
        """
        self.ensure_one()
        if (date == self._l10n_ve_bs_local_today()
                and fields.Datetime.now() < self._l10n_ve_bs_cutoff_at(date)):
            return date - timedelta(days=1)
        return date

    def _l10n_ve_bs_rate_acceptable_for(self, date):
        """¿La tasa disponible sirve para un documento de fecha `date`?

        True si hay una tasa Bs con fecha entre la mínima aceptable
        (`_l10n_ve_bs_min_rate_date`) y `date`, o si no hay nada que pedir
        (sin moneda Bs, o Bs es la moneda de la compañía).
        """
        self.ensure_one()
        date = date or self._l10n_ve_bs_local_today()
        bs = self.l10n_ve_bs_currency_id
        if not bs or bs == self.currency_id:
            return True
        return bool(self.env["res.currency.rate"].sudo().search_count(
            self._l10n_ve_bs_rate_domain() + [
                ("name", ">=", self._l10n_ve_bs_min_rate_date(date)),
                ("name", "<=", date)], limit=1))

    def _l10n_ve_bs_rate_valid_until(self):
        """Hasta cuándo (UTC, naive) es aceptable la tasa vigente de hoy.

        Con la tasa de hoy cargada: hasta la hora de corte de mañana. Con la
        de ayer y antes del corte: hasta el corte de hoy. Si no hay tasa
        aceptable: ahora (ya vencida). Lo usa el POS para no imprimir Bs con
        una tasa que dejó de valer mientras la caja seguía abierta.
        """
        self.ensure_one()
        today = self._l10n_ve_bs_local_today()
        if self._l10n_ve_bs_has_rate_on(today):
            return self._l10n_ve_bs_cutoff_at(today + timedelta(days=1))
        if self._l10n_ve_bs_rate_acceptable_for(today):
            return self._l10n_ve_bs_cutoff_at(today)
        return fields.Datetime.now()

    def _l10n_ve_bs_has_rate_on(self, date):
        """¿Hay una tasa Bs cargada EXACTAMENTE para `date`?

        Es la pregunta que hacen la confirmación de facturas desde la
        interfaz y el POS antes de cobrar: la regla del negocio es pedir la
        tasa del día en vez de usar la de otro día en silencio.
        Devuelve True cuando no hay nada que pedir (sin moneda Bs, o la moneda
        Bs es la de la compañía), para que los llamadores no muestren un
        diálogo que no se puede satisfacer.
        """
        self.ensure_one()
        date = date or fields.Date.context_today(self)
        bs = self.l10n_ve_bs_currency_id
        if not bs or bs == self.currency_id:
            return True
        return bool(self.env["res.currency.rate"].sudo().search_count(
            self._l10n_ve_bs_rate_domain() + [("name", "=", date)], limit=1))
