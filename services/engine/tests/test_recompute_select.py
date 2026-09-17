"""`RECOMPUTE_COLUMNS` pinned to the functions that read an opportunity row.

The recompute asks PostgREST for a projection instead of `select=*`, which makes the column
list a contract between a constant in `ingest.py` and a dozen consumers in three other modules.
Nothing enforces that contract at runtime, and **both directions of drift are silent**:

  * **Too narrow** — a consumer reads a column the select stopped providing. `dict.get()`
    returns None, and every consumer here treats None as "the portal published no value": the
    gate declines to exclude, `keyword_relevance` scores an empty string, `evaluate_eligibility`
    answers `unknown`. The feed keeps returning rows, the sweep keeps reporting success, and the
    tenders that should have ranked high quietly stop doing so. That is ET-7 — the one failure
    in this product with no natural feedback signal — arriving through an optimisation.
  * **Too wide** — a column nobody reads stays in the list and is paid for three times a day
    per workspace, forever, which is the thing this change exists to stop.

So the two tests below come at it from opposite sides, and neither is sufficient alone:

  * `TestEveryConsumerSurvivesTheProjection` builds a row that **raises** on any column outside
    the list and runs the real functions over it. A missing column becomes a loud failure here
    instead of a silent None in production. This is the known-pitfalls rule about stubs stated
    the other way round: a stub that returns MORE than the real query does is not a test, so
    this one returns exactly what the real query returns and nothing else.
  * `TestTheListMatchesWhatTheConsumersActuallyRead` records every key the same real functions
    touch and compares the recorded set with the constant in both directions.

**Exercise the branches deliberately.** A first pass at the recorder missed `source_id`
entirely, because `_enrich_documents` reads it only after `not eligibility` is true and the
sample row had its eligibility already parsed — the `and` short-circuited and the probe
reported a nine-column answer with total confidence. A row that happens not to take a branch
proves nothing about the column that branch reads, which is why `_ENRICH_ROWS` below holds both
shapes and why the equality assertion, not the subset one, is what caught it.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.deterministic.discovery import (
    Rule,
    evaluate_eligibility,
    evaluate_gate,
    keyword_relevance,
)
from app.discovery import relevance
from app.discovery.ingest import RECOMPUTE_COLUMNS, SOURCES_WITH_ELIGIBILITY
from pipeline.relevance import _tender_line

#: Keywords and rules chosen so EVERY rule kind fires its condition — an inert rule reads no
#: column, so a rule list that never matches would pin nothing.
KEYWORDS = ["wire rope", "steel"]
ALL_RULE_KINDS = [
    Rule(name="cat-in", kind="category_prefix_in", spec={"prefixes": ["zzz_"]}),
    Rule(name="cat-not-in", kind="category_prefix_not_in", spec={"prefixes": ["steel_"]}),
    Rule(name="auth-in", kind="authority_contains", spec={"needles": ["Defence"]}),
    Rule(name="auth-not-in", kind="authority_not_contains", spec={"needles": ["Steel"]}),
    Rule(name="days", kind="min_days_to_close", spec={"days": 3}),
    Rule(name="kw", kind="keyword_match_required", spec={"keywords": KEYWORDS}),
    Rule(name="value", kind="value_between", spec={"min": 1, "max": 10**12}),
]


def _row(**overrides: Any) -> dict[str, Any]:
    """A row carrying EXACTLY the projected columns — the shape PostgREST will now return."""
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "title": "Supply of Steel Wire Rope 20 mm IS 2266",
        "authority": "Ministry of Steel",
        "category_codes": ["steel_wire_rope", "services_home_cust"],
        "closing_at": "2099-12-01T00:00:00+00:00",
        "estimated_value": 4_500_000,
        "eligibility": {"min_avg_annual_turnover_inr": 5_000_000},
        "market": "IN",
        "document_urls": ["https://portal.example/bid/GEM-2026-B-1"],
        "source_id": next(iter(SOURCES_WITH_ELIGIBILITY)),
    }
    assert set(row) == set(RECOMPUTE_COLUMNS), (
        "this fixture must mirror the projection exactly, or it stops testing it"
    )
    row.update(overrides)
    return row


class _StrictRow(dict):
    """A row that REFUSES any column the projection does not carry.

    Production would answer None and carry on; that is the whole danger. Raising converts the
    silent degradation into a test failure that names the column.
    """

    def get(self, key, default=None):
        self._check(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self._check(key)
        return super().__getitem__(key)

    @staticmethod
    def _check(key: str) -> None:
        if key not in RECOMPUTE_COLUMNS:
            raise AssertionError(
                f"a recompute consumer read {key!r}, which the projection does not select. "
                f"In production this returns None silently and the gate reads it as "
                f"'no value published'. Add {key!r} to RECOMPUTE_COLUMNS with its consumer, "
                f"or stop reading it."
            )


class _RecordingRow(dict):
    """Same row, recording rather than refusing — the other direction of drift."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.seen: set[str] = set()

    def get(self, key, default=None):
        self.seen.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.seen.add(key)
        return super().__getitem__(key)


