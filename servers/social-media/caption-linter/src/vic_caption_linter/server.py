"""Vic Caption Linter MCP server: count and lint one post against each platform's real limits.

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
from .logic import CaptionInputError

SITE = "https://github.com/voidgazer009/vic-mcp-servers/tree/main/servers/social-media/caption-linter"

mcp = MCPServer(
    name="vic-caption-linter",
    title="Vic Caption Linter",
    description="Count and lint one social post against each platform's real limits: X weighted count, Bluesky graphemes, Threads, Mastodon, Instagram, TikTok, YouTube bytes.",
    version=__version__,
    website_url=SITE,
    instructions=(
        "Use before publishing or cross-posting a caption, title or description. Platforms count differently (X weights CJK and emoji 2 and links 23; "
        "Bluesky counts graphemes; YouTube counts bytes), so never count by eye or with a word processor. Pass the exact final text and the platform ids "
        "the user posts to. Show every error and warning. Fold positions are measured by others, not published; say so. Mastodon's limit is per server: ask or pass it."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

Text = Annotated[str, Field(min_length=1, max_length=100000, description="The exact final post text, including hashtags, links and line breaks.")]
Plats = Annotated[list[str], Field(min_length=1, max_length=12, description="Platform ids: x, bluesky, threads, mastodon, linkedin, instagram, tiktok, youtube_title, youtube_description, pinterest_title, pinterest_description, facebook. Aliases like twitter, ig, yt_title work.")]


class PlatformCount(BaseModel):
    platform: str = Field(description="Platform id.")
    name: str = Field(description="Human name of the field.")
    count: int = Field(description="Length in the platform's own unit.")
    limit: int | None = Field(description="Maximum, null when the platform documents none.")
    unit: str = Field(description="What the count is measured in.")
    remaining: int | None = Field(description="limit minus count; negative when over.")
    fits: bool = Field(description="True when count is within the limit.")


class CountResult(BaseModel):
    counts: list[PlatformCount] = Field(description="One row per platform, in request order.")
    warnings: list[str] = Field(description="Show to the user.")


class Issue(BaseModel):
    severity: str = Field(description="error, warning or info.")
    platform: str | None = Field(description="Platform id, null for issues that apply everywhere.")
    message: str = Field(description="What is wrong and how to fix it.")


class LintResult(BaseModel):
    ok: bool = Field(description="True when there is no error-level issue.")
    error_count: int = Field(description="Number of error-level issues.")
    counts: list[PlatformCount] = Field(description="Counts per platform.")
    issues: list[Issue] = Field(description="All findings.")
    hashtags: list[str] = Field(description="Hashtags found (links' #fragments excluded).")
    links: list[str] = Field(description="Links found.")
    warnings: list[str] = Field(description="Show to the user.")


class FitResult(BaseModel):
    fits: list[str] = Field(description="Platform ids where the text fits as written.")
    too_long: list[dict[str, int | str]] = Field(description="Platforms it does not fit, with 'over_by' characters to cut.")
    warnings: list[str] = Field(description="Show to the user.")


class LimitRow(BaseModel):
    platform: str = Field(description="Platform id.")
    name: str = Field(description="Field name.")
    limit: int | None = Field(description="Maximum or null.")
    unit: str = Field(description="Counting unit.")
    rule: str = Field(description="How it is counted and extra rules.")
    source: str = Field(description="Official page the rule comes from.")


class LimitsResult(BaseModel):
    limits: list[LimitRow] = Field(description="All platform fields.")
    checked: str = Field(description="Date the rules were checked against sources.")


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except CaptionInputError as e:
        raise ToolError(str(e)) from e


def _warn(rows: list[dict], premium: bool, mastodon_limit: int) -> list[str]:
    w = ["Counts follow each platform's published rule as of 2026-11-23; the in-app composer can differ slightly, so re-check posts that sit within a few characters of a limit."]
    if any(r["platform"] == "mastodon" for r in rows) and mastodon_limit == 500:
        w.append("Mastodon: 500 is only the default; pass mastodon_limit for the server you post to.")
    if any(r["platform"] == "x" for r in rows) and premium:
        w.append("X Premium long posts cannot be scheduled on the web and only the first 280 characters notify mentions.")
    return w


@mcp.tool(title="Count a post for each platform", annotations=READ_ONLY)
def count_post_text(
    text: Text,
    platforms: Plats,
    x_premium: Annotated[bool, Field(description="Use X's 25,000 limit for a Premium account instead of 280.")] = False,
    mastodon_limit: Annotated[int, Field(ge=1, le=100000, description="The server's max_characters; default 500.")] = 500,
    content_warning: Annotated[str, Field(max_length=2000, description="Mastodon content warning text; it counts toward the limit.")] = "",
) -> CountResult:
    """Measure one text the way each platform counts it (X weighted with links 23 and CJK/emoji 2, Bluesky graphemes, Threads emoji bytes, Mastodon, TikTok UTF-16, YouTube bytes) and say how many characters remain. Use to check a caption before posting or cross-posting."""
    rows = _guard(logic.count_post, text, platforms, x_premium=x_premium, mastodon_limit=mastodon_limit, content_warning=content_warning)
    return CountResult(counts=[PlatformCount(**r) for r in rows], warnings=_warn(rows, x_premium, mastodon_limit))


@mcp.tool(title="Lint a post before publishing", annotations=READ_ONLY)
def lint_post_text(
    text: Text,
    platforms: Plats,
    x_premium: Annotated[bool, Field(description="Use X's 25,000 limit for a Premium account.")] = False,
    mastodon_limit: Annotated[int, Field(ge=1, le=100000, description="The server's max_characters; default 500.")] = 500,
    content_warning: Annotated[str, Field(max_length=2000, description="Mastodon content warning text.")] = "",
) -> LintResult:
    """Full pre-publish check: over-limit per platform, Instagram hashtag cap (Help Center 5, API 30), Threads link cap, YouTube forbidden < >, Bluesky byte cap, CJK double weight on X, unfilled placeholders like {{name}}, glued hashtags, and where the see-more fold falls."""
    r = _guard(logic.lint_post, text, platforms, x_premium=x_premium, mastodon_limit=mastodon_limit, content_warning=content_warning)
    return LintResult(ok=r["ok"], error_count=r["error_count"], counts=[PlatformCount(**c) for c in r["counts"]],
                      issues=[Issue(**i) for i in r["issues"]], hashtags=r["hashtags"], links=r["links"],
                      warnings=_warn(r["counts"], x_premium, mastodon_limit))


@mcp.tool(title="Which platforms does this text fit", annotations=READ_ONLY)
def find_fitting_platforms(
    text: Text,
    x_premium: Annotated[bool, Field(description="Use X's 25,000 limit.")] = False,
) -> FitResult:
    """Check one text against every supported platform at once and list where it fits as written and by how many characters it is too long elsewhere. Use to decide which version to write first when one idea goes to many networks."""
    r = _guard(logic.fit_platforms, text, x_premium=x_premium)
    return FitResult(fits=r["fits"], too_long=r["too_long"], warnings=_warn([], x_premium, 500))


@mcp.tool(title="List platform limits and sources", annotations=READ_ONLY)
def list_platform_limits() -> LimitsResult:
    """Return every limit this server enforces, how each platform counts, and the official page each rule comes from. Use to explain a result or to cite the source for a limit."""
    rows = [LimitRow(platform=k, name=v["name"], limit=v["limit"], unit=v["unit"], rule=v["rule"], source=v["source"]) for k, v in logic.PLATFORMS.items()]
    return LimitsResult(limits=rows, checked="2026-11-23")


@mcp.resource("caption://limits", name="caption-limits", title="Platform limits", mime_type="application/json",
              description="The limits, counting rules and official sources this server uses.")
def limits_resource() -> str:
    return json.dumps(logic.PLATFORMS, indent=2, ensure_ascii=False)


@mcp.prompt(title="Adapt one post to many platforms", description="Rewrite a draft for each platform and verify every version with the linter.")
def adapt_post(draft: str, platforms: str) -> str:
    return (
        f"Draft:\n\n---\n{draft}\n---\n\nPlatforms: {platforms}\n\n"
        "1. Call find_fitting_platforms on the draft.\n2. Rewrite it for each platform that is too long, hook in the first line.\n"
        "3. Call lint_post_text on every version and fix each error.\n4. Show the final versions with their counts and warnings."
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
