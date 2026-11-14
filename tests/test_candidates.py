import json

import candidates as cand
import gemini_client

RAW = {"candidates": [
    {"name": "Kalachandji's", "address": "5430 Gurley Ave, Dallas, TX 75223", "rating": "4.6", "review_count": "2,345",
     "website": "https://kalachandjis.com", "source_url": "https://maps.google.com/?cid=1", "category": "Vegetarian restaurant"},
    {"name": "No Street Place", "address": "Dallas, TX", "source_url": "https://maps.google.com/?cid=2"},
    {"name": "No Source Place", "address": "100 Main St, Dallas, TX 75201", "source_url": ""},
    {"name": "Fake Source", "address": "100 Main St, Dallas, TX 75201", "source_url": "https://example.com/x"},
    {"name": "Bad Values", "address": "12 Elm St, Plano, TX 75074", "rating": 11, "review_count": -5,
     "source_url": "https://www.yelp.com/biz/bad", "website": "javascript:alert(1)"},
    {"name": "Kalachandji's", "address": "5430 Gurley Ave, Dallas, TX 75223", "source_url": "https://kalachandjis.com"},  # dup
    {"name": "Near UTD Grill", "address": "near UT Dallas, Richardson", "source_url": "https://maps.google.com/?cid=3"},
]}


def test_filter_keeps_only_verifiable():
    out = cand.filter_candidates(RAW, grounded=True)
    assert [c["name"] for c in out] == ["Kalachandji's", "Bad Values"]
    k, b = out
    assert k["rating"] == 4.6 and k["review_count"] == 2345 and k["website"] == "https://kalachandjis.com"
    assert len(k["candidate_id"]) == 32
    assert b["rating"] is None and b["review_count"] is None and b["website"] is None


def test_ungrounded_answers_are_never_used():
    assert cand.filter_candidates(RAW, grounded=False) == []


def test_caps_at_five():
    many = {"candidates": [{"name": f"Place {i}", "address": f"{i + 1} Main St, Dallas, TX 75201",
                            "source_url": f"https://maps.google.com/?cid={i}"} for i in range(9)]}
    assert len(cand.filter_candidates(many, True)) == 5


def test_street_address_rules():
    assert cand.real_street_address("7859 McCallum Blvd Ste 106, Dallas, TX 75252")
    assert cand.real_street_address("1 Infinite Loop, Cupertino, CA")
    assert not cand.real_street_address("Dallas, TX 75252")
    assert not cand.real_street_address("Main Street, Dallas, TX")
    assert not cand.real_street_address(None)


def test_find_handles_garbage_json():
    gen = lambda *a, **k: gemini_client.GenResult("sorry, no idea", "m", True, 1, [])
    assert cand.find("asdfgh", generate=gen)["candidates"] == []


def test_find_passes_typo_query_and_filters():
    seen = {}

    def gen(prompt, grounded=False, **k):
        seen["p"], seen["g"] = prompt, grounded
        return gemini_client.GenResult(json.dumps(RAW), "m", True, 1, [])
    out = cand.find('kalachanjis dalas"', generate=gen)
    assert seen["g"] is True and "kalachanjis dalas'" in seen["p"] and "typos" in seen["p"]
    assert len(out["candidates"]) == 2