def _run_every_consumer(row) -> None:
    """Every function the recompute applies to an opportunity row, with the real code.

    Deliberately not a call to `recompute_matches` itself: that would need half the module
    monkeypatched, and each patch is another chance to stub a consumer out of the very check
    this file exists to perform.
    """
    # 1. the gate — every rule kind, so every column a rule can read is read
    evaluate_gate(row, ALL_RULE_KINDS)
    # 2. the deterministic keyword scorer (the model-outage fallback, and the gate's own
    #    `keyword_match_required`)
    keyword_relevance(row, KEYWORDS)
    # 3. the relevance cache key — a column missing here silently re-scores or never re-scores
    relevance.input_hash("Manufacturer of steel wire rope", KEYWORDS, row)
    relevance._deterministic_row(row, KEYWORDS)
    # 4. band assignment. No capability statement → the keyword path, so no model call.
    relevance.bands_for(
        [row], capability_statement="", keywords=KEYWORDS, existing={}
    )
    # 5. the model prompt builder, which runs when a capability statement DOES exist
    _tender_line(row)
    # 6. Depth-1 eligibility, including the cross-currency guard's read of `market`
    evaluate_eligibility(
        row.get("eligibility"),
        {"avg_annual_turnover_inr": 82_000_000},
        "en",
        same_currency=(row.get("market") or "IN") == "IN",
    )
    # 7. the match-row builder in `recompute_matches`
    _ = {"opportunity_id": row["id"]}
    # 8. `_enrich_documents`: the pending filter, the ordering, and the connector's parent id
    if not row.get("eligibility") and row.get("document_urls") \
            and row.get("source_id") in SOURCES_WITH_ELIGIBILITY:
        _ = str(row["document_urls"][0]).rstrip("/").rsplit("/", 1)[-1]
    _ = row.get("closing_at") or "9999"


#: Both eligibility shapes. `_enrich_documents` reads `source_id` and `document_urls` ONLY on
#: the unparsed branch, so a single row cannot reach them — see the module docstring.
_ENRICH_ROWS = ({}, {"eligibility": None})


class TestEveryConsumerSurvivesTheProjection:
    """Run the real consumers over a row that has nothing but the projected columns."""

    @pytest.mark.parametrize("overrides", _ENRICH_ROWS)
    def test_no_consumer_reads_a_column_the_select_omits(self, overrides):
        _run_every_consumer(_StrictRow(_row(**overrides)))

    def test_the_gate_decides_the_same_on_a_projected_row_as_on_a_full_one(self):
        """The change is to bytes, never to verdicts.

        A full row carries ten more columns (source_fields, raw_snapshot_ref, emd, geography,
        published_at, prebid_at, portal_ref_no, eligibility_at, first_seen_at, last_seen_at).
        If any of them could move a verdict, dropping them is a behaviour change wearing an
        optimisation's clothes.
        """
        projected = _row()
        full = {
            **projected,
            "source_fields": {"ba_is_global_tendering": True, "bid_number": "GEM/2026/B/1"},
            "raw_snapshot_ref": "s3://snapshots/abc",
            "portal_ref_no": "GEM/2026/B/1",
            "geography": "IN-JH",
            "emd": 100_000,
            "published_at": "2026-01-01T00:00:00+00:00",
            "prebid_at": "2026-02-01T00:00:00+00:00",
            "eligibility_at": "2026-01-02T00:00:00+00:00",
            "first_seen_at": "2026-01-01T00:00:00+00:00",
            "last_seen_at": "2026-09-17T00:00:00+00:00",
            "notice_language": "en",
        }

        for rules in ([], ALL_RULE_KINDS):
            thin, fat = evaluate_gate(projected, rules), evaluate_gate(full, rules)
            assert (thin.in_scope, thin.excluded_by_rule) == (fat.in_scope, fat.excluded_by_rule)

        assert keyword_relevance(projected, KEYWORDS) == keyword_relevance(full, KEYWORDS)
        assert relevance.input_hash("cap", KEYWORDS, projected) == relevance.input_hash(
            "cap", KEYWORDS, full
        )
        thin_v = evaluate_eligibility(projected.get("eligibility"), {"avg_annual_turnover_inr": 1})
        fat_v = evaluate_eligibility(full.get("eligibility"), {"avg_annual_turnover_inr": 1})
        assert (thin_v.signal, thin_v.reason) == (fat_v.signal, fat_v.reason)


class TestTheListMatchesWhatTheConsumersActuallyRead:
    def test_no_consumer_reaches_outside_the_list(self):
        """Subset: the list is not too narrow."""
        seen: set[str] = set()
        for overrides in _ENRICH_ROWS:
            row = _RecordingRow(_row(**overrides))
            _run_every_consumer(row)
            seen |= row.seen
        assert seen <= set(RECOMPUTE_COLUMNS), (
            f"read but not selected: {sorted(seen - set(RECOMPUTE_COLUMNS))}"
        )

    def test_every_listed_column_is_read_by_someone(self):
        """Superset: the list is not too wide.

        A column nobody reads is paid for on every page of every sweep of every workspace. If
        this fails, either a consumer was deleted and the column should go, or the consumer
        that reads it is missing from `_run_every_consumer` — in which case this file has
        stopped pinning it and the subset test above is no longer trustworthy either.
        """
        seen: set[str] = set()
        for overrides in _ENRICH_ROWS:
            row = _RecordingRow(_row(**overrides))
            _run_every_consumer(row)
            seen |= row.seen
        assert set(RECOMPUTE_COLUMNS) <= seen, (
            f"selected but read by nothing exercised here: "
            f"{sorted(set(RECOMPUTE_COLUMNS) - seen)}"
        )

    def test_the_list_has_no_duplicates(self):
        # A duplicate is harmless to PostgREST and a sign the list was edited by hand without
        # reading it — which is exactly when the comments stop matching the columns.
        assert len(RECOMPUTE_COLUMNS) == len(set(RECOMPUTE_COLUMNS))
