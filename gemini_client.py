"""Robust Gemini layer: retries with exponential backoff on 429/5xx, model fallback, timeouts,
and errors that carry a friendly user-facing message.

Config (all optional, read from the environment; the key is never logged or written anywhere):
  GEMINI_API_KEY (or GOOGLE_API_KEY)   required for live mode
  GEMINI_MODEL            primary model (default gemini-3.8-flash)
  GEMINI_FALLBACK_MODELS  comma list tried in order after the primary (default gemini-3.7-flash,gemini-3.5-flash)
  GEMINI_MAX_RETRIES      retries per model on 429/5xx (default 3)
  GEMINI_TIMEOUT_S        per-request timeout, seconds (default 45)
  GEMINI_TOTAL_BUDGET_S   hard cap across all retries + models for one generate() (default 90)
"""
from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_FALLBACKS = "gemini-3.7-flash,gemini-3.5-flash"
RETRYABLE = {429, 500, 502, 503, 504}

USER_MESSAGES = {
    "no_key": "Live lookups are off on this server (no Gemini API key configured). A sample report is available meanwhile.",
    "quota": "Our AI provider's quota is used up right now. Please try again in a few minutes.",
    "overloaded": "Our AI provider is overloaded right now. Please try again in a minute.",
    "timeout": "The AI lookup took too long. Please try again.",
    "auth": "The server's Gemini API key was rejected. The site owner needs to update it. A sample report is available meanwhile.",
    "model": "The configured Gemini model is not available. The site owner needs to update GEMINI_MODEL.",
    "bad_response": "The AI returned something we could not read. Please try again.",
    "other": "Something went wrong talking to the AI provider. Please try again.",
}


class GeminiError(Exception):
    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind if kind in USER_MESSAGES else "other"
        self.detail = _redact(detail)[:300]
        super().__init__(f"{self.kind}: {self.detail}")

    @property
    def user_message(self) -> str:
        return USER_MESSAGES[self.kind]


@dataclass
class GenResult:
    text: str
    model: str
    grounded: bool
    attempts: int
    sources: list


def _redact(s: str) -> str:
    """Never let anything key-shaped reach logs or users."""
    s = str(s or "")
    for k in (os.environ.get("GEMINI_API_KEY"), os.environ.get("GOOGLE_API_KEY")):
        if k:
            s = s.replace(k, "[redacted]")
    return re.sub(r"(AIza[0-9A-Za-z_\-]{20,}|AQ\.[0-9A-Za-z_\-]{20,})", "[redacted]", s)


def api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


def models() -> list[str]:
    primary = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
    fb = os.environ.get("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACKS)
    out = []
    for m in [primary] + [x.strip() for x in fb.split(",")]:
        if m and m not in out:
            out.append(m)
    return out


def _int(name, default):
    try:
        return int(float(os.environ.get(name, default)))
    except ValueError:
        return default


def classify(e: Exception) -> tuple[str, int | None]:
    """Map an SDK/network exception to (kind, http_code)."""
    code = getattr(e, "code", None)
    if not isinstance(code, int):
        m = re.search(r"\b(4\d\d|5\d\d)\b", str(e)[:200])
        code = int(m.group(1)) if m else None
    msg = str(e).lower()
    name = type(e).__name__.lower()
    if "timeout" in name or "timed out" in msg or "timeout" in msg:
        return "timeout", code
    if code == 429 or "resource_exhausted" in msg or "quota" in msg:
        return "quota", 429
    if code in (500, 502, 503, 504) or "unavailable" in msg or "overloaded" in msg or "high demand" in msg:
        return "overloaded", code or 503
    if code in (401, 403) or "api key not valid" in msg or "permission_denied" in msg:
        return "auth", code
    if code == 404 or ("model" in msg and ("not found" in msg or "not supported" in msg or "retired" in msg)):
        return "model", code
    if isinstance(e, (ConnectionError, OSError)) or "connect" in name:
        return "overloaded", None  # transient network problem: retry
    return "other", code


def _retry_after(e: Exception) -> float | None:
    m = re.search(r"retry(?:Delay| in)[\"': ]*([0-9.]+)\s*s", str(e), re.I)
    return float(m.group(1)) if m else None


def backoff_delay(attempt: int, base: float = 1.5, cap: float = 20.0, hint: float | None = None) -> float:
    d = min(cap, base * (2 ** attempt)) * (0.75 + random.random() * 0.5)
    if hint:
        d = max(d, min(hint, cap))
    return d


def _make_client(timeout_s: int):
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key(), http_options=types.HttpOptions(timeout=timeout_s * 1000))


