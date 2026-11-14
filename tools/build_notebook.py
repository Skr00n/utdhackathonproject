"""Rebuild page_one_builder.ipynb (no saved outputs). Embeds the code as a small zip so the
notebook works even without cloning the repo. Run: python tools/build_notebook.py"""
import base64, io, json, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["page_one.py", "handout.py", "data/restaurants.csv", "data/rankings_manual.csv", "data/gaps_manual.json", "data/focus_keywords.csv", "sample_output/tikka_n_kabab.plan.json", "sample_output/sample_chettinad_kitchen.plan.json"]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for f in FILES:
        z.write(ROOT / f, f)
BLOB = base64.b64encode(buf.getvalue()).decode()

def md(s): return {"cell_type": "markdown", "metadata": {}, "source": s.strip("\n")}
def code(s): return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip("\n")}

cells = [
md("""
# Page One Builder: 10 keywords on Google Maps (SEO + AEO)
Cells follow the handout in order: **Setup → Restaurant → Keywords → Where it stands → Gaps → Fixes → Rank grid map → Export PDF**.

**Keys rule:** add `GEMINI_API_KEY` in Colab's 🔑 Secrets panel. Never paste a key into a cell.
Without a key it runs in **offline mode**: a cached plan for Tikka N Kabab written from real facts; rankings come from your by-hand check (else 'to be checked by hand'); the rank grid ring values are **simulated** and labeled.
"""),
md("## 0. Setup"),
code("%pip install -q google-genai python-dotenv reportlab"),
code(f"""
import os, sys, io, base64, zipfile, pathlib
# Key: Colab secret GEMINI_API_KEY, else environment / .env. Never hard-code it.
try:
    from google.colab import userdata
    os.environ['GEMINI_API_KEY'] = userdata.get('GEMINI_API_KEY') or os.environ.get('GEMINI_API_KEY', '')
except Exception:
    pass
print('Gemini key found:', bool(os.environ.get('GEMINI_API_KEY')))
# Code: use the repo files if present, else unpack the embedded copy
if not pathlib.Path('page_one.py').exists():
    zipfile.ZipFile(io.BytesIO(base64.b64decode('{BLOB}'))).extractall('.')
sys.path.insert(0, os.getcwd())
import page_one, handout, importlib; importlib.reload(handout); importlib.reload(page_one)
print('Code ready')
"""),
md("## 1. Restaurant input (edit here)"),
code("""
RESTAURANT = {
    'name': 'Tikka N Kabab',
    'address': '7859 McCallum Blvd Ste 106, Dallas, TX 75252',
    'cuisine': 'Pakistani, Indian (kabab)',
    'menu_items': 'Chicken Samosa (2pc) $2.99; Veg Samosa (2pc) $3.99; Onion Bhaji (pakoda) $5.99; Dal Puri (4) $4.99; Chicken 65 $9.99',  # separate with ;
    'website': '[website]',          # unknown: leave placeholder until confirmed
    'menu_link': '[website]/menu',
    'phone': '(469) 857-3000',
    'hours': 'Mo-Su 11:00-21:30',
    'features': 'Google rating 4.2 (407 reviews); near UT Dallas; order online on Google; dine-in and pickup',
    'price_range': '$',
    'lat': '32.9895',    # approx; right-click the pin in Google Maps to copy exact lat, lng
    'lng': '-96.7735',
}
OFFLINE = False   # True = cached sample (no API call). Also auto-falls back if no key / Gemini fails.

import csv
with open('my_restaurant.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(RESTAURANT)); w.writeheader(); w.writerow(RESTAURANT)
args = ['--csv', 'my_restaurant.csv', '--row', '0'] + (['--offline'] if OFFLINE else [])
outdir = page_one.main(args)
"""),
md("## 2. Keywords: 10 keywords in 3 groups (dish, cuisine + area, need) with why"),
code("""
import json, pandas as pd
from IPython.display import HTML, display
plan = json.load(open(outdir/'plan.json'))
why = {k['keyword'].lower(): k for k in plan['keywords']}
pd.DataFrame([{'#': t['rank'], 'keyword': t['keyword'], 'group': handout.GROUP_LABEL.get(t['intent_group'], t['intent_group']),
               'intent': why.get(t['keyword'].lower(), {}).get('est_intent'), 'why it matters': why.get(t['keyword'].lower(), {}).get('why')}
              for t in plan['top10']])
"""),
md("""## 3. Where it stands today: Maps top 3 (local SEO) · Google page 1 (SEO) · AI assistants (AEO)
**Done by hand** (handout p.3, no paid SEO tools): open an incognito window and for each keyword
1. search google.com/maps: note our position (or `not in top 20`) and who is #1-#3 (separate with `;`)
2. search google.com: is our site on page 1? (`yes`/`no`)
3. ask Gemini or ChatGPT the keyword as a question: is Tikka N Kabab named? (`yes`/`no`)

Fill the table below and run it. It saves `data/rankings_manual.csv` and rebuilds where-it-stands, gaps, the rank grid center and the PDF.
`AI check (Gemini)` is an optional automatic extra when a key is set."""),
code("""
MANUAL = [  # keyword, maps_position, maps_top3, page1_yes_no, ai_names_it, notes
    # ('samosa near UTD', '7', 'Place A; Place B; Place C', 'no', 'no', 'winner has 2x photos'),
    # 'chicken 65 near me' AI check is already in data/rankings_manual.csv (ChatGPT did not name us)
]
AI_CHECK = True   # optional Gemini auto-check (only runs if a key is set)

import csv, json, pathlib
plan = json.load(open(outdir/'plan.json'))
mp = pathlib.Path('data/rankings_manual.csv'); mp.parent.mkdir(exist_ok=True)
rows = {t['keyword']: ['', '', '', '', ''] for t in plan['top10']}
if mp.exists():  # keep what the team already entered
    for r_ in csv.DictReader(open(mp)): rows[r_['keyword']] = [r_.get(k, '') for k in handout.MANUAL_FIELDS[1:]]
for m in MANUAL: rows[m[0]] = (list(m[1:]) + [''] * 5)[:5]
with open(mp, 'w', newline='') as f:
    w = csv.writer(f); w.writerow(handout.MANUAL_FIELDS)
    for k, v in rows.items(): w.writerow([k] + v[:5])
print(open(mp).read()[:1500])
if MANUAL:
    handout.run_handout(outdir, plan['restaurant'], plan, plan['meta'], os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash'),
                        live=(plan['meta'].get('mode') == 'live' and AI_CHECK), manual_path='data/rankings_manual.csv')
else:
    print('Add rows to MANUAL to update; rows already in data/rankings_manual.csv were used in the run above.')
"""),
code("""
ws = pd.read_csv(outdir/'where_it_stands.csv')
print('Source:', ws['source'].iloc[0])
ws[['keyword', 'maps_today', 'page1', 'ai_names_it', 'ai_check_gemini', 'top3', 'biggest_gap']].rename(columns={
    'maps_today': 'Maps today', 'page1': 'Page 1?', 'ai_names_it': 'AI names it?', 'ai_check_gemini': 'AI check (Gemini)', 'top3': 'Current top 3', 'biggest_gap': 'Biggest gap vs top 3'})
"""),
md("## 4. Gap analysis vs whoever wins each keyword"),
code("""
gap_cols = handout.GAP_AREAS
ws[['keyword'] + gap_cols]
"""),
md("## 5. Fixes ready to paste"),
code("""
fx = json.load(open(outdir/'fixes.json'))
print('GOOGLE BUSINESS DESCRIPTION\\n', fx['description'], '\\n')
print('4 WEEKLY GOOGLE POSTS'); [print(' -', p) for p in fx['weekly_posts']]
print('\\nMENU DESCRIPTIONS'); [print(' -', m['item'] + ':', m['description']) for m in fx['menu_descriptions']]
print('\\nONE PAGE PER KEYWORD GROUP'); [print(f" - [{g}] {p['title_tag']}  ->  {p['url']}") for g, p in fx['pages'].items()]
print('\\n5 FAQ ANSWERS'); [print(' Q:', f['q'], '\\n A:', f['a']) for f in fx['faqs']]
print('\\nREVIEW REQUEST TEXT\\n', fx['review_sms'], '\\n(', fx['review_rules'], ')')
print('\\nSCHEMA (Restaurant + FAQPage JSON-LD)'); print(open(outdir/'schema_restaurant.jsonld').read()); print(open(outdir/'schema_faq.jsonld').read())
"""),
code("""
# Full HTML report + landing page preview
display(HTML(open(outdir/'report.html').read()))
"""),
md("## 6. Stretch: rank grid map (1, 3, 5 miles in 8 directions)"),
code("""
p = outdir/'rank_grid.html'
if p.exists():
    import html as _h
    display(HTML(f'<iframe srcdoc="{_h.escape(p.read_text())}" width="620" height="760" style="border:0"></iframe>'))
else:
    print('No lat/lng set, so no rank grid. Add lat and lng in the Restaurant cell.')
"""),
md("## 7. Export: one PDF with keywords, gaps and the 30-day plan"),
code("""
import shutil, glob
pdf = next(iter(glob.glob(str(outdir/'page_one_plan.*'))), None)
print('PDF:', pdf)
shutil.make_archive('page_one_output', 'zip', outdir)
try:
    from google.colab import files
    files.download(pdf); files.download('page_one_output.zip')
except Exception:
    print('Saved', pdf, 'and page_one_output.zip')
"""),
]
nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
      "language_info": {"name": "python"}, "colab": {"provenance": []}}, "nbformat": 4, "nbformat_minor": 5}
for i, c in enumerate(nb["cells"]):
    c["id"] = f"cell{i}"
(ROOT / "page_one_builder.ipynb").write_text(json.dumps(nb, indent=1))
print("wrote page_one_builder.ipynb", len(BLOB), "b64 bytes embedded")
