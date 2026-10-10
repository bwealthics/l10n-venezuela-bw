# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency_pos. License LGPL-3.
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPosBsRate(TransactionCase):
    """Lectura y carga de la tasa Bs del día desde el POS.

    Se usa una moneda Bs de prueba (sin tasas previas) para no depender de
    los datos de la base: así "sin tasa", "con tasa hoy" y "fuera de ±15 %"
    son escenarios deterministas.
    """

    # Instante fijo DESPUÉS de la hora de corte (12:00 en Caracas = 16:00 UTC):
    # la regla "antes de las 9:15 vale la tasa de ayer" haría que el resultado
    # dependiera de la hora a la que corre la suite.
    freeze_time = freeze_time("2026-07-26 16:00:00")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # La compañía de prueba del common no es venezolana; la regla de pedir
        # la tasa del día se fuerza aquí para probarla.
        cls.startClassPatcher(patch.object(
            type(cls.env["res.company"]), "_l10n_ve_bs_requires_daily_rate",
            lambda self: True))
        cls.company = cls.env.company
        cls.bs = cls.env["res.currency"].create({
            "name": "XVB", "symbol": "Bs", "rounding": 0.01,
            "position": "after",
        })
        cls.company.l10n_ve_bs_currency_id = cls.bs
        cls.config = cls.env["pos.config"].create({"name": "POS Bs test"})
        cls.company.partner_id.tz = "America/Caracas"
        cls.today = cls.company._l10n_ve_bs_local_today()
        cls.Rate = cls.env["res.currency.rate"]

    def _rate_vals(self, name, value):
        return {
            "currency_id": self.bs.id,
            "company_id": self.company.root_id.id,
            "name": name,
            "company_rate": value,
        }

    def _open_session(self):
        """Sesión POS mínima para las pruebas de chatter/orden. Crearla
        depende de que la base de pruebas tenga plan contable y métodos de
        pago; si no los tiene, la prueba se omite en vez de fallar por algo
        ajeno a este módulo."""
        try:
            with self.env.cr.savepoint():
                return self.env["pos.session"].create({
                    "config_id": self.config.id,
                    "user_id": self.env.user.id})
        except Exception as error:  # noqa: BLE001 - se omite, no se oculta
            self.skipTest(f"No se pudo crear la sesión POS de prueba: {error}")

    def _today_records(self):
        return self.Rate.search([
            ("currency_id", "=", self.bs.id), ("name", "=", self.today)])

    # ── get ───────────────────────────────────────────────────────────────
    def test_get_sin_ninguna_tasa(self):
        info = self.config.l10n_ve_bs_get_today_rate()
        self.assertFalse(info["is_today"])
        self.assertEqual(info["rate"], 0.0)
        self.assertFalse(info["date"])
        self.assertEqual(info["currency"]["id"], self.bs.id)
        self.assertEqual(info["currency"]["name"], "XVB")
        self.assertEqual(info["currency"]["decimal_places"], 2)

    def test_get_con_tasa_de_hoy(self):
        self.Rate.create(self._rate_vals(self.today, 140.25))
        info = self.config.l10n_ve_bs_get_today_rate()
        self.assertTrue(info["is_today"])
        self.assertAlmostEqual(info["rate"], 140.25, places=4)
        self.assertEqual(info["date"], fields.Date.to_string(self.today))

    def test_get_tasa_de_ayer_vale_antes_de_la_hora_de_corte(self):
        # Antes de las 9:15 (Caracas) el BCV aún no publicó la tasa del día:
        # vale la de ayer, hasta el corte de hoy (13:15 UTC).
        yesterday = self.today - timedelta(days=1)
        self.Rate.create(self._rate_vals(yesterday, 100.0))
        with freeze_time("2026-07-26 12:00:00"):  # 08:00 en Caracas
            info = self.config.l10n_ve_bs_get_today_rate()
        self.assertTrue(info["is_today"])
        self.assertEqual(info["date"], fields.Date.to_string(yesterday))
        self.assertEqual(info["valid_until"], "2026-07-26 13:15:00")

    def test_get_tasa_de_ayer_no_cuenta_como_hoy(self):
        # Después de la hora de corte la de ayer se informa pero NO es "hoy".
        yesterday = self.today - timedelta(days=1)
        self.Rate.create(self._rate_vals(yesterday, 100.0))
        info = self.config.l10n_ve_bs_get_today_rate()
        self.assertFalse(info["is_today"])
        self.assertAlmostEqual(info["rate"], 100.0, places=4)
        self.assertEqual(info["date"], fields.Date.to_string(yesterday))

    def test_get_sin_moneda_bs(self):
        self.company.l10n_ve_bs_currency_id = False
        info = self.config.l10n_ve_bs_get_today_rate()
        self.assertFalse(info["currency"])
        self.assertTrue(info["is_today"])  # nada que pedir

    # ── set ───────────────────────────────────────────────────────────────
    def test_set_sin_tasa_previa(self):
        info = self.config.l10n_ve_bs_set_today_rate(140.5)
        self.assertTrue(info["is_today"])
        self.assertAlmostEqual(info["rate"], 140.5, places=4)
        record = self._today_records()
        self.assertEqual(len(record), 1)
        self.assertAlmostEqual(record.company_rate, 140.5, places=4)
        self.assertEqual(record.company_id, self.company.root_id)

    def test_set_dentro_de_tolerancia(self):
        self.Rate.create(self._rate_vals(self.today - timedelta(days=1), 100.0))
        info = self.config.l10n_ve_bs_set_today_rate(114.0)  # +14 %
        self.assertTrue(info["is_today"])
        self.assertAlmostEqual(info["rate"], 114.0, places=4)

    def test_set_fuera_de_15_por_ciento(self):
        self.Rate.create(self._rate_vals(self.today - timedelta(days=1), 100.0))
        for bad in (116.0, 84.0, 1000.0, 10.0):
            with self.assertRaises(UserError, msg=f"tasa {bad}"):
                self.config.l10n_ve_bs_set_today_rate(bad)
        self.assertFalse(self._today_records())

    def test_set_valores_invalidos(self):
        for bad in (0, -5, "abc", None, float("nan"), float("inf")):
            with self.assertRaises(UserError, msg=f"valor {bad!r}"):
                self.config.l10n_ve_bs_set_today_rate(bad)
        self.assertFalse(self._today_records())

    def test_set_no_pisa_tasa_existente(self):
        existing = self.Rate.create(self._rate_vals(self.today, 140.0))
        info = self.config.l10n_ve_bs_set_today_rate(999.0)
        self.assertAlmostEqual(info["rate"], 140.0, places=4)
        self.assertTrue(info["is_today"])
        self.assertAlmostEqual(existing.company_rate, 140.0, places=4)
        self.assertEqual(len(self._today_records()), 1)

    def test_set_sin_moneda_bs(self):
        self.company.l10n_ve_bs_currency_id = False
        with self.assertRaises(UserError):
            self.config.l10n_ve_bs_set_today_rate(140.0)

    def test_set_deja_constancia_en_la_sesion(self):
        session = self._open_session()
        before = len(session.message_ids)
        self.config.l10n_ve_bs_set_today_rate(140.0)
        self.assertGreater(len(session.message_ids), before)
        self.assertIn("140", session.message_ids[0].body)

    # ── pos.order ─────────────────────────────────────────────────────────
    def test_orden_sin_tasa_toma_la_ultima_vigente(self):
        self.Rate.create(self._rate_vals(self.today, 140.0))
        session = self._open_session()
        rate, rate_date = self.env["pos.order"]._l10n_ve_bs_default_rate({
            "session_id": session.id,
            "date_order": fields.Datetime.now(),
        })
        self.assertAlmostEqual(rate, 140.0, places=4)
        self.assertEqual(rate_date, self.today)

    def test_borrador_no_recibe_tasa_por_defecto(self):
        # La tasa de la fecha de creación de un borrador puede ser la de ayer;
        # no debe quedar fijada antes del cobro.
        self.Rate.create(self._rate_vals(self.today, 140.0))
        session = self._open_session()
        order = self.env["pos.order"].create({
            "session_id": session.id,
            "company_id": self.company.id,
            "state": "draft",
            "amount_tax": 0.0, "amount_total": 0.0,
            "amount_paid": 0.0, "amount_return": 0.0,
        })
        self.assertFalse(order.l10n_ve_bs_rate)
        order.write({"state": "paid"})
        self.assertAlmostEqual(order.l10n_ve_bs_rate, 140.0, places=4)
        self.assertEqual(order.l10n_ve_bs_rate_date, self.today)
