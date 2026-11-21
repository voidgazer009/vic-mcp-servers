"""Pure demurrage / detention day-counting and charge logic. No network, no clock."""
from __future__ import annotations

from datetime import date, timedelta
from itertools import product

MAX_SPAN_DAYS = 400


class DemurrageInputError(ValueError):
    """Raised for input that cannot be calculated."""


def parse_date(s: str, field: str = "date") -> date:
    try:
        return date.fromisoformat(s.strip())
    except (ValueError, AttributeError) as e:
        raise DemurrageInputError(f"{field} must be an ISO date YYYY-MM-DD, got {s!r}") from e


def parse_holidays(items: list[str] | None) -> set[date]:
    return {parse_date(h, "holidays item") for h in (items or [])}


def check_tiers(tiers: list[dict]) -> list[tuple[int, float]]:
    """Return sorted (from_day, rate) tiers. First tier must start at chargeable day 1."""
    if not tiers:
        raise DemurrageInputError("tiers must contain at least one rate tier")
    out = sorted((int(t["from_day"]), float(t["rate"])) for t in tiers)
    if out[0][0] != 1:
        raise DemurrageInputError("the first tier must start at from_day 1 (the first chargeable day)")
    if len({d for d, _ in out}) != len(out):
        raise DemurrageInputError("two tiers start on the same from_day")
    if any(r < 0 for _, r in out):
        raise DemurrageInputError("rates cannot be negative")
    return out


def rate_for(tiers: list[tuple[int, float]], n: int) -> float:
    rate = tiers[0][1]
    for d, r in tiers:
        if d <= n:
            rate = r
    return rate


def is_working(d: date, weekend: tuple[int, ...], holidays: set[date]) -> bool:
    return d.weekday() not in weekend and d not in holidays


def walk(start: date, end: date, free_days: int, free_type: str, charge_type: str, include_start: bool,
         include_end: bool, tiers: list[tuple[int, float]], holidays: set[date], weekend: tuple[int, ...] = (5, 6)):
    """Day by day clock. Returns (days, last_free_day). Each day: date, status free|skipped|charged, charge_day_no, rate."""
    if end < start:
        raise DemurrageInputError("end_date is before start_date")
    if (end - start).days > MAX_SPAN_DAYS:
        raise DemurrageInputError(f"the span is longer than {MAX_SPAN_DAYS} days; check the dates")
    days, free_left, n, last_free = [], free_days, 0, None
    d = start if include_start else start + timedelta(days=1)
    last = end if include_end else end - timedelta(days=1)
    while d <= last:
        work = is_working(d, weekend, holidays)
        if free_left > 0:
            if free_type == "calendar" or work:
                free_left -= 1
                last_free = d
                days.append({"date": d, "status": "free", "charge_day_no": 0, "rate": 0.0})
            else:
                days.append({"date": d, "status": "skipped", "charge_day_no": 0, "rate": 0.0})
        elif charge_type == "working" and not work:
            days.append({"date": d, "status": "skipped", "charge_day_no": 0, "rate": 0.0})
        else:
            n += 1
            days.append({"date": d, "status": "charged", "charge_day_no": n, "rate": rate_for(tiers, n)})
        d += timedelta(days=1)
    return days, last_free


def last_free_day(start: date, free_days: int, free_type: str, include_start: bool, holidays: set[date],
                  weekend: tuple[int, ...] = (5, 6)) -> tuple[date | None, date | None]:
    """(last free day, first chargeable day) by walking forward; calendar charge days after free time."""
    if free_days == 0:
        d = start if include_start else start + timedelta(days=1)
        return None, d
    d = start if include_start else start + timedelta(days=1)
    left = free_days
    while True:
        if free_type == "calendar" or is_working(d, weekend, holidays):
            left -= 1
            if left == 0:
                return d, d + timedelta(days=1)
        d += timedelta(days=1)
        if (d - start).days > MAX_SPAN_DAYS:
            raise DemurrageInputError("free time runs past 400 days; check free_days")


def charges(start, end, free_days, free_type, charge_type, include_start, include_end, tiers, holidays, fixed_fee=0.0):
    days, lfd = walk(start, end, free_days, free_type, charge_type, include_start, include_end, tiers, holidays)
    charged = [x for x in days if x["status"] == "charged"]
    by_tier: dict[float, dict] = {}
    for x in charged:
        t = by_tier.setdefault(x["rate"], {"rate": x["rate"], "days": 0, "amount": 0.0})
        t["days"] += 1
        t["amount"] = round(t["amount"] + x["rate"], 2)
    total = round(sum(x["rate"] for x in charged) + fixed_fee, 2)
    return {"days": days, "last_free_day": lfd, "charged_days": len(charged),
            "free_days_used": sum(1 for x in days if x["status"] == "free"),
            "by_rate": list(by_tier.values()), "total": total}


def explain_invoice(billed: float, start, end, free_days, charge_type, tiers, holidays, fixed_fee=0.0):
    """Try every combination of counting conventions and report which ones reproduce the billed amount."""
    rows = []
    for shift, inc_s, inc_e, ft in product((0, 1), (True, False), (True, False), ("calendar", "working")):
        c = charges(start - timedelta(days=shift), end, free_days, ft, charge_type, inc_s, inc_e, tiers, holidays, fixed_fee)
        rows.append({"started_one_day_earlier": bool(shift), "include_start_day": inc_s, "include_end_day": inc_e, "free_day_type": ft,
                     "charged_days": c["charged_days"], "total": c["total"],
                     "matches_billed": abs(c["total"] - billed) < 0.005, "difference": round(billed - c["total"], 2)})
    return rows
