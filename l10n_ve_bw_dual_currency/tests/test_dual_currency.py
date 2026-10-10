# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
"""Pruebas del núcleo de doble moneda: tasa congelada por asiento y Bs por apunte.

Las cifras esperadas están calculadas A MANO (con Decimal y redondeo
half-up), no con el propio módulo: una prueba que calcula su esperado con el
mismo código que verifica no detecta nada. Los casos con redondeo usan la tasa
611,37 (y no 610,5): con 610,5 todo precio de centavos impares cae justo en
«.5» de céntimo y el resultado dependería del desempate del flotante.

`DualCurrencyCommon` también lo importan test_report y test_legal_books, para
no repetir la configuración de monedas, tasas e impuestos.
"""
from datetime import date
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

# (fecha, Bs por 1 unidad de la moneda de la compañía). 2025-01-15 queda
# ANTES de la primera tasa a propósito: es la fecha «sin tasa» de las pruebas.
# 2026-07-29 no tiene tasa propia: la última anterior es la del 2026-07-27.
RATES = (
    ("2025-06-10", 400.0),
    ("2025-12-15", 450.0),
    ("2026-07-24", 600.0),
    ("2026-07-25", 610.5),
    ("2026-07-27", 611.37),
    ("2026-08-01", 650.0),
)
NO_RATE_DATE = "2025-01-15"


