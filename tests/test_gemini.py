import pytest

import gemini_client as g


class FakeErr(Exception):
    def __init__(self, code, msg=""):
        self.code = code
        super().__init__(f"{code} {msg}")


class Resp:
    def __init__(self, text):
        self.text = text
        self.candidates = []


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return Resp(step)


def test_retry_429_then_success(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "m1")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "")
    sleeps = []
    c = FakeClient([FakeErr(429, "RESOURCE_EXHAUSTED"), FakeErr(429, "quota"), '{"ok": true}'])
    r = g.generate("p", client=c, sleep=sleeps.append, log=lambda *a: None)
    assert r.text == '{"ok": true}' and r.model == "m1" and r.attempts == 3
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] * 1.2  # exponential backoff


def test_503_exhausts_then_falls_back_to_next_model(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "m1")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "m2")
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "2")
    c = FakeClient([FakeErr(503, "UNAVAILABLE high demand")] * 3 + ["done"])
    r = g.generate("p", client=c, sleep=lambda s: None, log=lambda *a: None)
    assert r.model == "m2" and c.calls == ["m1", "m1", "m1", "m2"]


def test_retired_model_skips_to_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "old")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "new")
    c = FakeClient([FakeErr(404, "model not found"), "hi"])
    assert g.generate("p", client=c, sleep=lambda s: None, log=lambda *a: None).model == "new"


def test_auth_error_does_not_retry(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "m1")
    c = FakeClient([FakeErr(403, "PERMISSION_DENIED")])
    with pytest.raises(g.GeminiError) as e:
        g.generate("p", client=c, sleep=lambda s: None, log=lambda *a: None)
    assert e.value.kind == "auth" and len(c.calls) == 1 and "key" in e.value.user_message


def test_all_fail_gives_friendly_error(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "m1")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "")
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "1")
    c = FakeClient([FakeErr(429), FakeErr(429)])
    with pytest.raises(g.GeminiError) as e:
        g.generate("p", client=c, sleep=lambda s: None, log=lambda *a: None)
    assert e.value.kind == "quota" and "try again" in e.value.user_message.lower()


def test_grounding_unsupported_retries_without_search(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "m1")
    c = FakeClient([FakeErr(400, "tool google_search is not enabled"), "plain"])
    r = g.generate("p", grounded=True, client=c, sleep=lambda s: None, log=lambda *a: None)
    assert r.text == "plain" and r.grounded is False


def test_no_key():
    with pytest.raises(g.GeminiError) as e:
        g.generate("p")
    assert e.value.kind == "no_key"


def test_redacts_key_shapes(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.Ab8FAKEFAKEFAKEFAKEFAKEFAKE")
    e = g.GeminiError("other", "bad key AQ.Ab8FAKEFAKEFAKEFAKEFAKEFAKE and AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE00")
    assert "FAKEFAKE" not in str(e)


def test_extract_json():
    assert g.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert g.extract_json('Sure! {"a": [1]} thanks') == {"a": [1]}
    with pytest.raises(g.GeminiError):
        g.extract_json("no json here")
