"""Vic Creator Quote MCP server: judge influencer quotes by CPM, CPE and payback.

Built on the official MCP Python SDK v2 (protocol revision 2026-07-28). Offline: no network, no API key.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from . import logic
from .logic import QuoteInputError

mcp = MCPServer(
    name="vic-creator-quote",
    title="Vic Creator Quote",
    description="Judge influencer and creator quotes: engagement rate from real posts, CPM/CPE with usage and exclusivity, payback ceiling, counter-offer drafts.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers/tree/main/servers/social-media/creator-quote",
    instructions=(
        "Use these tools when a brand, agency or seller is deciding whether a creator's quote is fair. Ask the user for the creator's recent post "
        "views and engagements (native analytics screenshots are best) and for their own target CPM; never invent benchmarks or market rates. "
        "Judge on cost per expected view, not per follower. Counter-offer drafts are never sent: show them to the user. Always show warnings."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
COUNT = Field(ge=0, le=1_000_000_000)


class PostIn(BaseModel):
    views: int = Field(gt=0, le=10_000_000_000, description="Views or plays of the post (not reach).")
    likes: int = Field(ge=0, le=1_000_000_000, description="Likes; 0 if hidden.")
    comments: int = Field(ge=0, le=1_000_000_000, description="Comments.")
    shares: int = Field(default=0, ge=0, le=1_000_000_000, description="Shares or reposts; 0 if not shown.")
    saves: int = Field(default=0, ge=0, le=1_000_000_000, description="Saves or bookmarks; 0 if not shown.")


class PostRate(BaseModel):
    index: int = Field(description="1-based position of the post in the input.")
    views: int = Field(description="Views.")
    engagements: int = Field(description="Likes + comments + shares + saves.")
    er_by_views_pct: float = Field(description="Engagements / views, in %.")
    er_by_followers_pct: float | None = Field(description="Engagements / followers in %, null if followers not given.")
    viral_outlier: bool = Field(description="True when views exceed 3x the median (needs 4+ posts).")


class EngagementResult(BaseModel):
    posts: list[PostRate] = Field(description="One row per input post.")
    posts_used: int = Field(description="Posts behind the medians.")
    median_views: float = Field(description="Median views: the number to price on.")
    median_engagements: float = Field(description="Median engagements per post.")
    median_er_by_views_pct: float = Field(description="Median engagement rate by views, in %.")
    mean_views_all_posts: float = Field(description="Mean views over all posts, shown to expose viral skew.")
    median_er_by_followers_pct: float | None = Field(description="Median ER by followers in %, null if followers not given.")
    views_to_followers_pct: float | None = Field(description="Median views as % of followers, null if followers not given.")
    warnings: list[str] = Field(description="Show to the user.")


class QuoteResult(BaseModel):
    expected_total_views: float = Field(description="avg views x deliverables.")
    base_cpm: float = Field(description="Base fee per 1,000 expected views.")
    usage_fee: float = Field(description="Base fee x usage % per month x months.")
    exclusivity_fee: float = Field(description="Exclusivity fee as given.")
    contract_cost: float = Field(description="Base fee + usage + exclusivity.")
    effective_cpm: float = Field(description="Contract cost per 1,000 expected views: compare quotes on this.")
    cpe: float | None = Field(description="Base fee per engagement, null if engagements not given.")
    er_by_views_pct: float | None = Field(description="Typical engagement rate by views in %.")
    follower_based_cpm: float | None = Field(description="Fee per 1,000 followers; shown only as the misleading alternative.")
    cpm_verdict: str = Field(description="within_target, above_target or no_target_given.")
    cpm_gap_pct: float | None = Field(description="Effective CPM vs target in %; positive means above target.")
    cpe_verdict: str | None = Field(description="within_target or above_target; null without target_cpe.")
    max_base_fee_at_target_cpm: float | None = Field(description="Highest base fee that keeps effective CPM at target: your counter-offer ceiling.")
    warnings: list[str] = Field(description="Show to the user.")


class PaybackResult(BaseModel):
    profit_per_sale: float = Field(description="Net order value x margin %.")
    sales_to_break_even: int = Field(description="Whole sales needed to cover the contract cost.")
    expected_balance: float | None = Field(description="Expected sales profit minus contract cost, null without expected_sales.")
    base_fee_ceiling: float | None = Field(description="Highest base fee that still breaks even at expected sales, with usage added.")
    warnings: list[str] = Field(description="Show to the user.")


class CounterOfferDraft(BaseModel):
    subject: str = Field(description="Email subject.")
    body: str = Field(description="Email body text.")
    draft_only: bool = Field(description="Always true: nothing is sent.")
    warnings: list[str] = Field(description="Show to the user.")


def _guard(fn, *a):
    try:
        return fn(*a)
    except QuoteInputError as e:
        raise ToolError(str(e)) from e


@mcp.tool(title="Calculate engagement rate", annotations=READ_ONLY)
def calculate_engagement_rate(
    posts: Annotated[list[PostIn], Field(min_length=1, max_length=60, description="Recent posts of one format (Reels, TikToks, videos); 10-12 is ideal.")],
    followers: Annotated[int | None, Field(ge=1, le=2_000_000_000, description="Follower count on the same date; optional, adds follower-based rates.")] = None,
    exclude_viral: Annotated[bool, Field(description="Drop posts above 3x median views from the medians (needs 4+ posts).")] = True,
) -> EngagementResult:
    """Compute engagement rate per post by views and by followers (likes + comments + shares + saves), the median across posts, and flag viral outliers that inflate averages. Use before pricing a creator."""
    return EngagementResult(**_guard(logic.engagement_rate, [p.model_dump() for p in posts], followers, exclude_viral))


@mcp.tool(title="Evaluate creator quote", annotations=READ_ONLY)
def evaluate_creator_quote(
    fee: Annotated[float, Field(gt=0, le=100_000_000, description="Base fee for all deliverables together, one currency.")],
    avg_views: Annotated[float, Field(gt=0, le=10_000_000_000, description="Typical (median) views per deliverable.")],
    deliverables: Annotated[int, Field(ge=1, le=500, description="Number of posts or videos covered by the fee.")] = 1,
    avg_engagements: Annotated[float | None, Field(ge=0, le=10_000_000_000, description="Typical engagements per deliverable; optional, adds CPE.")] = None,
    followers: Annotated[int | None, Field(ge=1, le=2_000_000_000, description="Follower count; optional, only for the warning about follower-based CPM.")] = None,
    usage_pct_per_month: Annotated[float, Field(ge=0, le=100, description="Usage-rights fee as % of base fee per month; 0 if none.")] = 0.0,
    usage_months: Annotated[int, Field(ge=0, le=60, description="Months of usage rights bought; 0 if none.")] = 0,
    exclusivity_fee: Annotated[float, Field(ge=0, le=100_000_000, description="Extra fee for exclusivity; 0 if none.")] = 0.0,
    target_cpm: Annotated[float | None, Field(gt=0, le=100_000, description="Your own acceptable cost per 1,000 views for this channel; required for a verdict.")] = None,
    target_cpe: Annotated[float | None, Field(gt=0, le=100_000, description="Your acceptable cost per engagement; optional.")] = None,
) -> QuoteResult:
    """Judge one creator quote: base and effective CPM (usage and exclusivity included), cost per engagement, a verdict against your own targets, and the highest base fee that meets your target CPM. Use when a creator sends a price."""
    return QuoteResult(**_guard(logic.evaluate_quote, fee, deliverables, avg_views, avg_engagements, followers,
                                usage_pct_per_month, usage_months, exclusivity_fee, target_cpm, target_cpe))


@mcp.tool(title="Calculate payback ceiling", annotations=READ_ONLY)
def calculate_payback_ceiling(
    contract_cost: Annotated[float, Field(gt=0, le=100_000_000, description="Total contract cost: base fee + usage + exclusivity.")],
    net_order_value: Annotated[float, Field(gt=0, le=10_000_000, description="Average order value after discounts and refunds.")],
    margin_pct: Annotated[float, Field(gt=0, le=100, description="Contribution margin per order in %, after product, shipping and fees.")],
    expected_sales: Annotated[int | None, Field(ge=0, le=100_000_000, description="Sales you expect from the post; optional, adds balance and ceiling.")] = None,
    usage_pct_per_month: Annotated[float, Field(ge=0, le=100, description="Usage fee % per month, used for the base-fee ceiling.")] = 0.0,
    usage_months: Annotated[int, Field(ge=0, le=60, description="Usage months, used for the base-fee ceiling.")] = 0,
) -> PaybackResult:
    """Work out how many sales a creator deal must drive to pay for itself, the expected profit or loss at your sales estimate, and the highest base fee you can pay and still break even. Use for sales-driven (not awareness) campaigns."""
    return PaybackResult(**_guard(logic.payback, contract_cost, net_order_value, margin_pct, expected_sales, usage_pct_per_month, usage_months))


@mcp.tool(title="Draft counter-offer", annotations=READ_ONLY)
def draft_counter_offer(
    creator: Annotated[str, Field(min_length=1, max_length=120, description="Creator name to address.")],
    brand: Annotated[str, Field(min_length=1, max_length=120, description="Your brand name.")],
    sender: Annotated[str, Field(min_length=1, max_length=120, description="Your name for the sign-off.")],
    deliverables: Annotated[int, Field(ge=1, le=500, description="Deliverables covered by the quote.")],
    current_fee: Annotated[float, Field(gt=0, le=100_000_000, description="Fee the creator quoted.")],
    proposed_fee: Annotated[float, Field(gt=0, le=100_000_000, description="Fee you propose; must be below current_fee.")],
    currency: Annotated[str, Field(min_length=3, max_length=3, description="ISO currency code, e.g. USD.")] = "USD",
    current_cpm: Annotated[float | None, Field(gt=0, le=100_000, description="Quote's CPM from evaluate_creator_quote; optional reason line.")] = None,
    target_cpm: Annotated[float | None, Field(gt=0, le=100_000, description="Your target CPM; optional reason line, needs current_cpm.")] = None,
    language: Annotated[Literal["en", "zh"], Field(description="Draft language: en or zh.")] = "en",
) -> CounterOfferDraft:
    """Write a polite counter-offer email draft to a creator, optionally citing the CPM gap, in English or Chinese. It only drafts text and never sends anything; the user reviews and sends it. Use after evaluate_creator_quote says above target."""
    return CounterOfferDraft(**_guard(logic.counter_offer, creator, brand, deliverables, current_fee, proposed_fee,
                                      currency.upper(), current_cpm, target_cpm, language, sender))


@mcp.resource("creator://formulas", name="creator-formulas", title="Creator pricing formulas", mime_type="application/json",
              description="Formulas behind every tool in this server.")
def formulas() -> str:
    return json.dumps({
        "engagements": "likes + comments + shares + saves",
        "er_by_views": "engagements / views x 100",
        "er_by_followers": "engagements / followers x 100",
        "cpm": "fee / expected views x 1000",
        "cpe": "fee / engagements",
        "usage_fee": "base fee x usage % per month x months",
        "effective_cpm": "(fee + usage + exclusivity) / expected views x 1000",
        "max_base_fee": "(target_cpm x views / 1000 - exclusivity) / (1 + usage% x months)",
        "break_even_sales": "ceil(contract cost / (net order value x margin %))",
    }, indent=2)


@mcp.prompt(title="Review a creator quote", description="Check a creator's quote against recent post stats and your target CPM.")
def review_creator_quote(quote_text: str, post_stats_text: str, target_cpm: str) -> str:
    return (
        f"You help a brand judge a creator quote. Quote: {quote_text}\nRecent posts: {post_stats_text}\nTarget CPM: {target_cpm}\n\n"
        "1. Call calculate_engagement_rate on the posts.\n"
        "2. Call evaluate_creator_quote with the median views, including usage and exclusivity.\n"
        "3. If above target, call draft_counter_offer with max_base_fee_at_target_cpm and show the draft; never claim it was sent.\n"
        "4. Summarise warnings and the single recommendation."
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
