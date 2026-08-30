# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_einvoice. License LGPL-3.
from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestEinvoice(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.l10n_ve_edoc_provider = "l10n.ve.edoc.provider.dummy"
        cls.tax_16 = cls.env["account.tax"].create({
            "name": "IVA 16% — prueba edoc",
            "amount": 16.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.tax_exempt = cls.env["account.tax"].create({
            "name": "Exento — prueba edoc",
            "amount": 0.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.digital_journal = cls.env["account.journal"].create({
            "name": "Ventas por Imprenta Digital",
            "code": "DIGI",
            "type": "sale",
            "company_id": cls.company.id,
            "l10n_ve_emission_channel": "digital",
        })
        cls.partner = cls.env["res.partner"].with_context(
            no_vat_validation=True).create({
                "name": "Cliente Empresa, C.A.",
                "vat": "J-98765432-1",
                "street": "Av. Principal, Lechería",
            })

    def _invoice(self, journal=None):
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": fields.Date.to_date("2026-07-25"),
            "journal_id": (journal or self.digital_journal).id,
            "invoice_line_ids": [
                Command.create({
                    "name": "Servicio gravado",
                    "quantity": 1.0,
                    "price_unit": 100.0,
                    "tax_ids": [Command.set(self.tax_16.ids)],
                }),
                Command.create({
                    "name": "Insumo exento",
                    "quantity": 2.0,
                    "price_unit": 25.0,
                    "tax_ids": [Command.set(self.tax_exempt.ids)],
                }),
            ],
        })
        move.action_post()
        return move

    def test_document_vals_split_taxed_and_exempt(self):
        # Toda la lógica fiscal vive aquí y no en el adaptador: es lo que
        # permite cambiar de imprenta sin tocar nada fiscal.
        vals = self._invoice()._l10n_ve_edoc_document_vals()
        self.assertEqual(vals["tipo_documento"], "factura")
        self.assertEqual(vals["emisor"]["rif"], self.company.vat or "")
        self.assertEqual(vals["comprador"]["rif"], "J-98765432-1")
        self.assertAlmostEqual(vals["total_base"], 100.0, places=2)
        self.assertAlmostEqual(vals["total_exento"], 50.0, places=2)
        self.assertAlmostEqual(vals["total_iva"], 16.0, places=2)
        exempt_line = next(ln for ln in vals["lineas"] if ln["exento"])
        self.assertAlmostEqual(exempt_line["alicuota"], 0.0, places=2)

    def test_credit_note_references_affected_document(self):
        # La NC debe referenciar número, fecha y monto del documento afectado.
        invoice = self._invoice()
        reversal = self.env["account.move.reversal"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "journal_id": self.digital_journal.id,
            "reason": "prueba",
        })
        refund = self.env["account.move"].browse(
            reversal.reverse_moves()["res_id"])
        vals = refund._l10n_ve_edoc_document_vals()
        self.assertEqual(vals["tipo_documento"], "nota_credito")
        self.assertEqual(vals["documento_afectado"]["numero"], invoice.name)
        self.assertAlmostEqual(
            vals["documento_afectado"]["monto"], invoice.amount_total, places=2)

    def test_debit_note_references_affected_document(self):
        # La ND es un out_invoice con debit_origin_id: sin su rama saldría a
        # la imprenta como "factura" y sin la referencia (número, fecha y
        # monto del documento afectado) que exige la PA 0071.
        if "debit_origin_id" not in self.env["account.move"]._fields:
            self.skipTest("account_debit_note no está instalado")
        invoice = self._invoice()
        wizard = self.env["account.debit.note"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "reason": "Intereses de mora — prueba",
            "copy_lines": True,
        })
        debit = self.env["account.move"].browse(
            wizard.create_debit()["res_id"])
        debit.action_post()
        vals = debit._l10n_ve_edoc_document_vals()
        self.assertEqual(vals["tipo_documento"], "nota_debito")
        afectado = vals["documento_afectado"]
        self.assertEqual(afectado["numero"], invoice.name)
        self.assertEqual(afectado["fecha"], invoice.invoice_date)
        self.assertAlmostEqual(
            afectado["monto"], invoice.amount_total, places=2)

    def test_send_assigns_control_number_and_logs(self):
        move = self._invoice()
        move.action_l10n_ve_edoc_send()
        self.assertEqual(move.l10n_ve_edoc_state, "assigned")
        self.assertTrue(move.l10n_ve_control_number)
        self.assertTrue(move.l10n_ve_control_date)
        log = self.env["l10n.ve.edoc.log"].search([("move_id", "=", move.id)])
        self.assertTrue(log, "cada llamada al proveedor deja bitácora")
        self.assertTrue(log[0].ok)

    def test_control_number_written_despite_the_guard(self):
        # El diario es de canal 'digital', donde el Nº de control está
        # bloqueado para el usuario. El conector SÍ puede escribirlo: usa el
        # contexto de write-back. Si esto se rompe, no se puede facturar.
        move = self._invoice()
        with self.assertRaises(UserError):
            move.l10n_ve_control_number = "00-99999999"
        move.action_l10n_ve_edoc_send()
        self.assertTrue(move.l10n_ve_control_number)

    def test_send_rejects_wrong_channel(self):
        move = self._invoice(journal=self.company_data["default_journal_sale"])
        with self.assertRaises(UserError):
            move.action_l10n_ve_edoc_send()

    def test_send_is_not_repeatable(self):
        move = self._invoice()
        move.action_l10n_ve_edoc_send()
        with self.assertRaises(UserError):
            move.action_l10n_ve_edoc_send()

    def test_async_provider_needs_a_second_step(self):
        # Con un proveedor asíncrono (Unidigital) la emisión no trae el Nº de
        # control: el documento queda 'sent' y se consulta después.
        provider = self.env["l10n.ve.edoc.provider.dummy"]
        move = self._invoice()
        self.patch(type(provider), "_dummy_fetch_delay", 1)
        move.action_l10n_ve_edoc_send()
        self.assertEqual(move.l10n_ve_edoc_state, "sent")
        self.assertFalse(move.l10n_ve_control_number)
        move.action_l10n_ve_edoc_fetch()
        self.assertEqual(move.l10n_ve_edoc_state, "assigned")
        self.assertTrue(move.l10n_ve_control_number)

    def test_document_vals_enriched_for_the_printer(self):
        # Campos que la imprenta exige y el adaptador no puede inventar:
        # hora de emisión, identificación partida, código/unidad/IVA por
        # línea, subtotal, tipo de venta y formas de pago.
        move = self._invoice()
        vals = move._l10n_ve_edoc_document_vals()
        self.assertRegex(vals["hora"], r"^\d{2}:\d{2}:\d{2}$")
        self.assertEqual(vals["comprador"]["tipo_identificacion"], "J")
        self.assertEqual(vals["comprador"]["numero_identificacion"],
                         "987654321")
        self.assertEqual(vals["nro_items"], 2)
        self.assertAlmostEqual(vals["subtotal"], 150.0, places=2)
        self.assertIn(vals["tipo_venta"], ("contado", "credito"))
        gravada = next(ln for ln in vals["lineas"] if not ln["exento"])
        self.assertAlmostEqual(gravada["iva"], 16.0, places=2)
        self.assertAlmostEqual(gravada["total"], 116.0, places=2)
        self.assertAlmostEqual(gravada["descuento_monto"], 0.0, places=2)
        # Sin cobros conciliados no viajan formas de pago: las decide el
        # adaptador con el tipo de venta.
        self.assertEqual(vals["formas_pago"], [])

    def test_cancel_requires_emitted_document(self):
        # Nada que anular ante la imprenta si aún no se envió.
        move = self._invoice()
        with self.assertRaises(UserError):
            move.action_l10n_ve_edoc_cancel()

    def test_cancel_wizard_marks_cancelled_and_logs(self):
        move = self._invoice()
        move.action_l10n_ve_edoc_send()
        wizard = self.env["l10n.ve.edoc.cancel.wizard"].create({
            "move_id": move.id,
            "reason": "Error en los datos del comprador (prueba)",
        })
        wizard.action_confirm()
        self.assertEqual(move.l10n_ve_edoc_state, "cancelled")
        log = self.env["l10n.ve.edoc.log"].search([
            ("move_id", "=", move.id), ("endpoint", "=", "cancel")])
        self.assertTrue(log)
        self.assertTrue(log[0].ok)

    def test_cancel_failure_keeps_state_and_logs(self):
        # El fallo de la imprenta al anular NO revienta ni pierde el estado
        # 'assigned'; queda en la bitácora y en el campo de error, igual que
        # en el envío.
        move = self._invoice()
        move.action_l10n_ve_edoc_send()

        def boom(self, move, reason):
            raise ValueError("la imprenta no acepta la anulación")

        self.patch(
            type(self.env["l10n.ve.edoc.provider.dummy"]),
            "_edoc_cancel", boom)
        wizard = self.env["l10n.ve.edoc.cancel.wizard"].create({
            "move_id": move.id, "reason": "prueba"})
        result = wizard.action_confirm()
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(move.l10n_ve_edoc_state, "assigned")
        self.assertIn("no acepta", move.l10n_ve_edoc_error)
        log = self.env["l10n.ve.edoc.log"].search([
            ("move_id", "=", move.id), ("endpoint", "=", "cancel")])
        self.assertFalse(log[0].ok)

    def test_hka_url_resolution(self):
        # En pruebas SIEMPRE demo (aunque haya URL configurada): imposible
        # probar contra producción. En producción la URL es obligatoria.
        provider = self.env["l10n.ve.edoc.provider.hka"]
        self.company.l10n_ve_edoc_test = True
        self.company.l10n_ve_edoc_url = "https://prod.example.com/"
        self.assertEqual(provider._hka_base_url(self.company),
                         "https://demoemisionv2.thefactoryhka.com.ve")
        self.company.l10n_ve_edoc_test = False
        self.assertEqual(provider._hka_base_url(self.company),
                         "https://prod.example.com")
        self.company.l10n_ve_edoc_url = False
        with self.assertRaises(UserError):
            provider._hka_base_url(self.company)

    def test_hka_payload_maps_the_neutral_dict(self):
        # Traducción dict neutro → dialecto HKA, sin red: montos como
        # strings, comprador partido, desglose de IVA por código y forma de
        # pago por defecto. Es el formato del wiki del proveedor.
        move = self._invoice()
        vals = move._l10n_ve_edoc_document_vals()
        payload = self.env["l10n.ve.edoc.provider.hka"]._hka_payload(
            move, vals)
        doc = payload["documentoElectronico"]
        ident = doc["encabezado"]["identificacionDocumento"]
        self.assertEqual(ident["tipoDocumento"], "01")
        self.assertEqual(ident["numeroDocumento"], move.name)
        self.assertRegex(ident["horaEmision"], r"^\d{2}:\d{2}:\d{2}$")
        comprador = doc["encabezado"]["comprador"]
        self.assertEqual(comprador["tipoIdentificacion"], "J")
        self.assertEqual(comprador["numeroIdentificacion"], "987654321")
        totales = doc["encabezado"]["totales"]
        self.assertEqual(totales["montoGravadoTotal"], "100.00")
        self.assertEqual(totales["montoExentoTotal"], "50.00")
        self.assertEqual(totales["totalIVA"], "16.00")
        self.assertEqual(totales["totalAPagar"], "166.00")
        self.assertEqual(
            {imp["codigoTotalImp"] for imp in totales["impuestosSubtotal"]},
            {"G", "E"})
        self.assertTrue(totales["formasPago"],
                        "sin cobros, viaja una forma de pago por el total")
        self.assertEqual(totales["formasPago"][0]["monto"], "166.00")
        self.assertEqual(len(doc["detallesItems"]), 2)
        primera = doc["detallesItems"][0]
        self.assertEqual(primera["numeroLinea"], "1")
        self.assertEqual(primera["tasaIVA"], "16.00")
        self.assertEqual(primera["valorIVA"], "16.00")
        self.assertEqual(primera["codigoImpuesto"], "G")
        # El equivalente en Bs viaja cuando la moneda del documento no es la
        # de referencia configurada (aquí USD vs VES).
        bs_currency = self.company.l10n_ve_bs_currency_id
        if bs_currency and bs_currency != move.currency_id:
            self.assertIn("totalesOtraMoneda", doc["encabezado"])
            self.assertEqual(
                doc["encabezado"]["totalesOtraMoneda"]["moneda"],
                bs_currency.name)

    def test_hka_payload_credit_note_references_affected(self):
        invoice = self._invoice()
        reversal = self.env["account.move.reversal"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "journal_id": self.digital_journal.id,
            "reason": "prueba anulación parcial",
        })
        refund = self.env["account.move"].browse(
            reversal.reverse_moves()["res_id"])
        vals = refund._l10n_ve_edoc_document_vals()
        payload = self.env["l10n.ve.edoc.provider.hka"]._hka_payload(
            refund, vals)
        ident = payload["documentoElectronico"]["encabezado"][
            "identificacionDocumento"]
        self.assertEqual(ident["tipoDocumento"], "03")
        self.assertEqual(ident["numeroFacturaAfectada"], invoice.name)
        self.assertEqual(ident["montoFacturaAfectada"], "166.00")

    def test_provider_failure_does_not_break_accounting(self):
        # Un fallo del proveedor deja el documento en 'error' con su bitácora,
        # pero NUNCA tumba la factura ya contabilizada.
        move = self._invoice()

        def boom(self, move, vals):
            raise ValueError("la imprenta no responde")

        self.patch(
            type(self.env["l10n.ve.edoc.provider.dummy"]), "_edoc_send", boom)
        move.action_l10n_ve_edoc_send()
        self.assertEqual(move.l10n_ve_edoc_state, "error")
        self.assertIn("no responde", move.l10n_ve_edoc_error)
        self.assertEqual(move.state, "posted")
        log = self.env["l10n.ve.edoc.log"].search([("move_id", "=", move.id)])
        self.assertFalse(log[0].ok)
