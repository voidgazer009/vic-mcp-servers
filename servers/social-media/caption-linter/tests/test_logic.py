import pytest

from vic_caption_linter import logic
from vic_caption_linter.logic import CaptionInputError


def c(pid, text, **kw):
    return logic.measure(pid, text, **kw)[0]


def test_x_weighted_golden():
    # "Hi " = 3, "你好" = 2 CJK x 2 = 4, " " = 1, emoji = 2, " " = 1, link = 23 -> 34
    assert c("x", "Hi 你好 😀 https://a.co/x") == 34


def test_x_link_is_23_whatever_length():
    short = c("x", "see https://a.co/x")
    long = c("x", "see https://example.com/" + "a" * 200)
    assert short == long == 4 + 23


def test_x_japanese_fits_140():
    assert c("x", "あ" * 140) == 280 and c("x", "あ" * 141) == 282


def test_bluesky_graphemes_not_codepoints():
    # family emoji is 5 code points but 1 grapheme; plus " hi" = 3 -> 4
    assert c("bluesky", "\U0001F468\u200D\U0001F469\u200D\U0001F467 hi") == 4


def test_threads_emoji_counts_utf8_bytes():
    # grinning face is 4 UTF-8 bytes, "a" is 1 -> 5
    assert c("threads", "\U0001F600a") == 5


def test_mastodon_mention_username_and_link():
    # "@bob" (domain dropped) = 4, " hi " = 4, link = 23 -> 31
    assert c("mastodon", "@bob@example.social hi https://x.com/abc") == 31


def test_mastodon_content_warning_counts():
    assert c("mastodon", "abc", content_warning="warn") == 7


def test_tiktok_utf16_units():
    assert c("tiktok", "\U0001F600") == 2


def test_youtube_description_bytes():
    # each Chinese character is 3 UTF-8 bytes
    assert c("youtube_description", "你好") == 6


def test_over_limit_error_and_fix_amount():
    r = logic.lint_post("a" * 285, ["x"])
    assert not r["ok"] and "5 over" in r["issues"][0]["message"]


def test_instagram_hashtags_warning_and_hard_error():
    six = " ".join(f"#t{i}a" for i in range(6))
    r = logic.lint_post("hello " + six, ["instagram"])
    assert r["ok"] and any("Help Center" in i["message"] for i in r["issues"])
    many = " ".join(f"#t{i}a" for i in range(31))
    assert not logic.lint_post(many, ["instagram"])["ok"]


def test_url_fragment_is_not_a_hashtag():
    r = logic.lint_post("read https://example.com/page#section now", ["instagram"])
    assert r["hashtags"] == []


def test_youtube_forbidden_chars_and_placeholder():
    r = logic.lint_post("Best <tool> {{name}}", ["youtube_title"])
    msgs = " ".join(i["message"] for i in r["issues"])
    assert not r["ok"] and "< >" in msgs and "placeholder" in msgs


def test_threads_link_cap():
    text = " ".join(f"https://e.com/{i}" for i in range(6))
    assert not logic.lint_post(text, ["threads"])["ok"]


def test_aliases_and_unknown():
    assert logic.resolve_platforms(["Twitter", "IG", "x"]) == ["x", "instagram"]
    with pytest.raises(CaptionInputError):
        logic.resolve_platforms(["myspace"])
    with pytest.raises(CaptionInputError):
        logic.count_post("   ", ["x"])


def test_fit_platforms():
    r = logic.fit_platforms("a" * 400)
    assert "x" in [t["platform"] for t in r["too_long"]] and "threads" in r["fits"]
