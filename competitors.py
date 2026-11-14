"""Competitor comparison ("How you compare").

Live: one Gemini call with Google Search grounding finds up to 8 similar restaurants within ~20 miles,
with rating, reviews, category, which of the target's 10 keywords they appear for, and words their
listing/site uses. Every value is sanitized; anything missing or out of range becomes None and is shown
as "not found". Nothing is ever filled in with a guess.

Demo (Tikka N Kabab): seeded from the team's by-hand checks (data/competitors_tikka.json). A live
enrichment may fill ONLY fields that are still empty; hand-check values are never overwritten.
"""
from __future__ import annotations

import html
import json
import math
import re
import statistics
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED_TIKKA = ROOT / "data" / "competitors_tikka.json"
MAX_COMPETITORS = 8
MAX_RADIUS_MI = 20
LIVE_LABEL = "Gemini + Google Search lookup (unverified; check the listing)"
NF = "not found"
CMP_FIELDS = ["name", "address", "distance_mi", "rating", "review_count", "category", "keywords_ranked", "listing_keywords"]

PROMPT = """Use Google Search. Target restaurant: {name}, {address}. Cuisine: {cuisine}.
Find up to {cap} OTHER restaurants with the same or similar cuisine within {radius} miles of the target
that compete for the same local searches (Google Maps local pack, Google results, AI assistant answers).
For each competitor report ONLY values you found in search results (Google Maps/Business Profile, the
restaurant's own site, Yelp, etc.). Use null for anything you could not find. Do NOT estimate or guess.
- name, address (full street address)
- lat, lng (only if found), distance_miles from the target (only if found or computable from addresses)
- rating (Google star rating) and review_count (Google review count)
- category (their Google Business Profile primary category, e.g. "Indian restaurant")
- keywords_ranked: which of THESE target keywords they appear to rank for or get cited for: {keywords}
- listing_keywords: up to 6 dish/feature words their listing or website uses (e.g. "biryani", "halal" only if they say so)
- source_urls: 1-3 URLs where you found the data
Also report the target's own Google rating, review_count and category if found.
Return ONLY JSON: {{"target":{{"rating":null,"review_count":null,"category":null}},
"competitors":[{{"name":"","address":null,"lat":null,"lng":null,"distance_miles":null,"rating":null,
"review_count":null,"category":null,"keywords_ranked":[],"listing_keywords":[],"source_urls":[]}}]}}"""

