# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
import base64
import io
from datetime import datetime, time

import pytz
import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# También es el orden de las columnas numéricas en las tablas de detalle
AMOUNT_KEYS = (
    "total", "base_16", "tax_16", "base_8", "tax_8",
    "base_31", "tax_31", "exempt", "wh_iva",
)

# Orden y rótulo de los sub-bloques del art. 76 cuando hay más de un canal de
# emisión en el período. Es una TUPLA, no un dict, para que el orden del libro
# sea estable entre corridas.
CHANNEL_LABELS = (
    ("mf", "Emitidas por máquina fiscal"),
    ("digital", "Emitidas por imprenta digital (medios electrónicos)"),
    ("libre", "Emitidas sobre forma libre de imprenta autorizada"),
    ("contingencia", "Emitidas en contingencia (talonario)"),
    (False, "Sin canal de emisión declarado"),
)


class L10nVeFiscalBookWizard(models.TransientModel):
    _name = "l10n.ve.fiscal.book.wizard"
    _description = "Asistente de Libros Fiscales (Venezuela)"

    company_id = fields.Many2one(
        "res.company", string="Compañía", required=True,
        default=lambda self: self.env.company)
    date_from = fields.Date(
        string="Desde", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string="Hasta", required=True,
        default=lambda self: fields.Date.context_today(self))
    book_type = fields.Selection(
        [("sale", "Libro de Ventas"), ("purchase", "Libro de Compras")],
        string="Tipo de libro", required=True, default="sale")
    file = fields.Binary(string="Archivo generado", readonly=True)
    filename = fields.Char(string="Nombre del archivo")

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_(
                    "La fecha inicial debe ser anterior o igual a la fecha final."))

    # ------------------------------------------------------------------
    # Acción principal
    # ------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        ves = self._get_ves_currency()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        try:
            if self.book_type == "sale":
                self._write_sale_book(workbook, ves)
            else:
                self._write_purchase_book(workbook, ves)
        finally:
            workbook.close()
        label = "ventas" if self.book_type == "sale" else "compras"
        self.write({
            "file": base64.b64encode(output.getvalue()),
            "filename": "libro_%s_%s_%s.xlsx" % (
                label,
                self.date_from.strftime("%Y%m%d"),
                self.date_to.strftime("%Y%m%d"),
            ),
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Libros Fiscales (VE)"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    # ------------------------------------------------------------------
    # Helpers de datos
    # ------------------------------------------------------------------
    def _get_ves_currency(self):
        ves = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "VES")], limit=1)
        if not ves:
            raise UserError(_(
                "No existe la moneda VES (Bolívar) en el sistema. Es necesaria "
                "para expresar los libros fiscales en bolívares a la tasa BCV."))
        return ves

    def _to_ves(self, amount, ves, date, currency=None):
        currency = currency or self.company_id.currency_id
        if not amount:
            return 0.0
        return currency._convert(amount, ves, self.company_id, date)

    @staticmethod
    def _rate_key(rate):
        for key, value in (("16", 16.0), ("8", 8.0), ("31", 31.0)):
            if abs(rate - value) < 0.011:
                return key
        # alícuota gravada no estándar: se agrupa en la general
        return "16"

    @staticmethod
    def _get_doc_type(move):
        if move.move_type in ("out_refund", "in_refund"):
            return "03", move.reversed_entry_id.name or ""
        # debit_origin_id existe solo con account_debit_note instalado
        if "debit_origin_id" in move._fields and move.debit_origin_id:
            return "02", move.debit_origin_id.name or ""
        return "01", ""

    def _get_sale_moves(self):
        # Las facturas emitidas desde el POS a contribuyentes se listan POR
        # DOCUMENTO en el bloque del art. 76 (con su Nº de factura y Nº de
        # control), igual que el resto de facturas de cliente. Solo las
        # órdenes POS NO facturadas van al resumen diario del art. 77; los
        # asientos de cierre de sesión (move_type 'entry') quedan fuera por
        # el filtro de tipo de documento.
        return self.env["account.move"].search([
            ("company_id", "=", self.company_id.id),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ], order="date, name")

    def _get_purchase_moves(self):
        return self.env["account.move"].search([
            ("company_id", "=", self.company_id.id),
            ("move_type", "in", ("in_invoice", "in_refund")),
            ("state", "=", "posted"),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ], order="date, name")

    def _prepare_move_row(self, move, ves):
        sign = -1.0 if move.move_type in ("out_refund", "in_refund") else 1.0
        # Dirección contable del documento: factor × balance da las líneas
        # normales en positivo y NETEA las negativas (p. ej. la deducción de
        # un anticipo) en vez de sumarlas en valor absoluto; a las NC les da
        # su signo sin doble multiplicación.
        factor = -1.0 if move.is_sale_document(include_receipts=True) else 1.0
        vals = dict.fromkeys(AMOUNT_KEYS, 0.0)
        # Base por la alícuota COMBINADA de cada línea (IVA 16% + adicional
        # 15% => 31%, también como grupo de impuestos): se cuenta UNA sola
        # vez aunque varios impuestos compartan la misma base. Iterar las
        # tax lines sumando tax_base_amount la duplicaría (cada impuesto
        # repite la base completa) y clasificaría el 15% como "16".
        tax_keys = {}  # tax.id -> {rate_key: base de sus líneas en esa combinación}
        exempt = 0.0
        for line in move.invoice_line_ids.filtered(
                lambda l: l.display_type == "product"):
            amount = factor * line.balance
            leaf_taxes = line.tax_ids
            group_taxes = leaf_taxes.filtered(lambda t: t.amount_type == "group")
            leaf_taxes = (leaf_taxes - group_taxes) | group_taxes.children_tax_ids
            rate = round(sum(t.amount for t in leaf_taxes), 2)
            if not rate:
                exempt += amount
                continue
            key = self._rate_key(rate)
            vals["base_%s" % key] += self._to_ves(amount, ves, move.date)
            for tax in leaf_taxes:
                if tax.amount:
                    shares = tax_keys.setdefault(tax.id, {})
                    shares[key] = shares.get(key, 0.0) + amount
        # IVA desde las líneas de impuesto (montos contabilizados exactos),
        # en la columna de la alícuota combinada de sus líneas base; un
        # impuesto usado en combinaciones distintas dentro del documento se
        # reparte proporcional a la base de cada combinación.
        for line in move.line_ids.filtered("tax_line_id"):
            if not line.tax_line_id.amount:
                continue
            amount = factor * line.balance
            shares = tax_keys.get(line.tax_line_id.id) or {
                self._rate_key(line.tax_line_id.amount): 1.0}
            total_share = sum(shares.values())
            for key, share in shares.items():
                part = amount * share / total_share if total_share else 0.0
                vals["tax_%s" % key] += self._to_ves(part, ves, move.date)
        vals["exempt"] = self._to_ves(exempt, ves, move.date)
        vals["total"] = sign * self._to_ves(
            abs(move.amount_total_signed), ves, move.date)
        doc_type, affected = self._get_doc_type(move)
        if move.move_type in ("in_invoice", "in_refund"):
            number = move.ref or move.name
            vals["wh_iva"], vals["wh_voucher"] = self._get_wh_iva_data(move, ves)
        else:
            number = move.name
            vals["wh_iva"], vals["wh_voucher"] = \
                self._get_wh_iva_received_data(move, ves)
        partner = move.commercial_partner_id
        vals.update({
            "date": move.invoice_date or move.date,
            "number": number,
            "control": move.l10n_ve_control_number or "",
            "partner": partner.name or "",
            "vat": partner.vat or "",
            "doc_type": doc_type,
            "affected": affected,
        })
        return vals

    def _get_wh_iva_data(self, move, ves):
        """IVA retenido al proveedor + nº de comprobante, leídos de la
        interfaz canónica del módulo l10n_ve_bw_wh_iva (modelo
        l10n.ve.iva.wh.voucher) SOLO si está instalado (sin dependencia
        dura). El monto por documento lo aporta el método público
        _l10n_ve_get_amount_for_move, en moneda de la compañía."""
        Voucher = self.env.get("l10n.ve.iva.wh.voucher")
        if Voucher is None or not hasattr(Voucher, "_l10n_ve_get_amount_for_move"):
            return 0.0, ""
        vouchers = Voucher.sudo().search([
            ("company_id", "=", self.company_id.id),
            ("move_ids", "in", move.id),
            ("state", "=", "posted"),
        ])
        if not vouchers:
            return 0.0, ""
        amount = sum(
            voucher._l10n_ve_get_amount_for_move(move) for voucher in vouchers)
        numbers = ", ".join(n for n in vouchers.mapped("number") if n)
        return self._to_ves(amount, ves, move.date), numbers

    def _get_wh_iva_received_data(self, move, ves):
        """IVA que NOS retuvieron los clientes (agentes de retención) al
        pagar la factura, leído de los pagos conciliados con el documento
        (account.move.matched_payment_ids) cuando el módulo l10n_ve_bw_wh_iva
        está instalado; sin él los campos no existen y se reporta 0."""
        if "l10n_ve_iva_wh_received_amount" not in self.env["account.payment"]._fields:
            return 0.0, ""
        amount = 0.0
        numbers = []
        payments = move.matched_payment_ids.filtered(
            lambda p: p.state not in ("draft", "canceled", "rejected"))
        for payment in payments:
            wh = getattr(payment, "l10n_ve_iva_wh_received_amount", 0.0)
            if not wh:
                continue
            # Un pago agrupado puede abarcar varias facturas: la retención
            # se prorratea por el total de cada documento para no duplicarla
            # en el libro ni en el resumen del período.
            sale_docs = payment.invoice_ids.filtered(
                lambda m: m.is_sale_document(include_receipts=True))
            total = sum(abs(doc.amount_total_signed) for doc in sale_docs)
            share = abs(move.amount_total_signed) / total if total else 1.0
            # La retención se practicó en la fecha del pago: se expresa en Bs
            # a la tasa BCV de esa fecha (la del comprobante recibido).
            amount += self._to_ves(
                wh * share, ves, payment.date, currency=payment.currency_id)
            number = getattr(payment, "l10n_ve_iva_wh_received_number", "") or ""
            if number and number not in numbers:
                numbers.append(number)
        return amount, ", ".join(numbers)

    def _get_pos_day_rows(self, ves):
        """Ventas a NO contribuyentes (art. 77): una fila por sesión POS
        cerrada y día, con rango de órdenes y totales del día en Bs. Las
        órdenes FACTURADAS (account_move) se excluyen: sus facturas van por
        documento en el bloque del art. 76."""
        # pos.order.date_order es Datetime UTC naive: los límites del período
        # se construyen en la zona horaria del usuario (la misma que usa
        # context_timestamp para agrupar por día) y se convierten a UTC.
        tz_name = self.env.context.get("tz") or self.env.user.tz
        tz = pytz.timezone(tz_name) if tz_name else pytz.utc
        start = tz.localize(
            datetime.combine(self.date_from, time.min),
        ).astimezone(pytz.utc).replace(tzinfo=None)
        stop = tz.localize(
            datetime.combine(self.date_to, time.max),
        ).astimezone(pytz.utc).replace(tzinfo=None)
        # sudo: el libro es un reporte legal de solo lectura que agrega TODAS
        # las ventas; el contador que lo genera no requiere rol de POS.
        orders = self.env["pos.order"].sudo().search([
            ("company_id", "=", self.company_id.id),
            ("date_order", ">=", start),
            ("date_order", "<=", stop),
            ("state", "in", ("paid", "done")),
            ("account_move", "=", False),
            ("session_id.state", "=", "closed"),
            # Las de contingencia NO pasaron por la máquina: dentro de la fila
            # resumen del art. 77 los totales no cuadrarían contra el Reporte
            # Z. Van en su propio bloque, documento por documento.
            ("l10n_ve_contingency_control", "=", False),
        ], order="date_order, name")
        groups = {}
        for order in orders:
            day = fields.Datetime.context_timestamp(self, order.date_order).date()
            key = (order.session_id.id, day)
            groups.setdefault(key, {
                "session": order.session_id,
                "day": day,
                "orders": [],
            })["orders"].append(order)
        rows = []
        for group in sorted(groups.values(), key=lambda g: (g["day"], g["session"].id)):
            vals = dict.fromkeys(AMOUNT_KEYS, 0.0)
            day = group["day"]
            for order in group["orders"]:
                self._add_pos_order_amounts(vals, order, day, ves)
            vals["total"] = sum(
                vals[k] for k in AMOUNT_KEYS if k not in ("total", "wh_iva"))
            names = sorted(order.name or "" for order in group["orders"])
            config = group["session"].config_id
            vals.update({
                "date": day,
                "machine": config.l10n_ve_machine_serial or config.name or "",
                "session": group["session"].name or "",
                "first_order": names[0],
                "last_order": names[-1],
            })
            rows.append(vals)
        return rows

    def _add_pos_order_amounts(self, vals, order, day, ves):
        """Acumula en `vals` las bases e IVA de una orden POS, en Bs."""
        currency = order.currency_id
        for line in order.lines:
            base = self._to_ves(
                line.price_subtotal, ves, day, currency=currency)
            tax_amount = self._to_ves(
                line.price_subtotal_incl - line.price_subtotal,
                ves, day, currency=currency)
            # Alícuota COMBINADA de la línea (16+15 => 31, también como
            # grupo): con "el primer impuesto" el gap completo caería en
            # "16", y un grupo (amount propio 0) caería en exento.
            taxes = line.tax_ids
            group_taxes = taxes.filtered(lambda t: t.amount_type == "group")
            taxes = (taxes - group_taxes) | group_taxes.children_tax_ids
            rate = round(sum(tax.amount for tax in taxes), 2)
            if rate:
                key = self._rate_key(rate)
                vals["base_%s" % key] += base
                vals["tax_%s" % key] += tax_amount
            else:
                vals["exempt"] += base + tax_amount

    def _get_pos_contingency_rows(self, ves):
        """Órdenes POS facturadas a mano en el talonario (PA 0071 art. 11).

        Una fila POR ORDEN, no una fila resumen: cada formato del talonario es
        un documento con su propio Nº de control. Solo las NO facturadas —las
        que sí generaron factura ya salen en el bloque I, en el sub-bloque de
        su canal— para no contarlas dos veces.
        """
        tz_name = self.env.context.get("tz") or self.env.user.tz
        tz = pytz.timezone(tz_name) if tz_name else pytz.utc
        start = tz.localize(
            datetime.combine(self.date_from, time.min),
        ).astimezone(pytz.utc).replace(tzinfo=None)
        stop = tz.localize(
            datetime.combine(self.date_to, time.max),
        ).astimezone(pytz.utc).replace(tzinfo=None)
        orders = self.env["pos.order"].sudo().search([
            ("company_id", "=", self.company_id.id),
            ("date_order", ">=", start),
            ("date_order", "<=", stop),
            ("state", "in", ("paid", "done")),
            ("account_move", "=", False),
            ("session_id.state", "=", "closed"),
            ("l10n_ve_contingency_control", "!=", False),
        ], order="date_order, name")
        rows = []
        for order in orders:
            day = fields.Datetime.context_timestamp(self, order.date_order).date()
            vals = dict.fromkeys(AMOUNT_KEYS, 0.0)
            self._add_pos_order_amounts(vals, order, day, ves)
            vals["total"] = sum(
                vals[k] for k in AMOUNT_KEYS if k not in ("total", "wh_iva"))
            partner = order.partner_id
            vals.update({
                "date": day,
                "number": order.name or "",
                "control": order.l10n_ve_contingency_control or "",
                "partner": partner.name or "CONSUMIDOR FINAL",
                "vat": partner.vat or "",
                "doc_type": "01",
                "affected": "",
                "wh_voucher": "",
            })
            rows.append(vals)
        return rows

    # ------------------------------------------------------------------
    # Helpers XLSX
    # ------------------------------------------------------------------
    def _get_formats(self, workbook):
        return {
            "title": workbook.add_format({"bold": True, "font_size": 13}),
            "bold": workbook.add_format({"bold": True}),
            "section": workbook.add_format(
                {"bold": True, "font_size": 11, "font_color": "#1F4E78"}),
            "header": workbook.add_format({
                "bold": True, "bg_color": "#D9E1F2", "border": 1,
                "text_wrap": True, "align": "center", "valign": "vcenter"}),
            "text": workbook.add_format({"border": 1}),
            "num": workbook.add_format({"border": 1, "num_format": "#,##0.00"}),
            "total_label": workbook.add_format(
                {"bold": True, "border": 1, "bg_color": "#F2F2F2"}),
            "total_num": workbook.add_format({
                "bold": True, "border": 1, "bg_color": "#F2F2F2",
                "num_format": "#,##0.00"}),
        }

    def _write_book_header(self, sheet, fmts, title):
        company = self.company_id
        sheet.write(0, 0, company.name or "", fmts["title"])
        sheet.write(1, 0, "RIF: %s" % (company.vat or ""), fmts["bold"])
        sheet.write(2, 0, title, fmts["title"])
        sheet.write(3, 0, "Período: %s al %s — montos expresados en Bs" % (
            self.date_from.strftime("%d/%m/%Y"),
            self.date_to.strftime("%d/%m/%Y")), fmts["bold"])
        return 5

    def _write_sale_detail_by_channel(self, sheet, fmts, row, headers, ves):
        """Bloque I partido por canal de emisión, con subtotal por canal.

        La PA SNAT/2024/000102 art. 6 obliga a registrar en forma SEPARADA las
        operaciones emitidas por medios electrónicos. Si todos los documentos
        del período salieron por el mismo canal —o si aún no se configuró
        ninguno— se escribe una sola tabla, igual que antes: el libro no cambia
        hasta que el canal se usa de verdad.
        """
        by_channel = {}
        for move in self._get_sale_moves():
            by_channel.setdefault(
                move.journal_id.l10n_ve_emission_channel, []).append(move)
        totals = dict.fromkeys(AMOUNT_KEYS, 0.0)
        split = len(by_channel) > 1
        for channel, label in CHANNEL_LABELS:
            moves = by_channel.get(channel)
            if not moves:
                continue
            if split:
                sheet.write(row, 0, "  %s" % label, fmts["section"])
                row += 1
            move_rows = [self._prepare_move_row(move, ves) for move in moves]
            row, block = self._write_detail_table(
                sheet, fmts, row, headers, move_rows, with_voucher=True)
            for key in AMOUNT_KEYS:
                totals[key] += block[key]
        return row, totals

    def _write_detail_table(self, sheet, fmts, row, headers, move_rows,
                            with_voucher=False):
        """Tabla de detalle por documento; devuelve (fila siguiente, totales)."""
        for col, header in enumerate(headers):
            sheet.write(row, col, header, fmts["header"])
        row += 1
        totals = dict.fromkeys(AMOUNT_KEYS, 0.0)
        for vals in move_rows:
            sheet.write(row, 0, vals["date"].strftime("%d/%m/%Y"), fmts["text"])
            sheet.write(row, 1, vals["number"] or "", fmts["text"])
            sheet.write(row, 2, vals["control"], fmts["text"])
            sheet.write(row, 3, vals["partner"], fmts["text"])
            sheet.write(row, 4, vals["vat"], fmts["text"])
            sheet.write(row, 5, vals["doc_type"], fmts["text"])
            sheet.write(row, 6, vals["affected"], fmts["text"])
            for offset, key in enumerate(AMOUNT_KEYS):
                sheet.write_number(
                    row, 7 + offset, round(vals[key], 2), fmts["num"])
                totals[key] += vals[key]
            if with_voucher:
                sheet.write(
                    row, 7 + len(AMOUNT_KEYS), vals["wh_voucher"],
                    fmts["text"])
            row += 1
        sheet.write(row, 0, "TOTALES", fmts["total_label"])
        for col in range(1, 7):
            sheet.write(row, col, "", fmts["total_label"])
        for offset, key in enumerate(AMOUNT_KEYS):
            sheet.write_number(
                row, 7 + offset, round(totals[key], 2), fmts["total_num"])
        if with_voucher:
            sheet.write(row, 7 + len(AMOUNT_KEYS), "", fmts["total_label"])
        return row + 2, totals

    def _write_summary(self, sheet, fmts, row, totals, tax_label, wh_label):
        sheet.write(row, 0, "RESUMEN DEL PERÍODO (Art. 72)", fmts["section"])
        row += 1
        for col, header in enumerate(
                ["Concepto", "Base Imponible", tax_label]):
            sheet.write(row, col, header, fmts["header"])
        row += 1
        lines = [
            ("Operaciones gravadas — alícuota general 16%",
             totals["base_16"], totals["tax_16"]),
            ("Operaciones gravadas — alícuota reducida 8%",
             totals["base_8"], totals["tax_8"]),
            ("Operaciones gravadas — alícuota general + adicional 31%",
             totals["base_31"], totals["tax_31"]),
            ("Operaciones exentas, exoneradas o no sujetas",
             totals["exempt"], 0.0),
        ]
        for label, base, tax in lines:
            sheet.write(row, 0, label, fmts["text"])
            sheet.write_number(row, 1, round(base, 2), fmts["num"])
            sheet.write_number(row, 2, round(tax, 2), fmts["num"])
            row += 1
        total_base = totals["base_16"] + totals["base_8"] + totals["base_31"] \
            + totals["exempt"]
        total_tax = totals["tax_16"] + totals["tax_8"] + totals["tax_31"]
        sheet.write(row, 0, "TOTALES", fmts["total_label"])
        sheet.write_number(row, 1, round(total_base, 2), fmts["total_num"])
        sheet.write_number(row, 2, round(total_tax, 2), fmts["total_num"])
        row += 1
        sheet.write(row, 0, wh_label, fmts["total_label"])
        sheet.write(row, 1, "", fmts["total_label"])
        sheet.write_number(
            row, 2, round(totals["wh_iva"], 2), fmts["total_num"])
        return row + 1

    # ------------------------------------------------------------------
    # Libro de Ventas
    # ------------------------------------------------------------------
    def _write_sale_book(self, workbook, ves):
        fmts = self._get_formats(workbook)
        sheet = workbook.add_worksheet("Libro de Ventas")
        sheet.set_column(0, 0, 11)
        sheet.set_column(1, 2, 18)
        sheet.set_column(3, 3, 40)
        sheet.set_column(4, 4, 14)
        sheet.set_column(5, 5, 9)
        sheet.set_column(6, 6, 18)
        sheet.set_column(7, 15, 15)
        sheet.set_column(16, 16, 22)
        row = self._write_book_header(sheet, fmts, "LIBRO DE VENTAS")

        sheet.write(
            row, 0,
            "I. VENTAS A CONTRIBUYENTES — una fila por documento (Art. 76)",
            fmts["section"])
        row += 1
        headers = [
            "Fecha", "Nº de Documento", "Nº de Control", "Razón Social",
            "RIF", "Tipo Doc.", "Nº Doc. Afectado", "Total Documento",
            "Base Gravada 16%", "IVA 16%", "Base Gravada 8%", "IVA 8%",
            "Base Gravada 31%", "IVA 31%", "Exento/No Gravado", "IVA Retenido",
            "Nº Comprobante de Retención",
        ]
        row, block1 = self._write_sale_detail_by_channel(
            sheet, fmts, row, headers, ves)

        sheet.write(
            row, 0,
            "II. VENTAS A NO CONTRIBUYENTES — resumen diario por máquina/"
            "sesión POS (Art. 77)",
            fmts["section"])
        row += 1
        headers2 = [
            "Fecha", "Nº Registro de Máquina", "Sesión",
            "Primera Orden del Día", "Última Orden del Día",
            "Total Gravado", "IVA", "Exento/No Gravado",
        ]
        for col, header in enumerate(headers2):
            sheet.write(row, col, header, fmts["header"])
        row += 1
        pos_rows = self._get_pos_day_rows(ves)
        block2 = dict.fromkeys(AMOUNT_KEYS, 0.0)
        for vals in pos_rows:
            taxable = vals["base_16"] + vals["base_8"] + vals["base_31"]
            tax = vals["tax_16"] + vals["tax_8"] + vals["tax_31"]
            sheet.write(row, 0, vals["date"].strftime("%d/%m/%Y"), fmts["text"])
            sheet.write(row, 1, vals["machine"], fmts["text"])
            sheet.write(row, 2, vals["session"], fmts["text"])
            sheet.write(row, 3, vals["first_order"], fmts["text"])
            sheet.write(row, 4, vals["last_order"], fmts["text"])
            sheet.write_number(row, 5, round(taxable, 2), fmts["num"])
            sheet.write_number(row, 6, round(tax, 2), fmts["num"])
            sheet.write_number(row, 7, round(vals["exempt"], 2), fmts["num"])
            for key in AMOUNT_KEYS:
                block2[key] += vals[key]
            row += 1
        sheet.write(row, 0, "TOTALES", fmts["total_label"])
        for col in range(1, 5):
            sheet.write(row, col, "", fmts["total_label"])
        sheet.write_number(row, 5, round(
            block2["base_16"] + block2["base_8"] + block2["base_31"], 2),
            fmts["total_num"])
        sheet.write_number(row, 6, round(
            block2["tax_16"] + block2["tax_8"] + block2["tax_31"], 2),
            fmts["total_num"])
        sheet.write_number(
            row, 7, round(block2["exempt"], 2), fmts["total_num"])
        row += 2

        # III. Ventas facturadas a mano durante una falla de la máquina.
        # Van fuera del resumen del art. 77 pero SÍ dentro del total del
        # período: son ventas del mes como cualquier otra.
        contingency_rows = self._get_pos_contingency_rows(ves)
        block3 = dict.fromkeys(AMOUNT_KEYS, 0.0)
        if contingency_rows:
            sheet.write(
                row, 0,
                "III. VENTAS EN CONTINGENCIA — facturadas en talonario "
                "autorizado (PA 0071 Art. 11)",
                fmts["section"])
            row += 1
            row, block3 = self._write_detail_table(
                sheet, fmts, row, headers, contingency_rows, with_voucher=True)

        combined = {
            key: block1[key] + block2[key] + block3[key] for key in AMOUNT_KEYS
        }
        self._write_summary(
            sheet, fmts, row, combined,
            tax_label="Débito Fiscal",
            wh_label="IVA retenido por agentes de retención")

    # ------------------------------------------------------------------
    # Libro de Compras
    # ------------------------------------------------------------------
    def _write_purchase_book(self, workbook, ves):
        fmts = self._get_formats(workbook)
        sheet = workbook.add_worksheet("Libro de Compras")
        sheet.set_column(0, 0, 11)
        sheet.set_column(1, 2, 18)
        sheet.set_column(3, 3, 40)
        sheet.set_column(4, 4, 14)
        sheet.set_column(5, 5, 9)
        sheet.set_column(6, 6, 18)
        sheet.set_column(7, 15, 15)
        sheet.set_column(16, 16, 22)
        row = self._write_book_header(sheet, fmts, "LIBRO DE COMPRAS")

        sheet.write(
            row, 0,
            "COMPRAS NACIONALES E IMPORTACIONES — una fila por documento "
            "(Art. 75)",
            fmts["section"])
        row += 1
        headers = [
            "Fecha", "Nº de Factura", "Nº de Control", "Proveedor", "RIF",
            "Tipo Doc.", "Nº Doc. Afectado", "Total Documento",
            "Base Gravada 16%", "Crédito Fiscal 16%",
            "Base Gravada 8%", "Crédito Fiscal 8%",
            "Base Gravada 31%", "Crédito Fiscal 31%",
            "Exento/Sin Derecho a Crédito", "IVA Retenido al Proveedor",
            "Nº Comprobante de Retención",
        ]
        move_rows = [
            self._prepare_move_row(move, ves)
            for move in self._get_purchase_moves()
        ]
        row, totals = self._write_detail_table(
            sheet, fmts, row, headers, move_rows, with_voucher=True)

        self._write_summary(
            sheet, fmts, row, totals,
            tax_label="Crédito Fiscal",
            wh_label="IVA retenido a proveedores (como agente de retención)")
