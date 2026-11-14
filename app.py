"""Page One Builder web app (FastAPI).

Type a restaurant name or link -> up to 5 real matches (Gemini + Google Search) in a dropdown -> pick one ->
background build (keywords, pages, schema, where-it-stands, competitors, PDF) -> shareable /r/<id>.

Run locally:  pip install -r requirements.txt && python app.py   (http://localhost:8000)
No GEMINI_API_KEY = live lookups are off; an offline sample report is offered as a fallback.
The key is read only from the environment or a gitignored .env; it is never logged or written.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

import candidates as candmod
import competitors as cmpmod
import core
import gemini_client
import page_one
import providers

VERSION = "1.0.0"
DATA_DIR = Path(os.environ.get("DATA_DIR") or (ROOT / "var")).resolve()
CACHE_TTL_S = int(float(os.environ.get("CACHE_TTL_HOURS", "168")) * 3600)
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "12"))
MAX_BUILDS = int(os.environ.get("MAX_CONCURRENT_BUILDS", "2"))
TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") == "1"
COMPETITORS_ON = os.environ.get("COMPETITORS", "1") != "0"
STAGES = ["queued", "lookup", "keywords", "writing", "checks", "competitors", "done"]

cache = core.DiskCache(DATA_DIR / "cache", CACHE_TTL_S)
store = core.ReportStore(DATA_DIR / "reports")
limiter = core.RateLimiter(RATE_LIMIT, 60)
pool = ThreadPoolExecutor(max_workers=max(1, MAX_BUILDS), thread_name_prefix="build")
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
LOOKUP_FIELDS = core.FIELDS

app = FastAPI(title="Page One Builder", version=VERSION, docs_url=None, redoc_url=None)


def log(*a):
    print(time.strftime("%H:%M:%S"), *(gemini_client._redact(str(x)) for x in a), flush=True)


def page() -> str:
    return (ROOT / "index.html").read_text()


def client_ip(req: Request) -> str:
    if TRUST_PROXY:
        xff = req.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return req.client.host if req.client else "unknown"


def err(status: int, kind: str, message: str, **extra):
    return JSONResponse({"status": "error", "kind": kind, "message": message, "demo_available": True, **extra}, status_code=status)


def limited(req: Request):
    ok, retry = limiter.allow(client_ip(req))
    if ok:
        return None
    return err(429, "rate_limited", f"Too many requests. Please wait {retry} seconds and try again.", retry_after=retry)


# --------------------------------------------------------------------------- demo (Tikka N Kabab)
def tikka_row() -> dict:
    with open(ROOT / "data" / "restaurants.csv", newline="", encoding="utf-8-sig") as fh:
        row = next(csv.DictReader(fh))
    return core.validate_info(row)


DEMO_LOCK = threading.Lock()


def ensure_demo_report() -> str:
    """Build the offline Tikka demo once per process start (fast, no network)."""
    rid = core.DEMO_ID
    with DEMO_LOCK:
        m = store.meta(rid)
        if m and m.get("status") == "ok" and m.get("version") == VERSION and m.get("pid") == os.getpid():
            return rid
        d = store.dir(rid)
        d.mkdir(parents=True, exist_ok=True)
        page_one.main(["--offline", "--outdir", str(d)])
        _stamp_report(d, mode="demo")
        info = tikka_row()
        store.save_meta(rid, {"id": rid, "status": "ok", "mode": "demo", "info": info, "query": "Tikka N Kabab",
                              "created": now_iso(), "version": VERSION, "pid": os.getpid(), "summary": summary(d)})
        return rid


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- lookup
DETAILS_PROMPT = """Use Google Search. Get the public details of THIS exact restaurant:
{name}, {address}
Return ONLY a JSON object with keys: {fields}, found.
- found: true only if you found this exact place (same name and street address).
- features: dine-in/takeout/delivery/catering etc. ONLY if the official site or Google listing says so. Dietary claims (halal, vegan) ONLY if stated there.
- menu_items: 8-14 real dishes separated by ';', with prices ONLY when shown (e.g. "Chicken Biryani $12.99").
- rating, review_count, category: the Google Business Profile star rating, review count and primary category, only if found.
- price_range: only if shown on the listing (e.g. "$$"). lat, lng: only if found.
Use an empty string for anything you cannot verify. Never invent or estimate details."""


def lookup_details(cand: dict) -> dict:
    """Full facts for the exact place the user picked. Name/address stay the picked candidate's."""
    res = gemini_client.generate(DETAILS_PROMPT.format(name=cand["name"], address=cand["address"], fields=", ".join(LOOKUP_FIELDS)),
                                 grounded=True, max_tokens=4000, temperature=0.1)
    if not res.grounded:
        raise gemini_client.GeminiError("other", "search grounding unavailable for details")
    data = gemini_client.extract_json(res.text)
    if not isinstance(data, dict):
        data = {}
    same = str(data.get("found")).lower() != "false"
    base = {k: "" for k in LOOKUP_FIELDS}
    if same:
        base.update({k: data.get(k, "") for k in LOOKUP_FIELDS})
    base.update(name=cand["name"], address=cand["address"])
    for k in ("website", "category", "cuisine"):
        if not base.get(k) and cand.get(k):
            base[k] = cand[k]
    for k in ("rating", "review_count"):
        if cand.get(k) is not None and not base.get(k):
            base[k] = str(cand[k])
    return {"info": core.validate_info(base), "sources": ([{"title": "Listing", "uri": cand["source_url"]}] + res.sources)[:8]}


