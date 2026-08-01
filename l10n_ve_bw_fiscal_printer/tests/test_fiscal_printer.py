# Part of l10n_ve_bw_fiscal_printer. License LGPL-3.
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFiscalPrinter(TransactionCase):
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
        cls.config = cls.env["pos.config"].create({
            "name": "Caja Test Fiscal",
            "l10n_ve_bridge_url": "http://localhost:5001",
            "l10n_ve_machine_serial": "Z1B0012345",
        })
        cls.tax16 = cls.env["account.tax"].create({
            "name": "IVA 16% test", "amount": 16.0, "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.partner = cls.env["res.partner"].create(
            {"name": "CLIENTE PRUEBA", "vat": "J-12345678-9"})
        cls.product = cls.env["product.product"].create(
            {"name": "SUSHI ROLL TEST PRODUCTO LARGO DE MAS DE 40 CARACTERES",
             "list_price": 10.0})

    def _invoice(self, move_type="out_invoice", lines=None, **extra):
        lines = lines or [
            (0, 0, {"product_id": self.product.id, "quantity": 2,
                    "price_unit": 10.0, "tax_ids": [(6, 0, self.tax16.ids)]}),
            (0, 0, {"product_id": self.product.id, "quantity": 1,
                    "price_unit": 5.0, "tax_ids": [(5, 0, 0)]}),
        ]
        move = self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": self.partner.id,
            "invoice_date": self.today,
            "invoice_line_ids": lines,
            **extra,
        })
        move.action_post()
        return move

    def test_load_pos_data_fields(self):
        pm_fields = self.env["pos.payment.method"]._load_pos_data_fields(self.config)
        self.assertIn("l10n_ve_fiscal_payment_code", pm_fields)
        self.assertIn("l10n_ve_igtf_applies", pm_fields)
        company_fields = self.env["res.company"]._load_pos_data_fields(self.config)
        self.assertIn("l10n_ve_is_spe", company_fields)
        self.assertIn("l10n_ve_igtf_pct", company_fields)

    def test_ves_rate(self):
        rate = self.config.l10n_ve_get_ves_rate()
        expected = self.company.currency_id._convert(
            1.0, self.ves, self.company, self.today, round=False)
        self.assertAlmostEqual(rate, expected, places=4)
        self.assertGreater(rate, 0)

    def test_ves_rate_missing_is_zero(self):
        # Sin filas de tasa NUNCA usar la tasa implícita 1.0: devolver 0
        self.env["res.currency.rate"].search(
            [("currency_id", "=", self.ves.id)]).unlink()
        self.assertEqual(self.config.l10n_ve_get_ves_rate(), 0.0)
        move = self._invoice()
        with self.assertRaises(UserError):
            move._l10n_ve_build_payload(self.config)

    def test_rate_pct_nearest(self):
        AccountMove = self.env["account.move"]
        self.assertEqual(AccountMove._l10n_ve_rate_pct(self.tax16), 16)
        self.assertEqual(
            AccountMove._l10n_ve_rate_pct(self.env["account.tax"]), 0)

    def test_build_payload_invoice(self):
        move = self._invoice()
        payload = move._l10n_ve_build_payload(self.config)
        self.assertEqual(payload["cliente_rif"], "J123456789")
        self.assertEqual(payload["serial_impresora"], "Z1B0012345")
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["iva_porcentaje"], 16)
        self.assertEqual(payload["items"][1]["iva_porcentaje"], 0)
        self.assertLessEqual(len(payload["items"][0]["descripcion"]), 40)
        # unitario con IVA en VES
        line = move.invoice_line_ids.filtered(lambda l: l.tax_ids)[0]
        expected_unit = round(round(move.currency_id._convert(
            line.price_total, self.ves, self.company, self.today), 2) / 2, 2)
        self.assertAlmostEqual(payload["items"][0]["precio"], expected_unit, places=2)
        # total/pago = aritmética de la MÁQUINA (Σ precio×cantidad redondeados)
        machine_total = round(sum(
            it["precio"] * it["cantidad"] for it in payload["items"]), 2)
        self.assertEqual(payload["monto_total"], machine_total)
        self.assertEqual(payload["pagos"], [{"metodo": "01", "monto": machine_total}])
        # y no se aleja del total contable convertido
        expected_total = round(move.currency_id._convert(
            move.amount_total, self.ves, self.company, self.today), 2)
        self.assertLessEqual(abs(machine_total - expected_total), 0.05)

    def test_negative_line_blocked(self):
        move = self._invoice(lines=[
            (0, 0, {"product_id": self.product.id, "quantity": 1,
                    "price_unit": 10.0, "tax_ids": [(5, 0, 0)]}),
            (0, 0, {"product_id": self.product.id, "quantity": 1,
                    "price_unit": -3.0, "tax_ids": [(5, 0, 0)]}),
        ])
        with self.assertRaises(UserError):
            move._l10n_ve_build_payload(self.config)

    def test_multiple_bridge_configs_blocked(self):
        self.env["pos.config"].create({
            "name": "Caja Dos",
            "l10n_ve_bridge_url": "http://localhost:5001",
        })
        move = self._invoice()
        with self.assertRaises(UserError):
            move._l10n_ve_get_bridge_config()

    def test_refund_requires_fiscal_origin(self):
        move = self._invoice()
        refund = self._invoice(move_type="out_refund",
                               reversed_entry_id=move.id)
        with self.assertRaises(UserError):
            refund._l10n_ve_build_payload(self.config)
        move.write({"l10n_ve_fiscal_number": "00001325",
                    "l10n_ve_fiscal_machine_serial": "Z1B0012345",
                    "l10n_ve_fiscal_date": "2026-07-19 12:00:00"})
        payload = refund._l10n_ve_build_payload(self.config)
        self.assertEqual(payload["numero_factura_afectada"], "00001325")
        self.assertEqual(payload["fecha_afectada"], "19072026")

    def test_set_fiscal_result(self):
        move = self._invoice()
        move.l10n_ve_set_fiscal_result("00001326", "Z1B0012345", "invoice")
        self.assertEqual(move.l10n_ve_fiscal_number, "00001326")
        self.assertEqual(move.l10n_ve_control_number, "00001326")
        self.assertEqual(move.l10n_ve_fiscal_doc_type, "invoice")
        self.assertTrue(move.l10n_ve_fiscal_date)
        # idempotente con el mismo número; ERROR con uno distinto (doble print)
        move.l10n_ve_set_fiscal_result("00001326", "Z1B0012345", "invoice")
        with self.assertRaises(UserError):
            move.l10n_ve_set_fiscal_result("00001399", "Z1B0012345", "invoice")
        self.assertEqual(move.l10n_ve_fiscal_number, "00001326")

    def test_action_guards(self):
        move = self._invoice()
        move.write({"l10n_ve_fiscal_number": "00000001"})
        with self.assertRaises(UserError):
            move.action_l10n_ve_print_fiscal()

    def test_action_returns_client_action(self):
        move = self._invoice()
        action = move.action_l10n_ve_print_fiscal()
        self.assertEqual(action["tag"], "l10n_ve_bw_fiscal_printer.print_fiscal")
        self.assertEqual(action["params"]["endpoint"], "/print-invoice")
        self.assertEqual(action["params"]["bridge_url"], "http://localhost:5001")
        self.assertTrue(action["params"]["payload"]["items"])
        self.assertEqual(action["params"]["payload"]["uuid"], "move-%s" % move.id)

    # ------------------------------------------------------------------
    # Modo contingencia (PA 0071 art. 11)
    # ------------------------------------------------------------------
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
        state = session.l10n_ve_contingency_open("Impresora sin papel y trabada")
        self.assertEqual(session.l10n_ve_contingency_user_id, self.env.user)
        self.assertTrue(session.l10n_ve_contingency_start)
        self.assertEqual(state["reason"], "Impresora sin papel y trabada")
        # Reabrir NO pisa quién ni cuándo la autorizó la primera vez.
        first_start = session.l10n_ve_contingency_start
        session.l10n_ve_contingency_open("otro motivo distinto")
        self.assertEqual(session.l10n_ve_contingency_start, first_start)
        self.assertEqual(
            session.l10n_ve_contingency_reason, "Impresora sin papel y trabada")

    def test_contingency_rejects_short_reason(self):
        _journal, session = self._contingency_session()
        with self.assertRaises(UserError):
            session.l10n_ve_contingency_open("x")

    def test_contingency_requires_journal_on_config(self):
        session = self.env["pos.session"].create({
            "config_id": self.config.id,
            "user_id": self.env.uid,
        })
        self.config.l10n_ve_contingency_journal_id = False
        with self.assertRaises(UserError):
            session.l10n_ve_contingency_open("Se fue la luz en el local")

    def test_contingency_session_fields_reach_the_pos(self):
        # Si estos campos no viajan, el frontend nunca sabe que el modo está
        # activo y el botón rojo no aparece.
        fields_list = self.env["pos.session"]._load_pos_data_fields(self.config)
        self.assertIn("l10n_ve_contingency_reason", fields_list)
        self.assertIn("l10n_ve_contingency_start", fields_list)

    def test_contingency_invoice_goes_to_its_own_journal(self):
        journal, session = self._contingency_session()
        order = self.env["pos.order"].create({
            "session_id": session.id,
            "company_id": self.company.id,
            "partner_id": self.partner.id,
            "amount_tax": 1.6,
            "amount_total": 11.6,
            "amount_paid": 11.6,
            "amount_return": 0.0,
            "l10n_ve_contingency_control": "00-00004321",
            "lines": [Command.create({
                "product_id": self.product.id,
                "qty": 1.0,
                "price_unit": 10.0,
                "price_subtotal": 10.0,
                "price_subtotal_incl": 11.6,
                "tax_ids": [Command.set(self.tax16.ids)],
            })],
        })
        vals = order._prepare_invoice_vals()
        self.assertEqual(vals["journal_id"], journal.id)
        self.assertEqual(vals["l10n_ve_control_number"], "00-00004321")
        self.assertIn("Contingencia", vals["ref"])

    # ------------------------------------------------------------------
    # Facturación backend: consolidado multi-orden y write-back del guard
    # ------------------------------------------------------------------
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

    def test_consolidated_invoice_without_fiscal_data_passes(self):
        # REGRESIÓN: el wizard pos.make.invoice llama _prepare_invoice_vals
        # sobre un recordset MULTI (el core es multi-aware); leer los campos
        # fiscales sin guard reventaba con ValueError de singleton antes de
        # llegar a facturar CUALQUIER consolidado, tuviera o no datos fiscales.
        session = self._backend_session()
        orders = self._pos_order(session) | self._pos_order(session)
        vals = orders._prepare_invoice_vals()
        self.assertNotIn(
            "l10n_ve_control_number", vals,
            "El consolidado no lleva correlativo fiscal de ninguna orden")
        self.assertEqual(vals["pos_order_ids"], orders.ids)
        self.assertEqual(vals["move_type"], "out_invoice")

    def test_consolidated_invoice_blocked_if_any_order_is_fiscal(self):
        # Consolidar una orden con ticket de máquina o de talonario dejaría
        # ese correlativo fuera del Libro de Ventas: se bloquea con un error
        # claro en vez del ValueError de singleton.
        session = self._backend_session()
        plain = self._pos_order(session)
        fiscal = self._pos_order(session, l10n_ve_fiscal_number="00001111")
        with self.assertRaises(UserError):
            (plain | fiscal)._prepare_invoice_vals()
        contingency = self._pos_order(
            session, l10n_ve_contingency_control="00-00009999")
        with self.assertRaises(UserError):
            (plain | contingency)._prepare_invoice_vals()

    def test_create_invoice_carries_fiscal_number_through_mf_guard(self):
        # El diario de facturación de la caja es canal 'mf': el guard de
        # create de l10n_ve_bw_fiscal_books bloquea el Nº de control salvo
        # write-back. El override de _create_invoice debe declarar el
        # contexto: el número viene de un ticket YA impreso por la máquina.
        session = self._backend_session()
        journal = self.config.invoice_journal_id
        self.assertTrue(journal, "la caja debe tener diario de facturación")
        journal.l10n_ve_emission_channel = "mf"
        order = self._pos_order(
            session,
            l10n_ve_fiscal_number="00001327",
            l10n_ve_fiscal_machine_serial="Z1B0012345",
            l10n_ve_fiscal_date="2026-07-30 10:00:00",
            l10n_ve_fiscal_doc_type="invoice",
        )
        vals = order._prepare_invoice_vals()
        self.assertEqual(vals["l10n_ve_control_number"], "00001327")
        move = order._create_invoice(vals)
        self.assertEqual(move.l10n_ve_control_number, "00001327")
        self.assertEqual(move.l10n_ve_fiscal_number, "00001327")
        self.assertEqual(move.l10n_ve_fiscal_machine_serial, "Z1B0012345")
        self.assertEqual(move.journal_id, journal)
