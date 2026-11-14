import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Tests never use a real key or the network: strip any key before modules load.
for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ.pop(k, None)
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="pob-test-")
os.environ["RATE_LIMIT_PER_MIN"] = "1000"
os.environ.pop("RANK_PROVIDER", None)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("time.sleep", lambda s: None)
    yield
