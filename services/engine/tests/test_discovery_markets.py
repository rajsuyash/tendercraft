"""Watched markets — the scope that decides which countries reach the feed.

The load-bearing property is not "the list saves". It is that **no path can produce an empty
one**. A workspace watching nothing renders a feed identical to "no tenders published today",
and a tender never seen produces no error message anywhere in this product (ET-7) — so an empty
scope is not a small misconfiguration, it is the module's whole failure mode arriving through
its own settings screen.

Three independent guards, because one of them will eventually be bypassed:
  * the DB check constraint (migration 0022, verified against production Postgres),
  * the endpoint's own 422,
  * `get_workspace_markets` falling back to the home market rather than returning [].
"""

from __future__ import annotations

from app import db
from app.discovery.registry import REGISTRY


class TestTheWatchedSetCanNeverBeEmpty:
    def test_a_workspace_with_no_stored_scope_falls_back_to_its_home_market(self, monkeypatch):
        monkeypatch.setattr(
            db, "_rest", lambda *a, **k: [{"market": "FR", "discovery_markets": []}]
        )
        assert db.get_workspace_markets("w") == ["FR"]

    def test_a_missing_workspace_still_yields_a_usable_scope(self, monkeypatch):
        # Returning [] here would mean "watch nothing", and `get_opportunities` reads an empty
        # list as "no filter" — so the two failures would cancel into showing EVERY market's
        # corpus to a workspace we could not identify. Neither half may be relaxed alone.
        monkeypatch.setattr(db, "_rest", lambda *a, **k: [])
        assert db.get_workspace_markets("nope") == ["IN"]

    def test_a_stored_scope_is_returned_verbatim(self, monkeypatch):
        monkeypatch.setattr(
            db, "_rest", lambda *a, **k: [{"market": "FR", "discovery_markets": ["FR", "IN"]}]
        )
        assert db.get_workspace_markets("w") == ["FR", "IN"]


class TestTheCorpusQueryIsScopedByTheWatchedSet:
    def test_several_markets_become_one_in_filter(self, monkeypatch):
        seen: dict = {}

        def fake(method, path, *, params=None, **k):
            seen.update(params or {})
            return []

        monkeypatch.setattr(db, "_rest", fake)
        db.get_opportunities(markets=["FR", "IN"])
        assert seen["market"] == "in.(FR,IN)"

    def test_duplicates_collapse_rather_than_widening_the_query(self, monkeypatch):
        seen: dict = {}
        monkeypatch.setattr(
            db, "_rest", lambda m, p, *, params=None, **k: (seen.update(params or {}), [])[1]
        )
        db.get_opportunities(markets=["IN", "IN", "FR"])
        assert seen["market"] == "in.(FR,IN)"


def test_every_registered_market_is_offerable():
    """A country the UI can offer must have a source, or ticking it promises tenders that can
    never arrive — which reads to the user as a broken feed, not as a missing connector."""
    for source in REGISTRY:
        assert source.market, f"{source.source_id} has no market"


class TestTheFeedReadIsScopedTooNotJustTheRecompute:
    """The bug this class exists to prevent, verified live on production before the fix:
    unticking India re-ranked the feed and filtered nothing. `recompute_matches` was scoped by
    the watched set, but `get_feed` was not — and match rows created under a WIDER scope survive,
    by design, so the user's shortlist is not destroyed by toggling a country. That means the
    read is the only place the scope can be enforced, and it was the one place it was missing.
    """

    def _capture(self, monkeypatch):
        seen: dict = {}

        def fake(method, path, *, params=None, **k):
            seen.update(params or {})
            return []

        monkeypatch.setattr(db, "_rest", fake)
        return seen

    def test_the_feed_query_joins_and_filters_on_the_watched_markets(self, monkeypatch):
        seen = self._capture(monkeypatch)
        db.get_feed("w", "in_scope", markets=["FR"])
        # !inner, not a plain embed: without the join the filter nulls the embedded object and
        # the row still comes back — which looks like a tender with no details, not a hidden one.
        assert seen["select"] == "*,opportunities!inner(*)"
        assert seen["opportunities.market"] == "in.(FR)"

    def test_no_scope_means_no_filter_rather_than_no_rows(self, monkeypatch):
        # A caller that lost its scope must degrade to showing everything, never to an empty
        # feed: an empty feed is indistinguishable from "nothing published today" (ET-7).
        seen = self._capture(monkeypatch)
        db.get_feed("w", "in_scope", markets=None)
        assert seen["select"] == "*,opportunities(*)"
        assert "opportunities.market" not in seen

    def test_the_scope_helper_is_shared_so_counts_cannot_drift_from_rows(self):
        # The counters and the list must be built from ONE function. Four counters describing
        # the same object will disagree (docs/known-pitfalls.md) — here that would mean the
        # coverage strip claiming tenders the user cannot see.
        scope = db._market_scope(["IN", "FR"])
        assert scope["opportunities.market"] == "in.(FR,IN)"
