"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_demurrage.server import mcp

pytestmark = pytest.mark.anyio
TIERS = [{"from_day": 1, "rate": 150}, {"from_day": 4, "rate": 300}]


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == {"find_last_free_day", "calculate_charges", "compare_exit_dates", "audit_invoice"}
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            a = t.annotations
            assert a.read_only_hint is True and a.destructive_hint is False and a.idempotent_hint is True and a.open_world_hint is False
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p}"


async def test_calculate_us_deadline():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_charges", {"kind": "demurrage", "start_date": "2026-11-16", "end_date": "2026-11-25", "free_days": 5, "tiers": TIERS, "us_trade": True})
        s = r.structured_content
        assert not r.is_error and s["total"] == 1050 and s["fmc_invoice_deadline"] == "2026-12-25" and s["warnings"]


async def test_last_free_day_days_left():
    async with Client(mcp) as c:
        r = await c.call_tool("find_last_free_day", {"start_date": "2026-11-16", "free_days": 5, "today": "2026-11-18"})
        assert r.structured_content["last_free_day"] == "2026-11-20" and r.structured_content["days_left"] == 2


async def test_compare_and_audit():
    async with Client(mcp) as c:
        r = await c.call_tool("compare_exit_dates", {"kind": "demurrage", "start_date": "2026-11-16", "candidate_end_dates": ["2026-11-20", "2026-11-23"], "free_days": 5, "tiers": TIERS})
        o = r.structured_content["options"]
        assert o[0]["total"] == 0 and o[1]["total"] == 150 * 3 and r.structured_content["cheapest_end_date"] == "2026-11-20"
        r = await c.call_tool("audit_invoice", {"kind": "demurrage", "start_date": "2026-11-16", "end_date": "2026-11-25", "free_days": 5, "tiers": TIERS, "billed_amount": 1350})
        s = r.structured_content
        assert s["your_rule_difference"] == 300 and "started a day earlier=True" in s["verdict"] and "DRAFT" in s["draft_dispute_note"]


async def test_errors_are_tool_errors():
    async with Client(mcp) as c:
        for args in ({"kind": "demurrage", "start_date": "2026-11-25", "end_date": "2026-11-16", "free_days": 5, "tiers": TIERS},
                     {"kind": "demurrage", "start_date": "2026-02-30", "end_date": "2026-03-16", "free_days": 5, "tiers": TIERS},
                     {"kind": "demurrage", "start_date": "2026-11-16", "end_date": "2026-11-25", "free_days": 5, "tiers": [{"from_day": 3, "rate": 1}]}):
            assert (await c.call_tool("calculate_charges", args)).is_error
