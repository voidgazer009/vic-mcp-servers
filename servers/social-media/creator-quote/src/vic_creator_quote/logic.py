"""Pure functions for judging influencer / creator quotes. No network, no I/O."""

from __future__ import annotations

import math
import statistics


class QuoteInputError(ValueError):
    """Raised for inputs that cannot produce a meaningful answer."""


def _r(x: float, n: int = 2) -> float:
    return round(x + 0.0, n)


def engagement_rate(posts: list[dict], followers: int | None, exclude_viral: bool) -> dict:
    """Per-post and median engagement rates. Engagements = likes + comments + shares + saves."""
    if not posts:
        raise QuoteInputError("posts must contain at least one post")
    rows = []
    for i, p in enumerate(posts, 1):
        eng = p["likes"] + p["comments"] + p["shares"] + p["saves"]
        views = p["views"]
        if views <= 0:
            raise QuoteInputError(f"post {i}: views must be above 0")
        rows.append({
            "index": i, "views": views, "engagements": eng,
            "er_by_views_pct": _r(eng / views * 100),
            "er_by_followers_pct": _r(eng / followers * 100) if followers else None,
            "viral_outlier": False,
        })
    med_views = statistics.median(r["views"] for r in rows)
    warnings: list[str] = []
    if len(rows) >= 4:
        for r in rows:
            if r["views"] > 3 * med_views:
                r["viral_outlier"] = True
    used = [r for r in rows if not (exclude_viral and r["viral_outlier"])]
    if not used:
        used = rows
    outliers = [r["index"] for r in rows if r["viral_outlier"]]
    if outliers:
        warnings.append(f"Posts {outliers} have more than 3x the median views; the mean is inflated by them. Quote on the median, not the mean.")
    if len(rows) < 10:
        warnings.append(f"Only {len(rows)} posts: use the last 10-12 posts of the same format for a stable median.")
    if any(p.get("likes_only") for p in posts):
        warnings.append("Some posts only had likes: engagement is understated against full-engagement benchmarks.")
    med_views_used = statistics.median(r["views"] for r in used)
    med_eng_used = statistics.median(r["engagements"] for r in used)
    med_er = statistics.median(r["er_by_views_pct"] for r in used)
    mean_views = statistics.mean(r["views"] for r in rows)
    out = {
        "posts": rows,
        "posts_used": len(used),
        "median_views": _r(med_views_used, 0),
        "median_engagements": _r(med_eng_used, 0),
        "median_er_by_views_pct": _r(med_er),
        "mean_views_all_posts": _r(mean_views, 0),
        "median_er_by_followers_pct": _r(statistics.median(r["er_by_followers_pct"] for r in used)) if followers else None,
        "views_to_followers_pct": _r(med_views_used / followers * 100) if followers else None,
        "warnings": warnings,
    }
    return out


def evaluate_quote(fee: float, deliverables: int, avg_views: float, avg_engagements: float | None,
                   followers: int | None, usage_pct_per_month: float, usage_months: int,
                   exclusivity_fee: float, target_cpm: float | None, target_cpe: float | None) -> dict:
    total_views = avg_views * deliverables
    if total_views <= 0:
        raise QuoteInputError("avg_views and deliverables must be above 0")
    warnings: list[str] = []
    base_cpm = fee / total_views * 1000
    usage_fee = fee * usage_pct_per_month / 100 * usage_months
    contract = fee + usage_fee + exclusivity_fee
    eff_cpm = contract / total_views * 1000
    cpe = er_views = None
    if avg_engagements is not None:
        total_eng = avg_engagements * deliverables
        er_views = avg_engagements / avg_views * 100
        if er_views > 100:
            warnings.append("Engagements exceed views for the typical post: check that views and engagements cover the same posts and period.")
        if total_eng > 0:
            cpe = fee / total_eng
        else:
            warnings.append("Zero engagements: cost per engagement is undefined.")
    follower_cpm = fee / followers * 1000 if followers else None
    if follower_cpm is not None:
        warnings.append(f"Follower-based CPM would be {_r(follower_cpm)}; it ignores how many followers actually watch. Judge the quote on {_r(base_cpm)} (per expected view).")
        if avg_views > followers * 3:
            warnings.append("Typical views are more than 3x followers: confirm they are not from a few viral posts.")
    if usage_fee or exclusivity_fee:
        warnings.append(f"Usage and exclusivity add {_r(usage_fee + exclusivity_fee)} on top of the base fee; compare quotes on effective CPM.")
    verdict, gap, max_base = "no_target_given", None, None
    if target_cpm is not None:
        budget = target_cpm * total_views / 1000
        factor = 1 + usage_pct_per_month / 100 * usage_months
        max_base = (budget - exclusivity_fee) / factor
        if max_base <= 0:
            max_base = 0.0
            warnings.append("Exclusivity fee alone already exceeds the budget implied by your target CPM.")
        gap = (eff_cpm / target_cpm - 1) * 100
        verdict = "within_target" if eff_cpm <= target_cpm else "above_target"
        if gap < -50:
            warnings.append("Effective CPM is over 50% below your target: verify audience quality (purchased followers, engagement pods) before celebrating.")
    cpe_verdict = None
    if target_cpe is not None:
        if cpe is None:
            warnings.append("target_cpe given but avg_engagements missing or zero: no CPE verdict.")
        else:
            cpe_verdict = "within_target" if cpe <= target_cpe else "above_target"
    warnings.append("Views are expected performance, not a guarantee; ask for native analytics screenshots of the last 30-90 days.")
    return {
        "expected_total_views": _r(total_views, 0),
        "base_cpm": _r(base_cpm),
        "usage_fee": _r(usage_fee),
        "exclusivity_fee": _r(exclusivity_fee),
        "contract_cost": _r(contract),
        "effective_cpm": _r(eff_cpm),
        "cpe": _r(cpe, 4) if cpe is not None else None,
        "er_by_views_pct": _r(er_views) if er_views is not None else None,
        "follower_based_cpm": _r(follower_cpm) if follower_cpm is not None else None,
        "cpm_verdict": verdict,
        "cpm_gap_pct": _r(gap) if gap is not None else None,
        "cpe_verdict": cpe_verdict,
        "max_base_fee_at_target_cpm": _r(max_base) if max_base is not None else None,
        "warnings": warnings,
    }


