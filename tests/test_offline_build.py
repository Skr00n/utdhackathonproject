import json

import page_one


def test_offline_build_outputs(tmp_path):
    out = page_one.main(["--offline", "--outdir", str(tmp_path / "t")])
    for f in ("report.html", "landing.html", "plan.json", "fixes.json", "page_one_plan.pdf", "rank_grid.html",
              "schema_restaurant.jsonld", "schema_faq.jsonld", "where_it_stands.csv"):
        assert (out / f).exists(), f
    fixes = json.loads((out / "fixes.json").read_text())
    assert fixes["compare"]["competitors"] and fixes["close_the_gap"]
    grid = (out / "rank_grid.csv").read_text()
    assert "SIMULATED" in grid
    plan = json.loads((out / "plan.json").read_text())
    assert plan["meta"]["mode"] == "offline"


def test_require_live_never_falls_back_to_sample(tmp_path, monkeypatch):
    import gemini_client
    import pytest
    csvp = tmp_path / "r.csv"
    csvp.write_text("name,address,cuisine\nOther Place,\"Plano, TX\",Thai\n")
    with pytest.raises(gemini_client.GeminiError):
        page_one.main(["--csv", str(csvp), "--row", "0", "--require-live", "--outdir", str(tmp_path / "o")])
