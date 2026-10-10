# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_dual_currency. License LGPL-3.
"""Libros contables (Diario, Mayor y Balance de Comprobación) en USD y Bs.

El Código de Comercio (arts. 32 a 35) exige llevar el Libro Diario y el Libro
Mayor, y la contabilidad de MISOYMASA vive en USD. Los montos en bolívares que
se muestran aquí NO se convierten al vuelo: se leen de los campos almacenados
por apunte (`l10n_ve_debit_bs`, `l10n_ve_credit_bs`, `l10n_ve_balance_bs`) que
congelan la tasa BCV de cada asiento. Por eso los totales cuadran al céntimo en
las dos monedas: el recuadre por asiento ya lo hizo el módulo al guardar.

Diseño: el cálculo (métodos `_compute_*`, que devuelven listas y diccionarios
de Python) está separado de la escritura del XLSX (métodos `_write_*`). Así se
puede probar la contabilidad sin abrir ningún archivo.
"""
import base64
import io
from collections import defaultdict

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Una hoja de Excel admite 1.048.576 filas; dejamos margen para cabeceras y
# secciones. Pasado este límite es mejor pedir un período menor que entregar un
# archivo truncado en silencio.
MAX_SHEET_ROWS = 1000000

# Tope de asientos listados por tipo de advertencia. Si hay más se agrega una
# fila con el conteo, para que la hoja siga siendo legible.
MAX_WARNINGS = 500

# Umbral (en Bs) a partir del cual el ajuste de redondeo de un asiento se
# considera una diferencia cambiaria real y no ruido de redondeo.
ADJUSTMENT_THRESHOLD = 1.0

PRIOR_RESULTS_LABEL = "Resultados no distribuidos de ejercicios anteriores"

# Campos que se leen de los apuntes del período, una sola vez, para el Diario y
# el Mayor (búsqueda por lotes en vez de un read por asiento).
LINE_FIELDS = (
    "date", "move_id", "move_name", "journal_id", "account_id", "partner_id",
    "name", "debit", "credit", "balance", "l10n_ve_debit_bs",
    "l10n_ve_credit_bs", "l10n_ve_balance_bs",
)

ZERO_ROW = {
    "initial_usd": 0.0, "initial_bs": 0.0,
    "debit_usd": 0.0, "credit_usd": 0.0,
    "debit_bs": 0.0, "credit_bs": 0.0,
}


