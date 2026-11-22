"""Pure cash-flow maths. No network, no I/O.

Method: standard direct-method weekly cash forecast (the "13-week cash flow" used by small businesses and lenders).
Each week is 7 days starting at ``start``; closing = opening + inflows - outflows.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

MAX_OCCURRENCES = 2000


class CashflowInputError(ValueError):
    """Raised for inputs that cannot be forecast; message tells the caller how to fix it."""


def _r(x: float) -> float:
    return round(x + 0.0, 2)


def add_months(d: date, months: int, anchor_day: int) -> date:
    """Add months keeping the anchor day, clamped to month end (31 Jan + 1 month = 28/29 Feb)."""
    idx = d.year * 12 + (d.month - 1) + months
    y, m = divmod(idx, 12)
    m += 1
    return date(y, m, min(anchor_day, calendar.monthrange(y, m)[1]))


def occurrences(first: date, repeat: str, until: date | None, horizon_end: date) -> list[date]:
    """All dates of an item up to the horizon end (and ``until`` if given)."""
    last = min(horizon_end, until) if until else horizon_end
    out: list[date] = []
    if repeat == "none":
        return [first] if first <= last else []
    step_months = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(repeat)
    n = 0
    while True:
        if repeat == "weekly":
            d = first + timedelta(days=7 * n)
        elif repeat == "biweekly":
            d = first + timedelta(days=14 * n)
        elif step_months:
            d = add_months(first, step_months * n, first.day)
        else:
            raise CashflowInputError(f"Unknown repeat '{repeat}'. Use none, weekly, biweekly, monthly, quarterly or yearly.")
        if d > last:
            break
        out.append(d)
        n += 1
        if n > MAX_OCCURRENCES:
            raise CashflowInputError("Too many repeats; shorten the horizon or the repeat period.")
    return out


def forecast(start: date, opening_balance: float, weeks: int, items: list[dict], min_buffer: float = 0.0,
             inflow_delay_days: int = 0, inflow_haircut_pct: float = 0.0) -> dict:
    """Weekly forecast. Items: label, amount (>0), direction in|out, date, repeat, until, confidence (0-1), delay_days."""
    if weeks < 1:
        raise CashflowInputError("weeks must be at least 1.")
    horizon_end = start + timedelta(days=7 * weeks - 1)
    inflow = [0.0] * weeks
    outflow = [0.0] * weeks
    warnings: list[str] = []
    counted = 0
    outside = 0
    low_conf_in = 0.0
    for it in items:
        if it["direction"] not in ("in", "out"):
            raise CashflowInputError(f"Item '{it['label']}': direction must be 'in' or 'out'.")
        is_in = it["direction"] == "in"
        delay = int(it.get("delay_days", 0)) + (inflow_delay_days if is_in else 0)
        conf = float(it.get("confidence", 1.0))
        if is_in:
            conf *= (1 - inflow_haircut_pct / 100)
        until = it.get("until")
        # shift the whole series by the delay, so a delayed monthly retainer also arrives late each time
        first = it["date"] + timedelta(days=delay)
        until_shifted = until + timedelta(days=delay) if until else None
        hit = False
        for d in occurrences(first, it.get("repeat", "none"), until_shifted, horizon_end):
            if d < start:
                continue
            w = (d - start).days // 7
            amt = it["amount"] * (conf if is_in else 1.0)
            if is_in:
                inflow[w] += amt
                low_conf_in += it["amount"] * (1 - conf) if conf < 1 else 0
            else:
                outflow[w] += it["amount"]
            hit = True
        if hit:
            counted += 1
        else:
            outside += 1
    rows = []
    bal = opening_balance
    lowest = (bal, None)
    first_neg = None
    below_buffer = []
    for i in range(weeks):
        net = inflow[i] - outflow[i]
        bal = bal + net
        ws = start + timedelta(days=7 * i)
        rows.append({"week": i + 1, "week_start": ws.isoformat(), "inflow": _r(inflow[i]), "outflow": _r(outflow[i]),
                     "net": _r(net), "closing_balance": _r(bal)})
        if lowest[1] is None or bal < lowest[0]:
            lowest = (bal, i + 1)
        if bal < 0 and first_neg is None:
            first_neg = i + 1
        if bal < min_buffer:
            below_buffer.append(i + 1)
    total_in, total_out = sum(inflow), sum(outflow)
    if first_neg:
        warnings.append(f"Cash goes negative in week {first_neg} ({rows[first_neg-1]['week_start']}): chase invoices, delay spending or arrange a buffer before then.")
    elif below_buffer:
        warnings.append(f"Balance falls below your {min_buffer:,.2f} buffer in {len(below_buffer)} week(s), first in week {below_buffer[0]}.")
    if opening_balance < 0:
        warnings.append("Opening balance is already negative.")
    if outside:
        warnings.append(f"{outside} item(s) fall outside the forecast window and were ignored.")
    if total_out == 0:
        warnings.append("No outflows entered: add rent, tools, tax and your own pay, or the forecast will look too good.")
    if total_in and total_out and total_in > 0 and max(inflow) / total_in > 0.5:
        warnings.append("More than half of all inflow lands in a single week: one late payment would change the picture. Run stress_test_cashflow.")
    warnings.append("Forecast is only as good as the inputs; reconcile against the bank statement weekly. Not financial advice.")
    return {
        "start": start.isoformat(), "end": horizon_end.isoformat(), "opening_balance": _r(opening_balance),
        "weeks": rows, "total_inflow": _r(total_in), "total_outflow": _r(total_out),
        "closing_balance": _r(bal), "lowest_balance": _r(lowest[0]), "lowest_week": lowest[1],
        "first_negative_week": first_neg or 0, "weeks_below_buffer": below_buffer, "warnings": warnings,
    }


def runway(cash: float, monthly_expenses: float, monthly_income: float = 0.0, monthly_income_growth_pct: float = 0.0,
           max_months: int = 120) -> dict:
    """Months of cash left. Month-by-month so income growth is honoured."""
    if monthly_expenses <= 0:
        raise CashflowInputError("monthly_expenses must be above 0.")
    warnings: list[str] = []
    burn = monthly_expenses - monthly_income
    bal = cash
    months = 0
    inc = monthly_income
    while bal >= 0 and months < max_months:
        bal += inc - monthly_expenses
        if bal < 0:
            # fraction of the final month that cash could cover
            prev = bal - (inc - monthly_expenses)
            shortfall = monthly_expenses - inc
            months_f = months + (prev / shortfall if shortfall > 0 else 0)
            break
        months += 1
        inc *= 1 + monthly_income_growth_pct / 100
        months_f = float(months)
    else:
        months_f = float(months)
    sustainable = bal >= 0
    if cash <= 0:
        months_f = 0.0
        sustainable = False
        warnings.append("No cash on hand.")
    elif sustainable:
        warnings.append(f"Income covers expenses within {max_months} months: no runway limit reached.")
    elif months_f < 3:
        warnings.append("Under 3 months of runway: act now (cut costs, chase receivables, raise prices).")
    elif months_f < 6:
        warnings.append("Under 6 months of runway: most advisers want at least 6 months of expenses in reserve.")
    warnings.append("Runway assumes flat expenses and the income path you gave. Not financial advice.")
    return {
        "cash": _r(cash), "monthly_expenses": _r(monthly_expenses), "monthly_income": _r(monthly_income),
        "net_monthly_burn": _r(burn), "runway_months": round(months_f, 1), "sustainable": sustainable,
        "months_of_expenses_in_cash": round(cash / monthly_expenses, 1), "warnings": warnings,
    }
