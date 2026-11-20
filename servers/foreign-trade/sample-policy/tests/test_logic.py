"""Golden tests, all hand-calculated."""
import pytest

from vic_sample_policy.logic import SamplePolicyInputError, credit, draft_terms, quote_package, roi, triage

ITEMS = [{"qty": 2, "unit_cost": 10, "prep_fee": 0}, {"qty": 1, "unit_cost": 30, "prep_fee": 20}]


def tri(**kw):
    base = dict(email_type="corporate", company_verified=None, specs_given=False, target_qty_given=False, asks_testing_details=False,
                refuses_any_cost=False, many_models_no_project=False, residential_address=False, unanswered_samples=0,
                pressure_to_ship=False, met_in_person=False, customized=False, sample_value=0, value_threshold=50, has_courier_account=True)
    base.update(kw)
    return triage(**base)


def row(res, tier):
    return next(r for r in res["rows"] if r["tier"] == tier)


def test_quote_cost_price():
    # product = 2*10 + 1*30 = 50; prep = 20; handling 5; charge = 50 + 20 + 5 = 75; freight 60
    q = quote_package(ITEMS, 60, 5, 0)
    assert (q["product_cost"], q["prep_total"], q["sample_charge"]) == (50, 20, 75)
    # free collect: outlay 75, buyer 0 -> -75
    assert row(q, "FREE_COLLECT")["your_net_if_no_order"] == -75
    # prepaid freight: outlay 75 + 60 = 135, credit 60
    r = row(q, "FREE_FREIGHT_CREDIT")
    assert (r["your_cash_outlay"], r["credit_on_first_order"], r["your_net_if_no_order"]) == (135, 60, -135)
    # refundable fee: buyer pays 75 + 60 = 135, outlay 135 -> net 0, credit only the 75 fee
    r = row(q, "FEE_CREDIT")
    assert (r["buyer_pays_you_now"], r["your_net_if_no_order"], r["credit_on_first_order"]) == (135, 0, 75)


def test_quote_markup():
    # 20% markup: 50*1.2 = 60; charge = 60 + 20 + 5 = 85; buyer pays 85 + 60 = 145; outlay 135 -> +10
    r = row(quote_package(ITEMS, 60, 5, 20), "FULL_PAID")
    assert (r["buyer_pays_you_now"], r["your_net_if_no_order"], r["credit_on_first_order"]) == (145, 10, 0)


def test_quote_empty_rejected():
    with pytest.raises(SamplePolicyInputError):
        quote_package([], 10, 0, 0)


def test_roi_break_even():
    # order profit = 5000*20% = 1000; A = 1000 + 0 - 60 - 135 = 805; B = -135; p=10%
    # EV = 0.1*805 + 0.9*(-135) = 80.5 - 121.5 = -41; break-even = 135/(805+135) = 14.36%
    r = roi(135, 0, 60, 5000, 20, 10)
    assert (r["profit_if_order"], r["profit_if_no_order"], r["expected_profit"], r["break_even_conversion_pct"]) == (805, -135, -41, 14.36)
    assert any("negative" in w for w in r["warnings"])


def test_roi_never_loses():
    # buyer paid 100, outlay 80 -> B = +20, no break-even needed
    assert roi(80, 100, 0, 1000, 10, 5)["break_even_conversion_pct"] is None


def test_credit_cases():
    kw = dict(fee=75, prep=0, freight=60, scope=["sample_fee"], cap_pct=100, min_order=2000, valid_days=180)
    # in scope: only the 75 fee; order 5000 -> payable 4925
    r = credit(sample_date="2026-01-01", order_date="2026-03-01", order_value=5000, **kw)
    assert (r["credit"], r["payable_after_credit"]) == (75, 4925)
    # cap 1% of 5000 = 50
    assert credit(sample_date="2026-01-01", order_date="2026-03-01", order_value=5000, **{**kw, "cap_pct": 1})["credit"] == 50
    # below minimum
    r = credit(sample_date="2026-01-01", order_date="2026-03-01", order_value=1000, **kw)
    assert r["credit"] == 0 and r["payable_after_credit"] == 1000
    # 2026-01-01 -> 2026-08-01 = 31+28+31+30+31+30+31 = 212 days > 180
    r = credit(sample_date="2026-01-01", order_date="2026-08-01", order_value=5000, **kw)
    assert r["days_since_sample"] == 212 and r["credit"] == 0


