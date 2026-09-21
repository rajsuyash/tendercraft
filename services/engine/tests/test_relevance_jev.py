"""score(): Jev is the bander, Gemini writes the sentence, deterministic phrase fills the rest."""
from __future__ import annotations

from app.deterministic.discovery import phrase
from pipeline import jev
from pipeline import relevance as rel
from pipeline.client import ModelError
from pipeline.jev import JevBand


def _t(i, closing="2026-10-01"):
    return {"id": f"t{i}", "title": f"Tender {i}", "category_codes": [], "authority": "", "closing_at": closing}


def _jev(bands: dict[str, tuple[str, float]]):
    return lambda cap, kw, opps: {o["id"]: JevBand(o["id"], *bands[o["id"]]) for o in opps if o["id"] in bands}


def _gemini(results):
    """results: {id: (band, rationale, matched)}; returns RelevanceResult per item asked for."""
    def fake(cap, kw, batch, language="en"):
        return [rel.RelevanceResult(o["id"], *results[o["id"]], confidence=0.9) for o in batch if o["id"] in results]
    return fake


def test_jev_band_wins_and_gemini_only_supplies_words(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(jev, "band_tenders", _jev({"t1": ("high", 0.9)}))
    monkeypatch.setattr(rel, "score_batch", _gemini({"t1": ("low", "You make this rope.", "steel wire rope")}))
    out = rel.score("cap", [], [_t(1)], explain_budget=40)
    assert out["t1"].band == "high"
    assert out["t1"].rationale == "You make this rope."
    assert out["t1"].matched_capability == "steel wire rope"
    assert out["t1"].confidence == 0.9


def test_low_rows_never_reach_gemini_and_get_the_phrase(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(jev, "band_tenders", _jev({"t1": ("low", 0.97)}))
    monkeypatch.setattr(rel, "score_batch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("gemini called")))
    out = rel.score("cap", [], [_t(1)], explain_budget=40, language="fr")
    assert out["t1"].band == "low"
    assert out["t1"].rationale == phrase("jev_band", "fr", band="low", confidence=97)
    assert out["t1"].matched_capability == ""


def test_explain_budget_caps_gemini_soonest_closing_first(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    opps = [_t(1, "2026-12-01"), _t(2, "2026-10-01"), _t(3, "2026-11-01")]
    monkeypatch.setattr(jev, "band_tenders", _jev({"t1": ("high", .8), "t2": ("high", .8), "t3": ("medium", .6)}))
    asked = []

    def fake(cap, kw, batch, language="en"):
        asked.extend(o["id"] for o in batch)
        return [rel.RelevanceResult(o["id"], "high", "why", "cap", 0.9) for o in batch]

    monkeypatch.setattr(rel, "score_batch", fake)
    out = rel.score("cap", [], opps, explain_budget=2)
    assert asked == ["t2", "t3"]
    assert out["t1"].rationale == phrase("jev_band", "en", band="high", confidence=80)


def test_jev_failure_falls_back_to_gemini_path_with_budget(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(jev, "band_tenders", lambda *a: {})
    monkeypatch.setattr(rel, "score_batch", _gemini({"t1": ("medium", "adjacent", "rope")}))
    out = rel.score("cap", [], [_t(1), _t(2)], explain_budget=1)
    assert out["t1"].band == "medium" and "t2" not in out  # Gemini path, budget of 1


def test_no_key_means_no_jev_call(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(jev, "band_tenders", lambda *a: (_ for _ in ()).throw(AssertionError("jev called")))
    monkeypatch.setattr(rel, "score_batch", _gemini({"t1": ("high", "why", "cap")}))
    assert rel.score("cap", [], [_t(1)], explain_budget=40)["t1"].band == "high"


def test_gemini_failure_keeps_jev_band_with_phrase(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(jev, "band_tenders", _jev({"t1": ("high", 0.66)}))
    monkeypatch.setattr(rel, "score_batch", lambda *a, **k: (_ for _ in ()).throw(ModelError("down")))
    out = rel.score("cap", [], [_t(1)], explain_budget=40)
    assert out["t1"].band == "high" and out["t1"].rationale == phrase("jev_band", "en", band="high", confidence=66)


def test_disagreement_is_counted_not_applied(monkeypatch, caplog):
    import logging
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(jev, "band_tenders", _jev({"t1": ("high", 0.9)}))
    monkeypatch.setattr(rel, "score_batch", _gemini({"t1": ("low", "no", "")}))
    with caplog.at_level(logging.INFO, logger="tendercraft.pipeline"):
        out = rel.score("cap", [], [_t(1)], explain_budget=40)
    assert out["t1"].band == "high"
    assert any("disagreements=1" in r.message for r in caplog.records)


def test_bands_for_passes_every_stale_row_to_score(monkeypatch):
    from app.discovery import relevance as orch
    seen = {}

    def fake_score(cap, kw, opps, language="en", explain_budget=40):
        seen["n"] = len(opps)
        seen["budget"] = explain_budget
        return {}

    monkeypatch.setattr(rel, "score", fake_score)
    opps = [{"id": f"t{i}", "title": "x", "category_codes": [], "closing_at": None} for i in range(60)]
    orch.bands_for(opps, capability_statement="cap", keywords=["x"], budget=40)
    assert seen == {"n": 60, "budget": 40}
