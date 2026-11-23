"""Pure functions: count text the way each platform counts it and lint a post against its limits.

Sources (checked 2026-11-23): X docs "Counting characters" + twitter-text config v3; AT Protocol app.bsky.feed.post lexicon;
Meta Threads posts docs; Mastodon StatusLengthValidator; Instagram Help Center + Graph API media reference;
TikTok Content Posting API; LinkedIn Help; YouTube Data API videos resource; Pinterest API v5 OpenAPI.
"""

from __future__ import annotations

import re
import unicodedata

class CaptionInputError(ValueError):
    """Raised for input the tools cannot process."""


URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.I)
HASHTAG_RE = re.compile(r"(?<![\w&/#])#(?!\d+\b)([\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+)")
MENTION_RE = re.compile(r"(?<![\w@/.])@([A-Za-z0-9_][A-Za-z0-9_.-]*)(@[A-Za-z0-9.-]+)?")
PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}|\[(?:insert|link|url|todo|tbd)[^\]]*\]|\bTODO\b|\bXXX+\b|lorem ipsum", re.I)
TRAILING_PUNCT = ".,;:!?)]}'\u3002\uff0c\uff01\uff1f\u3001"

# id -> spec. kind: "post" (whole post text) or a titled field.
PLATFORMS: dict[str, dict] = {
    "x": {"name": "X (Twitter)", "limit": 280, "unit": "weighted", "premium_limit": 25000,
          "rule": "Weighted count: CJK and emoji = 2, other text = 1, every link = 23.",
          "source": "https://docs.x.com/fundamentals/counting-characters"},
    "bluesky": {"name": "Bluesky", "limit": 300, "unit": "graphemes", "byte_limit": 3000,
                "rule": "300 graphemes (what a reader sees as one character) and at most 3,000 UTF-8 bytes; links count at full length.",
                "source": "https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/feed/post.json"},
    "threads": {"name": "Threads", "limit": 500, "unit": "characters (emoji = UTF-8 bytes)", "max_links": 5,
                "rule": "500 characters, each emoji counted as its UTF-8 byte length; at most 5 unique links.",
                "source": "https://developers.facebook.com/docs/threads/posts"},
    "mastodon": {"name": "Mastodon", "limit": 500, "unit": "graphemes (links 23, mentions = username)",
                 "rule": "Server default 500 (each server can change it); links count 23, a mention counts only its username, the content warning counts too.",
                 "source": "https://github.com/mastodon/mastodon/blob/main/app/validators/status_length_validator.rb"},
    "linkedin": {"name": "LinkedIn post", "limit": 3000, "unit": "characters",
                 "rule": "3,000 characters; LinkedIn does not document the counting unit.",
                 "source": "https://www.linkedin.com/help/linkedin/answer/a528176"},
    "instagram": {"name": "Instagram caption", "limit": 2200, "unit": "characters", "max_hashtags_help": 5, "max_hashtags_api": 30, "max_mentions": 20,
                  "rule": "2,200 characters, 20 @ tags. Help Center says 5 hashtags; Meta's API reference still says 30.",
                  "source": "https://help.instagram.com/351460621611097"},
    "tiktok": {"name": "TikTok video caption (API)", "limit": 2200, "unit": "UTF-16 units",
               "rule": "2,200 UTF-16 units through the posting API; many emoji use two units. The app composer may allow more.",
               "source": "https://developers.tiktok.com/doc/content-posting-api-reference-direct-post"},
    "youtube_title": {"name": "YouTube title", "limit": 100, "unit": "characters", "forbid": "<>",
                      "rule": "100 characters; < and > are not allowed.",
                      "source": "https://developers.google.com/youtube/v3/docs/videos"},
    "youtube_description": {"name": "YouTube description", "limit": 5000, "unit": "UTF-8 bytes", "forbid": "<>",
                            "rule": "5,000 bytes (non-Latin text and emoji use several); < and > are not allowed.",
                            "source": "https://developers.google.com/youtube/v3/docs/videos"},
    "pinterest_title": {"name": "Pinterest pin title", "limit": 100, "unit": "characters",
                        "rule": "100 characters; the first ~40 are most likely to show.",
                        "source": "https://github.com/pinterest/api-description/blob/main/v5/openapi.yaml"},
    "pinterest_description": {"name": "Pinterest pin description", "limit": 800, "unit": "characters",
                              "rule": "800 characters through the API (many tables still say 500).",
                              "source": "https://github.com/pinterest/api-description/blob/main/v5/openapi.yaml"},
    "facebook": {"name": "Facebook post", "limit": None, "unit": "characters",
                 "rule": "No limit is documented; the often-quoted 63,206 comes from a 2011 report, so none is enforced here.",
                 "source": "https://www.facebook.com/business/help"},
}

