"""Pure UTM logic for campaign tagging (no I/O, no network).

Rules come from Google's GA4 help pages (checked 2026-11-15):
- "URL builders: Collect campaign data with custom URLs" (support.google.com/analytics/answer/10917952):
  utm_source / utm_medium / utm_campaign should always be set; values are CASE SENSITIVE
  (Meta != meta, SpringSale != Spring_Sale); lower case is the recommended standard.
- "Default channel group" (support.google.com/analytics/answer/9756891): manual-traffic channel rules,
  evaluated top to bottom; the source lists are Google's spreadsheet, so ours are a subset (approximate).
"""

from __future__ import annotations

import difflib
import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

UTM_KEYS = ["utm_id", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "utm_source_platform", "utm_creative_format", "utm_marketing_tactic"]
MAX_VALUE_LEN = 100  # our convention, not a Google limit: long values are unreadable in reports
MAX_URL_LEN = 2000  # common practical limit for URLs in ads and QR codes

SEARCH = {"google", "bing", "baidu", "yahoo", "duckduckgo", "yandex", "naver", "ecosia", "sogou", "so.com", "360.cn"}
SOCIAL = {"facebook", "fb", "instagram", "ig", "twitter", "x", "t.co", "linkedin", "pinterest", "reddit", "tiktok",
          "snapchat", "weibo", "wechat", "weixin", "line", "telegram", "threads", "quora", "vk", "tumblr", "whatsapp"}
VIDEO = {"youtube", "vimeo", "tiktok", "twitch", "bilibili", "dailymotion"}
SHOPPING = {"amazon", "ebay", "etsy", "walmart", "aliexpress", "shopee", "lazada", "taobao", "tmall", "temu", "shein"}
AI = {"chatgpt", "gemini", "deepseek", "copilot", "grok", "perplexity", "claude"}
PAID_MEDIUM = re.compile(r"^(.*cp.*|ppc|retargeting|paid.*)$", re.I)
SHOP_CAMPAIGN = re.compile(r"^(.*(([^a-df-z]|^)shop|shopping).*)$", re.I)
SOCIAL_MEDIA = {"social", "social-network", "social-media", "sm", "social network", "social media"}
DISPLAY_MEDIA = {"display", "banner", "expandable", "interstitial", "cpm"}
EMAIL_WORDS = {"email", "e-mail", "e_mail", "e mail"}

COMMON_MEDIUMS = {"cpc", "ppc", "email", "social", "organic", "referral", "display", "banner", "affiliate", "sms", "audio",
                  "video", "paid_social", "paid-social", "paid_search", "organic_social", "push", "qr", "podcast", "influencer"}

# Presets for build_campaign_links: platform -> (utm_source, utm_medium)
PLATFORM_PRESETS = {
    "facebook": ("facebook", "paid_social"), "instagram": ("instagram", "paid_social"),
    "linkedin": ("linkedin", "paid_social"), "tiktok": ("tiktok", "paid_social"),
    "x": ("x", "paid_social"), "pinterest": ("pinterest", "paid_social"), "reddit": ("reddit", "paid_social"),
    "youtube": ("youtube", "paid_video"), "google_ads": ("google", "cpc"), "bing_ads": ("bing", "cpc"),
    "baidu": ("baidu", "cpc"), "newsletter": ("newsletter", "email"), "email": ("email", "email"),
    "wechat": ("wechat", "social"), "weibo": ("weibo", "social"), "bilibili": ("bilibili", "social"),
    "xiaohongshu": ("xiaohongshu", "social"), "influencer": ("influencer", "referral"), "podcast": ("podcast", "audio"),
    "sms": ("sms", "sms"), "qr": ("qr", "referral"),
}


class UtmInputError(ValueError):
    """Raised for inputs that cannot produce a usable tagged URL."""


def normalize_value(v: str, sep: str = "_") -> str:
    """Lower-case, trim, collapse whitespace/punctuation runs into one separator. Non-ASCII letters (e.g. Chinese) are kept."""
    v = v.strip().lower()
    v = re.sub(r"[\s_\-+.,;:/\\|]+", sep, v)
    v = re.sub(r"[^\w\-]", "", v, flags=re.UNICODE).strip("_-")
    return v


