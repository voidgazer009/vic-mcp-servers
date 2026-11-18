"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_invoice_aging.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == {"calculate_due_date", "age_invoices", "calculate_late_interest", "draft_payment_reminder"}
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            assert t.annotations.read_only_hint is True
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p}"


async def test_due_and_interest_calls():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_due_date", {"invoice_date": "2026-01-15", "net_days": 30, "end_of_month": True})
        assert r.structured_content["due_date"] == "2026-03-02"
        r = await c.call_tool("calculate_late_interest", {"principal": 10000, "due_date": "2026-01-31", "paid_or_as_of": "2026-03-02", "regime": "eu", "reference_rate_pct": 2})
        assert r.structured_content["total_claim"] == 122.19


async def test_aging_call():
    async with Client(mcp) as c:
        r = await c.call_tool("age_invoices", {"as_of": "2026-11-18", "invoices": [
            {"invoice_id": "A", "client": "X", "amount": 1000, "due_date": "2026-10-01"}]})
        assert r.structured_content["overdue_invoices"][0]["days_overdue"] == 48


async def test_invalid_input_is_tool_error():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_late_interest", {"principal": 100, "due_date": "2026-01-01", "paid_or_as_of": "2026-02-01", "regime": "eu"})
        assert r.is_error
        r = await c.call_tool("age_invoices", {"as_of": "2026-11-18", "invoices": [{"invoice_id": "A", "client": "X", "amount": 10, "paid_amount": 20, "due_date": "2026-10-01"}]})
        assert r.is_error


async def test_reminder_is_draft_and_resource_prompt():
    async with Client(mcp) as c:
        r = await c.call_tool("draft_payment_reminder", {"client": "Ann", "invoice_id": "I-1", "open_amount": 500, "days_overdue": 70, "sender": "Vic"})
        assert r.structured_content["draft_only"] is True and r.structured_content["stage"] == "final"
        assert (await c.list_resources()).resources and (await c.list_prompts()).prompts
