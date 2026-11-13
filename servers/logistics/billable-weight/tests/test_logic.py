"""Golden tests. Every expected number below was worked out by hand (see comments)."""
import pytest

from vic_billable_weight.logic import (
    FreightInputError, FreightOption, Options, Piece, audit_adjustment, ceil_to, chargeable_weight,
    compare_options, optimize_box, surcharge_flags,
)


# ---------------------------------------------------------------- rounding
def test_ceil_to_tolerates_float_noise():
    assert ceil_to(19.2, 0.5) == 19.5
    assert ceil_to(20.0000000001, 0.5) == 20.0
    assert ceil_to(20.01, 1) == 21


# ---------------------------------------------------------------- express
def test_ups_single_carton_dimensional():
    # 60*40*40 = 96,000 cm3 / 5000 = 19.2 kg -> next 0.5 kg = 19.5; actual 7 kg -> 7.0; billable 19.5
    r = chargeable_weight([Piece(60, 40, 40, 7)], "ups_express")
    assert r["billable"] == 19.5
    assert r["billed_by"] == "dimensional"
    assert r["pieces"][0]["dim_weight"] == 19.2


def test_ups_sides_round_up_to_next_cm():
    # 50 x 40 x 30.4 -> 50 x 40 x 31 = 62,000 / 5000 = 12.4 -> 12.5; actual 9.2 -> 9.5; billable 12.5
    r = chargeable_weight([Piece(50, 40, 30.4, 9.2)], "ups_express")
    assert r["pieces"][0]["dims_used"] == [50, 40, 31]
    assert r["billable"] == 12.5


def test_ups_vs_dhl_shipment_rounding_band():
    # pieces: 30x30x30 (5.4 kg dim) actual 10.3 -> 10.5 ; actual 10.0 -> 10.0 ; sum 20.5
    # UPS: over 20 kg -> whole kg -> 21 ; DHL: up to 30 kg -> 0.5 kg -> 20.5 ; FedEx: band to 20.5 -> 20.5
    p = [Piece(30, 30, 30, 10.3), Piece(30, 30, 30, 10.0)]
    assert chargeable_weight(p, "ups_express")["billable"] == 21
    assert chargeable_weight(p, "dhl_express")["billable"] == 20.5
    assert chargeable_weight(p, "fedex_international")["billable"] == 20.5


def test_multi_piece_sum_per_package():
    # 2 x (60x40x40, 7 kg) = 2 x 19.5 = 39 -> over 20 kg whole kg = 39 ; + (50x40x31) 12.5 -> 51.5 -> 52
    r = chargeable_weight([Piece(60, 40, 40, 7, 2), Piece(50, 40, 30.4, 9.2)], "ups_express")
    assert r["billable"] == 52
    assert r["piece_count"] == 3


# ---------------------------------------------------------------- air / sea / road
def test_air_cargo_whole_shipment_nearest_cm():
    # 60.4 x 40.6 x 40 -> nearest cm 60 x 41 x 40 = 98,400 ; x3 = 295,200 / 6000 = 49.2 kg ; actual 30 -> 49.5
    r = chargeable_weight([Piece(60.4, 40.6, 40, 10, 3)], "air_cargo_iata")
    assert r["total_dim_weight"] == pytest.approx(49.2)
    assert r["billable"] == 49.5


def test_air_cargo_volume_split():
    # 分泡 40% to customer: 49.2 - (49.2 - 30) * 0.4 = 41.52 -> 42.0
    r = chargeable_weight([Piece(60.4, 40.6, 40, 10, 3)], "air_cargo_iata", Options(volume_split_customer_pct=40))
    assert r["billable"] == 42.0


def test_sea_lcl_revenue_tons_and_minimum():
    # 10 x 60x50x40 = 10 x 0.12 = 1.2 cbm ; 250 kg = 0.25 t -> 1.2 RT
    assert chargeable_weight([Piece(60, 50, 40, 25, 10)], "sea_lcl")["billable"] == 1.2
    # 2 cartons = 0.24 cbm -> 1 RT minimum
    r = chargeable_weight([Piece(60, 50, 40, 25, 2)], "sea_lcl")
    assert r["billable"] == 1.0 and any("minimum" in w for w in r["warnings"])
    # dense: 1 cbm crate weighing 1,500 kg -> 1.5 RT (weight wins)
    assert chargeable_weight([Piece(100, 100, 100, 1500)], "sea_lcl")["billable"] == 1.5


def test_us_domestic_inches_and_cm_input_agree():
    # 20 x 14 x 12 in = 3,360 / 139 = 24.17 -> 25 lb
    assert chargeable_weight([Piece(20, 14, 12, 18)], "us_domestic_daily", Options("in", "lb"))["billable"] == 25
    # same box given in cm/kg: 50.8 x 35.56 x 30.48 cm, 8.165 kg -> 20 x 14 x 12 in -> 25 lb
    assert chargeable_weight([Piece(50.8, 35.56, 30.48, 8.165)], "us_domestic_daily")["billable"] == 25


