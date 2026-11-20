"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_sample_policy.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


NAMES = {"quote_sample_package", "sample_roi", "first_order_credit", "triage_sample_request", "draft_sample_terms"}


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == NAMES
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            a = t.annotations
            assert a.read_only_hint is True and a.destructive_hint is False and a.idempotent_hint is True and a.open_world_hint is False
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description") or "$ref" in spec or "items" in spec, f"{t.name}.{p}"


async def test_quote_structured():
    async with Client(mcp) as c:
        r = await c.call_tool("quote_sample_package", {"items": [{"name": "A", "qty": 2, "unit_cost": 10}], "freight": 40})
        assert not r.is_error
        rows = {x["tier"]: x for x in r.structured_content["rows"]}
        assert rows["FREE_FREIGHT_CREDIT"]["your_cash_outlay"] == 60  # 2*10 + 40 freight


async def test_triage_and_draft_flow():
    async with Client(mcp) as c:
        r = await c.call_tool("triage_sample_request", {"email_type": "lookalike", "specs_given": False, "target_qty_given": False})
        assert r.structured_content["tier"] == "FULL_PAID" and r.structured_content["red_flags"]
        d = await c.call_tool("draft_sample_terms", {"tier": "FREE_COLLECT"})
        assert "collect" in d.structured_content["english"]


async def test_errors_are_tool_errors():
    async with Client(mcp) as c:
        r = await c.call_tool("first_order_credit", {"sample_fee_paid": 10, "prep_fee_paid": 0, "freight_paid": 0, "creditable": ["sample_fee"],
                                                     "order_value": 100, "sample_date": "2026-99-99", "order_date": "2026-01-01"})
        assert r.is_error and "YYYY-MM-DD" in r.content[0].text
        r = await c.call_tool("draft_sample_terms", {"tier": "NO_SAMPLE"})
        assert r.is_error
        r = await c.call_tool("sample_roi", {"your_cash_outlay": 1, "buyer_pays_you_now": 0, "credit_on_first_order": 0, "expected_order_value": -1, "gross_margin_pct": 10, "conversion_pct": 5})
        assert r.is_error
