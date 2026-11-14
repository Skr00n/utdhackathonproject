#!/usr/bin/env python3
"""Page One Builder: 10 keywords on Google Maps (SEO + AEO).

Generates a 10-keyword local search plan for a restaurant: Google Business Profile
changes, website page copy, AEO FAQs, validated JSON-LD schema, a manual rank
tracker, an HTML report, and a landing page with schema in <head>.

Keys rule: the Gemini key is read ONLY from the environment (GEMINI_API_KEY),
a local .env file (gitignored), or Colab secrets. It is never written anywhere.

Usage:
  python page_one.py --restaurant "Sample Chettinad Kitchen"
  python page_one.py --csv data/restaurants.csv --row 0
  python page_one.py --offline          # cached sample output, no key / wifi needed
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLE_JSON = ROOT / "sample_output" / "sample_chettinad_kitchen.plan.json"

SAMPLE_RESTAURANT = {
    "name": "Sample Chettinad Kitchen",
    "address": "Richardson, TX 75080",
    "cuisine": "South Indian (Chettinad)",
    "website": "https://example.com/sample-chettinad-kitchen",
    "menu_link": "https://example.com/sample-chettinad-kitchen/menu",
    "phone": "",
    "hours": "Mo-Su 11:00-23:00",
    "features": "halal; lunch buffet; open till 11 PM; near UT Dallas",
    "menu_items": "chicken biryani; chettinad chicken; dosa",
}

INTENT_GROUPS = ["dish", "cuisine_near_me", "occasion_feature"]

# ----------------------------------------------------------------------------
# Input
# ----------------------------------------------------------------------------

def load_csv_row(path: str, row: int | None, name: str | None) -> dict:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    if not rows:
        sys.exit(f"No rows in {path}")
    if name:
        for r in rows:
            if r.get("name", "").lower() == name.lower():
                return normalize(r)
        sys.exit(f"Restaurant '{name}' not found in {path}")
    idx = row or 0
    if idx >= len(rows):
        sys.exit(f"Row {idx} out of range (CSV has {len(rows)} rows, 0-indexed)")
    return normalize(rows[idx])


def normalize(r: dict) -> dict:
    out = dict(SAMPLE_RESTAURANT) if r.get("name") == SAMPLE_RESTAURANT["name"] else {k: "" for k in SAMPLE_RESTAURANT}
    aliases = {"menu": "menu_link", "menu link": "menu_link", "telephone": "phone", "items": "menu_items"}
    for k, v in r.items():
        k = aliases.get(k, k.replace(" ", "_"))
        if v:
            out[k] = v
    return out


def split_list(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"[;|]", s or "") if x.strip()]


def city_of(address: str) -> str:
    m = re.search(r"([A-Za-z .]+),\s*([A-Z]{2})", address or "")
    return f"{m.group(1).strip().split(',')[-1].strip()}, {m.group(2)}" if m else address

# ----------------------------------------------------------------------------
# Gemini
# ----------------------------------------------------------------------------

PROMPT = """You are a local SEO + AEO (answer-engine optimization) strategist for restaurants.
Restaurant data (only use these facts; do NOT invent awards, reviews, prices or claims):
{restaurant}

Task:
1. Generate exactly 20 realistic local search keywords that people type into Google Maps
   or ask AI assistants (ChatGPT, Gemini, Siri) about this kind of restaurant in this city.
   Group each into intent_group: "dish", "cuisine_near_me", or "occasion_feature".
   Give est_intent: "high" | "medium" | "low" (likelihood the searcher visits/orders soon),
   intent_score 1-10, and a one-line why.
