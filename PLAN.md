# Plan: Page One Builder for Tikka N Kabab

Gets a real local restaurant onto Google Maps' top 3, Google page 1 and AI-assistant answers for 10 searches people actually make. It writes the fixes; it does not post anything.

## Scoring (real rubric)
It works 30 · Real-world usefulness 25 · Use of AI 20 · Engineering quality 15 · Stretch + polish 10

## Checklist (handout order)
- [x] 1. 10 keywords in 3 groups (dish, cuisine + area, need) with why: `keywords_20.csv`
- [ ] 2. Where it stands BY HAND (incognito): Maps position + top 3, page 1 y/n, AI names it y/n → `data/rankings_manual.csv` (chicken 65 AI check done: not named by ChatGPT or Gemini; 9 keywords + Maps/page 1 left)
- [x] 3. Gap analysis vs winners (categories, menu, photos, reviews, review words, hours, website, posts): `where_it_stands.csv`, `data/gaps_manual.json`
- [x] 4. Fixes: GBP description, 4 weekly posts, menu descriptions, page per keyword group, 5 FAQs, schema, review text (no incentives): `fixes.json`, `landing.html`, `schema_*.jsonld`
- [x] 5. Stretch: rank grid 1/3/5 mi map: `rank_grid.html` / `rank_grid.csv` (rings simulated/estimated, labeled)
- [x] 6. One PDF: `sample_output/page_one_plan.pdf`
- [ ] Check schema in Google's Rich Results Test (paste `schema_faq.jsonld`, `schema_restaurant.jsonld`)
- [ ] Confirm unknowns: website, exact lat/lng, halal status, kabab menu items
- [ ] Fill TEAM.md (name, UTD email, internship/full-time)
- [ ] Re-run (`python page_one.py --offline` or notebook) after entering by-hand ranks, `python tools/build_notebook.py`, push, submit PDF

## Run
`pip install -r requirements.txt && python page_one.py` (live with GEMINI_API_KEY) or `python page_one.py --offline`. Colab: open `page_one_builder.ipynb`, add the secret, Run all.

## Honest methods only
No fake reviews, no incentives for reviews, no fake clicks, no keyword stuffing. Unknown facts stay as [placeholders].