@tagged("post_install", "-at_install")
class DualCurrencyCommon(AccountTestInvoicingCommon):
    """Configuración compartida: VES activa, tasas, impuestos y un cliente."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # La compañía de prueba del common no es venezolana; la regla de pedir
        # la tasa del día se fuerza aquí para probarla.
        cls.startClassPatcher(patch.object(
            type(cls.env["res.company"]), "_l10n_ve_bs_requires_daily_rate",
            lambda self: True))
        cls.company = cls.company_data["company"]
        cls.company.partner_id.tz = "America/Caracas"
        cls.bs = cls.env.ref("base.VES")
        cls.bs.active = True
        # Las tasas VES previas (si la base de pruebas trae alguna) se quitan
        # para que «antes de toda tasa» sea una fecha real. Se desconfigura la
        # moneda Bs de las compañías mientras tanto: el bloqueo de borrado de
        # tasas en uso solo mira compañías con esa moneda.
        cls.env["res.company"].search([]).write(
            {"l10n_ve_bs_currency_id": False})
        cls.bs.rate_ids.unlink()
        cls.rate_by_date = {}
        for day, value in RATES:
            cls.rate_by_date[day] = cls._create_bs_rate(day, value)
        cls.company.l10n_ve_bs_currency_id = cls.bs

        tax_values = {
            "amount_type": "percent",
            "company_id": cls.company.id,
        }
        cls.tax_iva16 = cls.env["account.tax"].create({
            **tax_values, "name": "IVA 16% (ventas) — doble moneda",
            "amount": 16.0, "type_tax_use": "sale"})
        cls.tax_exento = cls.env["account.tax"].create({
            **tax_values, "name": "Exento (ventas) — doble moneda",
            "amount": 0.0, "type_tax_use": "sale"})
        cls.tax_iva16_compras = cls.env["account.tax"].create({
            **tax_values, "name": "IVA 16% (compras) — doble moneda",
            "amount": 16.0, "type_tax_use": "purchase"})
        cls.partner = cls.env["res.partner"].create({
            "name": "Cliente de prueba doble moneda",
            "lang": "en_US",
        })

    @classmethod
    def _create_bs_rate(cls, day, value, company=True):
        """Tasa Bs de un día (value = Bs por 1 unidad de la moneda base)."""
        return cls.env["res.currency.rate"].create({
            "name": day,
            "currency_id": cls.bs.id,
            "rate": value,
            "company_id": cls.company.id if company else False,
        })

    # ------------------------------------------------------------------
    # Ayudas
    # ------------------------------------------------------------------
    @classmethod
    def _invoice(cls, invoice_date, lines=None, move_type="out_invoice",
                 post=True, **vals):
        """Factura de prueba. `lines` = [(precio, impuesto), ...].

        Es classmethod para poder usarla también al preparar la clase.

        Por defecto (cliente): 100 con IVA 16 % y 50 exentos, que en USD dan
        base 150, IVA 16 y total 166.
        """
        purchase = move_type.startswith("in_")
        account = cls.company_data[
            "default_account_expense" if purchase else "default_account_revenue"]
        if lines is None:
            lines = ([(100.0, cls.tax_iva16_compras)] if purchase else
                     [(100.0, cls.tax_iva16), (50.0, cls.tax_exento)])
        move = cls.env["account.move"].create({
            "move_type": move_type,
            "partner_id": cls.partner.id,
            "invoice_date": fields.Date.to_date(invoice_date),
            "invoice_line_ids": [
                Command.create({
                    "name": "Línea de prueba",
                    "quantity": 1.0,
                    "price_unit": price,
                    "account_id": account.id,
                    "tax_ids": [Command.set(tax.ids)],
                })
                for price, tax in lines
            ],
            **vals,
        })
        if post:
            move.action_post()
        return move

    def assertBs(self, value, expected, msg=None):
        """Igualdad de montos Bs a la precisión de la moneda (sin flotantes)."""
        self.assertEqual(
            self.bs.compare_amounts(value, expected), 0,
            msg or "%s != %s" % (value, expected))

    @staticmethod
    def _lines(move, display_type):
        return move.line_ids.filtered(lambda l: l.display_type == display_type)

    @classmethod
    def _entry(cls, entry_date, lines):
        """Asiento manual posteado. `lines` = [(cuenta, debe, haber, extra)]."""
        move = cls.env["account.move"].create({
            "move_type": "entry",
            "journal_id": cls.company_data["default_journal_misc"].id,
            "date": fields.Date.to_date(entry_date),
            "line_ids": [
                Command.create({
                    "account_id": account.id,
                    "debit": debit,
                    "credit": credit,
                    "name": "prueba",
                    **(extra[0] if extra else {}),
                })
                for account, debit, credit, *extra in lines
            ],
        })
        move.action_post()
        return move


@tagged("post_install", "-at_install")
class TestDualCurrency(DualCurrencyCommon):

    # --- Conversión por asiento -----------------------------------------

    def test_invoice_usd_vat_and_exempt(self):
        """Base 150 + IVA 16 = 166 USD a 610,5: sin residuo de redondeo."""
        inv = self._invoice("2026-07-25")
        self.assertAlmostEqual(inv.l10n_ve_bs_rate, 610.5, places=6)
        self.assertEqual(inv.l10n_ve_bs_rate_date, date(2026, 7, 25))
        self.assertFalse(inv.l10n_ve_bs_rate_missing)

        taxed, exempt = self._lines(inv, "product").sorted("price_unit",
                                                           reverse=True)
        # El impuesto exento al 0 % puede generar o no una línea de impuesto en
        # cero: se suman las que haya en vez de asumir una sola.
        tax = self._lines(inv, "tax")
        receivable = self._lines(inv, "payment_term")
        self.assertBs(taxed.l10n_ve_balance_bs, -61050.0)
        self.assertBs(exempt.l10n_ve_balance_bs, -30525.0)
        self.assertBs(sum(tax.mapped("l10n_ve_balance_bs")), -9768.0)
        self.assertBs(receivable.l10n_ve_balance_bs, 101343.0)
        # Debe/Haber Bs salen del signo del saldo.
        self.assertBs(receivable.l10n_ve_debit_bs, 101343.0)
        self.assertBs(receivable.l10n_ve_credit_bs, 0.0)
        self.assertBs(taxed.l10n_ve_credit_bs, 61050.0)
        self.assertBs(taxed.l10n_ve_debit_bs, 0.0)
        # El asiento suma cero en Bs y no hizo falta recuadrar.
        self.assertBs(sum(inv.line_ids.mapped("l10n_ve_balance_bs")), 0.0)
        self.assertBs(sum(inv.line_ids.mapped("l10n_ve_bs_adjustment")), 0.0)
        # Totales del documento: el total es base + IVA.
        self.assertBs(inv.l10n_ve_amount_untaxed_bs, 91575.0)
        self.assertBs(inv.l10n_ve_amount_tax_bs, 9768.0)
        self.assertBs(inv.l10n_ve_amount_total_bs, 101343.0)
        self.assertBs(
            inv.l10n_ve_amount_total_bs,
            inv.l10n_ve_amount_untaxed_bs + inv.l10n_ve_amount_tax_bs)
        self.assertBs(inv.l10n_ve_amount_residual_bs, 101343.0)
        self.assertBs(inv.l10n_ve_bs_adjustment, 0.0)
        # Columnas Bs de la línea: subtotal, total con IVA y precio unitario.
        self.assertBs(taxed.l10n_ve_price_subtotal_bs, 61050.0)
        self.assertBs(taxed.l10n_ve_price_total_bs, 70818.0)
        self.assertBs(exempt.l10n_ve_price_subtotal_bs, 30525.0)
        self.assertBs(exempt.l10n_ve_price_total_bs, 30525.0)
        self.assertBs(taxed.l10n_ve_price_unit_bs, 61050.0)

    def test_rounding_residual_goes_to_receivable(self):
        """El residuo de redondeo (−0,01 Bs) lo absorbe la línea de cobro.

        10,01 + IVA 1,60 + exento 5,03 = 16,64 USD a 611,37. Cada línea
        redondeada da -6119,81, -3075,19, -978,19 y 10173,20: suman +0,01, y
        ese centavo sale de la cuenta por cobrar (10173,19). Es un caso con
        residuo real (la prueba de 150 USD no lo tiene).
        """
        inv = self._invoice("2026-07-27", lines=[
            (10.01, self.tax_iva16), (5.03, self.tax_exento)])
        self.assertAlmostEqual(inv.l10n_ve_bs_rate, 611.37, places=6)
        self.assertEqual(inv.l10n_ve_bs_rate_date, date(2026, 7, 27))

        products = {l.price_unit: l for l in self._lines(inv, "product")}
        tax = self._lines(inv, "tax")
        receivable = self._lines(inv, "payment_term")
        self.assertBs(products[10.01].l10n_ve_balance_bs, -6119.81)
        self.assertBs(products[5.03].l10n_ve_balance_bs, -3075.19)
        self.assertBs(sum(tax.mapped("l10n_ve_balance_bs")), -978.19)
        self.assertBs(receivable.l10n_ve_balance_bs, 10173.19)
        self.assertBs(receivable.l10n_ve_bs_adjustment, -0.01)
        for line in list(products.values()) + list(tax):
            self.assertBs(line.l10n_ve_bs_adjustment, 0.0)
            # Las líneas sin ajuste son exactamente round(saldo × tasa).
            self.assertBs(
                line.l10n_ve_balance_bs,
                self.bs.round(line.balance * inv.l10n_ve_bs_rate))
        self.assertBs(sum(inv.line_ids.mapped("l10n_ve_balance_bs")), 0.0)

        self.assertBs(inv.l10n_ve_bs_adjustment, -0.01)
        self.assertBs(inv.l10n_ve_amount_untaxed_bs, 9195.0)
        self.assertBs(inv.l10n_ve_amount_tax_bs, 978.19)
        self.assertBs(inv.l10n_ve_amount_total_bs, 10173.19)
        self.assertBs(
            inv.l10n_ve_amount_total_bs,
            inv.l10n_ve_amount_untaxed_bs + inv.l10n_ve_amount_tax_bs)
        # La suma de los importes Bs de las líneas cuadra con la base Bs.
        self.assertBs(
            sum(self._lines(inv, "product").mapped("l10n_ve_price_subtotal_bs")),
            inv.l10n_ve_amount_untaxed_bs)

    def test_vendor_bill_in_ves(self):
        """Factura de proveedor en VES: el Bs de cada apunte es su monto exacto."""
        bill = self._invoice(
            "2026-07-25", move_type="in_invoice",
            lines=[(1000.50, self.tax_iva16_compras)],
            currency_id=self.bs.id)
        self.assertEqual(bill.currency_id, self.bs)
        # IVA 16 % de 1000,50 = 160,08; total 1160,58.
        for line in bill.line_ids:
            self.assertBs(
                line.l10n_ve_balance_bs, line.amount_currency,
                "El Bs de una línea en VES debe ser su amount_currency")
            self.assertBs(line.l10n_ve_bs_adjustment, 0.0)
        self.assertBs(bill.l10n_ve_amount_untaxed_bs, 1000.50)
        self.assertBs(bill.l10n_ve_amount_tax_bs, 160.08)
        self.assertBs(bill.l10n_ve_amount_total_bs, 1160.58)
        # En un documento ya en Bs el saldo Bs es el saldo del documento.
        self.assertBs(bill.l10n_ve_amount_residual_bs, bill.amount_residual)
        # Una factura emitida en Bs no se duplica: el PDF no imprime bloque Bs.
        self.assertEqual(bill._l10n_ve_bs_amounts(), {})
        self.assertNotIn("l10n_ve_bs", bill.tax_totals)

    def test_mixed_entry_vesline_and_usd_lines(self):
        """Asiento mixto (línea VES + líneas USD): el ajuste va a la línea USD.

        Línea VES: 100 USD con amount_currency 61.000 Bs. Líneas USD: cobrar
        60 y ingreso 40, que a 610,5 son 36.630 y 24.420 Bs. Descuadre real de
        50 Bs (61.000 contra 61.050): la línea VES queda exacta y el cuadre
        lo absorbe la cuenta por cobrar, que es la línea de cobro/pago.
        """
        receivable = self.company_data["default_account_receivable"]
        revenue = self.company_data["default_account_revenue"]
        # Cualquier cuenta que no sea cobrar/pagar sirve para la línea en VES.
        ves_account = self.company_data["default_account_deferred_expense"]
        partner = {"partner_id": self.partner.id}
        move = self._entry("2026-07-25", [
            (ves_account, 100.0, 0.0, {
                "currency_id": self.bs.id, "amount_currency": 61000.0,
                **partner}),
            (receivable, 0.0, 60.0, partner),
            (revenue, 0.0, 40.0, partner),
        ])
        line_ves, line_rec, line_rev = move.line_ids.sorted("id")
        self.assertAlmostEqual(move.l10n_ve_bs_rate, 610.5, places=6)
        self.assertFalse(move.l10n_ve_bs_rate_missing)
        self.assertBs(line_ves.l10n_ve_balance_bs, 61000.0)
        self.assertBs(line_ves.l10n_ve_bs_adjustment, 0.0)
        self.assertBs(line_rev.l10n_ve_balance_bs, -24420.0)
        self.assertBs(line_rev.l10n_ve_bs_adjustment, 0.0)
        # -36.630 de la tasa + 50 de recuadre.
        self.assertBs(line_rec.l10n_ve_balance_bs, -36580.0)
        self.assertBs(line_rec.l10n_ve_bs_adjustment, 50.0)
        self.assertBs(move.l10n_ve_bs_adjustment, 50.0)
        self.assertBs(sum(move.line_ids.mapped("l10n_ve_balance_bs")), 0.0)

    def test_entry_without_rate_is_marked_and_not_balanced(self):
        """Sin tasa (fecha anterior a toda tasa) no se inventan bolívares."""
        receivable = self.company_data["default_account_receivable"]
        revenue = self.company_data["default_account_revenue"]
        partner = {"partner_id": self.partner.id}
        move = self._entry(NO_RATE_DATE, [
            (receivable, 100.0, 0.0, partner),
            (revenue, 0.0, 100.0, partner),
        ])
        self.assertTrue(move.l10n_ve_bs_rate_missing)
        self.assertEqual(move.l10n_ve_bs_rate, 0.0)
        self.assertFalse(move.l10n_ve_bs_rate_date)
        for line in move.line_ids:
            self.assertBs(line.l10n_ve_balance_bs, 0.0)
            self.assertBs(line.l10n_ve_bs_adjustment, 0.0)
        self.assertBs(move.l10n_ve_bs_adjustment, 0.0)

    def test_invoice_without_rate(self):
        """Factura sin tasa: botón bloqueado, _post la deja marcada, sin bloque Bs."""
        inv = self._invoice(NO_RATE_DATE, post=False)
        with self.assertRaises(RedirectWarning):
            inv.action_post()
        inv._post()
        self.assertEqual(inv.state, "posted")
        self.assertTrue(inv.l10n_ve_bs_rate_missing)
        self.assertBs(inv.l10n_ve_amount_total_bs, 0.0)
        self.assertEqual(inv._l10n_ve_bs_amounts(), {})
        self.assertNotIn("l10n_ve_bs", inv.tax_totals)

    def test_bs_equal_company_currency(self):
        """Si el bolívar es la moneda de la compañía, Bs = saldo, a tasa 1."""
        self.company.l10n_ve_bs_currency_id = self.company.currency_id
        inv = self._invoice("2026-07-25")
        self.assertEqual(inv.l10n_ve_bs_rate, 1.0)
        self.assertFalse(inv.l10n_ve_bs_rate_missing)
        for line in inv.line_ids:
            self.assertAlmostEqual(line.l10n_ve_balance_bs, line.balance, places=2)
        self.assertEqual(inv._l10n_ve_bs_amounts(), {})
        self.assertAlmostEqual(
            inv.l10n_ve_amount_total_bs, inv.amount_total, places=2)

    # --- Tasa del documento ---------------------------------------------

    def test_credit_note_inherits_rate(self):
        """La NC por reversión usa la tasa de la factura, no la de su fecha."""
        inv = self._invoice("2026-07-25")
        # Aun editando la tasa de la tabla, el asiento ya confirmado no se mueve.
        self.rate_by_date["2026-07-25"].rate = 700.0
        inv.invalidate_recordset()
        self.assertAlmostEqual(inv.l10n_ve_bs_rate, 610.5, places=6)
        self.assertBs(inv.l10n_ve_amount_total_bs, 101343.0)

        # El 2026-08-01 la tabla dice 650: la NC debe ignorarla.
        credit = self._reverse_invoice(
            inv, date=fields.Date.to_date("2026-08-01"))
        self.assertEqual(credit.reversed_entry_id, inv)
        self.assertAlmostEqual(credit.l10n_ve_bs_rate, 610.5, places=6)
        self.assertEqual(credit.l10n_ve_bs_rate_date, date(2026, 7, 25))
        credit.action_post()
        self.assertAlmostEqual(credit.l10n_ve_bs_rate, 610.5, places=6)
        self.assertBs(credit.l10n_ve_amount_total_bs,
                      inv.l10n_ve_amount_total_bs)
        # La NC total anula la factura también en Bs.
        receivable = (inv | credit).line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable")
        self.assertBs(sum(receivable.mapped("l10n_ve_balance_bs")), 0.0)

    # --- Hora de corte (9:15 Caracas) --------------------------------------

    def test_cutoff_before_uses_previous_day_rate(self):
        """Antes de las 9:15 una factura de HOY se confirma con la tasa de
        ayer (el 2026-07-26 no tiene tasa; la del 25 es 610,5)."""
        with freeze_time("2026-07-26 12:00:00"):  # 08:00 en Caracas
            self.assertTrue(
                self.company._l10n_ve_bs_rate_acceptable_for(date(2026, 7, 26)))
            inv = self._invoice("2026-07-26")
        self.assertEqual(inv.state, "posted")
        self.assertAlmostEqual(inv.l10n_ve_bs_rate, 610.5, places=6)
        self.assertEqual(inv.l10n_ve_bs_rate_date, date(2026, 7, 25))

    def test_cutoff_after_requires_today_rate(self):
        """Después de las 9:15 se exige la tasa del día."""
        with freeze_time("2026-07-26 14:00:00"):  # 10:00 en Caracas
            self.assertFalse(
                self.company._l10n_ve_bs_rate_acceptable_for(date(2026, 7, 26)))
            draft = self._invoice("2026-07-26", post=False)
            with self.assertRaises(RedirectWarning):
                draft.action_post()

    def test_cutoff_only_applies_to_today(self):
        """Para una fecha que no es hoy se exige la tasa exacta de esa fecha,
        aunque sea temprano."""
        with freeze_time("2026-07-28 12:00:00"):  # 08:00 del 28 en Caracas
            self.assertFalse(
                self.company._l10n_ve_bs_rate_acceptable_for(date(2026, 7, 26)))
            self.assertTrue(
                self.company._l10n_ve_bs_rate_acceptable_for(date(2026, 7, 28)))

    def test_cutoff_is_configurable(self):
        with freeze_time("2026-07-26 12:00:00"):  # 08:00 en Caracas
            self.company.l10n_ve_bs_rate_cutoff = 7.0  # corte a las 7:00
            self.assertFalse(
                self.company._l10n_ve_bs_rate_acceptable_for(date(2026, 7, 26)))

    def test_posted_credit_note_frozen_when_origin_reposted(self):
        """Regresión: re-postear la factura de origen con otra fecha (otra
        tasa) no debe re-tasar una nota de crédito ya confirmada."""
        inv = self._invoice("2026-07-25")
        credit = self._reverse_invoice(
            inv, date=fields.Date.to_date("2026-08-01"))
        credit.action_post()
        self.env.flush_all()
        total_before = credit.l10n_ve_amount_total_bs
        # La factura de origen se corrige: borrador, nueva fecha, confirmar.
        inv.button_draft()
        inv.invoice_date = fields.Date.to_date("2026-08-01")
        inv.action_post()
        self.env.flush_all()
        self.assertAlmostEqual(inv.l10n_ve_bs_rate, 650.0, places=6)
        credit.invalidate_recordset()
        self.assertAlmostEqual(credit.l10n_ve_bs_rate, 610.5, places=6)
        self.assertBs(credit.l10n_ve_amount_total_bs, total_before)

    def test_posted_rate_frozen_on_same_value_write(self):
        """Regresión: reescribir con el mismo valor un campo del que depende la
        tasa (la tasa manual, permitido en confirmados si no cambia; Odoo marca
        `modified` sin comparar) no re-tasa un asiento confirmado aunque la
        tabla haya cambiado."""
        inv = self._invoice("2026-07-25")
        self.env.flush_all()
        self.rate_by_date["2026-07-25"].rate = 700.0
        inv.write({"l10n_ve_bs_rate_override": 0.0})
        self.env.flush_all()
        inv.invalidate_recordset()
        self.assertAlmostEqual(inv.l10n_ve_bs_rate, 610.5, places=6)
        self.assertBs(inv.l10n_ve_amount_total_bs, 101343.0)

    def test_missing_rate_without_create_access(self):
        """Sin permiso para crear tasas, el aviso no ofrece un botón que
        llevaría a AccessError: indica la tasa manual."""
        draft = self._invoice("2026-07-29", post=False)
        with patch.object(type(self.env["res.currency.rate"]), "has_access",
                          lambda self, operation: operation != "create"):
            with self.assertRaises(UserError) as ctx:
                draft.action_post()
        self.assertNotIsInstance(ctx.exception, RedirectWarning)
        self.assertIn("Tasa Bs manual", str(ctx.exception))

    def test_credit_note_post_does_not_ask_for_rate(self):
        """Una NC en un día sin tasa se confirma: hereda la del origen."""
        inv = self._invoice("2026-07-25")
        credit = self._reverse_invoice(
            inv, date=fields.Date.to_date("2026-07-29"))
        self.assertFalse(
            self.company._l10n_ve_bs_has_rate_on(date(2026, 7, 29)))
        credit.action_post()  # no debe lanzar RedirectWarning
        self.assertEqual(credit.state, "posted")
        self.assertAlmostEqual(credit.l10n_ve_bs_rate, 610.5, places=6)

    def test_post_without_exact_rate(self):
        """Botón: pide la tasa. _post() directo: usa la última y guarda su fecha."""
        inv = self._invoice("2026-07-29", post=False)
        with self.assertRaises(RedirectWarning) as ctx:
            inv.action_post()
        message, action = ctx.exception.args[0], ctx.exception.args[1]
        self.assertIn("29-07-2026", message)
        self.assertEqual(action["res_model"], "res.currency.rate")
        self.assertEqual(action["context"]["default_name"], "2026-07-29")
        self.assertEqual(inv.state, "draft")

        # El contexto de salto permite confirmar desde el botón.
        inv.with_context(l10n_ve_bs_skip_rate_check=True).action_post()
        self.assertEqual(inv.state, "posted")
        self.assertAlmostEqual(inv.l10n_ve_bs_rate, 611.37, places=6)
        self.assertEqual(inv.l10n_ve_bs_rate_date, date(2026, 7, 27))

        # Flujos automáticos: _post() no se bloquea, usa la última tasa.
        other = self._invoice("2026-07-29", post=False)
        other._post()
        self.assertEqual(other.state, "posted")
        self.assertAlmostEqual(other.l10n_ve_bs_rate, 611.37, places=6)
        self.assertEqual(other.l10n_ve_bs_rate_date, date(2026, 7, 27))
        self.assertFalse(other.l10n_ve_bs_rate_missing)

    def test_mass_validation_asks_for_rate(self):
        """La confirmación masiva de la lista tampoco usa otra tasa en silencio."""
        inv = self._invoice("2026-07-29", post=False)
        wizard = self.env["validate.account.move"].with_context(
            active_model="account.move", active_ids=inv.ids).create({})
        with self.assertRaises(RedirectWarning):
            wizard.validate_move()
        self.assertEqual(inv.state, "draft")

    def test_manual_override(self):
        """La tasa manual se respeta, exime de la tasa del día y se limpia."""
        inv = self._invoice(
            "2026-07-29", post=False, l10n_ve_bs_rate_override=700.0)
        self.assertAlmostEqual(inv.l10n_ve_bs_rate, 700.0, places=6)
        self.assertFalse(inv.l10n_ve_bs_rate_missing)
        # 2026-07-29 no tiene tasa y aun así se confirma: hay tasa manual.
        inv.action_post()
        self.assertEqual(inv.state, "posted")
        self.assertAlmostEqual(inv.l10n_ve_bs_rate, 700.0, places=6)
        self.assertBs(inv.l10n_ve_amount_total_bs, 116200.0)  # 166 × 700

        # Posteado: no se cambia, pero reescribir el mismo valor es inocuo.
        with self.assertRaises(UserError) as ctx:
            inv.write({"l10n_ve_bs_rate_override": 800.0})
        self.assertIn("Tasa Bs manual", str(ctx.exception))
        inv.write({"l10n_ve_bs_rate_override": 700.0})

        # El botón del banner vuelve a la tabla en un borrador.
        draft = self._invoice(
            "2026-07-25", post=False, l10n_ve_bs_rate_override=700.0)
        self.assertAlmostEqual(draft.l10n_ve_bs_rate, 700.0, places=6)
        draft.action_l10n_ve_bs_refresh_rate()
        self.assertEqual(draft.l10n_ve_bs_rate_override, 0.0)
        self.assertAlmostEqual(draft.l10n_ve_bs_rate, 610.5, places=6)

    def test_stale_draft_rate_and_post_refresh(self):
        """Borrador con la tasa de ayer: avisa, y al confirmar congela la nueva."""
        draft = self._invoice("2026-08-02", post=False)
        self.assertAlmostEqual(draft.l10n_ve_bs_rate, 650.0, places=6)
        self.assertEqual(draft.l10n_ve_bs_rate_date, date(2026, 8, 1))
        self.assertFalse(draft.l10n_ve_bs_rate_outdated)

        # n8n carga la tasa del día DESPUÉS de crear el borrador.
        self._create_bs_rate("2026-08-02", 660.0)
        draft.invalidate_recordset(["l10n_ve_bs_rate_outdated"])
        self.assertTrue(draft.l10n_ve_bs_rate_outdated)

        # Confirmar congela la tasa vigente en ese momento.
        draft.action_post()
        self.assertAlmostEqual(draft.l10n_ve_bs_rate, 660.0, places=6)
        self.assertEqual(draft.l10n_ve_bs_rate_date, date(2026, 8, 2))
        self.assertBs(draft.l10n_ve_amount_total_bs, 109560.0)  # 166 × 660

    def test_refresh_rate_button(self):
        """«Recalcular tasa» trae la tasa nueva a un borrador desactualizado."""
        draft = self._invoice("2026-08-02", post=False)
        self.assertAlmostEqual(draft.l10n_ve_bs_rate, 650.0, places=6)
        self._create_bs_rate("2026-08-02", 660.0)
        draft.action_l10n_ve_bs_refresh_rate()
        self.assertAlmostEqual(draft.l10n_ve_bs_rate, 660.0, places=6)
        self.assertEqual(draft.l10n_ve_bs_rate_date, date(2026, 8, 2))
        draft.invalidate_recordset(["l10n_ve_bs_rate_outdated"])
        self.assertFalse(draft.l10n_ve_bs_rate_outdated)

    # --- Tabla de tasas -------------------------------------------------

    def test_unlink_rate_used_by_posted_move(self):
        """No se borra una tasa que respalda un asiento posteado."""
        self._invoice("2026-07-24")
        rate = self.rate_by_date["2026-07-24"]
        with self.assertRaises(UserError):
            rate.unlink()
        self.assertTrue(rate.exists())

    def test_unlink_rate_unused_or_manual(self):
        """Una tasa sin asientos se borra; una con solo tasa manual, también."""
        unused = self._create_bs_rate("2026-09-01", 700.0)
        unused.unlink()
        self.assertFalse(unused.exists())

        # La factura con tasa manual no depende de la tabla.
        self._invoice("2026-08-01", l10n_ve_bs_rate_override=700.0)
        manual = self.rate_by_date["2026-08-01"]
        manual.unlink()
        self.assertFalse(manual.exists())

    def test_company_rate_helpers(self):
        company = self.company
        self.assertEqual(
            company._l10n_ve_bs_rate_at(date(2026, 7, 25))[1],
            date(2026, 7, 25))
        rate, rate_date = company._l10n_ve_bs_rate_at(date(2026, 7, 29))
        self.assertAlmostEqual(rate, 611.37, places=6)
        self.assertEqual(rate_date, date(2026, 7, 27))
        self.assertEqual(
            company._l10n_ve_bs_rate_at(date(2025, 1, 15)), (0.0, False))
        self.assertTrue(company._l10n_ve_bs_has_rate_on(date(2026, 7, 24)))
        self.assertFalse(company._l10n_ve_bs_has_rate_on(date(2026, 7, 29)))

        # La versión por lote da lo mismo que la búsqueda de una fecha.
        dates = {date(2025, 1, 15), date(2025, 6, 10), date(2025, 12, 31),
                 date(2026, 7, 24), date(2026, 7, 29), date(2026, 9, 30)}
        batch = company._l10n_ve_bs_rates_at(dates)
        self.assertEqual(set(batch), dates)
        for day in dates:
            self.assertEqual(batch[day], company._l10n_ve_bs_rate_at(day), day)
        single = company._l10n_ve_bs_rates_at({date(2026, 7, 29)})
        self.assertEqual(
            single, {date(2026, 7, 29): company._l10n_ve_bs_rate_at(
                date(2026, 7, 29))})

    def test_company_rate_prefers_company_over_global(self):
        """Igual que el core: la tasa de la compañía gana a la global, aunque
        la global sea más reciente."""
        self._create_bs_rate("2026-07-26", 999.0, company=False)
        company = self.company
        rate, rate_date = company._l10n_ve_bs_rate_at(date(2026, 7, 26))
        self.assertAlmostEqual(rate, 610.5, places=6)
        self.assertEqual(rate_date, date(2026, 7, 25))
        batch = company._l10n_ve_bs_rates_at(
            {date(2026, 7, 26), date(2026, 7, 27)})
        self.assertEqual(batch[date(2026, 7, 26)][1], date(2026, 7, 25))
        self.assertEqual(batch[date(2026, 7, 27)][1], date(2026, 7, 27))

    def test_company_rate_helpers_without_bs_or_bs_is_company(self):
        company = self.company
        company.l10n_ve_bs_currency_id = company.currency_id
        self.assertEqual(
            company._l10n_ve_bs_rate_at(date(2026, 7, 29)),
            (1.0, date(2026, 7, 29)))
        self.assertEqual(
            company._l10n_ve_bs_rates_at({date(2026, 7, 29), date(2026, 7, 30)}),
            {date(2026, 7, 29): (1.0, date(2026, 7, 29)),
             date(2026, 7, 30): (1.0, date(2026, 7, 30))})
        self.assertTrue(company._l10n_ve_bs_has_rate_on(date(2026, 7, 29)))

        company.l10n_ve_bs_currency_id = False
        self.assertEqual(
            company._l10n_ve_bs_rate_at(date(2026, 7, 29)), (0.0, False))
        self.assertTrue(company._l10n_ve_bs_has_rate_on(date(2026, 7, 29)))

    # --- Pagos ----------------------------------------------------------

    def test_payment_amount_bs(self):
        """Monto Bs del pago: los Bs de su línea de liquidez a SU tasa."""
        inv = self._invoice("2026-07-25")
        payment = self._register_payment(inv, payment_date="2026-08-01")
        self.assertAlmostEqual(payment.l10n_ve_bs_rate, 650.0, places=6)
        self.assertBs(payment.l10n_ve_amount_bs, 107900.0)  # 166 × 650
        # La factura pagada no tiene saldo en Bs.
        self.assertBs(inv.l10n_ve_amount_residual_bs, 0.0)

    def test_payment_in_ves_amount_bs(self):
        """Un pago expresado en VES es su monto, tal cual."""
        payment = self.env["account.payment"].create({
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": self.partner.id,
            "amount": 5000.0,
            "currency_id": self.bs.id,
            "date": "2026-07-25",
            "journal_id": self.company_data["default_journal_bank"].id,
        })
        self.assertBs(payment.l10n_ve_amount_bs, 5000.0)

    def test_partial_payment_residual_bs(self):
        """El saldo Bs es la parte proporcional del total Bs que queda por cobrar."""
        inv = self._invoice("2026-07-25")
        self._register_payment(inv, amount=50.0, payment_date="2026-08-01")
        self.assertAlmostEqual(inv.amount_residual, 116.0, places=2)
        self.assertBs(inv.l10n_ve_amount_residual_bs, 70818.0)  # 116 × 610,5
        amounts = inv._l10n_ve_bs_amounts()
        self.assertTrue(amounts["show_residual"])
        self.assertBs(amounts["residual"], 70818.0)

    # --- Widget de totales y datos del PDF --------------------------------

    def test_tax_totals_bs(self):
        inv = self._invoice("2026-07-25")
        totals = inv.tax_totals
        self.assertIn("l10n_ve_bs", totals)
        bs_totals = totals["l10n_ve_bs"]
        self.assertEqual(bs_totals["currency_id"], self.bs.id)
        self.assertAlmostEqual(bs_totals["rate"], 610.5, places=6)
        self.assertEqual(bs_totals["rate_date"], "2026-07-25")
        self.assertBs(bs_totals["base_amount"], 91575.0)
        self.assertBs(bs_totals["tax_amount"], 9768.0)
        self.assertBs(bs_totals["total_amount"], 101343.0)
        self.assertBs(bs_totals["residual_amount"], 101343.0)
        # El primer subtotal es la base imponible Bs.
        first = totals["subtotals"][0]["name"]
        self.assertBs(bs_totals["subtotals"][first], 91575.0)
        # Cada grupo de impuesto del core trae su columna Bs.
        core_groups = {
            str(group["id"])
            for subtotal in totals["subtotals"]
            for group in subtotal["tax_groups"]
        }
        self.assertTrue(core_groups <= set(bs_totals["tax_groups"]))
        self.assertBs(
            sum(g["tax_amount"] for g in bs_totals["tax_groups"].values()),
            9768.0)

    def test_bs_amounts_dual(self):
        inv = self._invoice("2026-07-25")
        amounts = inv._l10n_ve_bs_amounts()
        self.assertTrue(amounts["dual"])
        self.assertEqual(amounts["currency"], self.bs)
        self.assertAlmostEqual(amounts["rate"], 610.5, places=6)
        self.assertEqual(amounts["date"], date(2026, 7, 25))
        self.assertEqual(amounts["rate_date"], date(2026, 7, 25))
        self.assertBs(amounts["untaxed"], 91575.0)
        self.assertBs(amounts["tax"], 9768.0)
        self.assertBs(amounts["total"], 101343.0)
        # Recién emitida y sin cobrar: el saldo no aporta nada.
        self.assertFalse(amounts["show_residual"])
        groups = amounts["tax_groups"]
        self.assertTrue(groups)
        for group in groups:
            self.assertEqual(
                set(group),
                {"tax_group_id", "name", "base", "tax", "base_bs", "tax_bs"})
        self.assertBs(sum(g["tax_bs"] for g in groups), 9768.0)
        self.assertTrue(any(
            self.bs.compare_amounts(g["tax_bs"], 9768.0) == 0 for g in groups))

    def test_bs_amounts_empty_without_bs_currency(self):
        inv = self._invoice("2026-07-25")
        self.company.l10n_ve_bs_currency_id = False
        self.assertEqual(inv._l10n_ve_bs_amounts(), {})


    # --- Borrador en el formulario ----------------------------------------

    def test_draft_form_widget_and_line_bs(self):
        """Regresión: en el formulario, antes de guardar, Odoo no ha generado
        las líneas de impuesto ni de cobro y el asiento no cuadra. El recuadre
        no debe comerse el Bs de la única línea de producto, y el widget debe
        mostrar los Bs convertidos a la tasa del borrador (no ceros)."""
        form = Form(self.env["account.move"].with_context(
            default_move_type="out_invoice"))
        form.partner_id = self.partner
        form.invoice_date = fields.Date.to_date("2026-07-25")
        with form.invoice_line_ids.new() as line:
            line.name = "Plato"
            line.quantity = 1.0
            line.price_unit = 100.0
            line.tax_ids.clear()
            line.tax_ids.add(self.tax_iva16)
        bs_totals = form.tax_totals["l10n_ve_bs"]
        # 100 USD de base (precio sin IVA en el common) y 16 de IVA a 610,5.
        base = form.tax_totals["base_amount"]
        tax = form.tax_totals["tax_amount"]
        self.assertAlmostEqual(bs_totals["base_amount"], round(base * 610.5, 2), places=2)
        self.assertAlmostEqual(bs_totals["tax_amount"], round(tax * 610.5, 2), places=2)
        self.assertAlmostEqual(
            bs_totals["total_amount"],
            bs_totals["base_amount"] + bs_totals["tax_amount"], places=2)
        self.assertTrue(bs_totals["total_amount"] > 0)
        move = form.save()
        product_line = move.invoice_line_ids
        self.assertAlmostEqual(
            product_line.l10n_ve_price_subtotal_bs,
            round(product_line.price_subtotal * 610.5, 2), places=2)
        # Ya guardado, el asiento cuadra en Bs.
        self.assertAlmostEqual(sum(move.line_ids.mapped("l10n_ve_balance_bs")), 0.0, places=2)


@tagged("post_install", "-at_install")
class TestDualFiscalBooks(DualCurrencyCommon):
    """Los Libros IVA usan los Bs almacenados (tasa congelada) del módulo."""

    def _wizard(self, date_from, date_to, book_type="sale"):
        return self.env["l10n.ve.fiscal.book.wizard"].create({
            "company_id": self.company.id,
            "date_from": date_from,
            "date_to": date_to,
            "book_type": book_type,
        })

    def test_hooks_use_stored_bs(self):
        inv = self._invoice("2026-07-25")
        credit = self._reverse_invoice(
            inv, date=fields.Date.to_date("2026-08-01"), post=True)
        wizard = self._wizard("2026-07-01", "2026-08-31")
        self.assertTrue(wizard._l10n_ve_dual_uses_bs(self.bs))
        self.assertFalse(wizard._l10n_ve_dual_uses_bs(self.env.ref("base.EUR")))

        line = self._lines(inv, "product").sorted("price_unit")[-1]
        # La línea de venta es un haber (-61.050 Bs): el factor -1 del libro de
        # ventas la deja en positivo.
        self.assertBs(
            wizard._l10n_ve_line_ves(line, -1.0, self.bs), 61050.0)
        self.assertBs(
            wizard._l10n_ve_line_ves(line, 1.0, self.bs), -61050.0)
        self.assertBs(wizard._l10n_ve_move_total_ves(inv, self.bs), 101343.0)
        # La NC sale con el total positivo (el signo lo pone el libro) y a la
        # tasa de la factura, no a la del 2026-08-01.
        self.assertBs(wizard._l10n_ve_move_total_ves(credit, self.bs), 101343.0)
        # IVA retenido a la tasa congelada del asiento: 16 USD × 610,5.
        self.assertBs(wizard._l10n_ve_amount_ves(inv, 16.0, self.bs), 9768.0)

    def test_generate_sale_book(self):
        self._invoice("2026-07-25")
        wizard = self._wizard("2026-07-01", "2026-07-31")
        wizard.action_generate()
        self.assertTrue(wizard.file)

    def test_generate_aborts_when_a_document_has_no_rate(self):
        """Sin tasa, `_convert` pondría USD en columnas Bs: se aborta."""
        inv = self._invoice(NO_RATE_DATE, post=False)
        inv._post()
        self.assertTrue(inv.l10n_ve_bs_rate_missing)
        wizard = self._wizard("2025-01-01", "2025-01-31")
        with self.assertRaises(UserError) as ctx:
            wizard.action_generate()
        self.assertIn("tasa BCV", str(ctx.exception))
