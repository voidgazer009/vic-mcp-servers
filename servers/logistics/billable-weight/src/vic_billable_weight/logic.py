"""Pure business logic for billable (chargeable) weight, express surcharges,
carrier weight-adjustment audits and box-size optimisation.

No I/O, no network. Every rule cites its source in RULE_SOURCES / PROFILES.
All public functions raise FreightInputError for bad input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

KG_PER_LB = 0.45359237
CM_PER_IN = 2.54


class FreightInputError(ValueError):
    """Raised for inputs a human can fix (shown to the model as a tool error)."""


# ---------------------------------------------------------------------------
# Rounding helpers
# ---------------------------------------------------------------------------


def ceil_to(x: float, step: float) -> float:
    """Round x up to the next multiple of step, tolerant of float noise (20.0000001 -> 20)."""
    if step <= 0:
        return x
    n = math.ceil(round(x / step, 6))
    return round(n * step, 4)


def round_dim(x: float, mode: str) -> float:
    if mode == "ceil":
        return float(math.ceil(round(x, 6)))
    if mode == "nearest":  # half up, as carriers read a tape measure
        return float(math.floor(x + 0.5))
    return round(x, 2)


# ---------------------------------------------------------------------------
# Carrier / mode profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    native: str  # "metric" (cm/kg) or "imperial" (in/lb)
    divisor: float  # cm3 per kg (metric) or in3 per lb (imperial)
    dim_rounding: str  # ceil | nearest | none
    basis: str  # "piece": max(actual, dim) per piece then sum; "shipment": sum actual vs sum volume
    piece_step: float | None  # rounding of each piece's actual and dim weight
    shipment_steps: tuple[tuple[float, float], ...]  # (upper bound inclusive, step)
    unit: str  # kg | lb | RT
    source: str
    notes: str = ""
    min_units: float = 0.0

    def shipment_step(self, total: float) -> float:
        for upper, step in self.shipment_steps:
            if total <= upper + 1e-9:
                return step
        return self.shipment_steps[-1][1]


INF = float("inf")

PROFILES: dict[str, Profile] = {
    "ups_express": Profile(
        key="ups_express", label="UPS Worldwide Express / Saver (international, from China)", native="metric",
        divisor=5000, dim_rounding="ceil", basis="piece", piece_step=0.5, shipment_steps=((20, 0.5), (INF, 1.0)),
        unit="kg",
        source="UPS 2026 Rate and Service Guide, China (South), 'Billable Weight' steps 1-4",
        notes="Each side rounded up to the next cm, /5000, actual and dim weight each rounded up to 0.5 kg per package; "
              "shipment total rounded to 0.5 kg up to 20 kg, whole kg above. UPS Expedited rounds to whole kg (use custom).",
    ),
    "fedex_international": Profile(
        key="fedex_international", label="FedEx International Priority / Economy (from China)", native="metric",
        divisor=5000, dim_rounding="ceil", basis="piece", piece_step=0.5, shipment_steps=((20.5, 0.5), (INF, 1.0)),
        unit="kg",
        source="fedex.com.cn FAQ 'How do I calculate dimensional weight' (each side to next-higher cm, /5000); "
               "weight bands of the FedEx China 2026 rate sheet (0.5 kg steps to 20.5 kg, whole kg from 21 kg)",
        notes="Rated weight per package = greater of actual and dimensional weight. Weight steps follow the rate-sheet "
              "bands; if your contract bills differently, set rounding_step.",
    ),
    "dhl_express": Profile(
        key="dhl_express", label="DHL Express Worldwide (international)", native="metric",
        divisor=5000, dim_rounding="none", basis="piece", piece_step=0.5, shipment_steps=((30, 0.5), (INF, 1.0)),
        unit="kg",
        source="DHL Express Service & Rate Guide 2026 (volumetric = LxWxH cm / 5000 per piece; each piece rounded up "
               "to 0.5 kg; shipment rounded to 0.5 kg up to 30 kg, 1 kg above, as published in the 2026 Brazil guide)",
        notes="Rounding bands can differ by origin country guide; check the 2026 guide for your origin.",
    ),
    "air_cargo_iata": Profile(
        key="air_cargo_iata", label="Air cargo / air freight forwarder (IATA 1:6000)", native="metric",
        divisor=6000, dim_rounding="nearest", basis="shipment", piece_step=None, shipment_steps=((INF, 0.5),),
        unit="kg",
        source="IATA standard volume ratio 6,000 cm3 per kg (1 cbm = 166.67 kg); dims to nearest cm, chargeable weight "
               "rounded up to the next 0.5 kg (IATA TACT rules)",
        notes="Whole consignment: total gross weight vs total volume / 6000. Forwarders may share the volume difference "
              "(分泡) - use volume_split_customer_pct.",
    ),
    "sea_lcl": Profile(
        key="sea_lcl", label="Sea LCL (W/M, 1 cbm = 1,000 kg)", native="metric",
        divisor=1000, dim_rounding="none", basis="shipment", piece_step=None, shipment_steps=((INF, 0.01),),
        unit="RT", min_units=1.0,
        source="Ocean LCL weight-or-measure (W/M) tariff convention: 1 revenue ton = 1 cbm or 1,000 kg, whichever is "
               "greater; most CFS tariffs bill a 1 RT minimum",
        notes="Result is in revenue tons (RT). Origin/destination CFS charges are also billed per RT.",
    ),
    "road_ltl_eu": Profile(
        key="road_ltl_eu", label="European road groupage / LTL (1 cbm = 333 kg)", native="metric",
        divisor=3000, dim_rounding="nearest", basis="shipment", piece_step=None, shipment_steps=((INF, 1.0),),
        unit="kg",
        source="Common European groupage volume ratio 1 cbm = 333 kg; many carriers also bill by loading metre",
        notes="Ratios vary (250-333 kg/cbm) and pallets may be billed by loading metre; confirm with your carrier.",
    ),
    "us_domestic_daily": Profile(
        key="us_domestic_daily", label="UPS / FedEx US domestic, daily rates (139 in3/lb)", native="imperial",
        divisor=139, dim_rounding="nearest", basis="piece", piece_step=1.0, shipment_steps=((INF, 1.0),),
        unit="lb",
        source="ups.com 'Shipping Dimensions and Weight' (sides rounded to nearest whole inch, /139 daily or /166 "
               "retail, fractions up to next whole lb)",
        notes="For UPS retail counter rates use divisor_override=166.",
    ),
    "custom": Profile(
        key="custom", label="Custom (your forwarder's divisor and rounding)", native="metric",
        divisor=5000, dim_rounding="ceil", basis="piece", piece_step=0.5, shipment_steps=((INF, 0.5),),
        unit="kg", source="User-supplied divisor and rounding",
        notes="Set divisor_override (e.g. 6000 for many 专线/空派 lines) and rounding_step.",
    ),
}


@dataclass
class Piece:
    length: float
    width: float
    height: float
    weight: float
    quantity: int = 1
    ref: str = ""


@dataclass
class Options:
    dimension_unit: str = "cm"
    weight_unit: str = "kg"
    divisor_override: float | None = None
    rounding_step: float | None = None
    min_billable_per_piece: float | None = None
    volume_split_customer_pct: float = 0.0


def _validate_piece(p: Piece, i: int) -> None:
    for name in ("length", "width", "height", "weight"):
        v = getattr(p, name)
        if v is None or not math.isfinite(v) or v <= 0:
            raise FreightInputError(f"Piece {i + 1}: {name} must be a positive number, got {v!r}.")
    if p.quantity < 1:
        raise FreightInputError(f"Piece {i + 1}: quantity must be at least 1.")


def _to_native(p: Piece, prof: Profile, opt: Options) -> tuple[list[float], float]:
    dims = [p.length, p.width, p.height]
    w = p.weight
    if prof.native == "metric":
        if opt.dimension_unit == "in":
            dims = [d * CM_PER_IN for d in dims]
        if opt.weight_unit == "lb":
            w = w * KG_PER_LB
    else:
        if opt.dimension_unit == "cm":
            dims = [d / CM_PER_IN for d in dims]
        if opt.weight_unit == "kg":
            w = w / KG_PER_LB
    return dims, w


def get_profile(key: str) -> Profile:
    if key not in PROFILES:
        raise FreightInputError(f"Unknown carrier profile '{key}'. Valid: {', '.join(PROFILES)}.")
    return PROFILES[key]


def chargeable_weight(pieces: list[Piece], profile: str, opt: Options | None = None) -> dict:
    """Billable weight of a shipment under one carrier profile. See PROFILES for each rule."""
    opt = opt or Options()
    prof = get_profile(profile)
    if not pieces:
        raise FreightInputError("Give at least one piece (length, width, height, weight).")
    if len(pieces) > 200:
        raise FreightInputError("At most 200 piece lines per call.")
    if profile == "custom" and not opt.divisor_override:
        raise FreightInputError("Profile 'custom' needs divisor_override (e.g. 5000 or 6000).")
    if not 0 <= opt.volume_split_customer_pct <= 100:
        raise FreightInputError("volume_split_customer_pct must be between 0 and 100.")
    if opt.divisor_override and prof.native == "metric" and opt.divisor_override < 1000:
        raise FreightInputError(f"Divisor {opt.divisor_override:g} looks like an inch/lb divisor; cm/kg profiles need 1000-10000 (e.g. 5000, 6000).")
    divisor = opt.divisor_override or prof.divisor
    piece_step = opt.rounding_step if opt.rounding_step else prof.piece_step
    warnings: list[str] = []
    rows = []
    tot_actual = tot_vol_w = tot_piece_billable = tot_cbm = 0.0
    n_pieces = 0
    vol_unit = "cm" if prof.native == "metric" else "in"
    for i, p in enumerate(pieces):
        _validate_piece(p, i)
        dims, w = _to_native(p, prof, opt)
        rdims = [round_dim(d, prof.dim_rounding) for d in dims]
        if min(rdims) <= 0:
            raise FreightInputError(f"Piece {i + 1}: a side rounds to 0 {vol_unit}; check the unit.")
        volume = rdims[0] * rdims[1] * rdims[2]
        dim_w = volume / divisor
        cbm = volume / 1e6 if prof.native == "metric" else volume * CM_PER_IN ** 3 / 1e6
        if prof.basis == "piece":
            a_r = ceil_to(w, piece_step) if piece_step else w
            d_r = ceil_to(dim_w, piece_step) if piece_step else dim_w
            billable = max(a_r, d_r)
            if opt.min_billable_per_piece and billable < opt.min_billable_per_piece:
                billable = opt.min_billable_per_piece
        else:
            billable = max(w, dim_w)
            if opt.min_billable_per_piece and billable < opt.min_billable_per_piece:
                billable = opt.min_billable_per_piece
        rows.append({
            "ref": p.ref or f"#{i + 1}", "quantity": p.quantity,
            "dims_used": rdims, "actual_weight": round(w, 3), "dim_weight": round(dim_w, 3),
            "billable_each": round(billable, 3), "billable_total": round(billable * p.quantity, 3),
            "billed_by": "dimensional" if dim_w > w + 1e-9 else "actual",
            "air_ratio": round(dim_w / w, 2) if w else None,
        })
        sc = {"ups_express": "ups", "fedex_international": "fedex", "dhl_express": "dhl"}.get(prof.key)
        if sc:
            hits = surcharge_flags(sc, rdims, w, dim_w)
            for h in hits["surcharges"]:
                warnings.append(f"{p.ref or f'#{i + 1}'}: {h['name']} ({h['reason']}). Run check_express_surcharges for details.")
            if hits["min_billable_kg"] and billable < hits["min_billable_kg"]:
                warnings.append(f"{p.ref or f'#{i + 1}'}: that surcharge also sets a {hits['min_billable_kg']:g} kg minimum billable weight, not included above.")
        tot_actual += w * p.quantity
        tot_vol_w += dim_w * p.quantity
        tot_piece_billable += billable * p.quantity
        tot_cbm += cbm * p.quantity
        n_pieces += p.quantity

    if prof.basis == "piece":
        raw = tot_piece_billable
    else:
        raw = max(tot_actual, tot_vol_w)
        if opt.min_billable_per_piece:
            raw = max(raw, tot_piece_billable)
    split = opt.volume_split_customer_pct
    if split and tot_vol_w > tot_actual and prof.basis == "shipment":
        raw = tot_vol_w - (tot_vol_w - tot_actual) * split / 100
        if opt.min_billable_per_piece:
            raw = max(raw, tot_piece_billable)
    elif split and prof.basis == "piece":
        warnings.append("volume_split_customer_pct (分泡) is ignored for per-piece express profiles; express carriers do not share volume.")

    if prof.unit == "RT":
        if tot_cbm and tot_actual / tot_cbm > 1000:
            warnings.append("Dense cargo (over 1,000 kg per cbm): LCL bills by weight here.")
        rt_raw = max(tot_cbm, tot_actual / 1000)
        step = opt.rounding_step or 0.01
        billable_total = max(ceil_to(rt_raw, step), prof.min_units)
        if rt_raw < prof.min_units:
            warnings.append(f"Shipment is {rt_raw:.3f} RT, billed at the {prof.min_units:g} RT minimum.")
    else:
        step = opt.rounding_step or prof.shipment_step(raw)
        billable_total = ceil_to(raw, step)

    billed_by = "dimensional" if tot_vol_w > tot_actual + 1e-9 else "actual"
    if billed_by == "dimensional" and tot_actual > 0 and prof.unit != "RT":
        ratio = tot_vol_w / tot_actual
        if ratio >= 1.5:
            warnings.append(f"You are paying for air: volumetric weight is {ratio:.1f}x the actual weight. Run optimize_box_size or compare sea/rail.")
    if opt.divisor_override and opt.divisor_override != prof.divisor:
        warnings.append(f"Divisor {opt.divisor_override:g} overrides the profile default {prof.divisor:g}; make sure your quote says so in writing.")
    if prof.basis == "piece" and n_pieces > 1:
        warnings.append("Express bills each package separately: several light boxes can cost more than one consolidated box.")
    if opt.min_billable_per_piece:
        warnings.append(f"Per-piece minimum of {opt.min_billable_per_piece:g} {prof.unit} applied (common on FBA/专线 lines).")
    if profile == "fedex_international":
        warnings.append("FedEx weight steps follow the China rate-sheet bands; your contract may differ.")
    density = (tot_actual if prof.native == "metric" else tot_actual * KG_PER_LB) / tot_cbm if tot_cbm else 0
    return {
        "profile": prof.key, "profile_label": prof.label, "unit": prof.unit, "divisor": divisor,
        "pieces": rows, "piece_count": n_pieces,
        "total_actual_weight": round(tot_actual, 3), "total_dim_weight": round(tot_vol_w, 3),
        "total_cbm": round(tot_cbm, 4), "density_kg_per_cbm": round(density, 1),
        "billable": billable_total, "billed_by": billed_by,
        "rule": prof.notes, "source": prof.source, "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Express surcharge thresholds (international, metric). Amounts are China list prices before discount.
# ---------------------------------------------------------------------------

SURCHARGE_RULES = {
    "ups": {
        "source": "UPS 2026 Rate and Service Guide, China (South): Additional Handling, Large Package Surcharge, "
                  "Over Maximum Limits",
        "max": {"weight_kg": 70, "length_cm": 274, "length_girth_cm": 400},
    },
    "fedex": {
        "source": "FedEx China 2026 surcharge guide (fedex-ahs-guide-en-cn, fedex-rates-ifsur-cm-en-cn-2026): AHS, "
                  "Oversize Charge, Unauthorized Package Charge (effective 12 Jan 2026 volume criteria)",
        "max": {"weight_kg": 68, "length_cm": 274, "length_girth_cm": 419},
    },
    "dhl": {
        "source": "DHL Express Service & Rate Guide 2026 / Additional Handling Surcharge Guide: Overweight Piece, "
                  "Oversize Piece, Non-Conveyable Piece; Express Worldwide max piece 120x80x80 cm, 70 kg",
        "max": {"weight_kg": 70},
    },
}


def _sorted_dims(dims: list[float]) -> list[float]:
    return sorted(dims, reverse=True)


def surcharge_flags(carrier: str, dims_cm: list[float], actual_kg: float, dim_weight_kg: float,
                    packaging: str = "corrugated") -> dict:
    """Which non-standard surcharges one package triggers. Thresholds are 'greater than' as the guides word them."""
    if carrier not in SURCHARGE_RULES:
        raise FreightInputError(f"Surcharge rules exist for ups, fedex, dhl only, not '{carrier}'.")
    L, W, H = _sorted_dims(dims_cm)
    lg = L + 2 * W + 2 * H
    vol = L * W * H
    hits: list[dict] = []
    min_billable = 0.0
    refused = False

    def add(code, name, reason, amount=None, mbw=None):
        hits.append({"code": code, "name": name, "reason": reason, "list_price": amount, "min_billable_kg": mbw})

    if carrier == "ups":
        over = []
        if actual_kg > 70: over.append(f"actual weight {actual_kg:g} kg > 70 kg")
        if L > 274: over.append(f"length {L:g} cm > 274 cm")
        if lg > 400: over.append(f"length+girth {lg:g} cm > 400 cm")
        if over:
            refused = True
            add("UPS_OVER_MAX", "Over Maximum Limits (package not accepted; fee if tendered)", "; ".join(over))
        if 300 < lg <= 400:
            add("UPS_LPS", "Large Package Surcharge", f"length+girth {lg:g} cm > 300 cm", "RMB514 / package", 40)
            min_billable = 40
        else:
            ah = []
            if L > 122: ah.append(f"longest side {L:g} cm > 122 cm")
            if W > 76: ah.append(f"second-longest side {W:g} cm > 76 cm")
            if actual_kg > 25: ah.append(f"actual weight {actual_kg:g} kg > 25 kg")
            if packaging != "corrugated": ah.append(f"packaging '{packaging}' is not fully encased in corrugated cardboard")
            if ah:
                add("UPS_AH", "Additional Handling Charge", "; ".join(ah), "RMB142.80 / package")
    elif carrier == "fedex":
        unauth = [r for r in [
            f"longest side {L:g} cm > 274 cm" if L > 274 else "",
            f"length+girth {lg:g} cm > 419 cm" if lg > 419 else "",
            f"actual weight {actual_kg:g} kg > 68 kg" if actual_kg > 68 else ""] if r]
        oversize = [r for r in [
            f"longest side {L:g} cm > 243 cm" if L > 243 else "",
            f"length+girth {lg:g} cm > 330 cm" if lg > 330 else "",
            f"volume {vol:,.0f} cm3 > 283,168 cm3" if vol > 283168 else "",
            f"actual weight {actual_kg:g} kg > 50 kg" if actual_kg > 50 else ""] if r]
        ahs_dim = [r for r in [
            f"longest side {L:g} cm > 121 cm" if L > 121 else "",
            f"second-longest side {W:g} cm > 76 cm" if W > 76 else "",
            f"length+girth {lg:g} cm > 266 cm" if lg > 266 else "",
            f"volume {vol:,.0f} cm3 > 169,901 cm3" if vol > 169901 else ""] if r]
        ahs_w = actual_kg > 25
        if unauth:
            refused = True
            add("FDX_UNAUTHORIZED", "Unauthorized Package Charge (exceeds FedEx limits)", "; ".join(unauth),
                None, 18 if ahs_dim else None)
        elif oversize:
            add("FDX_OVERSIZE", "Oversize Charge", "; ".join(oversize), "CNY516 / package", 18 if ahs_dim else None)
        elif ahs_dim:
            add("FDX_AHS_DIM", "Additional Handling Surcharge - Dimension", "; ".join(ahs_dim), "CNY195 / package", 18)
        elif ahs_w:
            add("FDX_AHS_WEIGHT", "Additional Handling Surcharge - Weight", f"actual weight {actual_kg:g} kg > 25 kg", "CNY195 / package")
        elif packaging != "corrugated":
            add("FDX_AHS_PACKAGING", "Additional Handling Surcharge - Packaging", f"packaging '{packaging}'")
        if ahs_dim and not unauth:
            min_billable = 18
    else:  # dhl
        if actual_kg > 70 or dim_weight_kg > 70:
            add("DHL_OVERWEIGHT", "Overweight Piece", f"actual {actual_kg:g} kg or volumetric {dim_weight_kg:g} kg > 70 kg (must be palletised)")
        elif L > 100 or W > 80:
            add("DHL_OVERSIZE", "Oversize Piece", f"longest {L:g} cm > 100 cm or second-longest {W:g} cm > 80 cm")
        elif actual_kg > 25 or packaging != "corrugated":
            why = f"actual weight {actual_kg:g} kg > 25 kg" if actual_kg > 25 else f"packaging '{packaging}'"
            add("DHL_NON_CONVEYABLE", "Non-Conveyable Piece", why)
        if L > 120 or W > 80 or H > 80:
            refused = True
            add("DHL_OVER_PIECE_MAX", "Exceeds Express Worldwide max piece size 120x80x80 cm (non-pallet)",
                f"{L:g}x{W:g}x{H:g} cm; ship on a pallet or use freight")
    return {"dims_sorted_cm": [L, W, H], "length_plus_girth_cm": round(lg, 1), "volume_cm3": round(vol),
            "surcharges": hits, "min_billable_kg": min_billable, "likely_refused": refused}


# ---------------------------------------------------------------------------
# Weight-adjustment audit
# ---------------------------------------------------------------------------


def _single(dims, weight, profile, opt) -> dict:
    return chargeable_weight([Piece(dims[0], dims[1], dims[2], weight)], profile, opt)


def _native(dims: list[float], weight: float, prof: Profile, opt: Options) -> tuple[list[float], float, Options]:
    """Convert user units to the profile's native units and return Options that say so."""
    if len(dims) != 3 or any((not math.isfinite(x)) or x <= 0 for x in dims) or not math.isfinite(weight) or weight <= 0:
        raise FreightInputError("Dimensions need exactly 3 positive numbers and weight must be positive.")
    d, w = _to_native(Piece(dims[0], dims[1], dims[2], weight), prof, opt)
    unit_d, unit_w = ("cm", "kg") if prof.native == "metric" else ("in", "lb")
    nopt = Options(unit_d, unit_w, opt.divisor_override, opt.rounding_step, opt.min_billable_per_piece,
                   opt.volume_split_customer_pct)
    return d, w, nopt


