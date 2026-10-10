# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency_pos. License LGPL-3.
import math

from odoo import _, fields, models
from odoo.exceptions import UserError

# Una tasa digitada a mano en caja que se aleje más de este porcentaje de la
# última tasa conocida casi siempre es un typo (un dígito de más o de menos).
# El n8n que carga la tasa BCV cada mañana no pasa por aquí: este tope solo
# protege el camino de emergencia desde el POS.
L10N_VE_BS_RATE_TOLERANCE = 0.15


class PosConfig(models.Model):
    _inherit = "pos.config"

    def _l10n_ve_bs_currency_payload(self, bs):
        """Datos mínimos de la moneda Bs para que el POS formatee montos sin
        depender de que ``res.currency`` de Bs esté cargada en el cliente (el
        POS solo carga la moneda de la compañía)."""
        if not bs:
            return False
        return {
            "id": bs.id,
            "name": bs.name,
            "symbol": bs.symbol,
            "decimal_places": bs.decimal_places,
            "position": bs.position,
        }

    def l10n_ve_bs_get_today_rate(self):
        """Tasa Bs vigente para el POS y si YA existe la de hoy.

        ``is_today`` es lo que decide si el POS pide la tasa antes de cobrar.
        ``rate``/``date`` son la última tasa ≤ hoy (o 0.0/False si no hay
        ninguna): sirven de referencia visual para el cajero y de respaldo
        sin conexión, pero NO sustituyen a la de hoy cuando ``is_today`` es
        False (regla de negocio: no usar la tasa de otro día en silencio).
        Si la compañía no tiene moneda Bs, ``currency`` es False y el POS no
        pide nada; si Bs es la moneda de la compañía no hay nada que pedir
        (``is_today`` True, tasa 1.0).
        """
        self.ensure_one()
        # sudo: el cajero del POS no tiene ACL de lectura sobre las tasas ni
        # sobre las monedas inactivas, y aquí solo se leen para mostrarlas.
        company = self.company_id.sudo()
        bs = company.l10n_ve_bs_currency_id
        # Hoy en la zona de la compañía (la de la hora de corte), no la del
        # usuario del POS: así "hoy" y "antes de las 9:15" son lo mismo para
        # todas las cajas.
        today = company._l10n_ve_bs_local_today()
        rate, rate_date = company._l10n_ve_bs_rate_at(today)
        valid_until = False
        if not bs:
            is_today = True
        elif bs == company.currency_id:
            is_today = True
        else:
            # Fuera de VE no rige la regla de pedir la tasa del día.
            # "is_today" = la tasa vigente es ACEPTABLE ahora: la de hoy, o
            # la de ayer antes de la hora de corte (el BCV publica a las 9:00
            # y el n8n carga a las 9:15).
            is_today = (not company._l10n_ve_bs_requires_daily_rate()
                        or company._l10n_ve_bs_rate_acceptable_for(today))
            valid_until = fields.Datetime.to_string(
                company._l10n_ve_bs_rate_valid_until())
        return {
            "rate": rate,
            "date": fields.Date.to_string(rate_date) if rate_date else False,
            "is_today": is_today,
            # UTC ("YYYY-MM-DD HH:MM:SS"): el POS deja de imprimir Bs con esta
            # tasa pasado ese momento aunque la caja siga abierta.
            "valid_until": valid_until,
            "currency": self._l10n_ve_bs_currency_payload(bs),
        }

    def l10n_ve_bs_set_today_rate(self, rate):
        """Carga la tasa BCV de hoy digitada por el cajero.

        Es el camino de emergencia cuando el n8n de las 7 a.m. no la dejó
        cargada. Reglas:
        - Solo crea: si ya existe la tasa de hoy NO se pisa (otra caja pudo
          cargarla un instante antes); se devuelve la existente.
        - ``rate`` = Bs por 1 unidad de la moneda de la compañía, > 0 y a
          menos de ±15 % de la última tasa conocida (si la hay).
        - Queda constancia en el chatter de la sesión POS abierta.
        """
        self.ensure_one()
        company = self.company_id.sudo()
        bs = company.l10n_ve_bs_currency_id
        if not bs or bs == company.currency_id:
            raise UserError(_(
                "La compañía %s no tiene una moneda de referencia en Bs "
                "distinta de su moneda: no hay tasa que cargar.",
                company.display_name))
        today = company._l10n_ve_bs_local_today()
        if company._l10n_ve_bs_has_rate_on(today):
            # Carrera entre cajas, o el n8n la cargó mientras el cajero
            # digitaba: la tasa existente manda y no se pisa.
            return self.l10n_ve_bs_get_today_rate()

        try:
            rate = float(rate)
        except (TypeError, ValueError):
            raise UserError(_("La tasa debe ser un número."))
        if not math.isfinite(rate) or rate <= 0:
            raise UserError(_("La tasa debe ser mayor que cero."))
        last_rate, last_date = company._l10n_ve_bs_rate_at(today)
        if last_date and last_rate > 0:
            deviation = abs(rate - last_rate) / last_rate
            if deviation > L10N_VE_BS_RATE_TOLERANCE:
                raise UserError(_(
                    "La tasa %(rate)s se aleja %(pct).1f %% de la última tasa "
                    "cargada (%(last)s del %(date)s). El máximo permitido "
                    "desde el POS es %(max).0f %%; revise el valor digitado.",
                    rate=rate, pct=deviation * 100, last=last_rate,
                    date=last_date.strftime("%d-%m-%Y"),
                    max=L10N_VE_BS_RATE_TOLERANCE * 100))

        # Las tasas viven en la compañía raíz (ver res.currency._get_rates).
        # ``company_rate`` es el campo "unidades de esta moneda por 1 de la
        # moneda de la compañía" (Bs por 1 USD); Odoo 19 deriva de él el
        # ``rate`` técnico. sudo: el cajero no puede crear res.currency.rate.
        self.env["res.currency.rate"].sudo().create({
            "currency_id": bs.id,
            "company_id": company.root_id.id,
            "name": today,
            "company_rate": rate,
        })

        session = self.sudo().current_session_id
        if session:
            session.message_post(
                body=_(
                    "Tasa BCV del %(date)s cargada desde el POS por "
                    "%(user)s: 1 %(company_cur)s = %(rate)s %(bs)s.",
                    date=today.strftime("%d-%m-%Y"),
                    user=self.env.user.name,
                    company_cur=company.currency_id.name,
                    rate=rate, bs=bs.name),
                author_id=self.env.user.partner_id.id)
        return self.l10n_ve_bs_get_today_rate()
