"""Golden tests. Every expected number below was worked out by hand (see comments)."""
import pytest

from vic_export_quote.calc import QuoteInputError, QuoteInputs, build_quote_ladder, margin_to_markup, plan_loading, tiered_unit_prices


def base(**kw):
    d = dict(unit_cost=5, quantity=1000, target_margin_pct=20, origin_fixed_costs=300, main_freight=1200,
             insurance_rate_pct=0.3, import_duty_pct=3.9, duty_basis="FOB", destination_costs=600)
    d.update(kw)
    return QuoteInputs(**d)


def test_fob_hits_target_margin_exactly():
    # FOB cost = 5*1000 + 300 = 5300; FOB = 5300 / 0.8 = 6625; profit 1325
    r = build_quote_ladder(base())
    fob = r["ladder"][1]
    assert fob["total"] == 6625.00
    assert fob["margin_pct"] == 20.00
    assert r["profit_total"] == 1325.00


def test_same_profit_every_term():
    r = build_quote_ladder(base())
    assert {row["profit_total"] for row in r["ladder"]} == {1325.00}


def test_cif_insurance_on_110_pct_of_cif():
    # CFR = 6625 + 1200 = 7825; k = 1.1*0.003 = 0.0033; CIF = 7825/0.9967 = 7850.91
    r = build_quote_ladder(base())
    cif = r["ladder"][3]["total"]
    assert cif == pytest.approx(7850.91, abs=0.01)
    assert r["insurance_premium"] == pytest.approx(cif * 1.1 * 0.003, abs=0.01)


def test_duty_basis_fob_vs_cif():
    us = build_quote_ladder(base(duty_basis="FOB"))
    eu = build_quote_ladder(base(duty_basis="CIF"))
    assert us["import_duty"] == pytest.approx(6625 * 0.039, abs=0.01)       # 258.38
    assert eu["import_duty"] == pytest.approx(7850.91 * 0.039, abs=0.01)    # 306.19


def test_vat_on_cif_plus_duty():
    r = build_quote_ladder(base(duty_basis="CIF", import_vat_pct=19))
    assert r["import_vat"] == pytest.approx((7850.91 + 306.19) * 0.19, abs=0.02)
    assert any("import VAT" in w for w in r["warnings"])


def test_margin_vs_markup():
    assert margin_to_markup(20) == pytest.approx(25)
    assert margin_to_markup(50) == pytest.approx(100)


def test_floor_warning_and_ddp_squeeze():
    r = build_quote_ladder(base(target_margin_pct=12, min_margin_pct=15))
    assert any("below your floor" in w for w in r["warnings"])
    r2 = build_quote_ladder(base(target_margin_pct=16, min_margin_pct=15))
    assert any("at DDP" in w for w in r2["warnings"])


def test_small_order_fixed_cost_warning():
    r = build_quote_ladder(base(quantity=50))
    assert any("small for its fixed costs" in w for w in r["warnings"])


@pytest.mark.parametrize("kw", [dict(quantity=0), dict(unit_cost=0), dict(target_margin_pct=100),
                                dict(insurance_rate_pct=30), dict(insurance_cover_pct=90), dict(duty_basis="XYZ")])
def test_bad_inputs_rejected(kw):
    with pytest.raises(QuoteInputError):
        build_quote_ladder(base(**kw))


def test_tiers_fall_with_quantity():
    t = tiered_unit_prices(base(quantity=500), [500, 1000, 5000])
    fob = [x["fob_unit_price"] for x in t]
    assert fob[0] > fob[1] > fob[2]


def test_container_space_limited():
    # 60x40x40: 20GP 9*5*5=225 -> 90% = 202; 40HQ 20*5*6=600 -> 540
    r = plan_loading(60, 40, 40, 12, total_cartons=500)
    by = {c["container"]: c for c in r["containers"]}
    assert by["20GP"]["max_cartons"] == 202
    assert by["40HQ"]["max_cartons"] == 540
    assert "40HQ" in r["recommendation"]


def test_container_weight_limited_tiles():
    # 60x60x8 cm, 40 kg: 20GP space 9*3*29=783 -> 90% = 704; weight 28000/40 = 700
    r = plan_loading(60, 60, 8, 40, total_cartons=2000)
    by = {c["container"]: c for c in r["containers"]}
    assert by["20GP"]["limited_by"] == "weight"
    assert by["20GP"]["max_cartons"] == 700
    assert any("Heavy cargo" in w for w in r["warnings"])
    # 40HQ holds only 26500/40 = 662 by weight, so 3 x 20GP beats any 40ft mix
    assert r["recommendation"].startswith("3 x 20GP")


def test_lcl_for_small_shipments():
    r = plan_loading(50, 40, 30, 10, total_cartons=40)  # 2.4 CBM
    assert r["recommendation"].startswith("LCL")


def test_multi_container():
    # caps 20GP 202, 40GP 450, 40HQ 540. 1500 -> 2x40HQ + 1x40GP (cost 4.3) beats 3x40HQ (4.35)
    r = plan_loading(60, 40, 40, 12, total_cartons=1500)
    assert r["recommendation"].startswith("2 x 40HQ + 1 x 40GP")


def test_rate_ratio_changes_mix():
    # 1100 cartons at ratio 1.4: 2x40GP + 1x20GP (cost 3.8) is cheapest. 400 cartons at ratio 2.5: 2x20GP (2.0) beats 1x40GP (2.5)
    cheap40 = plan_loading(60, 40, 40, 12, total_cartons=1100, forty_to_twenty_rate_ratio=1.4)
    assert "2 x 40GP + 1 x 20GP" in cheap40["recommendation"]
    assert "Very tight" in cheap40["recommendation"]
    dear40 = plan_loading(60, 40, 40, 12, total_cartons=400, forty_to_twenty_rate_ratio=2.5)
    assert dear40["recommendation"].startswith("2 x 20GP")


def test_rotation_allowed_can_fit_more():
    up = plan_loading(100, 30, 20, 5, keep_upright=True)
    free = plan_loading(100, 30, 20, 5, keep_upright=False)
    assert free["containers"][0]["cartons_by_space"] >= up["containers"][0]["cartons_by_space"]


def test_bad_carton():
    with pytest.raises(QuoteInputError):
        plan_loading(0, 40, 40, 10)


def test_oversize_carton_warns():
    # 250 cm tall upright: only the 40HQ (269.8 cm inside) takes it
    r = plan_loading(120, 100, 250, 200, total_cartons=10)
    by = {c["container"]: c for c in r["containers"]}
    assert by["20GP"]["max_cartons"] == 0 and by["40HQ"]["max_cartons"] > 0
    assert any("does not fit a 20GP, 40GP" in w for w in r["warnings"])
    assert r["recommendation"].startswith("1 x 40HQ")
