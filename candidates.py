"""Restaurant candidates for the search dropdown.

One grounded Gemini call (Google Search) returns up to 5 REAL matches for what the user typed (typos ok).
Every candidate must have a real street address and a source URL; anything else is dropped.
Ungrounded answers are never used (model memory is not a source)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

import core

MAX_CANDIDATES = 5

PROMPT = """Use Google Search. A user is looking for a specific restaurant and typed: "{q}"
The text may contain typos, missing words or only part of the name; find the closest REAL, currently listed
restaurants (Google Maps / Business Profile) that match. Return up to {n}, best match first.
For each, report ONLY values found in search results; use null when not found; never guess:
- name (official name), address (full street address with number, city, state, ZIP)
- rating (Google stars) and review_count (Google review count)
- website (official site) and source_url (the page where you found the listing: Google Maps, the official site, Yelp, etc.)
- category (Google primary category) and cuisine
If nothing real matches, return an empty list.
Return ONLY JSON: {{"candidates":[{{"name":"","address":"","rating":null,"review_count":null,"website":null,
"source_url":"","category":null,"cuisine":null}}]}}"""

STREET_RE = re.compile(r"\b\d{1,6}[A-Za-z]?(?:-\d+)?\s+[A-Za-z0-9]")
ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")


def real_street_address(a) -> bool:
    if not isinstance(a, str):
        return False
    a = a.strip()
    if len(a) < 10 or len(a) > 200:
        return False
    if not STREET_RE.search(a):
        return False  # e.g. "Dallas, TX" or "Near UTD" has no street number
    return a.count(",") >= 2 or bool(ZIP_RE.search(a))


def valid_source(u) -> str | None:
    if not isinstance(u, str):
        return None
    u = u.strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname:
        return None
    if p.hostname.endswith(("example.com", "example.org", "localhost")):
        return None
    return u[:500]


def _num(v, lo, hi, cast):
    try:
        x = cast(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None
    return x if lo <= x <= hi else None


def candidate_id(name: str, address: str) -> str:
    return core.cache_key("cand", core.normalize_query(name), core.normalize_query(address))


def filter_candidates(data, grounded: bool) -> list[dict]:
    """Keep only verifiable candidates. Pure: unit-tested without network."""
    if not grounded or not isinstance(data, dict):
        return []
    out, seen = [], set()
    for c in data.get("candidates") or []:
        if not isinstance(c, dict):
            continue
        name = core.clean_text(c.get("name") or "", 120)
        addr = core.clean_text(c.get("address") or "", 200)
        src = valid_source(c.get("source_url"))
        if len(name) < 2 or not real_street_address(addr) or not src:
            continue
        cid = candidate_id(name, addr)
        if cid in seen:
            continue
        seen.add(cid)
        web = valid_source(c.get("website"))
        out.append({"candidate_id": cid, "name": name, "address": addr,
                    "rating": _num(c.get("rating"), 1.0, 5.0, float), "review_count": _num(c.get("review_count"), 0, 10_000_000, int),
                    "website": web, "source_url": src,
                    "category": core.clean_text(c.get("category") or "", 80) or None,
                    "cuisine": core.clean_text(c.get("cuisine") or "", 80) or None})
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def find(q: str, generate=None) -> dict:
    import gemini_client
    generate = generate or gemini_client.generate
    res = generate(PROMPT.format(q=q.replace('"', "'"), n=MAX_CANDIDATES), grounded=True, max_tokens=3000, temperature=0.1)
    try:
        data = gemini_client.extract_json(res.text)
    except gemini_client.GeminiError:
        data = {}
    return {"candidates": filter_candidates(data, res.grounded), "grounded": res.grounded,
            "engine": res.model, "sources": res.sources}
