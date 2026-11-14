"""Pure pricing maths for one-person companies (no I/O, no network).

Conventions (see README "How the numbers work"):
- Tax and fee shares are *divisions*: to keep 75% you divide by 0.75, you do not add 25%.
- Billable hours = working weeks x hours per week x utilization (billable share of worked hours).
- Tax is charged on pre-tax profit, and business expenses are deductible, so
  revenue = net / (1 - tax) + expenses.
"""

from __future__ import annotations


class PricingInputError(ValueError):
    """Raised for inputs that cannot produce a meaningful price."""


def _r(x: float, n: int = 2) -> float:
    return round(x + 0.0, n)


def hourly_rate(
    target_net_income: float, annual_expenses: float, tax_rate_pct: float, weeks_off: float,
    hours_per_week: float, utilization_pct: float, buffer_pct: float, payment_fee_pct: float,
    days_per_week: float,
) -> dict:
    if not 0 <= tax_rate_pct < 90 or not 0 <= payment_fee_pct < 50:
        raise PricingInputError("tax_rate_pct must be in [0, 90) and payment_fee_pct in [0, 50).")
    working_weeks = 52 - weeks_off
    if working_weeks <= 0:
        raise PricingInputError("weeks_off must be below 52.")
    billable_hours = working_weeks * hours_per_week * utilization_pct / 100
    if billable_hours <= 0:
        raise PricingInputError("Billable hours must be above zero.")
    pre_tax_profit = target_net_income / (1 - tax_rate_pct / 100)
    revenue_needed = (pre_tax_profit + annual_expenses) * (1 + buffer_pct / 100)
    invoiced = revenue_needed / (1 - payment_fee_pct / 100)
    rate = invoiced / billable_hours
    naive = (target_net_income + annual_expenses) / (working_weeks * hours_per_week)
    billable_per_day = hours_per_week * utilization_pct / 100 / days_per_week
    warnings = []
    if utilization_pct > 75:
        warnings.append("Utilization above 75% is rarely sustained: sales, admin, revisions and learning take time. Track real hours for a month before relying on it.")
    if billable_hours > 1600:
        warnings.append(f"{billable_hours:.0f} billable hours a year is more than most solo operators actually invoice (typically 1,000 to 1,500).")
    if tax_rate_pct == 0 and target_net_income > 0:
        warnings.append("Tax rate is 0%: income tax and social contributions are ignored, so the rate is a floor that is too low in most countries.")
    warnings.append("This is a floor, not a market price. Compare it with what clients in your niche pay, and quote above it.")
    return {
        "working_weeks": _r(working_weeks, 1), "billable_hours_per_year": _r(billable_hours, 1),
        "pre_tax_profit_needed": _r(pre_tax_profit), "revenue_needed_before_fees": _r(revenue_needed),
        "revenue_to_invoice": _r(invoiced), "hourly_rate": _r(rate), "day_rate": _r(rate * billable_per_day),
        "naive_rate_ignoring_tax_and_utilization": _r(naive), "underpricing_if_naive_pct": _r((1 - naive / rate) * 100, 1),
        "warnings": warnings,
    }


def fixed_project_price(
    estimated_hours: float, hourly_rate_: float, risk_buffer_pct: float, revision_rounds: int,
    hours_per_revision: float, pass_through_costs: float, payment_fee_pct: float,
) -> dict:
    if not 0 <= payment_fee_pct < 50:
        raise PricingInputError("payment_fee_pct must be in [0, 50).")
    planned = estimated_hours * (1 + risk_buffer_pct / 100) + revision_rounds * hours_per_revision
    labour = planned * hourly_rate_
    net_needed = labour + pass_through_costs
    price = net_needed / (1 - payment_fee_pct / 100)
    scenarios = []
    for pct in (100, 125, 150, 200):
        hrs = planned * pct / 100
        eff = (net_needed - pass_through_costs) / hrs
        scenarios.append({"hours_worked": _r(hrs, 1), "overrun_pct": pct - 100, "effective_hourly_rate": _r(eff), "vs_target_rate_pct": _r((eff / hourly_rate_ - 1) * 100, 1)})
    warnings = []
    if risk_buffer_pct < 15:
        warnings.append("Risk buffer under 15%: fixed-price projects usually overrun. Consider 20 to 30% unless the scope is tiny and well known.")
    if revision_rounds == 0:
        warnings.append("No revision rounds included. State in the quote how many are covered and what extra rounds cost.")
    warnings.append("Write the scope, number of revisions, payment schedule and change-request rate into the quote; the price only holds for that scope.")
    return {
        "planned_hours": _r(planned, 1), "labour_cost": _r(labour), "pass_through_costs": _r(pass_through_costs),
        "quote_price": _r(price), "fees_absorbed": _r(price - net_needed), "scenarios": scenarios, "warnings": warnings,
    }


