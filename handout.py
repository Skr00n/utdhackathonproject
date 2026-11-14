"""Handout steps 2-6 for Page One Builder.

2. Where it stands today (Maps top 3 / Google page 1 / AI assistants)
3. Gap analysis vs whoever wins each keyword
4. Fixes ready to paste (description, 4 weekly posts, menu copy, page per group, 5 FAQs, review text)
5. STRETCH: rank grid map (1/3/5 miles x 8 directions + center)
6. One PDF with everything + a 30-day plan

LIVE vs ESTIMATED: when a Gemini key works, steps 2/3/5 use Gemini with Google Search
grounding (if the SDK supports it) and a direct "best X near Y" question for the AEO check.
Without a key (offline) every value is a deterministic SAMPLE/SIMULATED estimate and is
labeled that way everywhere. Nothing offline is claimed to be live.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import re
from pathlib import Path

GROUP_LABEL = {"dish": "Dish", "cuisine_near_me": "Cuisine + area", "occasion_feature": "Need / occasion"}
DIRS = [("N", 0), ("NE", 45), ("E", 90), ("SE", 135), ("S", 180), ("SW", 225), ("W", 270), ("NW", 315)]
RINGS = [1, 3, 5]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _seed(*parts) -> int:
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def city_of(addr: str) -> str:
    m = re.search(r"([A-Za-z .]+),\s*([A-Z]{2})", addr or "")
    return f"{m.group(1).strip()}, {m.group(2)}" if m else (addr or "the area")


# ----------------------------------------------------------------------------- Gemini helpers
def _client():
    from google import genai
    import os
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _ask(model: str, prompt: str, grounded: bool = False, max_tokens: int = 4000) -> tuple[str, bool]:
    """Returns (text, grounded_used). Tries Google Search grounding, falls back to plain."""
    from google.genai import types
    client = _client()
    if grounded:
        try:
            cfg = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())],
                                              temperature=0.2, max_output_tokens=max_tokens)
            return (client.models.generate_content(model=model, contents=prompt, config=cfg).text or ""), True
        except Exception as e:
            print(f"  ! grounding unavailable ({type(e).__name__}); asking without search")
    cfg = types.GenerateContentConfig(temperature=0.2, max_output_tokens=max_tokens)
    return (client.models.generate_content(model=model, contents=prompt, config=cfg).text or ""), False


def _json_from(text: str):
    text = re.sub(r"```(?:json)?", "", text or "")
    m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
    return json.loads(m.group(1)) if m else json.loads(text)


# ----------------------------------------------------------------------------- 2 + 3: where it stands, gaps
def _sample_competitors(kw: str, city: str) -> list[str]:
    pool = [f"Competitor {c}" for c in "ABCDEFGHIJ"]  # placeholders; live mode fills real names
    s = _seed(kw)
    return [pool[(s + i * 3) % len(pool)] + " (sample)" for i in range(3)]


GAP_AREAS = ["categories", "menu items", "photos", "reviews (count/rating)", "review words", "hours", "website", "posts"]


def sample_stands(r: dict, plan: dict) -> list[dict]:
    """No live data and no manual data: show 'to be checked by hand' (never fake positions)."""
    rows = []
    for t in plan["top10"]:
        kw = t["keyword"]; s = _seed(r["name"], kw)
        rows.append({
            "keyword": kw, "group": GROUP_LABEL.get(t.get("intent_group"), t.get("intent_group")),
            "maps_today": "to be checked by hand", "maps_rank": None, "in_top3": False,
            "page1": "to be checked by hand", "ai_names_it": "to be checked by hand",
            "top3": ["to be checked by hand"],
            "biggest_gap": _sample_gap(t, s, r),
            "gaps": _sample_gap_table(t, s, r),
            "source": "NOT YET CHECKED: fill data/rankings_manual.csv by hand (gaps below are likely gaps to verify)",
        })
    return rows


def _item(kw: str) -> str:
    return re.sub(r"\s+(near me|near utd|dallas.*|north dallas|richardson)$", "", kw).strip()


def _sample_gap(t: dict, s: int, r: dict) -> str:
    kw = _item(t["keyword"])
    opts = [f"Likely: winners have more reviews that mention '{kw}' (verify)",
            f"Likely: winners list '{kw}' as a named menu item with a photo (verify)",
            "Likely: winners post weekly on Google; check our last post date (verify)",
            "Likely: winners have a web page for this search; we have no website listed (verify)",
            "Likely: winners use a more specific primary category (verify)"]
    return opts[s % len(opts)]


def _sample_gap_table(t: dict, s: int, r: dict) -> dict:
    kw = _item(t["keyword"])
    cats = t.get("gbp", {}).get("categories", [])
    rating = re.search(r"rating\s*([0-9.]+)", r.get("features", ""))
    return {
        "categories": f"Check winner's primary category. Fix: primary '{cats[0] if cats else 'Restaurant'}' + secondary {', '.join(cats[1:3])} (today: generic 'Restaurant').",
        "menu items": f"Check if winner lists '{kw}' by name. Fix: add every menu item with price + 1-line description (below).",
        "photos": "Compare photo count + recency. Fix: upload 10 real food/storefront photos now, 3 per week.",
        "reviews (count/rating)": f"Compare winner's count/rating vs ours ({rating.group(1) if rating else '?'} stars). Fix: ask every real customer (text below).",
        "review words": f"Check if winner's reviews mention '{kw}'. Fix: ask customers to mention what they ordered (never script wording).",
        "hours": f"Check winner's hours/holiday hours. Fix: confirm {r.get('hours') or 'hours'} and add holiday hours.",
        "website": "Winner usually links a site with menu + schema. Fix: publish the pages below ([website] needed).",
        "posts": "Check winner's last post date. Fix: use the 4 weekly posts below.",
    }


STANDS_PROMPT = """You are checking local search results for a restaurant. Use Google Search.
Restaurant: {name}, {address}. Cuisine: {cuisine}.
For EACH keyword below, searched from {city}, report:
- top3: the 3 businesses that currently show in the Google Maps local pack (top 3)
- maps_rank: this restaurant's approximate Maps position (number) or null if not found in top 20
- page1: true/false whether this restaurant's website or listing appears on Google page 1
- gaps: for the #1 winner vs this restaurant, one short line each for: categories, menu items, photos,
  reviews (count/rating), review words, hours, website, posts
