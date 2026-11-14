import competitors as c

KW = ["chicken 65 near me", "butter chicken near UTD", "beef nihari Dallas"]
TARGET = {"name": "Tikka N Kabab", "address": "Dallas, TX", "lat": "32.9895", "lng": "-96.7735",
          "cuisine": "Pakistani", "features": "Google rating 4.2 (407 reviews)", "menu_items": "Chicken 65 $9.99"}


def test_sanitize_drops_invented_and_out_of_range():
    data = {"target": {"rating": "4.2", "review_count": "407"}, "competitors": [
        {"name": "Tikka N Kabab", "rating": 5},  # the target itself
        {"name": "Good Place", "rating": "4.5", "review_count": "1,200", "category": "Indian restaurant",
         "keywords_ranked": ["chicken 65 near me", "made up keyword"], "lat": 32.99, "lng": -96.75,
         "source_urls": ["https://maps.google.com/x", "not a url"]},
        {"name": "Bad Data", "rating": 9.9, "review_count": -3, "category": "unknown"},
        {"name": "Far Away", "lat": 29.76, "lng": -95.36},  # Houston, > 20 mi
        {"name": "good place"},  # duplicate
    ]}
    out = c.sanitize_result(data, TARGET, KW, c.LIVE_LABEL)
    names = [x["name"] for x in out["competitors"]]
    assert names == ["Good Place", "Bad Data"]
    gp, bad = out["competitors"]
    assert gp["rating"] == 4.5 and gp["review_count"] == 1200 and gp["keywords_ranked"] == ["chicken 65 near me"]
    assert 0 < gp["distance_mi"] < 3 and gp["source_urls"] == ["https://maps.google.com/x"]
    assert bad["rating"] is None and bad["review_count"] is None and bad["category"] is None
    assert out["target"]["rating"] == 4.2


def test_seed_has_real_values_only():
    s = c.tikka_seed()
    by = {x["name"]: x for x in s["competitors"]}
    assert by["Bawarchi Indian Cuisine - Richardson"]["rating"] == 3.6
    assert by["Bawarchi Indian Cuisine - Richardson"]["review_count"] == 2650
    assert by["Yummy Spice & Rice"]["review_count"] == 1003
    assert by["Saravanaa Bhavan"]["rating"] is None  # not checked -> not invented
    assert len(s["competitors"]) <= c.MAX_COMPETITORS


def test_enrich_never_overwrites_hand_check():
    seed = c.tikka_seed()

    class R:
        text = ('{"competitors":[{"name":"Bawarchi Indian Cuisine - Richardson","rating":4.9,"review_count":1,'
                '"address":"123 Main St, Richardson, TX"},{"name":"Saravanaa Bhavan","rating":4.1,"review_count":3000}]}')
        model = "m"; grounded = True; sources = []
    out = c.enrich_seed(seed, TARGET, generate=lambda *a, **k: R())
    by = {x["name"]: x for x in out["competitors"]}
    assert by["Bawarchi Indian Cuisine - Richardson"]["rating"] == 3.6  # hand check kept
    assert by["Bawarchi Indian Cuisine - Richardson"]["address"] == "123 Main St, Richardson, TX"
    assert by["Bawarchi Indian Cuisine - Richardson"]["field_sources"] == {"address": c.LIVE_LABEL}
    assert by["Saravanaa Bhavan"]["rating"] == 4.1 and by["Saravanaa Bhavan"]["field_sources"]["rating"] == c.LIVE_LABEL


def test_analyze_ties_steps_to_findings():
    cmp = c.tikka_seed()
    a = c.analyze(TARGET, cmp, KW)
    txt = " ".join(a["findings"] + a["close_the_gap"])
    assert "407" in txt and "2,650" in txt and "Yummy Spice & Rice" in txt
    assert any("category" in s.lower() for s in a["close_the_gap"])
    assert a["coverage"]["chicken 65 near me"]


def test_render_marks_not_found():
    cmp = c.tikka_seed()
    h = c.render_html(TARGET, cmp, c.analyze(TARGET, cmp, KW), KW)
    assert "How you compare" in h and "not found" in h and "<script" not in h
