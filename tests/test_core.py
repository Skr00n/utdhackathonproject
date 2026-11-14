import time

import pytest

import core


@pytest.mark.parametrize("q,want", [
    ("  Tikka  N   Kabab, Dallas ", "tikka n kabab dallas"),
    ("TIKKA N KABAB DALLAS", "tikka n kabab dallas"),
    ("https://www.TikkaNKababTX.com/menu?x=1", "tikkankababtx.com"),
    ("tikkankababtx.com", "tikkankababtx.com"),
    ("Yummy Spice & Rice", "yummy spice and rice"),
    ("Café  Brazil!", "café brazil"),
])
def test_normalize_query(q, want):
    assert core.normalize_query(q) == want


def test_validate_query():
    assert core.validate_query("  Bawarchi  ") == "Bawarchi"
    for bad in ["", " ", "a", "!!!", "x" * 201, None, 5]:
        with pytest.raises(core.ValidationError):
            core.validate_query(bad)


def test_validate_info_sanitizes():
    out = core.validate_info({"name": " Test Place ", "website": "example.com", "menu_link": "javascript:alert(1)",
                              "lat": "999", "lng": "-96.7", "rating": "7.5", "review_count": "1,234",
                              "phone": "unknown", "features": "x" * 5000, "extra": "ignored"})
    assert out["name"] == "Test Place"
    assert out["website"] == "https://example.com"
    assert out["menu_link"] == ""
    assert out["lat"] == "" and out["lng"] == "-96.7"
    assert out["rating"] == "" and out["review_count"] == "1234"
    assert out["phone"] == ""
    assert len(out["features"]) == 600 and "extra" not in out
    with pytest.raises(core.ValidationError):
        core.validate_info({"name": ""})


def test_disk_cache_roundtrip_and_ttl(tmp_path):
    c = core.DiskCache(tmp_path, ttl_s=100)
    assert c.get("ns", "k") is None
    c.set("ns", "k", {"a": 1})
    assert c.get("ns", "k") == {"a": 1}
    import json
    p = c._p("ns", "k")
    p.write_text(json.dumps({"_t": 0, "v": {"a": 1}}))  # written long ago
    assert c.get("ns", "k") is None


def test_rate_limiter():
    rl = core.RateLimiter(2, 60)
    t = time.monotonic()
    assert rl.allow("ip", t)[0] and rl.allow("ip", t)[0]
    ok, retry = rl.allow("ip", t + 1)
    assert not ok and retry > 0
    assert rl.allow("other", t)[0]
    assert rl.allow("ip", t + 61)[0]


def test_report_store_rejects_traversal(tmp_path):
    s = core.ReportStore(tmp_path)
    assert s.dir("../etc") is None and s.dir("a/b/c/d") is None and s.dir("short") is None
    assert s.dir("abcdef123") is not None
