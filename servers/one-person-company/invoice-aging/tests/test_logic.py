from datetime import date

import pytest

from vic_invoice_aging import logic
from vic_invoice_aging.logic import InvoiceInputError


def test_due_date_net30():
    # 2026-01-15 + 30 days: 16 days left in Jan (to 31st) + 14 in Feb = 2026-02-14 (a Saturday)
    r = logic.due_date(date(2026, 1, 15), 30)
    assert r["due_date"] == "2026-02-14" and r["weekday"] == "Saturday" and any("Saturday" in w for w in r["warnings"])


def test_due_date_eom():
    # EOM+30 from 15 Jan 2026: 31 Jan + 30 days = 2 Mar 2026 (Feb has 28 days)
    assert logic.due_date(date(2026, 1, 15), 30, True)["due_date"] == "2026-03-02"


def test_due_date_long_terms_warn():
    assert any("60 days" in w for w in logic.due_date(date(2026, 1, 5), 90)["warnings"])


def test_eu_interest_golden():
    # 10000 x (2% + 8%) x 30 / 365 = 10000 x 0.10 x 0.0821918 = 82.19; plus EUR 40 = 122.19.  31 Jan -> 2 Mar = 30 days
    r = logic.late_interest(10000, date(2026, 1, 31), date(2026, 3, 2), "eu", 2.0, None, 0)
    assert r["days_overdue"] == 30 and r["interest"] == 82.19 and r["fixed_compensation"] == 40 and r["total_claim"] == 122.19


def test_uk_interest_and_fixed_sums():
    # 10000 x 12% x 30/365 = 98.63; fixed GBP 100 at >= 10000
    r = logic.late_interest(10000, date(2026, 1, 31), date(2026, 3, 2), "uk", 4.0, None, 0)
    assert r["interest"] == 98.63 and r["fixed_compensation"] == 100
    # 500 x 12% x 61/365 = 10.03; fixed 40 below 1000
    r = logic.late_interest(500, date(2026, 1, 1), date(2026, 3, 3), "uk", 4.0, None, 0)
    assert r["days_overdue"] == 61 and r["interest"] == 10.03 and r["fixed_compensation"] == 40
    assert logic.uk_fixed_sum(999.99) == 40 and logic.uk_fixed_sum(1000) == 70 and logic.uk_fixed_sum(9999.99) == 70


def test_interest_not_overdue_and_errors():
    assert logic.late_interest(100, date(2026, 5, 1), date(2026, 5, 1), "eu", 2, None, 0)["total_claim"] == 0
    with pytest.raises(InvoiceInputError):
        logic.late_interest(100, date(2026, 5, 1), date(2026, 6, 1), "eu", None, None, 0)
    with pytest.raises(InvoiceInputError):
        logic.late_interest(100, date(2026, 5, 1), date(2026, 6, 1), "custom", None, None, 0)


def test_aging_golden():
    inv = [
        {"invoice_id": "A", "client": "X", "amount": 1000, "due_date": date(2026, 11, 28)},  # as_of 11-18: not due (-10)
        {"invoice_id": "B", "client": "X", "amount": 400, "due_date": date(2026, 11, 8)},    # 10 days -> 1_30
        {"invoice_id": "C", "client": "Y", "amount": 2000, "paid_amount": 500, "due_date": date(2026, 8, 10)},  # 100 days, open 1500 -> over_90
        {"invoice_id": "D", "client": "Y", "amount": 300, "paid_amount": 300, "due_date": date(2026, 9, 1)},  # paid, skipped
    ]
    r = logic.age_invoices(date(2026, 11, 18), inv)
    assert r["outstanding"] == 2900 and r["overdue_total"] == 1900 and r["overdue_pct"] == 65.5
    assert {b["bucket"]: b["amount"] for b in r["buckets"]} == {"not_due": 1000, "1_30": 400, "31_60": 0, "61_90": 0, "over_90": 1500}
    assert r["overdue_invoices"][0]["invoice_id"] == "C" and r["overdue_invoices"][0]["days_overdue"] == 100
    assert r["by_client"][0] == {"client": "Y", "open_amount": 1500} and r["by_client"][1]["open_amount"] == 1400
    assert any("fully paid" in w for w in r["warnings"]) and any("over 90" in w for w in r["warnings"])


def test_aging_boundaries_and_errors():
    assert [logic.bucket_of(d) for d in (0, 1, 30, 31, 60, 61, 90, 91)] == ["not_due", "1_30", "1_30", "31_60", "31_60", "61_90", "61_90", "over_90"]
    with pytest.raises(InvoiceInputError):
        logic.age_invoices(date(2026, 1, 1), [])
    with pytest.raises(InvoiceInputError):
        logic.age_invoices(date(2026, 1, 1), [{"invoice_id": "A", "client": "X", "amount": 10, "paid_amount": 20, "due_date": date(2026, 1, 1)}])


def test_reminder_stages():
    assert [logic.reminder_stage(d) for d in (-3, 0, 1, 7, 8, 30, 31, 60, 61)] == ["pre_due", "pre_due", "friendly", "friendly", "firm", "firm", "formal", "formal", "final"]
    r = logic.reminder_draft("Ann", "INV-1", 1200, "USD", 45, "Vic", "en", 15.5)
    assert r["draft_only"] and "INV-1" in r["subject"] and "USD 1,200.00" in r["body"] and "15.50" in r["body"]
    assert "逾期" in logic.reminder_draft("王", "INV-1", 10, "CNY", 3, "Vic", "zh", None)["body"]
