"""Protocol-level tests through a real MCP client (in-process transport)."""
import pytest
from mcp import Client

from vic_export_quote.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_lists_five_tools_with_schemas_and_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        names = {t.name for t in tools}
        assert names == {"calculate_export_quote", "price_by_quantity", "plan_container_loading", "explain_incoterm", "convert_currency"}
        for t in tools:
            assert t.description and len(t.description) > 60
            assert t.output_schema
            assert t.annotations and t.annotations.read_only_hint is True
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p} has no description"


async def test_quote_call_structured():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_export_quote", {"unit_cost": 5, "quantity": 1000, "target_margin_pct": 20, "origin_fixed_costs": 300})
        assert not r.is_error
        assert r.structured_content["ladder"][1]["total"] == 6625.0


async def test_invalid_input_is_tool_error_not_crash():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_export_quote", {"unit_cost": -1, "quantity": 10, "target_margin_pct": 20})
        assert r.is_error
        r = await c.call_tool("explain_incoterm", {"code": "DAT"})
        assert r.is_error and "DPU" in r.content[0].text


async def test_incoterm_container_suggestion():
    async with Client(mcp) as c:
        r = await c.call_tool("explain_incoterm", {"code": "CIF", "transport": "sea_container"})
        assert "CIP" in r.structured_content["suggestion"]


async def test_resource_and_prompt():
    async with Client(mcp) as c:
        res = (await c.list_resources()).resources
        assert any(str(x.uri) == "incoterms://2020" for x in res)
        prompts = (await c.list_prompts()).prompts
        assert any(p.name == "quotation_reply" for p in prompts)


async def test_incoterm_tolerates_case_and_spaces():
    async with Client(mcp) as c:
        r = await c.call_tool("explain_incoterm", {"code": " fob "})
        assert not r.is_error and r.structured_content["code"] == "FOB"
