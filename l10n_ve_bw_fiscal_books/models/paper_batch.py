# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_fiscal_books. License LGPL-3.
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Prefijo alfanumérico opcional + cola numérica: cubre "000001" y "00-000001".
NUMBER_RE = re.compile(r"^(.*?)(\d+)$")

# Formatos restantes a partir de los cuales next_numbers() devuelve un aviso
# para que el encargado pida el siguiente talonario a la imprenta a tiempo.
LOW_PAPER_THRESHOLD = 10


class L10nVePaperBatch(models.Model):
    """Papelería fiscal preimpresa de imprenta autorizada (PA 0071).

    Un registro por lote físico: un talonario de contingencia (Nº de factura y
    Nº de control preimpresos, se llena a mano) o una caja de formas libres
    (solo el Nº de control viene preimpreso; el contenido lo imprime Odoo).
    De aquí salen la PROPUESTA del siguiente correlativo en el POS y la
    validación de rango/duplicados; los números ya usados se leen de los
    documentos reales (account.move y pos.order), no de un contador propio,
    para que un salto o corrección manual no desincronice nada.
    """
    _name = "l10n.ve.paper.batch"
    _description = "Papelería fiscal preimpresa (VE)"
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    type = fields.Selection(
        [("talonario", "Talonario (contingencia)"),
         ("forma_libre", "Formas libres")],
        string="Tipo de papelería", required=True, default="talonario",
        help="Talonario: factura manuscrita completa, con Nº de factura y Nº "
             "de control preimpresos (contingencia, PA 0071 art. 11).\n"
             "Formas libres: papelería con solo el Nº de control preimpreso; "
             "el contenido de la factura lo imprime el sistema (canal libre).")
    company_id = fields.Many2one(
        "res.company", string="Compañía", required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    printer_name = fields.Char(
        string="Imprenta autorizada",
        help="Razón social de la imprenta autorizada que elaboró la papelería "
             "(está impresa al pie de cada formato).")
    printer_vat = fields.Char(string="RIF de la imprenta")
    printer_authorization = fields.Char(
        string="Nº de autorización de la imprenta",
        help="Número de la Providencia de autorización de la imprenta, "
             "impreso al pie de cada formato.")

    control_from = fields.Char(
        string="Nº de control desde", required=True, default="000001")
    control_to = fields.Char(
        string="Nº de control hasta",
        help="Último Nº de control del lote. Vacío = rango abierto (no "
             "recomendado: sin tope no hay aviso de agotamiento).")
    invoice_from = fields.Char(
        string="Nº de factura desde", default="000001",
        help="Solo talonario: primera factura preimpresa del lote. En formas "
             "libres el Nº de factura lo asigna la secuencia del diario.")
    invoice_to = fields.Char(string="Nº de factura hasta")

    @api.depends("type", "control_from", "control_to", "printer_name")
    def _compute_name(self):
        for batch in self:
            label = ("Talonario" if batch.type == "talonario"
                     else "Formas libres")
            name = "%s control %s–%s" % (
                label, batch.control_from or "?", batch.control_to or "…")
            if batch.printer_name:
                name += " (%s)" % batch.printer_name
            batch.name = name

    # ------------------------------------------------------------------
    # Validación de rangos
    # ------------------------------------------------------------------
    @staticmethod
    def _split(value):
        """'00-000123' -> ('00-', 123, 6); None si no termina en dígitos."""
        match = NUMBER_RE.match((value or "").strip())
        if not match:
            return None
        prefix, digits = match.groups()
        return prefix, int(digits), len(digits)

    @api.constrains("type", "control_from", "control_to",
                    "invoice_from", "invoice_to")
    def _check_ranges(self):
        for batch in self:
            kinds = [("control", batch.control_from, batch.control_to)]
            if batch.type == "talonario":
                if not batch.invoice_from:
                    raise ValidationError(_(
                        "Un talonario lleva el Nº de factura preimpreso: "
                        "indique el 'Nº de factura desde'."))
                kinds.append(("factura", batch.invoice_from, batch.invoice_to))
            for label, start, end in kinds:
                s = self._split(start)
                if not s:
                    raise ValidationError(_(
                        "El Nº de %(label)s inicial '%(value)s' debe terminar "
                        "en dígitos (ej. 000001 o 00-000001).",
                        label=label, value=start or ""))
                if end:
                    e = self._split(end)
                    if not e or e[0] != s[0]:
                        raise ValidationError(_(
                            "El rango de Nº de %(label)s debe compartir el "
                            "mismo prefijo ('%(start)s' vs '%(end)s').",
                            label=label, start=start, end=end))
                    if e[1] < s[1]:
                        raise ValidationError(_(
                            "El rango de Nº de %(label)s está invertido "
                            "('%(start)s' > '%(end)s').",
                            label=label, start=start, end=end))

    # ------------------------------------------------------------------
    # Números usados / propuesta del siguiente
    # ------------------------------------------------------------------
    def _used_numbers(self, kind):
        """Colas numéricas ya usadas dentro del rango del lote.

        sudo(): el cajero del POS no tiene (ni necesita) acceso a
        account.move; aquí solo se agregan los números, ningún otro dato
        sale hacia el cliente.
        """
        self.ensure_one()
        if kind == "control":
            move_field = "l10n_ve_control_number"
            order_field = "l10n_ve_contingency_control"
            start = self.control_from
        else:
            move_field = "l10n_ve_paper_number"
            order_field = "l10n_ve_contingency_invoice_number"
            start = self.invoice_from
        prefix, _num, _width = self._split(start)
        # SOLO ventas en diarios de canal papel: el mismo campo Nº de control
        # guarda en las COMPRAS el correlativo del proveedor (p. ej. una
        # factura de imprenta con control de 12 dígitos) y en canal mf el de
        # la máquina fiscal — ninguno pertenece a nuestros talonarios y, con
        # rango abierto, uno solo dispararía la propuesta a la estratósfera.
        move_domain = [("company_id", "=", self.company_id.id),
                       ("move_type", "in", ("out_invoice", "out_refund")),
                       ("journal_id.l10n_ve_emission_channel", "in",
                        ("contingencia", "libre")),
                       (move_field, "!=", False)]
        order_domain = [("company_id", "=", self.company_id.id),
                        (order_field, "!=", False)]
        if prefix:
            move_domain.append((move_field, "=like", prefix + "%"))
            order_domain.append((order_field, "=like", prefix + "%"))
        values = self.env["account.move"].sudo().search(
            move_domain).mapped(move_field)
        values += self.env["pos.order"].sudo().search(
            order_domain).mapped(order_field)
        used = set()
        for value in values:
            parts = self._split(value)
            if parts and parts[0] == prefix:
                used.add(parts[1])
        return used

    def _next_number(self, kind):
        """(siguiente valor formateado | False si el lote se agotó,
        restantes | None si el rango es abierto)."""
        self.ensure_one()
        start = self.control_from if kind == "control" else self.invoice_from
        end = self.control_to if kind == "control" else self.invoice_to
        prefix, first, width = self._split(start)
        last = self._split(end)[1] if end else None
        used = {n for n in self._used_numbers(kind)
                if n >= first and (last is None or n <= last)}
        nxt = max(used) + 1 if used else first
        # Huecos: la propuesta sigue del mayor usado; un formato saltado se
        # registra corrigiendo a mano el número propuesto en el diálogo.
        if last is not None and nxt > last:
            return False, 0
        remaining = None if last is None else last - nxt + 1
        return "%s%0*d" % (prefix, width, nxt), remaining

    def next_numbers(self):
        """Propuesta para el POS: siguiente Nº de factura y de control.

        Nunca lanza excepción (el POS decide cómo pintar el problema):
        devuelve {'error': ...} si el lote está agotado.
        """
        self.ensure_one()
        control, control_left = self._next_number("control")
        if not control:
            return {"error": _(
                "El lote '%s' agotó sus números de control: registre el "
                "talonario o la caja de formas siguiente en Contabilidad › "
                "Configuración › Papelería fiscal (VE).") % self.display_name}
        result = {
            "type": self.type,
            "control": control,
            "invoice": False,
            "warning": False,
        }
        remaining = [control_left]
        if self.type == "talonario":
            invoice, invoice_left = self._next_number("invoice")
            if not invoice:
                return {"error": _(
                    "El lote '%s' agotó sus números de factura: registre el "
                    "talonario siguiente en Contabilidad › Configuración › "
                    "Papelería fiscal (VE).") % self.display_name}
            result["invoice"] = invoice
            remaining.append(invoice_left)
        lows = [r for r in remaining if r is not None]
        if lows and min(lows) <= LOW_PAPER_THRESHOLD:
            result["warning"] = _(
                "Quedan %s formatos en este lote: pida el siguiente a la "
                "imprenta autorizada.") % min(lows)
        return result

    def check_numbers(self, invoice_number, control_number):
        """Valida los números digitados: rango del lote + no usados.

        Devuelve False si todo está bien, o el texto del problema (el POS lo
        muestra sin romper el flujo de cobro).
        """
        self.ensure_one()
        checks = [("control", control_number, self.control_from,
                   self.control_to)]
        if self.type == "talonario":
            checks.append(("factura", invoice_number, self.invoice_from,
                           self.invoice_to))
        for kind_label, value, start, end in checks:
            kind = "control" if kind_label == "control" else "invoice"
            parts = self._split(value)
            expected_prefix, first, _w = self._split(start)
            if not parts or parts[0] != expected_prefix:
                return _(
                    "El Nº de %(kind)s '%(value)s' no coincide con el formato "
                    "del lote (ej. %(sample)s).",
                    kind=kind_label, value=value or "", sample=start)
            number = parts[1]
            last = self._split(end)[1] if end else None
            if number < first or (last is not None and number > last):
                return _(
                    "El Nº de %(kind)s '%(value)s' está fuera del rango del "
                    "lote (%(start)s–%(end)s).",
                    kind=kind_label, value=value, start=start, end=end or "…")
            if number in self._used_numbers(kind):
                return _(
                    "El Nº de %(kind)s '%(value)s' ya fue usado en otro "
                    "documento.", kind=kind_label, value=value)
        return False
