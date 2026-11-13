"""Vic Billable Weight MCP server.

Five deterministic tools for the most disputed number in international shipping:
the billable (chargeable) weight. Works out what UPS, FedEx, DHL, air cargo, sea
LCL and road groupage will bill, flags oversize surcharges before you book,
audits a carrier's weight/dimension adjustment and drafts the dispute, and shows
how much smaller a carton must be to stop paying for air.

Runs fully offline. Built on the official MCP Python SDK v2 (protocol revision 2026-07-28).
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .logic import (
    PROFILES,
    RULE_SOURCES,
    SURCHARGE_RULES,
    FreightInputError,
    FreightOption,
    Options,
    Piece,
    audit_adjustment,
    chargeable_weight,
    compare_options,
    dispute_draft,
    optimize_box,
    round_dim,
    surcharge_flags,
    _to_native,
)

mcp = MCPServer(
    name="vic-billable-weight",
    title="Vic Billable Weight",
    description="Billable weight for express, air, sea LCL and road; surcharge checks, adjustment audits, box sizing.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers/tree/main/servers/logistics/billable-weight",
    instructions=(
        "Use these tools whenever the user ships cartons internationally and asks what weight they will be billed, "
        "which carrier or mode is cheaper, why a carrier invoice has a weight or dimension adjustment, or how to pack "
        "smaller. Always: 1) ask for real carton dimensions and gross weight instead of guessing; 2) ask which carrier "
        "or forwarder and which divisor their quote states (5000 express, 6000 air cargo or many 专线 lines); 3) never "
        "invent freight rates - ask the user for them; 4) show the warnings returned by the tools; 5) dispute messages "
        "are drafts for the user to send themselves."
    ),
)

LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

ProfileKey = Literal["ups_express", "fedex_international", "dhl_express", "air_cargo_iata", "sea_lcl",
                     "road_ltl_eu", "us_domestic_daily", "custom"]
ParcelProfileKey = Literal["ups_express", "fedex_international", "dhl_express", "us_domestic_daily", "custom"]
DimUnit = Annotated[Literal["cm", "in"], Field(description="Unit of all lengths you give: cm or in. Converted to the carrier's own unit before rounding.")]
WeightUnit = Annotated[Literal["kg", "lb"], Field(description="Unit of all weights you give: kg or lb.")]

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class PieceIn(BaseModel):
    length: float = Field(gt=0, le=2000, description="Outer length of the packed carton, in dimension_unit.")
    width: float = Field(gt=0, le=2000, description="Outer width of the packed carton, in dimension_unit.")
    height: float = Field(gt=0, le=2000, description="Outer height of the packed carton, in dimension_unit.")
    weight: float = Field(gt=0, le=10000, description="Gross weight of ONE carton (goods + packaging), in weight_unit.")
    quantity: int = Field(default=1, ge=1, le=10000, description="How many identical cartons of this size.")
    ref: str = Field(default="", max_length=40, description="Optional label, e.g. SKU or carton number.")


class AdjustmentIn(BaseModel):
    tracking: str = Field(min_length=1, max_length=40, description="Tracking / waybill number of the adjusted package.")
    declared_dims: list[float] = Field(min_length=3, max_length=3, description="The L, W, H you declared when booking, in dimension_unit.")
    declared_weight: float = Field(gt=0, le=10000, description="The gross weight you declared, in weight_unit.")
    audited_dims: list[float] | None = Field(default=None, min_length=3, max_length=3, description="The L, W, H the carrier says it measured. Leave empty if only the weight changed.")
    audited_weight: float | None = Field(default=None, gt=0, le=10000, description="The weight the carrier says it measured. Leave empty if only dimensions changed.")
    billed_weight: float | None = Field(default=None, gt=0, le=10000, description="The billable weight printed on the invoice, if shown. Lets the tool catch an invoice that does not match the carrier's own audit.")


class OptionIn(BaseModel):
    name: str = Field(min_length=1, max_length=40, description="Your name for this quote, e.g. 'DHL 3-day' or 'Forwarder A air'.")
    carrier_profile: ProfileKey = Field(description="How this option computes billable weight (see calculate_chargeable_weight).")
    rate: float = Field(gt=0, le=100000, description="Price per billable unit from the quote: per kg (per lb for us_domestic_daily, per RT for sea_lcl).")
    min_charge: float = Field(default=0, ge=0, le=1000000, description="Minimum freight charge on the quote, if any.")
    fixed_fees: float = Field(default=0, ge=0, le=1000000, description="Per-shipment fees on the quote: customs, documents, pickup, CFS, delivery.")
    fuel_surcharge_pct: float = Field(default=0, ge=0, le=100, description="Fuel surcharge in % of freight, e.g. 43.25.")
    transit_days: int | None = Field(default=None, ge=0, le=120, description="Door-to-door transit days quoted, for the speed-vs-cost note.")
    divisor_override: float | None = Field(default=None, ge=1000, le=10000, description="Divisor this quote uses if it differs from the profile default, e.g. 6000.")


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class PieceRow(BaseModel):
    ref: str
    quantity: int
    dims_used: list[float] = Field(description="Sides after the carrier's rounding, in the carrier's unit.")
    actual_weight: float
    dim_weight: float = Field(description="Volume / divisor, before rounding.")
    billable_each: float
    billable_total: float
    billed_by: Literal["actual", "dimensional"]
    air_ratio: float | None = Field(description="Dimensional / actual weight. Above 1 means you pay for air.")


class ChargeableResult(BaseModel):
    profile: str
    profile_label: str
    unit: Literal["kg", "lb", "RT"]
    divisor: float
    pieces: list[PieceRow]
    piece_count: int
    total_actual_weight: float
    total_dim_weight: float
    total_cbm: float
    density_kg_per_cbm: float
    billable: float = Field(description="Billable weight of the whole shipment (kg, lb, or revenue tons for sea LCL).")
    billed_by: Literal["actual", "dimensional"]
    rule: str
    source: str
    warnings: list[str]


class SurchargeHit(BaseModel):
    code: str
    name: str
    reason: str
    list_price: str | None = Field(description="Published 2026 China list price before discount, where known.")
    min_billable_kg: float | None


class PieceSurcharge(BaseModel):
    ref: str
    quantity: int
    dims_sorted_cm: list[float]
    length_plus_girth_cm: float
    volume_cm3: float
    surcharges: list[SurchargeHit]
    min_billable_kg: float
    likely_refused: bool


class SurchargeResult(BaseModel):
    carrier: str
    pieces: list[PieceSurcharge]
    clean: bool = Field(description="True when no piece triggers any non-standard surcharge.")
    source: str
    warnings: list[str]


class AuditSide(BaseModel):
    dims_used: list[float]
    actual_weight: float
    dim_weight: float
    billable: float


class AuditRow(BaseModel):
    tracking: str
    declared: AuditSide
    audited: AuditSide
    side_delta: list[float] = Field(description="Audited minus declared, longest side first.")
    side_delta_pct: list[float]
    weight_ratio: float
    billable_delta: float
    extra_cost_estimate: float | None
    verdict: Literal["no_change", "audit_lower", "consistent_with_rounding", "borderline", "worth_disputing", "strong_dispute"]
    reasons: list[str]
    new_surcharges: list[str]
    dispute_draft: str | None = Field(description="Draft message for the user to send. Never sent by this server.")


class AuditResult(BaseModel):
    profile: str
    unit: str
    rows: list[AuditRow]
    total_extra_units: float
    total_extra_cost: float | None
    disputable_extra_cost: float | None = Field(description="Extra cost on rows judged worth disputing or strong.")
    evidence_checklist: list[str]
    warnings: list[str]


class SideCut(BaseModel):
    side: str
    current: float = Field(description="Current side length, in the carrier's unit.")
    to: float = Field(description="Side length needed for this single cut alone.")
    cut: float
    billable_after: float | None
    saves: float | None
    feasible: bool
    note: str


class OneCut(BaseModel):
    side: str
    billable_after_1_unit_cut: float
    saves: float


class TightBox(BaseModel):
    dims: list[float]
    billable: float
    saves: float


class OptimizeResult(BaseModel):
    profile: str
    unit: str
    current_dims_used: list[float]
    actual_weight: float
    current_billable: float
    best_possible_billable: float = Field(description="Billable weight if the box were small enough to bill by actual weight.")
    max_volume_without_dim_penalty: float
    single_side_cuts: list[SideCut]
    tightest_box: TightBox | None = Field(description="Product size + padding on every side, if product dims were given.")
    one_unit_cut_effect: list[OneCut]
    warnings: list[str]


class OptionRow(BaseModel):
    name: str
    profile: str
    billable: float
    unit: str
    billed_by: str
    freight: float
    fuel: float
    fixed_fees: float
    total: float
    min_charge_applied: bool
    cost_per_actual_kg: float | None
    transit_days: int | None


class CompareResult(BaseModel):
    options: list[OptionRow] = Field(description="Cheapest first.")
    cheapest: str
    fastest: str | None
    warnings: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pieces(items: list[PieceIn]) -> list[Piece]:
    return [Piece(p.length, p.width, p.height, p.weight, p.quantity, p.ref) for p in items]


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except FreightInputError as e:
        raise ToolError(str(e)) from e
    except (ValueError, ZeroDivisionError, OverflowError) as e:  # defensive: never crash the server
        raise ToolError(f"Could not compute with these inputs ({type(e).__name__}: {e}). Check units and sizes.") from e


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(title="Calculate billable (chargeable) weight", annotations=LOCAL)
def calculate_chargeable_weight(
    pieces: Annotated[list[PieceIn], Field(min_length=1, max_length=200, description="Carton lines: outer L, W, H, gross weight per carton and quantity.")],
    carrier_profile: Annotated[ProfileKey, Field(description="Billing rule: ups_express, fedex_international, dhl_express (5000, per package), air_cargo_iata (6000, whole shipment), sea_lcl (W/M 1 cbm = 1 t), road_ltl_eu (1 cbm = 333 kg), us_domestic_daily (139 in3/lb), custom.")],
    dimension_unit: DimUnit = "cm",
    weight_unit: WeightUnit = "kg",
    divisor_override: Annotated[float | None, Field(ge=100, le=10000, description="Divisor your quote states if it differs from the profile default, e.g. 6000 for many 专线/空派 lines, or 166 for UPS US retail with us_domestic_daily.")] = None,
    rounding_step: Annotated[float | None, Field(ge=0.01, le=10, description="Override the rounding step (0.1, 0.5 or 1 is typical) when your forwarder's quote says so.")] = None,
    min_billable_per_piece: Annotated[float | None, Field(gt=0, le=1000, description="Per-carton minimum billable weight, e.g. 12 on many FBA air/sea lines ('单件不足12kg按12kg').")] = None,
    volume_split_customer_pct: Annotated[float, Field(ge=0, le=100, description="Air cargo / sea / road only: share of the volume-vs-actual difference the forwarder gives back to you (分泡), e.g. 40 for a 60/40 split.")] = 0,
) -> ChargeableResult:
    """Work out the weight a carrier will actually bill: per-package express rules for UPS, FedEx and DHL (5000 divisor, side and 0.5 kg rounding), whole-shipment air cargo (1:6000), sea LCL revenue tons and road groupage.

    Shows dims after rounding, actual vs dimensional weight per carton, density and why. Use it before booking or quoting
    freight, and whenever a user asks why a light box is billed as heavy.
    """
    if divisor_override is not None and PROFILES[carrier_profile].native == "metric" and divisor_override < 1000:
        raise ToolError(f"Divisor {divisor_override:g} is an inch/lb divisor; for cm/kg profiles use 1000-10000 (e.g. 5000, 6000).")
    opt = Options(dimension_unit, weight_unit, divisor_override, rounding_step, min_billable_per_piece, volume_split_customer_pct)
    return ChargeableResult(**_guard(chargeable_weight, _pieces(pieces), carrier_profile, opt))


@mcp.tool(title="Check express oversize / overweight surcharges", annotations=LOCAL)
def check_express_surcharges(
    pieces: Annotated[list[PieceIn], Field(min_length=1, max_length=200, description="Carton lines to check: outer L, W, H, gross weight and quantity.")],
    carrier: Annotated[Literal["ups", "fedex", "dhl"], Field(description="Express carrier whose 2026 international surcharge thresholds to apply.")],
    dimension_unit: DimUnit = "cm",
    weight_unit: WeightUnit = "kg",
    packaging: Annotated[Literal["corrugated", "non_corrugated", "cylindrical_unboxed"], Field(description="Outer packaging. Wood, metal, plastic bags, foam or unboxed drums trigger handling charges.")] = "corrugated",
) -> SurchargeResult:
    """Check each carton against UPS, FedEx or DHL 2026 international surcharge lines before booking: Additional Handling, Large Package / Oversize, Overweight Piece, Non-Conveyable and over-maximum (refused) limits.

    Returns the triggered surcharge, the exact side or weight that crossed the line, minimum billable weights (UPS
    Large Package 40 kg, FedEx AHS 18 kg) and published China list prices where known.
    """
    prof = {"ups": "ups_express", "fedex": "fedex_international", "dhl": "dhl_express"}[carrier]
    p = PROFILES[prof]
    rows = []
    any_hit = False
    for i, item in enumerate(_pieces(pieces)):
        dims, w = _guard(_to_native, item, p, Options(dimension_unit, weight_unit))
        rdims = [round_dim(d, p.dim_rounding) for d in dims]
        dim_w = rdims[0] * rdims[1] * rdims[2] / p.divisor
        res = _guard(surcharge_flags, carrier, rdims, round(w, 3), round(dim_w, 3), packaging)
        any_hit = any_hit or bool(res["surcharges"])
        rows.append(PieceSurcharge(ref=item.ref or f"#{i + 1}", quantity=item.quantity, **res))
    warnings = ["Thresholds are the 2026 published international rules; amounts are China list prices before your discount and change yearly."]
    if any(r.likely_refused for r in rows):
        warnings.append("At least one carton exceeds the carrier's package limits: it may be refused or billed an over-max fee. Palletise or use air freight.")
    if any(r.min_billable_kg for r in rows):
        warnings.append("A minimum billable weight applies to some cartons; re-run calculate_chargeable_weight with min_billable_per_piece to price it.")
    if carrier == "dhl":
        warnings.append("DHL Non-Conveyable thresholds follow the 2026 EU/BR guides; US-origin exports use 56-150 lb.")
    return SurchargeResult(carrier=carrier, pieces=rows, clean=not any_hit, source=SURCHARGE_RULES[carrier]["source"], warnings=warnings)


@mcp.tool(title="Audit a carrier weight / dimension adjustment", annotations=LOCAL)
def audit_weight_adjustment(
    adjustments: Annotated[list[AdjustmentIn], Field(min_length=1, max_length=50, description="One line per adjusted package from the invoice: what you declared vs what the carrier says it measured.")],
    carrier_profile: Annotated[ParcelProfileKey, Field(description="Billing rule the carrier applies: ups_express, fedex_international, dhl_express, us_domestic_daily or custom.")],
    dimension_unit: DimUnit = "cm",
    weight_unit: WeightUnit = "kg",
    rate_per_unit: Annotated[float | None, Field(gt=0, le=100000, description="Your average price per billable kg (or lb) on this lane, to estimate the money at stake.")] = None,
    divisor_override: Annotated[float | None, Field(ge=100, le=10000, description="Divisor your contract uses if it differs from the profile default.")] = None,
    draft_language: Annotated[Literal["zh", "en", "none"], Field(description="Language of the dispute drafts for rows worth disputing; 'none' for no drafts.")] = "zh",
) -> AuditResult:
    """Check whether a carrier's 'shipping charge correction' or 'weight adjustment' is justified: re-rates your declared and the carrier's audited dimensions and weight, separates normal rounding from real overcharges, and flags new surcharges.

    Gives a verdict per tracking number, money at stake, an evidence checklist and a ready-to-send dispute draft. Drafts
    only: nothing is sent.
    """
    opt = Options(dimension_unit, weight_unit, divisor_override)
    prof = PROFILES[carrier_profile]
    rows: list[AuditRow] = []
    evidence: list[str] = []
    seen = set()
    for a in adjustments:
        if a.tracking in seen:
            raise ToolError(f"Tracking '{a.tracking}' appears twice; give each package once.")
        seen.add(a.tracking)
        if a.audited_dims is None and a.audited_weight is None:
            raise ToolError(f"{a.tracking}: give audited_dims, audited_weight or both - otherwise there is nothing to audit.")
        res = _guard(audit_adjustment, a.declared_dims, a.declared_weight, a.audited_dims, a.audited_weight,
                     carrier_profile, opt, rate_per_unit, a.billed_weight)
        evidence = evidence or res["evidence_checklist"]
        draft = None
        if draft_language != "none" and res["verdict"] in ("worth_disputing", "strong_dispute", "borderline"):
            draft = dispute_draft(a.tracking, prof.label, res, draft_language)
        rows.append(AuditRow(tracking=a.tracking, dispute_draft=draft, **{k: res[k] for k in (
            "declared", "audited", "side_delta", "side_delta_pct", "weight_ratio", "billable_delta",
            "extra_cost_estimate", "verdict", "reasons", "new_surcharges")}))
    total_units = round(sum(max(r.billable_delta, 0) for r in rows), 3)
    total_cost = round(total_units * rate_per_unit, 2) if rate_per_unit else None
    disp = round(sum(r.extra_cost_estimate or 0 for r in rows if r.verdict in ("worth_disputing", "strong_dispute")), 2) if rate_per_unit else None
    warnings = ["Verdicts compare numbers only; the carrier decides. Disputes win with photos of the sealed box on a scale and a tape on each side."]
    if prof.key == "fedex_international":
        warnings.append("FedEx weight steps follow the China rate-sheet bands; your contract may differ.")
    if not rate_per_unit:
        warnings.append("Give rate_per_unit to see the money at stake.")
    return AuditResult(profile=prof.key, unit=prof.unit, rows=rows, total_extra_units=total_units,
                       total_extra_cost=total_cost, disputable_extra_cost=disp, evidence_checklist=evidence, warnings=warnings)


@mcp.tool(title="Find the carton size that stops paying for air", annotations=LOCAL)
def optimize_box_size(
    length: Annotated[float, Field(gt=0, le=2000, description="Current carton outer length, in dimension_unit.")],
    width: Annotated[float, Field(gt=0, le=2000, description="Current carton outer width, in dimension_unit.")],
    height: Annotated[float, Field(gt=0, le=2000, description="Current carton outer height, in dimension_unit.")],
    weight: Annotated[float, Field(gt=0, le=10000, description="Gross weight of the packed carton, in weight_unit.")],
    carrier_profile: Annotated[ParcelProfileKey, Field(description="Per-package billing rule to optimise for: ups_express, fedex_international, dhl_express, us_domestic_daily or custom.")],
    dimension_unit: DimUnit = "cm",
    weight_unit: WeightUnit = "kg",
    product_length: Annotated[float | None, Field(gt=0, le=2000, description="Length of the product itself (in the same order as the carton sides), so cuts never go below it.")] = None,
    product_width: Annotated[float | None, Field(gt=0, le=2000, description="Width of the product itself.")] = None,
    product_height: Annotated[float | None, Field(gt=0, le=2000, description="Height of the product itself.")] = None,
    padding: Annotated[float, Field(ge=0, le=30, description="Protective padding to keep on each side beyond the product, in dimension_unit.")] = 2.0,
    divisor_override: Annotated[float | None, Field(ge=100, le=10000, description="Divisor your quote uses if not the profile default.")] = None,
) -> OptimizeResult:
    """Show how much smaller a carton must be before express bills it by real weight instead of volume: the volume ceiling, the cut needed on each side, the saving per 1 cm (or inch) cut, and the tightest feasible box around the product.

    Also warns when a side sits just over an Additional Handling / Oversize line. Use it when a user ships light, bulky
    goods or asks how to cut express costs.
    """
    prod = [product_length, product_width, product_height]
    if any(x is not None for x in prod) and not all(x is not None for x in prod):
        raise ToolError("Give all three product dimensions (product_length, product_width, product_height) or none.")
    if all(x is not None for x in prod) and any(p > c for p, c in zip(prod, [length, width, height])):
        raise ToolError("A product dimension is larger than the carton side it is paired with; give the sides in the same order.")
    opt = Options(dimension_unit, weight_unit, divisor_override)
    res = _guard(optimize_box, [length, width, height], weight, carrier_profile, opt,
                 prod if all(x is not None for x in prod) else None, padding)
    return OptimizeResult(**res)


@mcp.tool(title="Compare freight quotes on billable weight", annotations=LOCAL)
def compare_freight_options(
    pieces: Annotated[list[PieceIn], Field(min_length=1, max_length=200, description="Carton lines of the shipment: outer L, W, H, gross weight and quantity.")],
    options: Annotated[list[OptionIn], Field(min_length=1, max_length=10, description="Quotes to compare, each with its billing profile, rate, minimum, fees, fuel and transit days. Use the user's real quotes.")],
    dimension_unit: DimUnit = "cm",
    weight_unit: WeightUnit = "kg",
    min_billable_per_piece: Annotated[float | None, Field(gt=0, le=1000, description="Per-carton minimum billable weight applied to every option, e.g. 12 for FBA lines.")] = None,
    volume_split_customer_pct: Annotated[float, Field(ge=0, le=100, description="分泡 share given back to you on air cargo / sea / road options, in %.")] = 0,
) -> CompareResult:
    """Price one shipment under several real quotes (express vs air cargo vs sea LCL vs road, or forwarder A vs B), each on its own billable-weight rule, and rank them by total cost with cost per real kg and cost per day saved.

    Rates must come from the user's quotes; this tool never invents prices.
    """
    for o in options:
        if o.divisor_override is not None and PROFILES[o.carrier_profile].native == "metric" and o.divisor_override < 1000:
            raise ToolError(f"Option '{o.name}': divisor {o.divisor_override:g} is too small for a cm/kg profile.")
    opts = [FreightOption(o.name, o.carrier_profile, o.rate, o.min_charge, o.fixed_fees, o.fuel_surcharge_pct,
                          o.transit_days, o.divisor_override) for o in options]
    base = Options(dimension_unit, weight_unit, None, None, min_billable_per_piece, volume_split_customer_pct)
    return CompareResult(**_guard(compare_options, _pieces(pieces), opts, base))


# ---------------------------------------------------------------------------
# Resource and prompt
# ---------------------------------------------------------------------------


@mcp.resource("freight://billable-weight-rules", name="billable-weight-rules", title="Billable weight and surcharge rules",
              mime_type="application/json",
              description="Every carrier profile (divisor, rounding, basis, source) and the express surcharge sources used by the tools.")
def rules() -> str:
    return json.dumps({"profiles": RULE_SOURCES,
                       "surcharges": {k: v["source"] for k, v in SURCHARGE_RULES.items()}}, ensure_ascii=False, indent=2)


@mcp.prompt(title="Audit a freight invoice",
            description="Walk through a carrier or forwarder invoice line by line, re-rate it, and prepare disputes for the user to send.")
def audit_freight_invoice(invoice_text: str, language: str = "中文") -> str:
    return (
        "You are a careful logistics cost auditor. Here is a carrier or forwarder invoice / adjustment notice:\n\n"
        f"---\n{invoice_text}\n---\n\n"
        "Steps:\n"
        "1. List each package: tracking number, declared and audited dimensions and weight, billed weight, charges. "
        "Say what is missing and ask me for it (especially my declared dimensions and the divisor in my quote).\n"
        "2. Call audit_weight_adjustment with all packages at once, with my rate per kg if I gave one.\n"
        "3. Call check_express_surcharges for any carton that got a handling / oversize fee.\n"
        "4. Summarise: total extra charged, how much is worth disputing, and which lines are just normal rounding.\n"
        "5. For lines worth disputing, show the dispute draft and the evidence I need. "
        f"Write in {language}.\n"
        "6. Then call optimize_box_size for the carton that costs most, so it does not happen again.\n"
        "Never send anything yourself: everything is a draft for my review."
    )


def main() -> None:
    """Entry point: stdio by default, `--http` for stateless Streamable HTTP on port 8000."""
    import sys

    if "--http" in sys.argv:
        mcp.run(transport="streamable-http", stateless_http=True)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