def test_per_piece_minimum_fba_line():
    # custom 6000, 0.5 step: 30x30x30 = 4.5 kg dim, actual 5 -> 5 ; min 12 each -> 2 x 12 = 24
    r = chargeable_weight([Piece(30, 30, 30, 5, 2)], "custom", Options(divisor_override=6000, min_billable_per_piece=12))
    assert r["billable"] == 24


def test_errors():
    with pytest.raises(FreightInputError):
        chargeable_weight([], "ups_express")
    with pytest.raises(FreightInputError):
        chargeable_weight([Piece(0, 10, 10, 1)], "ups_express")
    with pytest.raises(FreightInputError):
        chargeable_weight([Piece(10, 10, 10, 1)], "custom")
    with pytest.raises(FreightInputError):
        chargeable_weight([Piece(10, 10, 10, 1)], "ups_express", Options(divisor_override=139))
    with pytest.raises(FreightInputError):
        chargeable_weight([Piece(10, 10, 10, 1)], "nope")


# ---------------------------------------------------------------- surcharges
def test_ups_additional_handling_and_large_package():
    # 123 + 2*40 + 2*30 = 263 cm (under 300) ; longest 123 > 122 and 30 kg > 25 -> Additional Handling only
    r = surcharge_flags("ups", [123, 40, 30], 30, 29.5)
    assert [s["code"] for s in r["surcharges"]] == ["UPS_AH"]
    # 123 + 2*50 + 2*40 = 303 > 300 -> already a Large Package, so no AH
    assert [s["code"] for s in surcharge_flags("ups", [123, 50, 40], 30, 49.2)["surcharges"]] == ["UPS_LPS"]
    # 150 + 2*60 + 2*50 = 370 > 300 -> Large Package, 40 kg minimum, no AH on top
    r = surcharge_flags("ups", [150, 60, 50], 20, 90)
    assert [s["code"] for s in r["surcharges"]] == ["UPS_LPS"] and r["min_billable_kg"] == 40
    r = surcharge_flags("ups", [280, 30, 30], 20, 50)
    assert r["likely_refused"]


def test_fedex_highest_only_with_18kg_minimum():
    r = surcharge_flags("fedex", [125, 50, 40], 20, 50)
    assert [s["code"] for s in r["surcharges"]] == ["FDX_AHS_DIM"] and r["min_billable_kg"] == 18
    # 100x60x60 = 360,000 cm3 > 283,168 -> Oversize (highest), AHS-dim also met -> 18 kg minimum
    r = surcharge_flags("fedex", [100, 60, 60], 20, 72)
    assert [s["code"] for s in r["surcharges"]] == ["FDX_OVERSIZE"] and r["min_billable_kg"] == 18
    assert surcharge_flags("fedex", [40, 30, 30], 26, 7.2)["surcharges"][0]["code"] == "FDX_AHS_WEIGHT"


def test_dhl_pieces():
    assert surcharge_flags("dhl", [110, 50, 40], 10, 44)["surcharges"][0]["code"] == "DHL_OVERSIZE"
    assert surcharge_flags("dhl", [60, 60, 60], 72, 43.2)["surcharges"][0]["code"] == "DHL_OVERWEIGHT"
    # 120x80x80 / 5000 = 153.6 kg volumetric > 70 -> Overweight even though it weighs 20 kg
    assert surcharge_flags("dhl", [120, 80, 80], 20, 153.6)["surcharges"][0]["code"] == "DHL_OVERWEIGHT"
    assert surcharge_flags("dhl", [40, 30, 30], 30, 7.2)["surcharges"][0]["code"] == "DHL_NON_CONVEYABLE"
    assert surcharge_flags("dhl", [40, 30, 30], 10, 7.2)["surcharges"] == []


# ---------------------------------------------------------------- adjustment audit
def test_audit_reddit_ups_case():
    # declared 46x18x7 in = 5,796/139 = 41.70 -> 42 lb ; audited 48x21x9 = 9,072/139 = 65.27 -> 66 lb ; +24 lb
    r = audit_adjustment([46, 18, 7], 16, [48, 21, 9], 26, "us_domestic_daily", Options("in", "lb"), rate_per_unit=2)
    assert r["declared"]["billable"] == 42 and r["audited"]["billable"] == 66
    assert r["billable_delta"] == 24 and r["extra_cost_estimate"] == 48
    assert r["verdict"] == "worth_disputing"


def test_audit_weight_jump_same_box_is_strong():
    # 11x8x6 in = 528/139 = 3.8 -> 4 lb ; declared 30 oz = 1.875 -> 2 lb ; audited 28 lb same box -> +24 lb
    r = audit_adjustment([11, 8, 6], 1.875, [11, 8, 6], 28, "us_domestic_daily", Options("in", "lb"))
    assert r["billable_delta"] == 24 and r["verdict"] == "strong_dispute"