- biggest_gap: the single biggest gap in one line
If you cannot verify something say "unknown" rather than guessing.
Keywords: {keywords}
Return ONLY JSON: {{"rows":[{{"keyword":"","top3":["","",""],"maps_rank":null,"page1":false,
"gaps":{{"categories":"","menu items":"","photos":"","reviews (count/rating)":"","review words":"","hours":"","website":"","posts":""}},
"biggest_gap":""}}]}}"""


def live_stands(r: dict, plan: dict, model: str) -> list[dict]:
    city = city_of(r.get("address", ""))
    kws = [t["keyword"] for t in plan["top10"]]
    text, grounded = _ask(model, STANDS_PROMPT.format(city=city, keywords=json.dumps(kws), **{k: r.get(k, "") for k in ("name", "address", "cuisine")}), grounded=True, max_tokens=12000)
    data = {row.get("keyword", "").lower(): row for row in _json_from(text).get("rows", [])}
    src = "LIVE: Gemini + Google Search grounding" if grounded else "LIVE: Gemini estimate (no search grounding)"
    rows = []
    for t in plan["top10"]:
        kw = t["keyword"]; d = data.get(kw.lower(), {})
        mr = d.get("maps_rank")
        # Real AEO check: ask the assistant directly and look for the name in the answer
        try:
            ans, _ = _ask(model, f"What are the best places for {kw} near {city}? Name specific restaurants.", max_tokens=600)
            named = r["name"].lower().split(" (")[0] in ans.lower()
        except Exception:
            named = None
        rows.append({
            "keyword": kw, "group": GROUP_LABEL.get(t.get("intent_group"), t.get("intent_group")),
            "maps_today": f"#{mr}" if isinstance(mr, int) else "not found",
            "maps_rank": mr if isinstance(mr, int) else 21, "in_top3": isinstance(mr, int) and mr <= 3,
            "page1": "yes" if d.get("page1") is True else "no",
            "ai_names_it": {True: "yes", False: "no", None: "unknown"}[named],
            "ai_check_gemini": {True: "yes", False: "no", None: "unknown"}[named],
            "top3": d.get("top3") or ["unknown"] * 3,
            "biggest_gap": d.get("biggest_gap") or "unknown",
            "gaps": d.get("gaps") or _sample_gap_table(t, _seed(kw), r),
            "source": src + "; AI check = direct Gemini question",
        })
    return rows


# ----------------------------------------------------------------------------- manual (by-hand) rankings
MANUAL_FIELDS = ["keyword", "maps_position", "maps_top3", "page1_yes_no", "ai_names_it", "notes"]


def load_manual(path) -> dict:
    """data/rankings_manual.csv filled BY HAND (incognito Google Maps / google.com / ask Gemini or ChatGPT)."""
    p = Path(path) if path else None
    if not p or not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8-sig") as f:
        rows = [{k.strip().lower(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    return {r["keyword"].lower(): r for r in rows if r.get("keyword") and any(r.get(k) for k in MANUAL_FIELDS[1:5])}


def write_manual_template(path, plan: dict):
    p = Path(path)
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="") as f:
        w = csv.writer(f); w.writerow(MANUAL_FIELDS)
        for t in plan["top10"]:
            w.writerow([t["keyword"], "", "", "", "", ""])


def apply_manual(stands: list[dict], manual: dict, gaps_path=None) -> int:
    n = 0
    gm = {}
    if gaps_path and Path(gaps_path).exists():  # optional by-hand gap notes: {keyword: {area: text}}
        gm = {k.lower(): v for k, v in json.loads(Path(gaps_path).read_text()).items() if not k.startswith("_")}
    for s in stands:
        if "*" in gm:  # applies to every keyword
            s["gaps"] = {**s["gaps"], **gm["*"]}
        if s["keyword"].lower() in gm:
            s["gaps"] = {**s["gaps"], **gm[s["keyword"].lower()]}
        m = manual.get(s["keyword"].lower())
        s.setdefault("ai_check_gemini", "not run")
        if not m:
            continue
        n += 1
        pos = m.get("maps_position", "")
        if pos:
            try:
                k = int(re.sub(r"[^0-9]", "", pos)); s["maps_today"] = f"#{k}"; s["maps_rank"] = k; s["in_top3"] = k <= 3; s["manual_pos"] = True
            except ValueError:
                if "not" in pos.lower():
                    s["maps_today"] = "not in top 20"; s["maps_rank"] = 21; s["in_top3"] = False; s["manual_pos"] = True
                else:  # e.g. "listed (exact # pending)"
                    s["maps_today"] = pos
        if m.get("maps_top3"):
            s["top3"] = [x.strip() for x in re.split(r"[;|]", m["maps_top3"]) if x.strip()] or s["top3"]
            s["gaps"] = {a: v.replace("(est.)", "(est. - verify vs " + s["top3"][0] + ")") for a, v in s["gaps"].items()}
        if m.get("page1_yes_no"):
            s["page1"] = m["page1_yes_no"].lower()
        if m.get("ai_names_it"):
            s["ai_names_it"] = m["ai_names_it"].lower()
        if m.get("notes"):
            s["biggest_gap"] = m["notes"]
        s["manual"] = True
        s["source"] = "MANUAL check by team (by hand; blanks = not checked yet)" + ("; " + s["source"] if "LIVE" in s["source"] else "")
    return n


# ----------------------------------------------------------------------------- 4: fixes
def build_fixes(r: dict, plan: dict) -> dict:
    name = r["name"]; city = city_of(r.get("address", ""))
    menu = [m.strip() for m in re.split(r"[;|]", r.get("menu_items", "")) if m.strip()]
    feats = [m.strip() for m in re.split(r"[;|]", r.get("features", "")) if m.strip()]
    kws = [t["keyword"] for t in plan["top10"]]
    def nm(m): return re.sub(r"\s*\$\d+(\.\d{2})?$", "", m).strip()
    def pr(m):
        x = re.search(r"\$(\d+(?:\.\d{2})?)$", m); return f"${x.group(1)}" if x else "[price]"
    first = menu[-1] if menu else "our signature dish"
    posts = [
        f"Week 1 - {nm(first)}: Crispy, made to order, {pr(first)}. Open daily {r.get('hours') or '[hours]'}. Tap Call to order: {r.get('phone') or '[phone]'}. [photo of the dish]",
        f"Week 2 - Snack time: {', '.join(nm(m) + ' ' + pr(m) for m in menu[:2])}. Perfect for a quick bite near UT Dallas. [photo of samosas]" if menu else "Week 2 - Snack time. [photo]",
        f"Week 3 - Try something new: {nm(menu[3]) if len(menu) > 3 else nm(first)} {pr(menu[3]) if len(menu) > 3 else ''} and {nm(menu[2]) if len(menu) > 2 else ''} {pr(menu[2]) if len(menu) > 2 else ''}. Visit us at {r.get('address')}. [photo]",
        f"Week 4 - Thank you, neighbors: we read every review. If you visited, an honest review helps others find us. Open daily {r.get('hours') or ''}. [storefront photo]",
    ]
    menu_desc = []
    for m in menu:
        rel = next((k for k in kws if nm(m).split()[0].lower() in k.lower()), None)
        menu_desc.append({"item": nm(m), "price": pr(m), "description":
                          f"{nm(m)} - made to order at {name} in North Dallas. {pr(m)}." + (f" (Targets: '{rel}')" if rel else "")})
    pages = {}
    for t in plan["top10"]:
        g = GROUP_LABEL.get(t.get("intent_group"), t.get("intent_group"))
        if g not in pages and t.get("website", {}).get("page_copy"):
            w = t["website"]
            pages[g] = {"keyword": t["keyword"], "title_tag": w.get("title_tag"), "meta_description": w.get("meta_description"),
                        "h1": w.get("h1"), "page_copy": w.get("page_copy"), "url": f"{(r.get('website') or '').rstrip('/')}/{re.sub(r'[^a-z0-9]+', '-', t['keyword'].lower()).strip('-')}"}
    review_sms = (f"Hi! Thanks for eating at {name}. If you have a minute, an honest Google review really helps a small "
                  f"local restaurant like ours: [review link]. Mentioning what you ordered helps others find it. Thank you! "
                  f"- the {name} team")
    return {"description": plan.get("gbp_description", ""), "weekly_posts": posts, "menu_descriptions": menu_desc,
            "pages": pages, "faqs": plan.get("faqs", [])[:5], "review_sms": review_sms,
            "review_rules": "Send only to real customers. No discounts, gifts or contests for reviews, never ask for 5 stars or specific wording, never review-gate."}


# ----------------------------------------------------------------------------- 5: rank grid
def grid_points(lat: float, lng: float) -> list[dict]:
    pts = [{"label": "center", "miles": 0, "dir": "C", "lat": lat, "lng": lng}]
    for mi in RINGS:
        for d, deg in DIRS:
            dlat = mi / 69.0 * math.cos(math.radians(deg))
            dlng = mi / (69.0 * math.cos(math.radians(lat))) * math.sin(math.radians(deg))
            pts.append({"label": f"{mi}mi {d}", "miles": mi, "dir": d, "lat": round(lat + dlat, 5), "lng": round(lng + dlng, 5)})
    return pts


def simulate_grid(r: dict, stands: list[dict], pts: list[dict]) -> list[dict]:
    rows = []
    for s in stands:
        base = s.get("maps_rank") or (6 + _seed(r["name"], s["keyword"]) % 10)  # unknown -> simulated baseline
        for p in pts:
            noise = _seed(r["name"], s["keyword"], p["label"]) % 3
            rank = base if p["miles"] == 0 else min(21, int(base + p["miles"] * 1.6 + noise))
            src = "SIMULATED estimate" + (" (center = manual Maps position)" if s.get("manual_pos") else " (no real rank data yet)")
            rows.append({"keyword": s["keyword"], **p, "rank": rank, "source": src})
    return rows


GRID_PROMPT = """Use Google Search. Restaurant: {name}, {address}. Estimate this restaurant's Google Maps rank
(1-20, or 21 if not in top 20) for the search "{kw}" when the searcher stands at each point below.
Rank usually worsens with distance and depends on competitors near each point. Points: {pts}
Return ONLY JSON: {{"ranks":[<one integer per point, same order>]}}"""


def live_grid(r: dict, stands: list[dict], pts: list[dict], model: str) -> list[dict]:
    rows = []
    for s in stands:
        try:
            text, g = _ask(model, GRID_PROMPT.format(name=r["name"], address=r.get("address"), kw=s["keyword"],
                                                    pts=json.dumps([[p["label"], p["lat"], p["lng"]] for p in pts])), grounded=True, max_tokens=1500)
            ranks = [int(x) for x in _json_from(text)["ranks"]]
            assert len(ranks) == len(pts)
            src = "Gemini grounded ESTIMATE" if g else "Gemini ESTIMATE"
        except Exception as e:
            print(f"  ! grid estimate failed for '{s['keyword']}' ({type(e).__name__}); simulated")
            rows += simulate_grid(r, [s], pts); continue
        if s.get("manual_pos"):
            ranks[0] = s["maps_rank"]; src += " (center = manual Maps position)"
        rows += [{"keyword": s["keyword"], **p, "rank": max(1, min(21, k)), "source": src} for p, k in zip(pts, ranks)]
    return rows


def _color(rank: int) -> str:
    return "#16a34a" if rank <= 3 else "#84cc16" if rank <= 7 else "#f59e0b" if rank <= 12 else "#dc2626"


def render_grid_html(r: dict, rows: list[dict]) -> str:
    """Pure SVG/HTML heatmap, no dependencies, keyword dropdown."""
    kws = list(dict.fromkeys(x["keyword"] for x in rows))
    src = rows[0]["source"] if rows else ""
    size, maxmi = 520, 5.6
    def xy(p):
        lat0, lng0 = rows[0]["lat"], rows[0]["lng"]
        dx = (p["lng"] - lng0) * 69.0 * math.cos(math.radians(lat0)); dy = (p["lat"] - lat0) * 69.0
        return size / 2 + dx / maxmi * size / 2, size / 2 - dy / maxmi * size / 2
    svgs = []
    for i, kw in enumerate(kws):
        pts = [x for x in rows if x["keyword"] == kw]
        rings = "".join(f'<circle cx="{size/2}" cy="{size/2}" r="{mi/maxmi*size/2}" fill="none" stroke="#cbd5e1" stroke-dasharray="4 4"/>'
                        f'<text x="{size/2+4}" y="{size/2 - mi/maxmi*size/2 - 4}" font-size="11" fill="#64748b">{mi} mi</text>' for mi in RINGS)
        dots = "".join(f'<g><title>{esc(p["label"])}: rank {p["rank"] if p["rank"] <= 20 else "20+"}</title><circle cx="{xy(p)[0]:.1f}" cy="{xy(p)[1]:.1f}" r="17" fill="{_color(p["rank"])}" stroke="#fff" stroke-width="2"/>'
                       f'<text x="{xy(p)[0]:.1f}" y="{xy(p)[1]+4:.1f}" text-anchor="middle" font-size="12" font-weight="bold" fill="#fff">{p["rank"] if p["rank"] <= 20 else "20+"}</text></g>' for p in pts)
        avg = sum(p["rank"] for p in pts) / len(pts); top3 = sum(p["rank"] <= 3 for p in pts)
        svgs.append(f'<div class="kw" id="kw{i}" style="display:{"block" if i == 0 else "none"}"><p>Average rank <b>{avg:.1f}</b> · top-3 at <b>{top3}/{len(pts)}</b> points</p>'
                    f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" style="background:#f1f5f9;border-radius:12px">{rings}{dots}'
                    f'<text x="{size/2}" y="16" text-anchor="middle" font-size="12" fill="#475569">N</text></svg></div>')
    opts = "".join(f'<option value="{i}">{esc(k)}</option>' for i, k in enumerate(kws))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Rank grid - {esc(r['name'])}</title>
<style>body{{font:15px system-ui,sans-serif;margin:24px;color:#0f172a}}select{{font-size:15px;padding:6px}}.lg span{{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;margin-right:6px}}.note{{background:#fef3c7;padding:8px 12px;border-radius:8px}}</style></head><body>
<h2>Rank grid: {esc(r['name'])}</h2>
<p class="note">Data source: <b>{esc(src)}</b>. Points at 1, 3 and 5 miles in 8 directions + the restaurant (center). {'These are not live rankings.' if 'SIMULATED' in src else 'Model estimates; verify by searching from each spot.'}</p>
<p>Keyword: <select onchange="document.querySelectorAll('.kw').forEach(d=>d.style.display='none');document.getElementById('kw'+this.value).style.display='block'">{opts}</select></p>
<p class="lg"><span style="background:#16a34a">1-3</span><span style="background:#84cc16">4-7</span><span style="background:#f59e0b">8-12</span><span style="background:#dc2626">13+</span></p>
{''.join(svgs)}</body></html>"""


