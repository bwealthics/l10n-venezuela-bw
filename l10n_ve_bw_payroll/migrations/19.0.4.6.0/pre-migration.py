# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
"""v4.6: input_type_anticipo y rule_ve_reg_anticipo se crearon a mano en
una base en producción (2026-10-25) antes de existir en el módulo. Adoptarlos con su
XML-ID antes de cargar los datos evita duplicar el input ANTICIPO y la regla
VE_ANTICIPO (y deja vivos los ajustes salariales que ya los usan)."""


def _adopt(cr, name, model, table, where, params):
    cr.execute(
        "SELECT 1 FROM ir_model_data WHERE module = 'l10n_ve_bw_payroll' "
        "AND name = %s", (name,))
    if cr.fetchone():
        return
    cr.execute("SELECT id FROM %s WHERE %s ORDER BY id LIMIT 1" % (table, where),
               params)
    row = cr.fetchone()
    if not row:
        return
    cr.execute(
        "INSERT INTO ir_model_data (module, name, model, res_id, noupdate) "
        "VALUES ('l10n_ve_bw_payroll', %s, %s, %s, false)",
        (name, model, row[0]))


def migrate(cr, version):
    _adopt(cr, "input_type_anticipo", "hr.payslip.input.type",
           "hr_payslip_input_type", "code = %s", ("ANTICIPO",))
    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module = 'l10n_ve_bw_payroll' "
        "AND name = 'structure_ve_regular'")
    struct = cr.fetchone()
    if struct:
        _adopt(cr, "rule_ve_reg_anticipo", "hr.salary.rule", "hr_salary_rule",
               "code = %s AND struct_id = %s", ("VE_ANTICIPO", struct[0]))
