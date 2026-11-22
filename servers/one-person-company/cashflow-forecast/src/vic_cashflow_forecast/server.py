"""Vic Cashflow Forecast MCP server: 13-week cash forecast, runway and late-payment stress test.

Built on the official MCP Python SDK v2 (protocol revision 2026-07-28). Offline: no network, no API key.
"""

from __future__ import annotations

import json
import datetime as dt
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from . import logic
from .logic import CashflowInputError

mcp = MCPServer(
    name="vic-cashflow-forecast",
    title="Vic Cashflow Forecast",
    description="Weekly cash-flow forecast for freelancers and one-person companies: 13-week balance, runway, late-payment stress test.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers/tree/main/servers/one-person-company/cashflow-forecast",
    instructions=(
        "Use these tools when a freelancer or one-person company asks whether cash will last, when money gets tight, or what happens "
        "if a client pays late. Ask for the opening bank balance, expected invoices with dates, and recurring costs (rent, tools, tax, "
        "own pay) instead of guessing; give each uncertain invoice a confidence below 1. Run forecast_cashflow first, then "
        "stress_test_cashflow. Always show warnings. Everything is computed locally; results are estimates, not financial advice."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ISO10 = {"minLength": 10, "maxLength": 10}  # ISO dates are exactly 10 characters


class CashItem(BaseModel):
    label: str = Field(min_length=1, max_length=80, description="What the money is, e.g. 'Acme invoice #12' or 'Office rent'.")
    amount: float = Field(gt=0, le=1_000_000_000, description="Positive amount per occurrence, in one currency.")
    direction: Literal["in", "out"] = Field(description="'in' for money received, 'out' for money paid.")
    date: dt.date = Field(json_schema_extra=ISO10, description="Expected date (first date if it repeats), ISO format YYYY-MM-DD.")
    repeat: Literal["none", "weekly", "biweekly", "monthly", "quarterly", "yearly"] = Field(default="none", description="How often it repeats; monthly keeps the day of month and clamps to month end.")
    until: dt.date | None = Field(default=None, json_schema_extra=ISO10, description="Last date it may occur, ISO YYYY-MM-DD; omit to repeat through the whole window.")
    confidence: float = Field(default=1.0, ge=0, le=1, description="Chance the money really arrives, 0 to 1. Applied to inflows only; outflows are always counted in full.")
    delay_days: int = Field(default=0, ge=0, le=365, description="Known days this item will slip past its date, e.g. a client who always pays 14 days late.")


class WeekRow(BaseModel):
    week: int = Field(description="Week number, 1-based.")
    week_start: str = Field(description="First day of the week, ISO date.")
    inflow: float = Field(description="Expected money in this week.")
    outflow: float = Field(description="Money out this week.")
    net: float = Field(description="Inflow minus outflow.")
    closing_balance: float = Field(description="Cash at the end of the week.")


class ForecastResult(BaseModel):
    start: str = Field(description="First day of week 1.")
    end: str = Field(description="Last day of the window.")
    opening_balance: float = Field(description="Starting cash.")
    weeks: list[WeekRow] = Field(description="One row per week.")
    total_inflow: float = Field(description="Sum of expected inflows.")
    total_outflow: float = Field(description="Sum of outflows.")
    closing_balance: float = Field(description="Cash at the end of the window.")
    lowest_balance: float = Field(description="Lowest weekly closing balance across the window.")
    lowest_week: int = Field(description="Week number of the lowest weekly closing balance.")
    first_negative_week: int = Field(description="First week with negative cash; 0 if never negative.")
    weeks_below_buffer: list[int] = Field(description="Weeks where cash is below the requested buffer.")
    warnings: list[str] = Field(description="Show to the user.")


class RunwayResult(BaseModel):
    cash: float = Field(description="Cash on hand.")
    monthly_expenses: float = Field(description="Monthly expenses used.")
    monthly_income: float = Field(description="Starting monthly income used.")
    net_monthly_burn: float = Field(description="Expenses minus starting income; negative means cash grows.")
    runway_months: float = Field(description="Months until cash runs out, 1 decimal; capped at the search limit when sustainable.")
    sustainable: bool = Field(description="True when cash never runs out within 120 months.")
    months_of_expenses_in_cash: float = Field(description="Cash divided by monthly expenses.")
    warnings: list[str] = Field(description="Show to the user.")


class StressResult(BaseModel):
    base: ForecastResult = Field(description="Forecast with your inputs as given.")
    stressed: ForecastResult = Field(description="Same forecast with the delay and haircut applied to every inflow.")
    lowest_balance_change: float = Field(description="Stressed lowest balance minus base lowest balance.")
    closing_balance_change: float = Field(description="Stressed closing balance minus base closing balance.")
    extra_negative_weeks: int = Field(description="How many more weeks end below zero under stress.")
    verdict: str = Field(description="One-line summary: survives, tight, or runs out.")
    warnings: list[str] = Field(description="Show to the user.")


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except CashflowInputError as e:
        raise ToolError(str(e)) from e


def _items(items: list[CashItem]) -> list[dict]:
    return [i.model_dump() for i in items]


StartDate = Annotated[dt.date, Field(json_schema_extra=ISO10, description="First day of week 1, ISO format YYYY-MM-DD; a Monday is conventional.")]
Opening = Annotated[float, Field(ge=-1_000_000_000, le=1_000_000_000, description="Bank balance at the start date, in the same currency as the items.")]
Weeks = Annotated[int, Field(ge=1, le=52, description="Number of weekly columns to forecast; 13 is the standard horizon.")]
Items = Annotated[list[CashItem], Field(min_length=1, max_length=300, description="Expected cash movements: invoices to be paid, rent, tools, tax, own pay.")]
Buffer = Annotated[float, Field(ge=0, le=1_000_000_000, description="Minimum cash you want to keep; weeks below it are flagged.")]


@mcp.tool(title="Forecast weekly cash flow", annotations=READ_ONLY)
def forecast_cashflow(start: StartDate, opening_balance: Opening, items: Items, weeks: Weeks = 13, min_buffer: Buffer = 0.0) -> ForecastResult:
    """Build a week-by-week cash forecast (default 13 weeks) from the opening balance, expected invoices and recurring costs, and flag the first week cash goes negative or under your buffer. Use for any 'will I run out of money' question."""
    return ForecastResult(**_guard(logic.forecast, start, opening_balance, weeks, _items(items), min_buffer))


@mcp.tool(title="Calculate cash runway", annotations=READ_ONLY)
def calculate_runway(
    cash: Annotated[float, Field(ge=-1_000_000_000, le=1_000_000_000, description="Cash on hand today.")],
    monthly_expenses: Annotated[float, Field(gt=0, le=1_000_000_000, description="Average monthly spending including your own pay and tax set-aside.")],
    monthly_income: Annotated[float, Field(ge=0, le=1_000_000_000, description="Average monthly income now; 0 if none.")] = 0.0,
    monthly_income_growth_pct: Annotated[float, Field(ge=-50, le=100, description="Expected month-on-month income growth in %; 0 for flat.")] = 0.0,
) -> RunwayResult:
    """Estimate how many months the cash lasts at the current burn rate, optionally with income growing or shrinking each month, and how many months of expenses the cash covers. Use for a quick survival check before quitting a job or taking a quiet quarter."""
    return RunwayResult(**_guard(logic.runway, cash, monthly_expenses, monthly_income, monthly_income_growth_pct))


@mcp.tool(title="Stress-test cash flow", annotations=READ_ONLY)
def stress_test_cashflow(
    start: StartDate,
    opening_balance: Opening,
    items: Items,
    inflow_delay_days: Annotated[int, Field(ge=0, le=180, description="Extra days every inflow arrives late in the stressed case, e.g. 30.")] = 30,
    inflow_haircut_pct: Annotated[float, Field(ge=0, le=100, description="Percent of every inflow that never arrives in the stressed case, e.g. 20.")] = 0.0,
    weeks: Weeks = 13,
    min_buffer: Buffer = 0.0,
) -> StressResult:
    """Run the forecast twice, as given and with every inflow delayed and/or cut, and compare the lowest balance and negative weeks. Use to see whether one big client paying 30 days late would sink you."""
    items_d = _items(items)
    base = _guard(logic.forecast, start, opening_balance, weeks, items_d, min_buffer)
    stressed = _guard(logic.forecast, start, opening_balance, weeks, items_d, min_buffer, inflow_delay_days, inflow_haircut_pct)
    neg = lambda r: sum(1 for w in r["weeks"] if w["closing_balance"] < 0)
    if stressed["first_negative_week"]:
        verdict = f"Runs out of cash in week {stressed['first_negative_week']} under stress."
    elif stressed["weeks_below_buffer"]:
        verdict = "Survives but falls below your buffer under stress."
    else:
        verdict = "Survives the stress case."
    warnings = [w for w in stressed["warnings"] if "Run stress_test_cashflow" not in w]
    if not base["first_negative_week"] and stressed["first_negative_week"]:
        warnings.insert(0, "The base case is fine but the stress case goes negative: line up a credit buffer or earlier payment terms.")
    return StressResult(base=ForecastResult(**base), stressed=ForecastResult(**stressed),
                        lowest_balance_change=round(stressed["lowest_balance"] - base["lowest_balance"], 2),
                        closing_balance_change=round(stressed["closing_balance"] - base["closing_balance"], 2),
                        extra_negative_weeks=neg(stressed) - neg(base), verdict=verdict, warnings=warnings)


@mcp.resource("cashflow://method", name="cashflow-method", title="Cash forecast method", mime_type="application/json",
              description="How the weekly forecast, runway and stress test are calculated.")
def method() -> str:
    return json.dumps({
        "week": "7 days from the start date; week n = start + 7(n-1) to start + 7n - 1",
        "closing": "opening + expected inflows - outflows, cumulative",
        "expected_inflow": "amount x confidence x (1 - stress haircut); outflows count in full",
        "delay": "the whole series shifts by delay days, then lands in the week of the shifted date",
        "monthly": "keeps the original day of month, clamped to month end",
        "runway": "month-by-month: balance + income - expenses until below zero; last month pro-rated",
        "reference": "Direct-method 13-week cash flow, the standard small-business and lender format",
    }, indent=2)


@mcp.prompt(title="13-week cash check", description="Collect inputs, forecast 13 weeks, stress-test a late payer and recommend actions.")
def thirteen_week_cash_check(today: str, situation: str) -> str:
    return (
        f"You are a cash-flow adviser for a one-person company. Today is {today}. The owner says:\n\n---\n{situation}\n---\n\n"
        "1. Ask for anything missing: bank balance, invoices with dates and likelihood, recurring costs, tax set-aside, own pay.\n"
        "2. Call forecast_cashflow with a buffer of about one month of expenses.\n"
        "3. Call stress_test_cashflow with the biggest client paying 30 days late.\n"
        "4. Show the weekly table, the lowest week, warnings, and the two most useful actions (chase, delay, invoice earlier)."
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