def audit_adjustment(declared_dims: list[float], declared_weight: float, audited_dims: list[float] | None,
                     audited_weight: float | None, profile: str, opt: Options | None = None,
                     rate_per_unit: float | None = None, billed_weight: float | None = None) -> dict:
    """Compare what you declared with what the carrier says it measured, and judge whether to dispute."""
    opt = opt or Options()
    prof = get_profile(profile)
    if prof.basis != "piece":
        raise FreightInputError("Adjustment audits are for per-package parcel/express profiles (ups_express, fedex_international, dhl_express, us_domestic_daily, custom).")
    a_dims = audited_dims or declared_dims
    a_w = audited_weight if audited_weight is not None else declared_weight
    declared_dims, declared_weight, nopt = _native(declared_dims, declared_weight, prof, opt)
    a_dims, a_w, _ = _native(a_dims, a_w, prof, opt)
    opt = nopt
    dec = _single(declared_dims, declared_weight, profile, opt)
    aud = _single(a_dims, a_w, profile, opt)
    d_row, a_row = dec["pieces"][0], aud["pieces"][0]
    # compare sides sorted so "60x40x30" vs "40x60x30" is not a change
    ds, as_ = sorted(d_row["dims_used"], reverse=True), sorted(a_row["dims_used"], reverse=True)
    raw_ds = sorted(declared_dims, reverse=True)
    raw_as = sorted(a_dims, reverse=True)
    side_delta = [round(a - d, 2) for a, d in zip(raw_as, raw_ds)]
    side_pct = [round((a - d) / d * 100, 1) for a, d in zip(raw_as, raw_ds)]
    w_ratio = a_w / declared_weight
    delta_units = round(aud["billable"] - dec["billable"], 3)
    reasons: list[str] = []
    evidence: list[str] = []
    unit = prof.unit
    tol = 1.0 if prof.native == "metric" else 0.5  # 1 cm or 0.5 in rounding / measuring tolerance per side

    if billed_weight is not None and billed_weight > aud["billable"] + 1e-9:
        reasons.append(f"Billed {billed_weight:g} {unit} but even the carrier's own audited dims and weight give {aud['billable']:g} {unit}: the invoice does not match its own data.")
    if delta_units <= 0 and (billed_weight is None or billed_weight <= aud["billable"]):
        verdict = "no_change" if delta_units == 0 else "audit_lower"
        if delta_units < 0:
            reasons.append("Carrier's audited data gives a LOWER billable weight than you declared; you may be owed a credit.")
    else:
        big_side = [i for i, s in enumerate(side_delta) if s > max(tol * 2, raw_ds[i] * 0.05)]
        within_tol = all(s <= tol for s in side_delta)
        weight_jump = w_ratio >= 1.5 and a_w - declared_weight >= (2 if prof.native == "metric" else 4.4)
        severity = 0  # 1 consistent, 2 borderline, 3 worth disputing, 4 strong
        if billed_weight is not None and billed_weight > aud["billable"] + 1e-9:
            severity = 4
        if weight_jump and all(abs(s) <= tol for s in side_delta):
            severity = max(severity, 4)
            reasons.append(f"Audited weight is {w_ratio:.1f}x your declared weight with the same box size: typical of a mis-scan, label swap or pallet weight counted on one box.")
        elif weight_jump:
            severity = max(severity, 3)
            reasons.append(f"Audited weight is {w_ratio:.1f}x your declared weight ({declared_weight:g} -> {a_w:g} {unit if unit != 'RT' else 'kg'}).")
        if big_side:
            severity = max(severity, 3)
            sides = ", ".join(f"side {i + 1} +{side_delta[i]:g} ({side_pct[i]:+g}%)" for i in big_side)
            reasons.append(f"Audited sides are much larger than declared ({sides}); more than measuring tolerance unless the box bulged.")
        elif within_tol and not weight_jump:
            severity = max(severity, 1)
            reasons.append(f"Each audited side is within {tol:g} {'cm' if prof.native == 'metric' else 'in'} of yours: the carrier rounds sides up and its scanner reads the outermost point. A dispute is unlikely to win; measure to the next whole unit before booking.")
        elif not weight_jump:
            severity = max(severity, 2)
            reasons.append("Sides grew a little more than rounding explains; dispute only if you have photos of the tape measure on the sealed box.")
        if severity == 1 and a_w > declared_weight * 1.05:
            severity = 2
            reasons.append(f"Audited weight is {a_w - declared_weight:g} heavier than declared; check your scale calibration.")
        verdict = {1: "consistent_with_rounding", 2: "borderline", 3: "worth_disputing", 4: "strong_dispute"}[max(severity, 1)]
        evidence = [
            "Photo of the sealed box on a scale showing the reading, with the tracking label visible",
            "Photos of a tape measure along each of the three sides at the widest point (bulges included)",
            "Packing list / product spec sheet with carton size and gross weight",
            "The carrier's audit record (scanner image or measurement log) - ask for it in writing",
            "Booking screenshot showing the dimensions and weight you declared",
        ]
    extra_cost = round(delta_units * rate_per_unit, 2) if rate_per_unit and delta_units > 0 else None
    # surcharge changes
    sc_carrier = {"ups_express": "ups", "fedex_international": "fedex", "dhl_express": "dhl"}.get(profile)
    new_surcharges: list[str] = []
    if sc_carrier:
        d_dims_cm, d_w = d_row["dims_used"], d_row["actual_weight"]
        a_dims_cm, a_wkg = a_row["dims_used"], a_row["actual_weight"]
        f1 = {s["code"] for s in surcharge_flags(sc_carrier, d_dims_cm, d_w, d_row["dim_weight"])["surcharges"]}
        f2 = surcharge_flags(sc_carrier, a_dims_cm, a_wkg, a_row["dim_weight"])["surcharges"]
        new_surcharges = [f"{s['name']} ({s['reason']})" for s in f2 if s["code"] not in f1]
        if new_surcharges:
            reasons.append("The audited size also triggers a surcharge you did not have: " + "; ".join(new_surcharges) + ".")
    return {
        "profile": prof.key, "unit": unit,
        "declared": {"dims_used": d_row["dims_used"], "actual_weight": d_row["actual_weight"], "dim_weight": d_row["dim_weight"], "billable": dec["billable"]},
        "audited": {"dims_used": a_row["dims_used"], "actual_weight": a_row["actual_weight"], "dim_weight": a_row["dim_weight"], "billable": aud["billable"]},
        "side_delta": side_delta, "side_delta_pct": side_pct, "weight_ratio": round(w_ratio, 2),
        "billable_delta": delta_units, "extra_cost_estimate": extra_cost,
        "verdict": verdict, "reasons": reasons, "new_surcharges": new_surcharges, "evidence_checklist": evidence,
    }


