# Part of l10n_ve_bw_payroll. License LGPL-3.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Conceptos que mueven el saldo de GARANTÍA (los intereses se llevan aparte:
# art. 143 — se pagan al trabajador anualmente o en la liquidación).
GARANTIA_CONCEPTS = ("garantia", "adicionales", "anticipo", "liquidacion")


class L10nVePrestacionesLine(models.Model):
    _name = "l10n.ve.prestaciones.line"
    _description = "Libro de garantía de prestaciones sociales (art. 142-143 LOTTT)"
    _order = "date desc, id desc"

    employee_id = fields.Many2one(
        "hr.employee", string="Trabajador", required=True, index=True,
        ondelete="restrict")
    company_id = fields.Many2one(
        related="employee_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    concept = fields.Selection([
        ("garantia", "Garantía trimestral (15 días)"),
        ("adicionales", "Días adicionales (2/año)"),
        ("intereses", "Intereses (art. 143)"),
        ("anticipo", "Anticipo (art. 144)"),
        ("liquidacion", "Liquidación"),
    ], required=True)
    days = fields.Float(string="Días", digits=(6, 2))
    daily_integral = fields.Float(
        string="Salario integral diario", digits=(16, 4),
        help="Salario integral diario usado en el cálculo (moneda de la compañía).")
    amount = fields.Monetary(
        string="Monto", required=True,
        help="Positivo acumula (garantía, adicionales, devengo de intereses); "
             "negativo reduce (anticipos, liquidación, pago de intereses del "
             "art. 143 — anual o en el finiquito).")
    provision_id = fields.Many2one(
        "l10n.ve.payroll.provision", string="Corrida de provisión",
        ondelete="set null", index=True)
    note = fields.Char(string="Nota")

    @api.model
    def _garantia_balance(self, employee, date=None):
        """Saldo de garantía (sin intereses) a la fecha."""
        domain = [("employee_id", "=", employee.id),
                  ("concept", "in", GARANTIA_CONCEPTS)]
        if date:
            domain.append(("date", "<=", date))
        return sum(self.search(domain).mapped("amount"))

    @api.model
    def _intereses_balance(self, employee, date=None):
        domain = [("employee_id", "=", employee.id),
                  ("concept", "=", "intereses")]
        if date:
            domain.append(("date", "<=", date))
        return sum(self.search(domain).mapped("amount"))

    @api.constrains("amount", "concept")
    def _check_anticipo(self):
        for line in self:
            if line.concept == "anticipo":
                if line.amount >= 0:
                    raise ValidationError(_("Un anticipo debe ser un monto negativo."))
                balance_without = self._garantia_balance(line.employee_id) - line.amount
                if -line.amount > 0.75 * balance_without + 0.005:
                    raise ValidationError(_(
                        "El anticipo excede el 75%% del saldo de garantía "
                        "(art. 144 LOTTT): saldo %(bal).2f, máximo %(max).2f.",
                        bal=balance_without, max=0.75 * balance_without))
            elif line.concept in ("garantia", "adicionales") and line.amount < 0:
                # Los intereses SÍ admiten negativos: su pago anual o en la
                # liquidación (art. 143) se registra como línea negativa.
                raise ValidationError(_(
                    "El concepto %s no admite montos negativos.", line.concept))
