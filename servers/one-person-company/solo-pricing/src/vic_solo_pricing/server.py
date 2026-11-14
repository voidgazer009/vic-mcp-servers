"""Vic Solo Pricing MCP server: pricing maths for one-person companies and freelancers.

Built on the official MCP Python SDK v2 (protocol revision 2026-07-28). Offline: no network, no API key.
"""

from __future__ import annotations

import json
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from . import logic
from .logic import PricingInputError

mcp = MCPServer(
    name="vic-solo-pricing",
    title="Vic Solo Pricing",
    description="Pricing maths for solo founders and freelancers: hourly rate, fixed-price quotes, fee gross-up, discount impact, real hourly rate.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers/tree/main/servers/one-person-company/solo-pricing",
    instructions=(
        "Use these tools when a freelancer or one-person company sets a rate, prices a fixed-fee project, passes on "
        "payment fees, considers a discount, or checks what a finished job really paid per hour. Ask for missing inputs "
        "(tax rate, expenses, realistic billable utilization) instead of inventing them; never assume a tax rate for the "
        "user's country. Always show the returned warnings. Results are a floor to quote above, not tax or legal advice."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
Pct = float


class HourlyRateResult(BaseModel):
    working_weeks: float = Field(description="52 minus weeks off.")
    billable_hours_per_year: float = Field(description="Hours a year you can actually invoice.")
    pre_tax_profit_needed: float = Field(description="Profit before tax that leaves the target net income.")
    revenue_needed_before_fees: float = Field(description="Profit + expenses + buffer.")
    revenue_to_invoice: float = Field(description="Annual invoicing needed after payment fees.")
    hourly_rate: float = Field(description="Minimum hourly rate (floor).")
    day_rate: float = Field(description="Minimum day rate from billable hours per working day.")
    naive_rate_ignoring_tax_and_utilization: float = Field(description="What (income + expenses) / all worked hours would give.")
    underpricing_if_naive_pct: float = Field(description="How far below the true floor the naive rate is, in %.")
    warnings: list[str] = Field(description="Show to the user.")


class Scenario(BaseModel):
    hours_worked: float
    overrun_pct: float = Field(description="Hours over plan, in %.")
    effective_hourly_rate: float = Field(description="Labour income per hour actually worked.")
    vs_target_rate_pct: float = Field(description="Effective rate versus the target rate, in %.")


class ProjectQuote(BaseModel):
    planned_hours: float = Field(description="Estimate + risk buffer + revision hours.")
    labour_cost: float
    pass_through_costs: float
    quote_price: float = Field(description="Price to quote, fees included.")
    fees_absorbed: float = Field(description="Payment fees included in the price.")
    scenarios: list[Scenario] = Field(description="What the job pays per hour if it overruns.")
    warnings: list[str]


class FeeResult(BaseModel):
    invoice_amount: float = Field(description="Amount to invoice so that net_wanted arrives.")
    total_fees: float
    effective_fee_pct: float = Field(description="Fees as % of the invoice.")
    naive_markup_amount: float = Field(description="What adding the fee % on top would give (too low).")
    naive_shortfall: float = Field(description="How much short the naive amount would leave you.")
    warnings: list[str]


class DiscountResult(BaseModel):
    old_unit_margin: float
    new_price: float
    new_unit_margin: float
    required_volume_increase_pct: float | None = Field(description="Extra volume needed to keep total profit; null if impossible.")
    required_units: float | None
    profit_now: float
    profit_at_current_volume_after_discount: float
    warnings: list[str]


class RealRateResult(BaseModel):
    fees: float
    net_earned: float
    real_hourly_rate: float = Field(description="Net earned per hour actually worked.")
    vs_target_pct: float | None = Field(description="Real rate versus target, in %; null without a target.")
    warnings: list[str]


def _guard(fn, *a):
    try:
        return fn(*a)
    except PricingInputError as e:
        raise ToolError(str(e)) from e


@mcp.tool(title="Calculate minimum hourly and day rate", annotations=READ_ONLY)
def calculate_hourly_rate(
    target_net_income: Annotated[float, Field(gt=0, le=100_000_000, description="Yearly take-home income you want after tax, in your currency.")],
    tax_rate_pct: Annotated[float, Field(ge=0, lt=90, description="Share of pre-tax profit going to income tax and social contributions, in %. Ask the user; do not guess.")],
    annual_expenses: Annotated[float, Field(ge=0, le=100_000_000, description="Yearly deductible business costs: software, equipment, insurance, accountant, workspace.")] = 0.0,
    weeks_off: Annotated[float, Field(ge=0, lt=52, description="Weeks a year with no work: holidays, sickness, public holidays.")] = 6.0,
    hours_per_week: Annotated[float, Field(gt=0, le=80, description="Hours you work in a normal working week, billable or not.")] = 40.0,
    utilization_pct: Annotated[float, Field(gt=0, le=100, description="Share of worked hours you can invoice, in %. Solo operators are typically 50 to 65.")] = 60.0,
    buffer_pct: Annotated[float, Field(ge=0, le=100, description="Extra profit or safety margin on top of required revenue, in %.")] = 10.0,
    payment_fee_pct: Annotated[float, Field(ge=0, lt=50, description="Average payment platform and currency conversion fees, in % of invoice.")] = 0.0,
    days_per_week: Annotated[float, Field(gt=0, le=7, description="Working days per week, used for the day rate.")] = 5.0,
) -> HourlyRateResult:
    """Work backwards from the income you want to the minimum hourly and day rate: grosses up for tax (a division, not an addition), adds expenses and a buffer, and divides by billable hours, not worked hours. Use it when someone asks what to charge or suspects they are underpriced."""
    return HourlyRateResult(**_guard(logic.hourly_rate, target_net_income, annual_expenses, tax_rate_pct, weeks_off, hours_per_week, utilization_pct, buffer_pct, payment_fee_pct, days_per_week))


@mcp.tool(title="Price a fixed-fee project", annotations=READ_ONLY)
def quote_fixed_project(
    estimated_hours: Annotated[float, Field(gt=0, le=10_000, description="Your honest hour estimate for the core work, before any buffer.")],
    hourly_rate: Annotated[float, Field(gt=0, le=100_000, description="Your target hourly rate, e.g. from calculate_hourly_rate.")],
    risk_buffer_pct: Annotated[float, Field(ge=0, le=200, description="Extra hours for unknowns, in % of the estimate. 20 to 30 is typical.")] = 25.0,
    revision_rounds: Annotated[int, Field(ge=0, le=20, description="Revision rounds included in the price.")] = 2,
    hours_per_revision: Annotated[float, Field(ge=0, le=200, description="Hours one revision round usually takes.")] = 2.0,
    pass_through_costs: Annotated[float, Field(ge=0, le=100_000_000, description="Costs you pay for this job: stock assets, licences, contractors, API usage.")] = 0.0,
    payment_fee_pct: Annotated[float, Field(ge=0, lt=50, description="Payment and currency fees, in % of the invoice.")] = 0.0,
) -> ProjectQuote:
    """Turn an hour estimate into a fixed-fee quote that includes a risk buffer, included revision rounds, pass-through costs and payment fees, and show what the job pays per hour if it overruns by 25%, 50% or 100%. Use before sending a proposal."""
    return ProjectQuote(**_guard(logic.fixed_project_price, estimated_hours, hourly_rate, risk_buffer_pct, revision_rounds, hours_per_revision, pass_through_costs, payment_fee_pct))


@mcp.tool(title="Gross up an invoice for payment fees", annotations=READ_ONLY)
def gross_up_for_fees(
    net_wanted: Annotated[float, Field(gt=0, le=100_000_000, description="Amount you want to receive after fees.")],
    fee_pct: Annotated[float, Field(ge=0, lt=50, description="Percentage fee from your payment provider, e.g. 2.9. Read it from your own dashboard.")],
    fixed_fee: Annotated[float, Field(ge=0, le=10_000, description="Fixed fee per payment in the same currency, e.g. 0.30.")] = 0.0,
    fx_spread_pct: Annotated[float, Field(ge=0, lt=50, description="Currency conversion margin in %, 0 if no conversion.")] = 0.0,
) -> FeeResult:
    """Find the invoice amount that leaves you exactly the net amount after a percentage fee, a fixed fee and a currency spread. Dividing by (1 - fee) is correct; adding the fee percentage on top leaves you short, and the result shows by how much."""
    return FeeResult(**_guard(logic.fee_gross_up, net_wanted, fee_pct, fixed_fee, fx_spread_pct))


@mcp.tool(title="Check what a discount really costs", annotations=READ_ONLY)
def analyze_discount(
    price: Annotated[float, Field(gt=0, le=100_000_000, description="Current price per unit, package or hour.")],
    unit_variable_cost: Annotated[float, Field(ge=0, le=100_000_000, description="Cost you pay for each extra sale, including your own time valued at your rate.")],
    discount_pct: Annotated[float, Field(gt=0, lt=100, description="Proposed discount, in %.")],
    current_units: Annotated[float, Field(gt=0, le=1_000_000_000, description="Units you sell in the period at the current price.")] = 100.0,
) -> DiscountResult:
    """Show how much extra volume a discount needs just to keep total profit unchanged. A 10% discount on a 60% margin needs 20% more sales. Use when a client asks for a cheaper price or before running a promotion."""
    return DiscountResult(**_guard(logic.discount_impact, price, unit_variable_cost, discount_pct, current_units))


@mcp.tool(title="Measure the real hourly rate of a finished job", annotations=READ_ONLY)
def check_real_hourly_rate(
    revenue: Annotated[float, Field(gt=0, le=100_000_000, description="Amount invoiced for the job.")],
    hours_worked: Annotated[float, Field(gt=0, le=100_000, description="Every hour spent on it: delivery, calls, emails, revisions, scoping.")],
    payment_fee_pct: Annotated[float, Field(ge=0, lt=100, description="Payment and currency fees, in % of revenue.")] = 0.0,
    direct_costs: Annotated[float, Field(ge=0, le=100_000_000, description="Costs paid for this job (assets, contractors, licences).")] = 0.0,
    target_hourly_rate: Annotated[float | None, Field(gt=0, le=100_000, description="Your target hourly rate to compare with.")] = None,
) -> RealRateResult:
    """Compute what a completed job actually paid per hour after fees and direct costs, and compare it with the target rate. Use for post-project reviews, to find which clients or scopes underpay."""
    return RealRateResult(**_guard(logic.real_hourly_rate, revenue, payment_fee_pct, direct_costs, hours_worked, target_hourly_rate))


@mcp.resource("pricing://formulas", name="pricing-formulas", title="Solo pricing formulas", mime_type="application/json",
              description="The formulas and conventions behind every tool in this server.")
def formulas() -> str:
    return json.dumps({
        "revenue": "net / (1 - tax) + expenses, then x (1 + buffer), then / (1 - payment_fee)",
        "billable_hours": "(52 - weeks_off) x hours_per_week x utilization",
        "fixed_price": "((hours x (1 + risk) + rounds x hours_per_round) x rate + costs) / (1 - fee)",
        "discount_volume": "old_margin / new_margin - 1",
        "real_rate": "(revenue - fees - costs) / hours_worked",
    }, indent=2)


@mcp.prompt(title="Price a new client project", description="Walk from a client brief to a defensible fixed-fee quote using the pricing tools.")
def price_a_project(brief: str, currency: str = "USD") -> str:
    return (
        f"You are a pricing advisor for a one-person company. Client brief:\n\n---\n{brief}\n---\n\n"
        "1. Ask for the user's target income, tax rate, expenses and realistic utilization if unknown.\n"
        "2. Call calculate_hourly_rate for the floor rate.\n"
        "3. Break the brief into tasks, estimate hours honestly, then call quote_fixed_project.\n"
        "4. If fees or currency conversion apply, call gross_up_for_fees.\n"
        f"5. Present the price in {currency} with scope, revision limit and payment schedule, and show every warning."
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
