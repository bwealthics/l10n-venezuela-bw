# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
from odoo import _, models
from odoo.exceptions import UserError


class L10nVeFiscalBookWizard(models.TransientModel):
    _inherit = "l10n.ve.fiscal.book.wizard"

    def _l10n_ve_dual_uses_bs(self, ves):
        """True si el libro se pide en el bolívar de la compañía.

        Si el libro se pidiera en otra moneda, los Bs almacenados no aplican
        y se deja la conversión original.
        """
        return ves == self.company_id.l10n_ve_bs_currency_id

    def _l10n_ve_dual_check_rates(self, ves):
        """Aborta si algún documento del libro no tiene tasa Bs.

        Sin tasa los Bs almacenados valen 0 y la conversión original
        (``_convert``) terminaría en ``COALESCE(..., 1.0)``: pondría montos
        en la moneda de la compañía (USD) en las columnas de Bs sin avisar.
        Es preferible detener el libro y listar los asientos que dejarlo
        mal en silencio.
        """
        if not self._l10n_ve_dual_uses_bs(ves):
            return
        if self.book_type == "sale":
            moves = self._get_sale_moves()
        else:
            moves = self._get_purchase_moves()
        # Un documento sin tasa pero con todas sus líneas en Bs (p. ej. una
        # factura de proveedor en VES anterior a la primera tasa cargada)
        # tiene sus Bs exactos: solo bloquean los que dejaron líneas en otra
        # moneda sin convertir.
        missing = moves.filtered(
            lambda m: m.l10n_ve_bs_rate_missing and any(
                line.currency_id != ves
                and not line.company_currency_id.is_zero(line.balance)
                for line in m.line_ids))
        if missing:
            raise UserError(_(
                "No hay tasa BCV registrada para %(count)s documento(s) del "
                "período, así que no se pueden expresar en bolívares. Cargue "
                "la tasa en Monedas y vuelva a generar el libro. Ejemplos: "
                "%(names)s",
                count=len(missing),
                names=", ".join(missing[:10].mapped(
                    lambda m: m.name or str(m.id))),
            ))

    def action_generate(self):
        # Se valida ANTES de armar el XLSX, con una sola consulta de los
        # documentos del período.
        self.ensure_one()
        self._l10n_ve_dual_check_rates(self._get_ves_currency())
        return super().action_generate()

    def _l10n_ve_line_ves(self, line, factor, ves):
        # Bs del apunte con la tasa congelada del asiento: el libro iguala
        # al Diario/Mayor y no depende de la tabla de tasas del día.
        if self._l10n_ve_dual_uses_bs(ves):
            return factor * line.l10n_ve_balance_bs
        return super()._l10n_ve_line_ves(line, factor, ves)

    def _l10n_ve_move_total_ves(self, move, ves):
        if self._l10n_ve_dual_uses_bs(ves):
            # abs(): el total del documento va siempre positivo; el signo de
            # las notas de crédito lo aplica el llamador.
            return abs(move.l10n_ve_amount_total_bs)
        return super()._l10n_ve_move_total_ves(move, ves)

    def _l10n_ve_amount_ves(self, move, amount, ves):
        # El IVA retenido se convierte a la tasa CONGELADA del asiento (la
        # misma del IVA de la fila) y no a la de move.date: en facturas con
        # fecha de factura distinta de la contable, la retención dejaría de
        # ser el 75 %/100 % del IVA mostrado. ``amount`` viene en moneda de
        # la compañía y la tasa del asiento son Bs por 1 de esa moneda.
        if self._l10n_ve_dual_uses_bs(ves):
            # Proporción del IVA Bs ALMACENADO del documento: en las facturas
            # de proveedor emitidas en VES el comprobante trae la retención en
            # USD redondeada a céntimos, y multiplicarla por la tasa se
            # desviaría unos bolívares del 75 %/100 % exacto del IVA en Bs.
            tax_lines = move.line_ids.filtered(lambda l: l.display_type == "tax")
            tax_company = abs(sum(tax_lines.mapped("balance")))
            tax_bs = abs(sum(tax_lines.mapped("l10n_ve_balance_bs")))
            if tax_company and tax_bs:
                return ves.round(amount / tax_company * tax_bs)
            if move.l10n_ve_bs_rate:
                return ves.round(amount * move.l10n_ve_bs_rate)
        return super()._l10n_ve_amount_ves(move, amount, ves)
