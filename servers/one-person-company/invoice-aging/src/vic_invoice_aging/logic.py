"""Pure receivables maths for one-person companies (no I/O, no network).

Rules implemented (see README "How the numbers work"):
- EU: Directive 2011/7/EU on combating late payment in commercial transactions. Art. 3(1)(d): statutory
  interest = reference rate (ECB main refinancing rate in force on 1 Jan / 1 Jul) + at least 8 percentage points.
  Art. 6: fixed compensation of at least EUR 40 for recovery costs. Art. 3(5): B2B terms above 60 days must not be
  grossly unfair to the creditor. Member states may set stricter rules.
- UK: Late Payment of Commercial Debts (Interest) Act 1998: 8% over the Bank of England base rate (rate on 30 Jun /
  31 Dec before the debt became overdue), fixed sum GBP 40 (debt < 1,000), 70 (1,000 to 9,999.99), 100 (>= 10,000).
- Interest runs simple, actual/365, from the day after the due date.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta


class InvoiceInputError(ValueError):
    """Raised for inputs that cannot produce a meaningful result."""


def _r(x: float, n: int = 2) -> float:
    return round(x + 0.0, n)


def due_date(invoice_date: date, net_days: int, end_of_month: bool = False) -> dict:
    if net_days < 0:
        raise InvoiceInputError("net_days must be 0 or more.")
    base = invoice_date
    if end_of_month:
        base = date(invoice_date.year, invoice_date.month, calendar.monthrange(invoice_date.year, invoice_date.month)[1])
    due = base + timedelta(days=net_days)
    warnings = []
    if net_days > 60:
        warnings.append("Terms above 60 days can be challenged as grossly unfair between businesses under EU Directive 2011/7/EU Art. 3(5); check your local law.")
    if due.weekday() >= 5:
        warnings.append(f"Due date falls on a {due.strftime('%A')}; many payers settle on the next working day, so do not chase before then.")
    return {"invoice_date": invoice_date.isoformat(), "due_date": due.isoformat(), "weekday": due.strftime("%A"),
            "total_days": (due - invoice_date).days, "terms": ("EOM+" if end_of_month else "Net ") + str(net_days), "warnings": warnings}


def uk_fixed_sum(principal: float) -> float:
    if principal < 1000:
        return 40.0
    if principal < 10000:
        return 70.0
    return 100.0


def late_interest(principal: float, due: date, paid_or_as_of: date, regime: str, reference_rate_pct: float | None,
                  custom_annual_rate_pct: float | None, custom_fixed_fee: float) -> dict:
    if regime in ("eu", "uk"):
        if reference_rate_pct is None:
            raise InvoiceInputError("reference_rate_pct is required for eu/uk: the ECB main refinancing rate or the Bank of England base rate in force at the start of the half-year. Look it up; it is not hard-coded because it changes.")
        if not -1 <= reference_rate_pct <= 30:
            raise InvoiceInputError("reference_rate_pct must be between -1 and 30.")
        annual = reference_rate_pct + 8.0
        fixed = 40.0 if regime == "eu" else uk_fixed_sum(principal)
        basis = "reference rate + 8 percentage points"
    elif regime == "custom":
        if custom_annual_rate_pct is None:
            raise InvoiceInputError("custom_annual_rate_pct is required for regime custom (the rate written in your contract).")
        annual, fixed, basis = custom_annual_rate_pct, custom_fixed_fee, "contract rate"
    else:
        raise InvoiceInputError("regime must be eu, uk or custom.")
    days = (paid_or_as_of - due).days
    warnings = ["Statutory interest applies to business-to-business debts only, and only if the contract does not set a lawful rate; confirm with a local adviser before charging."]
    if days <= 0:
        return {"days_overdue": 0, "annual_rate_pct": _r(annual), "interest": 0.0, "fixed_compensation": 0.0, "total_claim": 0.0,
                "daily_interest": _r(principal * annual / 100 / 365, 4), "basis": basis,
                "warnings": ["Not overdue on the given date: no interest or fixed compensation yet."] + warnings}
    interest = principal * annual / 100 * days / 365
    if regime == "eu":
        warnings.append("EUR 40 is the EU minimum for fixed recovery costs; your country may set a higher sum or a different currency amount.")
    return {"days_overdue": days, "annual_rate_pct": _r(annual), "interest": _r(interest), "fixed_compensation": _r(fixed),
            "total_claim": _r(interest + fixed), "daily_interest": _r(principal * annual / 100 / 365, 4), "basis": basis, "warnings": warnings}


BUCKETS = ["not_due", "1_30", "31_60", "61_90", "over_90"]


def bucket_of(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "not_due"
    if days_overdue <= 30:
        return "1_30"
    if days_overdue <= 60:
        return "31_60"
    if days_overdue <= 90:
        return "61_90"
    return "over_90"


def age_invoices(as_of: date, invoices: list[dict]) -> dict:
    if not invoices:
        raise InvoiceInputError("Provide at least one invoice.")
    totals = {b: 0.0 for b in BUCKETS}
    counts = {b: 0 for b in BUCKETS}
    by_client: dict[str, float] = {}
    overdue = []
    warnings = []
    seen = set()
    for inv in invoices:
        iid = inv["invoice_id"]
        if iid in seen:
            warnings.append(f"Duplicate invoice_id {iid}: counted twice; check for a double entry.")
        seen.add(iid)
        paid = inv.get("paid_amount", 0.0)
        if paid > inv["amount"]:
            raise InvoiceInputError(f"Invoice {iid}: paid_amount exceeds amount.")
        open_amt = inv["amount"] - paid
        if open_amt <= 0:
            warnings.append(f"Invoice {iid} is fully paid and was skipped.")
            continue
        days = (as_of - inv["due_date"]).days
        b = bucket_of(days)
        totals[b] += open_amt
        counts[b] += 1
        by_client[inv["client"]] = by_client.get(inv["client"], 0.0) + open_amt
        if days > 0:
            overdue.append({"invoice_id": iid, "client": inv["client"], "open_amount": _r(open_amt), "days_overdue": days, "bucket": b})
    outstanding = sum(totals.values())
    if outstanding <= 0:
        raise InvoiceInputError("No open balance: every invoice is fully paid.")
    overdue_total = outstanding - totals["not_due"]
    overdue.sort(key=lambda x: (-x["days_overdue"], -x["open_amount"]))
    top_client, top_amt = max(by_client.items(), key=lambda kv: kv[1])
    if overdue_total / outstanding > 0.5:
        warnings.append("More than half of your open balance is overdue: chase now and pause new work for the worst payers.")
    if totals["over_90"] > 0:
        warnings.append("Invoices over 90 days overdue are often hard to recover; escalate in writing and consider a statutory interest claim.")
    if len(by_client) > 1 and top_amt / outstanding > 0.5:
        warnings.append(f"{top_client} is {_r(top_amt / outstanding * 100, 1)}% of your open balance: concentration risk.")
    return {"as_of": as_of.isoformat(), "outstanding": _r(outstanding), "overdue_total": _r(overdue_total),
            "overdue_pct": _r(overdue_total / outstanding * 100, 1),
            "buckets": [{"bucket": b, "amount": _r(totals[b]), "invoice_count": counts[b]} for b in BUCKETS],
            "by_client": [{"client": c, "open_amount": _r(a)} for c, a in sorted(by_client.items(), key=lambda kv: -kv[1])],
            "overdue_invoices": overdue, "warnings": warnings}


def reminder_stage(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "pre_due"
    if days_overdue <= 7:
        return "friendly"
    if days_overdue <= 30:
        return "firm"
    if days_overdue <= 60:
        return "formal"
    return "final"


def reminder_draft(client: str, invoice_id: str, open_amount: float, currency: str, days_overdue: int, sender: str,
                   language: str, interest_amount: float | None) -> dict:
    if language not in ("en", "zh"):
        raise InvoiceInputError("language must be en or zh.")
    stage = reminder_stage(days_overdue)
    amt = f"{currency} {open_amount:,.2f}"
    extra_en = f" Statutory late-payment interest of {currency} {interest_amount:,.2f} has accrued to date and may be claimed." if interest_amount and stage in ("formal", "final") else ""
    extra_zh = f"按约定/法定逾期利息目前累计 {currency} {interest_amount:,.2f}，我方保留主张的权利。" if interest_amount and stage in ("formal", "final") else ""
    en = {
        "pre_due": ("Upcoming payment: invoice {i}", "Hi {c},\n\nA quick heads-up that invoice {i} for {a} is due soon. Let me know if you need anything from me to process it.\n\nThanks,\n{s}"),
        "friendly": ("Reminder: invoice {i}", "Hi {c},\n\nInvoice {i} for {a} is {d} day(s) past due. It may have slipped through; could you confirm the payment date?\n\nThanks,\n{s}"),
        "firm": ("Overdue: invoice {i} ({d} days)", "Hi {c},\n\nInvoice {i} for {a} is now {d} days overdue. Please arrange payment this week or tell me the date it will be paid.{x}\n\nRegards,\n{s}"),
        "formal": ("Second notice: invoice {i} ({d} days overdue)", "Dear {c},\n\nDespite earlier reminders, invoice {i} for {a} remains unpaid {d} days after its due date. Please pay within 7 days.{x}\n\nSincerely,\n{s}"),
        "final": ("Final notice: invoice {i} ({d} days overdue)", "Dear {c},\n\nInvoice {i} for {a} is {d} days overdue. This is a final notice: unless payment or a written payment plan reaches me within 7 days, I will pause further work and pursue recovery.{x}\n\nSincerely,\n{s}"),
    }
    zh = {
        "pre_due": ("付款提醒：发票 {i} 即将到期", "{c} 您好，\n\n发票 {i}（{a}）即将到期，如处理付款需要我补充资料请告诉我。\n\n谢谢，\n{s}"),
        "friendly": ("温馨提醒：发票 {i}", "{c} 您好，\n\n发票 {i}（{a}）已逾期 {d} 天，可能是漏掉了，方便告知预计付款日期吗？\n\n谢谢，\n{s}"),
        "firm": ("发票 {i} 已逾期 {d} 天", "{c} 您好，\n\n发票 {i}（{a}）已逾期 {d} 天，请本周内安排付款，或告知确切付款日期。{x}\n\n此致，\n{s}"),
        "formal": ("第二次通知：发票 {i} 逾期 {d} 天", "{c} 您好，\n\n此前已多次提醒，发票 {i}（{a}）逾期 {d} 天仍未付款，请在 7 日内付清。{x}\n\n此致，\n{s}"),
        "final": ("最后通知：发票 {i} 逾期 {d} 天", "{c} 您好，\n\n发票 {i}（{a}）已逾期 {d} 天。这是最后通知：若 7 日内未收到付款或书面付款计划，我将暂停后续工作并启动追收。{x}\n\n此致，\n{s}"),
    }
    subj, body = (en if language == "en" else zh)[stage]
    x = extra_en if language == "en" else extra_zh
    fill = dict(i=invoice_id, c=client, a=amt, d=max(days_overdue, 0), s=sender, x=x)
    warnings = ["Draft only: nothing was sent. Review the tone and facts, then send it yourself."]
    if stage == "final":
        warnings.append("Final notices have legal weight in some countries; do not threaten specific legal action you are not prepared to take.")
    return {"stage": stage, "subject": subj.format(**fill), "body": body.format(**fill), "draft_only": True, "warnings": warnings}