def _check_url(url: str) -> tuple:
    url = url.strip()
    if not url:
        raise UtmInputError("url is empty.")
    if "://" not in url and not url.startswith("//"):
        raise UtmInputError("url must start with http:// or https:// (got a bare domain or path). Add the scheme.")
    p = urlsplit(url)
    if p.scheme not in ("http", "https"):
        raise UtmInputError(f"Only http and https URLs can carry UTM tags (got '{p.scheme}').")
    if not p.netloc or " " in p.netloc:
        raise UtmInputError("url has no valid host name.")
    return p


def predict_channel(source: str | None, medium: str | None, campaign: str | None = None) -> dict:
    """Approximate GA4 default channel group for manually tagged traffic (rules evaluated in Google's order)."""
    s = (source or "").strip().lower()
    m = (medium or "").strip().lower()
    c = (campaign or "").strip().lower()
    paid = bool(PAID_MEDIUM.match(m))
    why = ""
    ch = "Unassigned"
    if s == "(direct)" and m in ("(not set)", "(none)"):
        ch, why = "Direct", "source (direct) + medium (not set)/(none)"
    elif "cross-network" in c:
        ch, why = "Cross-network", "campaign name contains 'cross-network'"
    elif paid and (s in SHOPPING or SHOP_CAMPAIGN.match(c)):
        ch, why = "Paid Shopping", "paid medium + shopping source or campaign name containing 'shop'"
    elif paid and s in SEARCH:
        ch, why = "Paid Search", "paid medium + search-engine source"
    elif paid and s in SOCIAL:
        ch, why = "Paid Social", "paid medium + social source"
    elif paid and s in VIDEO:
        ch, why = "Paid Video", "paid medium + video source"
    elif m in DISPLAY_MEDIA:
        ch, why = "Display", "medium is display/banner/expandable/interstitial/cpm"
    elif paid:
        ch, why = "Paid Other", "paid medium but the source is not a known search/social/video/shopping site"
    elif s in SHOPPING or SHOP_CAMPAIGN.match(c):
        ch, why = "Organic Shopping", "shopping source or campaign name containing 'shop'"
    elif s in SOCIAL or m in SOCIAL_MEDIA:
        ch, why = "Organic Social", "social source or social medium"
    elif s in VIDEO or "video" in m:
        ch, why = "Organic Video", "video source or medium containing 'video'"
    elif s in SEARCH or m == "organic":
        ch, why = "Organic Search", "search-engine source or medium 'organic'"
    elif m == "ai-assistant":
        ch, why = "AI Assistant", "medium is exactly 'ai-assistant'"
    elif m in ("referral", "app", "link"):
        ch, why = "Referral", "medium is referral/app/link"
    elif s in EMAIL_WORDS or m in EMAIL_WORDS:
        ch, why = "Email", "source or medium is email"
    elif m == "affiliate":
        ch, why = "Affiliates", "medium is affiliate"
    elif m == "audio":
        ch, why = "Audio", "medium is audio"
    elif s == "sms" or m == "sms":
        ch, why = "SMS", "source or medium is sms"
    elif m.endswith("push") or "mobile" in m or "notification" in m or s == "firebase":
        ch, why = "Mobile Push Notifications", "medium ends with push / contains mobile or notification"
    else:
        why = "no GA4 default channel rule matches: the traffic lands in 'Unassigned'"
    warnings = []
    if ch == "Unassigned":
        warnings.append("This source/medium pair falls into 'Unassigned' in GA4's default channel group. Use a standard medium such as cpc, paid_social, email, social, referral, organic.")
    if ch == "Paid Other":
        warnings.append("Paid medium with an unrecognised source ends up in 'Paid Other'. If it is a social or search platform, use its standard source name (e.g. linkedin, google).")
    if s in SOCIAL and m in ("referral",):
        warnings.append("A social source with medium 'referral' is counted as Organic Social, not Referral, because the source rule wins.")
    warnings.append("Approximate: Google's full source lists are longer than the ones used here, so unusual sites may be classified differently in your property.")
    return {"channel": ch, "reason": why, "warnings": warnings}


