"""Vic Demurrage & Detention MCP server: last free day, tiered charge calculation, what-if exit dates and invoice audit. Fully offline."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .logic import (DemurrageInputError, charges, check_tiers, explain_invoice, last_free_day, parse_date,
                    parse_holidays)

mcp = MCPServer(
    name="vic-demurrage-detention",
    title="Vic Demurrage & Detention",
    description="Last free day, tiered demurrage/detention charges, what-if exit dates and invoice audit for containers.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers",
    instructions=(
        "Use these tools to rebuild a carrier's demurrage or detention count from the tariff rule: free days, calendar or "
        "working days, whether the start and end day count, and the daily rate tiers. The tariff or contract of the carrier "
        "or terminal always wins: ask the user for the rule (or read it from the invoice) instead of guessing, and say which "
        "assumptions you used. Results are estimates, never a payment instruction or legal advice. Any dispute note is a "
        "draft for the user to review; never send it."
    ),
)

LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

DateStr = Annotated[str, Field(min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$", description="ISO date YYYY-MM-DD, in the port's local calendar.")]
FreeDays = Annotated[int, Field(ge=0, le=60, description="Free days granted by the tariff or contract before charges start (0 to 60).")]
DayType = Annotated[Literal["calendar", "working"], Field(description="'calendar' counts every day; 'working' skips weekends and the holidays you list. Many US terminals count free time in working days but bill chargeable days in calendar days.")]
Holidays = Annotated[list[str], Field(max_length=60, description="Non-working holiday dates YYYY-MM-DD (terminal closed). Only used for working-day counting.")]
StartFlag = Annotated[bool, Field(description="True if the start day (discharge/availability or gate-out) is counted as day 1; False if counting starts the next day. Read the tariff rule.")]
EndFlag = Annotated[bool, Field(description="True if the end day (gate-out or empty return) is charged as a full day. 'Each day or part thereof' rules usually mean True.")]


class Tier(BaseModel):
    from_day: int = Field(ge=1, le=400, description="Chargeable day number where this rate starts; the first tier must start at 1.")
    rate: float = Field(ge=0, le=100000, description="Charge per container per day from that day on, in the tariff currency.")


Tiers = Annotated[list[Tier], Field(min_length=1, max_length=12, description="Rising daily rate tiers, e.g. [{from_day:1, rate:150}, {from_day:4, rate:300}]. Day 1 is the first chargeable day after free time.")]


class DayRow(BaseModel):
    date: str = Field(description="Calendar date.")
    status: str = Field(description="free, skipped (non-working day not counted) or charged.")
    charge_day_no: int = Field(description="Chargeable day number, 0 when not charged.")
    rate: float = Field(description="Rate applied that day.")


class RateBlock(BaseModel):
    rate: float
    days: int
    amount: float


class LastFree(BaseModel):
    last_free_day: str | None = Field(description="Last day that is still free; null when free_days is 0.")
    first_chargeable_day: str = Field(description="First day a charge can start.")
    days_left: int | None = Field(description="Calendar days from today to the last free day (negative if passed); null when today was not given.")
    warnings: list[str] = Field(description="Show these to the user.")


class ChargeResult(BaseModel):
    currency: str
    kind: str
    total: float = Field(description="Estimated total including any fixed fee.")
    charged_days: int
    free_days_used: int
    last_free_day: str | None
    by_rate: list[RateBlock]
    days: list[DayRow]
    fmc_invoice_deadline: str | None = Field(description="With us_trade=true: the date after which a US invoice for this charge is no longer payable (30 calendar days after the last charged day, 46 CFR 541.7).")
    warnings: list[str] = Field(description="Show these to the user.")


class ExitOption(BaseModel):
    end_date: str
    charged_days: int
    total: float
    extra_vs_cheapest: float


class WhatIfResult(BaseModel):
    currency: str
    options: list[ExitOption]
    cheapest_end_date: str
    warnings: list[str] = Field(description="Show these to the user.")


class Convention(BaseModel):
    started_one_day_earlier: bool = Field(description="True if the clock started a day before your start date (e.g. the day-before vessel departure or a 'first 3 AM' rule).")
    include_start_day: bool
    include_end_day: bool
    free_day_type: str
    charged_days: int
    total: float
    matches_billed: bool
    difference: float = Field(description="Billed amount minus this recalculation.")


class AuditResult(BaseModel):
    currency: str
    billed: float
    your_rule_total: float = Field(description="Total with the rule exactly as given.")
    your_rule_difference: float = Field(description="Billed minus total under your rule; positive means you were billed more.")
    verdict: str
    conventions: list[Convention]
    draft_dispute_note: str = Field(description="Draft only. Review and edit before the user sends anything.")
    warnings: list[str] = Field(description="Show these to the user.")


def _run(fn, *a, **k):
    try:
        return fn(*a, **k)
    except DemurrageInputError as e:
        raise ToolError(str(e)) from e


def _tiers(t: list[Tier]):
    return _run(check_tiers, [x.model_dump() for x in t])


_GEN = "Estimate from the rule you gave. The carrier's tariff, contract or terminal rules decide the real amount; check start event, free-day type and exclusions (strikes, holds, closures) with them."


def _fmt(d: date | None) -> str | None:
    return d.isoformat() if d else None


@mcp.tool(title="Find last free day", annotations=LOCAL)
def find_last_free_day(
    start_date: DateStr,
    free_days: FreeDays,
    free_day_type: DayType = "calendar",
    include_start_day: StartFlag = True,
    holidays: Holidays = [],
    today: Annotated[str | None, Field(default=None, min_length=10, max_length=10, description="Optional today's date YYYY-MM-DD to compute days left; the server has no clock of its own.")] = None,
) -> LastFree:
    """Work out the last free day and first chargeable day for a container from its start date and free time, in calendar or working days.

    Use it the moment a container is discharged or gated out, to know the deadline to pick up or return it.
    """
    s = _run(parse_date, start_date, "start_date")
    hol = _run(parse_holidays, holidays)
    lfd, first = _run(last_free_day, s, free_days, free_day_type, include_start_day, hol)
    left = (lfd - _run(parse_date, today, "today")).days if (lfd and today) else None
    warns = [_GEN]
    if free_day_type == "working" and not hol:
        warns.append("Working days skip only weekends because no holidays were listed; add terminal closure dates if any fall in the period.")
    if free_days == 0:
        warns.append("No free time: charges start on the first counted day.")
    if left is not None and left < 0:
        warns.append("The last free day has already passed; charges are running.")
    return LastFree(last_free_day=_fmt(lfd), first_chargeable_day=_fmt(first), days_left=left, warnings=warns)


def _calc(kind, start_date, end_date, free_days, free_day_type, charge_day_type, include_start_day, include_end_day, tiers, holidays, fixed_fee):
    s, e = _run(parse_date, start_date, "start_date"), _run(parse_date, end_date, "end_date")
    return s, e, _run(charges, s, e, free_days, free_day_type, charge_day_type, include_start_day, include_end_day, _tiers(tiers), _run(parse_holidays, holidays), fixed_fee)


@mcp.tool(title="Calculate demurrage or detention", annotations=LOCAL)
def calculate_charges(
    kind: Annotated[Literal["demurrage", "detention"], Field(description="demurrage = loaded container at the terminal past free time; detention = container outside the terminal (late empty return).")],
    start_date: DateStr,
    end_date: DateStr,
    free_days: FreeDays,
    tiers: Tiers,
    free_day_type: DayType = "calendar",
    charge_day_type: Annotated[Literal["calendar", "working"], Field(description="Days counted once free time is used up. Usually 'calendar' (weekends and holidays are billed).")] = "calendar",
    include_start_day: StartFlag = True,
    include_end_day: EndFlag = True,
    holidays: Holidays = [],
    fixed_fee: Annotated[float, Field(ge=0, le=1000000, description="Fixed or administrative fee added once, in the tariff currency.")] = 0.0,
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$", description="3-letter currency code of the tariff, e.g. USD.")] = "USD",
    us_trade: Annotated[bool, Field(description="True for US import/export: also gives the FMC 30-day invoice deadline (46 CFR 541.7).")] = False,
) -> ChargeResult:
    """Count days between a start and an end date, apply free time and rising daily rate tiers, and return the total with a day-by-day table.

    Use it to estimate demurrage when a container leaves the terminal or detention when the empty comes back, or to check a tariff before booking.
    """
    s, e, c = _calc(kind, start_date, end_date, free_days, free_day_type, charge_day_type, include_start_day, include_end_day, tiers, holidays, fixed_fee)
    warns = [_GEN]
    if c["charged_days"] == 0:
        warns.append("Everything falls inside free time: no charge under this rule.")
    if free_day_type == "working" and not holidays:
        warns.append("Working days skip only weekends because no holidays were listed.")
    if not include_end_day:
        warns.append("The end day is not counted; many tariffs charge 'each day or part thereof', which would add a day.")
    deadline = None
    if us_trade and c["charged_days"]:
        last = [x for x in c["days"] if x["status"] == "charged"][-1]["date"]
        deadline = (last + timedelta(days=30)).isoformat()
        warns.append("US trade: under 46 CFR 541.7 an invoice issued more than 30 calendar days after the charge was last incurred is not payable. Not legal advice.")
    return ChargeResult(currency=currency.upper(), kind=kind, total=c["total"], charged_days=c["charged_days"], free_days_used=c["free_days_used"],
                        last_free_day=_fmt(c["last_free_day"]), by_rate=[RateBlock(**b) for b in c["by_rate"]],
                        days=[DayRow(date=x["date"].isoformat(), status=x["status"], charge_day_no=x["charge_day_no"], rate=x["rate"]) for x in c["days"]],
                        fmc_invoice_deadline=deadline, warnings=warns)


@mcp.tool(title="Compare exit dates", annotations=LOCAL)
def compare_exit_dates(
    kind: Annotated[Literal["demurrage", "detention"], Field(description="demurrage (pick-up date) or detention (empty return date).")],
    start_date: DateStr,
    candidate_end_dates: Annotated[list[str], Field(min_length=1, max_length=14, description="Possible pick-up or return dates YYYY-MM-DD to compare, 1 to 14.")],
    free_days: FreeDays,
    tiers: Tiers,
    free_day_type: DayType = "calendar",
    include_start_day: StartFlag = True,
    include_end_day: EndFlag = True,
    holidays: Holidays = [],
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$", description="3-letter currency code of the tariff.")] = "USD",
) -> WhatIfResult:
    """Price several possible pick-up or return dates side by side and show how much each extra day costs.

    Use it when deciding whether to rush a truck for tomorrow or wait until Monday, or to see what a delay will add.
    """
    s = _run(parse_date, start_date, "start_date")
    t, hol = _tiers(tiers), _run(parse_holidays, holidays)
    rows = []
    for d in sorted({_run(parse_date, x, "candidate_end_dates item") for x in candidate_end_dates}):
        c = _run(charges, s, d, free_days, free_day_type, "calendar", include_start_day, include_end_day, t, hol)
        rows.append((d, c["charged_days"], c["total"]))
    best = min(r[2] for r in rows)
    opts = [ExitOption(end_date=d.isoformat(), charged_days=n, total=tot, extra_vs_cheapest=round(tot - best, 2)) for d, n, tot in rows]
    cheapest = next(o.end_date for o in opts if o.extra_vs_cheapest == 0)
    return WhatIfResult(currency=currency.upper(), options=opts, cheapest_end_date=cheapest,
                        warnings=[_GEN, "Charge days after free time are counted in calendar days here; weekends and holidays are billed."])


@mcp.tool(title="Audit a demurrage invoice", annotations=LOCAL)
def audit_invoice(
    kind: Annotated[Literal["demurrage", "detention"], Field(description="demurrage or detention.")],
    start_date: DateStr,
    end_date: DateStr,
    free_days: FreeDays,
    tiers: Tiers,
    billed_amount: Annotated[float, Field(ge=0, le=10000000, description="Total on the invoice, in the tariff currency.")],
    free_day_type: DayType = "calendar",
    include_start_day: StartFlag = True,
    include_end_day: EndFlag = True,
    holidays: Holidays = [],
    fixed_fee: Annotated[float, Field(ge=0, le=1000000, description="Fixed or admin fee the invoice includes, if any.")] = 0.0,
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$", description="3-letter currency code of the tariff.")] = "USD",
) -> AuditResult:
    """Recalculate an invoice under your reading of the rule, then try the other counting conventions to see which one explains the billed amount.

    Use it when a carrier or forwarder invoice looks too high, to find the off-by-one or working-day dispute and get a draft note to ask for a correction.
    """
    s, e, c = _calc(kind, start_date, end_date, free_days, free_day_type, "calendar", include_start_day, include_end_day, tiers, holidays, fixed_fee)
    t, hol = _tiers(tiers), _run(parse_holidays, holidays)
    rows = _run(explain_invoice, billed_amount, s, e, free_days, "calendar", t, hol, fixed_fee)
    diff = round(billed_amount - c["total"], 2)
    matches = [r for r in rows if r["matches_billed"]]
    if abs(diff) < 0.005:
        verdict = "The invoice matches your reading of the rule."
        note = ""
    elif matches:
        m = matches[0]
        verdict = (f"Billed {diff:+.2f} {currency.upper()} vs your rule. The invoice is reproduced by: start day counted={m['include_start_day']}, "
                   f"started a day earlier={m['started_one_day_earlier']}, end day counted={m['include_end_day']}, free days in {m['free_day_type']} days. Check which one the tariff really says.")
        note = ""
    else:
        verdict = f"Billed {diff:+.2f} {currency.upper()} vs your rule and no counting convention reproduces it: ask for the rate, day count and tariff rule reference."
        note = ""
    if abs(diff) >= 0.005:
        note = (f"DRAFT, review before sending.\n\nSubject: Request to review {kind} invoice\n\nHello,\n\nWe rebuilt the {kind} count for this container: "
                f"start {start_date}, end {end_date}, {free_days} free {free_day_type} days, your tariff tiers. We calculate {c['total']:.2f} {currency.upper()} "
                f"but the invoice shows {billed_amount:.2f} {currency.upper()}. Please send the tariff rule, start and end events, the dates charged and the rate "
                f"for each day so we can reconcile. If the days were counted differently from the tariff, please correct the invoice. We also ask you to consider "
                f"a waiver or mitigation of the excess.\n\nThank you.")
    warns = [_GEN, "This is not legal advice. In US trade, the FMC billing rule (46 CFR 541) lets the billed party ask for mitigation, refund or waiver within 30 calendar days of the invoice date; keep that deadline."]
    return AuditResult(currency=currency.upper(), billed=billed_amount, your_rule_total=c["total"], your_rule_difference=diff, verdict=verdict,
                       conventions=[Convention(**r) for r in rows], draft_dispute_note=note, warnings=warns)


@mcp.resource("demurrage://counting-checklist", name="counting-checklist", title="Counting rule checklist", mime_type="text/markdown",
              description="Fields to read from a tariff rule before counting demurrage or detention days.")
def checklist() -> str:
    return ("# Fields to read from the tariff rule\n- Start event (discharge, availability, gate-out) and start time of day\n"
            "- Free days, separate for demurrage and detention\n- Day type: calendar or working (and which holidays)\n"
            "- Is the start day day 1? Is the end day charged ('each day or part thereof')?\n- Rate tiers by container type and size\n"
            "- Exclusions: terminal closures, government holds, strikes\n- US: invoice within 30 days (46 CFR 541.7); mitigation request window 30 days (541.8)\n")


@mcp.prompt(title="Check a container invoice", description="Walk through a demurrage or detention invoice and rebuild the count.")
def invoice_check(invoice_text: str) -> str:
    return (
        "Here is a demurrage/detention invoice or tariff text:\n\n---\n" + invoice_text + "\n---\n\n"
        "1. Extract start date, end date, free days, day type, rate tiers and billed total; ask me for anything missing.\n"
        "2. Call audit_invoice and show which counting convention explains the amount.\n"
        "3. Show the draft dispute note for my review. Do not send anything."
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
