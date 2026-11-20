"""Pure functions for export sample policy: cost, tiers, ROI, first-order credit, clause drafts.

Practice sources (not law): exporter SOPs describe four sample arrangements (free + freight collect, free + prepaid
freight credited later, refundable sample fee, fully paid) and say any credit must be written into the PI/e-mail.
All money is in ONE currency chosen by the caller; no conversion is done.
"""
from __future__ import annotations

from datetime import date

TIERS = ["FREE_COLLECT", "FREE_FREIGHT_CREDIT", "FEE_CREDIT", "FULL_PAID", "NO_SAMPLE"]
TIER_NAMES = {
    "FREE_COLLECT": "样品免费，运费到付（买方快递账号）/ Free sample, freight collect",
    "FREE_FREIGHT_CREDIT": "样品免费，卖方垫运费，首单抵扣 / Free sample, freight prepaid by us, credited on first order",
    "FEE_CREDIT": "收样品费，首单抵扣 / Paid sample, fee credited on first order",
    "FULL_PAID": "样品费和运费全收，不退 / Sample fee and freight fully paid, not refundable",
    "NO_SAMPLE": "暂不寄样，发目录/视频/检测报告 / No sample for now, send catalogue, video or test report",
}


class SamplePolicyInputError(ValueError):
    """Invalid input; the message tells the caller how to fix it."""


def _r(x: float) -> float:
    return round(x + 1e-12, 2)


def quote_package(items: list[dict], freight: float, handling_fee: float, markup_pct: float) -> dict:
    if not items:
        raise SamplePolicyInputError("items must contain at least one sample line.")
    product = sum(i["qty"] * i["unit_cost"] for i in items)
    prep = sum(i.get("prep_fee", 0.0) for i in items)
    charge = product * (1 + markup_pct / 100) + prep + handling_fee
    base_out = product + prep + handling_fee  # what the sample costs us before freight
    rows = []

    def row(tier, buyer_now, outlay, credit, note):
        rows.append({"tier": tier, "name": TIER_NAMES[tier], "buyer_pays_you_now": _r(buyer_now),
                     "your_cash_outlay": _r(outlay), "your_net_if_no_order": _r(buyer_now - outlay),
                     "credit_on_first_order": _r(credit), "note": note})

    row("FREE_COLLECT", 0, base_out, 0, "Buyer pays the courier directly with his own account; freight is not in your outlay.")
    row("FREE_FREIGHT_CREDIT", 0, base_out + freight, freight, "You prepay freight; only the freight is credited when the first order is paid.")
    row("FEE_CREDIT", charge + freight, base_out + freight, charge, "Buyer pays fee plus freight up front; only the sample fee is credited, freight is not.")
    row("FULL_PAID", charge + freight, base_out + freight, 0, "Buyer pays fee plus freight; nothing is credited unless you agree later.")
    warns = []
    if markup_pct == 0 and handling_fee == 0:
        warns.append("Sample fee equals your cost price; add a handling fee or markup if staff time and packing are not free.")
    if freight > product + prep and product + prep > 0:
        warns.append("Freight is higher than the sample itself: never prepay it for an unverified buyer.")
    if base_out == 0:
        warns.append("Sample cost, prep and handling are all 0: check unit_cost before quoting.")
    warns.append("Credits must be written into the PI or e-mail (which order, which amount, expiry); verbal promises cause disputes.")
    return {"product_cost": _r(product), "prep_total": _r(prep), "handling_fee": _r(handling_fee), "freight": _r(freight),
            "sample_charge": _r(charge), "rows": rows, "warnings": warns}


def roi(outlay: float, buyer_paid: float, credit: float, order_value: float, margin_pct: float, conversion_pct: float) -> dict:
    om = order_value * margin_pct / 100
    a = om + buyer_paid - credit - outlay  # profit if the buyer orders
    b = buyer_paid - outlay  # profit (loss) if he does not
    p = conversion_pct / 100
    ev = p * a + (1 - p) * b
    be = None
    if b < 0 and a > b:
        be = _r(-b / (a - b) * 100)
    warns = ["The conversion rate is your own estimate; use your CRM history of samples sent versus orders received, not hope."]
    if a <= 0:
        warns.append("Even if the buyer orders you lose money after the credit and sample cost: shrink the credit or raise the minimum order.")
    if be is not None and conversion_pct < be:
        warns.append(f"Expected value is negative: you need at least {be}% of buyers to order to break even.")
    if b >= 0:
        warns.append("This policy never loses money on the sample itself, but charging may cost you good buyers.")
    return {"profit_if_order": _r(a), "profit_if_no_order": _r(b), "expected_profit": _r(ev),
            "break_even_conversion_pct": be, "warnings": warns}