def _clean(name: str, value: str | None, normalize: bool, notes: list, warnings: list) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    if normalize:
        out = normalize_value(raw)
        if not out:
            raise UtmInputError(f"{name} '{raw}' has no usable characters after cleaning.")
        if out != raw:
            notes.append(f"{name}: '{raw}' -> '{out}'")
        v = out
    else:
        v = raw
        if v != v.lower():
            warnings.append(f"{name} '{v}' has upper-case letters. GA4 treats Meta and meta as different values; lower case is recommended.")
        if re.search(r"\s", v):
            warnings.append(f"{name} '{v}' contains spaces, which become %20 or + and fragment reports. Use _ or -.")
    if len(v) > MAX_VALUE_LEN:
        warnings.append(f"{name} is {len(v)} characters long; keep values under {MAX_VALUE_LEN} so reports stay readable.")
    if re.search(r"[^\x00-\x7f]", v):
        warnings.append(f"{name} contains non-ASCII characters; they are percent-encoded in the URL and show as such in some tools. Prefer ASCII (pinyin or English) for codes you will filter on.")
    return v


def build_url(url: str, source: str, medium: str, campaign: str, id: str | None = None, term: str | None = None,
              content: str | None = None, source_platform: str | None = None, normalize: bool = True) -> dict:
    p = _check_url(url)
    notes: list[str] = []
    warnings: list[str] = []
    vals = {
        "utm_source": _clean("utm_source", source, normalize, notes, warnings),
        "utm_medium": _clean("utm_medium", medium, normalize, notes, warnings),
        "utm_campaign": _clean("utm_campaign", campaign, normalize, notes, warnings),
        "utm_id": _clean("utm_id", id, normalize, notes, warnings),
        "utm_term": _clean("utm_term", term, normalize, notes, warnings),
        "utm_content": _clean("utm_content", content, normalize, notes, warnings),
        "utm_source_platform": _clean("utm_source_platform", source_platform, normalize, notes, warnings),
    }
    for k in ("utm_source", "utm_medium", "utm_campaign"):
        if not vals[k]:
            raise UtmInputError(f"{k} is required: GA4 reports '(not set)' without it.")
    existing = parse_qsl(p.query, keep_blank_values=True)
    replaced = [k for k, _ in existing if k in UTM_KEYS and vals.get(k)]
    if replaced:
        warnings.append("The URL already had UTM parameters (" + ", ".join(sorted(set(replaced))) + "); they were replaced. Check the link was not already tagged by another team.")
    kept = [(k, v) for k, v in existing if not (k in UTM_KEYS and vals.get(k))]
    tags = [(k, vals[k]) for k in UTM_KEYS if vals.get(k)]
    query = urlencode(kept + tags, quote_via=quote)
    out = urlunsplit((p.scheme, p.netloc, p.path, query, p.fragment))
    if not vals["utm_id"]:
        warnings.append("No utm_id: Google recommends it (with source, medium, campaign) to match cost data imported into GA4.")
    if p.fragment and "?" in p.fragment:
        warnings.append("The URL fragment (#...) contains a '?'; browsers never send fragments to the server, so check the page's own routing.")
    if len(out) > MAX_URL_LEN:
        warnings.append(f"The final URL is {len(out)} characters; some ad platforms and QR generators cut URLs above {MAX_URL_LEN}.")
    if vals["utm_medium"] not in COMMON_MEDIUMS:
        warnings.append(f"Medium '{vals['utm_medium']}' is not a common standard value; check the channel prediction before launch.")
    ch = predict_channel(vals["utm_source"], vals["utm_medium"], vals["utm_campaign"])
    warnings += [w for w in ch["warnings"] if "Approximate" not in w]
    return {"url": out, "parameters": {k: v for k, v in vals.items() if v}, "changes": notes,
            "predicted_channel": ch["channel"], "channel_reason": ch["reason"], "warnings": warnings}


