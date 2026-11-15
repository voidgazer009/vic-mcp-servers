"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_utm_builder.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == {"build_utm_url", "lint_utm_url", "predict_ga4_channel", "build_campaign_links"}
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            assert t.annotations.read_only_hint is True
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p}"


async def test_build_structured():
    async with Client(mcp) as c:
        r = await c.call_tool("build_utm_url", {"url": "https://example.com/", "source": "LinkedIn", "medium": "Paid Social", "campaign": "Launch"})
        assert not r.is_error
        assert r.structured_content["url"] == "https://example.com/?utm_source=linkedin&utm_medium=paid_social&utm_campaign=launch"
        assert r.structured_content["predicted_channel"] == "Paid Social"


async def test_batch_and_lint():
    async with Client(mcp) as c:
        r = await c.call_tool("build_campaign_links", {"url": "https://example.com/", "campaign": "launch", "targets": [{"platform": "youtube"}, {"platform": "wechat", "medium": "social"}]})
        assert len(r.structured_content["links"]) == 2
        r = await c.call_tool("lint_utm_url", {"url": "https://example.com/?utm_source=a"})
        assert r.structured_content["valid"] is False


async def test_invalid_input_is_tool_error():
    async with Client(mcp) as c:
        r = await c.call_tool("build_utm_url", {"url": "example.com/page", "source": "a", "medium": "b", "campaign": "c"})
        assert r.is_error and "http" in r.content[0].text
        r = await c.call_tool("build_campaign_links", {"url": "https://example.com/", "campaign": "c", "targets": [{"platform": "nopenet"}]})
        assert r.is_error and "Known" in r.content[0].text
        r = await c.call_tool("predict_ga4_channel", {"source": "", "medium": "x"})
        assert r.is_error