def dispute_draft(tracking: str, carrier_label: str, audit: dict, language: str) -> str:
    """Plain-text dispute message. Draft only: never sent by this server."""
    d, a, u = audit["declared"], audit["audited"], audit["unit"]
    du = "cm" if u in ("kg", "RT") else "in"
    wu = "kg" if u in ("kg", "RT") else "lb"
    dd = "x".join(f"{x:g}" for x in d["dims_used"]) + f" {du}"
    ad = "x".join(f"{x:g}" for x in a["dims_used"]) + f" {du}"
    if language == "zh":
        return (
            f"主题：运单 {tracking} 计费重量调整申诉\n\n您好，\n\n"
            f"我司运单 {tracking}（{carrier_label}）被调整计费重量，申请复核：\n"
            f"• 我方申报：尺寸 {dd}，实重 {d['actual_weight']:g} {wu}，计费重 {d['billable']:g} {u}\n"
            f"• 贵司复测：尺寸 {ad}，实重 {a['actual_weight']:g} {wu}，计费重 {a['billable']:g} {u}\n"
            f"• 差额：{audit['billable_delta']:g} {u}\n\n"
            + "".join(f"• {r}\n" for r in audit["reasons"]) +
            "\n附件为封箱后称重和三边测量照片、装箱单。请提供复测记录（扫描图像或测量日志），"
            "如无法提供，请按申报数据更正账单并退还差额。\n\n谢谢！"
        )
    return (
        f"Subject: Billing adjustment dispute, tracking {tracking}\n\nHello,\n\n"
        f"We dispute the weight/dimension adjustment on {tracking} ({carrier_label}):\n"
        f"• Declared: {dd}, actual {d['actual_weight']:g} {wu}, billable {d['billable']:g} {u}\n"
        f"• Your audit: {ad}, actual {a['actual_weight']:g} {wu}, billable {a['billable']:g} {u}\n"
        f"• Difference: {audit['billable_delta']:g} {u}\n\n"
        + "".join(f"• {r}\n" for r in audit["reasons"]) +
        "\nAttached: photos of the sealed box on the scale and a tape measure on each side, and the packing list. "
        "Please send the audit record (scanner image or measurement log). If it cannot be provided, please re-rate "
        "the shipment on the declared data and credit the difference.\n\nThank you."
    )