cand_limiter = core.RateLimiter(int(os.environ.get("CANDIDATE_RATE_LIMIT_PER_MIN", "30")), 60)


@app.get("/api/candidates")
def api_candidates(request: Request, q: str = ""):
    """Up to 5 real restaurant matches (Gemini + Google Search). Cached by normalized query."""
    ok, retry = cand_limiter.allow(client_ip(request))
    if not ok:
        return err(429, "rate_limited", f"Too many searches. Please wait {retry} seconds.", retry_after=retry)
    try:
        q = core.validate_query(q)
    except core.ValidationError as e:
        return err(400, "invalid", str(e))
    if len(q) < 3:
        return err(400, "invalid", "Type at least 3 characters.")
    nq = core.normalize_query(q)
    hit = cache.get("candidates", nq)
    if hit is None:
        if not gemini_client.api_key():
            return err(503, "no_key", gemini_client.USER_MESSAGES["no_key"])
        t0 = time.monotonic()
        try:
            hit = candmod.find(q)
        except gemini_client.GeminiError as e:
            log("candidates failed:", e.kind, e.detail)
            return err(503 if e.kind in ("quota", "overloaded", "timeout", "no_key") else 502, e.kind, e.user_message)
        log(f"candidates '{nq}' -> {len(hit['candidates'])} in {time.monotonic() - t0:.1f}s")
        if hit["candidates"]:
            cache.set("candidates", nq, hit)
        for c in hit["candidates"]:
            cache.set("candidate", c["candidate_id"], c)
    if not hit["candidates"]:
        return {"status": "none", "candidates": [],
                "message": "We couldn't find a real restaurant matching that. Check the spelling, add the city, or paste its website."}
    return {"status": "ok", "candidates": hit["candidates"]}


# --------------------------------------------------------------------------- build (background jobs)
class BuildIn(BaseModel):
    candidate_id: str = ""
    lookup_id: str = ""  # "demo" = offline sample report


def set_job(jid: str, **kw):
    with JOBS_LOCK:
        JOBS[jid].update(kw, updated=time.time())


def _stamp_report(d: Path, mode: str, info: dict | None = None, sources: list | None = None):
    """Honesty banner at the top of every report."""
    rp = d / "report.html"
    if not rp.exists():
        return
    if mode == "demo":
        msg = ("<b>Sample report (offline example): Tikka N Kabab.</b> Restaurant facts, by-hand rank checks and competitor values come from the team's "
               "hand checks (labeled per section). The keyword plan is cached Gemini output. Where-it-stands cells left blank were not checked yet. "
               "The rank grid is SIMULATED, not live rankings.")
    else:
        src = "".join(f"<li><a href='{page_one.esc(s['uri'])}' target='_blank' rel='noopener'>{page_one.esc(s.get('title') or s['uri'])}</a></li>"
                      for s in (sources or [])[:6])
        msg = ("<b>How to read this report.</b> Restaurant facts (address, hours, menu, rating, reviews, features) came from an automated "
               "Gemini + Google Search lookup for the place the requester picked from the search results; they are <b>not independently verified</b>. "
               "Menu prices not shown online appear as [price]. Where it stands = <b>to be checked by hand</b> (no rank data was invented). "
               + ("The rank grid uses real provider data. " if providers.has_real_ranks() else "The rank grid is <b>SIMULATED</b>, not live rankings. ")
               + "Competitor values are what search returned; 'not found' means not verified."
               + (f"<details><summary>Lookup sources</summary><ul>{src}</ul></details>" if src else ""))
    banner = (f"<div style='margin:12px auto;max-width:1100px;padding:12px 16px;border:1px solid #f59e0b;background:#fffbeb;"
              f"color:#78350f;border-radius:10px;font:14px/1.5 system-ui,sans-serif'>{msg}</div>")
    txt = rp.read_text()
    rp.write_text(re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + banner, txt, count=1))


