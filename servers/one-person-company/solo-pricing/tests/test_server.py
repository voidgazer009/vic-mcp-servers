"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_solo_pricing.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == {"calculate_hourly_rate", "quote_fixed_project", "gross_up_for_fees", "analyze_discount", "check_real_hourly_rate"}
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            assert t.annotations.read_only_hint is True
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p}"


async def test_rate_structured():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_hourly_rate", {"target_net_income": 60000, "tax_rate_pct": 25, "annual_expenses": 6000, "buffer_pct": 0})
        assert not r.is_error and r.structured_content["hourly_rate"] == 77.9


async def test_fee_and_discount_calls():
    async with Client(mcp) as c:
        r = await c.call_tool("gross_up_for_fees", {"net_wanted": 100, "fee_pct": 2.9, "fixed_fee": 0.3})
        assert r.structured_content["invoice_amount"] == 103.3
        r = await c.call_tool("analyze_discount", {"price": 100, "unit_variable_cost": 40, "discount_pct": 10})
        assert r.structured_content["required_volume_increase_pct"] == 20.0


async def test_invalid_input_is_tool_error():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_hourly_rate", {"target_net_income": -5, "tax_rate_pct": 25})
        assert r.is_error
        r = await c.call_tool("analyze_discount", {"price": 10, "unit_variable_cost": 12, "discount_pct": 5})
        assert r.is_error and "margin" in r.content[0].text