# Where the post is cut behind "see more": measured by others, NOT published by the platforms.
FOLDS = {"instagram": 125, "linkedin": 210}

ALIASES = {"twitter": "x", "bsky": "bluesky", "ig": "instagram", "li": "linkedin", "yt_title": "youtube_title",
           "youtube": "youtube_description", "yt_description": "youtube_description", "pinterest": "pinterest_description",
           "fb": "facebook", "tt": "tiktok", "mastodon.social": "mastodon"}


def resolve_platforms(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in names:
        k = n.strip().lower().replace(" ", "_").replace("-", "_")
        k = ALIASES.get(k, k)
        if k not in PLATFORMS:
            raise CaptionInputError(f"Unknown platform '{n}'. Use one of: {', '.join(PLATFORMS)}.")
        if k not in out:
            out.append(k)
    if not out:
        raise CaptionInputError("Give at least one platform.")
    return out


# ---- grapheme-ish clustering (stdlib only) ----
def _is_emoji_base(cp: int) -> bool:
    return (0x1F300 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x1F000 <= cp <= 0x1F2FF
            or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x231A, 0x231B, 0x2B50, 0x2B55, 0x2B1B, 0x2B1C, 0x3030, 0x303D))


def clusters(text: str) -> list[str]:
    """Approximate extended grapheme clusters: base + marks/ZWJ sequences/skin tones/flags/keycaps."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        j = i + 1
        cp = ord(text[i])
        if 0x1F1E6 <= cp <= 0x1F1FF and j < n and 0x1F1E6 <= ord(text[j]) <= 0x1F1FF:
            j += 1
        while j < n:
            c = text[j]
            o = ord(c)
            if unicodedata.category(c) in ("Mn", "Me") or o in (0xFE0F, 0x200D) or 0x1F3FB <= o <= 0x1F3FF or o == 0x20E3 or 0xE0020 <= o <= 0xE007F:
                j += 1
                if o == 0x200D and j < n:
                    j += 1
            else:
                break
        out.append(text[i:j])
        i = j
    return out


def is_emoji_cluster(c: str) -> bool:
    if "\ufe0f" in c or "\u20e3" in c:
        return True
    return any(_is_emoji_base(ord(ch)) or 0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in c)


def _x_weight(cp: int) -> int:
    # twitter-text config v3: these ranges weigh 1, everything else 2
    if cp <= 4351 or 8192 <= cp <= 8205 or 8208 <= cp <= 8223 or 8242 <= cp <= 8247:
        return 1
    return 2


def find_links(text: str) -> list[tuple[int, int, str]]:
    res = []
    for m in URL_RE.finditer(text):
        url = m.group(0)
        stripped = url.rstrip(TRAILING_PUNCT)
        res.append((m.start(), m.start() + len(stripped), stripped))
    return res


def _split_links(text: str) -> tuple[str, list[str]]:
    """Return text with links removed (replaced by a single private marker) and the links."""
    links = find_links(text)
    parts, last = [], 0
    for s, e, _ in links:
        parts.append(text[last:s])
        parts.append("\ue000")
        last = e
    parts.append(text[last:])
    return "".join(parts), [u for _, _, u in links]


def count_x(text: str) -> int:
    body, links = _split_links(text)
    total = 0
    for c in clusters(body):
        if c == "\ue000":
            total += 23
        elif is_emoji_cluster(c):
            total += 2
        else:
            total += sum(_x_weight(ord(ch)) for ch in c)
    return total


def count_mastodon(text: str, cw: str = "") -> int:
    body, _ = _split_links(text)
    body = MENTION_RE.sub(lambda m: "@" + m.group(1), body)
    total = 0
    for c in clusters(body):
        total += 23 if c == "\ue000" else 1
    cwb, _ = _split_links(cw)
    total += sum(23 if c == "\ue000" else 1 for c in clusters(cwb))
    return total


def count_threads(text: str) -> int:
    total = 0
    for c in clusters(text):
        total += len(c.encode("utf-8")) if is_emoji_cluster(c) else len(c)
    return total


def measure(pid: str, text: str, *, x_premium: bool = False, mastodon_limit: int = 500, content_warning: str = "") -> tuple[int, int | None]:
    """Return (count, limit) for one platform id."""
    spec = PLATFORMS[pid]
    limit = spec["limit"]
    if pid == "x":
        return count_x(text), spec["premium_limit"] if x_premium else limit
    if pid == "bluesky":
        return len(clusters(text)), limit
    if pid == "threads":
        return count_threads(text), limit
    if pid == "mastodon":
        return count_mastodon(text, content_warning), mastodon_limit
    if pid == "tiktok":
        return len(text.encode("utf-16-le")) // 2, limit
    if pid == "youtube_description":
        return len(text.encode("utf-8")), limit
    return len(text), limit


def _hashtags(text: str) -> list[str]:
    body, _ = _split_links(text)  # '#' inside URLs is a fragment, not a hashtag
    return HASHTAG_RE.findall(body)


def count_post(text: str, platforms: list[str], **kw) -> list[dict]:
    if not text.strip():
        raise CaptionInputError("The text is empty.")
    rows = []
    for pid in resolve_platforms(platforms):
        count, limit = measure(pid, text, **kw)
        rows.append({
            "platform": pid, "name": PLATFORMS[pid]["name"], "count": count, "limit": limit,
            "unit": PLATFORMS[pid]["unit"],
            "remaining": None if limit is None else limit - count,
            "fits": True if limit is None else count <= limit,
        })
    return rows


def lint_post(text: str, platforms: list[str], **kw) -> dict:
    if not text.strip():
        raise CaptionInputError("The text is empty.")
    pids = resolve_platforms(platforms)
    rows = count_post(text, pids, **kw)
    issues: list[dict] = []

    def add(sev: str, plat: str | None, msg: str):
        issues.append({"severity": sev, "platform": plat, "message": msg})

    links = [u for _, _, u in find_links(text)]
    tags = _hashtags(text)
    mentions = MENTION_RE.findall(text)
    cjk = sum(1 for ch in text if _x_weight(ord(ch)) == 2 and not is_emoji_cluster(ch) and ord(ch) > 0x2E80)

    for r in rows:
        if not r["fits"]:
            over = -r["remaining"]
            add("error", r["platform"], f"{r['name']}: {r['count']} {r['unit']} is {over} over the {r['limit']} limit. Cut at least {over}.")
        elif r["limit"] and r["remaining"] <= r["limit"] * 0.05 and r["remaining"] >= 0:
            add("info", r["platform"], f"{r['name']}: only {r['remaining']} left of {r['limit']}; a small edit could push it over.")
    for pid in pids:
        spec = PLATFORMS[pid]
        if pid == "bluesky":
            b = len(text.encode("utf-8"))
            if b > spec["byte_limit"]:
                add("error", pid, f"Bluesky: {b} bytes exceeds the {spec['byte_limit']}-byte cap.")
            long_links = [u for u in links if len(u) > 60]
            if long_links:
                add("warning", pid, f"Bluesky counts links at full length: {len(long_links)} link(s) over 60 characters eat the budget. Shorten them.")
        if pid == "threads":
            uniq = set(links)
            if len(uniq) > spec["max_links"]:
                add("error", pid, f"Threads: {len(uniq)} unique links; more than {spec['max_links']} fails at creation.")
            if any(len(u) > 60 for u in links):
                add("warning", pid, "Threads counts links at their full length (not documented otherwise); shorten long links.")
        if pid == "x":
            if cjk and not kw.get("x_premium"):
                add("warning", pid, f"X: {cjk} CJK characters count 2 each, so Chinese/Japanese/Korean text fits about 140 characters.")
            if len(tags) > 2:
                add("info", pid, f"X: {len(tags)} hashtags; 1-2 is the usual practice (not a limit).")
        if pid == "instagram":
            if len(tags) > spec["max_hashtags_api"]:
                add("error", pid, f"Instagram: {len(tags)} hashtags exceeds even the API cap of {spec['max_hashtags_api']}.")
            elif len(tags) > spec["max_hashtags_help"]:
                add("warning", pid, f"Instagram: {len(tags)} hashtags. The Help Center now says up to {spec['max_hashtags_help']} per post and a post/comment with more may not publish; Meta's API still says {spec['max_hashtags_api']}. Keep {spec['max_hashtags_help']} or fewer.")
            if len(mentions) > spec["max_mentions"]:
                add("error", pid, f"Instagram: {len(mentions)} @ tags exceeds {spec['max_mentions']}.")
            if links:
                add("info", pid, "Instagram: links in a caption are not clickable; use the bio link or a Story link sticker.")
        if pid == "tiktok":
            e = sum(1 for c in clusters(text) if is_emoji_cluster(c))
            if e and len(text.encode("utf-16-le")) // 2 != len(text):
                add("info", pid, "TikTok counts UTF-16 units: emoji and some symbols use two.")
        if spec.get("forbid"):
            bad = sorted({ch for ch in spec["forbid"] if ch in text})
            if bad:
                add("error", pid, f"{spec['name']}: the characters {' '.join(bad)} are rejected by the YouTube API. Remove them.")
        if pid in FOLDS and len(text) > FOLDS[pid]:
            add("info", pid, f"{spec['name']}: readers see roughly the first {FOLDS[pid]} characters before 'see more' (measured by others, not published). Put the hook there.")
        if pid == "mastodon" and kw.get("content_warning"):
            add("info", pid, "Mastodon: the content warning counts toward the same limit.")
        if pid == "mastodon" and kw.get("mastodon_limit", 500) == 500:
            add("info", pid, "Mastodon: 500 is only the default; pass the server's own max_characters if it differs.")
    if PLACEHOLDER_RE.search(text):
        add("error", None, f"Unfilled placeholder found: '{PLACEHOLDER_RE.search(text).group(0)}'.")
    if re.search(r"#\w+#\w+", text):
        add("warning", None, "Two hashtags are glued together (#a#b); put a space between them or neither works.")
    if text != text.rstrip() or re.search(r"[ \t]{3,}", text):
        add("info", None, "Trailing whitespace or runs of spaces; platforms keep them and they waste characters.")
    if len(set(links)) < len(links):
        add("info", None, "The same link appears more than once.")
    errors = sum(1 for i in issues if i["severity"] == "error")
    return {"ok": errors == 0, "error_count": errors, "counts": rows, "issues": issues,
            "hashtags": ["#" + t for t in tags], "links": links}


def fit_platforms(text: str, **kw) -> dict:
    """Which platforms the text fits as-is, and how much to cut for the rest."""
    rows = count_post(text, [p for p in PLATFORMS if p != "facebook"], **kw)
    return {"fits": [r["platform"] for r in rows if r["fits"]],
            "too_long": [{"platform": r["platform"], "over_by": -r["remaining"]} for r in rows if not r["fits"]]}