def test_audit_rounding_only():
    # declared 60x40x40 -> 19.5 ; audited 61x41x40 = 100,040/5000 = 20.008 -> 20.5 per package, and a UPS shipment
    # over 20 kg rounds to whole kg -> 21 ; +1.5 kg although each side grew only 1 cm
    r = audit_adjustment([60, 40, 40], 7, [61, 41, 40], 7, "ups_express")
    assert r["audited"]["billable"] == 21 and r["billable_delta"] == 1.5
    assert r["verdict"] == "consistent_with_rounding"


def test_audit_invoice_does_not_match_own_audit():
    r = audit_adjustment([60, 40, 40], 7, [61, 41, 40], 7, "ups_express", billed_weight=25)
    assert r["verdict"] == "strong_dispute"


def test_audit_new_surcharge_flagged():
    # declared 120 cm long, audited 123 cm -> crosses UPS 122 cm Additional Handling line
    r = audit_adjustment([120, 40, 30], 10, [123, 40, 30], 10, "ups_express")
    assert any("Additional Handling" in s for s in r["new_surcharges"])


# ---------------------------------------------------------------- optimisation
def test_optimize_box_height_cut():
    # ceiling = 7 kg x 5000 = 35,000 cm3 ; height = 35,000 / (60x40) = 14.58 -> 14 ; 60x40x14 = 6.72 -> 7.0 ; saves 12.5
    r = optimize_box([60, 40, 40], 7, "ups_express")
    h = next(c for c in r["single_side_cuts"] if c["side"] == "height")
    assert h["to"] == 14 and h["billable_after"] == 7.0 and h["saves"] == 12.5
    # 1 cm off height: 60x40x39 = 93,600/5000 = 18.72 -> 19.0 ; saves 0.5
    assert next(c for c in r["one_unit_cut_effect"] if c["side"] == "height")["saves"] == 0.5


def test_optimize_tightest_box_around_product():
    # product 50x30x20 + 2 cm -> 52x32x22 = 36,608/5000 = 7.32 -> 7.5 ; saves 19.5 - 7.5 = 12.0
    r = optimize_box([60, 40, 40], 7, "ups_express", product_dims=[50, 30, 20], padding=2)
    assert r["tightest_box"] == {"dims": [52, 32, 22], "billable": 7.5, "saves": 12.0}


# ---------------------------------------------------------------- comparison
def test_compare_three_modes():
    # 3 x 60x40x40, 10 kg
    # DHL: 3 x 19.5 = 58.5 -> >30 kg whole kg -> 59 x 40 = 2,360 + 20% fuel 472 = 2,832
    # Air: 288,000/6000 = 48 vs 30 -> 48 x 25 = 1,200 + 500 = 1,700
    # Sea: 0.288 cbm -> 1 RT minimum x 300 + 1,200 = 1,500 (cheapest)
    p = [Piece(60, 40, 40, 10, 3)]
    r = compare_options(p, [FreightOption("DHL", "dhl_express", 40, fuel_surcharge_pct=20, transit_days=4),
                            FreightOption("Air", "air_cargo_iata", 25, fixed_fees=500, transit_days=7),
                            FreightOption("Sea", "sea_lcl", 300, fixed_fees=1200, transit_days=35)])
    totals = {o["name"]: o["total"] for o in r["options"]}
    assert totals == {"DHL": 2832.0, "Air": 1700.0, "Sea": 1500.0}
    assert r["cheapest"] == "Sea" and r["fastest"] == "DHL"
    # DHL is 31 days faster for 1,332 more -> 42.97 per day
    assert any("42.97" in w for w in r["warnings"])


def test_volume_split_never_undercuts_per_piece_minimum():
    # 20 x 30x30x30 5 kg: actual 100, volume 20 x 27,000 / 6000 = 90 -> 100 ; 50% split irrelevant ;
    # per-piece minimum 12 -> 20 x 12 = 240 must win
    r = chargeable_weight([Piece(30, 30, 30, 5, 20)], "air_cargo_iata", Options(volume_split_customer_pct=50, min_billable_per_piece=12))
    assert r["billable"] == 240


def test_chargeable_warns_about_surcharge_lines():
    # FedEx: 123 cm > 121 cm -> AHS-Dimension with 18 kg minimum; 123x20x20/5000 = 9.84 -> 10 kg billed, so warn
    r = chargeable_weight([Piece(123, 20, 20, 5, ref="tube")], "fedex_international")
    assert r["billable"] == 10.0
    assert any("tube: Additional Handling" in w for w in r["warnings"])
    assert any("18 kg minimum" in w for w in r["warnings"])
