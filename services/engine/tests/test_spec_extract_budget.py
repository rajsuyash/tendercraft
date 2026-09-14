"""Extraction is about to become automatic, so its fan-out needs a ceiling.

Until now `extract_many` was reached only by a human clicking "Read specifications" on a
schedule they were looking at, so an unbounded loop was bounded in practice by attention.
Task 2 removes the human. Measured 2026-09-14: one real tender holds 48 distinct line
descriptions, which is fine; a 400-line BOQ is not, and nothing would have said so.
"""

from __future__ import annotations

from app import spec_service


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