def lint_url(url: str) -> dict:
    p = _check_url(url)
    pairs = parse_qsl(p.query, keep_blank_values=True)
    issues: list[dict] = []

    def add(sev: str, msg: str):
        issues.append({"severity": sev, "message": msg})

    present = {}
    counts: dict[str, int] = {}
    for k, v in pairs:
        kl = k.lower()
        if re.match(r"^utm[-_ ]?", kl):
            counts[k] = counts.get(k, 0) + 1
            present[k] = v
    if p.fragment and re.search(r"utm_", p.fragment):
        add("error", "UTM parameters sit after the # fragment; browsers do not send fragments to the server, so GA4 never sees them. Move them before the #.")
    for k in list(present):
        fixed = k.lower().replace("-", "_").replace(" ", "_")
        if k not in UTM_KEYS and fixed in UTM_KEYS:
            add("error", f"Parameter '{k}' must be written exactly '{fixed}' (lower case, underscore); GA4 ignores '{k}'.")
        elif k not in UTM_KEYS:
            close = difflib.get_close_matches(k.lower().replace("-", "_"), UTM_KEYS, n=1, cutoff=0.75)
            add("error", f"Unknown parameter '{k}'" + (f"; did you mean '{close[0]}'?" if close else "; GA4 ignores it."))
    for k, n in counts.items():
        if n > 1:
            add("error", f"'{k}' appears {n} times; only one value is used and which one is not guaranteed.")
    for k in ("utm_source", "utm_medium", "utm_campaign"):
        if k not in present:
            add("error", f"{k} is missing: GA4 will show '(not set)' for it.")
        elif not present[k].strip():
            add("error", f"{k} is empty.")
    if any(k in present for k in UTM_KEYS) and "utm_id" not in present:
        add("info", "No utm_id; Google recommends it to match imported cost data.")
    for k, v in present.items():
        if k not in UTM_KEYS or not v:
            continue
        if v != v.lower():
            add("warning", f"{k}='{v}' has upper-case letters; GA4 values are case sensitive, so '{v}' and '{v.lower()}' become two rows.")
        if re.search(r"\s", v):
            add("warning", f"{k}='{v}' contains spaces; use _ or -.")
        if re.search(r"\{\{.*?\}\}|\{[a-z_]+\}|\[[a-z_]+\]|%7B%7B", v, re.I):
            add("warning", f"{k}='{v}' looks like an unfilled template placeholder; this is only valid if the ad platform substitutes it.")
        if len(v) > MAX_VALUE_LEN:
            add("warning", f"{k} is {len(v)} characters long (over {MAX_VALUE_LEN}).")
    s, m, c = present.get("utm_source"), present.get("utm_medium"), present.get("utm_campaign")
    ch = None
    if s and m:
        ch = predict_channel(s, m, c)
        if ch["channel"] in ("Unassigned", "Paid Other"):
            add("warning", ch["warnings"][0])
    if m and m.lower() not in COMMON_MEDIUMS and m.lower() != "":
        add("info", f"Medium '{m}' is not a common standard value.")
    if len(url) > MAX_URL_LEN:
        add("warning", f"URL is {len(url)} characters (over {MAX_URL_LEN}).")
    if p.scheme == "http":
        add("info", "http link: most sites redirect to https, and redirects can drop query strings. Use https if the site supports it.")
    errs = sum(1 for i in issues if i["severity"] == "error")
    return {"valid": errs == 0, "error_count": errs, "issues": issues, "parameters": present,
            "predicted_channel": ch["channel"] if ch else None}


def campaign_links(url: str, campaign: str, targets: list[dict], utm_id: str | None, normalize: bool = True) -> dict:
    if not targets:
        raise UtmInputError("targets is empty; give at least one platform.")
    seen = set()
    links = []
    warnings: list[str] = []
    for t in targets:
        plat = normalize_value(t["platform"])
        src, med = PLATFORM_PRESETS.get(plat, (None, None))
        src = t.get("source") or src
        med = t.get("medium") or med
        if not src or not med:
            raise UtmInputError(f"Unknown platform '{t['platform']}'. Known: {', '.join(sorted(PLATFORM_PRESETS))}; or pass source and medium for it.")
        r = build_url(url, src, med, campaign, id=utm_id, content=t.get("content"), normalize=normalize)
        key = r["url"]
        if key in seen:
            warnings.append(f"Duplicate link for platform '{plat}' (same content): add different utm_content values to tell placements apart.")
        seen.add(key)
        links.append({"platform": plat, "url": r["url"], "predicted_channel": r["predicted_channel"],
                      "warnings": [w for w in r["warnings"] if not w.startswith("No utm_id")]})
    if not utm_id:
        warnings.append("No utm_id: Google recommends it to match imported cost data.")
    return {"links": links, "warnings": warnings}
