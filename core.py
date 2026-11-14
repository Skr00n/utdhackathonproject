"""Pure helpers for the web app: query normalization, demo detection, input validation,
on-disk cache, report store, per-IP rate limiting. No network, no keys."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

MAX_QUERY = 200
FIELDS = ["name", "address", "cuisine", "website", "menu_link", "phone", "hours", "features", "menu_items",
          "price_range", "lat", "lng", "rating", "review_count", "category"]
FIELD_LIMITS = {"menu_items": 2000, "features": 600}
DEFAULT_FIELD_LIMIT = 300
REPORT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,40}$")
DEMO_ID = "demo-tikka-n-kabab"


class ValidationError(ValueError):
    pass


# --------------------------------------------------------------------------- normalization
def clean_text(s: str, limit: int) -> str:
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = "".join(ch for ch in s if ch == "\n" or (ch.isprintable() and ch not in "\x0b\x0c"))
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s[:limit]


def normalize_query(q: str) -> str:
    """Stable cache key for what the user typed: case/space/punctuation-insensitive; URLs -> bare domain."""
    q = clean_text(q, MAX_QUERY * 2).lower().strip()
    if re.match(r"^(https?://)?(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?$", q):
        host = urlparse(q if "://" in q else "http://" + q).hostname or q
        return re.sub(r"^www\.", "", host)
    q = q.replace("&", " and ")
    q = re.sub(r"[^\w\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def validate_query(q) -> str:
    if not isinstance(q, str):
        raise ValidationError("Please type a restaurant name or website.")
    q = clean_text(q, MAX_QUERY + 1).replace("\n", " ")
    if len(q) < 2:
        raise ValidationError("Please type a restaurant name or website (at least 2 characters).")
    if len(q) > MAX_QUERY:
        raise ValidationError(f"That is too long. Keep it under {MAX_QUERY} characters.")
    if not re.search(r"[A-Za-z0-9]", q):
        raise ValidationError("Please type a restaurant name or website.")
    return q


def _valid_url(u: str) -> str:
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname or " " in u:
        return ""
    return u


def validate_info(info) -> dict:
    """Sanitize restaurant facts (from the lookup or edited by the user on the confirm card)."""
    if not isinstance(info, dict):
        raise ValidationError("Missing restaurant details.")
    out = {}
    for k in FIELDS:
        v = info.get(k, "")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v = str(v)
        if not isinstance(v, str):
            v = ""
        v = clean_text(v, FIELD_LIMITS.get(k, DEFAULT_FIELD_LIMIT)).replace("\n", " ")
        if v.lower() in ("unknown", "n/a", "none", "null", "not available"):
            v = ""
        out[k] = v
    out["website"] = _valid_url(out["website"])
    out["menu_link"] = _valid_url(out["menu_link"])
    for k, lo, hi in (("lat", -90, 90), ("lng", -180, 180)):
        try:
            f = float(out[k])
            out[k] = str(round(f, 6)) if lo <= f <= hi and f != 0 else ""
        except ValueError:
            out[k] = ""
    try:
        f = float(out["rating"]); out["rating"] = str(f) if 1 <= f <= 5 else ""
    except ValueError:
        out["rating"] = ""
    rc = re.sub(r"[,\s]", "", out["review_count"])
    out["review_count"] = rc if rc.isdigit() and int(rc) < 10_000_000 else ""
    if len(out["name"]) < 2:
        raise ValidationError("The restaurant name is missing.")
    return out


# --------------------------------------------------------------------------- cache
class DiskCache:
    """Tiny JSON-file cache: <dir>/<ns>/<key>.json with a TTL."""

    def __init__(self, root: Path, ttl_s: int):
        self.root = Path(root)
        self.ttl = ttl_s

    def _p(self, ns: str, key: str) -> Path:
        return self.root / ns / f"{cache_key(key)}.json"

    def get(self, ns: str, key: str):
        p = self._p(ns, key)
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            return None
        if self.ttl and time.time() - d.get("_t", 0) > self.ttl:
            return None
        return d.get("v")

    def set(self, ns: str, key: str, value):
        p = self._p(ns, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp" + secrets.token_hex(4))
        tmp.write_text(json.dumps({"_t": time.time(), "v": value}))
        os.replace(tmp, p)


# --------------------------------------------------------------------------- reports
class ReportStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def new_id() -> str:
        return secrets.token_urlsafe(9).replace("-", "a").replace("_", "b")

    def dir(self, rid: str) -> Path | None:
        if not isinstance(rid, str) or not REPORT_ID_RE.match(rid):
            return None
        d = (self.root / rid).resolve()
        if d.parent != self.root.resolve():
            return None
        return d

    def meta(self, rid: str) -> dict | None:
        d = self.dir(rid)
        if not d:
            return None
        try:
            return json.loads((d / "meta.json").read_text())
        except (OSError, ValueError):
            return None

    def save_meta(self, rid: str, meta: dict):
        d = self.dir(rid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps(meta, indent=2))

    def file(self, rid: str, kind: str) -> tuple[Path, str, str] | None:
        """kind pdf|html -> (path, download filename, media type)."""
        d = self.dir(rid)
        m = self.meta(rid)
        if not d or not m or m.get("status") != "ok":
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", (m.get("info", {}).get("name") or "restaurant").lower()).strip("-")[:50] or "restaurant"
        if kind == "pdf":
            if (d / "page_one_plan.pdf").exists():
                return d / "page_one_plan.pdf", f"{slug}-page-one-plan.pdf", "application/pdf"
            if (d / "page_one_plan.html").exists():
                return d / "page_one_plan.html", f"{slug}-page-one-plan.html", "text/html"
            return None
        if kind == "html" and (d / "report.html").exists():
            return d / "report.html", f"{slug}-page-one-report.html", "text/html"
        return None


# --------------------------------------------------------------------------- rate limit
class RateLimiter:
    """Sliding-window limiter per key (client IP). In-memory: per process."""

    def __init__(self, limit: int, window_s: int = 60):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        if self.limit <= 0:
            return True, 0
        now = now or time.monotonic()
        with self.lock:
            h = [t for t in self.hits.get(key, []) if now - t < self.window]
            if len(h) >= self.limit:
                self.hits[key] = h
                return False, int(self.window - (now - h[0])) + 1
            h.append(now)
            self.hits[key] = h
            if len(self.hits) > 10000:  # bound memory
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < self.window}
            return True, 0