def summary(d: Path) -> dict:
    try:
        f = json.loads((d / "fixes.json").read_text())
    except (OSError, ValueError):
        return {}
    c = f.get("compare") or {}
    return {"target": c.get("target"), "competitors": [{k: x.get(k) for k in ("name", "rating", "review_count", "category", "distance_mi", "keywords_ranked")}
                                                        for x in c.get("competitors", [])],
            "findings": (c.get("analysis") or {}).get("findings", []), "close_the_gap": f.get("close_the_gap", []),
            "competitor_mode": c.get("mode"), "warning": c.get("warning")}


def competitor_fetcher(jid: str):
    def fetch(r: dict, kws: list[str]):
        set_job(jid, stage="competitors")
        if not COMPETITORS_ON:
            return None
        key = core.cache_key((r.get("name") or "").lower(), (r.get("address") or "").lower(), "|".join(kws))
        hit = cache.get("competitors", key)
        if hit is not None:
            return hit
        t0 = time.monotonic()
        try:
            res = cmpmod.find_live(r, kws)
        except gemini_client.GeminiError as e:
            log("competitors failed:", e.kind, e.detail)
            return {"target": {}, "competitors": [], "mode": "failed", "engine": "",
                    "warning": "Competitor lookup failed this time (" + e.user_message + ") Rebuild later to retry."}
        log(f"competitors for '{r.get('name')}': {len(res['competitors'])} in {time.monotonic() - t0:.1f}s")
        cache.set("competitors", key, res)
        return res
    return fetch


def run_build(jid: str, rid: str, cand: dict):
    t0 = time.monotonic()
    d = store.dir(rid)
    try:
        set_job(jid, state="running", stage="lookup")
        det = cache.get("details", cand["candidate_id"])
        if det is None:
            det = lookup_details(cand)
            cache.set("details", cand["candidate_id"], det)
        info = det["info"]
        set_job(jid, stage="keywords")
        d.mkdir(parents=True, exist_ok=True)
        f = d / "restaurant.csv"
        with open(f, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=core.FIELDS)
            w.writeheader()
            w.writerow(info)
        page_one.main(["--csv", str(f), "--row", "0", "--simulate-grid", "--no-ai-check", "--require-live",
                       "--outdir", str(d), "--manual", str(d / "rankings_manual.csv")],
                      progress=lambda s: set_job(jid, stage=s), competitors=competitor_fetcher(jid))
        _stamp_report(d, mode="live", info=info, sources=det.get("sources"))
        store.save_meta(rid, {"id": rid, "status": "ok", "mode": "live", "info": info, "candidate": cand,
                              "created": now_iso(), "version": VERSION, "seconds": round(time.monotonic() - t0, 1), "summary": summary(d)})
        cache.set("report", cand["candidate_id"], rid)
        set_job(jid, state="ok", stage="done", report_id=rid)
        log(f"build {rid} ok in {time.monotonic() - t0:.1f}s")
    except gemini_client.GeminiError as e:
        log("build failed:", e.kind, e.detail)
        store.save_meta(rid, {"id": rid, "status": "error", "kind": e.kind, "created": now_iso()})
        set_job(jid, state="error", kind=e.kind, message=e.user_message)
    except Exception:  # never leave the page hanging
        traceback.print_exc()
        store.save_meta(rid, {"id": rid, "status": "error", "kind": "other", "created": now_iso()})
        set_job(jid, state="error", kind="other", message="Something went wrong building the report. Please try again.")


