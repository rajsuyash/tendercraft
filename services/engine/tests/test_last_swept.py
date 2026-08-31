"""When the corpus was last swept, per market.

Written after the feed header spent weeks reading "swept 31 Jul" while the GeM sweep ran daily.
The cause was that it took `items[0].last_seen_at` — the age of one TENDER. A closed tender
stops appearing in the portal listing, so its timestamp freezes on the day it closed, and the
workspace's best match happened to have closed in July.
"""

from __future__ import annotations

import pytest

from app import db


@pytest.fixture
def rows(monkeypatch):
    """Rows come back newest-first, which is what the query asks PostgREST for."""
    captured = {}

    # Every call is recorded, not just the last. `list_workspaces_for_sweep` now makes more
    # than one — it reads discovery_rules and vendor_profiles to decide sweep ORDER — and a
    # fixture that keeps only the final call turns "assert the workspaces query is unfiltered"
    # into "assert the last query happened to be workspaces", which is a different claim.
    captured["calls"] = []

    def fake_rest(method, path, **kwargs):
        params = kwargs.get("params") or {}
        captured["calls"].append({"path": path, "params": params})
        captured["path"] = path
        captured["params"] = params
        return captured.get("returns", [])

    monkeypatch.setattr(db, "_rest", fake_rest)
    return captured


def test_the_newest_row_per_market_wins(rows):
    rows["returns"] = [
        {"market": "IN", "last_seen_at": "2026-08-25T07:58:00Z"},
        {"market": "FR", "last_seen_at": "2026-07-31T10:57:00Z"},
        {"market": "IN", "last_seen_at": "2026-07-01T00:00:00Z"},
    ]
    assert db.last_swept_at(["IN", "FR"]) == {
        "IN": "2026-08-25T07:58:00Z",
        "FR": "2026-07-31T10:57:00Z",
    }


def test_a_market_is_reported_separately_not_collapsed(rows):
    """One number would let a working GeM sweep vouch for a TED connector that died a month
    ago — which is the exact production state this was written in."""
    rows["returns"] = [
        {"market": "IN", "last_seen_at": "2026-08-25T07:58:00Z"},
        {"market": "FR", "last_seen_at": "2026-07-31T10:57:00Z"},
    ]
    result = db.last_swept_at(["IN", "FR"])

    assert len(result) == 2
    assert result["FR"] < result["IN"]


def test_the_query_is_scoped_to_the_watched_markets(rows):
    rows["returns"] = []
    db.last_swept_at(["IN", "FR"])

    assert rows["path"] == "opportunities"
    assert rows["params"]["market"] == "in.(IN,FR)"
    assert rows["params"]["order"] == "last_seen_at.desc"


def test_no_markets_asked_for_means_no_scope_condition(rows):
    rows["returns"] = []
    db.last_swept_at([])
    assert "market" not in rows["params"]


def test_an_empty_corpus_reports_nothing_rather_than_a_wrong_date(rows):
    """The header renders only when this is non-empty. A fabricated "now" would say the sweep
    succeeded on a workspace that has never swept."""
    rows["returns"] = []
    assert db.last_swept_at(["IN"]) == {}


def test_rows_missing_a_market_or_timestamp_are_ignored(rows):
    rows["returns"] = [
        {"market": None, "last_seen_at": "2026-08-25T07:58:00Z"},
        {"market": "IN", "last_seen_at": None},
        {"market": "IN", "last_seen_at": "2026-08-20T00:00:00Z"},
    ]
    assert db.last_swept_at(["IN"]) == {"IN": "2026-08-20T00:00:00Z"}


def test_the_sweep_fanout_resolves_markets_the_same_way_as_the_feed(rows):
    """`list_workspaces_for_sweep` duplicates `get_workspace_markets`'s resolution — this pins
    them together, per the auth.py precedent: where a rule must exist twice, test it twice."""
    rows["returns"] = [
        {"id": "w1", "name": "Watches two", "market": "IN", "discovery_markets": ["IN", "FR"]},
        {"id": "w2", "name": "Home only", "market": "FR", "discovery_markets": []},
        {"id": "w3", "name": "Neither set", "market": None, "discovery_markets": None},
    ]
    assert db.list_workspaces_for_sweep() == [
        {"id": "w1", "name": "Watches two", "markets": ["IN", "FR"]},
        {"id": "w2", "name": "Home only", "markets": ["FR"]},
        {"id": "w3", "name": "Neither set", "markets": ["IN"]},
    ]


def test_the_sweep_fanout_has_no_opt_in_filter(rows):
    """Unlike the digest, every workspace expects a current feed whether or not it configured
    alerts — so this query must not learn to filter."""
    rows["returns"] = []
    db.list_workspaces_for_sweep()
    workspaces = [c for c in rows["calls"] if c["path"] == "workspaces"]
    assert len(workspaces) == 1, "the fan-out must read the workspace list exactly once"
    assert "enabled" not in workspaces[0]["params"]


def test_the_fanout_orders_configured_workspaces_first_and_drops_none(monkeypatch):
    """Ordering, never filtering.

    296 workspaces existed in production and exactly ONE had a discovery rule; the rest were
    isolation-test debris that `audit_events` being append-only makes undeletable. The
    per-workspace recompute is where the wall-clock goes, so a scheduled run reached the real
    workspace hours late or not at all — and 3600s is already the platform's ceiling.

    Dropping the debris would be faster and wrong: a workspace missing from the fan-out is a
    workspace whose feed silently stops updating, which is the failure the job exists to
    prevent. So every workspace is still returned, in a different order.
    """
    listing = [
        {"id": "debris1", "name": "Dup Test", "market": "IN", "discovery_markets": ["IN"]},
        {"id": "real", "name": "A Customer", "market": "IN", "discovery_markets": ["IN"]},
        {"id": "debris2", "name": "RBAC Workspace", "market": "IN", "discovery_markets": ["IN"]},
    ]

    def fake_rest(method, path, **kwargs):
        if path == "workspaces":
            return listing
        if path == "discovery_rules":
            return [{"workspace_id": "real"}]
        return []  # vendor_profiles

    monkeypatch.setattr(db, "_rest", fake_rest)
    got = db.list_workspaces_for_sweep()
    assert [w["id"] for w in got] == ["real", "debris1", "debris2"]
    assert len(got) == 3, "no workspace may be dropped from the fan-out"


def test_a_vendor_profile_also_counts_as_configured(monkeypatch):
    """A customer who filled in a profile but has not written a rule yet is still real."""
    def fake_rest(method, path, **kwargs):
        if path == "workspaces":
            return [{"id": "debris", "name": "Dup Test", "market": "IN"},
                    {"id": "real", "name": "A Customer", "market": "IN"}]
        if path == "vendor_profiles":
            return [{"workspace_id": "real"}]
        return []

    monkeypatch.setattr(db, "_rest", fake_rest)
    assert [w["id"] for w in db.list_workspaces_for_sweep()] == ["real", "debris"]


def test_an_unreadable_ordering_query_degrades_to_the_original_order(monkeypatch):
    """The ordering is an optimisation. If the helper read fails it must fall back to sweeping
    everything in portal order — never to an empty or truncated fan-out."""
    def fake_rest(method, path, **kwargs):
        if path == "workspaces":
            return [{"id": "a", "name": "A", "market": "IN"},
                    {"id": "b", "name": "B", "market": "IN"}]
        raise RuntimeError("postgrest is having a moment")

    monkeypatch.setattr(db, "_rest", fake_rest)
    assert [w["id"] for w in db.list_workspaces_for_sweep()] == ["a", "b"]