2. Pick the top 10 (mix of all three groups, highest intent and best fit for the restaurant's real menu/features).
   For each top keyword return:
   - gbp: categories (primary first), description_addition (1-2 natural sentences, <=750 chars total description),
     menu_items (items to add/rename on the GBP menu), photos (shot list), posts (2 Google Posts ideas),
     review_request (an honest way to ask real customers for reviews; never incentivize or script reviews)
   - website: title_tag (<=60 chars), meta_description (<=155 chars), h1, page_copy (300-500 words, natural,
     mention menu items, prices as "[price]" placeholders if unknown, hours, location; no keyword stuffing)
   - aeo_faqs: 3 Q&A pairs, short factual answers an AI assistant can quote.
3. faqs: the 5 best overall FAQs for a FAQPage schema block.
Honest methods only: no fake reviews, fake clicks, keyword stuffing or ranking manipulation.

Return JSON with this exact shape:
{{"keywords":[{{"keyword":"","intent_group":"","est_intent":"","intent_score":0,"why":""}}],
 "top10":[{{"rank":1,"keyword":"","intent_group":"","gbp":{{"categories":[],"description_addition":"","menu_items":[],"photos":[],"posts":[],"review_request":""}},
   "website":{{"title_tag":"","meta_description":"","h1":"","page_copy":""}},"aeo_faqs":[{{"q":"","a":""}}]}}],
 "gbp_description":"full suggested GBP description <=750 chars",
 "faqs":[{{"q":"","a":""}}]}}
"""


def get_api_key() -> str | None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        try:  # Colab secrets
            from google.colab import userdata  # type: ignore
            key = userdata.get("GEMINI_API_KEY")
            if key:
                os.environ["GEMINI_API_KEY"] = key
        except Exception:
            pass
    return key


def call_gemini(restaurant: dict, model: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=get_api_key())
    cfg = dict(response_mime_type="application/json", temperature=0.4, max_output_tokens=32000)
    try:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        config = types.GenerateContentConfig(**cfg)
    except Exception:
        cfg.pop("thinking_config", None)
        config = types.GenerateContentConfig(**cfg)
    resp = client.models.generate_content(
        model=model,
        contents=PROMPT.format(restaurant=json.dumps(restaurant, indent=2)),
        config=config,
    )
    text = (resp.text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    return json.loads(text)

# ----------------------------------------------------------------------------
# Schema (built deterministically from real data, then validated)
# ----------------------------------------------------------------------------

def build_restaurant_schema(r: dict, plan: dict) -> dict:
    addr = r.get("address", "")
    m = re.match(r"^(?:(?P<street>.+?),\s*)?(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s*(?P<zip>\d{5})?", addr)
    postal = {"@type": "PostalAddress", "addressCountry": "US"}
    if m:
        if m.group("street"):
            postal["streetAddress"] = m.group("street")
        postal["addressLocality"] = m.group("city").strip()
        postal["addressRegion"] = m.group("state")
        if m.group("zip"):
            postal["postalCode"] = m.group("zip")
    else:
        postal["streetAddress"] = addr
    s = {
        "@context": "https://schema.org",
        "@type": "Restaurant",
        "name": r["name"],
        "servesCuisine": [c.strip() for c in re.split(r"[,(/)]", r.get("cuisine", "")) if c.strip()] or r.get("cuisine"),
        "address": postal,
        "telephone": r.get("phone") or "+1-000-000-0000 (replace with real number)",
        "openingHours": [h.strip() for h in r.get("hours", "").split(";") if h.strip()] or ["Mo-Su 11:00-23:00"],
        "menu": r.get("menu_link") or r.get("website"),
        "acceptsReservations": "True",
        "url": r.get("website"),
        "priceRange": "$$",
        "description": plan.get("gbp_description", "")[:750],
        "hasMenu": {
            "@type": "Menu",
            "hasMenuSection": {
                "@type": "MenuSection",
                "name": "Signature dishes",
                "hasMenuItem": [{"@type": "MenuItem", "name": i.title()} for i in split_list(r.get("menu_items", ""))],
            },
        },
    }
    feats = split_list(r.get("features", ""))
    if feats:
        s["amenityFeature"] = [{"@type": "LocationFeatureSpecification", "name": f, "value": True} for f in feats]
    return s


def build_faq_schema(faqs: list[dict]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
            for f in faqs[:5]
        ],
    }


def validate_schema(restaurant_ld: dict, faq_ld: dict) -> list[str]:
    """Round-trip both blocks through the JSON parser and check required fields."""
    problems = []
    for label, block in (("Restaurant", restaurant_ld), ("FAQPage", faq_ld)):
        try:
            json.loads(json.dumps(block))
        except Exception as e:  # pragma: no cover
            problems.append(f"{label}: invalid JSON ({e})")
        if block.get("@context") != "https://schema.org":
            problems.append(f"{label}: missing @context")
    for k in ["name", "servesCuisine", "address", "telephone", "openingHours", "menu", "acceptsReservations"]:
        if not restaurant_ld.get(k):
            problems.append(f"Restaurant: missing {k}")
    if "(replace" in str(restaurant_ld.get("telephone")):
        problems.append("Restaurant: telephone is a placeholder - add the real number before publishing (warning)")
    if len(faq_ld.get("mainEntity", [])) != 5:
        problems.append(f"FAQPage: expected 5 questions, got {len(faq_ld.get('mainEntity', []))}")
    return problems

# ----------------------------------------------------------------------------
# Honesty lint
# ----------------------------------------------------------------------------

BANNED = ["fake review", "buy review", "paid review", "click farm", "best in the world", "#1 rated", "guaranteed ranking"]


def lint_plan(plan: dict) -> list[dict]:
    out = []
    for t in plan.get("top10", []):
        copy = t.get("website", {}).get("page_copy", "")
        words = re.findall(r"\w+", copy.lower())
        n = len(words) or 1
        kw = t["keyword"].lower()
        hits = copy.lower().count(kw)
        density = round(100 * hits * len(kw.split()) / n, 1)
        flags = []
        if not 300 <= n <= 500:
            flags.append(f"page copy {n} words (target 300-500)")
        if density > 3:
            flags.append(f"keyword density {density}% (>3% = stuffing risk)")
        for b in BANNED:
            if b in json.dumps(t).lower():
                flags.append(f"banned phrase: {b}")
        tt = t.get("website", {}).get("title_tag", "")
        md = t.get("website", {}).get("meta_description", "")
        if len(tt) > 60:
            flags.append(f"title tag {len(tt)} chars (>60)")
        if len(md) > 155:
            flags.append(f"meta description {len(md)} chars (>155)")
        out.append({"keyword": t["keyword"], "words": n, "density_pct": density, "flags": flags})
    return out

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def write_csvs(outdir: Path, plan: dict, r: dict):
    with open(outdir / "keywords_20.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["keyword", "intent_group", "est_intent", "intent_score", "in_top10", "why"])
        top = {t["keyword"].lower() for t in plan["top10"]}
        for k in plan["keywords"]:
            w.writerow([k["keyword"], k["intent_group"], k["est_intent"], k["intent_score"], k["keyword"].lower() in top, k.get("why", "")])
    with open(outdir / "rank_tracker.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "rank", "keyword", "intent_group", "search_location",
            "before_date", "before_maps_position(1-20 or 'not found')", "before_in_maps_top3(Y/N)",
            "before_ai_assistant_mentions(Y/N, which: ChatGPT/Gemini/Perplexity)", "before_ai_answer_notes",
            "changes_made", "after_date", "after_maps_position", "after_in_maps_top3(Y/N)", "after_ai_assistant_mentions(Y/N)", "notes",
        ])
        for t in plan["top10"]:
            w.writerow([t["rank"], t["keyword"], t["intent_group"], f"{city_of(r.get('address',''))} (incognito, location set)",
                        "", "", "", "", "", "", "", "", "", "", ""])


def esc(s) -> str:
    return html.escape(str(s or ""))


def paragraphs(text: str) -> str:
    return "".join(f"<p>{esc(p.strip())}</p>" for p in re.split(r"\n\s*\n|\n", text or "") if p.strip())


CSS = """
:root{--ink:#1d1d1f;--muted:#6e6e73;--line:#e5e5ea;--acc:#c2410c;--acc2:#0f766e;--bg:#fafaf7}
*{box-sizing:border-box}body{margin:0;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg)}
.wrap{max-width:1060px;margin:0 auto;padding:32px 20px 80px}
header.hero{background:linear-gradient(135deg,#7c2d12,#c2410c 60%,#ea580c);color:#fff;padding:40px 20px}
header.hero h1{margin:0 0 6px;font-size:34px}header.hero p{margin:0;opacity:.9}
.badges span{display:inline-block;background:rgba(255,255,255,.18);border-radius:999px;padding:4px 12px;margin:10px 6px 0 0;font-size:13px}
h2{margin:40px 0 12px;font-size:24px}h3{margin:0 0 8px}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px;margin:14px 0;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.stat{font-size:30px;font-weight:700;color:var(--acc)}.muted{color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#f4f4f0;font-weight:600}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
.g-dish{background:#fff1e6;color:#9a3412}.g-cuisine_near_me{background:#e6f4f1;color:#115e59}.g-occasion_feature{background:#eef0ff;color:#3730a3}
.i-high{color:#15803d;font-weight:700}.i-medium{color:#a16207}.i-low{color:#6b7280}
details{background:#fff;border:1px solid var(--line);border-radius:14px;margin:12px 0;padding:0 18px}
summary{cursor:pointer;padding:16px 0;font-weight:600;font-size:17px;list-style:none}summary::-webkit-details-marker{display:none}
summary .n{display:inline-block;width:30px;height:30px;line-height:30px;text-align:center;border-radius:50%;background:var(--acc);color:#fff;margin-right:10px;font-size:14px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding-bottom:18px}@media(max-width:800px){.cols{grid-template-columns:1fr}}
.box{background:#fafaf7;border:1px solid var(--line);border-radius:10px;padding:14px}.box h4{margin:0 0 8px;color:var(--acc2);font-size:14px;text-transform:uppercase;letter-spacing:.04em}
ul{margin:6px 0;padding-left:20px}pre{background:#0f172a;color:#e2e8f0;padding:16px;border-radius:10px;overflow:auto;font-size:12.5px;line-height:1.45}
.ok{color:#15803d;font-weight:700}.warn{color:#b45309}.faq dt{font-weight:600;margin-top:10px}.faq dd{margin:4px 0 0 0;color:#333}
.serp{font-family:arial,sans-serif;background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.serp .t{color:#1a0dab;font-size:18px}.serp .u{color:#006621;font-size:13px}.serp .d{color:#4d5156;font-size:14px}
.banner{background:#fef3c7;border:1px solid #fcd34d;border-radius:10px;padding:10px 14px;margin:14px 0;font-size:14px}
.honest{background:#ecfdf5;border:1px solid #a7f3d0;border-radius:14px;padding:18px}
"""


def render_report(r: dict, plan: dict, rest_ld: dict, faq_ld: dict, problems: list[str], lint: list[dict], meta: dict) -> str:
    groups = {g: [k for k in plan["keywords"] if k["intent_group"] == g] for g in INTENT_GROUPS}
    top = {t["keyword"].lower() for t in plan["top10"]}
    kw_rows = "".join(
        f"<tr><td>{'⭐ ' if k['keyword'].lower() in top else ''}{esc(k['keyword'])}</td>"
        f"<td><span class='pill g-{esc(k['intent_group'])}'>{esc(k['intent_group'].replace('_',' '))}</span></td>"
        f"<td class='i-{esc(k['est_intent'])}'>{esc(k['est_intent'])}</td><td>{esc(k['intent_score'])}/10</td><td class='muted'>{esc(k.get('why'))}</td></tr>"
        for k in sorted(plan["keywords"], key=lambda k: -int(k.get("intent_score", 0)))
    )
    lint_by = {l["keyword"]: l for l in lint}
    items = []
    for t in plan["top10"]:
        g, w = t["gbp"], t["website"]
        li = lint_by.get(t["keyword"], {})
        lint_html = ("<span class='ok'>✓ passes honesty lint</span>" if not li.get("flags") else
                     "<span class='warn'>⚠ " + esc("; ".join(li["flags"])) + "</span>")
        faqs = "".join(f"<dt>Q: {esc(f['q'])}</dt><dd>A: {esc(f['a'])}</dd>" for f in t.get("aeo_faqs", []))
        items.append(f"""
<details {'open' if t['rank']==1 else ''}><summary><span class='n'>{t['rank']}</span>{esc(t['keyword'])}
 <span class='pill g-{esc(t['intent_group'])}' style='margin-left:8px'>{esc(t['intent_group'].replace('_',' '))}</span></summary>
<div class='cols'>
 <div class='box'><h4>Google Business Profile</h4>
  <b>Categories:</b> {esc(', '.join(g.get('categories', [])))}<br>
  <b>Description addition:</b> {esc(g.get('description_addition'))}
  <br><b>Menu items:</b><ul>{''.join(f'<li>{esc(x)}</li>' for x in g.get('menu_items', []))}</ul>
  <b>Photos to add:</b><ul>{''.join(f'<li>{esc(x)}</li>' for x in g.get('photos', []))}</ul>
  <b>Google Posts:</b><ul>{''.join(f'<li>{esc(x)}</li>' for x in g.get('posts', []))}</ul>
  <b>Honest review request:</b> {esc(g.get('review_request'))}
 </div>
 <div class='box'><h4>Website page</h4>
  <div class='serp'><div class='u'>{esc(r.get('website'))}/{slugify(t['keyword'])}</div><div class='t'>{esc(w.get('title_tag'))}</div><div class='d'>{esc(w.get('meta_description'))}</div></div>
  <p><b>H1:</b> {esc(w.get('h1'))}</p>
  <p class='muted'>{li.get('words','?')} words · keyword density {li.get('density_pct','?')}% · {lint_html}</p>
  <details style='border:none;padding:0'><summary style='font-size:14px;padding:6px 0'>▸ Show full page copy</summary>{paragraphs(w.get('page_copy'))}</details>
  <h4 style='margin-top:12px'>AEO: answers AI assistants can quote</h4><dl class='faq'>{faqs}</dl>
 </div>
</div></details>""")
    prob_html = ("<p class='ok'>✓ Both JSON-LD blocks parse as valid JSON and include all required fields.</p>"
                 if not [p for p in problems if 'warning' not in p] else "")
    prob_html += "".join(f"<p class='warn'>⚠ {esc(p)}</p>" for p in problems)
    sample_banner = (f"<div class='banner'><b>SAMPLE OUTPUT (offline/demo mode).</b> {esc(meta.get('source_note',''))}</div>"
                     if meta.get("mode") == "offline" else "")
    faq_all = "".join(f"<dt>{esc(f['q'])}</dt><dd>{esc(f['a'])}</dd>" for f in plan["faqs"][:5])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Page One Plan: {esc(r['name'])}</title><style>{CSS}</style></head><body>
<header class="hero"><div class="wrap" style="padding:0 20px">
<h1>Page One Plan: {esc(r['name'])}</h1>
<p>10 keywords to win on Google Maps and in AI-assistant answers (SEO + AEO) · {esc(r.get('cuisine'))} · {esc(r.get('address'))}</p>
<div class="badges"><span>Generated {esc(meta.get('date'))}</span><span>Engine: {esc(meta.get('engine'))}</span><span>Honest methods only</span></div>
</div></header>
<div class="wrap">{sample_banner}
<div class="grid">
 <div class="card"><div class="stat">{len(plan['keywords'])}</div>keywords researched</div>
 <div class="card"><div class="stat">10</div>picked to target</div>
 <div class="card"><div class="stat">{sum(len(t.get('aeo_faqs',[])) for t in plan['top10'])+5}</div>AEO answers written</div>
 <div class="card"><div class="stat">2</div>JSON-LD blocks {'validated ✓' if not [p for p in problems if 'warning' not in p] else '(check)'}</div>
</div>
<div class="card"><h3>Restaurant</h3><b>{esc(r['name'])}</b> · {esc(r.get('cuisine'))}<br>{esc(r.get('address'))}<br>
Signature: {esc(', '.join(split_list(r.get('menu_items',''))))}<br>Features: {esc(', '.join(split_list(r.get('features',''))))}<br>
Hours: {esc(r.get('hours'))} · Menu: {esc(r.get('menu_link'))}</div>

<h2>1. Keyword engine: {len(plan['keywords'])} local searches, grouped by intent</h2>
<p class="muted">Dish searches: {len(groups['dish'])} · Cuisine + near me: {len(groups['cuisine_near_me'])} · Occasion / feature: {len(groups['occasion_feature'])}. ⭐ = picked for the top 10.</p>
<div class="card" style="padding:0;overflow:auto"><table><tr><th>Keyword</th><th>Intent group</th><th>Est. intent</th><th>Score</th><th>Why</th></tr>{kw_rows}</table></div>

<h2>2. The 10-keyword plan</h2>
<p class="muted">For each keyword: what to change on the Google Business Profile, the website page to publish, and the FAQ answers AI assistants can quote.</p>
<div class="card"><h3>Full suggested GBP description</h3><p>{esc(plan.get('gbp_description'))}</p><p class="muted">{len(plan.get('gbp_description',''))}/750 characters</p></div>
{''.join(items)}

<h2>3. Schema markup (JSON-LD)</h2>
<div class="card">{prob_html}<p class="muted">Paste each block into Google's Rich Results Test (search.google.com/test/rich-results) and the Schema.org validator (validator.schema.org) before publishing. Both are already embedded in the generated landing page's &lt;head&gt;.</p></div>
<h3>Restaurant</h3><pre>{esc(json.dumps(rest_ld, indent=2))}</pre>
<h3>FAQPage (5 FAQs)</h3><dl class="faq card">{faq_all}</dl><pre>{esc(json.dumps(faq_ld, indent=2))}</pre>

<h2>4. Manual rank check</h2>
<div class="card"><p>Fill in <code>rank_tracker.csv</code> <b>before</b> making changes, then re-check every 2 weeks.</p><ol>
<li>Open a private/incognito window, set the location to {esc(city_of(r.get('address','')))}, and search each keyword in Google Maps. Record the position (1-20 or "not found") and whether it is in the top 3 map pack.</li>
<li>Ask ChatGPT, Gemini and Perplexity the keyword as a question (e.g. "Where can I get {esc(plan['top10'][0]['keyword'])}?"). Record Y/N if {esc(r['name'])} is mentioned and what the answer said.</li>
<li>Log the change you made (GBP edit, page published, schema added) and the date.</li>
<li>Never ask anyone to click, search repeatedly, or leave reviews in exchange for anything. Measure, don't manipulate.</li></ol>
<table><tr><th>#</th><th>Keyword</th><th>Maps position (before)</th><th>Top 3?</th><th>AI mentions it?</th></tr>
{''.join(f"<tr><td>{t['rank']}</td><td>{esc(t['keyword'])}</td><td>__</td><td>☐</td><td>☐</td></tr>" for t in plan['top10'])}</table></div>

<h2>5. Honest methods</h2>
<div class="honest">This plan only uses what Google and AI assistants reward on their own: accurate business info, real menu items, real photos, helpful pages, structured data, and asking <b>real</b> customers for honest reviews. No fake reviews, no fake clicks, no keyword stuffing (every page is linted for density &gt;3%), no incentivized reviews, and no requests to anyone to change rankings.</div>

<h2>Files</h2><div class="card"><ul><li><code>landing.html</code> landing page with both schema blocks in &lt;head&gt;</li><li><code>plan.json</code> full plan</li><li><code>keywords_20.csv</code> all keywords</li><li><code>rank_tracker.csv</code> before/after tracker</li><li><code>schema_restaurant.jsonld</code>, <code>schema_faq.jsonld</code></li></ul></div>
</div></body></html>"""


def render_landing(r: dict, plan: dict, rest_ld: dict, faq_ld: dict) -> str:
    t = plan["top10"][0]
    w = t["website"]
    menu = "".join(f"<li><b>{esc(i.title())}</b> <span>[price]</span></li>" for i in split_list(r.get("menu_items", "")))
    feats = "".join(f"<span class='chip'>{esc(f)}</span>" for f in split_list(r.get("features", "")))
    faq = "".join(f"<details><summary>{esc(f['q'])}</summary><p>{esc(f['a'])}</p></details>" for f in plan["faqs"][:5])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(w['title_tag'])}</title>
<meta name="description" content="{esc(w['meta_description'])}">
<link rel="canonical" href="{esc(r.get('website'))}/{slugify(t['keyword'])}">
<script type="application/ld+json">
{json.dumps(rest_ld, indent=2)}
</script>
<script type="application/ld+json">
{json.dumps(faq_ld, indent=2)}
</script>
<style>
body{{margin:0;font:17px/1.6 Georgia,serif;color:#2b2118;background:#fffaf3}}
.hero{{background:linear-gradient(135deg,#7c2d12,#b45309);color:#fff;padding:70px 20px;text-align:center}}
.hero h1{{font-size:40px;margin:0 0 10px}}.hero p{{font-family:sans-serif;opacity:.9}}
.btn{{display:inline-block;background:#fff;color:#7c2d12;padding:12px 24px;border-radius:999px;text-decoration:none;font:600 16px sans-serif;margin:8px}}
main{{max-width:820px;margin:0 auto;padding:30px 20px 70px}}.chip{{display:inline-block;background:#fde68a;border-radius:999px;padding:4px 12px;margin:4px;font:14px sans-serif}}
.menu li{{list-style:none;border-bottom:1px dashed #d6c4a8;padding:8px 0;display:flex;justify-content:space-between}}.menu{{padding:0}}
details{{border-bottom:1px solid #eadcc8;padding:10px 0}}summary{{cursor:pointer;font-weight:bold}}
.info{{background:#fff;border:1px solid #eadcc8;border-radius:12px;padding:16px;font-family:sans-serif}}
</style></head><body>
<section class="hero"><h1>{esc(w['h1'])}</h1><p>{esc(r.get('cuisine'))} · {esc(r.get('address'))} · {esc(r.get('hours'))}</p>
<a class="btn" href="{esc(r.get('menu_link'))}">See the menu</a><a class="btn" href="tel:{esc(r.get('phone'))}">Call to order</a></section>
<main><div style="text-align:center">{feats}</div>
<article>{paragraphs(w['page_copy'])}</article>
<h2>Signature dishes</h2><ul class="menu">{menu}</ul>
<div class="info"><b>{esc(r['name'])}</b><br>{esc(r.get('address'))}<br>Hours: {esc(r.get('hours'))}<br>Menu: <a href="{esc(r.get('menu_link'))}">{esc(r.get('menu_link'))}</a></div>
<h2>Frequently asked questions</h2>{faq}
</main></body></html>"""


def check_plan_shape(plan: dict):
    assert isinstance(plan.get("keywords"), list) and len(plan["keywords"]) >= 10, "need >=10 keywords"
    assert isinstance(plan.get("top10"), list) and len(plan["top10"]) >= 1, "need top10"
    plan["top10"] = plan["top10"][:10]
    for i, t in enumerate(plan["top10"], 1):
        t["rank"] = i
        t.setdefault("gbp", {}); t.setdefault("website", {}); t.setdefault("aeo_faqs", [])
        t.setdefault("intent_group", "dish")
    for k in plan["keywords"]:
        k.setdefault("intent_group", "dish"); k.setdefault("est_intent", "medium"); k.setdefault("intent_score", 5)
    if len(plan.get("faqs", [])) < 5:
        extra = [f for t in plan["top10"] for f in t["aeo_faqs"]]
        plan["faqs"] = (plan.get("faqs", []) + extra)[:5]
    plan.setdefault("gbp_description", "")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Page One Builder: 10 keywords on Google Maps (SEO + AEO)")
    ap.add_argument("--restaurant", help="restaurant name (built-in sample, or looked up in --csv)")
    ap.add_argument("--csv", help="restaurants.csv (name,address,cuisine,website,menu_link[,phone,hours,features,menu_items])")
    ap.add_argument("--row", type=int, help="0-indexed CSV row")
    ap.add_argument("--offline", action="store_true", help="use cached sample output (no API key / wifi needed)")
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--all", action="store_true", help="batch: run every row of --csv and write out/index.html")
    a = ap.parse_args(argv)

    if a.all:
        if not a.csv:
            sys.exit("--all needs --csv")
        with open(a.csv, newline="", encoding="utf-8-sig") as f:
            n = sum(1 for _ in csv.DictReader(f))
        links = []
        for i in range(n):
            sub = ["--csv", a.csv, "--row", str(i), "--model", a.model, "--out", a.out] + (["--offline"] if a.offline else [])
            d = main(sub)
            links.append(f"<li><a href='{d.name}/report.html'>{esc(d.name)}</a> · <a href='{d.name}/landing.html'>landing</a></li>")
        idx = Path(a.out) / "index.html"
        idx.write_text(f"<!doctype html><meta charset=utf-8><title>Page One Builder</title><style>{CSS}</style><div class=wrap><h1>Page One plans</h1><ul>{''.join(links)}</ul></div>")
        print(f"→ Batch index: {idx}")
        return Path(a.out)

    if a.csv:
        r = load_csv_row(a.csv, a.row, a.restaurant)
    elif a.restaurant and a.restaurant.lower() != SAMPLE_RESTAURANT["name"].lower():
        r = {k: "" for k in SAMPLE_RESTAURANT}; r["name"] = a.restaurant
        print("! Only a name was given; pass --csv for address/cuisine/menu for better results.")
    else:
        r = dict(SAMPLE_RESTAURANT)

    meta = {"date": date.today().isoformat()}
    plan = None
    if not a.offline:
        if not get_api_key():
            print("! GEMINI_API_KEY not found (env, .env, or Colab secrets). Falling back to --offline sample output.")
        else:
            try:
                print(f"→ Asking {a.model} for 20 keywords + 10-keyword plan for {r['name']} ...")
                plan = call_gemini(r, a.model)
                check_plan_shape(plan)
                meta.update(mode="live", engine=a.model)
            except Exception as e:
                print(f"! Gemini call failed ({type(e).__name__}: {str(e)[:200]}). Falling back to offline sample output.")
                plan = None
    if plan is None:
        plan = json.loads(SAMPLE_JSON.read_text())
        meta.update(mode="offline", engine="cached sample", source_note=plan.get("_note", ""))
        if r["name"] != SAMPLE_RESTAURANT["name"]:
            print(f"! Offline mode only has cached output for {SAMPLE_RESTAURANT['name']}; using that restaurant.")
            r = dict(SAMPLE_RESTAURANT)
        check_plan_shape(plan)

    rest_ld = build_restaurant_schema(r, plan)
    faq_ld = build_faq_schema(plan["faqs"])
    problems = validate_schema(rest_ld, faq_ld)
    lint = lint_plan(plan)

    outdir = Path(a.out) / slugify(r["name"])
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "plan.json").write_text(json.dumps({"restaurant": r, "meta": meta, **plan, "lint": lint, "schema_problems": problems}, indent=2))
    (outdir / "schema_restaurant.jsonld").write_text(json.dumps(rest_ld, indent=2))
    (outdir / "schema_faq.jsonld").write_text(json.dumps(faq_ld, indent=2))
    write_csvs(outdir, plan, r)
    (outdir / "report.html").write_text(render_report(r, plan, rest_ld, faq_ld, problems, lint, meta))
    (outdir / "landing.html").write_text(render_landing(r, plan, rest_ld, faq_ld))

    # final validation: the schema embedded in the landing page must parse
    lp = (outdir / "landing.html").read_text()
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', lp, re.S)
    parsed = [json.loads(b) for b in blocks]
    print(f"✓ Mode: {meta['mode']} ({meta['engine']})")
    print(f"✓ {len(plan['keywords'])} keywords, top {len(plan['top10'])} planned")
    print(f"✓ JSON-LD in landing page: {len(parsed)} blocks parsed OK ({', '.join(p['@type'] for p in parsed)})")
    for p in problems:
        print(f"  ⚠ {p}")
    flagged = [l for l in lint if l["flags"]]
    print(f"✓ Honesty lint: {10 - len(flagged)}/{len(lint)} pages clean" + ("" if not flagged else f" ({len(flagged)} flagged, see report)"))
    print(f"→ Report:  {outdir / 'report.html'}")
    print(f"→ Landing: {outdir / 'landing.html'}")
    print(f"→ Data:    plan.json, keywords_20.csv, rank_tracker.csv, schema_*.jsonld in {outdir}")
    return outdir


if __name__ == "__main__":
    main()
