"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_transport_ids.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == {"validate_container_numbers", "validate_awb_numbers", "decode_container_size_type", "extract_and_validate_ids"}
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            a = t.annotations
            assert a.read_only_hint is True and a.destructive_hint is False and a.idempotent_hint is True and a.open_world_hint is False
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p}"


async def test_container_structured():
    async with Client(mcp) as c:
        r = await c.call_tool("validate_container_numbers", {"numbers": ["CSQU3054383", "CSQU3054384"]})
        assert not r.is_error
        s = r.structured_content
        assert s["valid_count"] == 1 and s["results"][1]["corrected"] == "CSQU3054383" and s["warnings"]


async def test_errors_are_tool_errors():
    async with Client(mcp) as c:
        r = await c.call_tool("validate_awb_numbers", {"numbers": []})
        assert r.is_error
        r = await c.call_tool("decode_container_size_type", {"code": "ab"})
        assert r.is_error
        r = await c.call_tool("extract_and_validate_ids", {"text": "   "})
        assert r.is_error


async def test_resource_prompt():
    async with Client(mcp) as c:
        assert (await c.list_resources()).resources
        assert (await c.list_prompts()).prompts
