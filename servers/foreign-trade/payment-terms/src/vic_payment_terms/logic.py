"""Pure payment-term logic (no MCP imports). Rules cited:
- UCP 600 (ICC): art. 6 expiry, 7(b) issuing bank undertaking, 14(b) max 5 banking days to examine,
  14(c) original transport documents presented within 21 calendar days after shipment, art. 16 single refusal notice.
- URC 522 (ICC) for documentary collections (D/P, D/A): banks do not guarantee payment.
- Soft clauses (软条款): terms that make payment depend on something only the applicant controls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class PaymentTermsInputError(ValueError):
    """Raised for invalid user input; the protocol layer turns it into a ToolError."""


# ---------------------------------------------------------------------------
# Term matrix
# ---------------------------------------------------------------------------
TERMS: dict[str, dict] = {
    "TT_ADVANCE": {
        "name": "T/T 100% in advance (电汇全款预付)",
        "bank_guarantee": False,
        "seller_risk": 1, "buyer_risk": 5,
        "who_carries_risk": "Buyer carries the risk (pays before seeing goods).",
        "how_it_works": "Buyer wires 100% before production or shipment. Seller ships after the funds are cleared.",
        "rules": "No ICC rule; governed by the sales contract. Wire is irrevocable once credited.",
        "pitfalls": [
            "Check funds are credited (cleared) in your account, not just a SWIFT MT103 screenshot: fake MT103s are a common scam.",
            "New buyers rarely accept it above a few thousand USD; offer it for samples and small first orders.",
        ],
        "best_for": "Samples, small first orders, made-to-order goods from a seller with a strong position.",
    },
    "TT_DEPOSIT": {
        "name": "T/T deposit + balance before shipment/release (定金 + 发货前/见提单副本付尾款)",
        "bank_guarantee": False,
        "seller_risk": 2, "buyer_risk": 3,
        "who_carries_risk": "Shared. Seller is exposed only to the unpaid part of the cost during production; goods are not released until the balance clears.",
        "how_it_works": "e.g. 30% deposit at order, 70% balance before shipment or before the original B/L (or telex release) is handed over.",
        "rules": "No ICC rule; write exact percentages, deadlines and the release condition into the contract.",
        "pitfalls": [
            "'Balance against copy of B/L' is NOT secure unless you keep the original B/L (or do not telex-release/ switch to a sea waybill) until the balance is credited.",
            "Deposit must at least cover raw materials and custom items; a 30% deposit on made-to-order goods can be below your cost.",
        ],
        "best_for": "The mainstream choice for first and repeat orders between small and mid-size traders.",
    },
    "TT_AFTER_BL": {
        "name": "T/T balance after shipment (e.g. 70% within 7 days of B/L date)",
        "bank_guarantee": False,
        "seller_risk": 3, "buyer_risk": 2,
        "who_carries_risk": "Seller carries the balance risk once the goods have left.",
        "how_it_works": "Deposit at order; balance due some days after the B/L date. Buyer can often get the goods through a telex release or sea waybill first.",
        "rules": "No ICC rule; unsecured trade credit.",
        "pitfalls": [
            "If the buyer holds the B/L originals or you telex-released, you have no leverage. Consider credit insurance.",
            "Define the due date from B/L date, not from 'arrival'.",
        ],
        "best_for": "Repeat buyers with a clean payment history.",
    },
    "LC_SIGHT": {
        "name": "L/C at sight (即期信用证)",
        "bank_guarantee": True,
        "seller_risk": 2, "buyer_risk": 2,
        "who_carries_risk": "Issuing bank pays against complying documents. Seller carries document risk and the issuing bank's credit risk (reduced if confirmed).",
        "how_it_works": "Buyer's bank issues the credit; seller ships, presents documents within 21 days of shipment (UCP 600 art. 14(c)) and before expiry; each bank has up to 5 banking days to examine (art. 14(b)).",
        "rules": "UCP 600 (ICC). Issued credits are irrevocable (art. 7, 2(b)).",
        "pitfalls": [
            "Soft clauses (e.g. inspection certificate signed by the applicant, shipping details 'to be advised by applicant') let the buyer block payment.",
            "Any discrepancy lets the bank refuse; strict compliance applies. Fees of USD 100-300 per discrepancy are common.",
            "Unconfirmed L/C from a weak issuing bank or high country risk: ask for confirmation.",
        ],
        "best_for": "Large first orders, new buyers in higher-risk countries, when the buyer can open a clean L/C.",
    },
    "LC_USANCE": {
        "name": "L/C usance (远期信用证, e.g. 60/90 days)",
        "bank_guarantee": True,
        "seller_risk": 3, "buyer_risk": 2,
        "who_carries_risk": "Bank undertakes to pay at maturity once documents comply; you wait for the money.",
        "how_it_works": "Same as sight L/C, but payment is due N days after B/L date or acceptance. You may discount the accepted draft at your bank (interest charged).",
        "rules": "UCP 600 arts. 7, 8; discounting is a separate bank facility.",
        "pitfalls": [
            "Check who bears discount interest: 'usance payable at sight' (buyer's usance) vs seller's usance.",
            "Maturity counted from B/L date vs acceptance date changes the cash date.",
        ],
        "best_for": "Buyers who need credit terms but you still want a bank undertaking.",
    },
    "DP": {
        "name": "D/P documents against payment (付款交单)",
        "bank_guarantee": False,
        "seller_risk": 4, "buyer_risk": 2,
        "who_carries_risk": "Seller carries the risk: goods are already shipped, and banks only hand over documents; they do not guarantee payment.",
        "how_it_works": "Seller ships and sends documents via banks; buyer receives them only after paying. If the buyer does not pay, goods sit at the port accruing demurrage.",
        "rules": "URC 522 (ICC): banks act as channels, no obligation to pay.",
        "pitfalls": [
            "Buyer may simply not collect; you must then resell or ship back. Fees and demurrage are yours.",
            "Do not name the buyer as consignee on an air waybill (cargo can be released without documents).",
        ],
        "best_for": "Long-standing buyers in stable markets; avoid for new buyers.",
    },
    "DA": {
        "name": "D/A documents against acceptance (承兑交单)",
        "bank_guarantee": False,
        "seller_risk": 5, "buyer_risk": 1,
        "who_carries_risk": "Seller carries nearly all the risk: buyer gets the documents by accepting a draft, then pays at maturity.",
        "how_it_works": "Documents are released against the buyer's signed acceptance of a time draft (e.g. 60 days). Payment is a promise by the buyer only, not a bank.",
        "rules": "URC 522 (ICC).",
        "pitfalls": [
            "It is open-account credit with extra paperwork: banks do not guarantee the draft.",
            "Often used by fraudulent buyers who take the goods and disappear. Avoid for new buyers.",
        ],
        "best_for": "Almost never for new buyers; only with credit insurance or a bank aval.",
    },
    "OA": {
        "name": "O/A open account (赊销 / 月结, e.g. net 30/60/90)",
        "bank_guarantee": False,
        "seller_risk": 5, "buyer_risk": 1,
        "who_carries_risk": "Seller carries all the risk: ships and invoices, then waits.",
        "how_it_works": "Goods and documents go straight to the buyer; the buyer pays by wire on the invoice due date.",
        "rules": "No ICC rule. Credit insurance (e.g. Sinosure 中信保) or factoring is the usual cover.",
        "pitfalls": [
            "Uninsured O/A to a new buyer is the single most common route to a total loss.",
            "Insurers usually require approved buyer limits before shipment and claims within a time limit after overdue.",
        ],
        "best_for": "Established buyers with insured credit limits.",
    },
}
ALIASES = {
    "TT": "TT_DEPOSIT", "T/T": "TT_DEPOSIT", "ADVANCE": "TT_ADVANCE", "PREPAY": "TT_ADVANCE",
    "LC": "LC_SIGHT", "L/C": "LC_SIGHT", "D/P": "DP", "D/A": "DA", "O/A": "OA", "OPEN_ACCOUNT": "OA",
    "USANCE": "LC_USANCE",
}


def resolve_term(code: str) -> str:
    key = code.strip().upper().replace(" ", "_").replace("-", "_")
    key = ALIASES.get(key, key)
    if key not in TERMS:
        raise PaymentTermsInputError(
            f"Unknown payment term '{code}'. Valid: {', '.join(TERMS)}. Aliases: T/T, L/C, D/P, D/A, O/A."
        )
    return key


# ---------------------------------------------------------------------------
# Cash-flow comparison
# ---------------------------------------------------------------------------
@dataclass
class Scenario:
    key: str
    label: str
    receipts: list[tuple[float, float]]  # (day, share of order value)
    unsecured_at_shipment_share: float   # share of order value unpaid and not bank-backed when goods leave
    fees_pct: float                      # bank/insurance fees as % of order value
    note: str


def _scenarios(p: int, s: int, usance_days: int, credit_days: int, deposit_pct: float,
               lc_fee_pct: float, lc_presentation_days: int, collection_fee_pct: float,
               credit_insurance_pct: float, after_bl_days: int) -> list[Scenario]:
    dep = deposit_pct / 100
    ship = float(p)
    arrive = float(p + s)
    lc_receipt = ship + lc_presentation_days + 5  # presentation + max 5 banking days (UCP 600 14(b)), approx. 5 days
    out = [
        Scenario("TT_ADVANCE", "T/T 100% advance", [(0.0, 1.0)], 0.0, 0.0, "Paid before production."),
        Scenario("TT_DEPOSIT", f"T/T {deposit_pct:g}% deposit + balance before release", [(0.0, dep), (ship, 1 - dep)], 0.0,
                 0.0, "Balance cleared before original B/L is released."),
        Scenario("TT_AFTER_BL", f"T/T {deposit_pct:g}% deposit + balance {after_bl_days} days after B/L", [(0.0, dep), (ship + after_bl_days, 1 - dep)],
                 1 - dep, 0.0, "Goods are with the buyer before balance is paid."),
        Scenario("LC_SIGHT", "L/C at sight", [(lc_receipt, 1.0)], 0.0, lc_fee_pct,
                 "Bank-backed if documents comply; fees are an assumption you can override."),
        Scenario("LC_USANCE", f"L/C usance {usance_days} days", [(lc_receipt + usance_days, 1.0)], 0.0, lc_fee_pct,
                 "Bank-backed if documents comply; you wait until maturity (or discount)."),
        Scenario("DP", "D/P at sight", [(arrive + 7, 1.0)], 1.0, collection_fee_pct,
                 "Paid when buyer collects documents (assumed 7 days after arrival)."),
        Scenario("DA", f"D/A {credit_days} days", [(ship + credit_days, 1.0)], 1.0, collection_fee_pct,
                 "Buyer promise only, no bank guarantee."),
        Scenario("OA", f"O/A net {credit_days}", [(ship + credit_days, 1.0)], 1.0, credit_insurance_pct,
                 "Cost shown is credit insurance premium if you set one."),
    ]
    return out


def _funding_cost(cost: float, receipts: list[tuple[float, float]], order_value: float, annual_rate: float) -> tuple[float, float]:
    """Interest on the seller's un-recovered cost, integrated over time.

    Cost is assumed spent at day 0 (conservative). balance(t) = max(0, cost - cumulative receipts(t)).
    Returns (interest, days until the cost is fully recovered).
    """
    pts = sorted(receipts)
    cum = 0.0
    prev_day = 0.0
    balance = cost
    area = 0.0
    recovered_day = 0.0 if cost <= 0 else float("inf")
    for day, share in pts:
        area += balance * (day - prev_day)
        prev_day = day
        cum += share * order_value
        balance = max(0.0, cost - cum)
        if balance == 0.0 and recovered_day == float("inf"):
            recovered_day = day
    interest = area * annual_rate / 365.0
    if recovered_day == float("inf"):
        recovered_day = prev_day
    return interest, recovered_day


def compare_terms(order_value: float, cost_pct: float, production_days: int, shipping_days: int,
                  annual_cost_of_capital_pct: float, deposit_pct: float = 30.0, usance_days: int = 60,
                  credit_days: int = 60, after_bl_days: int = 7, lc_fee_pct: float = 1.0,
                  lc_presentation_days: int = 7, collection_fee_pct: float = 0.3,
                  credit_insurance_pct: float = 0.0, terms: list[str] | None = None) -> dict:
    if order_value <= 0:
        raise PaymentTermsInputError("order_value must be greater than 0.")
    scen = _scenarios(production_days, shipping_days, usance_days, credit_days, deposit_pct, lc_fee_pct,
                      lc_presentation_days, collection_fee_pct, credit_insurance_pct, after_bl_days)
    if terms:
        wanted = {resolve_term(t) for t in terms}
        scen = [x for x in scen if x.key in wanted]
    cost = order_value * cost_pct / 100
    rate = annual_cost_of_capital_pct / 100
    rows = []
    for x in scen:
        interest, rec_day = _funding_cost(cost, x.receipts, order_value, rate)
        fees = order_value * x.fees_pct / 100
        full_day = max(d for d, _ in x.receipts)
        net = order_value - cost - interest - fees
        rows.append({
            "term": x.key, "label": x.label,
            "last_cash_day": round(full_day, 1),
            "cost_recovered_day": round(rec_day, 1),
            "financing_cost": round(interest, 2),
            "fees": round(fees, 2),
            "net_profit": round(net, 2),
            "net_margin_pct": round(net / order_value * 100, 2),
            "unsecured_at_shipment": round(x.unsecured_at_shipment_share * order_value, 2),
            "unsecured_pct_of_order": round(x.unsecured_at_shipment_share * 100, 1),
            "seller_risk_score": TERMS[x.key]["seller_risk"],
            "note": x.note,
        })
    warnings = [
        "Cost is assumed spent at day 0 (order date) and funded by you; real spending is staged, so interest is a conservative upper estimate.",
        f"Fee assumptions are yours to override: L/C {lc_fee_pct:g}% of value, collection {collection_fee_pct:g}%, credit insurance {credit_insurance_pct:g}%. Ask your bank/insurer for real quotes.",
        "Financing cost and fees are NOT a risk measure: a lower 'unsecured_at_shipment' matters more than a small interest saving.",
    ]
    if credit_insurance_pct == 0:
        warnings.append("O/A and D/A rows show no credit insurance premium. Get a quote (e.g. Sinosure) before offering credit terms.")
    if lc_presentation_days > 21:
        warnings.append("UCP 600 art. 14(c): original transport documents must be presented within 21 calendar days after shipment; plan for less.")
    best = min(rows, key=lambda r: (r["seller_risk_score"], r["financing_cost"] + r["fees"]), default=None)
    return {"order_value": round(order_value, 2), "your_cost": round(cost, 2), "rows": rows,
            "lowest_risk_term": best["term"] if best else None, "warnings": warnings}


# ---------------------------------------------------------------------------
# Recommendation (decision table)
# ---------------------------------------------------------------------------
def recommend(order_value_usd: float, buyer_history: str, country_risk: str, made_to_order: bool,
              has_credit_insurance: bool, buyer_requests: str | None) -> dict:
    if order_value_usd <= 0:
        raise PaymentTermsInputError("order_value_usd must be greater than 0.")
    warnings: list[str] = []
    ranked: list[tuple[str, str]] = []
    new = buyer_history == "new"
    high = country_risk == "high"
    if buyer_history == "paid_history" and has_credit_insurance and not high:
        ranked = [("OA", "Insured open account fits a buyer with a clean history; stay within the approved limit."),
                  ("TT_AFTER_BL", "Fallback without insurance cover: deposit plus balance after B/L."),
                  ("LC_USANCE", "If the buyer needs credit but a limit is not approved.")]
    elif buyer_history == "paid_history":
        ranked = [("TT_AFTER_BL", "A clean payment history justifies a deposit with the balance after shipment, in a small limit."),
                  ("TT_DEPOSIT", "Safer: balance before release of originals."),
                  ("LC_SIGHT", "Use when the order value is far above past orders.")]
    elif new and (order_value_usd >= 20000 or high):
        ranked = [("LC_SIGHT", "New buyer plus large value or higher country risk: bank undertaking is worth its fees (ask for confirmation if the issuing bank is weak)."),
                  ("TT_DEPOSIT", "Larger deposit (50%) with balance before release if the buyer refuses an L/C."),
                  ("TT_ADVANCE", "Fully prepaid for the first order if you have the leverage.")]
    elif new:
        ranked = [("TT_DEPOSIT", "Standard for a small first order: deposit at order, balance before the original B/L is released."),
                  ("TT_ADVANCE", "Full advance for samples and very small orders."),
                  ("LC_SIGHT", "Offer if the buyer wants more protection than a deposit.")]
    else:  # repeat, some history
        ranked = [("TT_DEPOSIT", "Repeat buyer without a long record: keep the balance before release."),
                  ("TT_AFTER_BL", "Allow only for amounts you can afford to lose."),
                  ("LC_SIGHT", "For orders much larger than before.")]
    if made_to_order:
        warnings.append("Made-to-order goods can rarely be resold: raise the deposit so it covers materials and custom parts (50% or more for new buyers).")
    if high and buyer_history != "paid_history":
        warnings.append("High country risk: check currency-transfer restrictions and whether an unconfirmed L/C from a local bank is enough.")
    if buyer_history in ("new", "some_history") and not has_credit_insurance:
        warnings.append("Never ship unsecured O/A, D/A or D/P to this buyer without credit insurance or a bank guarantee.")
    ask = None
    if buyer_requests:
        k = resolve_term(buyer_requests)
        s = TERMS[k]["seller_risk"]
        if k in ("OA", "DA", "DP", "TT_AFTER_BL") and (new or not has_credit_insurance):
            ask = (f"The buyer asks for {TERMS[k]['name']} (seller risk {s}/5). Counter with {ranked[0][0]} and offer a small discount "
                   "(for example 1-2%) rather than accepting unsecured terms.")
        elif k == "LC_USANCE" and new:
            ask = "Usance L/C is acceptable if it is irrevocable, confirmed or from a strong bank, and free of soft clauses; price the waiting time."
        else:
            ask = f"The buyer's request ({TERMS[k]['name']}) is within a reasonable risk range for this profile."
    warnings.append("Rule-of-thumb guidance, not credit advice. Verify the buyer (registration, trade references, payment history) first.")
    return {"recommendations": [{"rank": i + 1, "term": t, "name": TERMS[t]["name"], "reason": r} for i, (t, r) in enumerate(ranked)],
            "response_to_buyer_request": ask, "warnings": warnings}


# ---------------------------------------------------------------------------
# Clause linter
# ---------------------------------------------------------------------------
@dataclass
class Rule:
    id: str
    severity: str  # critical | high | medium | low
    pattern: str
    issue: str
    fix: str


RULES: list[Rule] = [
    Rule("SOFT_APPLICANT_CERT", "critical",
         r"(inspection|quality|approval|acceptance)\s+(certificate|report)[^.;\n]{0,60}(signed|issued|approved)\s+by\s+(the\s+)?(applicant|buyer)|"
         r"(acceptable|approved|satisfactory)\s+(to|by)\s+(the\s+)?(applicant|buyer)|买方(签署|确认|验收)的?(检验|验货|质检|验收)证书|申请人(签署|确认)",
         "Soft clause: payment depends on a document only the buyer controls.",
         "Delete it, or replace with a neutral inspector (SGS/BV/CIQ) certificate issued at your port."),
    Rule("SOFT_TO_BE_ADVISED", "critical",
         r"(vessel|ship|shipping|forwarder|carrier|port)[^.;\n]{0,40}(to be (advised|nominated|designated)|nominated by|designated by)[^.;\n]{0,30}(applicant|buyer)|"
         r"(to be (advised|nominated))\s+(later|by\s+(the\s+)?(applicant|buyer))|船名.{0,10}(待买方|买方指定|另行通知)",
         "Soft clause: shipping details are fixed later by the buyer, so you cannot know if you comply.",
         "Agree vessel, forwarder and ports before the L/C is issued; ask for an amendment."),
    Rule("SOFT_EFFECTIVE_LATER", "critical",
         r"(becomes?|shall become|will become)\s+(effective|valid|operative)\s+(only\s+)?(after|upon|when)|"
         r"(credit|l/?c)\s+(is\s+)?(not\s+)?(effective|valid)\s+until|信用证.{0,6}(生效|待.*通知)",
         "Soft clause: the credit is not effective until a buyer-controlled event happens.",
         "Do not start production until the credit is operative without conditions."),
    Rule("DA_TERMS", "high", r"\bd\s*/\s*a\b|documents?\s+against\s+acceptance|承兑交单",
         "D/A gives away the documents for a promise; banks do not guarantee payment (URC 522).",
         "Replace with D/P, L/C, or insured O/A; for a new buyer do not accept."),
    Rule("OPEN_ACCOUNT", "high", r"\bo\s*/\s*a\b|open\s+account|\bnet\s*(30|45|60|90|120)\b|赊销|月结|账期",
         "Open account is unsecured credit.",
         "Only for established buyers with credit insurance or an approved limit; state the due-date start (invoice or B/L date)."),
    Rule("PAY_AFTER_RECEIPT", "high",
         r"(after|upon|on)\s+(the\s+)?(receipt|arrival|delivery)\s+(of\s+(the\s+)?(goods|cargo|shipment)|at\s+destination)|payment\s+on\s+delivery|"
         r"货到(后)?付款|收货后.{0,6}付|到港后.{0,6}付",
         "Payment is triggered by arrival or receipt, which the buyer controls.",
         "Tie the due date to the B/L date or invoice date, not to receipt."),
    Rule("THIRD_PARTY_PAYER", "high",
         r"third[\s-]party\s+(payment|payer|account)|(personal|private)\s+account|paid\s+(by|from)\s+(a\s+)?(third|another)|第三方(付款|账户)|私人账户|个人账户",
         "Payment from a third party or to a personal account breaks sanctions/AML checks and complicates claims.",
         "Require payment from the buyer's own corporate account to your company account."),
    Rule("COPY_BL_BALANCE", "medium",
         r"against\s+(a\s+)?(copy\s+of\s+(the\s+)?|photocopy\s+of\s+(the\s+)?|scan(ned)?\s+(of\s+)?(the\s+)?)(b\s*/?\s*l|bill\s+of\s+lading)|"
         r"(b\s*/?\s*l|bill\s+of\s+lading)\s+(copy|photocopy)|(见|凭)提单(复印件|副本|扫描件)",
         "Balance against a B/L copy is safe only if you hold the originals until the money is credited.",
         "State: 'originals (or telex release) released only after full balance is credited to the seller's account'."),
    Rule("LC_UNCONFIRMED_USANCE", "medium",
         r"(usance|deferred|acceptance)\s+(l/?c|letter\s+of\s+credit|credit)|远期(信用证|L/?C)|\d+\s*days?\s+(after|from)\s+(b/?l|bill\s+of\s+lading|sight)",
         "Usance credit: you wait for the maturity date and depend on the issuing bank.",
         "Check who pays discount interest, and ask for confirmation if the issuing bank or country is weak."),
    Rule("VAGUE_TT", "medium", r"^(?!.*\d\s*%)(?!.*\d+\s*(percent|%)).*\b(t\s*/\s*t|wire\s+transfer|电汇)\b.*$",
         "T/T clause with no percentage, so the amount due and when are open to dispute.",
         "Write exact percentages and trigger dates, e.g. '30% within 3 days of PO, 70% before shipment'."),
    Rule("NO_BANK_CHARGES", "low", r"^(?!.*(bank\s+charges|banking\s+charges|bank\s+fees|\bour\b|\bsha\b|\bben\b|银行费用|手续费)).*\b(t\s*/\s*t|l\s*/\s*c)\b.*$",
         "Bank charges are not allocated: an under-payment from intermediary fees is common.",
         "State who pays bank charges (e.g. 'all bank charges outside the seller's country for the buyer's account')."),
]

CURRENCY_RE = re.compile(r"\b(usd|eur|cny|rmb|gbp|jpy|aud|cad|hkd)\b|us\$|€|£|美元|美金|欧元|人民币|英镑", re.I)
LATE_RE = re.compile(r"late\s+(payment\s+)?(interest|fee|charge)|overdue\s+interest|penalt|滞纳|逾期.{0,15}(利息|违约)", re.I)
LC_RE = re.compile(r"\bl\s*/\s*c\b|letter\s+of\s+credit|信用证", re.I)
CONFIRM_RE = re.compile(r"confirm|保兑", re.I)
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def check_clause(text: str) -> dict:
    t = text.strip()
    if len(t) < 8:
        raise PaymentTermsInputError("Clause text is too short to analyse (min 8 characters).")
    findings = []
    for r in RULES:
        flags = re.I | re.M | re.S if r.id in ("VAGUE_TT", "NO_BANK_CHARGES") else re.I
        m = re.search(r.pattern, t.replace("\n", " ") if r.id in ("VAGUE_TT", "NO_BANK_CHARGES") else t, flags)
        if m:
            snippet = m.group(0).strip() if r.id not in ("VAGUE_TT", "NO_BANK_CHARGES") else t[:80]
            findings.append({"rule": r.id, "severity": r.severity, "matched_text": snippet[:120],
                             "issue": r.issue, "suggested_fix": r.fix})
    if not CURRENCY_RE.search(t):
        findings.append({"rule": "NO_CURRENCY", "severity": "medium", "matched_text": "",
                         "issue": "No currency stated, so the amount due is ambiguous.",
                         "suggested_fix": "State the invoice currency (e.g. USD) and who bears exchange risk."})
    if not LATE_RE.search(t):
        findings.append({"rule": "NO_LATE_INTEREST", "severity": "low", "matched_text": "",
                         "issue": "No late-payment interest or penalty.",
                         "suggested_fix": "Add e.g. '0.05% per day on overdue amounts' (check local law limits)."})
    if LC_RE.search(t) and not CONFIRM_RE.search(t):
        findings.append({"rule": "LC_NOT_CONFIRMED", "severity": "low", "matched_text": "",
                         "issue": "L/C mentioned but no confirmation requirement.",
                         "suggested_fix": "For new buyers or higher-risk issuing banks, require a confirmed L/C (Silent/added confirmation)."})
    findings.sort(key=lambda f: SEV_ORDER[f["severity"]])
    worst = findings[0]["severity"] if findings else "none"
    verdict = {"critical": "DO_NOT_ACCEPT", "high": "RENEGOTIATE", "medium": "TIGHTEN", "low": "MINOR_EDITS", "none": "LOOKS_OK"}[worst]
    return {"verdict": verdict, "findings": findings,
            "warnings": ["Keyword-based screening of the text you pasted, not legal advice. Have your bank review L/C text before accepting.",
                         "A clause that is not flagged is not proven safe."]}
