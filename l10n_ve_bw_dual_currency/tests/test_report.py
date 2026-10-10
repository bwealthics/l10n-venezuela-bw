# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
"""Pruebas del PDF de la factura en doble moneda.

Se renderiza el HTML de `account.report_invoice` (el mismo QWeb del PDF) y se
lee con lxml: el texto visible con `text_content()` y los nodos por su
atributo `name`. Nunca se busca con regex sobre las etiquetas, porque QWeb
parte las cifras en `<span>` y el formato exacto depende del idioma.

Los montos esperados se formatean con `formatLang` (la cifra sola), el mismo
formateador que usa el widget monetario, así la prueba no depende del símbolo
de la moneda ni del separador de miles de la instalación.
"""
import lxml.html

from odoo.tests import tagged
from odoo.tools.misc import formatLang

from .test_dual_currency import DualCurrencyCommon


@tagged("post_install", "-at_install")
class TestDualReport(DualCurrencyCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 100 con IVA 16 % + 50 exentos a 610,5: cifras redondas y distintas
        # entre sí (61.050 / 30.525 / 9.768 / 101.343) para que cada una
        # sirva de huella en el texto del PDF.
        cls.invoice = cls._invoice("2026-07-25")

    # ------------------------------------------------------------------
    def _render(self, move):
        """(árbol lxml, texto visible con espacios normalizados)."""
        content = self.env["ir.actions.report"]._render_qweb_html(
            "account.report_invoice", move.ids)[0]
        doc = lxml.html.document_fromstring(content.decode("utf-8"))
        # split(): los montos llevan espacios duros entre símbolo y cifra.
        return doc, " ".join(doc.text_content().split())

    def _fmt(self, amount, currency=None):
        """Solo la cifra, con el separador del idioma (sin símbolo).

        Con `currency_obj`, formatLang antepone o pospone el símbolo según la
        moneda; el QWeb lo pinta con otro marcado, así que se compara la cifra.
        """
        currency = currency or self.bs
        return formatLang(self.env, amount, digits=currency.decimal_places)

    # ------------------------------------------------------------------
    def test_default_columns_and_totals(self):
        """Por defecto: «Importe Bs» por línea, sin «Precio Bs», totales a 3 columnas."""
        self.assertTrue(self.company.l10n_ve_show_line_amount_bs)
        self.assertFalse(self.company.l10n_ve_show_line_price_bs)
        doc, text = self._render(self.invoice)

        self.assertIn("Importe Bs", text)
        self.assertEqual(
            len(doc.xpath("//th[@name='th_l10n_ve_amount_bs']")), 1)
        self.assertNotIn("Precio Bs", text)
        self.assertFalse(doc.xpath("//th[@name='th_l10n_ve_price_bs']"))

        # El importe de cada línea, en Bs.
        self.assertIn(self._fmt(61050.0), text)
        self.assertIn(self._fmt(30525.0), text)
        # La tasa, en el bloque de información y en la nota legal.
        self.assertIn("Tasa BCV", text)
        self.assertIn(formatLang(self.env, 610.5, digits=4), text)
        self.assertIn("25-07-2026", text)
        self.assertIn("SNAT/2011/0071", text)

    def test_default_totals_table(self):
        doc, text = self._render(self.invoice)
        # Tabla de totales de 3 columnas: la fila de total trae USD y Bs.
        rows = doc.xpath("//tr[@name='l10n_ve_dual_total']")
        self.assertEqual(len(rows), 1)
        total_row = " ".join(rows[0].text_content().split())
        self.assertIn(self._fmt(101343.0), total_row)
        self.assertIn(
            self._fmt(166.0, self.company.currency_id), total_row)
        # El IVA, por grupo, en las dos monedas.
        tax_rows = doc.xpath("//tr[@name='l10n_ve_dual_tax']")
        self.assertTrue(tax_rows)
        tax_text = " ".join(
            " ".join(row.text_content().split()) for row in tax_rows)
        self.assertIn(self._fmt(9768.0), tax_text)
        self.assertIn(self._fmt(16.0, self.company.currency_id), tax_text)
        # Las 4 filas Bs de invoice_format sobran en modo dual.
        self.assertNotIn("Total en Bs", text)
        self.assertFalse(doc.xpath("//tr[@name='l10n_ve_bs_total']"))

    def test_price_bs_toggle(self):
        """«Precio Bs» solo aparece con el interruptor encendido."""
        self.company.l10n_ve_show_line_price_bs = True
        doc, text = self._render(self.invoice)
        self.assertIn("Precio Bs", text)
        self.assertEqual(
            len(doc.xpath("//th[@name='th_l10n_ve_price_bs']")), 1)
        # «Importe Bs» sigue ahí: son interruptores independientes.
        self.assertIn("Importe Bs", text)
        # Una celda de precio Bs por línea de producto.
        self.assertEqual(
            len(doc.xpath("//td[@name='td_l10n_ve_price_bs']")), 2)

        self.company.l10n_ve_show_line_price_bs = False
        doc, text = self._render(self.invoice)
        self.assertNotIn("Precio Bs", text)
        self.assertFalse(doc.xpath("//td[@name='td_l10n_ve_price_bs']"))

    def test_amount_bs_toggle_off(self):
        """Sin la columna «Importe Bs», los totales en Bs se siguen imprimiendo."""
        self.company.l10n_ve_show_line_amount_bs = False
        doc, text = self._render(self.invoice)
        self.assertNotIn("Importe Bs", text)
        self.assertFalse(doc.xpath("//th[@name='th_l10n_ve_amount_bs']"))
        self.assertTrue(doc.xpath("//tr[@name='l10n_ve_dual_total']"))
        self.assertIn(self._fmt(101343.0), text)

    def test_partial_payment_prints_bs_residual(self):
        """Con un cobro parcial el saldo pendiente sale también en Bs."""
        self._register_payment(
            self.invoice, amount=50.0, payment_date="2026-08-01")
        _doc, text = self._render(self.invoice)
        # 116 USD pendientes × 610,5 = 70.818 Bs (cifra que no aparece en
        # ninguna otra celda de la factura).
        self.assertIn(self._fmt(70818.0), text)

    def test_no_bs_block_without_rate(self):
        """Sin tasa no se imprime ninguna cifra Bs (serían ceros o dólares)."""
        inv = self._invoice("2025-01-15", post=False)
        inv._post()
        self.assertTrue(inv.l10n_ve_bs_rate_missing)
        doc, text = self._render(inv)
        self.assertNotIn("Importe Bs", text)
        self.assertNotIn("Tasa BCV", text)
        self.assertFalse(doc.xpath("//tr[@name='l10n_ve_dual_total']"))
        self.assertFalse(doc.xpath("//th[@name='th_l10n_ve_amount_bs']"))

    def test_no_bs_block_for_ves_invoice(self):
        """Una factura emitida en VES no se duplica en Bs."""
        bill = self._invoice(
            "2026-07-25", move_type="out_invoice",
            lines=[(1000.0, self.tax_iva16)], currency_id=self.bs.id)
        doc, text = self._render(bill)
        self.assertNotIn("Importe Bs", text)
        self.assertFalse(doc.xpath("//tr[@name='l10n_ve_dual_total']"))
