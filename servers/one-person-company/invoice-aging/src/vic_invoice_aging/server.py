"""Vic Invoice Aging MCP server: receivables maths for one-person companies.

Built on the official MCP Python SDK v2 (protocol revision 2026-07-28). Offline: no network, no API key.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from . import logic
from .logic import InvoiceInputError

mcp = MCPServer(
    name="vic-invoice-aging",
    title="Vic Invoice Aging",
    description="Receivables for freelancers: payment due dates, overdue aging buckets, EU/UK statutory late-payment interest, reminder drafts.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers/tree/main/servers/one-person-company/invoice-aging",
    instructions=(
        "Use these tools when a freelancer or one-person company sets payment terms, reviews unpaid invoices, or chases a late payer. "
        "Ask for the current date, invoice due dates and amounts instead of guessing them. For statutory interest, ask the user to look up "
        "the ECB or Bank of England reference rate; never invent it. Reminder drafts are never sent: show them to the user. "
        "Always show warnings. Results are not legal advice."
    ),
)

ISO10 = {"minLength": 10, "maxLength": 10}  # ISO dates are exactly 10 characters
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class DueDateResult(BaseModel):
    invoice_date: str = Field(description="ISO date of the invoice.")
    due_date: str = Field(description="ISO due date.")
    weekday: str = Field(description="Weekday of the due date.")
    total_days: int = Field(description="Days from invoice date to due date.")
    terms: str = Field(description="Terms as written, e.g. Net 30 or EOM+30.")
    warnings: list[str] = Field(description="Show to the user.")


class InvoiceIn(BaseModel):
    invoice_id: str = Field(min_length=1, max_length=60, description="Your invoice number, unique per invoice.")
    client: str = Field(min_length=1, max_length=120, description="Client name.")
    amount: float = Field(gt=0, le=100_000_000, description="Invoice total in one currency.")
    due_date: date = Field(json_schema_extra=ISO10, description="Due date, ISO format YYYY-MM-DD.")
    paid_amount: float = Field(default=0.0, ge=0, le=100_000_000, description="Part payments received so far; 0 if none.")


class Bucket(BaseModel):
    bucket: str = Field(description="not_due, 1_30, 31_60, 61_90 or over_90 (days overdue).")
    amount: float = Field(description="Open balance in the bucket.")
    invoice_count: int = Field(description="Invoices in the bucket.")


class ClientBalance(BaseModel):
    client: str = Field(description="Client name.")
    open_amount: float = Field(description="Open balance for this client.")


class OverdueInvoice(BaseModel):
    invoice_id: str = Field(description="Invoice number.")
    client: str = Field(description="Client name.")
    open_amount: float = Field(description="Unpaid part.")
    days_overdue: int = Field(description="Days past due on the as-of date.")
    bucket: str = Field(description="Aging bucket.")


class AgingResult(BaseModel):
    as_of: str = Field(description="Date the aging was run for.")
    outstanding: float = Field(description="Total open balance.")
    overdue_total: float = Field(description="Open balance already past due.")
    overdue_pct: float = Field(description="Overdue share of outstanding, in %.")
    buckets: list[Bucket] = Field(description="Open balance by days overdue.")
    by_client: list[ClientBalance] = Field(description="Open balance per client, largest first.")
    overdue_invoices: list[OverdueInvoice] = Field(description="Overdue invoices, oldest first: the chase list.")
    warnings: list[str] = Field(description="Show to the user.")


class InterestResult(BaseModel):
    days_overdue: int = Field(description="Days from due date to the end date; 0 if not overdue.")
    annual_rate_pct: float = Field(description="Annual interest rate applied, in %.")
    interest: float = Field(description="Simple interest, actual/365.")
    fixed_compensation: float = Field(description="Fixed recovery-cost sum (EUR 40 EU minimum, GBP 40/70/100 UK).")
    total_claim: float = Field(description="Interest plus fixed compensation, excluding principal.")
    daily_interest: float = Field(description="Interest added per further day.")
    basis: str = Field(description="How the rate was built.")
    warnings: list[str] = Field(description="Show to the user.")


class ReminderDraft(BaseModel):
    stage: str = Field(description="pre_due, friendly, firm, formal or final.")
    subject: str = Field(description="Email subject line.")
    body: str = Field(description="Email body text.")
    draft_only: bool = Field(description="Always true: nothing is sent.")
    warnings: list[str] = Field(description="Show to the user.")


def _guard(fn, *a):
    try:
        return fn(*a)
    except InvoiceInputError as e:
        raise ToolError(str(e)) from e


@mcp.tool(title="Calculate invoice due date", annotations=READ_ONLY)
def calculate_due_date(
    invoice_date: Annotated[date, Field(json_schema_extra=ISO10, description="Invoice issue date, ISO format YYYY-MM-DD.")],
    net_days: Annotated[int, Field(ge=0, le=365, description="Payment term in days, e.g. 30 for Net 30.")] = 30,
    end_of_month: Annotated[bool, Field(description="True for EOM terms: count the days from the end of the invoice month.")] = False,
) -> DueDateResult:
    """Work out the due date for Net N or EOM+N terms, flag weekend due dates and terms above 60 days that EU law can treat as unfair. Use when drafting an invoice or agreeing payment terms."""
    return DueDateResult(**_guard(logic.due_date, invoice_date, net_days, end_of_month))


@mcp.tool(title="Age unpaid invoices", annotations=READ_ONLY)
def age_invoices(
    as_of: Annotated[date, Field(json_schema_extra=ISO10, description="Today's date, or the date to review, ISO format YYYY-MM-DD.")],
    invoices: Annotated[list[InvoiceIn], Field(min_length=1, max_length=500, description="Invoices to review, one object per invoice.")],
) -> AgingResult:
    """Build an accounts-receivable aging report: open balance by days overdue (not due, 1-30, 31-60, 61-90, over 90), per client totals and an oldest-first chase list, with warnings for concentration and old debt. Use for a weekly receivables review."""
    return AgingResult(**_guard(logic.age_invoices, as_of, [i.model_dump() for i in invoices]))


@mcp.tool(title="Calculate late-payment interest", annotations=READ_ONLY)
def calculate_late_interest(
    principal: Annotated[float, Field(gt=0, le=100_000_000, description="Unpaid invoice amount.")],
    due_date: Annotated[date, Field(json_schema_extra=ISO10, description="Original due date, ISO format YYYY-MM-DD.")],
    paid_or_as_of: Annotated[date, Field(json_schema_extra=ISO10, description="Date the invoice was paid, or today if still unpaid.")],
    regime: Annotated[Literal["eu", "uk", "custom"], Field(description="eu = Directive 2011/7/EU, uk = Late Payment Act 1998, custom = rate from your contract.")] = "eu",
    reference_rate_pct: Annotated[float | None, Field(ge=-1, le=30, description="ECB main refinancing rate (eu) or Bank of England base rate (uk) at the start of the half-year the debt fell due. Required for eu and uk; look it up.")] = None,
    custom_annual_rate_pct: Annotated[float | None, Field(ge=0, le=100, description="Annual rate in %, only for regime custom.")] = None,
    custom_fixed_fee: Annotated[float, Field(ge=0, le=100_000, description="Fixed recovery fee, only for regime custom.")] = 0.0,
) -> InterestResult:
    """Compute statutory late-payment interest (reference rate + 8 points, actual/365) and the fixed recovery sum for an overdue B2B invoice under EU Directive 2011/7/EU, the UK Late Payment Act, or a contract rate. Use before chasing or invoicing interest."""
    return InterestResult(**_guard(logic.late_interest, principal, due_date, paid_or_as_of, regime, reference_rate_pct, custom_annual_rate_pct, custom_fixed_fee))


@mcp.tool(title="Draft a payment reminder", annotations=READ_ONLY)
def draft_payment_reminder(
    client: Annotated[str, Field(min_length=1, max_length=120, description="Client or contact name to address.")],
    invoice_id: Annotated[str, Field(min_length=1, max_length=60, description="Invoice number.")],
    open_amount: Annotated[float, Field(gt=0, le=100_000_000, description="Unpaid amount.")],
    days_overdue: Annotated[int, Field(ge=-30, le=3650, description="Days past due; zero or negative if not yet due.")],
    sender: Annotated[str, Field(min_length=1, max_length=120, description="Your name or business name for the sign-off.")],
    currency: Annotated[str, Field(min_length=3, max_length=3, description="ISO currency code, e.g. USD.")] = "USD",
    language: Annotated[Literal["en", "zh"], Field(description="Draft language: en or zh.")] = "en",
    interest_amount: Annotated[float | None, Field(ge=0, le=100_000_000, description="Accrued interest from calculate_late_interest; mentioned only in formal and final notices.")] = None,
) -> ReminderDraft:
    """Write a reminder email draft whose tone escalates with lateness (pre-due, friendly, firm, formal, final), in English or Chinese. It only drafts text and never sends anything; the user reviews and sends it. Use after age_invoices shows who to chase."""
    return ReminderDraft(**_guard(logic.reminder_draft, client, invoice_id, open_amount, currency.upper(), days_overdue, sender, language, interest_amount))


@mcp.resource("receivables://rules", name="receivables-rules", title="Late payment rules and formulas", mime_type="application/json",
              description="Formulas and legal references behind every tool in this server.")
def rules() -> str:
    return json.dumps({
        "due_date": "invoice_date + N days; EOM: end of invoice month + N days",
        "interest": "principal x (reference_rate + 8%) x days_overdue / 365, from the day after the due date",
        "eu": "Directive 2011/7/EU Art. 3(1)(d) interest, Art. 6 fixed compensation of at least EUR 40",
        "uk": "Late Payment of Commercial Debts (Interest) Act 1998: 8% over base rate; fixed GBP 40 / 70 / 100",
        "aging_buckets": ["not_due", "1-30", "31-60", "61-90", "over 90"],
    }, indent=2)


@mcp.prompt(title="Weekly receivables review", description="Review unpaid invoices, price the interest, and draft reminders for the worst payers.")
def weekly_receivables_review(today: str, invoices_text: str) -> str:
    return (
        f"You are a collections assistant for a one-person company. Today is {today}. Invoices:\n\n---\n{invoices_text}\n---\n\n"
        "1. Call age_invoices with these invoices.\n"
        "2. For the oldest overdue invoices, ask the user for their country and the current ECB/BoE reference rate, then call calculate_late_interest.\n"
        "3. Call draft_payment_reminder for each client to chase and show the drafts for review; never claim anything was sent.\n"
        "4. Summarise warnings and the single most urgent action."
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
