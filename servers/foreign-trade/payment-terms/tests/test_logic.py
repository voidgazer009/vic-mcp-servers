"""Golden tests. Base case: order 10,000, cost 70% = 7,000, production 30 d, shipping 25 d, capital cost 8%/yr."""
import pytest

from vic_payment_terms.logic import PaymentTermsInputError, check_clause, compare_terms, recommend, resolve_term

BASE = dict(order_value=10000, cost_pct=70, production_days=30, shipping_days=25, annual_cost_of_capital_pct=8)


def row(res, term):
    return next(r for r in res["rows"] if r["term"] == term)


def test_advance_has_no_financing_cost():
    # 100% cash on day 0 covers the 7,000 cost at once: interest 0, net = 10,000 - 7,000 = 3,000
    r = row(compare_terms(**BASE), "TT_ADVANCE")
    assert r["financing_cost"] == 0 and r["net_profit"] == 3000.0 and r["unsecured_at_shipment"] == 0


def test_deposit_balance_before_release():
    # 3,000 deposit at day 0 -> 4,000 un-recovered for 30 days: 4000*0.08*30/365 = 26.30
    r = row(compare_terms(**BASE), "TT_DEPOSIT")
    assert r["financing_cost"] == 26.30 and r["net_profit"] == 2973.70 and r["cost_recovered_day"] == 30


def test_open_account_60_days():
    # paid on day 30+60 = 90, nothing before: 7000*0.08*90/365 = 138.08; net 3000-138.08 = 2861.92
    r = row(compare_terms(**BASE), "OA")
    assert r["financing_cost"] == 138.08 and r["net_profit"] == 2861.92 and r["unsecured_pct_of_order"] == 100.0


def test_lc_sight_includes_fee_and_bank_days():
    # cash day = 30 ship + 7 presentation + 5 bank days = 42: 7000*0.08*42/365 = 64.44; fee 1% = 100
    r = row(compare_terms(**BASE), "LC_SIGHT")
    assert r["last_cash_day"] == 42 and r["financing_cost"] == 64.44 and r["fees"] == 100.0 and r["net_profit"] == 2835.56


def test_after_bl_balance_is_unsecured():
    # deposit 3000 day 0; 7000 on day 37; 4000*0.08*37/365 = 32.44; unsecured 70% = 7,000
    r = row(compare_terms(**BASE), "TT_AFTER_BL")
    assert r["financing_cost"] == 32.44 and r["unsecured_at_shipment"] == 7000.0


def test_lowest_risk_is_advance():
    assert compare_terms(**BASE)["lowest_risk_term"] == "TT_ADVANCE"


def test_filter_terms_and_aliases():
    res = compare_terms(**BASE, terms=["O/A", "L/C"])
    assert {r["term"] for r in res["rows"]} == {"OA", "LC_SIGHT"}
    assert resolve_term(" d/p ") == "DP"


def test_bad_inputs():
    with pytest.raises(PaymentTermsInputError):
        resolve_term("COD")
    with pytest.raises(PaymentTermsInputError):
        compare_terms(**{**BASE, "order_value": 0})
    with pytest.raises(PaymentTermsInputError):
        check_clause("short")
    with pytest.raises(PaymentTermsInputError):
        recommend(0, "new", "low", False, False, None)


def test_recommend_new_big_order_prefers_lc_and_counters_oa():
    r = recommend(50000, "new", "medium", True, False, "O/A")
    assert r["recommendations"][0]["term"] == "LC_SIGHT"
    assert "Counter with LC_SIGHT" in r["response_to_buyer_request"]
    assert any("Made-to-order" in w for w in r["warnings"])


def test_recommend_insured_repeat_allows_oa():
    assert recommend(30000, "paid_history", "low", False, True, None)["recommendations"][0]["term"] == "OA"


def test_soft_clause_is_critical():
    r = check_clause("L/C at sight. Payment against inspection certificate signed by the applicant. USD, bank charges for buyer, confirmed, late interest 0.05%/day")
    assert r["verdict"] == "DO_NOT_ACCEPT" and r["findings"][0]["rule"] == "SOFT_APPLICANT_CERT"


def test_chinese_soft_clause_and_oa():
    r = check_clause("付款方式：信用证，需附买方签署的验货证书；其余月结60天")
    rules = {f["rule"] for f in r["findings"]}
    assert "SOFT_APPLICANT_CERT" in rules and "OPEN_ACCOUNT" in rules


def test_pay_after_receipt_and_third_party():
    r = check_clause("Payment: T/T 100% within 15 days after receipt of goods, may be paid by a third party account. USD.")
    rules = {f["rule"] for f in r["findings"]}
    assert {"PAY_AFTER_RECEIPT", "THIRD_PARTY_PAYER"} <= rules and r["verdict"] == "RENEGOTIATE"


def test_clean_clause_is_not_critical():
    r = check_clause("Payment: 30% T/T deposit within 3 days of PO, 70% before shipment. Currency USD. All bank charges outside seller's country for buyer's account. Late payment interest 0.05% per day.")
    assert r["verdict"] == "LOOKS_OK"


def test_vague_tt_flagged():
    r = check_clause("Payment by T/T, in USD, our bank charges for the seller side, late interest applies")
    assert any(f["rule"] == "VAGUE_TT" for f in r["findings"])


def test_copy_of_bl_variants_and_chinese_late_interest():
    for t in ("70% against copy of BL, USD", "balance against B/L copy, USD", "尾款见提单副本付清，美元"):
        assert any(f["rule"] == "COPY_BL_BALANCE" for f in check_clause(t)["findings"]), t
    r = check_clause("30%定金，70%发货前付清，币种美元，逾期按日加收万分之五利息，银行费用买方承担")
    assert r["verdict"] == "LOOKS_OK", r["findings"]


def test_unrelated_word_not_flagged():
    # a clause that merely says 'balance' with no copy-of-BL wording must not trigger COPY_BL_BALANCE
    r = check_clause("Balance 70% before shipment, USD, bank charges for buyer, late interest 0.05% per day")
    assert not any(f["rule"] == "COPY_BL_BALANCE" for f in r["findings"])
