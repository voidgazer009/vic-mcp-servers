"""Protocol-level tests through a real MCP client (in-process transport)."""
import pytest
from mcp import Client

from vic_billable_weight.server import mcp

pytestmark = pytest.mark.anyio

TOOLS = {"calculate_chargeable_weight", "check_express_surcharges", "audit_weight_adjustment",
         "optimize_box_size", "compare_freight_options"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_lists_five_tools_with_schemas_and_annotations():
    async with Client(mcp) as c:
        tools = (await c.list_tools()).tools
        assert {t.name for t in tools} == TOOLS
        for t in tools:
            assert t.description and len(t.description) > 60
            assert t.output_schema
            a = t.annotations
            assert a.read_only_hint is True and a.destructive_hint is False and a.open_world_hint is False
            for p, spec in t.input_schema["properties"].items():
                assert spec.get("description"), f"{t.name}.{p} has no description"


async def test_chargeable_call_structured():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_chargeable_weight", {"pieces": [{"length": 60, "width": 40, "height": 40, "weight": 7}], "carrier_profile": "ups_express"})
        assert not r.is_error
        assert r.structured_content["billable"] == 19.5


async def test_invalid_inputs_are_tool_errors():
    async with Client(mcp) as c:
        r = await c.call_tool("calculate_chargeable_weight", {"pieces": [{"length": -1, "width": 40, "height": 40, "weight": 7}], "carrier_profile": "ups_express"})
        assert r.is_error
        r = await c.call_tool("calculate_chargeable_weight", {"pieces": [{"length": 60, "width": 40, "height": 40, "weight": 7}], "carrier_profile": "custom"})
        assert r.is_error and "divisor_override" in r.content[0].text
        r = await c.call_tool("calculate_chargeable_weight", {"pieces": [{"length": 60, "width": 40, "height": 40, "weight": 7}], "carrier_profile": "ups_express", "divisor_override": 139})
        assert r.is_error
        r = await c.call_tool("audit_weight_adjustment", {"adjustments": [{"tracking": "1Z1", "declared_dims": [60, 40, 40], "declared_weight": 7}], "carrier_profile": "ups_express"})
        assert r.is_error and "nothing to audit" in r.content[0].text
        r = await c.call_tool("optimize_box_size", {"length": 60, "width": 40, "height": 40, "weight": 7, "carrier_profile": "ups_express", "product_length": 50})
        assert r.is_error


async def test_audit_draft_and_totals():
    async with Client(mcp) as c:
        r = await c.call_tool("audit_weight_adjustment", {
            "adjustments": [
                {"tracking": "1ZA", "declared_dims": [46, 18, 7], "declared_weight": 16, "audited_dims": [48, 21, 9], "audited_weight": 26},
                {"tracking": "1ZB", "declared_dims": [11, 8, 6], "declared_weight": 1.875, "audited_weight": 28},
            ],
            "carrier_profile": "us_domestic_daily", "dimension_unit": "in", "weight_unit": "lb", "rate_per_unit": 2})
        assert not r.is_error
        sc = r.structured_content
        assert sc["total_extra_units"] == 48 and sc["total_extra_cost"] == 96 and sc["disputable_extra_cost"] == 96
        assert "1ZA" in sc["rows"][0]["dispute_draft"] and "申诉" in sc["rows"][0]["dispute_draft"]


async def test_surcharges_and_compare_and_optimize():
    async with Client(mcp) as c:
        r = await c.call_tool("check_express_surcharges", {"pieces": [{"length": 150, "width": 60, "height": 50, "weight": 20}], "carrier": "ups"})
        assert r.structured_content["pieces"][0]["surcharges"][0]["code"] == "UPS_LPS"
        r = await c.call_tool("compare_freight_options", {
            "pieces": [{"length": 60, "width": 40, "height": 40, "weight": 10, "quantity": 3}],
            "options": [{"name": "Air", "carrier_profile": "air_cargo_iata", "rate": 25, "fixed_fees": 500},
                        {"name": "Sea", "carrier_profile": "sea_lcl", "rate": 300, "fixed_fees": 1200}]})
        assert r.structured_content["cheapest"] == "Sea"
        r = await c.call_tool("optimize_box_size", {"length": 60, "width": 40, "height": 40, "weight": 7, "carrier_profile": "ups_express"})
        assert r.structured_content["best_possible_billable"] == 7.0


async def test_resource_and_prompt():
    async with Client(mcp) as c:
        res = (await c.list_resources()).resources
        assert any(str(x.uri) == "freight://billable-weight-rules" for x in res)
        prompts = (await c.list_prompts()).prompts
        assert any(p.name == "audit_freight_invoice" for p in prompts)