def write_grid(outdir: Path, r: dict, rows: list[dict]):
    with open(outdir / "rank_grid.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["keyword", "label", "miles", "dir", "lat", "lng", "rank", "source"])
        w.writeheader(); [w.writerow(x) for x in rows]
    (outdir / "rank_grid.html").write_text(render_grid_html(r, rows))


# ----------------------------------------------------------------------------- 6: 30-day plan + PDF
def thirty_day_plan(fixes: dict) -> list[tuple[str, str]]:
    return [
        ("Day 1", "Record 'where it stands' baseline (Maps, page 1, AI) for all 10 keywords; save rank_grid.csv."),
        ("Day 1", "Fix the website title tag (currently 'Best Hamburgers in Dallas') to the new title in section 4."),
        ("Day 1-2", "Update Google Business Profile: primary/secondary categories, new description, hours incl. holidays."),
        ("Day 2-3", "Add keyword-rich menu descriptions to the GBP menu and website; upload 10 real photos."),
        ("Day 3", "Start review asks: send the review text to real customers after each visit (no incentives)."),
        ("Day 4", "Publish Week 1 Google post."),
        ("Day 5-7", "Publish one web page per keyword group with Restaurant + FAQ schema; test in Rich Results Test."),
        ("Day 8-10", "Add the 5 FAQ answers to the site and GBP Q&A; submit pages in Google Search Console."),
        ("Day 11", "Publish Week 2 Google post; add 3 new photos."),
        ("Day 14", "Re-check all 10 keywords and the rank grid; compare to baseline."),
        ("Day 18", "Publish Week 3 Google post; reply to every new review."),
        ("Day 21", "Fix the biggest remaining gap per keyword from the gap table."),
        ("Day 25", "Publish Week 4 Google post; add 3 new photos."),
        ("Day 30", "Final re-check: Maps top 3, page 1, AI mentions, rank grid. Report before/after."),
    ]


def write_pdf(outdir: Path, r: dict, plan: dict, stands: list[dict], fixes: dict, grid_rows: list[dict], meta: dict) -> Path:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    except ImportError:
        p = outdir / "page_one_plan.html"
        p.write_text(render_plan_html(r, plan, stands, fixes, grid_rows, meta))
        print("  ! reportlab not installed; wrote page_one_plan.html instead (pip install reportlab)")
        return p
    ss = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=ss["BodyText"], fontSize=8, leading=10)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=12.5)
    P = lambda t, st=body: Paragraph(esc(t).replace("\n", "<br/>"), st)
    def table(data, widths):
        t = Table([[P(c, small) for c in row] for row in data], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c2d12")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d6c4a8")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t
    live = meta.get("mode") == "live"
    st = [Paragraph(f"Page One Plan: {esc(r['name'])}", ss["Title"]),
          P(f"{r.get('cuisine','')} · {r.get('address','')} · generated {meta.get('date','')}"),
          P(f"Data mode: {'LIVE (Gemini ' + str(meta.get('engine')) + ')' if live else 'OFFLINE SAMPLE: keyword plan is cached Gemini output; where-it-stands, gaps and rank grid are ESTIMATED/SIMULATED, not live lookups.'}"),
          P(f"Where-it-stands source: {stands[0]['source'] if stands else ''}. Rank grid source: {grid_rows[0]['source'] if grid_rows else ''}."),
          Spacer(1, 8), Paragraph("1. The 10 keywords", ss["Heading2"])]
    why = {k["keyword"].lower(): k for k in plan["keywords"]}
    st.append(table([["#", "Keyword", "Group", "Intent", "Why it matters"]] +
                    [[str(t["rank"]), t["keyword"], GROUP_LABEL.get(t.get("intent_group"), ""), why.get(t["keyword"].lower(), {}).get("est_intent", ""),
                      why.get(t["keyword"].lower(), {}).get("why", "")] for t in plan["top10"]], [0.3*inch, 1.8*inch, 1.1*inch, 0.6*inch, 3.4*inch]))
    st += [Paragraph("2. Where it stands today", ss["Heading2"]),
           table([["Keyword", "Maps today", "Page 1?", "AI names it?", "AI check (Gemini)", "Current top 3", "Biggest gap vs top 3"]] +
                 [[s["keyword"], s["maps_today"], s["page1"], s["ai_names_it"], s.get("ai_check_gemini", "not run"), ", ".join(s["top3"]), s["biggest_gap"]] for s in stands],
                 [1.2*inch, 0.75*inch, 0.55*inch, 0.65*inch, 0.65*inch, 1.5*inch, 1.9*inch]),
           P("How the by-hand check works: incognito window, search each keyword on google.com/maps (position or 'not in top 20', who is #1-#3), "
             "search google.com (is the site on page 1?), ask Gemini/ChatGPT the keyword as a question (is the restaurant named?). No paid SEO tools. "
             "Values marked (est.) are SAMPLE estimates until data/rankings_manual.csv is filled in.", small),
           Paragraph("3. Gap analysis vs the #1 result", ss["Heading2"])]
    if fixes.get("featured_gap"):
        ft = Table([[Paragraph("<b>" + esc(fixes["featured_gap"]) + "</b>", body)]], colWidths=[7.2*inch])
        ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fee2e2")), ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#dc2626"))]))
        st += [ft, Spacer(1, 6)]
    for s in stands[:10]:
        st += [Paragraph(f"<b>{esc(s['keyword'])}</b> (winner: {esc(s['top3'][0])})", body),
               table([["Area", "Gap and fix"]] + [[a, s["gaps"].get(a, "")] for a in GAP_AREAS], [1.4*inch, 5.8*inch]), Spacer(1, 4)]
    st += [PageBreak(), Paragraph("4. Fixes ready to paste", ss["Heading2"]),
           *([Paragraph("Website title tag (fix first)", ss["Heading3"]), P(fixes["website_title_tag"])] if fixes.get("website_title_tag") else []),
           Paragraph("Google Business Profile description", ss["Heading3"]), P(fixes["description"]),
           Paragraph("4 weekly Google posts", ss["Heading3"])] + [P(f"• {x}") for x in fixes["weekly_posts"]]
    st += [Paragraph("Keyword-rich menu descriptions", ss["Heading3"])] + [P(f"• {m['item']}: {m['description']}") for m in fixes["menu_descriptions"]]
    st += [Paragraph("One web page per keyword group", ss["Heading3"])]
    for g, pg in fixes["pages"].items():
        st += [P(f"[{g}] {pg['keyword']}  ->  {pg['url']}"), P(f"Title: {pg['title_tag']}\nMeta: {pg['meta_description']}\nH1: {pg['h1']}", small), P(pg["page_copy"], small), Spacer(1, 4)]
    st += [Paragraph("5 FAQ answers", ss["Heading3"])] + [P(f"Q: {f['q']}\nA: {f['a']}") for f in fixes["faqs"]]
    st += [Paragraph("Schema code (Restaurant + FAQPage JSON-LD)", ss["Heading3"]),
           P("Paste both blocks into the page <head>. Files: schema_restaurant.jsonld, schema_faq.jsonld (also embedded in landing.html).", small)]
    for fn in ("schema_restaurant.jsonld", "schema_faq.jsonld"):
        fp = outdir / fn
        if fp.exists():
            st.append(Paragraph(esc(fp.read_text()).replace("\n", "<br/>").replace("  ", "&nbsp;&nbsp;"), ParagraphStyle("c", parent=small, fontName="Courier", fontSize=7, leading=8.5)))
    st += [Paragraph("Review request text message", ss["Heading3"]), P(fixes["review_sms"]), P(fixes["review_rules"], small)]
    st += [Paragraph("5. Rank grid (1 / 3 / 5 miles)", ss["Heading2"]), P(f"Source: {grid_rows[0]['source'] if grid_rows else ''}. Interactive map: rank_grid.html. Average rank by distance:")]
    kws = list(dict.fromkeys(x["keyword"] for x in grid_rows))
    avg = lambda kw, mi: sum(x["rank"] for x in grid_rows if x["keyword"] == kw and x["miles"] == mi) / max(1, sum(1 for x in grid_rows if x["keyword"] == kw and x["miles"] == mi))
    st.append(table([["Keyword", "Center", "1 mi", "3 mi", "5 mi"]] + [[k] + [f"{avg(k, m):.1f}" for m in (0, 1, 3, 5)] for k in kws], [2.8*inch, 1.1*inch, 1.1*inch, 1.1*inch, 1.1*inch]))
    st += [Paragraph("6. 30-day plan", ss["Heading2"]), table([["When", "Action"]] + [list(x) for x in thirty_day_plan(fixes)], [0.9*inch, 6.3*inch]),
           Spacer(1, 8), P("Honest methods only: no fake reviews, no incentives for reviews, no fake clicks, no keyword stuffing.", small)]
    p = outdir / "page_one_plan.pdf"
    SimpleDocTemplate(str(p), pagesize=letter, leftMargin=0.6*inch, rightMargin=0.6*inch, topMargin=0.6*inch, bottomMargin=0.6*inch,
                      title=f"Page One Plan - {r['name']}").build(st)
    return p


