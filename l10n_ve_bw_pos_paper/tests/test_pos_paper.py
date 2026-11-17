# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_pos_paper. License LGPL-3.
from datetime import datetime

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPosPaper(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.today()
        cls.ves = cls.env["res.currency"].with_context(
            active_test=False).search([("name", "=", "VES")], limit=1)
        cls.ves.active = True
        if not cls.ves.rate_ids.filtered(lambda r: r.name == cls.today):
            cls.env["res.currency.rate"].create({
                "currency_id": cls.ves.id,
                "name": cls.today,
                "company_id": cls.company.id,
                "rate": 732.48,
            })
        cls.config = cls.env["pos.config"].create({"name": "Caja Test Papel"})
        cls.tax16 = cls.env["account.tax"].create({
            "name": "IVA 16% test", "amount": 16.0, "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.partner = cls.env["res.partner"].create(
            {"name": "CLIENTE PRUEBA", "vat": "J-12345678-9"})
        cls.product = cls.env["product.product"].create(
            {"name": "PRODUCTO TEST PAPEL", "list_price": 10.0})

    def _contingency_session(self):
        journal = self.env["account.journal"].create({
            "name": "Contingencia Test",
            "code": "CONTX",
            "type": "sale",
            "company_id": self.company.id,
            "l10n_ve_emission_channel": "contingencia",
        })
        self.config.l10n_ve_contingency_journal_id = journal
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
            "user_id": self.env.uid,
        })
        return journal, session

    def _backend_session(self):
        return self.env["pos.session"].create({
            "config_id": self.config.id,
            "user_id": self.env.uid,
        })

    def _pos_order(self, session, **extra):
        vals = {
            "session_id": session.id,
            "company_id": self.company.id,
            "partner_id": self.partner.id,
            "amount_tax": 1.6,
            "amount_total": 11.6,
            "amount_paid": 11.6,
            "amount_return": 0.0,
            "lines": [Command.create({
                "product_id": self.product.id,
                "qty": 1.0,
                "price_unit": 10.0,
                "price_subtotal": 10.0,
                "price_subtotal_incl": 11.6,
                "tax_ids": [Command.set(self.tax16.ids)],
            })],
        }
        vals.update(extra)
        return self.env["pos.order"].create(vals)

    # ------------------------------------------------------------------
    # Tasa BCV para el frontend (ves_rate.js)
    # ------------------------------------------------------------------
    def test_ves_rate(self):
        rate = self.config.l10n_ve_get_ves_rate()
        expected = self.company.currency_id._convert(
            1.0, self.ves, self.company, self.today, round=False)
        self.assertAlmostEqual(rate, expected, places=4)
        self.assertGreater(rate, 0)

    def test_ves_rate_missing_is_zero(self):
        # Sin filas de tasa NUNCA usar la tasa implícita 1.0: devolver 0.
        # Por SQL: con l10n_ve_bw_dual_currency instalado y asientos que ya
        # usan la tasa, el unlink del ORM se bloquea (ondelete de ese
        # módulo); el rollback del test la restaura.
        self.env.flush_all()
        self.env.cr.execute(
            "DELETE FROM res_currency_rate WHERE currency_id = %s",
            (self.ves.id,))
        self.env.invalidate_all()
        self.assertEqual(self.config.l10n_ve_get_ves_rate(), 0.0)

    # ------------------------------------------------------------------
    # Contingencia de sesión (PA 0071 art. 11)
    # ------------------------------------------------------------------
    def test_contingency_requires_pos_manager(self):
        # El control de grupo va en el SERVIDOR: el botón del POS solo pinta,
        # y un cajero puede llamar el método por RPC.
        _journal, session = self._contingency_session()
        cashier = self.env["res.users"].create({
            "name": "Cajero sin rango",
            "login": "cajero_contingencia_test",
            "group_ids": [Command.set([self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(AccessError):
            session.with_user(cashier).l10n_ve_contingency_open(
                "Se fue la luz en el local")

    def test_contingency_open_records_who_and_why(self):
        _journal, session = self._contingency_session()
        state = session.l10n_ve_contingency_open(
            "Impresora sin papel y trabada")
        self.assertEqual(session.l10n_ve_contingency_user_id, self.env.user)
        self.assertTrue(session.l10n_ve_contingency_start)
        self.assertEqual(state["reason"], "Impresora sin papel y trabada")
        # Reabrir NO pisa quién ni cuándo la autorizó la primera vez.
        first_start = session.l10n_ve_contingency_start
        session.l10n_ve_contingency_open("otro motivo distinto")
        self.assertEqual(session.l10n_ve_contingency_start, first_start)
        self.assertEqual(
            session.l10n_ve_contingency_reason,
            "Impresora sin papel y trabada")

    def test_contingency_rejects_short_reason(self):
        _journal, session = self._contingency_session()
        with self.assertRaises(UserError):
            session.l10n_ve_contingency_open("x")

    def test_contingency_requires_journal_on_config(self):
        session = self._backend_session()
        self.config.l10n_ve_contingency_journal_id = False
        with self.assertRaises(UserError):
            session.l10n_ve_contingency_open("Se fue la luz en el local")

    def test_contingency_session_fields_reach_the_pos(self):
        # Si estos campos no viajan, el frontend nunca sabe que el modo está
        # activo y el botón rojo no aparece.
        fields_list = self.env["pos.session"]._load_pos_data_fields(
            self.config)
        self.assertIn("l10n_ve_contingency_reason", fields_list)
        self.assertIn("l10n_ve_contingency_start", fields_list)

    def test_contingency_invoice_goes_to_its_own_journal(self):
        journal, session = self._contingency_session()
        order = self._pos_order(
            session, l10n_ve_contingency_control="00-00004321")
        vals = order._prepare_invoice_vals()
        self.assertEqual(vals["journal_id"], journal.id)
        self.assertEqual(vals["l10n_ve_control_number"], "00-00004321")
        self.assertIn("Contingencia", vals["ref"])

    # ------------------------------------------------------------------
    # Facturación consolidada multi-orden
    # ------------------------------------------------------------------
    def test_consolidated_invoice_without_fiscal_data_passes(self):
        # REGRESIÓN: el wizard pos.make.invoice llama _prepare_invoice_vals
        # sobre un recordset MULTI (el core es multi-aware); leer los campos
        # fiscales sin guard reventaba con ValueError de singleton.
        session = self._backend_session()
        orders = self._pos_order(session) | self._pos_order(session)
        vals = orders._prepare_invoice_vals()
        self.assertNotIn(
            "l10n_ve_control_number", vals,
            "El consolidado no lleva correlativo fiscal de ninguna orden")
        self.assertEqual(vals["pos_order_ids"], orders.ids)
        self.assertEqual(vals["move_type"], "out_invoice")

    def test_consolidated_invoice_blocked_if_any_order_is_paper(self):
        # Consolidar una orden de talonario dejaría ese correlativo fuera del
        # Libro de Ventas: se bloquea con un error claro.
        session = self._backend_session()
        plain = self._pos_order(session)
        contingency = self._pos_order(
            session, l10n_ve_contingency_control="00-00009999")
        with self.assertRaises(UserError):
            (plain | contingency)._prepare_invoice_vals()

    # ------------------------------------------------------------------
    # Modo papel permanente (talonario / formas libres)
    # ------------------------------------------------------------------
    def test_paper_mode_constraints(self):
        # Talonario exige diario de contingencia en la caja.
        with self.assertRaises(ValidationError):
            self.config.l10n_ve_paper_mode = "contingencia"
        journal = self.env["account.journal"].create({
            "name": "Contingencia Papel",
            "code": "CONTP",
            "type": "sale",
            "company_id": self.company.id,
            "l10n_ve_emission_channel": "contingencia",
        })
        self.config.l10n_ve_contingency_journal_id = journal
        self.config.l10n_ve_paper_mode = "contingencia"
        # Formas libres exigen canal 'libre' en el diario de facturación.
        with self.assertRaises(ValidationError):
            self.config.l10n_ve_paper_mode = "libre"
        self.config.invoice_journal_id.l10n_ve_emission_channel = "libre"
        self.config.l10n_ve_paper_mode = "libre"

    def test_paper_mode_batch_type_must_match(self):
        journal = self.env["account.journal"].create({
            "name": "Contingencia Papel 2",
            "code": "CONT2",
            "type": "sale",
            "company_id": self.company.id,
            "l10n_ve_emission_channel": "contingencia",
        })
        self.config.l10n_ve_contingency_journal_id = journal
        batch = self.env["l10n.ve.paper.batch"].create({
            "type": "forma_libre",
            "company_id": self.company.id,
            "control_from": "000001",
        })
        with self.assertRaises(ValidationError):
            self.config.write({
                "l10n_ve_paper_mode": "contingencia",
                "l10n_ve_paper_batch_id": batch.id,
            })

    def test_contingency_invoice_carries_paper_number(self):
        journal, session = self._contingency_session()
        order = self._pos_order(
            session,
            l10n_ve_contingency_control="000021",
            l10n_ve_contingency_invoice_number="000009",
        )
        vals = order._prepare_invoice_vals()
        self.assertEqual(vals["journal_id"], journal.id)
        self.assertEqual(vals["l10n_ve_control_number"], "000021")
        self.assertEqual(vals["l10n_ve_paper_number"], "000009")
        self.assertEqual(vals["ref"], "Contingencia F-000009 C-000021")
        # El create pasa el guard de fiscal_books gracias al contexto de
        # write-back de _create_invoice.
        move = order._create_invoice(vals)
        self.assertEqual(move.l10n_ve_paper_number, "000009")
        self.assertEqual(move.l10n_ve_control_number, "000021")

    def test_libre_mode_routes_to_invoice_journal(self):
        journal = self.config.invoice_journal_id
        journal.l10n_ve_emission_channel = "libre"
        self.config.l10n_ve_paper_mode = "libre"
        session = self._backend_session()
        order = self._pos_order(session, l10n_ve_contingency_control="000044")
        vals = order._prepare_invoice_vals()
        self.assertEqual(vals["journal_id"], journal.id,
                         "Forma libre factura en el diario normal de la caja")
        self.assertEqual(vals["l10n_ve_control_number"], "000044")
        self.assertTrue(vals["ref"].startswith("Forma libre"))
        self.assertFalse(vals.get("l10n_ve_paper_number"))
        # El create pasa: en canal libre la primera transcripción es legítima.
        move = order._create_invoice(vals)
        self.assertEqual(move.l10n_ve_control_number, "000044")

    def test_paper_mode_invoice_requires_partner(self):
        _journal, session = self._contingency_session()
        self.config.l10n_ve_paper_mode = "contingencia"
        order = self._pos_order(
            session, partner_id=False,
            l10n_ve_contingency_control="000055")
        with self.assertRaises(UserError):
            order._prepare_invoice_vals()

    def test_order_without_paper_keeps_core_vals(self):
        # Sin papelería, el hook no toca los vals del core: la caja normal
        # sigue facturando en su diario sin Nº de control.
        session = self._backend_session()
        order = self._pos_order(session)
        vals = order._prepare_invoice_vals()
        self.assertEqual(vals["journal_id"], self.config.invoice_journal_id.id)
        self.assertNotIn("l10n_ve_control_number", vals)

    def test_paper_event_log_is_stored(self):
        # La captura del talonario escribe la bitácora en la orden: el campo
        # debe existir y aceptar el valor que manda el frontend.
        session = self._backend_session()
        order = self._pos_order(
            session,
            l10n_ve_fiscal_event="contingency",
            l10n_ve_fiscal_event_note="10:00:00 · Cajero · Talonario")
        self.assertEqual(order.l10n_ve_fiscal_event, "contingency")

    def test_pos_config_paper_fields_reach_the_pos(self):
        # pos.config usa el default del mixin ([] = todos los campos). Si el
        # core algún día lo vuelve whitelist, este test avisa que hay que
        # añadir un override con los campos que leen los t-if del frontend.
        fields_list = self.env["pos.config"]._load_pos_data_fields(
            self.config)
        self.assertTrue(
            not fields_list
            or {"l10n_ve_paper_mode", "l10n_ve_paper_batch_id",
                "l10n_ve_contingency_journal_id"} <= set(fields_list))

    OLD = datetime(2000, 1, 1)

    def _age_last_data_change(self, config):
        # cr.now() es fijo dentro de la transacción del test: se envejece el
        # valor guardado para ver si el write lo vuelve a calcular.
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE pos_config SET last_data_change = %s WHERE id = %s",
            (self.OLD, config.id))
        config.invalidate_recordset(["last_data_change"])

    def test_paper_change_invalidates_pos_cache(self):
        self._contingency_session()
        self._age_last_data_change(self.config)
        self.config.l10n_ve_paper_mode = "contingencia"
        self.assertGreater(self.config.last_data_change, self.OLD)
        self._age_last_data_change(self.config)
        self.config.write({"l10n_ve_paper_mode": False,
                           "l10n_ve_contingency_journal_id": False})
        self.assertGreater(self.config.last_data_change, self.OLD)
