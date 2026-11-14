"""Golden tests, every number hand-calculated."""
import pytest

from vic_solo_pricing import logic as L


def test_hourly_rate_golden():
    # net 60000, tax 25% -> pretax 60000/0.75 = 80000; + expenses 6000 = 86000 (buffer 0, fee 0)
    # weeks 52-6 = 46; hours 46*40*0.6 = 1104; rate 86000/1104 = 77.8986
    r = L.hourly_rate(60000, 6000, 25, 6, 40, 60, 0, 0, 5)
    assert r["pre_tax_profit_needed"] == 80000.0
    assert r["billable_hours_per_year"] == 1104.0
    assert r["hourly_rate"] == 77.9
    # day rate: 40*0.6/5 = 4.8 billable h/day -> 77.8986*4.8 = 373.91
    assert r["day_rate"] == 373.91
    # naive: 66000 / (46*40) = 35.87
    assert r["naive_rate_ignoring_tax_and_utilization"] == 35.87


def test_hourly_rate_no_tax_full_utilization():
    # (50000+10000)/(48*30*1.0) = 60000/1440 = 41.6667
    assert L.hourly_rate(50000, 10000, 0, 4, 30, 100, 0, 0, 5)["hourly_rate"] == 41.67


def test_hourly_rate_with_fee():
    # 86000 / 0.97 = 88659.79 ; /1104 = 80.3081
    r = L.hourly_rate(60000, 6000, 25, 6, 40, 60, 0, 3, 5)
    assert r["revenue_to_invoice"] == 88659.79 and r["hourly_rate"] == 80.31


def test_fixed_project_golden():
    # hours 40*1.2 + 2*3 = 54; labour 54*80 = 4320; +100 = 4420; /0.97 = 4556.70
    r = L.fixed_project_price(40, 80, 20, 2, 3, 100, 3)
    assert r["planned_hours"] == 54.0 and r["quote_price"] == 4556.7
    # at 150% hours: 81 h, labour income 4320/81 = 53.33
    assert r["scenarios"][2]["effective_hourly_rate"] == 53.33


def test_fee_gross_up_golden():
    # (100+0.30)/(1-0.029) = 103.2956 ; naive 100*1.029+0.3 = 103.2 -> shortfall 0.0956
    r = L.fee_gross_up(100, 2.9, 0.30, 0)
    assert r["invoice_amount"] == 103.3 and r["naive_markup_amount"] == 103.2
    # with 0.5% fx: 100.3/0.966 = 103.8302
    assert L.fee_gross_up(100, 2.9, 0.30, 0.5)["invoice_amount"] == 103.83


def test_discount_golden():
    # margin 60 -> after 10% off 50 -> 60/50-1 = 20%
    r = L.discount_impact(100, 40, 10, 100)
    assert r["required_volume_increase_pct"] == 20.0 and r["required_units"] == 120.0
    # 40% off: margin 20 -> 200% more
    assert L.discount_impact(100, 40, 40, 100)["required_volume_increase_pct"] == 200.0


def test_discount_impossible():
    r = L.discount_impact(100, 40, 60, 10)
    assert r["required_volume_increase_pct"] is None and r["warnings"]


def test_real_rate_golden():
    # fees 5000*3% = 150; net 5000-150-100 = 4750; /70 = 67.857
    r = L.real_hourly_rate(5000, 3, 100, 70, 80)
    assert r["net_earned"] == 4750.0 and r["real_hourly_rate"] == 67.86 and r["vs_target_pct"] == -15.2


def test_errors():
    with pytest.raises(L.PricingInputError):
        L.hourly_rate(1, 0, 25, 52, 40, 60, 0, 0, 5)
    with pytest.raises(L.PricingInputError):
        L.discount_impact(10, 10, 5, 1)


def test_real_rate_loss_has_no_percent_below_target_message():
    # net = 1000 - 0 - 1200 = -200 ; /50 = -4.00 ; loss warning only
    r = L.real_hourly_rate(1000, 0, 1200, 50, 40)
    assert r["real_hourly_rate"] == -4.0
    assert not any("below your target" in w for w in r["warnings"]) and any("lost money" in w for w in r["warnings"])
