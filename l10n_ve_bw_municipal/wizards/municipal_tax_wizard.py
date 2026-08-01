# Part of l10n_ve_bw. License LGPL-3.
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

MONTH_SELECTION = [
    ("1", "Enero"),
    ("2", "Febrero"),
    ("3", "Marzo"),
    ("4", "Abril"),
    ("5", "Mayo"),
    ("6", "Junio"),
    ("7", "Julio"),
    ("8", "Agosto"),
    ("9", "Septiembre"),
    ("10", "Octubre"),
    ("11", "Noviembre"),
    ("12", "Diciembre"),
]


class L10nVeMunicipalTaxWizard(models.TransientModel):
    _name = "l10n.ve.municipal.tax.wizard"
    _description = "Impuesto Municipal (Venezuela)"

    @api.model
    def _default_period_date(self):
        # Mes vencido: el impuesto se liquida sobre el mes ya cerrado.
        return fields.Date.context_today(self).replace(day=1) - relativedelta(days=1)

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    year = fields.Integer(
        string="Año",
        required=True,
        default=lambda self: self._default_period_date().year,
    )
    month = fields.Selection(
        selection=MONTH_SELECTION,
        string="Mes",
        required=True,
        default=lambda self: str(self._default_period_date().month),
    )
    municipality = fields.Char(related="company_id.l10n_ve_municipal_name")
    rate = fields.Float(related="company_id.l10n_ve_municipal_rate")
    minimum_mmv = fields.Float(related="company_id.l10n_ve_municipal_minimum_mmv")
    tcmmv = fields.Float(related="company_id.l10n_ve_municipal_tcmmv")
    minimum_amount = fields.Monetary(
        string="Mínimo tributable del período",
        readonly=True,
        help="Mayor entre el mínimo fijo y veces MMV × TCMMV (convertido a la "
             "moneda de la compañía a la tasa de fin de mes).",
    )
    base_amount = fields.Monetary(
        string="Base imponible (ingresos brutos)",
        readonly=True,
    )
    computed_tax = fields.Monetary(
        string="Impuesto calculado (base × alícuota)",
        readonly=True,
    )
    tax_amount = fields.Monetary(
        string="Monto a pagar",
        readonly=True,
        help="Máximo entre el impuesto calculado y el mínimo tributable mensual.",
    )
    ves_currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_ves_currency",
    )
    amount_bs = fields.Monetary(
        string="Equivalente en Bs",
        currency_field="ves_currency_id",
        readonly=True,
        help="Monto a pagar convertido a bolívares a la tasa de fin de mes.",
    )
    is_computed = fields.Boolean(readonly=True)

    def _compute_ves_currency(self):
        ves = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "VES")], limit=1
        )
        for wizard in self:
            wizard.ves_currency_id = ves

    def _get_period_dates(self):
        self.ensure_one()
        if not 2000 <= self.year <= 2100:
            raise UserError(_("El año %s no es válido.", self.year))
        date_from = date(self.year, int(self.month), 1)
        date_to = date_from + relativedelta(months=1, days=-1)
        return date_from, date_to

    def _get_move_ref(self):
        # Ref ESTABLE e independiente de datos editables (nombre del municipio):
        # la detección de duplicados busca por este prefijo, que ya codifica el
        # período. Sin traducir.
        self.ensure_one()
        return "MUNI-%04d-%02d" % (self.year, int(self.month))

    def _get_move_line_label(self):
        # Etiqueta descriptiva (líneas y narration): aquí sí va el municipio.
        self.ensure_one()
        return ("Impuesto municipal %02d/%04d %s" % (
            int(self.month), self.year, self.company_id.l10n_ve_municipal_name or "",
        )).strip()

    def _compute_municipal_amounts(self):
        for wizard in self:
            company = wizard.company_id
            if not company.l10n_ve_municipal_rate:
                raise UserError(_(
                    "Configure la alícuota del impuesto municipal de la compañía "
                    "%s en Ajustes › Contabilidad, bloque Localización Venezuela.",
                    company.display_name,
                ))
            date_from, date_to = wizard._get_period_dates()
            currency = company.currency_id
            income_lines = self.env["account.move.line"].search([
                ("company_id", "=", company.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("account_id.account_type", "=", "income"),
            ])
            base = currency.round(
                sum(income_lines.mapped("credit")) - sum(income_lines.mapped("debit"))
            )
            computed = currency.round(base * company.l10n_ve_municipal_rate / 100.0)
            ves = wizard.ves_currency_id
            # Tasa VES REAL cargada hasta el fin del período: sin
            # res.currency.rate (o con la tasa 1:1 por defecto) _convert
            # devolvería el monto USD etiquetado como Bs
            # (res.currency._get_rates hace COALESCE(rate, fallback, 1.0)).
            has_ves_rate = bool(ves) and bool(self.env["res.currency.rate"].search_count([
                ("currency_id", "=", ves.id),
                ("company_id", "in", (company.root_id.id, False)),
                ("name", "<=", date_to),
                ("rate", "!=", 1.0),
            ], limit=1))
            # Mínimo tributable: el mayor entre el fijo y el de la ordenanza en
            # veces MMV (veces × TCMMV, en Bs, convertido a moneda de compañía).
            minimum = company.l10n_ve_municipal_minimum
            if company.l10n_ve_municipal_minimum_mmv:
                if not company.l10n_ve_municipal_tcmmv:
                    raise UserError(_(
                        "El mínimo tributable está configurado en veces MMV pero "
                        "falta el TCMMV (Bs) publicado por el BCV: cárguelo en "
                        "Ajustes › Contabilidad, bloque Localización Venezuela.",
                    ))
                minimum_bs = (company.l10n_ve_municipal_minimum_mmv
                              * company.l10n_ve_municipal_tcmmv)
                if currency == ves:
                    minimum_mmv = minimum_bs
                elif has_ves_rate:
                    minimum_mmv = ves._convert(minimum_bs, currency, company, date_to)
                else:
                    raise UserError(_(
                        "No hay tasa VES real cargada hasta el %s: no se puede "
                        "convertir el mínimo tributable (veces MMV × TCMMV) a la "
                        "moneda de la compañía.", date_to,
                    ))
                minimum = max(minimum, currency.round(minimum_mmv))
            amount = max(computed, minimum)
            amount_bs = 0.0
            if has_ves_rate:
                amount_bs = currency._convert(amount, ves, company, date_to)
            elif currency == ves:
                amount_bs = amount
            wizard.write({
                "base_amount": base,
                "computed_tax": computed,
                "minimum_amount": minimum,
                "tax_amount": amount,
                "amount_bs": amount_bs,
                "is_computed": True,
            })

    def _reopen_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Impuesto Municipal (VE)"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_compute(self):
        self.ensure_one()
        self._compute_municipal_amounts()
        return self._reopen_wizard()

    def action_generate_entry(self):
        self.ensure_one()
        self._compute_municipal_amounts()
        company = self.company_id
        missing = []
        if not company.l10n_ve_municipal_expense_account_id:
            missing.append(_("la cuenta de gasto"))
        if not company.l10n_ve_municipal_payable_account_id:
            missing.append(_("la cuenta por pagar"))
        if not company.l10n_ve_municipal_journal_id:
            missing.append(_("el diario misceláneo"))
        if missing:
            raise UserError(_(
                "Falta configurar %s del impuesto municipal en Ajustes › "
                "Contabilidad, bloque Localización Venezuela.",
                ", ".join(missing),
            ))
        if company.currency_id.compare_amounts(self.tax_amount, 0.0) <= 0:
            raise UserError(_("El monto del impuesto es cero: no hay nada que asentar."))
        date_to = self._get_period_dates()[1]
        ref = self._get_move_ref()
        label = self._get_move_line_label()
        # El prefijo MUNI-AAAA-MM ya codifica el período: el guard no depende
        # del nombre del municipio ni de la fecha (editables) del asiento.
        existing = self.env["account.move"].search([
            ("company_id", "=", company.id),
            ("ref", "=like", ref + "%"),
            ("state", "!=", "cancel"),
        ], limit=1)
        if existing:
            raise UserError(_(
                "Ya existe el asiento %(move)s con la referencia \"%(ref)s\" del "
                "período: no se genera un duplicado.",
                move=existing.display_name, ref=ref,
            ))
        move = self.env["account.move"].with_company(company).create({
            "move_type": "entry",
            "journal_id": company.l10n_ve_municipal_journal_id.id,
            "date": date_to,
            "ref": ref,
            "narration": label,
            "line_ids": [
                Command.create({
                    "name": label,
                    "account_id": company.l10n_ve_municipal_expense_account_id.id,
                    "debit": self.tax_amount,
                    "credit": 0.0,
                }),
                Command.create({
                    "name": label,
                    "account_id": company.l10n_ve_municipal_payable_account_id.id,
                    "debit": 0.0,
                    "credit": self.tax_amount,
                }),
            ],
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Impuesto municipal"),
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
        }
