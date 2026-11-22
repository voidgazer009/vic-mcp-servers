from datetime import date

import pytest

from vic_cashflow_forecast import logic
from vic_cashflow_forecast.logic import CashflowInputError

START = date(2026, 1, 5)  # a Monday


def item(label, amount, direction, d, repeat="none", **kw):
    return {"label": label, "amount": amount, "direction": direction, "date": d, "repeat": repeat, **kw}


def test_golden_basic_four_weeks():
    # opening 1000; week1 (Jan 5-11): +2000 invoice on Jan 8; week2 (Jan 12-18): -300 on Jan 15;
    # week3: nothing; week4 (Jan 26-Feb 1): -1500 on Jan 31.
    # closings: 3000, 2700, 2700, 1200
    r = logic.forecast(START, 1000, 4, [item("inv", 2000, "in", date(2026, 1, 8)), item("tool", 300, "out", date(2026, 1, 15)),
                                        item("rent", 1500, "out", date(2026, 1, 31))])
    assert [w["closing_balance"] for w in r["weeks"]] == [3000, 2700, 2700, 1200]
    assert r["lowest_balance"] == 1200 and r["lowest_week"] == 4 and r["first_negative_week"] == 0


def test_golden_monthly_end_of_month_clamp():
    # rent on the 31st monthly from Jan 31: Jan 31, Feb 28, Mar 31 (clamped, anchor stays 31).
    occ = logic.occurrences(date(2026, 1, 31), "monthly", None, date(2026, 3, 31))
    assert occ == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]


def test_golden_weekly_repeat_and_negative():
    # opening 500; -300 every week for 4 weeks (Jan 5, 12, 19, 26): 200, -100, -400, -700 -> negative in week 2
    r = logic.forecast(START, 500, 4, [item("x", 300, "out", date(2026, 1, 5), "weekly")])
    assert [w["closing_balance"] for w in r["weeks"]] == [200, -100, -400, -700]
    assert r["first_negative_week"] == 2
    assert any("negative in week 2" in w for w in r["warnings"])


def test_golden_confidence_weights_inflow():
    # 1000 invoice at 80% confidence = 800 expected; outflows are never discounted
    r = logic.forecast(START, 0, 1, [item("inv", 1000, "in", date(2026, 1, 6), confidence=0.8), item("c", 100, "out", date(2026, 1, 7))])
    assert r["total_inflow"] == 800 and r["closing_balance"] == 700


def test_golden_delay_shifts_week():
    # invoice due Jan 8 (week 1) paid 14 days late -> Jan 22 = week 3
    r = logic.forecast(START, 0, 4, [item("inv", 1000, "in", date(2026, 1, 8), delay_days=14)])
    assert [w["inflow"] for w in r["weeks"]] == [0, 0, 1000, 0]


def test_stress_params():
    base = [item("inv", 1000, "in", date(2026, 1, 8)), item("c", 400, "out", date(2026, 1, 8))]
    r = logic.forecast(START, 0, 4, base, inflow_delay_days=21, inflow_haircut_pct=50)
    # inflow Jan 8 + 21 = Jan 29 (week 4), 50% -> 500; outflow stays in week 1 -> week1 closing -400, week4 closing 100
    assert r["weeks"][0]["closing_balance"] == -400 and r["closing_balance"] == 100


def test_items_before_start_and_outside_window():
    r = logic.forecast(START, 100, 2, [item("old", 50, "out", date(2025, 12, 1)), item("far", 50, "out", date(2026, 6, 1))])
    assert r["closing_balance"] == 100
    assert any("outside" in w for w in r["warnings"])


def test_bad_inputs():
    with pytest.raises(CashflowInputError):
        logic.forecast(START, 0, 0, [])
    with pytest.raises(CashflowInputError):
        logic.occurrences(date(2026, 1, 1), "daily", None, date(2026, 2, 1))
    with pytest.raises(CashflowInputError):
        logic.occurrences(date(2000, 1, 1), "weekly", None, date(2090, 1, 1))
    with pytest.raises(CashflowInputError):
        logic.runway(1000, 0)


def test_golden_runway():
    # cash 6000, expenses 2000, income 500 -> burn 1500 -> 4.0 months
    r = logic.runway(6000, 2000, 500)
    assert r["runway_months"] == 4.0 and r["net_monthly_burn"] == 1500 and not r["sustainable"]
    assert r["months_of_expenses_in_cash"] == 3.0


def test_runway_sustainable_and_growth():
    assert logic.runway(1000, 2000, 2500)["sustainable"] is True
    # cash 1000, exp 1000, income 0 growth: 1 month of cash exactly
    assert logic.runway(1000, 1000, 0)["runway_months"] == 1.0
    assert logic.runway(0, 1000)["runway_months"] == 0.0