@app.post("/api/build")
def api_build(body: BuildIn, request: Request):
    if (r := limited(request)):
        return r
    if body.lookup_id == "demo":
        rid = ensure_demo_report()
        return {"status": "ok", "report_id": rid, "url": f"/r/{rid}"}
    if not re.fullmatch(r"[0-9a-f]{32}", body.candidate_id or ""):
        return err(400, "invalid", "Pick your restaurant from the list first.")
    cand = cache.get("candidate", body.candidate_id)
    if not cand:
        return err(410, "expired", "That search expired. Please search again.")
    if not gemini_client.api_key():
        return err(503, "no_key", gemini_client.USER_MESSAGES["no_key"])
    prev = cache.get("report", body.candidate_id)
    if prev and (store.meta(prev) or {}).get("status") == "ok":
        return {"status": "ok", "report_id": prev, "url": f"/r/{prev}", "cached": True}
    with JOBS_LOCK:
        running = sum(1 for j in JOBS.values() if j["state"] in ("queued", "running"))
        if running >= MAX_BUILDS * 3:
            return err(503, "busy", "The server is busy building other reports. Please try again in a minute.")
        jid = core.ReportStore.new_id()
        rid = core.ReportStore.new_id()
        JOBS[jid] = {"id": jid, "state": "queued", "stage": "queued", "report_id": None, "created": time.time()}
        if len(JOBS) > 500:  # drop old finished jobs
            for k in sorted(JOBS, key=lambda k: JOBS[k]["created"])[:100]:
                if JOBS[k]["state"] in ("ok", "error"):
                    JOBS.pop(k, None)
    pool.submit(run_build, jid, rid, cand)
    return {"status": "queued", "job_id": jid, "stages": STAGES}


@app.get("/api/jobs/{jid}")
def api_job(jid: str):
    j = JOBS.get(jid)
    if not j:
        return err(404, "not_found", "That build was not found (the server may have restarted). Please try again.")
    out = {k: j.get(k) for k in ("state", "stage", "report_id", "kind", "message")}
    out["stages"] = STAGES
    if j.get("report_id"):
        out["url"] = f"/r/{j['report_id']}"
    return out


# --------------------------------------------------------------------------- reports, downloads, pages
def _meta_or_404(rid: str):
    if rid == core.DEMO_ID:
        ensure_demo_report()
    m = store.meta(rid)
    if not m or m.get("status") != "ok":
        return None
    return m


@app.get("/api/reports/{rid}")
def api_report(rid: str):
    m = _meta_or_404(rid)
    if not m:
        return err(404, "not_found", "Report not found. It may have expired; build it again.")
    return {"id": rid, "mode": m["mode"], "info": m["info"], "created": m["created"], "summary": m.get("summary", {}),
            "url": f"/r/{rid}", "report_url": f"/api/reports/{rid}/report.html",
            "downloads": {"pdf": f"/api/reports/{rid}/download?f=pdf", "html": f"/api/reports/{rid}/download?f=html"}}


@app.get("/api/reports/{rid}/report.html")
def api_report_html(rid: str):
    if not _meta_or_404(rid):
        return HTMLResponse("<p>Report not found.</p>", status_code=404)
    hit = store.file(rid, "html")
    return FileResponse(hit[0], media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@app.get("/api/reports/{rid}/download")
def api_download(rid: str, f: str = "pdf"):
    if f not in ("pdf", "html"):
        return err(400, "invalid", "Download type must be pdf or html.")
    if not _meta_or_404(rid):
        return err(404, "not_found", "Report not found.")
    hit = store.file(rid, f)
    if not hit:
        return err(404, "not_found", "That file is not available for this report.")
    path, name, media = hit
    return FileResponse(path, media_type=media, filename=name)


@app.get("/api/download")
def api_download_compat(f: str = "pdf", id: str = core.DEMO_ID):
    return api_download(id, f)


@app.get("/healthz")
def healthz():
    return {"ok": True, "version": VERSION, "live_lookups": bool(gemini_client.api_key()),
            "models": gemini_client.models(), "rank_provider": providers.get_rank_provider().name,
            "competitors": COMPETITORS_ON}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(page())


@app.get("/r/{rid}", response_class=HTMLResponse)
def shared(rid: str):
    ok = _meta_or_404(rid) is not None
    return HTMLResponse(page(), status_code=200 if ok else 404)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return err(404, "not_found", "Not found.")
    return HTMLResponse(page(), status_code=404)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    print(f"Page One Builder {VERSION} on http://localhost:{port}  (live lookups: {bool(gemini_client.api_key())}; "
          f"models: {', '.join(gemini_client.models())})", flush=True)
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=port, log_level=os.environ.get("LOG_LEVEL", "info"))
