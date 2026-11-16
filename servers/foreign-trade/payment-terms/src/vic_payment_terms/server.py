"""Vic Payment Terms MCP server: choose, compare and screen export payment terms (T/T, L/C, D/P, D/A, O/A).

Built on the official MCP Python SDK v2 (protocol revision 2026-07-28). Fully offline.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .logic import TERMS, PaymentTermsInputError, check_clause, compare_terms, recommend, resolve_term

mcp = MCPServer(
    name="vic-payment-terms",
    title="Vic Payment Terms",
    description="Pick, compare and screen export payment terms: T/T, L/C, D/P, D/A, O/A, with cash-flow cost and clause red flags.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers",
    instructions=(
        "Use these tools when an exporter negotiates payment terms, receives an L/C or a contract payment clause, or "
        "asks which term is safe for a buyer. Always: 1) ask for order value, buyer history and country risk instead of "
        "guessing; 2) show every warning returned; 3) say the output is rule-based guidance, not credit or legal advice, "
        "and that bank fees and insurance premiums must be confirmed with the bank or insurer. Never tell the user a "
        "clause is safe merely because nothing was flagged."
    ),
)

LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

TermCode = Literal["TT_ADVANCE", "TT_DEPOSIT", "TT_AFTER_BL", "LC_SIGHT", "LC_USANCE", "DP", "DA", "OA"]


class TermInfo(BaseModel):
    code: str = Field(description="Normalised term code.")
    name: str = Field(description="Full name in English and Chinese.")
    bank_guarantee: bool = Field(description="True if a bank undertakes to pay (documentary credit).")
    seller_risk: int = Field(description="Seller risk score 1 (low) to 5 (high).")
    buyer_risk: int = Field(description="Buyer risk score 1 (low) to 5 (high).")
    who_carries_risk: str = Field(description="Plain-language statement of who carries the main risk.")
    how_it_works: str = Field(description="Sequence of events.")
    rules: str = Field(description="Governing rules (ICC UCP 600 / URC 522) or none.")
    pitfalls: list[str] = Field(description="Common traps for the seller.")
    best_for: str = Field(description="When this term fits.")


class CompareRow(BaseModel):
    term: str = Field(description="Term code.")
    label: str = Field(description="Scenario label including the numbers used.")
    last_cash_day: float = Field(description="Day after order when the final payment arrives.")
    cost_recovered_day: float = Field(description="Day when cumulative receipts first cover your cost.")
    financing_cost: float = Field(description="Interest on your un-recovered cost, order currency.")
    fees: float = Field(description="Assumed bank or insurance fees, order currency.")
    net_profit: float = Field(description="Order value minus cost, interest and fees.")
    net_margin_pct: float = Field(description="Net profit divided by order value, %.")
    unsecured_at_shipment: float = Field(description="Amount unpaid and not bank-backed when the goods ship.")
    unsecured_pct_of_order: float = Field(description="Same, as % of order value.")
    seller_risk_score: int = Field(description="1 (low) to 5 (high).")
    note: str = Field(description="What the numbers assume.")


class CompareResult(BaseModel):
    order_value: float
    your_cost: float
    rows: list[CompareRow]
    lowest_risk_term: str | None = Field(description="Lowest seller-risk term among the rows, ties broken by cost.")
    warnings: list[str] = Field(description="Show these to the user.")


class Recommendation(BaseModel):
    rank: int
    term: str
    name: str
    reason: str


class RecommendResult(BaseModel):
    recommendations: list[Recommendation]
    response_to_buyer_request: str | None = Field(description="Advice on the term the buyer asked for, if given.")
    warnings: list[str] = Field(description="Show these to the user.")


class Finding(BaseModel):
    rule: str = Field(description="Rule id, e.g. SOFT_APPLICANT_CERT.")
    severity: Literal["critical", "high", "medium", "low"]
    matched_text: str = Field(description="The words that triggered the rule, empty for 'missing' rules.")
    issue: str
    suggested_fix: str


class ClauseResult(BaseModel):
    verdict: Literal["DO_NOT_ACCEPT", "RENEGOTIATE", "TIGHTEN", "MINOR_EDITS", "LOOKS_OK"]
    findings: list[Finding]
    warnings: list[str] = Field(description="Show these to the user.")


@mcp.tool(title="Explain a payment term", annotations=LOCAL)
def explain_payment_term(
    code: Annotated[str, Field(min_length=1, max_length=20, description="Term code: TT_ADVANCE, TT_DEPOSIT, TT_AFTER_BL, LC_SIGHT, LC_USANCE, DP, DA, OA. Aliases T/T, L/C, D/P, D/A, O/A are accepted.")],
) -> TermInfo:
    """Explain one export payment term: who carries the risk, how it works, which ICC rules apply, and the traps for the seller.

    Use it when a buyer proposes a term you are unsure about, or to brief a new sales colleague.
    """
    try:
        k = resolve_term(code)
    except PaymentTermsInputError as e:
        raise ToolError(str(e)) from e
    return TermInfo(code=k, **TERMS[k])


@mcp.tool(title="Compare payment terms by cash flow and risk", annotations=LOCAL)
def compare_payment_terms(
    order_value: Annotated[float, Field(gt=0, description="Total invoice value of the order in any one currency.")],
    cost_pct: Annotated[float, Field(gt=0, le=100, description="Your total cost as % of order value (goods plus origin costs), e.g. 70.")],
    production_days: Annotated[int, Field(ge=0, le=365, description="Days from order/deposit to shipment (B/L date).")],
    shipping_days: Annotated[int, Field(ge=0, le=120, description="Transit days from shipment to arrival at the destination port.")],
    annual_cost_of_capital_pct: Annotated[float, Field(ge=0, le=60, description="Your yearly borrowing cost or opportunity cost, in %. 8 means 8%.")],
    deposit_pct: Annotated[float, Field(ge=0, le=100, description="Deposit % for the T/T deposit scenarios.")] = 30.0,
    credit_days: Annotated[int, Field(ge=0, le=365, description="Credit days for D/A and O/A, counted from the B/L date.")] = 60,
    usance_days: Annotated[int, Field(ge=0, le=365, description="Usance days for the L/C usance scenario, counted from the B/L date.")] = 60,
    after_bl_days: Annotated[int, Field(ge=0, le=120, description="Days after B/L when the T/T balance is due in the 'after B/L' scenario.")] = 7,
    lc_fee_pct: Annotated[float, Field(ge=0, le=10, description="Total L/C fees borne by you (advising, negotiation, discrepancy allowance) as % of value. Assumption: ask your bank.")] = 1.0,
    lc_presentation_days: Annotated[int, Field(ge=0, le=60, description="Days after shipment to prepare and present L/C documents. UCP 600 art. 14(c) caps this at 21 days.")] = 7,
    collection_fee_pct: Annotated[float, Field(ge=0, le=5, description="Collection bank fees for D/P and D/A as % of value.")] = 0.3,
    credit_insurance_pct: Annotated[float, Field(ge=0, le=10, description="Credit insurance premium for O/A as % of value; 0 means no insurance.")] = 0.0,
    terms: Annotated[list[TermCode] | None, Field(max_length=8, description="Limit the comparison to these term codes; omit to compare all eight.")] = None,
) -> CompareResult:
    """Compare T/T advance, T/T deposit, L/C, D/P, D/A and O/A for one order: when cash arrives, interest on your un-recovered cost, fees, net margin and the amount left unsecured at shipment.

    Use it to answer 'what does 60-day credit really cost me?' or to justify a counter-offer to a buyer.
    """
    try:
        res = compare_terms(order_value, cost_pct, production_days, shipping_days, annual_cost_of_capital_pct,
                            deposit_pct, usance_days, credit_days, after_bl_days, lc_fee_pct, lc_presentation_days,
                            collection_fee_pct, credit_insurance_pct, list(terms) if terms else None)
    except PaymentTermsInputError as e:
        raise ToolError(str(e)) from e
    return CompareResult(**res)


@mcp.tool(title="Recommend a payment term", annotations=LOCAL)
def recommend_payment_terms(
    order_value_usd: Annotated[float, Field(gt=0, description="Order value in USD (or equivalent).")],
    buyer_history: Annotated[Literal["new", "some_history", "paid_history"], Field(description="new = never traded; some_history = 1-2 small orders paid; paid_history = several orders paid on time.")],
    country_risk: Annotated[Literal["low", "medium", "high"], Field(description="Your judgement of buyer country risk (payment delays, FX controls, bank strength). Do not guess: check your credit insurer's country rating.")],
    made_to_order: Annotated[bool, Field(description="True if the goods are customised and hard to resell.")] = False,
    has_credit_insurance: Annotated[bool, Field(description="True if this buyer is covered by approved credit insurance (e.g. Sinosure limit).")] = False,
    buyer_requests: Annotated[str | None, Field(max_length=20, description="Term the buyer asked for, e.g. OA, DA, LC_SIGHT, T/T. Omit if none.")] = None,
) -> RecommendResult:
    """Rank the safest payment terms to offer a given buyer, with reasons, and answer what to do about the term the buyer asked for.

    Rule-based decision table (buyer history, order size, country risk, insurance). Use it before replying to a buyer who wants credit terms.
    """
    try:
        res = recommend(order_value_usd, buyer_history, country_risk, made_to_order, has_credit_insurance, buyer_requests)
    except PaymentTermsInputError as e:
        raise ToolError(str(e)) from e
    return RecommendResult(**res)


@mcp.tool(title="Screen a payment clause or L/C text", annotations=LOCAL)
def check_payment_clause(
    text: Annotated[str, Field(min_length=8, max_length=20000, description="The payment clause from a contract/PI, or L/C field 46A/47A text, in English or Chinese.")],
) -> ClauseResult:
    """Screen payment clause or L/C text for soft clauses, buyer-controlled triggers, open-account exposure, vague T/T wording and missing items.

    Returns severity-ranked findings with a suggested fix for each and an overall verdict. Use it before accepting a contract or L/C.
    """
    try:
        res = check_clause(text)
    except PaymentTermsInputError as e:
        raise ToolError(str(e)) from e
    return ClauseResult(**res)


@mcp.resource("payment-terms://matrix", name="payment-terms-matrix", title="Payment terms matrix", mime_type="application/json",
              description="All eight payment terms with risk scores, ICC rules and pitfalls.")
def matrix() -> str:
    return json.dumps(TERMS, ensure_ascii=False, indent=2)


@mcp.prompt(title="Reply to a buyer asking for credit terms",
            description="Handle a buyer who asks for open account, D/A or long L/C terms with checked numbers.")
def credit_terms_reply(buyer_message: str, language: str = "English") -> str:
    return (
        "You are an export sales manager. The buyer wrote:\n\n"
        f"---\n{buyer_message}\n---\n\n"
        "Steps:\n1. Ask me for order value, buyer history, country risk and my cost of capital if missing.\n"
        "2. Call recommend_payment_terms, then compare_payment_terms for the requested term and the recommended one.\n"
        "3. If the buyer attached a clause or L/C text, call check_payment_clause and show every finding.\n"
        f"4. Draft a polite counter-offer in {language} that explains the alternative; offer a small discount instead of unsecured credit.\n"
        "5. Keep it as a draft for my review. Do not send."
    )


def main() -> None:
    """Entry point: stdio by default, `--http` for stateless Streamable HTTP on port 8000."""
    import sys

    if "--http" in sys.argv:
        mcp.run(transport="streamable-http", stateless_http=True)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
