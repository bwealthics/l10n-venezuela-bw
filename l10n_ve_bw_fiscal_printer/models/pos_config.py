# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_printer. License LGPL-3.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    # Caja SIN máquina fiscal que factura sobre papelería de imprenta
    # autorizada de forma sostenida (no como respaldo de un bridge caído).
    # Con bridge configurado este selector se ignora: manda la máquina.
    l10n_ve_paper_mode = fields.Selection(
        [("contingencia", "Talonario (contingencia)"),
         ("libre", "Formas libres")],
        string="Facturación en papel (VE)",
        help="Talonario: factura manuscrita (PA 0071 art. 11); el POS pide el "
             "Nº de factura y el Nº de control preimpresos y genera la "
             "factura en el diario de contingencia.\n"
             "Formas libres: el POS pide solo el Nº de control preimpreso de "
             "la hoja y factura en el diario de la caja (canal libre); el "
             "contenido se imprime desde Odoo.\n"
             "Vacío = sin salida en papel.",
    )
    l10n_ve_paper_batch_id = fields.Many2one(
        "l10n.ve.paper.batch",
        string="Lote de papelería activo",
        domain="[('company_id', '=', company_id)]",
        help="Talonario o caja de formas libres en uso: de aquí salen la "
             "propuesta del siguiente correlativo, la validación de rango y "
             "duplicados y el aviso de agotamiento.",
    )
    # l10n_ve_machine_serial ya existe (l10n_ve_bw_fiscal_books): se reusa.

    @api.constrains("l10n_ve_paper_mode", "l10n_ve_contingency_journal_id",
                    "invoice_journal_id", "l10n_ve_paper_batch_id")
    def _check_l10n_ve_paper_mode(self):
        for config in self:
            mode = config.l10n_ve_paper_mode
            if not mode:
                continue
            if mode == "contingencia" and not config.l10n_ve_contingency_journal_id:
                raise ValidationError(_(
                    "La facturación por talonario exige asignar el diario de "
                    "contingencia (canal 'contingencia') en la caja %s.",
                    config.display_name))
            if (mode == "libre" and config.invoice_journal_id
                    .l10n_ve_emission_channel != "libre"):
                raise ValidationError(_(
                    "Con formas libres, el diario de facturación de la caja "
                    "%s debe tener el canal de emisión 'Forma libre' (así el "
                    "Nº de control queda write-once y el Libro de Ventas lo "
                    "segrega en su sub-bloque).", config.display_name))
            batch = config.l10n_ve_paper_batch_id
            expected = "talonario" if mode == "contingencia" else "forma_libre"
            if batch and batch.type != expected:
                raise ValidationError(_(
                    "El lote de papelería '%(batch)s' no corresponde al modo "
                    "de la caja %(config)s: se esperaba uno de tipo "
                    "'%(expected)s'.",
                    batch=batch.display_name, config=config.display_name,
                    expected=expected))

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
