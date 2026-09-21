"""pipeline/jev.py — transport patched at the point of use (pipeline.jev._post), never at httpx."""
from __future__ import annotations

import json
import logging

import pytest

from pipeline import jev
from pipeline.client import ModelError


def _tender(i: int, title: str = "Steel Wire Rope 19mm") -> dict:
    return {"id": f"t{i}", "title": title, "category_codes": ["Steel Wire Rope"], "authority": "SAIL"}


def _answer(choice="high", p=(0.8, 0.15, 0.05), conf=0.7) -> dict:
    return {"choice": choice, "probabilities": {"high": p[0], "medium": p[1], "low": p[2]}, "confidence": conf}


def test_available_requires_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert jev.available() is False
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    assert jev.available() is True


def test_band_tenders_parses_choice_probabilities_confidence(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    seen = []

    def fake_post(body):
        seen.append(body)
        return {"answers": {"t1": _answer(), "t2": _answer("low", (0.01, 0.04, 0.95), 0.99)},
                "usage": {"input_tokens": 100, "output_tokens": 5}}

    monkeypatch.setattr(jev, "_post", fake_post)
    out = jev.band_tenders("Manufacturer of steel wire rope", ["wire rope"], [_tender(1), _tender(2, "Pest control")])
    assert out["t1"].band == "high" and out["t1"].confidence == 0.7 and out["t1"].probabilities["high"] == 0.8
    assert out["t2"].band == "low"
    body = seen[0]
    assert body["model"] == jev.MODEL
    assert body["state"]["bidder"]["capability_statement"] == "Manufacturer of steel wire rope"
    assert set(body["questions"]) == {"t1", "t2"}
    q = body["questions"]["t1"]
    assert q["type"] == "choice" and set(q["criteria"]) == {"high", "medium", "low"}
    assert "`tenders.t1`" in q["instructions"]
    assert body["state"]["tenders"]["t1"]["title"] == "Steel Wire Rope 19mm"


def test_chunks_by_jev_chunk(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(jev, "CHUNK", 100)
    calls = []

    def fake_post(body):
        calls.append(len(body["questions"]))
        return {"answers": {k: _answer() for k in body["questions"]}, "usage": {"input_tokens": 1}}

    monkeypatch.setattr(jev, "_post", fake_post)
    out = jev.band_tenders("x", [], [_tender(i) for i in range(250)])
    assert calls == [100, 100, 50] and len(out) == 250


def test_chunk_failure_is_partial_not_fatal(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(jev, "CHUNK", 2)
    n = {"i": 0}

    def fake_post(body):
        n["i"] += 1
        if n["i"] == 1:
            raise ModelError("boom")
        return {"answers": {k: _answer() for k in body["questions"]}, "usage": {"input_tokens": 1}}

    monkeypatch.setattr(jev, "_post", fake_post)
    out = jev.band_tenders("x", [], [_tender(i) for i in range(4)])
    assert set(out) == {"t2", "t3"}


def test_out_of_enum_choice_and_missing_ids_are_dropped(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(jev, "_post", lambda body: {"answers": {"t1": _answer("maybe"), "zzz": _answer()}, "usage": {}})
    assert jev.band_tenders("x", [], [_tender(1), _tender(2)]) == {}


def test_post_retries_once_on_429_then_raises(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    attempts = []

    class Resp:
        status_code = 429
        headers = {"retry-after": "0"}
        text = "slow down"

        def json(self):
            return {}

    monkeypatch.setattr(jev.http.client, "post", lambda *a, **k: attempts.append(1) or Resp())
    monkeypatch.setattr(jev.time, "sleep", lambda s: None)
    with pytest.raises(ModelError):
        jev._post({"state": {}, "model": jev.MODEL, "questions": {}})
    assert len(attempts) == 2  # retry cap 1


def test_usage_is_logged(monkeypatch, caplog):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(jev, "_post", lambda body: {"answers": {"t1": _answer()}, "usage": {"input_tokens": 4651, "output_tokens": 795}})
    with caplog.at_level(logging.INFO, logger="tendercraft.pipeline"):
        jev.band_tenders("x", [], [_tender(1)])
    assert any("jev usage" in r.message and "input_tokens=4651" in r.message for r in caplog.records)


def test_prompt_file_is_the_source_of_criteria():
    data = json.loads(jev._PROMPT_PATH.read_text())
    assert set(data["criteria"]) == {"high", "medium", "low"}
    assert "{tender_ref}" in data["instructions"]