def payback(contract_cost: float, net_order_value: float, margin_pct: float, expected_sales: int | None,
            usage_pct_per_month: float, usage_months: int) -> dict:
    per_sale = net_order_value * margin_pct / 100
    if per_sale <= 0:
        raise QuoteInputError("net_order_value x margin_pct must be above 0")
    sales_needed = math.ceil(round(contract_cost / per_sale, 9))
    warnings = ["Direct-response payback ignores brand lift and repeat purchases; use it as a floor, not a verdict."]
    balance = ceiling = None
    if expected_sales is not None:
        gross = expected_sales * per_sale
        balance = gross - contract_cost
        ceiling = gross / (1 + usage_pct_per_month / 100 * usage_months)
        if balance < 0:
            warnings.append("At your expected sales the contract loses money on direct sales alone.")
    return {
        "profit_per_sale": _r(per_sale),
        "sales_to_break_even": sales_needed,
        "expected_balance": _r(balance) if balance is not None else None,
        "base_fee_ceiling": _r(ceiling) if ceiling is not None else None,
        "warnings": warnings,
    }


def counter_offer(creator: str, brand: str, deliverables: int, current_fee: float, proposed_fee: float,
                  currency: str, current_cpm: float | None, target_cpm: float | None, language: str, sender: str) -> dict:
    if proposed_fee >= current_fee:
        raise QuoteInputError("proposed_fee must be below current_fee for a counter-offer; just accept the quote otherwise")
    reason_en = ""
    reason_zh = ""
    if current_cpm is not None and target_cpm is not None:
        reason_en = f" Your quote works out to about {current_cpm:g} per 1,000 expected views; our target for this channel is {target_cpm:g}."
        reason_zh = f"按预期播放量折算，目前报价约为每千次播放 {current_cpm:g}，我们这个渠道的目标是 {target_cpm:g}。"
    if language == "zh":
        subject = f"关于 {brand} 合作报价的回复"
        body = (f"{creator}，你好：\n\n感谢你发来 {deliverables} 条内容 {currency} {current_fee:,.2f} 的报价。我们很喜欢你的内容。"
                f"{reason_zh}我们能接受的预算是 {currency} {proposed_fee:,.2f}。如果使用授权期限、独家条款或交付数量可以调整，我们也乐意再谈。\n\n期待你的回复。\n{sender}")
    else:
        subject = f"Re: {brand} collaboration rate"
        body = (f"Hi {creator},\n\nThanks for the quote of {currency} {current_fee:,.2f} for {deliverables} deliverable(s). We like your content.{reason_en} "
                f"Our budget for this scope is {currency} {proposed_fee:,.2f}. We are happy to adjust usage term, exclusivity or number of deliverables if that helps.\n\nLooking forward to hearing from you.\n{sender}")
    return {"subject": subject, "body": body, "draft_only": True,
            "warnings": ["Draft only: nothing is sent. Check amounts and scope, and keep the paid-partnership disclosure requirement in the contract (e.g. FTC Endorsement Guides)."]}
