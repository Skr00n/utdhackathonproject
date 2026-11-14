"""Page One Builder web app: paste a restaurant name or link, get the report on the same page.
Run: GEMINI_API_KEY in your environment or a gitignored .env, then `python3 app.py` and open http://localhost:8000
No key = falls back to the cached Tikka N Kabab demo (labeled)."""
import csv, json, os, re, sys, tempfile, pathlib, traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
except Exception: pass
import page_one
FIELDS = ["name","address","cuisine","website","menu_link","phone","hours","features","menu_items","price_range","lat","lng"]

def lookup(q):
    from google import genai
    from google.genai import types
    c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    p = ("Find this restaurant on Google (name or website): " + q + ". Return ONLY a JSON object with keys " + ", ".join(FIELDS) +
         ". features = Google rating and review count if known. menu_items = 8-14 real dishes with prices if shown, separated by ;. "
         "Use empty string for anything you cannot verify. Never invent details.")
    r = c.models.generate_content(model=os.environ.get("GEMINI_MODEL","gemini-2.5-flash"), contents=p,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
    m = re.search(r"\{.*\}", r.text or "", re.S)
    return json.loads(m.group(0)) if m else None

def build(q, confirmed):
    if not os.environ.get("GEMINI_API_KEY"):
        out = page_one.main(["--offline"]); LAST["dir"] = pathlib.Path(out)
        return "offline", None, (pathlib.Path(out)/"report.html").read_text()
    info = lookup(q)
    if not info: return "notfound", None, ""
    if not confirmed: return "confirm", info, ""
    d = tempfile.mkdtemp(); f = pathlib.Path(d)/"r.csv"
    with open(f,"w",newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS); w.writeheader(); w.writerow({k: str(info.get(k,"") or "") for k in FIELDS})
    out = page_one.main(["--csv", str(f), "--row", "0", "--simulate-grid"]); LAST["dir"] = pathlib.Path(out)
    return "ok", info, (pathlib.Path(out)/"report.html").read_text()

PAGE = (ROOT/"index.html").read_text()
LAST = {"dir": None}

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode(); self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/build":
            qs = parse_qs(u.query); q = (qs.get("q") or [""])[0].strip(); ok = (qs.get("confirm") or ["0"])[0] == "1"
            try:
                status, info, html = build(q, ok)
                self._send(200, json.dumps({"status": status, "info": info, "report": html}), "application/json")
            except Exception as e:
                traceback.print_exc(); self._send(500, json.dumps({"status": "error", "error": str(e)}), "application/json")
        elif u.path == "/api/download":
            kind = (parse_qs(u.query).get("f") or ["pdf"])[0]
            d = LAST["dir"]
            name = {"pdf": "page_one_plan.pdf", "html": "report.html"}.get(kind, "page_one_plan.pdf")
            fp = d / name if d else None
            if kind == "pdf" and fp and not fp.exists(): fp = d / "page_one_plan.html"; name = "page_one_plan.html"
            if not fp or not fp.exists(): return self._send(404, "Build a report first.", "text/plain")
            b = fp.read_bytes(); self.send_response(200)
            self.send_header("Content-Type", "application/pdf" if name.endswith(".pdf") else "text/html")
            self.send_header("Content-Disposition", 'attachment; filename="' + name + '"')
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            self._send(200, PAGE)
    def log_message(self, *a): pass

if __name__ == "__main__":
    print("Page One Builder running at http://localhost:8000  (key loaded: %s)" % bool(os.environ.get("GEMINI_API_KEY")))
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8000))), H).serve_forever()
