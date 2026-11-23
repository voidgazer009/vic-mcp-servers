"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_caption_linter.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == {"count_post_text", "lint_post_text", "find_fitting_platforms", "list_platform_limits"}
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            assert t.annotations.read_only_hint is True
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p}"


async def test_count_structured():
    async with Client(mcp) as c:
        r = await c.call_tool("count_post_text", {"text": "Hi 你好 😀 https://a.co/x", "platforms": ["x", "bluesky"]})
        assert not r.is_error
        rows = {x["platform"]: x for x in r.structured_content["counts"]}
        assert rows["x"]["count"] == 34 and rows["x"]["remaining"] == 246
        assert rows["bluesky"]["count"] == 22


async def test_lint_and_errors():
    async with Client(mcp) as c:
        r = await c.call_tool("lint_post_text", {"text": "x" * 301, "platforms": ["bluesky"]})
        assert r.structured_content["ok"] is False
        bad = await c.call_tool("lint_post_text", {"text": "hi", "platforms": ["myspace"]})
        assert bad.is_error
        limits = await c.call_tool("list_platform_limits", {})
        assert len(limits.structured_content["limits"]) >= 10