def _sources(resp) -> list:
    out = []
    try:
        gm = resp.candidates[0].grounding_metadata
        for ch in (gm.grounding_chunks or []):
            w = getattr(ch, "web", None)
            if w and getattr(w, "uri", None):
                out.append({"title": getattr(w, "title", "") or "", "uri": w.uri})
    except Exception:
        pass
    return out[:8]


def generate(prompt: str, *, grounded: bool = False, json_mode: bool = False, max_tokens: int = 8000,
             temperature: float = 0.3, client=None, sleep=time.sleep, log=print) -> GenResult:
    """Call Gemini with retries/backoff and model fallback. Raises GeminiError (never hangs past the budget)."""
    if client is None and not api_key():
        raise GeminiError("no_key")
    from google.genai import types

    timeout_s = _int("GEMINI_TIMEOUT_S", 45)
    budget = _int("GEMINI_TOTAL_BUDGET_S", 90)
    retries = _int("GEMINI_MAX_RETRIES", 3)
    deadline = time.monotonic() + budget
    client = client or _make_client(timeout_s)
    last: GeminiError | None = None
    attempts = 0

    for model in models():
        use_search = grounded
        attempt = 0
        while True:
            if time.monotonic() > deadline:
                raise last or GeminiError("timeout", "total budget exceeded")
            cfg = dict(temperature=temperature, max_output_tokens=max_tokens)
            if use_search:
                cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
            elif json_mode:
                cfg["response_mime_type"] = "application/json"
            attempts += 1
            try:
                resp = client.models.generate_content(model=model, contents=prompt,
                                                      config=types.GenerateContentConfig(**cfg))
                text = (getattr(resp, "text", None) or "").strip()
                if not text:
                    raise GeminiError("bad_response", "empty response")
                log(f"  · Gemini {model} ok (attempt {attempt + 1}, search={use_search})")
                return GenResult(text=text, model=model, grounded=use_search, attempts=attempts,
                                 sources=_sources(resp) if use_search else [])
            except GeminiError as ge:
                last = ge
                if attempt >= retries:
                    break
                attempt += 1
                continue
            except Exception as e:  # SDK / network errors
                kind, code = classify(e)
                last = GeminiError(kind, f"{model}: {type(e).__name__}: {e}")
                log(f"  ! Gemini {model} attempt {attempt + 1} failed: {kind} ({code})")
                if kind in ("auth",):
                    raise last
                if kind == "model":
                    break  # try next model
                if kind == "other" and use_search:
                    use_search = False  # grounding not supported here: retry same model without search
                    continue
                if kind in ("quota", "overloaded", "timeout") and attempt < retries:
                    d = backoff_delay(attempt, hint=_retry_after(e))
                    if time.monotonic() + d > deadline:
                        raise last
                    sleep(d)
                    attempt += 1
                    continue
                break  # exhausted retries on this model: fall back to the next one
    raise last or GeminiError("other", "no models configured")


def extract_json(text: str):
    import json
    text = re.sub(r"```(?:json)?", "", text or "")
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
    if not m:
        raise GeminiError("bad_response", "no JSON in response")
    try:
        return json.loads(m.group(1))
    except ValueError as e:
        raise GeminiError("bad_response", f"invalid JSON: {e}")
