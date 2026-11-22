"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_cashflow_forecast.server import mcp

pytestmark = pytest.mark.anyio

ITEMS = [
    {"label": "Acme invoice", "amount": 3000, "direction": "in", "date": "2026-01-14"},
    {"label": "Rent", "amount": 1000, "direction": "out", "date": "2026-01-05", "repeat": "monthly"},
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == {"forecast_cashflow", "calculate_runway", "stress_test_cashflow"}
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            assert t.annotations.read_only_hint is True
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p}"


async def test_forecast_call():
    async with Client(mcp) as c:
        r = await c.call_tool("forecast_cashflow", {"start": "2026-01-05", "opening_balance": 500, "items": ITEMS, "weeks": 6})
        s = r.structured_content
        # rent Jan 5 (wk1) -1000 -> -500; Acme Jan 14 (wk2) +3000 -> 2500; rent Feb 5 (wk5) -> 1500
        assert [w["closing_balance"] for w in s["weeks"]] == [-500, 2500, 2500, 2500, 1500, 1500]
        assert s["first_negative_week"] == 1


async def test_stress_call():
    async with Client(mcp) as c:
        r = await c.call_tool("stress_test_cashflow", {"start": "2026-01-05", "opening_balance": 1500, "items": ITEMS, "weeks": 6,
                                                       "inflow_delay_days": 30})
        s = r.structured_content
        # base never negative (500, 2500...); Acme moves to Feb 13 (wk6): wk5 rent Feb 5 -> 1500-1000-1000 = -500
        assert s["base"]["first_negative_week"] == 0
        assert s["stressed"]["first_negative_week"] == 5 and s["extra_negative_weeks"] == 1


async def test_runway_call_and_errors():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_runway", {"cash": 6000, "monthly_expenses": 2000, "monthly_income": 500})
        assert r.structured_content["runway_months"] == 4.0
        bad = await c.call_tool("calculate_runway", {"cash": 6000, "monthly_expenses": 0})
        assert bad.is_error
        bad = await c.call_tool("forecast_cashflow", {"start": "2026-01-05", "opening_balance": 0, "items": [
            {"label": "x", "amount": 1, "direction": "in", "date": "2000-01-01", "repeat": "weekly", "until": "2090-01-01"}], "weeks": 52})
        assert bad.is_error is False
