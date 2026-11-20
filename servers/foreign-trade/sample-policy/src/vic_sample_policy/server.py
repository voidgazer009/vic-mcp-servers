"""Vic Sample Policy MCP server: decide who gets a free sample, what to charge, and how to credit it on the first order.

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
from .logic import TIER_NAMES, SamplePolicyInputError, credit, draft_terms, quote_package, roi, triage

mcp = MCPServer(
    name="vic-sample-policy",
    title="Vic Sample Policy",
    description="Export sample policy: triage sample requests, price sample packages, credit fees on the first order, check ROI.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers",
    instructions=(
        "Use these tools when an exporter gets a sample request: decide the tier (free + collect, prepaid freight credited, "
        "refundable fee, fully paid, or no sample), price the package, check whether sending is worth it, compute the "
        "first-order credit and draft the clause. Always: 1) ask for the sample cost, freight and whatever the buyer "
        "said instead of guessing; 2) show every warning; 3) keep clauses as drafts for the user, never send them; "
        "4) tell the user the triage is a heuristic and the buyer must still be verified. All amounts share one currency."
    ),
)

LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
Tier = Literal["FREE_COLLECT", "FREE_FREIGHT_CREDIT", "FEE_CREDIT", "FULL_PAID", "NO_SAMPLE"]


class SampleItem(BaseModel):
    name: str = Field(min_length=1, max_length=80, description="Sample name or model number.")
    qty: int = Field(ge=1, le=1000, description="Number of pieces sent.")
    unit_cost: float = Field(ge=0, le=1_000_000, description="Your cost per piece in the package currency (not the selling price).")
    prep_fee: float = Field(default=0.0, ge=0, le=1_000_000, description="One-off cost for this line: mould, printing plate, logo set-up. 0 if none.")


class TierRow(BaseModel):
    tier: str = Field(description="Tier code.")
    name: str = Field(description="Tier in Chinese and English.")
    buyer_pays_you_now: float = Field(description="What the buyer pays you before dispatch.")
    your_cash_outlay: float = Field(description="What you spend: sample cost, handling and freight you prepay.")
    your_net_if_no_order: float = Field(description="Buyer payment minus your outlay if he never orders; negative means a loss.")
    credit_on_first_order: float = Field(description="Amount you would deduct from the first order payment.")
    note: str = Field(description="What the numbers assume.")


class PackageQuote(BaseModel):
    product_cost: float
    prep_total: float
    handling_fee: float
    freight: float
    sample_charge: float = Field(description="Sample fee you would charge in the paid tiers, freight excluded.")
    rows: list[TierRow]
    warnings: list[str] = Field(description="Show these to the user.")


class RoiResult(BaseModel):
    profit_if_order: float = Field(description="Total profit on sample plus first order if the buyer orders.")
    profit_if_no_order: float = Field(description="Profit or loss on the sample alone.")
    expected_profit: float = Field(description="Probability-weighted profit at the given conversion rate.")
    break_even_conversion_pct: float | None = Field(description="Conversion rate at which expected profit is zero; null if the sample never loses money or the order never pays back.")
    warnings: list[str] = Field(description="Show these to the user.")


class CreditResult(BaseModel):
    eligible_amount: float = Field(description="Paid amounts that fall in the agreed credit scope.")
    credit: float = Field(description="Credit to deduct from the first order.")
    days_since_sample: int
    order_value: float
    payable_after_credit: float
    reasons: list[str] = Field(description="Why the credit is reduced or zero.")
    warnings: list[str] = Field(description="Show these to the user.")


class TriageResult(BaseModel):
    score: int = Field(description="0 to 100, higher means a more serious buyer.")
    tier: str = Field(description="Recommended tier code.")
    tier_name: str
    reasons: list[str]
    red_flags: list[str]
    before_you_ship: list[str]
    warnings: list[str] = Field(description="Show these to the user.")


class TermsDraft(BaseModel):
    tier: str
    english: str = Field(description="Clause to paste into the PI or e-mail, English.")
    chinese: str = Field(description="Same clause in Chinese for internal review.")
    warnings: list[str] = Field(description="Show these to the user.")


@mcp.tool(title="Price a sample package under each policy tier", annotations=LOCAL)
def quote_sample_package(
    items: Annotated[list[SampleItem], Field(min_length=1, max_length=30, description="Sample lines with piece cost and any one-off set-up cost.")],
    freight: Annotated[float, Field(ge=0, le=100_000, description="Estimated courier freight to the buyer in the same currency. Get a courier quote; do not guess.")],
    handling_fee: Annotated[float, Field(ge=0, le=100_000, description="Packing and staff-time fee added to the sample fee. 0 if none.")] = 0.0,
    markup_pct: Annotated[float, Field(ge=0, le=500, description="Markup on the piece cost in the paid tiers, in %. 0 means cost price.")] = 0.0,
) -> PackageQuote:
    """Price one sample package under four policies (free+collect, free+prepaid freight credited, refundable fee, fully paid): what the buyer pays, what you spend, your loss if he never orders, and the credit due later.

    Use it before answering 'can you send me a sample?' with a concrete offer.
    """
    try:
        res = quote_package([i.model_dump() for i in items], freight, handling_fee, markup_pct)
    except SamplePolicyInputError as e:
        raise ToolError(str(e)) from e
    return PackageQuote(**res)


@mcp.tool(title="Is this sample worth sending? Expected value and break-even", annotations=LOCAL)
def sample_roi(
    your_cash_outlay: Annotated[float, Field(ge=0, le=10_000_000, description="Total you spend on the sample: cost, handling and freight you prepay.")],
    buyer_pays_you_now: Annotated[float, Field(ge=0, le=10_000_000, description="What the buyer pays you before dispatch (0 for free samples).")],
    credit_on_first_order: Annotated[float, Field(ge=0, le=10_000_000, description="Amount you promise to deduct from the first order.")],
    expected_order_value: Annotated[float, Field(gt=0, le=1_000_000_000, description="Realistic first-order value if the buyer converts.")],
    gross_margin_pct: Annotated[float, Field(gt=0, le=100, description="Your gross margin on that order, in %.")],
    conversion_pct: Annotated[float, Field(ge=0, le=100, description="Share of such buyers who order after a sample, in %. Use your CRM history.")],
) -> RoiResult:
    """Compute profit if the buyer orders, the loss if he does not, expected profit at your conversion rate and the break-even conversion rate for a sample policy.

    Use it to decide how many free samples your budget can afford.
    """
    try:
        res = roi(your_cash_outlay, buyer_pays_you_now, credit_on_first_order, expected_order_value, gross_margin_pct, conversion_pct)
    except SamplePolicyInputError as e:
        raise ToolError(str(e)) from e
    return RoiResult(**res)


@mcp.tool(title="Compute the first-order credit for a paid sample", annotations=LOCAL)
def first_order_credit(
    sample_fee_paid: Annotated[float, Field(ge=0, le=10_000_000, description="Sample fee the buyer paid, freight excluded.")],
    prep_fee_paid: Annotated[float, Field(ge=0, le=10_000_000, description="Set-up fee paid (mould, printing plate, logo). 0 if none.")],
    freight_paid: Annotated[float, Field(ge=0, le=10_000_000, description="Freight the buyer paid or you prepaid. 0 if none.")],
    creditable: Annotated[list[Literal["sample_fee", "prep_fee", "freight"]], Field(min_length=1, max_length=3, description="Which paid items your written offer says can be credited.")],
    order_value: Annotated[float, Field(gt=0, le=1_000_000_000, description="Value of the order the buyer wants to use the credit on.")],
    sample_date: Annotated[str, Field(min_length=10, max_length=10, description="Date the sample was dispatched or paid, YYYY-MM-DD.")],
    order_date: Annotated[str, Field(min_length=10, max_length=10, description="Date of the order, YYYY-MM-DD.")],
    min_order_value: Annotated[float, Field(ge=0, le=1_000_000_000, description="Minimum order value that qualifies; 0 if none was agreed.")] = 0.0,
    valid_days: Annotated[int, Field(ge=1, le=3650, description="Days after the sample during which the credit stays valid.")] = 180,
    cap_pct_of_order: Annotated[float, Field(gt=0, le=100, description="Maximum credit as % of the order value; 100 means no cap.")] = 100.0,
) -> CreditResult:
    """Apply the agreed credit rules (scope, minimum order, validity days, cap) to a first order and return the credit, the amount payable and the reason when the credit is cut.

    Use it when a buyer says 'deduct my sample fee from this order'.
    """
    try:
        res = credit(sample_fee_paid, prep_fee_paid, freight_paid, list(creditable), cap_pct_of_order, min_order_value,
                     valid_days, sample_date, order_date, order_value)
    except SamplePolicyInputError as e:
        raise ToolError(str(e)) from e
    return CreditResult(**res)


@mcp.tool(title="Triage a sample request and pick the tier", annotations=LOCAL)
def triage_sample_request(
    email_type: Annotated[Literal["corporate", "free", "lookalike"], Field(description="corporate = own company domain; free = Gmail/Yahoo etc.; lookalike = domain imitating a known company.")],
    specs_given: Annotated[bool, Field(description="True if the buyer named model, use or specification.")],
    target_qty_given: Annotated[bool, Field(description="True if the buyer stated an expected order quantity or target price.")],
    company_status: Annotated[Literal["verified", "failed", "unchecked"], Field(description="verified = website, registry and map all match; failed = checked and something does not match; unchecked = not checked yet.")] = "unchecked",
    asks_testing_details: Annotated[bool, Field(description="True if he asked about test standards, certificates or reports.")] = False,
    refuses_any_cost: Annotated[bool, Field(description="True if he refuses to pay even freight.")] = False,
    many_models_no_project: Annotated[bool, Field(description="True if he wants one of every model with no stated project.")] = False,
    residential_address: Annotated[bool, Field(description="True if the address is residential or does not match the company.")] = False,
    unanswered_samples: Annotated[int, Field(ge=0, le=50, description="Earlier samples sent to this buyer or address with no feedback.")] = 0,
    pressure_to_ship: Annotated[bool, Field(description="True if he pushes you to ship before specs or price are agreed.")] = False,
    met_in_person: Annotated[bool, Field(description="True if you met at a fair or in a video call.")] = False,
    customized: Annotated[bool, Field(description="True if the sample needs a new colour, logo, mould or spec.")] = False,
    sample_value: Annotated[float, Field(ge=0, le=10_000_000, description="Cost value of the sample package, same currency as the threshold.")] = 0.0,
    high_value_threshold: Annotated[float, Field(ge=0, le=10_000_000, description="Sample value from which you never give it free.")] = 50.0,
    buyer_has_courier_account: Annotated[bool, Field(description="True if he supplied a courier account you could validate.")] = True,
) -> TriageResult:
    """Score a sample request from what the buyer said and did, then recommend one of five tiers (free+collect, free+credit, refundable fee, fully paid, no sample) with red flags and a pre-shipping checklist.

    Use it before agreeing to send anything; it is a heuristic and does not verify the company.
    """
    try:
        res = triage(email_type, {"verified": True, "failed": False, "unchecked": None}[company_status], specs_given, target_qty_given, asks_testing_details, refuses_any_cost,
                     many_models_no_project, residential_address, unanswered_samples, pressure_to_ship, met_in_person,
                     customized, sample_value, high_value_threshold, buyer_has_courier_account)
    except SamplePolicyInputError as e:
        raise ToolError(str(e)) from e
    return TriageResult(**res)


@mcp.tool(title="Draft the sample clause for a PI or e-mail", annotations=LOCAL)
def draft_sample_terms(
    tier: Annotated[Tier, Field(description="Tier code from triage_sample_request or quote_sample_package.")],
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern="^[A-Za-z]{3}$", description="ISO 4217 code, e.g. USD.")] = "USD",
    sample_fee: Annotated[float, Field(ge=0, le=10_000_000, description="Sample fee quoted to the buyer, freight excluded.")] = 0.0,
    freight: Annotated[float, Field(ge=0, le=100_000, description="Estimated courier freight.")] = 0.0,
    min_order_value: Annotated[float, Field(ge=0, le=1_000_000_000, description="Minimum first-order value for the credit.")] = 0.0,
    valid_days: Annotated[int, Field(ge=1, le=3650, description="Days after dispatch the credit stays valid.")] = 180,
    extra_condition: Annotated[str, Field(max_length=300, description="One extra sentence to append, e.g. 'Credit applies to the same model only'.")] = "",
) -> TermsDraft:
    """Draft an English clause with a Chinese copy for the chosen tier, stating who pays, what is credited, the minimum order and the validity. Draft only, never sends.

    Use it so the credit and freight terms are written down before the sample leaves.
    """
    try:
        res = draft_terms(tier, currency.upper(), sample_fee, freight, extra_condition, min_order_value, valid_days)
    except SamplePolicyInputError as e:
        raise ToolError(str(e)) from e
    return TermsDraft(**res)


@mcp.resource("sample-policy://tiers", name="sample-policy-tiers", title="Sample policy tiers", mime_type="application/json",
              description="The five sample tiers with their Chinese and English names.")
def tiers() -> str:
    return json.dumps(TIER_NAMES, ensure_ascii=False, indent=2)


@mcp.prompt(title="Reply to a sample request",
            description="Handle a buyer's 'please send a sample' e-mail with triage, a priced offer and a draft clause.")
def sample_request_reply(buyer_message: str, language: str = "English") -> str:
    return (
        "You are an export sales manager. The buyer wrote:\n\n"
        f"---\n{buyer_message}\n---\n\n"
        "Steps:\n1. Ask me for sample cost, freight estimate and anything about the buyer you lack.\n"
        "2. Call triage_sample_request, then quote_sample_package and sample_roi for the recommended tier.\n"
        f"3. Call draft_sample_terms and write a polite reply in {language} that asks for the missing specs, order quantity and courier account.\n"
        "4. Show every warning and red flag. Keep everything as a draft for my review. Do not send."
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
