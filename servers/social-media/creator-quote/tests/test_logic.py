import pytest

from vic_creator_quote import logic
from vic_creator_quote.logic import QuoteInputError


def test_cpm_golden():
    # 800 / 12000 views x 1000 = 66.67; usage 10%/mo x 3 = 240; contract 1040; 1040/12000x1000 = 86.67
    r = logic.evaluate_quote(800, 1, 12000, None, 80000, 10, 3, 0, None, None)
    assert r["base_cpm"] == 66.67 and r["usage_fee"] == 240 and r["contract_cost"] == 1040 and r["effective_cpm"] == 86.67
    assert r["follower_based_cpm"] == 10.0


def test_max_base_fee_golden():
    # target 50 -> budget 50 x 12 = 600; usage factor 1 + .1x3 = 1.3; 600 / 1.3 = 461.54
    r = logic.evaluate_quote(800, 1, 12000, None, None, 10, 3, 0, 50, None)
    assert r["max_base_fee_at_target_cpm"] == 461.54 and r["cpm_verdict"] == "above_target" and r["cpm_gap_pct"] == 73.33


def test_cpe_and_er():
    # 2 posts x 10000 views = 20000; 500 engagements each = 1000; CPE = 400/1000 = 0.4; ER = 500/10000 = 5%
    r = logic.evaluate_quote(400, 2, 10000, 500, None, 0, 0, 0, 30, 0.5)
    assert r["cpe"] == 0.4 and r["er_by_views_pct"] == 5.0 and r["cpe_verdict"] == "within_target" and r["base_cpm"] == 20.0


def test_payback_golden():
    # profit per sale 50 x 40% = 20; 1040 / 20 = 52 sales; 30 sales -> 600 - 1040 = -440; ceiling 600/1.3 = 461.54
    r = logic.payback(1040, 50, 40, 30, 10, 3)
    assert r["sales_to_break_even"] == 52 and r["expected_balance"] == -440 and r["base_fee_ceiling"] == 461.54


def test_viral_outlier_median():
    posts = [dict(views=v, likes=v // 10, comments=0, shares=0, saves=0) for v in (10000, 11000, 9000, 10000, 200000)]
    r = logic.engagement_rate(posts, 50000, True)
    # median of all = 10000; 200000 > 3x -> outlier; median of remaining four = (10000+10000)/2
    assert r["posts"][4]["viral_outlier"] and r["median_views"] == 10000 and r["posts_used"] == 4
    assert r["median_er_by_views_pct"] == 10.0 and r["views_to_followers_pct"] == 20.0


def test_bad_inputs():
    with pytest.raises(QuoteInputError):
        logic.counter_offer("A", "B", 1, 100, 120, "USD", None, None, "en", "me")
    with pytest.raises(QuoteInputError):
        logic.engagement_rate([], None, True)


def test_counter_offer_draft_only():
    r = logic.counter_offer("Mia", "Acme", 2, 1000, 800, "USD", 66.67, 50, "zh", "Vic")
    assert r["draft_only"] and "800.00" in r["body"] and "66.67" in r["body"]
