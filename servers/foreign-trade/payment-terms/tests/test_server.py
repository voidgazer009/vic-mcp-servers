"""Protocol-level tests through a real MCP client (in-process)."""
import pytest
from mcp import Client

from vic_payment_terms.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_schemas_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == {"explain_payment_term", "compare_payment_terms", "recommend_payment_terms", "check_payment_clause"}
        for t in tools:
            assert len(t.description) > 60 and t.output_schema
            a = t.annotations
            assert a.read_only_hint is True and a.destructive_hint is False and a.idempotent_hint is True and a.open_world_hint is False
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p}"


async def test_compare_structured():
    async with Client(mcp) as c:
        r = await c.call_tool("compare_payment_terms", {"order_value": 10000, "cost_pct": 70, "production_days": 30, "shipping_days": 25, "annual_cost_of_capital_pct": 8, "terms": ["OA"]})
        assert not r.is_error
        assert r.structured_content["rows"][0]["financing_cost"] == 138.08


async def test_errors_are_tool_errors():
    async with Client(mcp) as c:
        r = await c.call_tool("explain_payment_term", {"code": "COD"})
        assert r.is_error and "Valid" in r.content[0].text
        r = await c.call_tool("compare_payment_terms", {"order_value": -5, "cost_pct": 70, "production_days": 30, "shipping_days": 25, "annual_cost_of_capital_pct": 8})
        assert r.is_error


async def test_clause_and_recommend():
    async with Client(mcp) as c:
        r = await c.call_tool("check_payment_clause", {"text": "Balance 70% against copy of B/L, USD"})
        assert any(f["rule"] == "COPY_BL_BALANCE" for f in r.structured_content["findings"])
        r = await c.call_tool("recommend_payment_terms", {"order_value_usd": 3000, "buyer_history": "new", "country_risk": "low", "buyer_requests": "DA"})
        assert r.structured_content["recommendations"][0]["term"] == "TT_DEPOSIT"


async def test_resource_prompt():
    async with Client(mcp) as c:
        assert any(str(x.uri) == "payment-terms://matrix" for x in (await c.list_resources()).resources)
        assert any(p.name == "credit_terms_reply" for p in (await c.list_prompts()).prompts)
