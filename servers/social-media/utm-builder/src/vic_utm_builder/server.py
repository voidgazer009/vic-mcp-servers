"""Vic UTM Builder MCP server: build, lint and classify UTM campaign links for GA4.

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
from .logic import UtmInputError

SITE = "https://github.com/voidgazer009/vic-mcp-servers/tree/main/servers/social-media/utm-builder"

mcp = MCPServer(
    name="vic-utm-builder",
    title="Vic UTM Builder",
    description="Build, lint and classify UTM campaign links for GA4: consistent naming, channel prediction, batch links per platform.",
    version=__version__,
    website_url=SITE,
    instructions=(
        "Use these tools whenever a marketer, creator or founder needs tracking links for posts, ads, emails or QR codes, "
        "or wants an existing link checked. GA4 UTM values are case sensitive, so always keep one lower-case naming "
        "convention. Ask for the destination URL and campaign name instead of inventing them. Show every warning, "
        "especially the predicted GA4 channel. The channel prediction is approximate; say so."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class BuiltUrl(BaseModel):
    url: str = Field(description="The tagged URL, ready to use.")
    parameters: dict[str, str] = Field(description="UTM parameters that were added.")
    changes: list[str] = Field(description="Values that were cleaned automatically, as 'name: old -> new'.")
    predicted_channel: str = Field(description="Approximate GA4 default channel group this traffic lands in.")
    channel_reason: str = Field(description="Which GA4 rule produced the channel.")
    warnings: list[str] = Field(description="Show to the user.")


class Issue(BaseModel):
    severity: str = Field(description="error, warning or info.")
    message: str = Field(description="What is wrong and how to fix it.")


class LintResult(BaseModel):
    valid: bool = Field(description="True when there is no error-level issue.")
    error_count: int = Field(description="Number of error-level issues.")
    issues: list[Issue] = Field(description="All findings, errors first as found.")
    parameters: dict[str, str] = Field(description="UTM parameters found in the URL.")
    predicted_channel: str | None = Field(description="Approximate GA4 channel, null when source or medium is missing.")


class ChannelResult(BaseModel):
    channel: str = Field(description="Approximate GA4 default channel group.")
    reason: str = Field(description="Which rule matched.")
    warnings: list[str] = Field(description="Show to the user.")


class Target(BaseModel):
    platform: str = Field(min_length=1, max_length=40, description="Platform key such as facebook, linkedin, youtube, newsletter, wechat, xiaohongshu, google_ads; unknown names need source and medium.")
    content: str | None = Field(default=None, max_length=100, description="Optional utm_content to tell placements apart, e.g. carousel_a.")
    source: str | None = Field(default=None, max_length=100, description="Override the preset utm_source.")
    medium: str | None = Field(default=None, max_length=100, description="Override the preset utm_medium, e.g. social for organic posts.")


class PlatformLink(BaseModel):
    platform: str = Field(description="Normalised platform key.")
    url: str = Field(description="Tagged URL for this platform.")
    predicted_channel: str = Field(description="Approximate GA4 channel.")
    warnings: list[str] = Field(description="Per-link warnings.")


class BatchResult(BaseModel):
    links: list[PlatformLink] = Field(description="One link per target, in order.")
    warnings: list[str] = Field(description="Show to the user.")


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except UtmInputError as e:
        raise ToolError(str(e)) from e


@mcp.tool(title="Build a UTM-tagged URL", annotations=READ_ONLY)
def build_utm_url(
    url: Annotated[str, Field(min_length=8, max_length=2000, description="Destination page, starting with http:// or https://. Existing query parameters and #fragment are kept.")],
    source: Annotated[str, Field(min_length=1, max_length=100, description="utm_source: where the traffic comes from, e.g. linkedin, newsletter, google.")],
    medium: Annotated[str, Field(min_length=1, max_length=100, description="utm_medium: the channel type, e.g. cpc, email, social, paid_social, referral.")],
    campaign: Annotated[str, Field(min_length=1, max_length=100, description="utm_campaign: one stable campaign name, e.g. spring_sale_2026.")],
    id: Annotated[str | None, Field(default=None, max_length=100, description="utm_id: campaign ID matching imported cost data. Recommended by Google.")] = None,
    term: Annotated[str | None, Field(default=None, max_length=100, description="utm_term: paid keyword.")] = None,
    content: Annotated[str | None, Field(default=None, max_length=100, description="utm_content: tells creatives or links apart, e.g. toplink.")] = None,
    source_platform: Annotated[str | None, Field(default=None, max_length=100, description="utm_source_platform: the buying or managing platform, e.g. Search Ads 360.")] = None,
    normalize: Annotated[bool, Field(description="Lower-case values and replace spaces and punctuation with _ so GA4 does not split rows. Turn off only to keep exact values.")] = True,
) -> BuiltUrl:
    """Add UTM parameters to a destination URL: cleans values to one lower-case convention, keeps existing query and fragment, replaces old UTM tags, predicts the GA4 default channel and warns about risks. Use when someone needs one tracking link for a post, ad, email or QR code."""
    return BuiltUrl(**_guard(logic.build_url, url, source, medium, campaign, id, term, content, source_platform, normalize))


@mcp.tool(title="Lint an existing UTM link", annotations=READ_ONLY)
def lint_utm_url(
    url: Annotated[str, Field(min_length=8, max_length=4000, description="A full link that already carries UTM parameters, starting with http:// or https://.")],
) -> LintResult:
    """Check a tagged link for the mistakes that break GA4 reports: missing source, medium or campaign, upper-case or spaced values, misspelled parameter names, duplicates, tags after a # fragment, unfilled placeholders, and a source/medium pair that lands in Unassigned. Use before launching or when a report looks split."""
    return LintResult(**_guard(logic.lint_url, url))


