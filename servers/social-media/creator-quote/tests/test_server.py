"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_creator_quote.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == {"calculate_engagement_rate", "evaluate_creator_quote", "calculate_payback_ceiling", "draft_counter_offer"}
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            assert t.annotations.read_only_hint is True
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p}"


async def test_evaluate_call():
    async with Client(mcp) as c:
        r = await c.call_tool("evaluate_creator_quote", {"fee": 800, "avg_views": 12000, "target_cpm": 50})
        assert r.structured_content["base_cpm"] == 66.67
        assert r.structured_content["max_base_fee_at_target_cpm"] == 600.0


async def test_payback_and_engagement_calls():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_payback_ceiling", {"contract_cost": 1000, "net_order_value": 50, "margin_pct": 40})
        assert r.structured_content["sales_to_break_even"] == 50
        r = await c.call_tool("calculate_engagement_rate", {"posts": [{"views": 1000, "likes": 80, "comments": 10, "shares": 5, "saves": 5}]})
        assert r.structured_content["median_er_by_views_pct"] == 10.0


async def test_invalid_input_is_tool_error():
    async with Client(mcp) as c:
        res = await c.call_tool("draft_counter_offer", {"creator": "A", "brand": "B", "sender": "C", "deliverables": 1, "current_fee": 100, "proposed_fee": 150})
        assert res.is_error is True
