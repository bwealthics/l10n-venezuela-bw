# Copyright 2026 BWEALTHICS LLC
# Part of l10n_ve_bw_payroll. License LGPL-3.
"""Mapeo de cuentas del chart ve_bw a las reglas salariales.

account_debit/account_credit son company_dependent y el template de cuentas
no permite referencias XML cross-módulo, así que el mapeo se hace por código
de cuenta al instalar. Para re-ejecutarlo (p. ej. tras crear una compañía VE
nueva) desde odoo-bin shell:

    from odoo.addons.l10n_ve_bw_payroll.hooks import map_rule_accounts
    map_rule_accounts(env, env['res.company'].browse(<id>))
"""
import logging

_logger = logging.getLogger(__name__)

# XML-ID de la regla -> (código cuenta débito, código cuenta crédito)
# Convención hr_payroll_account: una regla de monto NEGATIVO (deducción) lleva
# su pasivo en el slot de DÉBITO — el core invierte el signo y lo acredita
# (ver l10n_be_hr_payroll_account: "this is a credit, but the amount is
# negative"). Ponerlo en account_credit lo DEBITARÍA.
RULE_ACCOUNTS = {
    "rule_ve_reg_basic": ("610101", None),
    "rule_ve_reg_bnoct": ("610102", None),
    "rule_ve_reg_hed": ("610103", None),
    "rule_ve_reg_hen": ("610103", None),
    "rule_ve_reg_feriado": ("610104", None),
    "rule_ve_reg_comis": ("610105", None),
    "rule_ve_reg_bono_ns": ("610105", None),
    "rule_ve_reg_cesta": ("610201", "210502"),
    "rule_ve_reg_ivss_emp": ("210503", None),
    "rule_ve_reg_rpe_emp": ("210505", None),
    "rule_ve_reg_faov_emp": ("210504", None),
    "rule_ve_reg_islr": ("210507", None),
    "rule_ve_reg_embargo": ("210704", None),
    "rule_ve_reg_net": (None, "210501"),
    "rule_ve_reg_ivss_pat": ("610301", "210503"),
    "rule_ve_reg_rpe_pat": ("610303", "210505"),
    "rule_ve_reg_faov_pat": ("610302", "210504"),
    "rule_ve_reg_inces_pat": ("610304", "210506"),
    "rule_ve_reg_cepp_pat": ("610305", "210510"),
    # v2: el pago de utilidades consume la provisión (el gasto ya se devengó
    # mensualmente vía la corrida de provisiones).
    "rule_ve_util_util": ("210601", None),
    "rule_ve_util_inces_emp": ("210506", None),
    "rule_ve_util_islr": ("210507", None),
    "rule_ve_util_net": (None, "210501"),
    "rule_ve_util_cepp_pat": ("610305", "210510"),
    # Vacaciones (pagan contra las provisiones 2106xx)
    "rule_ve_vac_vac": ("210602", None),
    "rule_ve_vac_bvac": ("210603", None),
    "rule_ve_vac_ivss_emp": ("210503", None),
    "rule_ve_vac_rpe_emp": ("210505", None),
    "rule_ve_vac_faov_emp": ("210504", None),
    "rule_ve_vac_islr": ("210507", None),
    "rule_ve_vac_net": (None, "210501"),
    "rule_ve_vac_ivss_pat": ("610301", "210503"),
    "rule_ve_vac_rpe_pat": ("610303", "210505"),
    "rule_ve_vac_faov_pat": ("610302", "210504"),
    "rule_ve_vac_inces_pat": ("610304", "210506"),
    "rule_ve_vac_cepp_pat": ("610305", "210510"),
    # Liquidación (neto a 210508 Liquidaciones por Pagar)
    "rule_ve_liq_prest_gar": ("220101", None),
    "rule_ve_liq_prest_extra": ("610401", None),
    "rule_ve_liq_prest_trim": ("610401", None),
    "rule_ve_liq_int": ("220102", None),
    "rule_ve_liq_vac": ("210602", None),
    "rule_ve_liq_bvac": ("210603", None),
    "rule_ve_liq_util": ("210601", None),
    "rule_ve_liq_inces_util": ("210506", None),
    "rule_ve_liq_islr": ("210507", None),
    "rule_ve_liq_cepp_pat": ("610305", "210510"),
    "rule_ve_liq_net": (None, "210508"),
}

# Cuentas que el chart puede no tener aún en compañías con ve_bw instalado
# antes del bump 19.0.1.1.0 (el template no re-carga en upgrade).
MISSING_ACCOUNTS = [
    ("610305", "Aporte Contribución Especial de Pensiones", "expense"),
    ("210510", "Contribución Especial de Pensiones por Pagar", "liability_current"),
]


def _ensure_accounts(env, company):
    Account = env["account.account"].with_company(company)
    for code, name, account_type in MISSING_ACCOUNTS:
        if not Account.search_count([
                ("code", "=", code), ("company_ids", "in", company.id)], limit=1):
            Account.create({
                "code": code,
                "name": name,
                "account_type": account_type,
                "company_ids": [(6, 0, [company.id])],
            })
            _logger.info("l10n_ve_bw_payroll: cuenta %s creada en %s", code, company.name)


def map_rule_accounts(env, company):
    _ensure_accounts(env, company)
    Account = env["account.account"].with_company(company)

    def _account(code):
        account = Account.search([
            ("code", "=", code), ("company_ids", "in", company.id)], limit=1)
        if not account:
            _logger.warning(
                "l10n_ve_bw_payroll: cuenta %s inexistente en %s — la regla "
                "quedará sin mapear", code, company.name)
        return account

    for xmlid, (debit, credit) in RULE_ACCOUNTS.items():
        rule = env.ref("l10n_ve_bw_payroll.%s" % xmlid, raise_if_not_found=False)
        if not rule:
            continue
        rule = rule.with_company(company)
        # Escribir SIEMPRE ambos slots: un re-run debe limpiar mapeos viejos
        # (dos slots poblados generan líneas espejo que netean el pasivo a 0).
        rule.account_debit = _account(debit) if debit else False
        rule.account_credit = _account(credit) if credit else False

    # Las cuentas crédito de las reglas NET deben ser conciliables para poder
    # registrar el pago desde el payslip (exigencia de hr_payroll_account).
    for net_code in ("210501", "210508"):
        net_account = _account(net_code)
        if net_account and not net_account.reconcile:
            net_account.reconcile = True


def post_init_hook(env):
    companies = env["res.company"].search([("chart_template", "=", "ve_bw")])
    if not companies:
        _logger.warning(
            "l10n_ve_bw_payroll: ninguna compañía usa el chart ve_bw; "
            "las cuentas de las reglas quedaron sin mapear.")
    for company in companies:
        map_rule_accounts(env, company)