# ---------------------------------------------------------------------------
# Box-size optimisation
# ---------------------------------------------------------------------------

THRESHOLDS = {  # (description, check on sorted dims L>=W>=H) used to warn when a box sits just above a line
    "ups_express": [("UPS Additional Handling: longest side", 0, 122), ("UPS Additional Handling: second side", 1, 76)],
    "fedex_international": [("FedEx AHS-Dimension: longest side", 0, 121), ("FedEx AHS-Dimension: second side", 1, 76)],
    "dhl_express": [("DHL Oversize Piece: longest side", 0, 100), ("DHL Oversize Piece: second side", 1, 80)],
}


def optimize_box(dims: list[float], weight: float, profile: str, opt: Options | None = None,
                 product_dims: list[float] | None = None, padding: float = 2.0) -> dict:
    """How much smaller the carton must get before you stop paying for air, side by side."""
    opt = opt or Options()
    opt_in = opt
    prof = get_profile(profile)
    if prof.basis != "piece":
        raise FreightInputError("Box optimisation works per package; use an express/parcel profile (ups_express, fedex_international, dhl_express, us_domestic_daily, custom).")
    dims, weight, opt = _native(dims, weight, prof, opt)
    if product_dims:
        conv = _native(product_dims, 1.0, prof, Options(opt_in.dimension_unit, "kg"))[0]
        padding = padding * conv[0] / product_dims[0]  # same unit conversion as the sides
        product_dims = conv
    base = _single(dims, weight, profile, opt)
    row = base["pieces"][0]
    divisor = base["divisor"]
    cur = base["billable"]
    actual_billable = _single([1, 1, 1], weight, profile, opt)["billable"]  # billable if size did not matter
    floor = [0.0, 0.0, 0.0]
    if product_dims:
        floor = [x + padding for x in product_dims]
    # map product floors to the box sides in the order given by the user
    suggestions = []
    target_volume = actual_billable * divisor  # largest volume whose dim weight does not exceed actual billable
    used = row["dims_used"]
    for i, name in enumerate(["length", "width", "height"]):
        others = used[(i + 1) % 3] * used[(i + 2) % 3]
        need = target_volume / others
        need_r = math.floor(need) if prof.dim_rounding != "none" else round(need, 1)
        new_dims = list(used)
        new_dims[i] = need_r
        if need_r <= 0 or need_r >= used[i]:
            continue
        feasible = need_r >= floor[i]
        new_b = _single(new_dims, weight, profile, opt)["billable"] if need_r > 0 else None
        suggestions.append({
            "side": name, "current": used[i], "to": need_r, "cut": round(used[i] - need_r, 2),
            "billable_after": new_b, "saves": round(cur - new_b, 3) if new_b is not None else None,
            "feasible": feasible,
            "note": "" if feasible else f"Below product size + padding ({floor[i]:g}); not possible on this side alone.",
        })
    tightest = None
    if product_dims:
        tb = _single(floor, weight, profile, opt)
        tightest = {"dims": [round(x, 2) for x in floor], "billable": tb["billable"],
                    "saves": round(cur - tb["billable"], 3)}
    per_cm = []
    for i, name in enumerate(["length", "width", "height"]):
        new_dims = list(dims)
        new_dims[i] = max(used[i] - 1, 0.1)
        b = _single(new_dims, weight, profile, opt)["billable"]
        per_cm.append({"side": name, "billable_after_1_unit_cut": b, "saves": round(cur - b, 3)})
    warnings: list[str] = []
    s = sorted(used, reverse=True)
    for desc, idx, limit in THRESHOLDS.get(profile, []):
        if limit < s[idx] <= limit + 5:
            warnings.append(f"{desc} is {s[idx]:g} cm, just over the {limit} cm line: cutting {s[idx] - limit:g} cm avoids that surcharge.")
    if cur <= actual_billable:
        warnings.append("Already billed by actual weight: a smaller box will not lower the billable weight.")
    return {
        "profile": prof.key, "unit": prof.unit, "current_dims_used": used, "actual_weight": row["actual_weight"],
        "current_billable": cur, "best_possible_billable": actual_billable,
        "max_volume_without_dim_penalty": round(target_volume, 1),
        "single_side_cuts": suggestions, "tightest_box": tightest, "one_unit_cut_effect": per_cm, "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Option comparison
# ---------------------------------------------------------------------------


@dataclass
class FreightOption:
    name: str
    profile: str
    rate: float
    min_charge: float = 0.0
    fixed_fees: float = 0.0
    fuel_surcharge_pct: float = 0.0
    transit_days: int | None = None
    divisor_override: float | None = None


def compare_options(pieces: list[Piece], options: list[FreightOption], base_opt: Options | None = None) -> dict:
    base_opt = base_opt or Options()
    if len(options) < 1:
        raise FreightInputError("Give at least one option to price.")
    names = [o.name for o in options]
    if len(set(names)) != len(names):
        raise FreightInputError("Option names must be unique.")
    rows = []
    for o in options:
        if o.rate <= 0:
            raise FreightInputError(f"Option '{o.name}': rate must be positive.")
        opt = Options(base_opt.dimension_unit, base_opt.weight_unit, o.divisor_override, None,
                      base_opt.min_billable_per_piece, base_opt.volume_split_customer_pct if PROFILES.get(o.profile, PROFILES['custom']).basis == "shipment" else 0.0)
        if o.profile == "custom" and not o.divisor_override:
            raise FreightInputError(f"Option '{o.name}': profile 'custom' needs divisor_override.")
        cw = chargeable_weight(pieces, o.profile, opt)
        freight = max(cw["billable"] * o.rate, o.min_charge)
        fuel = freight * o.fuel_surcharge_pct / 100
        total = freight + fuel + o.fixed_fees
        rows.append({
            "name": o.name, "profile": o.profile, "billable": cw["billable"], "unit": cw["unit"],
            "billed_by": cw["billed_by"], "freight": round(freight, 2), "fuel": round(fuel, 2),
            "fixed_fees": round(o.fixed_fees, 2), "total": round(total, 2),
            "min_charge_applied": freight == o.min_charge and o.min_charge > 0,
            "cost_per_actual_kg": round(total / (cw["total_actual_weight"] if cw["unit"] != "lb" else cw["total_actual_weight"] * KG_PER_LB), 2) if cw["total_actual_weight"] else None,
            "transit_days": o.transit_days,
        })
    rows.sort(key=lambda r: r["total"])
    warnings = ["Totals cover only the rates you entered. Add destination charges, duties, remote-area and handling surcharges before deciding."]
    if any(r["unit"] == "RT" for r in rows):
        warnings.append("Sea LCL totals exclude origin/destination CFS, customs and delivery unless you put them in fixed_fees.")
    cheapest = rows[0]
    fastest = min((r for r in rows if r["transit_days"]), key=lambda r: r["transit_days"], default=None)
    if fastest and fastest["name"] != cheapest["name"]:
        extra = fastest["total"] - cheapest["total"]
        days = (cheapest["transit_days"] or 0) - fastest["transit_days"]
        if days > 0:
            warnings.append(f"'{fastest['name']}' is {days} day(s) faster for {extra:.2f} more ({extra / days:.2f} per day saved).")
    return {"options": rows, "cheapest": cheapest["name"], "fastest": fastest["name"] if fastest else None, "warnings": warnings}


RULE_SOURCES = {k: {"label": p.label, "divisor": p.divisor, "dim_rounding": p.dim_rounding, "basis": p.basis,
                    "piece_step": p.piece_step, "shipment_steps": [[u if u != INF else None, s] for u, s in p.shipment_steps],
                    "unit": p.unit, "rule": p.notes, "source": p.source} for k, p in PROFILES.items()}