def fee_gross_up(net_wanted: float, fee_pct: float, fixed_fee: float, fx_spread_pct: float) -> dict:
    total_pct = fee_pct + fx_spread_pct
    if not 0 <= total_pct < 50:
        raise PricingInputError("fee_pct + fx_spread_pct must be in [0, 50).")
    gross = (net_wanted + fixed_fee) / (1 - total_pct / 100)
    naive = net_wanted * (1 + total_pct / 100) + fixed_fee
    warnings = ["Fee rates differ by country, card type and plan, and change over time. Enter the rates shown in your own payment dashboard."]
    if total_pct >= 10:
        warnings.append("Combined fees of 10% or more: consider a cheaper payment route (bank transfer, local method) for large invoices.")
    return {
        "invoice_amount": _r(gross), "total_fees": _r(gross - net_wanted), "effective_fee_pct": _r((gross - net_wanted) / gross * 100, 2),
        "naive_markup_amount": _r(naive), "naive_shortfall": _r(gross - naive), "warnings": warnings,
    }


def discount_impact(price: float, unit_variable_cost: float, discount_pct: float, current_units: float) -> dict:
    if unit_variable_cost >= price:
        raise PricingInputError("unit_variable_cost must be below price; otherwise there is no margin to protect.")
    margin = price - unit_variable_cost
    new_price = price * (1 - discount_pct / 100)
    new_margin = new_price - unit_variable_cost
    warnings = []
    if new_margin <= 0:
        warnings.append("After this discount each sale loses money or breaks even: no extra volume can restore the profit.")
        return {"old_unit_margin": _r(margin), "new_price": _r(new_price), "new_unit_margin": _r(new_margin),
                "required_volume_increase_pct": None, "required_units": None, "profit_at_current_volume_after_discount": _r(new_margin * current_units),
                "profit_now": _r(margin * current_units), "warnings": warnings}
    inc = margin / new_margin - 1
    if inc > 0.5:
        warnings.append("You would need over 50% more sales just to stand still. Prefer a bundle, a bonus or a payment-term incentive over a price cut.")
    warnings.append("Ignores extra support time and fixed costs; for services, count your own hours as a variable cost.")
    return {"old_unit_margin": _r(margin), "new_price": _r(new_price), "new_unit_margin": _r(new_margin),
            "required_volume_increase_pct": _r(inc * 100, 1), "required_units": _r(current_units * (1 + inc), 1),
            "profit_at_current_volume_after_discount": _r(new_margin * current_units), "profit_now": _r(margin * current_units), "warnings": warnings}


def real_hourly_rate(revenue: float, payment_fee_pct: float, direct_costs: float, hours_worked: float, target_hourly_rate: float | None) -> dict:
    if not 0 <= payment_fee_pct < 100:
        raise PricingInputError("payment_fee_pct must be in [0, 100).")
    fees = revenue * payment_fee_pct / 100
    net = revenue - fees - direct_costs
    real = net / hours_worked
    warnings = []
    short = None
    if target_hourly_rate:
        short = _r((real / target_hourly_rate - 1) * 100, 1)
        if 0 < real < target_hourly_rate:
            warnings.append(f"You earned {abs(short):.1f}% below your target rate on this job. Raise the next quote, tighten scope or cap revisions.")
    if net <= 0:
        warnings.append("This job lost money after fees and costs.")
    warnings.append("Count every hour: calls, emails, revisions and unpaid scoping, not only design or coding time.")
    return {"fees": _r(fees), "net_earned": _r(net), "real_hourly_rate": _r(real), "vs_target_pct": short, "warnings": warnings}
