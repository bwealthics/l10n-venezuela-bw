# Part of l10n_ve_bw_payroll. License LGPL-3.
{
    "name": "Venezuela — Nómina (BWEALTHICS)",
    "summary": "Nómina venezolana: IVSS, RPE, FAOV, INCES, ISLR (AR-I), "
               "Contribución Especial de Pensiones, cesta ticket y recibo art. 106 LOTTT",
    "description": """
Localización de Nómina de Venezuela
===================================
* Estructuras: Nómina Regular y Utilidades (Odoo 19 Enterprise, hr_payroll).
* Deducciones del trabajador: IVSS 4% (tope 5 SM, lunes del período), RPE 0,5%
  (tope 10 SM), FAOV 1% (salario integral, sin tope), ISLR según % AR-I,
  INCES 0,5% sobre utilidades, retención judicial.
* Aportes patronales: IVSS 9/10/11% por clase de riesgo, RPE 2%, FAOV 2%,
  INCES 2%, Contribución Especial de Pensiones 9% (piso IMI en USD).
* Cesta ticket indexado en USD (no salarial, fuera del neto, base CEPP).
* Tasas y montos legales como hr.rule.parameter versionados por fecha —
  ninguna tasa está en el código.
* Bimoneda: el recibo calcula y contabiliza en la moneda de la compañía (USD)
  y muestra el contravalor en Bs a la tasa BCV de la fecha de pago.
* Recibo de pago art. 106 LOTTT (PDF bimonetario).
* Cuentas contables del chart ve_bw mapeadas automáticamente (hook).

Fuente normativa: Odoo/Localización VE/Nomina-VE-Requerimientos-2026.md (bóveda).
""",
    "version": "19.0.3.1.0",
    "license": "LGPL-3",
    "author": "BWEALTHICS LLC",
    "website": "https://www.bwealthics.com",
    "category": "Human Resources/Payroll",
    "countries": ["ve"],
    "depends": [
        "l10n_ve_bw_chart",
        "hr_payroll_account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/payroll_security.xml",
        "data/hr_salary_rule_category_data.xml",
        "data/hr_payroll_structure_type_data.xml",
        "data/hr_payroll_structure_data.xml",
        "data/hr_payslip_input_type_data.xml",
        "data/hr_rule_parameter_data.xml",
        "data/hr_salary_rule_regular_data.xml",
        "data/hr_salary_rule_utilidades_data.xml",
        "data/hr_salary_rule_vacaciones_data.xml",
        "data/hr_salary_rule_liquidacion_data.xml",
        "data/ir_cron_data.xml",
        "views/hr_employee_views.xml",
        "views/hr_payslip_views.xml",
        "views/res_config_settings_views.xml",
        "views/payroll_provision_views.xml",
        "views/prestaciones_views.xml",
        "wizards/liquidacion_wizard_views.xml",
        "wizards/declaraciones_export_views.xml",
        "views/menus.xml",
        "reports/report_payslip_ve.xml",
        "reports/prestaciones_statement.xml",
        "reports/arc_employee_report.xml",
    ],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "post_init_hook": "post_init_hook",
    "installable": True,
}
