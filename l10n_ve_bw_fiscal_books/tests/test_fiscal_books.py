# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
import base64
import io
from datetime import datetime, time, timedelta

import pytz

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

try:
    import openpyxl
except ImportError:
    openpyxl = None


@tagged("post_install", "-at_install")
class TestFiscalBooks(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        # POS access so the test methods can create/read pos.session/pos.order.
        cls.env.user.group_ids |= cls.env.ref("point_of_sale.group_pos_manager")
        country_ve = cls.env.ref("base.ve")
        Partner = cls.env["res.partner"].with_context(no_vat_validation=True)
        cls.partner = Partner.create({
            "name": "Cliente de Prueba VE, C.A.",
            "vat": "J-12345678-9",
            "country_id": country_ve.id,
        })
        cls.vendor = Partner.create({
            "name": "Proveedor de Prueba VE, C.A.",
            "vat": "J-98765432-1",
            "country_id": country_ve.id,
        })
        cls.sale_tax = cls.env["account.tax"].create({
            "name": "IVA 16% (Ventas) — prueba",
            "amount": 16.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.purchase_tax = cls.env["account.tax"].create({
            "name": "IVA 16% (Compras) — prueba",
            "amount": 16.0,
            "amount_type": "percent",
            "type_tax_use": "purchase",
            "company_id": cls.company.id,
        })
        today = fields.Date.today()
        cls.date_from = today.replace(day=1)
        cls.date_to = today
        cls.invoice = cls.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": cls.partner.id,
            "invoice_date": today,
            "l10n_ve_control_number": "00-00000001",
            "invoice_line_ids": [Command.create({
                "name": "Servicio de prueba",
                "quantity": 1.0,
                "price_unit": 100.0,
                "tax_ids": [Command.set(cls.sale_tax.ids)],
            })],
        })
        cls.invoice.action_post()
        cls.bill = cls.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": cls.vendor.id,
            "invoice_date": today,
            "ref": "FACT-PROV-0001",
            "l10n_ve_control_number": "00-00000002",
            "invoice_line_ids": [Command.create({
                "name": "Insumo de prueba",
                "quantity": 1.0,
                "price_unit": 50.0,
                "tax_ids": [Command.set(cls.purchase_tax.ids)],
            })],
        })
        cls.bill.action_post()
        # --- POS: config + sesión para los tests del bloque diario art. 77 ---
        # sudo: crear config/sesión POS requiere rol POS/Administrador, ajeno
        # al usuario contable del common; el wizard bajo prueba lee POS con sudo.
        cls.pos_config = cls.env["pos.config"].sudo().create({
            "name": "POS Libros VE",
            "company_id": cls.company.id,
            "l10n_ve_machine_serial": "Z1B1234567",
        })
        cls.pos_session = cls.env["pos.session"].sudo().create({
            "config_id": cls.pos_config.id,
            "user_id": cls.env.uid,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _make_wizard(self, book_type):
        return self.env["l10n.ve.fiscal.book.wizard"].create({
            "date_from": self.date_from,
            "date_to": self.date_to,
            "book_type": book_type,
        })

    def _generate(self, book_type):
        wizard = self._make_wizard(book_type)
        result = wizard.action_generate()
        self.assertEqual(result["res_id"], wizard.id)
        return wizard

    def _extract_cell_values(self, file_b64):
        if not openpyxl:
            return None
        workbook = openpyxl.load_workbook(
            io.BytesIO(base64.b64decode(file_b64)), read_only=True)
        values = set()
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        values.add(str(cell.value))
        return values

    def _create_pos_order(self, name, date_order, price=100.0):
        tax = self.sale_tax
        tax_amount = round(price * tax.amount / 100.0, 2)
        total = price + tax_amount
        return self.env["pos.order"].create({
            "name": name,
            "session_id": self.pos_session.id,
            "company_id": self.company.id,
            "date_order": date_order,
            "pos_reference": name,
            "sequence_number": 1,
            "amount_tax": tax_amount,
            "amount_total": total,
            "amount_paid": total,
            "amount_return": 0.0,
            "state": "paid",
            "lines": [Command.create({
                "name": "%s-1" % name,
                "product_id": self.product_a.id,
                "qty": 1.0,
                "price_unit": price,
                "price_subtotal": price,
                "price_subtotal_incl": total,
                "tax_ids": [Command.set(tax.ids)],
            })],
        })

    @staticmethod
    def _local_to_utc(local_dt, tz_name="America/Caracas"):
        tz = pytz.timezone(tz_name)
        return tz.localize(local_dt).astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # Tests básicos de generación
    # ------------------------------------------------------------------
    def test_sale_book(self):
        wizard = self._generate("sale")
        self.assertTrue(wizard.file, "El libro de ventas debe generar un binario")
        self.assertTrue(wizard.filename.startswith("libro_ventas_"))
        self.assertTrue(wizard.filename.endswith(".xlsx"))
        content = base64.b64decode(wizard.file)
        self.assertEqual(content[:2], b"PK", "El binario debe ser un XLSX (zip)")
        values = self._extract_cell_values(wizard.file)
        if values is None:
            return
        self.assertIn("LIBRO DE VENTAS", values)
        self.assertIn(self.invoice.name, values)
        self.assertIn("00-00000001", values)
        self.assertIn(self.partner.vat, values)

    def test_purchase_book(self):
        wizard = self._generate("purchase")
        self.assertTrue(wizard.file, "El libro de compras debe generar un binario")
        self.assertTrue(wizard.filename.startswith("libro_compras_"))
        content = base64.b64decode(wizard.file)
        self.assertEqual(content[:2], b"PK")
        values = self._extract_cell_values(wizard.file)
        if values is None:
            return
        self.assertIn("LIBRO DE COMPRAS", values)
        self.assertIn("FACT-PROV-0001", values)
        self.assertIn("00-00000002", values)
        self.assertIn(self.vendor.vat, values)

    def test_refund_referenced(self):
        refund_wizard = self.env["account.move.reversal"].with_context(
            active_model="account.move", active_ids=self.invoice.ids,
        ).create({
            "journal_id": self.invoice.journal_id.id,
            "reason": "Prueba NC",
        })
        action = refund_wizard.refund_moves()
        refund = self.env["account.move"].browse(action["res_id"])
        refund.action_post()
        wizard = self._generate("sale")
        values = self._extract_cell_values(wizard.file)
        if values is None:
            return
        self.assertIn(refund.name, values)
        # la NC (tipo 03) debe referenciar la factura afectada
        self.assertIn("03", values)

    def test_date_constraint(self):
        with self.assertRaises(ValidationError):
            self.env["l10n.ve.fiscal.book.wizard"].create({
                "date_from": self.date_to,
                "date_to": self.date_from - timedelta(days=1),
                "book_type": "sale",
            })

    def test_control_number_not_copied(self):
        copy = self.invoice.copy()
        self.assertFalse(copy.l10n_ve_control_number)

    # ------------------------------------------------------------------
    # Regresión: zona horaria del bloque diario POS (art. 77)
    # ------------------------------------------------------------------
    def test_pos_daily_block_timezone(self):
        """Los límites del período se aplican en hora local del usuario:
        una venta a las 21:00 locales del último día (01:00 UTC del día
        siguiente en Venezuela) DEBE entrar al libro, y una venta nocturna
        de la víspera del primer día NO debe producir filas fuera del
        período."""
        self.env.user.tz = "America/Caracas"
        order_late = self._create_pos_order(
            "POS/TZ-IN",
            self._local_to_utc(datetime.combine(self.date_to, time(21, 0))),
        )
        # 02:00 UTC del date_from = 22:00 hora local del día ANTERIOR:
        # caía dentro del rango UTC naive del comportamiento anterior.
        order_eve = self._create_pos_order(
            "POS/TZ-OUT",
            datetime.combine(self.date_from, time(2, 0)),
        )
        self.pos_session.state = "closed"
        wizard = self._make_wizard("sale")
        rows = wizard._get_pos_day_rows(wizard._get_ves_currency())
        days = [row["date"] for row in rows]
        self.assertIn(
            self.date_to, days,
            "La venta nocturna del último día (hora local) debe aparecer")
        self.assertTrue(
            all(self.date_from <= day <= self.date_to for day in days),
            "Ninguna fila del bloque diario puede quedar fechada fuera del período")
        names = {n for row in rows
                 for n in (row["first_order"], row["last_order"])}
        self.assertIn(order_late.name, names)
        self.assertNotIn(
            order_eve.name, names,
            "La venta de la víspera (hora local) no pertenece al período")

    # ------------------------------------------------------------------
    # Regresión: órdenes POS facturadas van por documento (art. 76)
    # ------------------------------------------------------------------
    def test_pos_invoiced_order_split_blocks(self):
        """Una orden POS facturada a un contribuyente debe listarse POR
        DOCUMENTO (con su Nº de factura y Nº de control) en el bloque del
        art. 76 y quedar EXCLUIDA del resumen diario del art. 77; la orden
        no facturada permanece en el bloque diario."""
        self.env.user.tz = "America/Caracas"
        mid_day = self._local_to_utc(
            datetime.combine(self.date_to, time(10, 0)))
        plain_order = self._create_pos_order("POS/NOINV", mid_day)
        invoiced_order = self._create_pos_order("POS/INV", mid_day, price=200.0)
        pos_invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": self.date_to,
            "l10n_ve_control_number": "00-00000099",
            "invoice_line_ids": [Command.create({
                "name": "Venta POS facturada",
                "quantity": 1.0,
                "price_unit": 200.0,
                "tax_ids": [Command.set(self.sale_tax.ids)],
            })],
        })
        pos_invoice.action_post()
        invoiced_order.account_move = pos_invoice
        self.pos_session.state = "closed"

        wizard = self._make_wizard("sale")
        self.assertIn(
            pos_invoice, wizard._get_sale_moves(),
            "La factura emitida desde POS debe listarse por documento (art. 76)")
        rows = wizard._get_pos_day_rows(wizard._get_ves_currency())
        names = {n for row in rows
                 for n in (row["first_order"], row["last_order"])}
        self.assertIn(plain_order.name, names)
        self.assertNotIn(
            invoiced_order.name, names,
            "La orden facturada no puede aparecer en el resumen diario (art. 77)")
        generated = self._generate("sale")
        values = self._extract_cell_values(generated.file)
        if values is None:
            return
        self.assertIn(pos_invoice.name, values)
        self.assertIn("00-00000099", values)

    # ------------------------------------------------------------------
    # Regresión: IVA retenido al proveedor (Libro de Compras)
    # ------------------------------------------------------------------
    def test_purchase_book_wh_iva_voucher(self):
        """La columna 'IVA Retenido al Proveedor' y el Nº de comprobante se
        leen de la interfaz canónica de l10n_ve_bw_wh_iva (move_ids +
        _l10n_ve_get_amount_for_move + number)."""
        Voucher = self.env.get("l10n.ve.iva.wh.voucher")
        if Voucher is None or not hasattr(Voucher, "_l10n_ve_get_amount_for_move"):
            self.skipTest("l10n_ve_bw_wh_iva no está instalado")
        voucher = Voucher.create({
            "number": "20260700000001",
            "date": self.date_to,
            "company_id": self.company.id,
            "partner_id": self.vendor.id,
            "move_ids": [Command.set(self.bill.ids)],
            "base_amount": 50.0,
            "tax_amount": 8.0,
            "withheld_amount": 6.0,
            "wh_rate": 75.0,
            "state": "posted",
        })
        wizard = self._make_wizard("purchase")
        ves = wizard._get_ves_currency()
        amount, numbers = wizard._get_wh_iva_data(self.bill, ves)
        self.assertEqual(numbers, voucher.number)
        self.assertAlmostEqual(
            amount, wizard._to_ves(6.0, ves, self.bill.date), places=2,
            msg="El IVA retenido del comprobante debe volcarse en Bs")
        # Un comprobante anulado no debe contarse
        voucher.action_cancel()
        amount, numbers = wizard._get_wh_iva_data(self.bill, ves)
        self.assertEqual((amount, numbers), (0.0, ""))
        generated = self._generate("purchase")
        values = self._extract_cell_values(generated.file)
        if values is None:
            return
        self.assertIn("IVA Retenido al Proveedor", values)

    # ------------------------------------------------------------------
    # Regresión: IVA que nos retuvieron los clientes (Libro de Ventas)
    # ------------------------------------------------------------------
    def test_sale_book_wh_iva_received(self):
        """La columna 'IVA Retenido' del Libro de Ventas debe reflejar la
        retención practicada por el cliente (agente de retención), leída de
        los pagos conciliados con la factura (matched_payment_ids)."""
        Payment = self.env["account.payment"]
        if "l10n_ve_iva_wh_received_amount" not in Payment._fields:
            self.skipTest(
                "l10n_ve_bw_wh_iva no está instalado (sin campos de "
                "retención recibida en account.payment)")
        payment_vals = {
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": self.partner.id,
            "amount": 104.0,
            "date": self.date_to,
            "journal_id": self.company_data["default_journal_bank"].id,
            "l10n_ve_iva_wh_received_amount": 12.0,
        }
        has_number_field = "l10n_ve_iva_wh_received_number" in Payment._fields
        if has_number_field:
            payment_vals["l10n_ve_iva_wh_received_number"] = "20260700000077"
        payment = Payment.create(payment_vals)
        payment.state = "in_process"
        self.invoice.matched_payment_ids = [Command.link(payment.id)]

        wizard = self._make_wizard("sale")
        ves = wizard._get_ves_currency()
        amount, numbers = wizard._get_wh_iva_received_data(self.invoice, ves)
        expected = wizard._to_ves(
            12.0, ves, payment.date, currency=payment.currency_id)
        self.assertAlmostEqual(
            amount, expected, places=2,
            msg="La retención recibida debe volcarse en la columna IVA Retenido")
        if has_number_field:
            self.assertEqual(numbers, "20260700000077")
        row = wizard._prepare_move_row(self.invoice, ves)
        self.assertAlmostEqual(row["wh_iva"], expected, places=2)
        # Un pago anulado no debe contarse
        payment.state = "canceled"
        amount, _numbers = wizard._get_wh_iva_received_data(self.invoice, ves)
        self.assertEqual(amount, 0.0)

    # ------------------------------------------------------------------
    # Canal de emisión y política del Nº de control
    # ------------------------------------------------------------------
    def _set_channel(self, move, channel):
        move.journal_id.l10n_ve_emission_channel = channel

    def test_control_free_without_channel(self):
        # REGRESIÓN CRÍTICA: sin canal declarado el Nº de control se edita a
        # voluntad. Es el caso de las facturas de PROVEEDOR, que el contador
        # corrige de rutina tras contabilizar.
        self.assertFalse(self.bill.journal_id.l10n_ve_emission_channel)
        self.bill.l10n_ve_control_number = "00-00000099"
        self.assertEqual(self.bill.l10n_ve_control_number, "00-00000099")

    def test_control_locked_for_assigned_channels(self):
        # Máquina fiscal e imprenta digital: lo asigna un tercero, nunca el
        # usuario — ni desde la interfaz ni por RPC.
        for channel in ("mf", "digital"):
            with self.subTest(channel=channel):
                self._set_channel(self.invoice, channel)
                with self.assertRaises(UserError):
                    self.invoice.l10n_ve_control_number = "00-00009999"

    def test_control_write_once_for_forma_libre(self):
        # Forma libre: se transcribe UNA vez del talonario y queda cerrado.
        self._set_channel(self.invoice, "libre")
        with self.assertRaises(UserError):
            self.invoice.l10n_ve_control_number = "00-00008888"
        # Con el campo vacío sí se acepta el primer valor...
        self.invoice.with_context(
            l10n_ve_control_writeback=True).l10n_ve_control_number = False
        self.invoice.l10n_ve_control_number = "00-00007777"
        self.assertEqual(self.invoice.l10n_ve_control_number, "00-00007777")
        # ...y el segundo ya no.
        with self.assertRaises(UserError):
            self.invoice.l10n_ve_control_number = "00-00006666"

    def test_control_editable_in_contingency(self):
        # Contingencia: replica un documento que ya existe en papel, así que
        # tiene que poder corregirse.
        self._set_channel(self.invoice, "contingencia")
        self.invoice.l10n_ve_control_number = "00-00005555"
        self.invoice.l10n_ve_control_number = "00-00004444"
        self.assertEqual(self.invoice.l10n_ve_control_number, "00-00004444")

    def test_control_writeback_context_bypasses_guard(self):
        # El bridge de la máquina y el conector de imprenta digital son el
        # origen legítimo: escriben con el contexto y el guard los deja pasar.
        self._set_channel(self.invoice, "mf")
        self.invoice.with_context(
            l10n_ve_control_writeback=True).l10n_ve_control_number = "00-00001326"
        self.assertEqual(self.invoice.l10n_ve_control_number, "00-00001326")

    def test_control_locked_on_create_for_assigned_channel(self):
        # Cierre de la vía create (RPC directo, import CSV/XLSX, duplicación
        # con vals): en canal 'mf' el Nº de control solo puede entrar con el
        # contexto de write-back de la máquina.
        self._set_channel(self.invoice, "mf")
        vals = {
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": self.date_to,
            "journal_id": self.invoice.journal_id.id,
            "l10n_ve_control_number": "00-00012345",
            "invoice_line_ids": [Command.create({
                "name": "Venta creada por RPC",
                "quantity": 1.0,
                "price_unit": 10.0,
                "tax_ids": [Command.set(self.sale_tax.ids)],
            })],
        }
        with self.assertRaises(UserError):
            self.env["account.move"].create(dict(vals))
        move = self.env["account.move"].with_context(
            l10n_ve_control_writeback=True).create(dict(vals))
        self.assertEqual(move.l10n_ve_control_number, "00-00012345")
        # Sin Nº de control el create en canal 'mf' sigue libre: la factura
        # se crea primero y el número llega después con el write-back.
        clean_vals = dict(vals)
        clean_vals.pop("l10n_ve_control_number")
        clean = self.env["account.move"].create(clean_vals)
        self.assertFalse(clean.l10n_ve_control_number)

    # ------------------------------------------------------------------
    # Wizard: alícuota combinada 16+15 (=31) y líneas negativas
    # ------------------------------------------------------------------
    def _combo_invoice(self, taxes, lines=None):
        lines = lines or [(100.0, taxes)]
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": self.date_to,
            "invoice_line_ids": [Command.create({
                "name": "Línea de prueba %s" % index,
                "quantity": 1.0,
                "price_unit": price,
                "tax_ids": [Command.set(line_taxes.ids)],
            }) for index, (price, line_taxes) in enumerate(lines)],
        })
        move.action_post()
        return move

    def test_move_row_combined_rate_31(self):
        # IVA 16% + adicional 15% (bienes suntuarios): la base se cuenta UNA
        # sola vez en la columna 31% y el IVA de AMBOS impuestos cae ahí;
        # nada puede quedar en la columna 16% ni duplicarse.
        tax15 = self.env["account.tax"].create({
            "name": "IVA adicional 15% — prueba",
            "amount": 15.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": self.company.id,
        })
        group = self.env["account.tax"].create({
            "name": "IVA 31% (grupo) — prueba",
            "amount_type": "group",
            "type_tax_use": "sale",
            "company_id": self.company.id,
            "children_tax_ids": [Command.set((self.sale_tax | tax15).ids)],
        })
        wizard = self._make_wizard("sale")
        ves = wizard._get_ves_currency()
        combos = [
            ("dos impuestos en la línea", self.sale_tax | tax15),
            ("grupo de impuestos 16+15", group),
        ]
        for label, taxes in combos:
            with self.subTest(combo=label):
                move = self._combo_invoice(taxes)
                row = wizard._prepare_move_row(move, ves)
                self.assertAlmostEqual(
                    row["base_31"], wizard._to_ves(100.0, ves, move.date),
                    delta=0.02,
                    msg="La base va una sola vez a la columna 31%")
                self.assertAlmostEqual(
                    row["tax_31"], wizard._to_ves(31.0, ves, move.date),
                    delta=0.02,
                    msg="El IVA de ambos impuestos cae completo en 31%")
                self.assertEqual(row["base_16"], 0.0)
                self.assertEqual(row["tax_16"], 0.0)
                self.assertEqual(row["exempt"], 0.0)

    def test_move_row_negative_line_netted(self):
        # La deducción de un anticipo (línea negativa) NETEA la base del
        # documento: 100 − 20 son 80 en la columna 16%, no 120 en valor
        # absoluto ni una fila descuadrada contra el total.
        move = self._combo_invoice(None, lines=[
            (100.0, self.sale_tax), (-20.0, self.sale_tax)])
        wizard = self._make_wizard("sale")
        ves = wizard._get_ves_currency()
        row = wizard._prepare_move_row(move, ves)
        self.assertAlmostEqual(
            row["base_16"], wizard._to_ves(80.0, ves, move.date), delta=0.02)
        self.assertAlmostEqual(
            row["tax_16"], wizard._to_ves(12.8, ves, move.date), delta=0.02)
        self.assertAlmostEqual(
            row["total"], wizard._to_ves(92.8, ves, move.date), delta=0.02)
        self.assertEqual(row["exempt"], 0.0)

    def test_contingency_journal_created_and_unhashed(self):
        from odoo.addons.l10n_ve_bw_fiscal_books.hooks import (
            create_contingency_journals,
        )
        self.company.account_fiscal_country_id = self.env.ref("base.ve")
        create_contingency_journals(self.env)
        journal = self.env["account.journal"].search([
            ("company_id", "=", self.company.id),
            ("l10n_ve_emission_channel", "=", "contingencia"),
        ])
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal.type, "sale")
        # SIN hash a propósito: replica el talonario y debe poder corregirse.
        self.assertFalse(journal.restrict_mode_hash_table)
        self.assertTrue(journal.default_account_id)
        # Idempotente: una segunda pasada no duplica.
        create_contingency_journals(self.env)
        self.assertEqual(len(self.env["account.journal"].search([
            ("company_id", "=", self.company.id),
            ("l10n_ve_emission_channel", "=", "contingencia"),
        ])), 1)

    def test_sale_book_splits_by_channel(self):
        # PA 102 art. 6: con dos canales en el período el bloque I se parte y
        # cada sub-bloque lleva su propio subtotal.
        self._set_channel(self.invoice, "mf")
        contingency = self.env["account.journal"].create({
            "name": "Contingencia de prueba",
            "code": "CONTT",
            "type": "sale",
            "company_id": self.company.id,
            "default_account_id": self.invoice.journal_id.default_account_id.id,
            "l10n_ve_emission_channel": "contingencia",
        })
        manual = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": self.date_to,
            "journal_id": contingency.id,
            "l10n_ve_control_number": "00-00003333",
            "invoice_line_ids": [Command.create({
                "name": "Venta en contingencia",
                "quantity": 1.0,
                "price_unit": 70.0,
                "tax_ids": [Command.set(self.sale_tax.ids)],
            })],
        })
        manual.action_post()
        wizard = self._generate("sale")
        values = self._extract_cell_values(wizard.file)
        if values is None:
            return
        self.assertIn("  Emitidas por máquina fiscal", values)
        self.assertIn("  Emitidas en contingencia (talonario)", values)
        self.assertIn("00-00003333", values)