def credit(fee: float, prep: float, freight: float, scope: list[str], cap_pct: float, min_order: float, valid_days: int,
           sample_date: str, order_date: str, order_value: float) -> dict:
    try:
        d0, d1 = date.fromisoformat(sample_date), date.fromisoformat(order_date)
    except ValueError as e:
        raise SamplePolicyInputError("Dates must be YYYY-MM-DD, e.g. 2026-11-20.") from e
    if d1 < d0:
        raise SamplePolicyInputError("order_date is before sample_date; check the dates.")
    paid = {"sample_fee": fee, "prep_fee": prep, "freight": freight}
    eligible = sum(paid[s] for s in set(scope))
    days = (d1 - d0).days
    reasons, warns = [], []
    cap = order_value * cap_pct / 100
    c = min(eligible, cap)
    if order_value < min_order:
        c = 0.0
        reasons.append(f"Order value {order_value} is below the agreed minimum {min_order}; no credit.")
    if days > valid_days:
        c = 0.0
        reasons.append(f"Order placed {days} days after the sample, beyond the {valid_days}-day validity; no credit.")
    if c and c < eligible:
        if cap_pct >= 100:
            reasons.append(f"Credit cannot exceed the order value ({_r(cap)}); eligible amount was {_r(eligible)}.")
        else:
            reasons.append(f"Credit capped at {cap_pct}% of the order ({_r(cap)}); eligible amount was {_r(eligible)}.")
    if eligible == 0:
        warns.append("Nothing in the agreed scope was actually paid, so there is nothing to credit.")
    if freight and "freight" not in scope:
        warns.append("Freight was paid but is not creditable under this scope; say so in writing to avoid a dispute.")
    return {"eligible_amount": _r(eligible), "credit": _r(c), "days_since_sample": days,
            "order_value": _r(order_value), "payable_after_credit": _r(order_value - c), "reasons": reasons, "warnings": warns}


def triage(email_type: str, company_verified: bool | None, specs_given: bool, target_qty_given: bool,
           asks_testing_details: bool, refuses_any_cost: bool, many_models_no_project: bool, residential_address: bool,
           unanswered_samples: int, pressure_to_ship: bool, met_in_person: bool, customized: bool, sample_value: float,
           value_threshold: float, has_courier_account: bool) -> dict:
    s, flags = 50, []

    def add(n, why):
        nonlocal s
        s += n
        if n < 0:
            flags.append(why)

    add({"corporate": 10, "free": -10, "lookalike": -25}[email_type], {"free": "Free e-mail address", "lookalike": "E-mail domain imitates a known company", "corporate": ""}[email_type])
    if company_verified is True:
        add(15, "")
    elif company_verified is False:
        add(-10, "Company could not be verified")
    if specs_given:
        add(10, "")
    if target_qty_given:
        add(10, "")
    if asks_testing_details:
        add(5, "")
    if refuses_any_cost:
        add(-20, "Refuses to pay even freight")
    if many_models_no_project:
        add(-10, "Asks for many models with no project")
    if residential_address:
        add(-10, "Residential or mismatched delivery address")
    if unanswered_samples:
        add(-10 * min(unanswered_samples, 3), f"{unanswered_samples} earlier sample(s) got no feedback")
    if pressure_to_ship:
        add(-10, "Pressure to ship before specs or price are agreed")
    if met_in_person:
        add(10, "")
    s = max(0, min(100, s))
    flags = [f for f in flags if f]
    idx = 4 if s < 25 else 3 if s < 45 else 2 if s < 60 else 1 if s < 75 else 0
    why = [f"Score {s}/100 maps to {TIERS[idx]}."]
    if idx == 0 and not has_courier_account:
        idx = 1
        why.append("No valid buyer courier account, so freight collect is not available: prepay and credit instead.")
    floor = 0
    if customized:
        floor = max(floor, 2)
        why.append("Customised samples are project work: at least a refundable fee.")
    if sample_value >= value_threshold:
        floor = max(floor, 2)
        why.append(f"Sample value {sample_value} reaches the {value_threshold} threshold: at least a refundable fee.")
    if idx < floor:
        idx = floor
    if email_type == "lookalike" or unanswered_samples >= 2:
        idx = max(idx, 3)
        why.append("Hard red flag: never better than fully paid.")
    warns = ["Triage is a heuristic on what the buyer told you; verify the company before shipping anything valuable."]
    if flags:
        warns.append("Red flags: " + "; ".join(flags) + ".")
    return {"score": s, "tier": TIERS[idx], "tier_name": TIER_NAMES[TIERS[idx]], "reasons": why, "red_flags": flags,
            "before_you_ship": ["Confirm model, quantity, use and expected order size in writing.",
                                "Photograph the packed sample and e-mail it before dispatch.",
                                "Record the courier account number and the credit terms in the PI."], "warnings": warns}