@mcp.tool(title="Predict the GA4 channel for a source and medium", annotations=READ_ONLY)
def predict_ga4_channel(
    source: Annotated[str, Field(min_length=1, max_length=100, description="utm_source value, e.g. linkedin.")],
    medium: Annotated[str, Field(min_length=1, max_length=100, description="utm_medium value, e.g. cpc or paid_social.")],
    campaign: Annotated[str | None, Field(default=None, max_length=100, description="utm_campaign value; some rules look at it (shopping, cross-network).")] = None,
) -> ChannelResult:
    """Tell which GA4 default channel group (Paid Social, Organic Social, Email, Referral, Unassigned and so on) a manually tagged source and medium will land in, following Google's documented rule order. Use to pick a medium that reports where you expect. Approximate: Google's source lists are longer."""
    r = logic.predict_channel(source, medium, campaign)
    return ChannelResult(**r)


@mcp.tool(title="Build one campaign's links for many platforms", annotations=READ_ONLY)
def build_campaign_links(
    url: Annotated[str, Field(min_length=8, max_length=2000, description="Destination page, starting with http:// or https://.")],
    campaign: Annotated[str, Field(min_length=1, max_length=100, description="One campaign name shared by every link.")],
    targets: Annotated[list[Target], Field(min_length=1, max_length=30, description="Platforms to tag, each with optional content, source and medium overrides.")],
    utm_id: Annotated[str | None, Field(default=None, max_length=100, description="utm_id shared by every link.")] = None,
    normalize: Annotated[bool, Field(description="Clean values to lower case with underscores.")] = True,
) -> BatchResult:
    """Create a consistent set of tagged links for one campaign across platforms (facebook, linkedin, youtube, newsletter, wechat, xiaohongshu, google ads and more) using standard source and medium presets, so naming never drifts between team members. Use when launching a campaign on several channels at once."""
    return BatchResult(**_guard(logic.campaign_links, url, campaign, [t.model_dump() for t in targets], utm_id, normalize))


@mcp.resource("utm://naming-convention", name="utm-naming-convention", title="UTM naming convention", mime_type="application/json",
              description="The naming rules and platform presets this server uses.")
def convention() -> str:
    return json.dumps({
        "rules": ["lower case only", "words separated by _", "one stable value per platform and per campaign",
                  "always set utm_source, utm_medium, utm_campaign; add utm_id when cost data is imported",
                  "never tag links between pages of your own site"],
        "presets_source_medium": {k: list(v) for k, v in logic.PLATFORM_PRESETS.items()},
    }, indent=2)


@mcp.prompt(title="Plan tracking for a campaign", description="Turn a campaign brief into a naming scheme and a full set of tagged links.")
def plan_campaign_tracking(brief: str, landing_url: str) -> str:
    return (
        f"You are a marketing analytics assistant. Campaign brief:\n\n---\n{brief}\n---\n\nLanding page: {landing_url}\n\n"
        "1. Propose one lower-case campaign name and a utm_id.\n"
        "2. List the platforms and placements; call build_campaign_links.\n"
        "3. For any custom source/medium call predict_ga4_channel.\n"
        "4. Show the links in a table with the predicted channel and every warning."
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
