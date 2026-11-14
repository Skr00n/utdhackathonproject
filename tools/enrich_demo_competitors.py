"""One-off: fill ONLY the empty fields of the Tikka demo competitors with a grounded Gemini lookup.
Hand-check values are never overwritten; every filled cell is marked with its source.
Writes data/competitors_tikka_enriched.json (committed so the demo stays instant and offline).
Run: GEMINI_API_KEY in env, then  python tools/enrich_demo_competitors.py"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import competitors as c  # noqa: E402
import page_one  # noqa: E402

t0 = time.monotonic()
seed = c.tikka_seed()
out = c.enrich_seed(seed, page_one.SAMPLE_RESTAURANT)
if out is seed:
    sys.exit("Grounding unavailable: nothing written (ungrounded answers are not used for facts).")
out["_note"] = ("Team hand-check seed (data/competitors_tikka.json). Cells listed in field_sources were filled by a "
                "Gemini + Google Search lookup and are unverified; everything else is from the team's hand check.")
p = ROOT / "data" / "competitors_tikka_enriched.json"
p.write_text(json.dumps(out, indent=2))
filled = sum(len(x.get("field_sources", {})) for x in out["competitors"])
print(f"wrote {p.relative_to(ROOT)}: {filled} empty cells filled in {time.monotonic() - t0:.1f}s ({out.get('engine')})")
