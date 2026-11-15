"""Golden tests: every expected value is worked out by hand from Google's GA4 help pages."""
import pytest

from vic_utm_builder import logic
from vic_utm_builder.logic import UtmInputError


def test_golden_build_keeps_query_and_fragment():
    # Hand-built: values lower-cased, spaces -> '_': LinkedIn->linkedin, "Paid Social"->paid_social, "Spring Sale 2026"->spring_sale_2026.
    # Existing ?ref=1 stays first, UTM tags follow in Google's order (id, source, medium, campaign...), #faq stays last.
    r = logic.build_url("https://example.com/pricing?ref=1#faq", "LinkedIn", "Paid Social", "Spring Sale 2026")
    assert r["url"] == "https://example.com/pricing?ref=1&utm_source=linkedin&utm_medium=paid_social&utm_campaign=spring_sale_2026#faq"
    # medium 'paid_social' matches ^paid.*$ and linkedin is a social source -> Paid Social
    assert r["predicted_channel"] == "Paid Social"
    assert any("utm_id" in w for w in r["warnings"])
    assert r["changes"]


@pytest.mark.parametrize("source,medium,campaign,channel", [
    ("newsletter", "email", None, "Email"),                  # medium email
    ("google", "cpc", None, "Paid Search"),                  # cpc matches .*cp.*, google is a search site
    ("google", "organic", None, "Organic Search"),           # medium exactly organic
    ("facebook", "social", None, "Organic Social"),          # social source, medium not paid
    ("xiaohongshu", "cpc", None, "Paid Other"),              # paid medium, source not in Google's lists
    ("blog", "referral", None, "Referral"),
    ("x", "weird", None, "Organic Social"),                  # source x is social even with odd medium
    ("foo", "bar", None, "Unassigned"),
    ("amazon", "cpc", None, "Paid Shopping"),
    ("youtube", "paid_video", None, "Paid Video"),
    ("(direct)", "(none)", None, "Direct"),
    ("blog", "x", "black-friday-shop", "Organic Shopping"),  # campaign name contains 'shop'
])
def test_golden_channels(source, medium, campaign, channel):
    assert logic.predict_channel(source, medium, campaign)["channel"] == channel


def test_golden_lint_typo_and_case():
    # utm_campaing is a typo for utm_campaign (error + missing campaign = 2 errors); Meta is upper case (warning).
    r = logic.lint_url("https://x.com/?utm_source=Meta&utm_medium=cpc&utm_campaing=a")
    assert r["valid"] is False and r["error_count"] == 2
    msgs = " ".join(i["message"] for i in r["issues"])
    assert "did you mean 'utm_campaign'" in msgs and "upper-case" in msgs


def test_lint_clean_link_is_valid():
    r = logic.lint_url("https://x.com/?utm_source=linkedin&utm_medium=paid_social&utm_campaign=a&utm_id=c1")
    assert r["valid"] and r["issues"] == [] and r["predicted_channel"] == "Paid Social"


def test_lint_fragment_and_duplicates():
    r = logic.lint_url("https://x.com/#a?utm_source=a")
    assert any("fragment" in i["message"] for i in r["issues"])
    r = logic.lint_url("https://x.com/?utm_source=a&utm_source=b&utm_medium=email&utm_campaign=c")
    assert any("2 times" in i["message"] for i in r["issues"])


def test_replace_existing_utm_warns():
    r = logic.build_url("https://x.com/?utm_source=old&a=1", "new", "email", "c")
    assert r["url"].count("utm_source") == 1 and "utm_source=new" in r["url"] and any("replaced" in w for w in r["warnings"])


def test_normalize_off_warns_on_uppercase():
    r = logic.build_url("https://x.com/", "Meta", "cpc", "c", normalize=False)
    assert "utm_source=Meta" in r["url"] and any("upper-case" in w for w in r["warnings"])


def test_chinese_value_kept_and_encoded():
    r = logic.build_url("https://x.com/", "wechat", "social", "双十一 大促")
    assert "utm_campaign=%E5%8F%8C%E5%8D%81%E4%B8%80_%E5%A4%A7%E4%BF%83" in r["url"]
    assert any("non-ASCII" in w for w in r["warnings"])


def test_batch_links():
    r = logic.campaign_links("https://x.com/", "launch", [{"platform": "LinkedIn"}, {"platform": "newsletter", "content": "toplink"}], "c1")
    assert r["links"][0]["url"] == "https://x.com/?utm_id=c1&utm_source=linkedin&utm_medium=paid_social&utm_campaign=launch"
    assert r["links"][1]["predicted_channel"] == "Email"


@pytest.mark.parametrize("bad", ["", "example.com", "ftp://x.com", "javascript:alert(1)", "https://"])
def test_bad_urls(bad):
    with pytest.raises(UtmInputError):
        logic.build_url(bad, "a", "b", "c")


def test_empty_required_and_unknown_platform():
    with pytest.raises(UtmInputError):
        logic.build_url("https://x.com/", " ", "b", "c")
    with pytest.raises(UtmInputError):
        logic.campaign_links("https://x.com/", "c", [{"platform": "nopenet"}], None)
    with pytest.raises(UtmInputError):
        logic.campaign_links("https://x.com/", "c", [], None)


def test_lint_wrong_case_and_hyphen_names():
    # 'UTM_Source' and 'utm-medium' are not recognised by GA4: 2 naming errors + source and medium missing = 4 errors.
    r = logic.lint_url("https://a.com/?UTM_Source=a&utm-medium=email&utm_campaign=c")
    assert r["error_count"] == 4
    assert "must be written exactly 'utm_source'" in " ".join(i["message"] for i in r["issues"])