ENRICH_PROMPT = """Use Google Search. These restaurants are near {address}. For each, report ONLY values you
found in search results (Google Business Profile, own site, Yelp). Use null for anything not found; never guess.
Fields: name (as given), address, lat, lng, rating (Google stars), review_count (Google), category (Google primary category).
Restaurants: {names}
Return ONLY JSON: {{"competitors":[{{"name":"","address":null,"lat":null,"lng":null,"rating":null,"review_count":null,"category":null,"source_urls":[]}}]}}"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


# --------------------------------------------------------------------------- sanitizing
def _num(v, lo, hi, cast=float):
    if v is None or isinstance(v, bool):
        return None
    try:
        x = cast(float(re.sub(r"[^0-9.\-]", "", str(v)))) if isinstance(v, str) else cast(v)
    except (ValueError, TypeError):
        return None
    return x if lo <= x <= hi else None


def _str(v, n=160):
    if not isinstance(v, str):
        return None
    v = re.sub(r"\s+", " ", v).strip()
    return v[:n] if v and v.lower() not in ("null", "none", "unknown", "n/a", "not found") else None


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def haversine_mi(lat1, lng1, lat2, lng2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _urls(v):
    return [u for u in (v or []) if isinstance(u, str) and re.match(r"^https?://", u)][:3] if isinstance(v, list) else []


def sanitize_competitor(c: dict, target: dict, keywords: list[str], source: str) -> dict | None:
    if not isinstance(c, dict):
        return None
    name = _str(c.get("name"), 120)
    if not name or _norm_name(name) == _norm_name(target.get("name", "")):
        return None
    kwset = {k.lower(): k for k in keywords}
    kr = [kwset[k.lower().strip()] for k in (c.get("keywords_ranked") or []) if isinstance(k, str) and k.lower().strip() in kwset]
    lk = [x for x in (_str(k, 40) for k in (c.get("listing_keywords") or []) if isinstance(k, str)) if x][:6]
    out = {"name": name, "address": _str(c.get("address"), 200), "distance_mi": None, "distance_basis": None,
           "rating": _num(c.get("rating"), 1.0, 5.0), "review_count": _num(c.get("review_count"), 0, 500000, int),
           "category": _str(c.get("category"), 80), "keywords_ranked": list(dict.fromkeys(kr)),
           "listing_keywords": list(dict.fromkeys(lk)), "source_urls": _urls(c.get("source_urls")),
           "notes": _str(c.get("notes"), 400), "source": c.get("source") or source}
    lat, lng = _num(c.get("lat"), -90, 90), _num(c.get("lng"), -180, 180)
    tlat, tlng = _num(target.get("lat"), -90, 90), _num(target.get("lng"), -180, 180)
    if lat and lng and tlat and tlng:
        out["distance_mi"] = round(haversine_mi(tlat, tlng, lat, lng), 1)
        out["distance_basis"] = "straight line from looked-up coordinates"
    elif _num(c.get("distance_miles", c.get("distance_mi")), 0, 100) is not None:
        out["distance_mi"] = round(_num(c.get("distance_miles", c.get("distance_mi")), 0, 100), 1)
        out["distance_basis"] = "as reported by the search lookup"
    if out["distance_mi"] is not None and out["distance_mi"] > MAX_RADIUS_MI + 5:
        return None  # outside the comparison radius
    return out


def sanitize_result(data: dict, target: dict, keywords: list[str], source: str) -> dict:
    comps, seen = [], set()
    for c in (data or {}).get("competitors", []) or []:
        s = sanitize_competitor(c, target, keywords, source)
        if s and _norm_name(s["name"]) not in seen:
            seen.add(_norm_name(s["name"]))
            comps.append(s)
        if len(comps) >= MAX_COMPETITORS:
            break
    t = (data or {}).get("target") or {}
    tgt = {"rating": _num(t.get("rating"), 1.0, 5.0), "review_count": _num(t.get("review_count"), 0, 500000, int),
           "category": _str(t.get("category"), 80), "source": source}
    return {"target": tgt, "competitors": comps}


# --------------------------------------------------------------------------- fetching
def find_live(target: dict, keywords: list[str], generate=None) -> dict:
    """One grounded Gemini call. Raises gemini_client.GeminiError on failure."""
    import gemini_client
    generate = generate or gemini_client.generate
    prompt = PROMPT.format(name=target.get("name", ""), address=target.get("address", ""), cuisine=target.get("cuisine", ""),
                           cap=MAX_COMPETITORS, radius=MAX_RADIUS_MI, keywords=json.dumps(keywords))
    res = generate(prompt, grounded=True, max_tokens=8000, temperature=0.1)
    data = gemini_client.extract_json(res.text)
    out = sanitize_result(data, target, keywords, LIVE_LABEL)
    out.update(mode="live", engine=res.model, grounded=res.grounded, search_sources=res.sources,
               fetched=date.today().isoformat())
    if not res.grounded:
        out["warning"] = "Google Search grounding was unavailable, so these values come from the model alone. Treat all as unverified."
    return out


def tikka_seed() -> dict:
    seed = json.loads(SEED_TIKKA.read_text())
    tgt = dict(seed["target"])
    comps = [dict(c, source_urls=[], distance_basis=None, field_sources={}) for c in seed["competitors"]]
    return {"target": tgt, "competitors": comps, "mode": "seed", "engine": "team hand check",
            "fetched": None, "search_sources": []}


def enrich_seed(seed: dict, target: dict, generate=None) -> dict:
    """Fill ONLY empty fields of seeded competitors from one grounded lookup. Hand-check values win."""
    import gemini_client
    generate = generate or gemini_client.generate
    names = [c["name"] for c in seed["competitors"]]
    res = generate(ENRICH_PROMPT.format(address=target.get("address", ""), names=json.dumps(names)),
                   grounded=True, max_tokens=6000, temperature=0.1)
    if not res.grounded:  # ungrounded = model memory; not good enough for facts
        return seed
    live = sanitize_result(gemini_client.extract_json(res.text), {"name": "", **{k: target.get(k) for k in ("lat", "lng")}},
                           [], LIVE_LABEL)
    by = {_norm_name(c["name"]): c for c in live["competitors"]}
    out = json.loads(json.dumps(seed))
    for c in out["competitors"]:
        l = by.get(_norm_name(c["name"]))
        if not l:
            continue
        fs = c.setdefault("field_sources", {})
        for f in ("address", "rating", "review_count", "category", "distance_mi"):
            if c.get(f) is None and l.get(f) is not None:
                c[f] = l[f]
                fs[f] = LIVE_LABEL
                if f == "distance_mi":
                    c["distance_basis"] = l.get("distance_basis")
        if l.get("source_urls"):
            c["source_urls"] = l["source_urls"]
    out.update(mode="seed+live", engine=res.model, fetched=date.today().isoformat(), search_sources=res.sources)
    return out


# --------------------------------------------------------------------------- analysis
def _fmt(v, kind=""):
    if v is None:
        return NF
    if kind == "reviews":
        return f"{v:,}"
    if kind == "dist":
        return f"{v} mi"
    return str(v)


def analyze(target: dict, cmp: dict, keywords: list[str], target_stands: list[dict] | None = None) -> dict:
    """Compare-and-contrast + 'Close the gap' steps. Only uses values present in the data."""
    comps = cmp.get("competitors", [])
    t = cmp.get("target", {}) or {}
    t_rating, t_reviews, t_cat = t.get("rating"), t.get("review_count"), t.get("category")
    name = target.get("name", "You")
    findings, steps = [], []

    rated = [c for c in comps if c.get("rating") is not None]
    if t_rating is not None and rated:
        higher = sorted([c for c in rated if c["rating"] > t_rating], key=lambda c: -c["rating"])
        lower = [c for c in rated if c["rating"] < t_rating]
        med = statistics.median(c["rating"] for c in rated)
        findings.append(f"Rating: you are {t_rating} vs a competitor median of {med:.1f} ({len(rated)} with a rating found). "
                        + (f"Higher than you: {', '.join(c['name'] + ' ' + str(c['rating']) for c in higher[:3])}. " if higher else "No competitor found with a higher rating. ")
                        + (f"Lower: {len(lower)}." if lower else ""))
        if higher:
            steps.append(f"Rating gap to {higher[0]['name']} ({higher[0]['rating']} vs your {t_rating}): reply to every review within 48 hours "
                         "and fix the top complaint theme in your recent reviews. Never filter, buy or incentivize reviews.")
    elif t_rating is None:
        findings.append("Rating: your own Google rating was not found; check it on your Business Profile.")

    counted = [c for c in comps if c.get("review_count") is not None]
    if t_reviews is not None and counted:
        more = sorted([c for c in counted if c["review_count"] > t_reviews], key=lambda c: -c["review_count"])
        med = statistics.median(c["review_count"] for c in counted)
        findings.append(f"Reviews: you have {t_reviews:,} vs a competitor median of {int(med):,}. "
                        + (f"Most: {more[0]['name']} with {more[0]['review_count']:,} ({more[0]['review_count'] - t_reviews:,} more than you)." if more else "You have the most reviews of those found."))
        if more:
            near = min(more, key=lambda c: c["review_count"])
            steps.append(f"Review-count gap: {near['name']} has {near['review_count']:,} reviews vs your {t_reviews:,} "
                         f"({near['review_count'] - t_reviews:,} apart). Send the honest review text to every real customer after each visit, "
                         "ask them to mention what they ordered, and track the count weekly.")

    cats = [c for c in comps if c.get("category")]
    if cats:
        generic = (t_cat or "").strip().lower() in ("restaurant", "")
        specific = [c for c in cats if c["category"].lower() != "restaurant"]
        if t_cat:
            findings.append(f"Category: yours is '{t_cat}'. Competitors use: " + ", ".join(sorted({c['category'] for c in cats})) + ".")
        if generic and specific:
            ex = specific[0]
            steps.append(f"Category: {ex['name']} uses the specific category '{ex['category']}'"
                         + (f" while yours is the generic '{t_cat}'" if t_cat else " and yours was not found")
                         + ". Set a specific primary category that matches your cuisine plus 2-3 secondary categories on your Business Profile.")

    cov = {k: [c["name"] for c in comps if k in c.get("keywords_ranked", [])] for k in keywords}
    you = {}
    for s in target_stands or []:
        v = (s.get("maps_today") or "").lower()
        you[s["keyword"]] = None if ("checked" in v or not v) else ("not in top 20" not in v and "not found" not in v)
    contested = [(k, v) for k, v in cov.items() if v]
    if contested:
        findings.append("Keyword coverage: competitors appear for " + "; ".join(f"'{k}' ({', '.join(v[:3])})" for k, v in contested[:5]) + ".")
        for k, v in contested[:3]:
            steps.append(f"Keyword '{k}': {', '.join(v[:2])} appear for it. Add the dish/term to your Business Profile menu with a photo, "
                         "publish the matching web page from this plan, and feature it in this week's Google post; re-check from an incognito window.")
    open_kws = [k for k, v in cov.items() if not v]
    if comps and open_kws and any(c.get("keywords_ranked") for c in comps):
        findings.append(f"No competitor data yet for: {', '.join(open_kws[:5])} (not checked, or no competitor found). Check these by hand; they may be the easiest openings.")

    t_text = " ".join(str(target.get(k, "")) for k in ("cuisine", "features", "menu_items")).lower()
    words = {}
    for c in comps:
        for w in c.get("listing_keywords", []):
            if w.lower() not in t_text:
                words.setdefault(w.lower(), []).append(c["name"])
    if words:
        top = sorted(words.items(), key=lambda kv: -len(kv[1]))[:6]
        findings.append("Words competitors' listings use that yours doesn't show: " + ", ".join(f"'{w}' ({len(n)})" for w, n in top) + ".")
        w, n = top[0]
        steps.append(f"Listing words: '{w}' appears on {', '.join(n[:2])}'s listing but not yours. If it is true for you, add it to your "
                     "description, menu or attributes (only claims you can back up).")

    if not comps:
        findings.append("No competitors were found with verifiable data. Check Google Maps by hand for your top keywords.")
    unknown = sum(1 for c in comps for f in ("rating", "review_count", "category") if c.get(f) is None)
    if unknown:
        steps.append(f"Fill the {unknown} 'not found' cells by hand: search each competitor on Google Maps (incognito) and record rating, reviews and category.")
    return {"findings": findings, "close_the_gap": steps[:7], "coverage": cov}


# --------------------------------------------------------------------------- rendering
def _src_mark(c, f):
    return " †" if (c.get("field_sources") or {}).get(f) else ""


def render_html(target: dict, cmp: dict, analysis: dict, keywords: list[str]) -> str:
    t = cmp.get("target", {}) or {}
    rows = [f"<tr style='background:#fff7ed'><td><b>{esc(target.get('name'))} (you)</b></td><td>{esc(target.get('address') or NF)}</td><td>-</td>"
            f"<td>{esc(_fmt(t.get('rating')))}</td><td>{esc(_fmt(t.get('review_count'), 'reviews'))}</td><td>{esc(t.get('category') or NF)}</td>"
            f"<td>see section 2</td><td class='muted'>{esc(t.get('source', ''))}</td></tr>"]
    for c in cmp.get("competitors", []):
        kws = ", ".join(c.get("keywords_ranked") or []) or NF
        links = " ".join(f"<a href='{esc(u)}' target='_blank' rel='noopener'>[{i + 1}]</a>" for i, u in enumerate(c.get("source_urls") or []))
        dist = _fmt(c.get("distance_mi"), "dist") + (f" <span class='muted'>({esc(c['distance_basis'])})</span>" if c.get("distance_basis") else "")
        rows.append(f"<tr><td><b>{esc(c['name'])}</b>{('<br><span class=muted>' + esc(c['notes']) + '</span>') if c.get('notes') else ''}</td>"
                    f"<td>{esc(c.get('address') or NF)}{_src_mark(c, 'address')}</td><td>{dist}{_src_mark(c, 'distance_mi')}</td>"
                    f"<td>{esc(_fmt(c.get('rating')))}{_src_mark(c, 'rating')}</td><td>{esc(_fmt(c.get('review_count'), 'reviews'))}{_src_mark(c, 'review_count')}</td>"
                    f"<td>{esc(c.get('category') or NF)}{_src_mark(c, 'category')}</td><td>{esc(kws)}"
                    f"{('<br><span class=muted>uses: ' + esc(', '.join(c['listing_keywords'])) + '</span>') if c.get('listing_keywords') else ''}</td>"
                    f"<td class='muted'>{esc(c.get('source'))} {links}</td></tr>")
    cov_rows = "".join(f"<tr><td>{esc(k)}</td><td>{len(v)}</td><td>{esc(', '.join(v) or '-')}</td></tr>" for k, v in analysis["coverage"].items())
    mode = cmp.get("mode")
    banner = {"live": f"Found by {LIVE_LABEL} on {cmp.get('fetched')}. Values are what search returned; 'not found' means we could not verify it.",
              "seed": "From the team's by-hand checks. 'not found' = not checked yet.",
              "seed+live": f"From the team's by-hand checks; cells marked † were filled by a {LIVE_LABEL} on {cmp.get('fetched')}. Hand-check values were never overwritten."}.get(mode, "")
    warn = f"<p class='warn'>⚠ {esc(cmp['warning'])}</p>" if cmp.get("warning") else ""
    src = "".join(f"<li><a href='{esc(s['uri'])}' target='_blank' rel='noopener'>{esc(s.get('title') or s['uri'])}</a></li>" for s in cmp.get("search_sources") or [])
    return f"""
