# Page One Builder: Team Plan (due 4:15 PM CT)

## What it does
Input a restaurant. Output exactly what to change so it shows up on Google Maps
and in AI answers (ChatGPT, Gemini) for the 10 searches locals actually use.

## What's in the repo
- `page_one_builder.ipynb`: Colab notebook (main demo). Runtime, then Run all.
- `page_one.py`: same pipeline as a command-line script.
- `data/`: sample restaurant + keyword data.
- `sample_output/`: saved example report (offline fallback).
- `tools/`: schema validator, keyword-density check, rank tracker.
- `.env.example`: put GEMINI_API_KEY here locally (never commit keys).

## Pipeline
1. Gemini generates 20 local keywords (dish / cuisine+area / need) with intent.
2. Rank and keep the top 10.
3. For each keyword: Google Business Profile changes, page copy, 3 AEO FAQs.
4. Build Restaurant + FAQPage JSON-LD schema and validate it.
5. Honesty check: keyword density + word count (no stuffing).
6. Export: report.html, landing.html (schema in head), JSON/CSV, rank tracker CSV.
7. If Gemini fails, fall back to the saved sample so the demo never breaks.

## Remaining (in order)
- [ ] Pick real restaurant; replace sample name/address/phone/menu.
- [ ] Run notebook live in Colab with GEMINI_API_KEY secret; confirm no fallback.
- [ ] Screenshot report + landing page for submission.
- [ ] Stretch goal (text TBD from handout): `--all` batch mode over restaurants.csv is ready.
- [ ] Submit repo link + Colab link before 4:15 PM.

## Run
Colab: https://colab.research.google.com/github/Skr00n/utdhackathonproject/blob/main/page_one_builder.ipynb
Local: pip install -r requirements.txt; cp .env.example .env; python page_one.py --restaurant "Name"
