# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_printer. License LGPL-3.
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    # Sin default: URL vacía = impresora fiscal desactivada (el POS valida
    # normal). Solo se activa al configurar la caja que tiene el bridge.
    l10n_ve_bridge_url = fields.Char(
        string="URL del bridge fiscal",
        help="Bridge local en la PC de la caja, p.ej. http://localhost:5001. "
             "Vacío = sin impresora fiscal en esta caja.",
    )
    l10n_ve_bridge_token = fields.Char(
        string="Token del bridge fiscal",
        help="Debe coincidir con el token del config.json del bridge.",
    )
    l10n_ve_default_payment_code = fields.Char(
        string="Código de pago fiscal por defecto",
        default="01",
        help="Slot de medio de pago de la máquina usado al imprimir desde el "
             "backend (facturas sin pagos POS).",
    )
    # Vacío = esta caja NO tiene salida de contingencia. Es el default seguro:
    # sin diario, el POS sigue bloqueando la venta si falla la máquina.
    l10n_ve_contingency_journal_id = fields.Many2one(
        "account.journal",
        string="Diario de contingencia",
        domain="[('l10n_ve_emission_channel', '=', 'contingencia'),"
               " ('company_id', '=', company_id)]",
        help="Diario donde se registran las ventas facturadas a mano en el "
             "talonario mientras la máquina fiscal está caída. No debe tener "
             "la cadena de hash activada: replica un documento de papel.",
    )
    l10n_ve_hide_precuenta = fields.Boolean(
        string="Ocultar pre-cuenta (Bill)",
        help="Oculta el botón Bill del POS Restaurante: el art. 49 de la "
             "PA 0071 prohíbe entregar notas de consumo/pre-cuentas con "
             "montos como documento sustitutivo de la factura fiscal.",
    )
    # l10n_ve_machine_serial ya existe (l10n_ve_bw_fiscal_books): se reusa.

    def l10n_ve_get_ves_rate(self):
        """Bolívares por 1 unidad de la moneda de la compañía, a la tasa BCV
        de hoy. La llama el frontend al validar cada orden."""
        self.ensure_one()
        ves = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "VES")], limit=1)
        if not ves:
            return 0.0
        company = self.company_id
        if ves != company.currency_id and not self.env["res.currency.rate"].search_count([
                ("currency_id", "=", ves.id),
                ("company_id", "in", (False, company.id)),
                ("name", "<=", fields.Date.context_today(self))], limit=1):
            # Sin filas de tasa, _convert usaría la tasa implícita 1.0 y toda
            # factura saldría en Bs = USD (≈730x menos). Mejor 0.0 y bloquear.
            return 0.0
        # round=False: el Libro de Ventas convierte a precisión completa; una
        # tasa truncada desviaría los totales Z vs Libro unos Bs por día.
        return company.currency_id._convert(
            1.0, ves, company, fields.Date.context_today(self), round=False)