<h2 id="compare">How you compare</h2>
<div class="card"><p class="muted">Similar restaurants within ~{MAX_RADIUS_MI} miles (max {MAX_COMPETITORS}). {esc(banner)}</p>{warn}
<div style="overflow-x:auto"><table><tr><th>Restaurant</th><th>Address</th><th>Distance</th><th>Rating</th><th>Reviews</th><th>Category</th><th>Target keywords they appear for</th><th>Source</th></tr>
{''.join(rows)}</table></div>
<h3>Compare and contrast</h3><ul>{''.join(f'<li>{esc(f)}</li>' for f in analysis['findings'])}</ul>
<h3>Keyword coverage (of your 10)</h3><table><tr><th>Keyword</th><th># competitors</th><th>Who</th></tr>{cov_rows}</table>
{('<details><summary>Search sources</summary><ul>' + src + '</ul></details>') if src else ''}
</div>"""


def render_plan_html(steps30: list[tuple[str, str]], close: list[str]) -> str:
    rows = "".join(f"<tr><td><b>{esc(a)}</b></td><td>{esc(b)}</td></tr>" for a, b in steps30)
    cg = "".join(f"<li>{esc(s)}</li>" for s in close) or "<li>No competitor gaps with verifiable data yet.</li>"
    return f"""
<h2 id="plan30">30-day plan</h2><div class="card"><table><tr><th>When</th><th>Action</th></tr>{rows}</table>
<h3>Close the gap</h3><p class="muted">Concrete steps tied to the competitor findings above.</p><ol>{cg}</ol></div>"""
