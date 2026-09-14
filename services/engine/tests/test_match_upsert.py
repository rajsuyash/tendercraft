"""A bulk upsert must never turn 'I did not touch this column' into 'set it to NULL'.

`relevance.bands_for` skips rows whose input hash is unchanged, so those rows carry no
relevance keys at all. PostgREST needs every object in one bulk body to share a key set, and
the old fix — pad with None — wrote an explicit NULL over the cached band on every run that
reused it. Measured 2026-09-14: 3,192 of 6,694 match rows in one workspace were band-NULL,
including 14 open wire-rope tenders the latest run had just touched.
"""

from __future__ import annotations

from app import db


def _capture(monkeypatch):
    posted: list[list[dict]] = []

    def fake_rest(method, path, *, params=None, json=None, prefer=None):
        assert method == "POST" and path == "opportunity_matches"
        posted.append(json)
        return []

    monkeypatch.setattr(db, "_rest", fake_rest)
    return posted


def test_a_row_without_relevance_keys_is_not_padded_with_null_bands(monkeypatch):
    posted = _capture(monkeypatch)
    banded = {"opportunity_id": "a", "state": "in_scope",
              "relevance_band": "high", "relevance_input_hash": "h1"}
    cached = {"opportunity_id": "b", "state": "in_scope"}

    db.upsert_opportunity_matches("ws", [banded, cached])

    by_id = {r["opportunity_id"]: r for batch in posted for r in batch}
    assert "relevance_band" not in by_id["b"], "an untouched column must stay untouched"
    assert "relevance_input_hash" not in by_id["b"]
    assert by_id["a"]["relevance_band"] == "high"
    assert by_id["a"]["workspace_id"] == "ws" and by_id["b"]["workspace_id"] == "ws"


def test_every_request_body_has_a_uniform_key_set(monkeypatch):
    # PostgREST answers a ragged bulk body with a bare 400 and no column name.
    posted = _capture(monkeypatch)
    rows = [
        {"opportunity_id": "a", "state": "in_scope", "relevance_band": "low"},
        {"opportunity_id": "b", "state": "excluded", "excluded_by_rule": "r"},
        {"opportunity_id": "c", "state": "in_scope", "relevance_band": "high"},
    ]
    db.upsert_opportunity_matches("ws", rows)
    for batch in posted:
        assert len({frozenset(r) for r in batch}) == 1
    assert sum(len(b) for b in posted) == 3


def test_an_explicit_none_is_still_written(monkeypatch):
    # The keyword fallback deliberately writes relevance_input_hash=None ("not a final
    # answer"). Grouping by key set must keep that explicit null, not strip it.
    posted = _capture(monkeypatch)
    db.upsert_opportunity_matches("ws", [
        {"opportunity_id": "a", "state": "in_scope",
         "relevance_band": "low", "relevance_input_hash": None},
    ])
    assert posted[0][0]["relevance_input_hash"] is None
    assert "relevance_input_hash" in posted[0][0]


def test_empty_input_posts_nothing(monkeypatch):
    posted = _capture(monkeypatch)
    assert db.upsert_opportunity_matches("ws", []) == 0
    assert posted == []
