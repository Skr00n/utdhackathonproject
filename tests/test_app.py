import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as appmod
import core
import gemini_client

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(appmod.app)
SAMPLE_PLAN = json.loads((ROOT / "sample_output" / "tikka_n_kabab.plan.json").read_text())


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["live_lookups"] is False
    assert "key" not in json.dumps(r.json()).lower().replace("live_lookups", "")


def test_index_and_unknown_report_page():
    assert client.get("/").status_code == 200
    assert "Page One" in client.get("/").text
    assert client.get("/r/doesnotexist1").status_code == 404


def test_index_has_no_tikka_suggestions():
    html = client.get("/").text
    assert "tikka" not in html.lower() and "city + name" in html


def test_offline_sample_flow_and_downloads():
    b = client.post("/api/build", json={"lookup_id": "demo"}).json()
    assert b["status"] == "ok" and b["report_id"] == core.DEMO_ID
    rid = b["report_id"]
    meta = client.get(f"/api/reports/{rid}").json()
    assert meta["mode"] == "demo" and meta["summary"]["competitors"]
    assert client.get(f"/r/{rid}").status_code == 200
    html = client.get(f"/api/reports/{rid}/report.html")
    assert html.status_code == 200 and "How you compare" in html.text and "Close the gap" in html.text
    assert "SIMULATED" in html.text and "Bawarchi" in html.text
    pdf = client.get(f"/api/reports/{rid}/download?f=pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"
    assert "attachment" in pdf.headers["content-disposition"] and "tikka-n-kabab" in pdf.headers["content-disposition"]
    h = client.get(f"/api/reports/{rid}/download?f=html")
    assert h.status_code == 200 and h.headers["content-type"].startswith("text/html") and "attachment" in h.headers["content-disposition"]
    assert client.get(f"/api/download?f=pdf&id={rid}").status_code == 200  # old URL shape still works
    assert client.get(f"/api/reports/{rid}/download?f=exe").status_code == 400
    assert client.get("/api/reports/nope123456/download?f=pdf").status_code == 404
    assert client.get("/api/reports/..%2F..%2Fetc/download?f=pdf").status_code == 404


def test_candidates_without_key_is_friendly():
    r = client.get("/api/candidates", params={"q": "Saravanaa Bhavan Richardson"})
    assert r.status_code == 503
    d = r.json()
    assert d["kind"] == "no_key" and d["demo_available"]


def test_tikka_is_not_shortcut():
    r = client.get("/api/candidates", params={"q": "tika n kebab"})
    assert r.status_code == 503 and r.json()["kind"] == "no_key"  # goes to the live search like any name


@pytest.mark.parametrize("q", ["", "xy", "y" * 300])
def test_input_validation(q):
    r = client.get("/api/candidates", params={"q": q})
    assert r.status_code == 400 and r.json()["kind"] == "invalid"


def test_build_rejects_bad_candidate_id():
    assert client.post("/api/build", json={"candidate_id": "../../x"}).status_code == 400
    assert client.post("/api/build", json={}).status_code == 400
    assert client.post("/api/build", json={"candidate_id": "0" * 32}).status_code == 410


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(appmod, "cand_limiter", core.RateLimiter(2, 60))
    codes = [client.get("/api/candidates", params={"q": "abc"}).status_code for _ in range(3)]
    assert codes[2] == 429


# ---------------------------------------------------------------- mocked live flow
CANDS_JSON = {"candidates": [
    {"name": "Test Biryani House", "address": "100 Main St, Plano, TX 75074", "rating": 4.4, "review_count": 812,
     "website": "https://testbiryani.com", "source_url": "https://maps.google.com/?cid=42", "category": "Indian restaurant"},
    {"name": "Unverified Spot", "address": "Plano, TX", "source_url": "https://maps.google.com/?cid=43"}]}
LOOKUP_JSON = {"found": True, "name": "Test Biryani House", "address": "100 Main St, Plano, TX 75074", "cuisine": "Indian",
               "website": "https://example.com", "menu_link": "", "phone": "", "hours": "", "features": "takeout",
               "menu_items": "Chicken Biryani $12.99; Paneer Tikka", "price_range": "", "lat": "33.02", "lng": "-96.70",
               "rating": "4.4", "review_count": "812", "category": "Indian restaurant"}
COMP_JSON = {"target": {"rating": 4.4, "review_count": 812, "category": "Indian restaurant"},
             "competitors": [{"name": "Other Biryani", "rating": 4.6, "review_count": 2000, "category": "Indian restaurant",
                              "lat": 33.05, "lng": -96.72, "keywords_ranked": [], "listing_keywords": ["halal"],
                              "source_urls": ["https://example.org"]}]}


def fake_generate(calls, fail_plan=False):
    def gen(prompt, grounded=False, **kw):
        calls.append(prompt[:40])
        if prompt.startswith("Use Google Search. A user is looking"):
            text = json.dumps(CANDS_JSON)
        elif prompt.startswith("Use Google Search. Get the public details"):
            text = json.dumps(LOOKUP_JSON)
        elif "local SEO + AEO" in prompt:
            if fail_plan:
                raise gemini_client.GeminiError("quota", "429")
            text = json.dumps(SAMPLE_PLAN)
        elif prompt.startswith("Use Google Search. Target restaurant"):
            text = json.dumps(COMP_JSON)
        else:
            raise AssertionError("unexpected prompt " + prompt[:60])
        return gemini_client.GenResult(text=text, model="fake-model", grounded=grounded, attempts=1,
                                       sources=[{"title": "src", "uri": "https://example.com/src"}] if grounded else [])
    return gen


def wait_job(jid, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["state"] in ("ok", "error"):
            return j
        time.sleep(0.05)
    raise AssertionError("job hung")


def test_mocked_live_build(monkeypatch):
    calls = []
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(gemini_client, "generate", fake_generate(calls))
    d = client.get("/api/candidates", params={"q": "test biryani hous plano"}).json()
    assert d["status"] == "ok" and [c["name"] for c in d["candidates"]] == ["Test Biryani House"]  # unverified dropped
    c0 = d["candidates"][0]
    n = len(calls)
    client.get("/api/candidates", params={"q": "Test  Biryani HOUS, plano"})  # cached by normalized query
    assert len(calls) == n
    b = client.post("/api/build", json={"candidate_id": c0["candidate_id"]}).json()
    assert b["status"] == "queued"
    j = wait_job(b["job_id"])
    assert j["state"] == "ok", j
    rid = j["report_id"]
    meta = client.get(f"/api/reports/{rid}").json()
    assert meta["mode"] == "live" and meta["info"]["name"] == "Test Biryani House"
    assert meta["info"]["address"] == "100 Main St, Plano, TX 75074"  # exact picked place
    s = meta["summary"]
    assert s["competitors"][0]["name"] == "Other Biryani" and s["target"]["review_count"] == 812
    html = client.get(f"/api/reports/{rid}/report.html").text
    assert "not independently verified" in html and "SIMULATED" in html and "How you compare" in html
    assert "Best Hamburgers" not in html  # Tikka hand-check data must not leak into other restaurants
    assert client.get(f"/api/reports/{rid}/download?f=pdf").content[:4] == b"%PDF"
    n = len(calls)
    again = client.post("/api/build", json={"candidate_id": c0["candidate_id"]}).json()
    assert again["status"] == "ok" and again["report_id"] == rid and len(calls) == n


def test_candidates_none_found(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(gemini_client, "generate", lambda *a, **k: gemini_client.GenResult('{"candidates": []}', "m", True, 1, []))
    d = client.get("/api/candidates", params={"q": "zzqx nowhere grill"}).json()
    assert d["status"] == "none" and "couldn't find" in d["message"]


def test_live_build_failure_is_reported_not_faked(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(gemini_client, "generate", fake_generate([], fail_plan=True))
    d = client.get("/api/candidates", params={"q": "fail test biryani"}).json()
    appmod.cache.set("report", d["candidates"][0]["candidate_id"], "")  # force a fresh build
    b = client.post("/api/build", json={"candidate_id": d["candidates"][0]["candidate_id"]}).json()
    j = wait_job(b["job_id"])
    assert j["state"] == "error" and j["kind"] == "quota" and "try again" in j["message"].lower()


def test_candidates_provider_errors_are_friendly(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")

    def boom(*a, **k):
        raise gemini_client.GeminiError("overloaded", "503")
    monkeypatch.setattr(gemini_client, "generate", boom)
    r = client.get("/api/candidates", params={"q": "Some New Place Frisco"})
    assert r.status_code == 503 and r.json()["kind"] == "overloaded" and r.json()["demo_available"]