def test_credit_bad_dates():
    kw = dict(fee=1, prep=0, freight=0, scope=["sample_fee"], cap_pct=100, min_order=0, valid_days=30, order_value=10)
    with pytest.raises(SamplePolicyInputError):
        credit(sample_date="2026-13-01", order_date="2026-03-01", **kw)
    with pytest.raises(SamplePolicyInputError):
        credit(sample_date="2026-03-02", order_date="2026-03-01", **kw)


def test_triage_scores():
    # free e-mail -10 -> 40 -> FULL_PAID
    assert (lambda r: (r["score"], r["tier"]))(tri(email_type="free")) == (40, "FULL_PAID")
    # 50 + 10 corporate + 10 specs + 10 qty + 15 verified = 95 -> FREE_COLLECT
    assert (lambda r: (r["score"], r["tier"]))(tri(company_verified=True, specs_given=True, target_qty_given=True)) == (95, "FREE_COLLECT")
    # 50 + 10 + 10 = 70 -> FREE_FREIGHT_CREDIT
    assert tri(specs_given=True)["tier"] == "FREE_FREIGHT_CREDIT"
    # same 95 but customised -> floor FEE_CREDIT; no courier account -> FREE_FREIGHT_CREDIT
    big = dict(company_verified=True, specs_given=True, target_qty_given=True)
    assert tri(customized=True, **big)["tier"] == "FEE_CREDIT"
    assert tri(has_courier_account=False, **big)["tier"] == "FREE_FREIGHT_CREDIT"
    # lookalike: 50 - 25 + 10 + 10 = 45 -> FEE_CREDIT, but hard flag forces FULL_PAID
    assert tri(email_type="lookalike", specs_given=True, target_qty_given=True)["tier"] == "FULL_PAID"


def test_triage_floor_and_no_sample():
    # sample value 80 >= 50 threshold -> never free
    assert tri(company_verified=True, specs_given=True, target_qty_given=True, sample_value=80)["tier"] == "FEE_CREDIT"
    # 50 - 10 free - 20 refuses - 10 many models - 10 pressure = 0 -> NO_SAMPLE
    r = tri(email_type="free", refuses_any_cost=True, many_models_no_project=True, pressure_to_ship=True)
    assert (r["score"], r["tier"]) == (0, "NO_SAMPLE") and len(r["red_flags"]) == 4


def test_triage_unanswered_cap():
    # 3 earlier unanswered -> -30, capped at 3; 2 or more forces FULL_PAID
    r = tri(unanswered_samples=9)
    assert r["score"] == 50 + 10 - 30 and r["tier"] == "FULL_PAID"


def test_draft_terms():
    d = draft_terms("FEE_CREDIT", "USD", 75, 60, "", 2000, 180)
    assert "USD 75.00" in d["english"] and "freight excluded" in d["english"] and "180 days" in d["english"]
    with pytest.raises(SamplePolicyInputError):
        draft_terms("NO_SAMPLE", "USD", 0, 0, "", 0, 30)


def test_warnings_added():
    assert any("all 0" in w for w in quote_package([{"qty": 1, "unit_cost": 0}], 0, 0, 0)["warnings"])
    # eligible 80 (50 fee + 30 freight) vs order 60 at 100% cap -> credit 60, reason names the order value
    r = credit(50, 0, 30, ["sample_fee", "freight"], 100, 0, 30, "2026-01-01", "2026-01-02", 60)
    assert r["credit"] == 60 and "cannot exceed the order value" in r["reasons"][0]
    assert any("minimum order" in w for w in draft_terms("FEE_CREDIT", "USD", 75, 60, "", 0, 30)["warnings"])