def draft_terms(tier: str, currency: str, fee: float, freight: float, scope_text: str, min_order: float, valid_days: int) -> dict:
    if tier == "NO_SAMPLE":
        raise SamplePolicyInputError("NO_SAMPLE has no sample terms; reply with a catalogue, video or test report instead.")
    if tier not in TIERS:
        raise SamplePolicyInputError(f"Unknown tier {tier!r}. Valid: {', '.join(TIERS[:4])}.")
    f, fr = f"{currency} {fee:.2f}", f"{currency} {freight:.2f}"
    if tier == "FREE_COLLECT":
        en = ("The sample is free of charge. Freight is collect: please send us your courier account number (DHL/UPS/FedEx). "
              "If the account is invalid or the consignee refuses the freight or duties, the buyer is responsible for all courier charges.")
        zh = "样品免费，运费到付：请提供您的快递账号（DHL/UPS/FedEx）。账号无效或收件人拒付运费、关税时，一切快递费用由买方承担。"
    elif tier == "FREE_FREIGHT_CREDIT":
        en = (f"The sample is free of charge. We prepay the courier freight of about {fr}; this freight will be deducted from the payment "
              f"of your first order of {currency} {min_order:.2f} or more placed within {valid_days} days of dispatch.")
        zh = f"样品免费。我们先垫付快递费约 {fr}，在寄样后 {valid_days} 天内、金额不低于 {currency} {min_order:.2f} 的首单货款中扣除。"
    elif tier == "FEE_CREDIT":
        en = (f"Sample fee: {f}, freight: {fr}, both payable before dispatch. The sample fee ({f}, freight excluded) will be deducted from "
              f"the payment of your first order of {currency} {min_order:.2f} or more placed within {valid_days} days of dispatch. {scope_text}".strip())
        zh = (f"样品费 {f}，运费 {fr}，寄样前付清。样品费（不含运费）在寄样后 {valid_days} 天内、金额不低于 {currency} {min_order:.2f} 的首单货款中抵扣。"
              + (f" {scope_text}" if scope_text else ""))
    else:
        en = f"Sample fee: {f}, freight: {fr}, both payable before dispatch and non-refundable. {scope_text}".strip()
        zh = f"样品费 {f}，运费 {fr}，寄样前付清，不予退还。" + (f" {scope_text}" if scope_text else "")
    extra = []
    if tier in ("FREE_FREIGHT_CREDIT", "FEE_CREDIT") and min_order == 0:
        extra.append("No minimum order value given, so any order would trigger the credit: set one.")
    if tier in ("FEE_CREDIT", "FULL_PAID") and fee == 0:
        extra.append("Sample fee is 0 in a paid tier: enter the fee you quote.")
    return {"tier": tier, "english": en, "chinese": zh,
            "warnings": extra + ["Draft only: review and adapt before sending; this is not legal advice.",
                         "Paste the clause into the PI or the e-mail the buyer confirms, not only into chat."]}
