import pytest

from datetime import date

from vic_demurrage.logic import (DemurrageInputError, charges, check_tiers, explain_invoice, last_free_day, parse_date)

T1 = check_tiers([{"from_day": 1, "rate": 150}, {"from_day": 4, "rate": 300}])
D = date


def test_golden_demurrage_calendar():
    # Mon 2026-11-16 .. Wed 2026-11-25 inclusive = 10 days; 5 free -> 5 charged: 3*150 + 2*300 = 1050
    c = charges(D(2026, 11, 16), D(2026, 11, 25), 5, "calendar", "calendar", True, True, T1, set())
    assert c["charged_days"] == 5 and c["total"] == 1050 and c["last_free_day"] == D(2026, 11, 20)


def test_golden_detention():
    # Wed 11-25 .. Tue 12-02 inclusive = 8 days; 4 free -> 4 charged at flat 100 = 400
    t = check_tiers([{"from_day": 1, "rate": 100}])
    assert charges(D(2026, 11, 25), D(2026, 12, 2), 4, "calendar", "calendar", True, True, t, set())["total"] == 400


def test_golden_working_free_days():
    # start Mon 11-16, 6 working free days: 16,17,18,19,20 (5), weekend skipped, Mon 23 = 6th -> LFD 11-23, charge from 11-24
    assert last_free_day(D(2026, 11, 16), 6, "working", True, set()) == (D(2026, 11, 23), D(2026, 11, 24))
    # with Mon 11-23 a holiday the 6th day moves to Tue 24
    assert last_free_day(D(2026, 11, 16), 6, "working", True, {D(2026, 11, 23)}) == (D(2026, 11, 24), D(2026, 11, 25))


def test_golden_working_free_calendar_charged():
    # 5 working free days from Mon 11-16 -> LFD Fri 20. Out Tue 11-24 incl: charged 21,22,23,24 = 4 days: 150*3+300 = 750
    c = charges(D(2026, 11, 16), D(2026, 11, 24), 5, "working", "calendar", True, True, T1, set())
    assert c["charged_days"] == 4 and c["total"] == 750


def test_start_end_flags():
    # exclude start day and end day: 11-17..11-24 = 8 days, 5 free -> 3 charged = 450
    assert charges(D(2026, 11, 16), D(2026, 11, 25), 5, "calendar", "calendar", False, False, T1, set())["total"] == 450


def test_explain_finds_off_by_one():
    rows = explain_invoice(1050, D(2026, 11, 16), D(2026, 11, 25), 5, "calendar", T1, set())
    assert any(r["matches_billed"] and r["include_start_day"] and r["include_end_day"] and r["free_day_type"] == "calendar" for r in rows)
    assert len(rows) == 16
    # billed 1350 = one extra 300-rate day: reproduced only when the clock started one day earlier (11 days, 6 charged: 450 + 3*300)
    rows = explain_invoice(1350, D(2026, 11, 16), D(2026, 11, 25), 5, "calendar", T1, set())
    assert any(r["matches_billed"] and r["started_one_day_earlier"] for r in rows)


def test_zero_free_and_fixed_fee():
    t = check_tiers([{"from_day": 1, "rate": 10}])
    # 3 days inclusive, no free, 3*10 + 25 fee = 55
    assert charges(D(2026, 1, 5), D(2026, 1, 7), 0, "calendar", "calendar", True, True, t, set(), 25)["total"] == 55
    assert last_free_day(D(2026, 1, 5), 0, "calendar", True, set())[0] is None


def test_bad_input():
    for bad in ([], [{"from_day": 2, "rate": 5}], [{"from_day": 1, "rate": 5}, {"from_day": 1, "rate": 6}]):
        with pytest.raises(DemurrageInputError):
            check_tiers(bad)
    with pytest.raises(DemurrageInputError):
        parse_date("2026-13-01")
    with pytest.raises(DemurrageInputError):
        charges(D(2026, 2, 2), D(2026, 1, 1), 1, "calendar", "calendar", True, True, T1, set())
    with pytest.raises(DemurrageInputError):
        charges(D(2024, 1, 1), D(2026, 1, 1), 1, "calendar", "calendar", True, True, T1, set())
