"""Extraction is about to become automatic, so its fan-out needs a ceiling.

Until now `extract_many` was reached only by a human clicking "Read specifications" on a
schedule they were looking at, so an unbounded loop was bounded in practice by attention.
Task 2 removes the human. Measured 2026-09-14: one real tender holds 48 distinct line
descriptions, which is fine; a 400-line BOQ is not, and nothing would have said so.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db, spec_service
from app.auth import AuthedUser, get_current_user
from app.main import create_app


def test_extract_many_stops_at_the_budget(monkeypatch):
    from pipeline import spec_extractor

    seen: list[str] = []
    monkeypatch.setattr(spec_extractor, "extract_parameters",
                        lambda d: seen.append(d) or ())

    out = spec_extractor.extract_many([f"line {i}" for i in range(50)], limit=10)

    assert len(seen) == 10, "the budget is a ceiling on MODEL CALLS, not a slice of the output"
    assert len(out) == 10


def test_extract_many_dedupes_before_spending_the_budget(monkeypatch):
    # A BOQ repeats the same rope at four consignee sites. Deduping first is the difference
    # between spending the budget on four identical strings and on four different ones.
    from pipeline import spec_extractor

    seen: list[str] = []
    monkeypatch.setattr(spec_extractor, "extract_parameters",
                        lambda d: seen.append(d) or ())

    spec_extractor.extract_many(["same"] * 20 + ["a", "b", "c"], limit=3)

    assert seen == ["same", "a", "b"], "dedupe must happen before the cap, not after"


def test_extract_schedule_reports_what_it_skipped(monkeypatch):
    # A silent partial read is the failure this product keeps finding: the number looks fine
    # and the remainder is invisible. The caller must be able to say "48 of 96 read".
    monkeypatch.setattr(spec_service.db, "replace_line_item_parameters",
                        lambda *a, **k: None)
    from pipeline import spec_extractor

    monkeypatch.setattr(spec_extractor, "extract_parameters", lambda d: ())

    items = [{"id": f"i{i}", "description": f"desc {i}"} for i in range(5)]
    result = spec_service.extract_schedule("ws", items, limit=2)

    assert result["distinct"] == 5
    assert result["read"] == 2
    assert result["skipped"] == 3


def test_extract_many_treats_a_negative_budget_as_zero_calls(monkeypatch):
    # SPEC_EXTRACT_BUDGET is an env var; a typo'd negative must mean "no calls", not
    # `unique[:-1]` silently dropping the last description off the end.
    from pipeline import spec_extractor

    seen: list[str] = []
    monkeypatch.setattr(spec_extractor, "extract_parameters",
                        lambda d: seen.append(d) or ())

    out = spec_extractor.extract_many(["a", "b", "c"], limit=-1)

    assert seen == []
    assert out == {}


# ── the route's response must not collide `lines` (the count) with `assess_schedule`'s
#    `lines` (the per-line array) — a dict-literal merge lets the second silently win ────────

@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


def test_extract_route_keeps_total_lines_and_the_line_array_separate(client, monkeypatch):
    from pipeline import spec_extractor

    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": t})
    monkeypatch.setattr(
        db, "get_line_items",
        lambda t, w: [{"id": f"i{i}", "description": f"desc {i}", "spec_parameters": []}
                      for i in range(5)],
    )
    monkeypatch.setattr(db, "get_capability_specs", lambda w: [])
    monkeypatch.setattr(db, "replace_line_item_parameters", lambda *a, **k: None)
    # The manual path stamps `specs_extracted_at` too, so a read done here is not reported
    # forever as "never read" (migration 0040).
    monkeypatch.setattr(db, "mark_specs_extracted", lambda w, t: None)
    monkeypatch.setattr(spec_extractor, "extract_parameters", lambda d: ())

    body = client.post("/api/tenders/tender-1/schedule/extract").json()["data"]

    assert isinstance(body["total_lines"], int)
    assert body["total_lines"] == 5
    assert isinstance(body["lines"], list)
    assert len(body["lines"]) == 5


def test_extract_route_does_not_stamp_when_the_read_is_partial(client, monkeypatch):
    # Same rule as the background path (test_schedule_autoextract.py): a schedule bigger than
    # the budget must leave the tender unstamped, or the skipped lines get announced as "state
    # no specification" when nobody has actually read them.
    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": t})
    monkeypatch.setattr(
        db, "get_line_items",
        lambda t, w: [{"id": "i1", "description": "d", "spec_parameters": []}],
    )
    monkeypatch.setattr(db, "get_capability_specs", lambda w: [])
    monkeypatch.setattr(spec_service, "extract_schedule",
                        lambda ws, items, **k: {"distinct": 100, "read": 80, "skipped": 20,
                                                "populated": 80, "budget": 80})
    stamped: list[tuple] = []
    monkeypatch.setattr(db, "mark_specs_extracted",
                        lambda w, t: stamped.append((w, t)))

    r = client.post("/api/tenders/tender-1/schedule/extract")

    assert r.status_code == 200
    assert stamped == [], "a partial read must leave the tender unstamped"
