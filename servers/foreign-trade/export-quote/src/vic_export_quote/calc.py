"""Pure calculation logic for export quotes. No I/O, fully unit-testable.

Pain points this module addresses (see the README "Pain points" table):
- CIF insurance is often computed on the wrong base. Under Incoterms 2020 CIF,
  minimum cover is 110% of the CIF value, so CIF = CFR / (1 - 1.1 * rate),
  not FOB + freight + FOB * rate.
- "Margin" and "markup" get mixed up. 20% margin means profit / price = 20%,
  which is a 25% markup on cost. Quoting with markup when you meant margin
  silently gives away profit.
- Fixed costs (trucking, customs clearance, documents) must be spread per unit,
  so small orders need a higher unit price. People forget and lose money on
  small orders.
- Container capacity is limited by volume AND weight. Heavy goods (tiles,
  steel, liquids) hit the weight limit long before the box is full.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from math import floor

# ---------------------------------------------------------------------------
# Incoterms 2020 reference data
# ---------------------------------------------------------------------------

INCOTERMS_2020: dict[str, dict] = {
    "EXW": {
        "name": "Ex Works",
        "mode": "any",
        "seller_pays_main_carriage": False,
        "seller_insures": False,
        "export_clearance": "buyer",
        "import_clearance": "buyer",
        "risk_transfers": "When goods are made available to the buyer at the seller's premises, not loaded.",
        "pitfalls": [
            "The buyer must handle export clearance in the seller's country, which foreign buyers often cannot do legally. For exports from China, FCA is usually safer.",
            "The seller has no duty to load the truck; if your staff load it and goods are damaged, liability is unclear.",
            "You get no export proof, which can block VAT export refunds (for China: export tax rebate).",
        ],
    },
    "FCA": {
        "name": "Free Carrier",
        "mode": "any",
        "seller_pays_main_carriage": False,
        "seller_insures": False,
        "export_clearance": "seller",
        "import_clearance": "buyer",
        "risk_transfers": "When goods are handed to the buyer's carrier at the named place (loaded if at seller's premises).",
        "pitfalls": [
            "Name the exact place (address or terminal). 'FCA Shenzhen' alone is ambiguous.",
            "For containers, ICC recommends FCA instead of FOB, because the box is handed over at the container yard, not on board.",
            "Incoterms 2020 lets parties agree the buyer's carrier issues an on-board bill of lading, useful for letters of credit; write it into the contract.",
        ],
    },
    "FAS": {
        "name": "Free Alongside Ship",
        "mode": "sea",
        "seller_pays_main_carriage": False,
        "seller_insures": False,
        "export_clearance": "seller",
        "import_clearance": "buyer",
        "risk_transfers": "When goods are placed alongside the vessel at the named port of shipment.",
        "pitfalls": ["Rare for containers. Mostly used for bulk or break-bulk cargo."],
    },
    "FOB": {
        "name": "Free On Board",
        "mode": "sea",
        "seller_pays_main_carriage": False,
        "seller_insures": False,
        "export_clearance": "seller",
        "import_clearance": "buyer",
        "risk_transfers": "When goods are on board the vessel at the named port of shipment.",
        "pitfalls": [
            "Sea and inland waterway only. Using FOB for air freight or rail is a misuse; use FCA.",
            "For containers, risk technically passes only on board, but you lose control at the container yard days earlier. ICC recommends FCA.",
            "Buyer-nominated forwarders sometimes charge the seller local fees (THC, documentation). Agree in writing who pays origin charges.",
        ],
    },
    "CFR": {
        "name": "Cost and Freight",
        "mode": "sea",
        "seller_pays_main_carriage": True,
        "seller_insures": False,
        "export_clearance": "seller",
        "import_clearance": "buyer",
        "risk_transfers": "On board at the port of shipment, even though the seller pays freight to destination.",
        "pitfalls": [
            "Risk passes at origin, cost passes at destination. If goods are lost at sea, the buyer bears the loss, so the buyer should insure.",
            "Destination terminal charges are usually for the buyer, but carriers sometimes bill them to the seller under the freight contract. Check the carrier terms.",
        ],
    },
    "CIF": {
        "name": "Cost, Insurance and Freight",
        "mode": "sea",
        "seller_pays_main_carriage": True,
        "seller_insures": True,
        "export_clearance": "seller",
        "import_clearance": "buyer",
        "risk_transfers": "On board at the port of shipment.",
        "pitfalls": [
            "Minimum cover is Institute Cargo Clauses (C) for 110% of the contract value. CIP (not CIF) requires the higher ICC (A).",
            "Insurance premium is based on 110% of the CIF price itself, so CIF = CFR / (1 - 1.1 x rate), not FOB + freight + FOB x rate.",
            "Sea only. For containers handed over at a terminal, ICC suggests CIP.",
        ],
    },
    "CPT": {
        "name": "Carriage Paid To",
        "mode": "any",
        "seller_pays_main_carriage": True,
        "seller_insures": False,
        "export_clearance": "seller",
        "import_clearance": "buyer",
        "risk_transfers": "When goods are handed to the first carrier, even though the seller pays carriage to the named destination.",
        "pitfalls": ["Risk passes early (first carrier). Buyers often think they are covered until arrival; they are not."],
    },
    "CIP": {
        "name": "Carriage and Insurance Paid To",
        "mode": "any",
        "seller_pays_main_carriage": True,
        "seller_insures": True,
        "export_clearance": "seller",
        "import_clearance": "buyer",
        "risk_transfers": "When goods are handed to the first carrier.",
        "pitfalls": ["Incoterms 2020 raised CIP minimum cover to ICC (A) (all risks), which costs more than CIF's ICC (C). Price it in."],
    },
    "DAP": {
        "name": "Delivered At Place",
        "mode": "any",
        "seller_pays_main_carriage": True,
        "seller_insures": False,
        "export_clearance": "seller",
        "import_clearance": "buyer",
        "risk_transfers": "When goods are ready for unloading at the named destination.",
        "pitfalls": [
            "Seller carries the risk for the whole journey, so insure even though it is not required.",
            "If the buyer fails to clear import customs, storage and demurrage pile up; agree who pays.",
        ],
    },
    "DPU": {
        "name": "Delivered at Place Unloaded",
        "mode": "any",
        "seller_pays_main_carriage": True,
        "seller_insures": False,
        "export_clearance": "seller",
        "import_clearance": "buyer",
        "risk_transfers": "When goods are unloaded at the named destination.",
        "pitfalls": ["The only term where the seller must unload. Make sure unloading is possible at that place."],
    },
    "DDP": {
        "name": "Delivered Duty Paid",
        "mode": "any",
        "seller_pays_main_carriage": True,
        "seller_insures": False,
        "export_clearance": "seller",
        "import_clearance": "seller",
        "risk_transfers": "When goods are ready for unloading at the named destination, import cleared.",
        "pitfalls": [
            "Seller pays import duty and import VAT. In the EU, a non-resident seller often cannot reclaim import VAT, which becomes a pure cost.",
            "Seller may need an importer-of-record or tax registration in the destination country.",
            "Tariffs change fast (e.g. US Section 301/232 measures). Re-check the duty rate before every DDP quote.",
        ],
    },
}

SEA_ONLY = {k for k, v in INCOTERMS_2020.items() if v["mode"] == "sea"}

# Common ISO container inside dimensions (cm) and typical max payload (kg).
# Payload varies by box and by road weight limits at origin/destination;
# callers can override max_payload_kg.
CONTAINERS: dict[str, dict] = {
    "20GP": {"length": 589.8, "width": 235.2, "height": 239.3, "max_payload_kg": 28000, "practical_cbm": 28.0},
    "40GP": {"length": 1203.2, "width": 235.2, "height": 239.3, "max_payload_kg": 26500, "practical_cbm": 58.0},
    "40HQ": {"length": 1203.2, "width": 235.2, "height": 269.8, "max_payload_kg": 26500, "practical_cbm": 68.0},
}


class QuoteInputError(ValueError):
    """Raised for inputs that make a quote meaningless. Message is user-facing."""


# ---------------------------------------------------------------------------
# Quote ladder
# ---------------------------------------------------------------------------

@dataclass
class QuoteInputs:
    unit_cost: float
    quantity: int
    target_margin_pct: float
    origin_fixed_costs: float = 0.0          # trucking to port, customs clearance, docs, THC (total, not per unit)
    main_freight: float = 0.0                # ocean/air freight for the whole shipment
    insurance_rate_pct: float = 0.0          # premium rate, e.g. 0.3 for 0.3 %
    insurance_cover_pct: float = 110.0       # Incoterms minimum is 110 %
    import_duty_pct: float = 0.0
    duty_basis: str = "CIF"                  # "CIF" (EU, China, most countries) or "FOB" (US, Canada, Australia)
    import_vat_pct: float = 0.0
    destination_costs: float = 0.0           # destination THC, delivery trucking, broker fee (total)
    min_margin_pct: float | None = None


def _r(x: float, nd: int = 2) -> float:
    return round(x + 0.0, nd)


def margin_to_markup(margin_pct: float) -> float:
    """20 % margin -> 25 % markup."""
    if margin_pct >= 100:
        raise QuoteInputError("Margin must be below 100%.")
    return margin_pct / (100 - margin_pct) * 100


def build_quote_ladder(q: QuoteInputs) -> dict:
    """Return per-unit and total prices for EXW, FCA/FOB, CFR, CIF, DDP.

    Pricing logic: FOB is the anchor, because it is the term most quotes are
    compared on. The target margin is hit exactly at FOB, on the seller's own
    cost (goods + origin costs). Freight, insurance, duty and destination
    costs are passed through at cost, so every term carries the same absolute
    profit and the margin % shrinks slightly on CFR/CIF/DDP (shown per row).
    """
    if q.quantity <= 0:
        raise QuoteInputError("Quantity must be at least 1.")
    if q.unit_cost <= 0:
        raise QuoteInputError("Unit cost must be greater than 0.")
    if not 0 <= q.target_margin_pct < 100:
        raise QuoteInputError("Target margin must be between 0 and 99.99 (it is profit / selling price, in %).")
    if q.insurance_rate_pct < 0 or q.insurance_rate_pct >= 5:
        raise QuoteInputError("Insurance rate looks wrong. Give it in percent, e.g. 0.3 for 0.3%. Typical cargo rates are 0.05% to 1%.")
    if q.insurance_cover_pct < 100:
        raise QuoteInputError("Insurance cover below 100% of value is under-insurance. Incoterms CIF/CIP minimum is 110%.")
    if q.duty_basis.upper() not in {"CIF", "FOB"}:
        raise QuoteInputError("duty_basis must be 'CIF' or 'FOB'.")
    for name in ("origin_fixed_costs", "main_freight", "import_duty_pct", "import_vat_pct", "destination_costs"):
        if getattr(q, name) < 0:
            raise QuoteInputError(f"{name} cannot be negative.")

    goods = q.unit_cost * q.quantity
    exw_cost = goods
    fob_cost = goods + q.origin_fixed_costs

    m = q.target_margin_pct / 100
    fob_total = fob_cost / (1 - m)
    profit = fob_total - fob_cost
    # Same absolute profit at every term.
    exw_total = exw_cost + profit
    cfr_total = fob_total + q.main_freight

    k = q.insurance_cover_pct / 100 * q.insurance_rate_pct / 100
    cif_total = cfr_total / (1 - k) if k else cfr_total
    insurance_premium = cif_total - cfr_total

    duty_base = cif_total if q.duty_basis.upper() == "CIF" else fob_total
    duty = duty_base * q.import_duty_pct / 100
    vat = (cif_total + duty) * q.import_vat_pct / 100
    ddp_total = cif_total + duty + vat + q.destination_costs

    def row(term: str, total: float, cost: float, note: str) -> dict:
        return {
            "incoterm": term,
            "total": _r(total),
            "unit_price": _r(total / q.quantity, 4),
            "your_cost_total": _r(cost),
            "profit_total": _r(total - cost),
            "margin_pct": _r((total - cost) / total * 100) if total else 0.0,
            "note": note,
        }

    ladder = [
        row("EXW", exw_total, exw_cost, "Goods only, at your factory. Buyer arranges everything."),
        row("FOB/FCA", fob_total, fob_cost, "Goods + origin trucking, export clearance, origin port charges."),
        row("CFR/CPT", cfr_total, fob_cost + q.main_freight, "FOB + main freight to destination port."),
        row("CIF/CIP", cif_total, fob_cost + q.main_freight + insurance_premium,
            f"CFR + insurance on {q.insurance_cover_pct:g}% of CIF value."),
        row("DDP", ddp_total, fob_cost + q.main_freight + insurance_premium + duty + vat + q.destination_costs,
            "CIF + import duty + import VAT + destination charges and delivery."),
    ]

    warnings: list[str] = []
    min_m = q.min_margin_pct
    if min_m is not None and q.target_margin_pct < min_m:
        warnings.append(
            f"Target margin {q.target_margin_pct:g}% is below your floor of {min_m:g}%. Do not send this quote without approval."
        )
    ddp_margin = profit / ddp_total * 100 if ddp_total else 0
    if min_m is not None and q.target_margin_pct >= min_m and ddp_margin < min_m and (q.main_freight or q.destination_costs):
        warnings.append(
            f"Margin is {q.target_margin_pct:g}% at FOB but only {ddp_margin:.2f}% at DDP, below your floor of {min_m:g}%, "
            "because pass-through costs raise the price without adding profit. If you quote CIF/DDP, raise the target or add a handling fee."
        )
    if q.origin_fixed_costs and q.origin_fixed_costs / fob_total > 0.10:
        warnings.append(
            f"Origin fixed costs are {q.origin_fixed_costs / fob_total * 100:.1f}% of the FOB value. "
            "This order is small for its fixed costs; consider a minimum order quantity or a small-order surcharge."
        )
    if q.main_freight == 0:
        warnings.append("main_freight is 0, so CFR/CIF/DDP equal FOB plus insurance only. Get a freight quote first.")
    if q.import_duty_pct == 0:
        warnings.append("import_duty_pct is 0. Confirm the destination HS-code duty rate before quoting DDP.")
    if q.import_vat_pct and q.import_vat_pct > 0:
        warnings.append("Under DDP you pay import VAT. A non-resident seller often cannot reclaim it, so it is a real cost.")

    return {
        "quantity": q.quantity,
        "goods_cost_total": _r(goods),
        "target_margin_pct": q.target_margin_pct,
        "equivalent_markup_pct": _r(margin_to_markup(q.target_margin_pct)),
        "profit_total": _r(profit),
        "insurance_premium": _r(insurance_premium),
        "import_duty": _r(duty),
        "import_vat": _r(vat),
        "ladder": ladder,
        "warnings": warnings,
    }


def tiered_unit_prices(base: QuoteInputs, quantities: list[int]) -> list[dict]:
    """Show how the FOB unit price falls as quantity rises, because fixed origin
    costs are spread across more units. Freight is scaled linearly with quantity
    (a rough proxy; real freight is stepwise by container)."""
    if not quantities:
        raise QuoteInputError("Give at least one quantity.")
    out = []
    for qty in sorted(set(quantities)):
        if qty <= 0:
            raise QuoteInputError("Quantities must be positive.")
        scale = qty / base.quantity
        qi = QuoteInputs(**{**base.__dict__, "quantity": qty, "main_freight": base.main_freight * scale,
                            "destination_costs": base.destination_costs})
        lad = build_quote_ladder(qi)["ladder"]
        out.append({
            "quantity": qty,
            "fob_unit_price": lad[1]["unit_price"],
            "cif_unit_price": lad[3]["unit_price"],
        })
    return out


# ---------------------------------------------------------------------------
# Container loading
# ---------------------------------------------------------------------------

def _fit_count(box: tuple[float, float, float], inner: tuple[float, float, float]) -> tuple[int, tuple[float, float, float]]:
    best = (0, box)
    for o in set(permutations(box)):
        n = floor(inner[0] / o[0]) * floor(inner[1] / o[1]) * floor(inner[2] / o[2])
        if n > best[0]:
            best = (n, o)
    return best


def _best_mix(results: list[dict], total: int, carton_cbm: float, ratio_40: float = 1.4) -> str:
    """Cheapest mix of 20GP/40GP/40HQ (by RELATIVE_BOX_COST) that holds `total` cartons."""
    from math import ceil

    box_cost = {"20GP": 1.0, "40GP": ratio_40, "40HQ": ratio_40 + 0.05}
    cap = {r["container"]: r["max_cartons"] for r in results}
    if not any(cap.values()):
        return "Carton does not fit any standard container; it needs flat-rack or break-bulk."
    best = None
    max_hq = ceil(total / cap["40HQ"]) if cap["40HQ"] else 0
    max_gp = ceil(total / cap["40GP"]) if cap["40GP"] else 0
    for hq in range(max_hq + 1):
        for gp in range(max_gp + 1):
            left = total - hq * cap["40HQ"] - gp * cap["40GP"]
            if left > 0 and not cap["20GP"]:
                continue
            twenty = ceil(left / cap["20GP"]) if left > 0 else 0
            cost = hq * box_cost["40HQ"] + gp * box_cost["40GP"] + twenty * box_cost["20GP"]
            boxes = hq + gp + twenty
            key = (round(cost, 4), boxes)
            if best is None or key < best[0]:
                best = (key, {"40HQ": hq, "40GP": gp, "20GP": twenty})
    mix = best[1]
    parts = [f"{n} x {k}" for k, n in mix.items() if n]
    capacity = sum(cap[k] * n for k, n in mix.items())
    util = total / capacity * 100
    msg = f"{' + '.join(parts)} for {total} cartons ({util:.0f}% of usable capacity), the cheapest mix if a 40ft costs {ratio_40:g}x a 20ft on your lane."
    if util > 97:
        msg += " Very tight: if cartons bulge or the loader is less efficient, some may be shut out. Agree a plan for leftovers."
    # Would sending the smallest remainder by LCL be cheaper?
    if sum(mix.values()) > 1 or util < 60:
        biggest = max((k for k, n in mix.items() if n), key=lambda k: cap[k])
        full = (total // cap[biggest])
        rest = total - full * cap[biggest]
        if full and rest and rest * carton_cbm < 15:
            msg += f" Alternative: {full} x {biggest} full + {rest} cartons ({rest * carton_cbm:.1f} CBM) by LCL. Compare both quotes."
    return msg


def plan_loading(length_cm: float, width_cm: float, height_cm: float, gross_weight_kg: float,
                 total_cartons: int | None = None, keep_upright: bool = True,
                 max_payload_kg: float | None = None, loading_efficiency_pct: float = 90.0,
                 forty_to_twenty_rate_ratio: float = 1.4) -> dict:
    """Cartons per container by geometry and by weight; recommend box choice."""
    for v, n in ((length_cm, "length_cm"), (width_cm, "width_cm"), (height_cm, "height_cm"), (gross_weight_kg, "gross_weight_kg")):
        if v <= 0:
            raise QuoteInputError(f"{n} must be greater than 0.")
    if length_cm > 1200 or width_cm > 1200 or height_cm > 1200:
        raise QuoteInputError("Carton dimensions are in centimetres; a side over 12 m will not fit any standard container.")
    if not 50 <= loading_efficiency_pct <= 100:
        raise QuoteInputError("loading_efficiency_pct should be between 50 and 100 (real-world stuffing loses 5-15%).")
    if not 1.0 <= forty_to_twenty_rate_ratio <= 3.0:
        raise QuoteInputError("forty_to_twenty_rate_ratio should be between 1.0 and 3.0 (a 40ft usually costs 1.3-1.6x a 20ft).")
    if total_cartons is not None and total_cartons <= 0:
        raise QuoteInputError("total_cartons must be positive.")

    carton_cbm = length_cm * width_cm * height_cm / 1_000_000
    results = []
    for name, c in CONTAINERS.items():
        inner = (c["length"], c["width"], c["height"])
        if keep_upright:
            best = (0, (length_cm, width_cm, height_cm))
            for o in ((length_cm, width_cm), (width_cm, length_cm)):
                n = floor(inner[0] / o[0]) * floor(inner[1] / o[1]) * floor(inner[2] / height_cm)
                if n > best[0]:
                    best = (n, (o[0], o[1], height_cm))
        else:
            best = _fit_count((length_cm, width_cm, height_cm), inner)
        geo = floor(best[0] * loading_efficiency_pct / 100)
        payload = max_payload_kg if max_payload_kg else c["max_payload_kg"]
        by_weight = floor(payload / gross_weight_kg)
        cap = min(geo, by_weight)
        results.append({
            "container": name,
            "cartons_by_space": geo,
            "cartons_by_weight": by_weight,
            "max_cartons": cap,
            "limited_by": "weight" if by_weight < geo else "space",
            "cbm_loaded": _r(cap * carton_cbm),
            "weight_loaded_kg": _r(cap * gross_weight_kg, 0),
            "orientation_cm": [round(x, 1) for x in best[1]],
        })

    rec = None
    warnings: list[str] = []
    if total_cartons:
        total_cbm = total_cartons * carton_cbm
        total_kg = total_cartons * gross_weight_kg
        if total_cbm < 15 and total_kg < 10000:
            rec = f"LCL (shared container): {total_cbm:.2f} CBM, {total_kg:.0f} kg. A full container is usually not worth it under about 15 CBM; compare LCL vs 20GP quotes."
        else:
            rec = _best_mix(results, total_cartons, carton_cbm, forty_to_twenty_rate_ratio)
    too_big = [r["container"] for r in results if r["cartons_by_space"] == 0]
    if too_big:
        warnings.append(f"The carton does not fit a {', '.join(too_big)} in the allowed orientation. "
                        + ("Allowing it to be tipped (keep_upright=false) may help, or use " if keep_upright else "Use ")
                        + "a high-cube, open-top or flat-rack container.")
    if any(r["limited_by"] == "weight" for r in results):
        warnings.append("Heavy cargo: weight, not space, limits loading. A 40ft box carries no more weight than a 20GP (often less), so for heavy goods several 20GPs are usually cheaper per kg.")
    warnings.append("Space counts assume identical cartons in one orientation block and include a loading-efficiency allowance. Pallets, mixed SKUs and fragile 'this side up' rules reduce capacity.")
    warnings.append("Max payload differs by box and by road limits (e.g. US/EU road weight caps can be lower than box payload). Confirm with your forwarder.")

    return {
        "carton_cbm": round(carton_cbm, 4),
        "containers": results,
        "recommendation": rec,
        "warnings": warnings,
    }