def render_plan_html(r, plan, stands, fixes, grid_rows, meta) -> str:
    rows = "".join(f"<tr><td>{esc(s['keyword'])}</td><td>{esc(s['maps_today'])}</td><td>{esc(s['page1'])}</td><td>{esc(s['ai_names_it'])}</td><td>{esc(s['biggest_gap'])}</td></tr>" for s in stands)
    return (f"<!doctype html><meta charset=utf-8><title>Page One Plan</title><h1>Page One Plan: {esc(r['name'])}</h1><p>Mode: {esc(meta.get('mode'))}. Source: {esc(stands[0]['source'] if stands else '')}</p>"
            f"<h2>Where it stands</h2><table border=1><tr><th>Keyword</th><th>Maps today</th><th>Page 1?</th><th>AI names it?</th><th>Biggest gap</th></tr>{rows}</table>"
            f"<h2>Fixes</h2><pre>{esc(json.dumps(fixes, indent=2))}</pre><h2>30-day plan</h2><ul>{''.join(f'<li><b>{a}</b> {esc(b)}</li>' for a, b in thirty_day_plan(fixes))}</ul>")


# ----------------------------------------------------------------------------- orchestrator
def run_handout(outdir: Path, r: dict, plan: dict, meta: dict, model: str, live: bool, simulate_grid: bool = False,
                manual_path=None, ai_check: bool = True) -> dict:
    stands = None
    manual = load_manual(manual_path)
    if manual_path and not Path(manual_path).exists():
        write_manual_template(manual_path, plan)
        print(f"→ Wrote blank manual rankings template: {manual_path} (fill it in by hand, then re-run)")
    if not ai_check:
        live = False
    if live:
        try:
            print("→ Where it stands: asking Gemini (Google Search grounding) + direct AI check ...")
            stands = live_stands(r, plan, model)
        except Exception as e:
            print(f"! Live 'where it stands' failed ({type(e).__name__}: {str(e)[:150]}); using SAMPLE estimates")
    if stands is None:
        stands = sample_stands(r, plan)
    n_manual = apply_manual(stands, manual, Path(manual_path).with_name("gaps_manual.json") if manual_path else None)
    print(f"✓ Manual rankings applied for {n_manual}/{len(stands)} keywords" if n_manual else "! No manual rankings filled in yet; where-it-stands shows " + ("Gemini estimates" if live else "'to be checked by hand'"))
    fixes = build_fixes(r, plan)
    gp = Path(manual_path).with_name("gaps_manual.json") if manual_path else None
    feat = json.loads(gp.read_text()) if gp and gp.exists() else {}
    if feat.get("_featured"):
        fixes["featured_gap"] = feat["_featured"]
    if feat.get("_title_fix"):
        fixes["website_title_tag"] = feat["_title_fix"]
    try:
        lat, lng = float(r.get("lat") or 0), float(r.get("lng") or 0)
    except ValueError:
        lat = lng = 0.0
    grid_rows = []
    if lat and lng:
        pts = grid_points(lat, lng)
        grid_rows = live_grid(r, stands, pts, model) if (live and not simulate_grid) else globals()['simulate_grid'](r, stands, pts)
        write_grid(outdir, r, grid_rows)
    else:
        print("! No lat/lng for this restaurant; skipping rank grid (add lat,lng columns or --lat/--lng)")
    with open(outdir / "where_it_stands.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["keyword", "group", "maps_today", "page1", "ai_names_it", "ai_check_gemini", "top3", "biggest_gap", "source"] + GAP_AREAS)
        for s in stands:
            w.writerow([s["keyword"], s["group"], s["maps_today"], s["page1"], s["ai_names_it"], s.get("ai_check_gemini", "not run"), " | ".join(s["top3"]), s["biggest_gap"], s["source"]] + [s["gaps"].get(a, "") for a in GAP_AREAS])
    (outdir / "fixes.json").write_text(json.dumps(fixes, indent=2))
    pdf = write_pdf(outdir, r, plan, stands, fixes, grid_rows, meta)
    print(f"✓ Where it stands: {len(stands)} keywords ({stands[0]['source']})")
    if grid_rows:
        print(f"✓ Rank grid: {len(grid_rows)} points ({grid_rows[0]['source']}) → {outdir / 'rank_grid.html'}")
    print(f"→ PDF:     {pdf}")
    return {"stands": stands, "fixes": fixes, "grid": grid_rows, "pdf": str(pdf)}