class L10nVeLegalBooksWizard(models.TransientModel):
    _name = "l10n.ve.legal.books.wizard"
    _description = "Asistente de Libros Contables (Diario, Mayor y Balance)"

    company_id = fields.Many2one(
        "res.company", string="Compañía", required=True,
        default=lambda self: self.env.company)
    date_from = fields.Date(
        string="Desde", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string="Hasta", required=True,
        default=lambda self: fields.Date.context_today(self))
    # Solo recorta el Libro Diario: el Mayor y el Balance de Comprobación se
    # calculan siempre con todos los diarios, porque el saldo de una cuenta no
    # tiene sentido si se le quita parte de sus movimientos.
    journal_ids = fields.Many2many(
        "account.journal", "l10n_ve_legal_books_wizard_journal_rel",
        "wizard_id", "journal_id", string="Diarios (solo Libro Diario)",
        help="Vacío = todos los diarios. Este filtro afecta únicamente al "
             "Libro Diario; el Mayor y el Balance incluyen todos los diarios.")
    file = fields.Binary(string="Archivo generado", readonly=True)
    filename = fields.Char(string="Nombre del archivo")

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_(
                    "La fecha inicial debe ser anterior o igual a la fecha final."))

    @api.constrains("company_id", "journal_ids")
    def _check_journal_company(self):
        for wizard in self:
            foreign = wizard.journal_ids.filtered(
                lambda j: j.company_id != wizard.company_id)
            if foreign:
                raise ValidationError(_(
                    "Los diarios seleccionados deben pertenecer a la compañía "
                    "%(company)s.", company=wizard.company_id.display_name))

    # ------------------------------------------------------------------
    # Acción principal
    # ------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        # with_company fija env.company: el código de cuenta (`account.code`)
        # depende de ella, y las reglas de registro de los apuntes también.
        wizard = self.with_company(self.company_id)
        usd, bs = wizard._get_currencies()
        lines = wizard._get_period_lines()
        trial = wizard._compute_trial_balance()
        journal = wizard._compute_journal(lines)
        ledger = wizard._compute_ledger(trial, lines)
        warnings = wizard._compute_warnings(trial)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        try:
            fmts = wizard._get_formats(workbook)
            wizard._write_journal_sheet(workbook, fmts, journal, usd, bs)
            wizard._write_ledger_sheet(workbook, fmts, ledger, usd, bs)
            wizard._write_trial_sheet(workbook, fmts, trial, usd, bs)
            wizard._write_warnings_sheet(workbook, fmts, trial, warnings, usd, bs)
        finally:
            workbook.close()
        self.write({
            "file": base64.b64encode(output.getvalue()),
            "filename": "libros_contables_%s_%s.xlsx" % (
                self.date_from.strftime("%Y%m%d"),
                self.date_to.strftime("%Y%m%d"),
            ),
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Libros contables"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    # ------------------------------------------------------------------
    # Helpers de datos
    # ------------------------------------------------------------------
    def _get_currencies(self):
        """(moneda de la compañía, moneda Bs de referencia)."""
        self.ensure_one()
        company = self.company_id
        bs = company.l10n_ve_bs_currency_id
        if not bs:
            raise UserError(_(
                "La compañía %s no tiene configurada la moneda Bs de referencia "
                "(Ajustes > Localización Venezuela). Es necesaria para expresar "
                "los libros contables en bolívares.", company.display_name))
        return company.currency_id, bs

    def _get_base_domain(self):
        """Apuntes de asientos publicados de la compañía, sin secciones ni notas.

        Solo asientos publicados: un borrador no es un registro contable y no
        debe aparecer en un libro legal. Las secciones y notas no tienen
        importe, solo ensuciarían el Diario y el Mayor.
        """
        return [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("display_type", "not in",
             ("line_section", "line_subsection", "line_note")),
        ]

    def _get_accounts_meta(self, account_ids):
        """{id: {code, name, type, include_initial_balance}} en una lectura por lotes.

        `account.code` es dependiente de la compañía activa; por eso se lee con
        `with_company`. `active_test=False` porque una cuenta archivada puede
        tener apuntes históricos que el libro debe mostrar.
        """
        accounts = self.env["account.account"].with_company(
            self.company_id).with_context(active_test=False).browse(
            [aid for aid in account_ids if aid])
        return {
            account.id: {
                "code": account.code or "",
                "name": account.name or "",
                "type": account.account_type,
                "include_initial_balance": account.include_initial_balance,
            }
            for account in accounts
        }

    def _get_period_lines(self):
        """Apuntes publicados del período, ordenados por fecha y asiento."""
        self.ensure_one()
        domain = self._get_base_domain() + [
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        Line = self.env["account.move.line"]
        if Line.search_count(domain) > MAX_SHEET_ROWS:
            raise UserError(_(
                "El período tiene más de %s apuntes: no caben en una hoja de "
                "Excel. Genere el libro por rangos de fechas más cortos.",
                MAX_SHEET_ROWS))
        return Line.search_fetch(
            domain, list(LINE_FIELDS), order="date, move_name, id")

    def _round_row(self, row, usd, bs):
        """Redondea a la precisión de cada moneda para evitar arrastre de flotantes."""
        for key, value in row.items():
            if key.endswith("_usd"):
                row[key] = usd.round(value)
            elif key.endswith("_bs"):
                row[key] = bs.round(value)
        return row

    def _sum_rows(self, rows, usd, bs):
        totals = {key: 0.0 for key in ZERO_ROW}
        totals["final_usd"] = 0.0
        totals["final_bs"] = 0.0
        for row in rows:
            for key in totals:
                totals[key] += row[key]
        return self._round_row(totals, usd, bs)

    # ------------------------------------------------------------------
    # Cálculo: Balance de Comprobación (base del Mayor)
    # ------------------------------------------------------------------
    def _compute_trial_balance(self):
        """Saldo inicial, movimientos y saldo final por cuenta, en USD y Bs.

        Regla de saldos iniciales:
        * cuentas con `include_initial_balance` (balance): todo lo anterior a
          `date_from`;
        * cuentas de resultado: solo desde el inicio del ejercicio fiscal hasta
          `date_from`; lo anterior al ejercicio se resume en UNA fila
          "Resultados no distribuidos de ejercicios anteriores". Sin esa fila
          el balance no sumaría cero: el resultado de años anteriores ya está
          en el patrimonio aunque nadie haya hecho el asiento de cierre.

        Devuelve `{'rows', 'totals', 'checks', 'fy_start'}`; `rows` ordenadas
        por código, cada una con las claves de `ZERO_ROW` más `final_usd` y
        `final_bs`.
        """
        self.ensure_one()
        usd, bs = self._get_currencies()
        company = self.company_id
        Line = self.env["account.move.line"]
        domain = self._get_base_domain()
        fy_start = company.compute_fiscalyear_dates(self.date_from)["date_from"]
        initial_aggs = ["balance:sum", "l10n_ve_balance_bs:sum"]

        before_fy = Line._read_group(
            domain + [("date", "<", fy_start)], ["account_id"], initial_aggs)
        in_fy = Line._read_group(
            domain + [("date", ">=", fy_start), ("date", "<", self.date_from)],
            ["account_id"], initial_aggs)
        period = Line._read_group(
            domain + [("date", ">=", self.date_from), ("date", "<=", self.date_to)],
            ["account_id"],
            ["debit:sum", "credit:sum",
             "l10n_ve_debit_bs:sum", "l10n_ve_credit_bs:sum"])

        account_ids = {g[0].id for g in before_fy} | {g[0].id for g in in_fy} \
            | {g[0].id for g in period}
        meta = self._get_accounts_meta(account_ids)

        data = defaultdict(lambda: dict(ZERO_ROW))
        prior_usd = prior_bs = 0.0
        for account, balance_usd, balance_bs in before_fy:
            if meta[account.id]["include_initial_balance"]:
                data[account.id]["initial_usd"] += balance_usd
                data[account.id]["initial_bs"] += balance_bs
            else:
                # Cuenta de resultado de un ejercicio ya terminado.
                prior_usd += balance_usd
                prior_bs += balance_bs
        for account, balance_usd, balance_bs in in_fy:
            data[account.id]["initial_usd"] += balance_usd
            data[account.id]["initial_bs"] += balance_bs
        for account, debit_usd, credit_usd, debit_bs, credit_bs in period:
            row = data[account.id]
            row["debit_usd"] += debit_usd
            row["credit_usd"] += credit_usd
            row["debit_bs"] += debit_bs
            row["credit_bs"] += credit_bs

        rows = []
        for account_id, values in data.items():
            row = self._round_row(dict(values), usd, bs)
            row["final_usd"] = usd.round(
                row["initial_usd"] + row["debit_usd"] - row["credit_usd"])
            row["final_bs"] = bs.round(
                row["initial_bs"] + row["debit_bs"] - row["credit_bs"])
            # Una cuenta sin saldo inicial ni movimiento no aporta al libro.
            if all(usd.is_zero(row[k]) for k in
                   ("initial_usd", "debit_usd", "credit_usd")) and \
                    all(bs.is_zero(row[k]) for k in
                        ("initial_bs", "debit_bs", "credit_bs")):
                continue
            info = meta[account_id]
            row.update({
                "id": account_id,
                "code": info["code"],
                "name": info["name"],
                "type": info["type"],
                "prior_results": False,
            })
            rows.append(row)

        prior_usd = usd.round(prior_usd)
        prior_bs = bs.round(prior_bs)
        if not usd.is_zero(prior_usd) or not bs.is_zero(prior_bs):
            rows.append(self._prior_results_row(prior_usd, prior_bs))

        # Orden por código; la fila de resultados anteriores va justo después de
        # su cuenta y, si no hay cuenta `equity_unaffected`, al final.
        rows.sort(key=lambda r: (r["code"] or "~", r["prior_results"]))
        totals = self._sum_rows(rows, usd, bs)
        return {
            "rows": rows,
            "totals": totals,
            "checks": self._build_checks(totals, usd, bs),
            "fy_start": fy_start,
        }

    def _prior_results_row(self, prior_usd, prior_bs):
        """Fila de resultados de ejercicios anteriores, sin movimientos.

        Se asigna a la cuenta `equity_unaffected` de la compañía cuando existe
        (su código aparece en la fila); si no, es una fila virtual sin cuenta.
        Es una fila APARTE aunque esa cuenta tenga movimientos propios: así el
        contador ve cuánto es utilidad acumulada de años cerrados y cuánto es
        saldo real de la cuenta.
        """
        accounts = self.env["account.account"].with_company(
            self.company_id).search([
                ("account_type", "=", "equity_unaffected"),
                ("company_ids", "parent_of", self.company_id.id),
            ])
        account = accounts.sorted(key=lambda a: a.code or "")[:1]
        return {
            "id": account.id or False,
            "code": account.code or "" if account else "",
            "name": PRIOR_RESULTS_LABEL,
            "type": "equity_unaffected",
            "prior_results": True,
            "initial_usd": prior_usd,
            "initial_bs": prior_bs,
            "debit_usd": 0.0, "credit_usd": 0.0,
            "debit_bs": 0.0, "credit_bs": 0.0,
            "final_usd": prior_usd,
            "final_bs": prior_bs,
        }

    def _build_checks(self, totals, usd, bs):
        """Verificaciones de cuadre del Balance: cada una debe dar cero."""
        spec = [
            (_("Σ Debe − Σ Haber del período (%s)", usd.name),
             totals["debit_usd"] - totals["credit_usd"], usd),
            (_("Σ Debe − Σ Haber del período (Bs)"),
             totals["debit_bs"] - totals["credit_bs"], bs),
            (_("Σ saldos iniciales (%s)", usd.name), totals["initial_usd"], usd),
            (_("Σ saldos iniciales (Bs)"), totals["initial_bs"], bs),
            (_("Σ saldos finales (%s)", usd.name), totals["final_usd"], usd),
            (_("Σ saldos finales (Bs)"), totals["final_bs"], bs),
        ]
        checks = []
        for label, value, currency in spec:
            value = currency.round(value)
            checks.append({
                "label": label,
                "value": value,
                "currency": currency.name,
                "ok": currency.is_zero(value),
            })
        return checks

    # ------------------------------------------------------------------
    # Cálculo: Libro Diario
    # ------------------------------------------------------------------
    def _compute_journal(self, lines=None):
        """Asientos del período con sus apuntes, en orden cronológico.

        Devuelve `{'moves': [...], 'totals': {...}}`. Cada asiento trae el
        total de debe y haber en ambas monedas, para que se vea el cuadre
        asiento por asiento. El filtro de diarios solo actúa aquí.
        """
        self.ensure_one()
        usd, bs = self._get_currencies()
        if lines is None:
            lines = self._get_period_lines()
        if self.journal_ids:
            lines = lines.filtered(lambda l: l.journal_id in self.journal_ids)
        meta = self._get_accounts_meta(set(lines.account_id.ids))

        moves = {}  # dict conserva el orden de inserción: fecha y número
        for line in lines:
            move_id = line.move_id.id
            move = moves.get(move_id)
            if move is None:
                move = moves[move_id] = {
                    "id": move_id,
                    "name": line.move_name or "",
                    "date": line.date,
                    "journal": line.journal_id.name or "",
                    "ref": line.move_id.ref or "",
                    "lines": [],
                    "debit_usd": 0.0, "credit_usd": 0.0,
                    "debit_bs": 0.0, "credit_bs": 0.0,
                }
            info = meta.get(line.account_id.id, {})
            move["lines"].append({
                "account_code": info.get("code", ""),
                "account_name": info.get("name", ""),
                "partner": line.partner_id.name or "",
                "label": line.name or "",
                "debit_usd": line.debit,
                "credit_usd": line.credit,
                "debit_bs": line.l10n_ve_debit_bs,
                "credit_bs": line.l10n_ve_credit_bs,
            })
            for key in ("debit_usd", "credit_usd", "debit_bs", "credit_bs"):
                move[key] += move["lines"][-1][key]

        move_list = [self._round_row(m, usd, bs) for m in moves.values()]
        totals = {key: 0.0 for key in ZERO_ROW if not key.startswith("initial")}
        for move in move_list:
            for key in totals:
                totals[key] += move[key]
        return {
            "moves": move_list,
            "totals": self._round_row(totals, usd, bs),
        }

    # ------------------------------------------------------------------
    # Cálculo: Libro Mayor
    # ------------------------------------------------------------------
    def _compute_ledger(self, trial=None, lines=None):
        """Por cuenta: saldo inicial, movimientos con saldo corrido y total.

        Parte de las filas del balance para que el saldo inicial y el final de
        cada cuenta del Mayor sean exactamente los del Balance de Comprobación.
        El saldo corrido se redondea en cada paso a la precisión de la moneda,
        igual que los importes almacenados, así el último saldo coincide con el
        saldo final sin diferencias de centavos.
        """
        self.ensure_one()
        usd, bs = self._get_currencies()
        if trial is None:
            trial = self._compute_trial_balance()
        if lines is None:
            lines = self._get_period_lines()

        by_account = defaultdict(list)
        for line in lines:
            by_account[line.account_id.id].append(line)

        ledger = []
        for row in trial["rows"]:
            account_lines = [] if row["prior_results"] else \
                by_account.get(row["id"], [])
            running_usd = row["initial_usd"]
            running_bs = row["initial_bs"]
            entries = []
            for line in account_lines:
                running_usd = usd.round(running_usd + line.balance)
                running_bs = bs.round(running_bs + line.l10n_ve_balance_bs)
                entries.append({
                    "date": line.date,
                    "move": line.move_name or "",
                    "partner": line.partner_id.name or "",
                    "label": line.name or "",
                    "debit_usd": line.debit,
                    "credit_usd": line.credit,
                    "balance_usd": running_usd,
                    "debit_bs": line.l10n_ve_debit_bs,
                    "credit_bs": line.l10n_ve_credit_bs,
                    "balance_bs": running_bs,
                })
            account = dict(row)
            account["lines"] = entries
            ledger.append(account)
        return ledger

    # ------------------------------------------------------------------
    # Cálculo: Advertencias
    # ------------------------------------------------------------------
    def _compute_warnings(self, trial=None):
        """Asientos que el contador debe revisar antes de firmar el libro.

        Tres familias, todas independientes del filtro de diarios:
        * sin tasa Bs (hasta `date_to`: un asiento anterior sin tasa también
          distorsiona los saldos iniciales);
        * con |ajuste| mayor a 1 Bs: diferencia cambiaria real, no redondeo;
        * que no cuadran en Bs (o en USD) dentro del período: el libro en esa
          moneda no suma cero por su culpa.
        Cada elemento: `{'type', 'move_id', 'date', 'move', 'journal',
        'detail', 'value'}`.
        """
        self.ensure_one()
        usd, bs = self._get_currencies()
        Move = self.env["account.move"]
        company_domain = [
            ("company_id", "=", self.company_id.id), ("state", "=", "posted")]
        in_period = [
            ("date", ">=", self.date_from), ("date", "<=", self.date_to)]
        warnings = []

        def add(kind, move, detail, value=None):
            warnings.append({
                "type": kind,
                "move_id": move.id,
                "date": move.date,
                "move": move.name or "",
                "journal": move.journal_id.name or "",
                "detail": detail,
                "value": value,
            })

        def add_more(kind, total, shown):
            if total > shown:
                warnings.append({
                    "type": kind, "move_id": False, "date": False, "move": "",
                    "journal": "",
                    "detail": _("... y %s asientos más que no se listan.",
                                total - shown),
                    "value": None,
                })

        # 1. Sin tasa Bs
        domain = company_domain + [
            ("date", "<=", self.date_to), ("l10n_ve_bs_rate_missing", "=", True)]
        all_missing = Move.search(domain, order="date, name")
        for move in all_missing[:MAX_WARNINGS]:
            where = _("en el período") if move.date >= self.date_from \
                else _("anterior al período (afecta los saldos iniciales)")
            add(_("Sin tasa Bs"), move, _(
                "No existe tasa BCV para la fecha del asiento (%s): sus "
                "importes en Bs de otras monedas quedaron en 0.", where))
        add_more(_("Sin tasa Bs"), len(all_missing), MAX_WARNINGS)
        # Los asientos sin tasa casi siempre quedan descuadrados en Bs; se
        # excluyen del punto 3 para no listarlos dos veces por la misma causa.
        missing_ids = set(all_missing.ids)

        # 2. Ajuste de redondeo / diferencia cambiaria mayor a 1 Bs
        domain = company_domain + in_period + [
            "|", ("l10n_ve_bs_adjustment", ">", ADJUSTMENT_THRESHOLD),
            ("l10n_ve_bs_adjustment", "<", -ADJUSTMENT_THRESHOLD)]
        all_adjusted = Move.search(domain, order="date, name")
        for move in all_adjusted[:MAX_WARNINGS]:
            add(_("Ajuste Bs mayor a 1"), move, _(
                "El recuadre en Bs del asiento es de %s Bs: posible "
                "diferencia cambiaria real, no solo redondeo.",
                bs.round(move.l10n_ve_bs_adjustment)),
                bs.round(move.l10n_ve_bs_adjustment))
        add_more(_("Ajuste Bs mayor a 1"), len(all_adjusted), MAX_WARNINGS)

        # 3. Asientos descuadrados (USD o Bs), incluidos los anteriores al
        # período: los saldos iniciales acumulan toda la historia, así que un
        # asiento viejo descuadrado rompe los cuadres iniciales y finales y
        # debe quedar listado para que la causa del DESCUADRE sea visible.
        Line = self.env["account.move.line"]
        groups = Line._read_group(
            self._get_base_domain() + [("date", "<=", self.date_to)],
            ["move_id"],
            ["balance:sum", "l10n_ve_balance_bs:sum"])
        unbalanced = [
            (move, usd_diff, bs_diff) for move, usd_diff, bs_diff in groups
            if (not usd.is_zero(usd_diff) or not bs.is_zero(bs_diff))
            and move.id not in missing_ids
        ]
        unbalanced.sort(key=lambda item: (item[0].date, item[0].name or ""))
        for move, usd_diff, bs_diff in unbalanced[:MAX_WARNINGS]:
            before = _(" (anterior al período: afecta los saldos iniciales)") \
                if move.date < self.date_from else ""
            if not bs.is_zero(bs_diff):
                add(_("Asiento descuadrado en Bs"), move, _(
                    "Σ de apuntes en Bs = %s (debe ser 0).",
                    bs.round(bs_diff)) + before, bs.round(bs_diff))
            if not usd.is_zero(usd_diff):
                add(_("Asiento descuadrado en %s", usd.name), move, _(
                    "Σ de apuntes en %(cur)s = %(value)s (debe ser 0).",
                    cur=usd.name, value=usd.round(usd_diff)) + before,
                    usd.round(usd_diff))
        add_more(_("Asiento descuadrado en Bs"), len(unbalanced),
                 min(len(unbalanced), MAX_WARNINGS))
        return warnings

    # ------------------------------------------------------------------
    # Helpers XLSX
    # ------------------------------------------------------------------
    def _get_formats(self, workbook):
        return {
            "title": workbook.add_format({"bold": True, "font_size": 13}),
            "bold": workbook.add_format({"bold": True}),
            "section": workbook.add_format({
                "bold": True, "font_size": 11, "font_color": "#1F4E78",
                "bg_color": "#EEF3FA", "border": 1}),
            "header": workbook.add_format({
                "bold": True, "bg_color": "#D9E1F2", "border": 1,
                "text_wrap": True, "align": "center", "valign": "vcenter"}),
            "text": workbook.add_format({"border": 1}),
            "wrap": workbook.add_format({"border": 1, "text_wrap": True}),
            "date": workbook.add_format(
                {"border": 1, "num_format": "dd/mm/yyyy", "align": "left"}),
            "num": workbook.add_format({"border": 1, "num_format": "#,##0.00"}),
            "italic": workbook.add_format({"border": 1, "italic": True}),
            "italic_num": workbook.add_format({
                "border": 1, "italic": True, "num_format": "#,##0.00"}),
            "total_label": workbook.add_format(
                {"bold": True, "border": 1, "bg_color": "#F2F2F2"}),
            "total_num": workbook.add_format({
                "bold": True, "border": 1, "bg_color": "#F2F2F2",
                "num_format": "#,##0.00"}),
            "ok": workbook.add_format({
                "bold": True, "border": 1, "font_color": "#006100",
                "bg_color": "#C6EFCE", "align": "center"}),
            "fail": workbook.add_format({
                "bold": True, "border": 1, "font_color": "#9C0006",
                "bg_color": "#FFC7CE", "align": "center"}),
        }

    def _write_header(self, sheet, fmts, title, usd):
        company = self.company_id
        sheet.write(0, 0, company.name or "", fmts["title"])
        sheet.write(1, 0, "RIF: %s" % (company.vat or ""), fmts["bold"])
        sheet.write(2, 0, title, fmts["title"])
        sheet.write(3, 0, "Período: %s al %s. Montos en %s y en Bs "
                    "(tasa BCV congelada en cada asiento)" % (
                        self.date_from.strftime("%d/%m/%Y"),
                        self.date_to.strftime("%d/%m/%Y"), usd.name),
                    fmts["bold"])
        return 5

    def _write_headers(self, sheet, fmts, row, headers):
        for col, header in enumerate(headers):
            sheet.write(row, col, header, fmts["header"])
        sheet.set_row(row, 32)
        return row + 1

    # ------------------------------------------------------------------
    # Hoja: Libro Diario
    # ------------------------------------------------------------------
    def _write_journal_sheet(self, workbook, fmts, journal, usd, bs):
        sheet = workbook.add_worksheet("Libro Diario")
        sheet.set_column(0, 0, 11)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 22)
        sheet.set_column(3, 3, 14)
        sheet.set_column(4, 4, 36)
        sheet.set_column(5, 5, 28)
        sheet.set_column(6, 6, 40)
        sheet.set_column(7, 10, 16)
        row = self._write_header(sheet, fmts, "LIBRO DIARIO", usd)
        if self.journal_ids:
            sheet.write(4, 0, "Diarios: %s" % ", ".join(
                self.journal_ids.mapped("name")), fmts["bold"])
        row = self._write_headers(sheet, fmts, row, [
            "Fecha", "Asiento", "Diario", "Cuenta", "Nombre de la cuenta",
            "Tercero", "Descripción",
            "Debe %s" % usd.name, "Haber %s" % usd.name,
            "Debe Bs", "Haber Bs"])
        first_data = row
        for move in journal["moves"]:
            for line in move["lines"]:
                sheet.write_datetime(row, 0, fields.Datetime.to_datetime(
                    move["date"]), fmts["date"])
                sheet.write(row, 1, move["name"], fmts["text"])
                sheet.write(row, 2, move["journal"], fmts["text"])
                sheet.write(row, 3, line["account_code"], fmts["text"])
                sheet.write(row, 4, line["account_name"], fmts["text"])
                sheet.write(row, 5, line["partner"], fmts["text"])
                sheet.write(
                    row, 6, line["label"] or move["ref"], fmts["text"])
                sheet.write_number(row, 7, line["debit_usd"], fmts["num"])
                sheet.write_number(row, 8, line["credit_usd"], fmts["num"])
                sheet.write_number(row, 9, line["debit_bs"], fmts["num"])
                sheet.write_number(row, 10, line["credit_bs"], fmts["num"])
                row += 1
        if row > first_data:
            sheet.autofilter(first_data - 1, 0, row - 1, 10)
        sheet.freeze_panes(first_data, 0)
        totals = journal["totals"]
        sheet.write(row, 0, "TOTALES", fmts["total_label"])
        for col in range(1, 7):
            sheet.write(row, col, "", fmts["total_label"])
        for col, key in enumerate(
                ("debit_usd", "credit_usd", "debit_bs", "credit_bs"), start=7):
            sheet.write_number(row, col, totals[key], fmts["total_num"])

    # ------------------------------------------------------------------
    # Hoja: Libro Mayor
    # ------------------------------------------------------------------
    def _write_ledger_sheet(self, workbook, fmts, ledger, usd, bs):
        sheet = workbook.add_worksheet("Libro Mayor")
        sheet.set_column(0, 0, 11)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 28)
        sheet.set_column(3, 3, 42)
        sheet.set_column(4, 9, 16)
        row = self._write_header(sheet, fmts, "LIBRO MAYOR", usd)
        row = self._write_headers(sheet, fmts, row, [
            "Fecha", "Asiento", "Tercero", "Descripción",
            "Debe %s" % usd.name, "Haber %s" % usd.name,
            "Saldo %s" % usd.name,
            "Debe Bs", "Haber Bs", "Saldo Bs"])
        sheet.freeze_panes(row, 0)
        for account in ledger:
            title = ("%s - %s" % (account["code"], account["name"])
                     if account["code"] else account["name"])
            sheet.write(row, 0, title, fmts["section"])
            for col in range(1, 10):
                sheet.write(row, col, "", fmts["section"])
            row += 1
            # Saldo inicial
            label = _("Saldo inicial")
            if account["prior_results"]:
                label = _("Saldo inicial (utilidad o pérdida acumulada de "
                          "ejercicios anteriores)")
            sheet.write_datetime(row, 0, fields.Datetime.to_datetime(
                self.date_from), fmts["date"])
            for col in (1, 2):
                sheet.write(row, col, "", fmts["italic"])
            sheet.write(row, 3, label, fmts["italic"])
            for col in (4, 5, 7, 8):
                sheet.write(row, col, "", fmts["italic"])
            sheet.write_number(row, 6, account["initial_usd"], fmts["italic_num"])
            sheet.write_number(row, 9, account["initial_bs"], fmts["italic_num"])
            row += 1
            for entry in account["lines"]:
                sheet.write_datetime(row, 0, fields.Datetime.to_datetime(
                    entry["date"]), fmts["date"])
                sheet.write(row, 1, entry["move"], fmts["text"])
                sheet.write(row, 2, entry["partner"], fmts["text"])
                sheet.write(row, 3, entry["label"], fmts["text"])
                sheet.write_number(row, 4, entry["debit_usd"], fmts["num"])
                sheet.write_number(row, 5, entry["credit_usd"], fmts["num"])
                sheet.write_number(row, 6, entry["balance_usd"], fmts["num"])
                sheet.write_number(row, 7, entry["debit_bs"], fmts["num"])
                sheet.write_number(row, 8, entry["credit_bs"], fmts["num"])
                sheet.write_number(row, 9, entry["balance_bs"], fmts["num"])
                row += 1
            # Total de la cuenta
            sheet.write(row, 0, "TOTAL CUENTA", fmts["total_label"])
            for col in (1, 2, 3):
                sheet.write(row, col, "", fmts["total_label"])
            sheet.write_number(row, 4, account["debit_usd"], fmts["total_num"])
            sheet.write_number(row, 5, account["credit_usd"], fmts["total_num"])
            sheet.write_number(row, 6, account["final_usd"], fmts["total_num"])
            sheet.write_number(row, 7, account["debit_bs"], fmts["total_num"])
            sheet.write_number(row, 8, account["credit_bs"], fmts["total_num"])
            sheet.write_number(row, 9, account["final_bs"], fmts["total_num"])
            row += 2

    # ------------------------------------------------------------------
    # Hoja: Balance de Comprobación
    # ------------------------------------------------------------------
    def _write_trial_sheet(self, workbook, fmts, trial, usd, bs):
        sheet = workbook.add_worksheet("Balance de Comprobación")
        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 1, 52)
        sheet.set_column(2, 9, 17)
        row = self._write_header(
            sheet, fmts, "BALANCE DE COMPROBACIÓN", usd)
        sheet.write(
            4, 0, "Saldos: positivo = deudor, negativo = acreedor. El "
            "ejercicio fiscal inicia el %s." % trial["fy_start"].strftime(
                "%d/%m/%Y"), fmts["bold"])
        row = self._write_headers(sheet, fmts, row, [
            "Código", "Cuenta",
            "Saldo inicial %s" % usd.name, "Debe %s" % usd.name,
            "Haber %s" % usd.name, "Saldo final %s" % usd.name,
            "Saldo inicial Bs", "Debe Bs", "Haber Bs", "Saldo final Bs"])
        sheet.freeze_panes(row, 2)
        for item in trial["rows"]:
            sheet.write(row, 0, item["code"], fmts["text"])
            sheet.write(row, 1, item["name"], fmts["text"])
            for col, key in enumerate((
                    "initial_usd", "debit_usd", "credit_usd", "final_usd",
                    "initial_bs", "debit_bs", "credit_bs", "final_bs"),
                    start=2):
                sheet.write_number(row, col, item[key], fmts["num"])
            row += 1
        totals = trial["totals"]
        sheet.write(row, 0, "TOTALES", fmts["total_label"])
        sheet.write(row, 1, "", fmts["total_label"])
        for col, key in enumerate((
                "initial_usd", "debit_usd", "credit_usd", "final_usd",
                "initial_bs", "debit_bs", "credit_bs", "final_bs"), start=2):
            sheet.write_number(row, col, totals[key], fmts["total_num"])
        row += 2
        sheet.write(row, 0, "VERIFICACIÓN DE CUADRE", fmts["section"])
        sheet.write(row, 1, "", fmts["section"])
        sheet.write(row, 2, "Diferencia", fmts["section"])
        sheet.write(row, 3, "Estado", fmts["section"])
        row += 1
        for check in trial["checks"]:
            sheet.write(row, 0, "", fmts["text"])
            sheet.write(row, 1, check["label"], fmts["text"])
            sheet.write_number(row, 2, check["value"], fmts["num"])
            sheet.write(
                row, 3, "OK" if check["ok"] else "DESCUADRE",
                fmts["ok"] if check["ok"] else fmts["fail"])
            row += 1

    # ------------------------------------------------------------------
    # Hoja: Advertencias
    # ------------------------------------------------------------------
    def _write_warnings_sheet(self, workbook, fmts, trial, warnings, usd, bs):
        sheet = workbook.add_worksheet("Advertencias")
        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 1, 11)
        sheet.set_column(2, 2, 22)
        sheet.set_column(3, 3, 22)
        sheet.set_column(4, 4, 90)
        sheet.set_column(5, 5, 16)
        row = self._write_header(sheet, fmts, "ADVERTENCIAS", usd)

        sheet.write(row, 0, "Verificaciones de cuadre", fmts["section"])
        for col in range(1, 6):
            sheet.write(row, col, "", fmts["section"])
        row += 1
        for check in trial["checks"]:
            sheet.write(row, 0, check["label"], fmts["text"])
            sheet.write(
                row, 1, "OK" if check["ok"] else "FALLA",
                fmts["ok"] if check["ok"] else fmts["fail"])
            sheet.write_number(row, 5, check["value"], fmts["num"])
            row += 1
        row += 1

        sheet.write(row, 0, "Asientos a revisar", fmts["section"])
        for col in range(1, 6):
            sheet.write(row, col, "", fmts["section"])
        row += 1
        # Solo se afirma que todo cuadra si además pasaron todos los cuadres:
        # un DESCUADRE sin asiento listado no debe leerse como "sin problemas".
        if not warnings and all(check["ok"] for check in trial["checks"]):
            sheet.write(
                row, 0, "Sin advertencias: todos los asientos tienen tasa y "
                "cuadran en USD y Bs.", fmts["text"])
            return
        if not warnings:
            sheet.write(
                row, 0, "Algún cuadre falla pero ningún asiento individual "
                "explica la diferencia: revise los saldos de apertura o los "
                "asientos de otras compañías/ejercicios.", fmts["text"])
            return
        row = self._write_headers(sheet, fmts, row, [
            "Tipo", "Fecha", "Asiento", "Diario", "Detalle", "Valor"])
        for item in warnings:
            sheet.write(row, 0, item["type"], fmts["text"])
            if item["date"]:
                sheet.write_datetime(row, 1, fields.Datetime.to_datetime(
                    item["date"]), fmts["date"])
            else:
                sheet.write(row, 1, "", fmts["text"])
            sheet.write(row, 2, item["move"], fmts["text"])
            sheet.write(row, 3, item["journal"], fmts["text"])
            sheet.write(row, 4, item["detail"], fmts["wrap"])
            if item["value"] is None:
                sheet.write(row, 5, "", fmts["text"])
            else:
                sheet.write_number(row, 5, item["value"], fmts["num"])
            row += 1
