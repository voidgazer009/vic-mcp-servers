"""Vic Export Quote MCP server.

Gives an AI agent five reliable tools for the most error-prone part of export
sales: turning a factory cost into a correct quote across Incoterms, sizing
the container, converting currency, and explaining terms to buyers.

Built on the official MCP Python SDK v2 (protocol revision 2026-07-28).
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

import httpx2 as httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .calc import (
    INCOTERMS_2020,
    QuoteInputError,
    QuoteInputs,
    build_quote_ladder,
    plan_loading,
    tiered_unit_prices,
)

mcp = MCPServer(
    name="vic-export-quote",
    title="Vic Export Quote",
    description="Correct export quotes across Incoterms, container loading, live FX and Incoterms 2020 guidance.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers",
    instructions=(
        "Use these tools whenever the user prices an export order, answers a buyer inquiry, or asks about Incoterms "
        "or container loading. Always: 1) ask for missing cost inputs instead of inventing freight, duty or "
        "insurance figures; 2) show the warnings returned by the tools to the user; 3) state that freight, duty "
        "and exchange rates must be re-confirmed before the quote is sent. Margin means profit divided by selling price."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

# ---------------------------------------------------------------------------
# Output models (give clients a typed outputSchema)
# ---------------------------------------------------------------------------


class LadderRow(BaseModel):
    incoterm: str = Field(description="Incoterm group, e.g. 'FOB/FCA'.")
    total: float = Field(description="Total price for the shipment in the input currency.")
    unit_price: float = Field(description="Price per unit, 4 decimals.")
    your_cost_total: float = Field(description="Your total cost at this term.")
    profit_total: float = Field(description="Profit at this term.")
    margin_pct: float = Field(description="Profit / price at this term, in %.")
    note: str = Field(description="What this term includes.")


class QuoteResult(BaseModel):
    currency: str
    quantity: int
    goods_cost_total: float
    target_margin_pct: float
    equivalent_markup_pct: float = Field(description="Markup on cost that gives the target margin.")
    profit_total: float
    insurance_premium: float
    import_duty: float
    import_vat: float
    ladder: list[LadderRow]
    warnings: list[str] = Field(description="Show these to the user before sending any quote.")


class TierRow(BaseModel):
    quantity: int
    fob_unit_price: float
    cif_unit_price: float


class TierResult(BaseModel):
    currency: str
    tiers: list[TierRow]
    note: str


class ContainerRow(BaseModel):
    container: str
    cartons_by_space: int
    cartons_by_weight: int
    max_cartons: int
    limited_by: Literal["space", "weight"]
    cbm_loaded: float
    weight_loaded_kg: float
    orientation_cm: list[float]


class LoadingResult(BaseModel):
    carton_cbm: float
    containers: list[ContainerRow]
    recommendation: str | None = Field(description="Box choice for total_cartons, if given.")
    warnings: list[str]


class IncotermResult(BaseModel):
    code: str
    name: str
    mode: Literal["any", "sea"]
    seller_pays_main_carriage: bool
    seller_insures: bool
    export_clearance: Literal["seller", "buyer"]
    import_clearance: Literal["seller", "buyer"]
    risk_transfers: str
    pitfalls: list[str]
    suggestion: str | None = Field(description="A better-fitting term for the stated transport, if any.")


class FxResult(BaseModel):
    amount: float
    from_currency: str
    to_currency: str
    rate: float
    converted: float
    rate_date: str = Field(description="ECB reference date of the rate (YYYY-MM-DD).")
    source: str
    warning: str


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

Money = Annotated[float, Field(ge=0)]


@mcp.tool(title="Calculate export quote across Incoterms", annotations=READ_ONLY)
def calculate_export_quote(
    unit_cost: Annotated[float, Field(gt=0, description="Your cost per unit (factory/purchase price), in `currency`.")],
    quantity: Annotated[int, Field(gt=0, description="Number of units in this order.")],
    target_margin_pct: Annotated[float, Field(ge=0, lt=100, description="Wanted margin = profit / selling price, in %. 20 means 20%.")],
    currency: Annotated[str, Field(min_length=3, max_length=3, description="ISO currency of all money inputs, e.g. USD or CNY.")] = "USD",
    origin_fixed_costs: Annotated[float, Field(ge=0, description="Total origin costs for the shipment: trucking to port, export customs, documents, origin THC.")] = 0.0,
    main_freight: Annotated[float, Field(ge=0, description="Total ocean/air freight to the destination port for the shipment. Ask the user or a forwarder; do not guess.")] = 0.0,
    insurance_rate_pct: Annotated[float, Field(ge=0, lt=5, description="Cargo insurance premium rate in %, e.g. 0.3 for 0.3%.")] = 0.0,
    insurance_cover_pct: Annotated[float, Field(ge=100, le=200, description="Insured value as % of CIF value. Incoterms minimum is 110.")] = 110.0,
    import_duty_pct: Annotated[float, Field(ge=0, le=500, description="Destination import duty rate for the HS code, in %. Needed for DDP.")] = 0.0,
    duty_basis: Annotated[Literal["CIF", "FOB"], Field(description="Value duty is charged on: CIF for EU, UK, China and most countries; FOB for US, Canada, Australia.")] = "CIF",
    import_vat_pct: Annotated[float, Field(ge=0, le=50, description="Destination import VAT/GST in %, charged on CIF + duty. 0 for the US.")] = 0.0,
    destination_costs: Annotated[float, Field(ge=0, description="Total destination charges for DDP: destination THC, customs broker, delivery trucking.")] = 0.0,
    min_margin_pct: Annotated[float | None, Field(ge=0, lt=100, description="Your margin floor in %. The tool warns when the quote falls below it.")] = None,
) -> QuoteResult:
    """Price one export order at EXW, FOB/FCA, CFR/CPT, CIF/CIP and DDP in a single call.

    Applies the target margin to your own cost, passes freight, insurance, duty and destination charges through at
    cost, and computes CIF insurance correctly on 110% of the CIF value. Returns a price ladder plus warnings
    (margin below floor, small-order fixed-cost drag, missing freight or duty). Use it before replying to any
    buyer price request.
    """
    try:
        res = build_quote_ladder(QuoteInputs(
            unit_cost=unit_cost, quantity=quantity, target_margin_pct=target_margin_pct,
            origin_fixed_costs=origin_fixed_costs, main_freight=main_freight,
            insurance_rate_pct=insurance_rate_pct, insurance_cover_pct=insurance_cover_pct,
            import_duty_pct=import_duty_pct, duty_basis=duty_basis, import_vat_pct=import_vat_pct,
            destination_costs=destination_costs, min_margin_pct=min_margin_pct,
        ))
    except QuoteInputError as e:
        raise ToolError(str(e)) from e
    return QuoteResult(currency=currency.upper(), **res)


@mcp.tool(title="Price by quantity (tiered pricing)", annotations=READ_ONLY)
def price_by_quantity(
    unit_cost: Annotated[float, Field(gt=0, description="Your cost per unit, in `currency`.")],
    target_margin_pct: Annotated[float, Field(ge=0, lt=100, description="Wanted margin = profit / selling price, in %.")],
    quantities: Annotated[list[int], Field(min_length=1, max_length=12, description="Order quantities to price, e.g. [500, 1000, 3000].")],
    origin_fixed_costs: Annotated[float, Field(ge=0, description="Total origin fixed costs per shipment (trucking, customs, documents).")] = 0.0,
    freight_per_unit: Annotated[float, Field(ge=0, description="Average freight per unit, used for the CIF column.")] = 0.0,
    insurance_rate_pct: Annotated[float, Field(ge=0, lt=5, description="Insurance premium rate in %.")] = 0.0,
    currency: Annotated[str, Field(min_length=3, max_length=3, description="ISO currency, e.g. USD.")] = "USD",
) -> TierResult:
    """Build a quantity price table (MOQ tiers) showing how the FOB and CIF unit price falls as fixed costs spread.

    Use it to answer 'what is the price for 500 / 1000 / 5000 pcs' or to set a minimum order quantity.
    """
    try:
        base_qty = min(quantities)
        if base_qty <= 0:
            raise QuoteInputError("Quantities must be positive.")
        base = QuoteInputs(unit_cost=unit_cost, quantity=base_qty, target_margin_pct=target_margin_pct,
                           origin_fixed_costs=origin_fixed_costs, main_freight=freight_per_unit * base_qty,
                           insurance_rate_pct=insurance_rate_pct)
        tiers = tiered_unit_prices(base, quantities)
    except QuoteInputError as e:
        raise ToolError(str(e)) from e
    return TierResult(
        currency=currency.upper(),
        tiers=[TierRow(**t) for t in tiers],
        note="Freight is scaled per unit; real freight steps up by container. Re-run calculate_export_quote with a real freight quote for the chosen tier.",
    )


@mcp.tool(title="Plan container loading", annotations=READ_ONLY)
def plan_container_loading(
    carton_length_cm: Annotated[float, Field(gt=0, description="Carton outer length in cm.")],
    carton_width_cm: Annotated[float, Field(gt=0, description="Carton outer width in cm.")],
    carton_height_cm: Annotated[float, Field(gt=0, description="Carton outer height in cm.")],
    carton_gross_weight_kg: Annotated[float, Field(gt=0, description="Gross weight of one packed carton in kg.")],
    total_cartons: Annotated[int | None, Field(gt=0, description="Cartons in the order. When given, the tool recommends LCL, 20GP, 40GP or 40HQ.")] = None,
    keep_upright: Annotated[bool, Field(description="True if cartons must stay 'this side up' (no tipping).")] = True,
    max_payload_kg: Annotated[float | None, Field(gt=0, le=30000, description="Override payload limit per container, e.g. a road weight cap from your forwarder.")] = None,
    loading_efficiency_pct: Annotated[float, Field(ge=50, le=100, description="Share of the theoretical fit you expect to achieve; 90 is typical for hand loading.")] = 90.0,
    forty_to_twenty_rate_ratio: Annotated[float, Field(ge=1.0, le=3.0, description="How many times a 40ft costs vs a 20ft on your lane (typical 1.3-1.6). Used to pick the cheapest box mix.")] = 1.4,
) -> LoadingResult:
    """Work out how many cartons fit in a 20GP, 40GP and 40HQ, limited by both space and weight, and which box to book.

    Use it when a buyer asks 'how many pieces per container' or before quoting CFR/CIF, so freight is priced on the right box.
    """
    try:
        res = plan_loading(carton_length_cm, carton_width_cm, carton_height_cm, carton_gross_weight_kg,
                           total_cartons, keep_upright, max_payload_kg, loading_efficiency_pct,
                           forty_to_twenty_rate_ratio)
    except QuoteInputError as e:
        raise ToolError(str(e)) from e
    return LoadingResult(**res)


@mcp.tool(title="Explain an Incoterm (2020)", annotations=READ_ONLY)
def explain_incoterm(
    code: Annotated[str, Field(min_length=3, max_length=12, description="Incoterms 2020 code, e.g. FOB, CIF, DDP. Case and spaces are ignored.")],
    transport: Annotated[Literal["sea_bulk", "sea_container", "air", "rail", "road", "multimodal", "unknown"], Field(description="How the goods move. Used to flag a misused term.")] = "unknown",
) -> IncotermResult:
    """Explain who pays, who insures, who clears customs and where risk passes under one Incoterms 2020 rule, with common pitfalls.

    Flags misuse, e.g. FOB or CIF for air freight or containers, and suggests the better term.
    """
    key = code.strip().upper()
    if key not in INCOTERMS_2020:
        raise ToolError(f"'{code}' is not an Incoterms 2020 rule. Valid: {', '.join(INCOTERMS_2020)}. (DAT was replaced by DPU in 2020.)")
    d = INCOTERMS_2020[key]
    suggestion = None
    swap = {"FOB": "FCA", "CFR": "CPT", "CIF": "CIP", "FAS": "FCA"}
    if d["mode"] == "sea" and transport in {"air", "rail", "road", "multimodal"}:
        suggestion = f"{key} is for sea and inland waterway only. For {transport} use {swap[key]}."
    elif d["mode"] == "sea" and transport == "sea_container" and key in swap:
        suggestion = f"For containers, ICC recommends {swap[key]} instead of {key}, because the container is handed over at the terminal, not on board."
    return IncotermResult(code=key, suggestion=suggestion, **d)


FX_URL = "https://api.frankfurter.dev/v1/latest"
CURRENCIES_URL = "https://api.frankfurter.dev/v1/currencies"


@mcp.tool(
    title="Convert currency (ECB reference rate)",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def convert_currency(
    amount: Annotated[float, Field(ge=0, description="Amount to convert.")],
    from_currency: Annotated[str, Field(min_length=3, max_length=3, description="ISO code to convert from, e.g. CNY.")],
    to_currency: Annotated[str, Field(min_length=3, max_length=3, description="ISO code to convert to, e.g. USD.")],
) -> FxResult:
    """Convert an amount using the latest European Central Bank reference rate (free, no API key, via frankfurter.dev).

    Rates update once per working day around 16:00 CET. Use it to turn a CNY cost into a USD/EUR quote.
    """
    f, t = from_currency.strip().upper(), to_currency.strip().upper()
    if f == t:
        return FxResult(amount=amount, from_currency=f, to_currency=t, rate=1.0, converted=round(amount, 2),
                        rate_date="n/a", source="identity", warning="Same currency, no conversion.")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(FX_URL, params={"base": f, "symbols": t})
    except httpx.HTTPError as e:
        raise ToolError(f"Exchange-rate service unreachable ({type(e).__name__}). Ask the user for a rate or try again later.") from e
    if r.status_code in (404, 422):
        unsupported = f"{f} or {t}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                known = (await client.get(CURRENCIES_URL)).json()
            missing = [c for c in (f, t) if c not in known]
            if missing:
                unsupported = " and ".join(missing)
            supported = ", ".join(sorted(known))
        except Exception:  # noqa: BLE001
            supported = "about 30 major currencies (USD, EUR, CNY, GBP, JPY, ...)"
        raise ToolError(f"The ECB feed has no rate for {unsupported}. Supported: {supported}. Ask the user for a bank rate instead.")
    if r.status_code != 200:
        raise ToolError(f"Exchange-rate service returned HTTP {r.status_code}. Ask the user for a rate or try again later.")
    data = r.json()
    rate = data.get("rates", {}).get(t)
    if rate is None:
        raise ToolError(f"No rate for {f}->{t} in the ECB feed.")
    return FxResult(
        amount=amount, from_currency=f, to_currency=t, rate=rate, converted=round(amount * rate, 2),
        rate_date=data.get("date", ""), source="European Central Bank via frankfurter.dev",
        warning="Reference rate only. Banks quote a spread (often 0.5-2%). For quotes valid 7+ days, add an FX buffer or a rate clause.",
    )


# ---------------------------------------------------------------------------
# Resource and prompt
# ---------------------------------------------------------------------------


@mcp.resource("incoterms://2020", name="incoterms-2020", title="Incoterms 2020 matrix", mime_type="application/json",
              description="All 11 Incoterms 2020 rules: costs, insurance, customs, risk transfer and pitfalls.")
def incoterms_matrix() -> str:
    return json.dumps(INCOTERMS_2020, ensure_ascii=False, indent=2)


@mcp.prompt(title="Reply to a buyer price inquiry",
            description="Turn a buyer's inquiry email into a checked quotation reply using the quote tools.")
def quotation_reply(inquiry_text: str, language: str = "English") -> str:
    return (
        "You are an experienced export sales manager. A buyer sent this inquiry:\n\n"
        f"---\n{inquiry_text}\n---\n\n"
        "Steps:\n"
        "1. Extract product, quantity, Incoterm, destination port, required delivery date and payment terms. "
        "List anything missing.\n"
        "2. If cost, freight or duty inputs are missing, ask me for them. Never invent them.\n"
        "3. Call plan_container_loading if carton data is known, then calculate_export_quote, and price_by_quantity "
        "if the buyer may order more.\n"
        "4. Show me all tool warnings first.\n"
        f"5. Draft the reply in {language}: thanks, price table for the requested term (and one alternative term), "
        "MOQ, lead time, payment terms, validity (7 days unless I say otherwise), and one question that moves the deal forward.\n"
        "6. Keep it as a draft for my review. Do not send."
    )


def main() -> None:
    """Entry point: stdio by default, `--http` for Streamable HTTP on port 8000."""
    import sys

    if "--http" in sys.argv:
        mcp.run(transport="streamable-http", stateless_http=True)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
