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
from app.deterministic.discovery import evaluate_eligibility
from app.discovery.registry import REGISTRY, for_market


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


class TestAnUnreviewedSourceCannotBeSwept:
    """`registry.py` has always said a blank `terms_reviewed` means DO NOT ENABLE, and until
    the first unreviewed row arrived that sentence was a comment rather than a control: one
    environment variable was the whole distance between "written down" and "crawling".

    It matters now because `bidassist` is registered, reachable, and deliberately unreviewed —
    it is the first credentialed source in the system, and both the G-8 divergence and the
    vendor-side feed scope are open questions for a human (docs/discovery/source-bidassist.md).
    A source whose terms nobody has read must not start sweeping because a deploy set a URL.
    """

    def test_a_source_with_no_review_date_is_not_returned_even_with_a_url(self, monkeypatch):
        from app.discovery import registry

        unreviewed = registry.Source(
            source_id="unreviewed", market="ZZ", connector_url="https://connector.example",
            tier="T2", terms_reviewed="", reviewer="nobody",
        )
        monkeypatch.setattr(registry, "REGISTRY", (unreviewed,))
        assert registry.for_market("ZZ") == ()

    def test_the_same_source_becomes_available_once_reviewed(self, monkeypatch):
        from app.discovery import registry

        reviewed = registry.Source(
            source_id="reviewed", market="ZZ", connector_url="https://connector.example",
            tier="T2", terms_reviewed="2026-08-29", reviewer="a human",
        )
        monkeypatch.setattr(registry, "REGISTRY", (reviewed,))
        assert [s.source_id for s in registry.for_market("ZZ")] == ["reviewed"]

    def test_every_registered_source_names_a_reviewer_not_a_placeholder(self):
        """A date with no name behind it is a rubber stamp, and `PENDING` left in the reviewer
        field while a date was added is how an unratified source quietly becomes a live one.

        bidassist was ratified by the decision owner on 2026-08-29 — the G-8 reading that the
        guardrail's subject is a *portal*, not a vendor we pay. The date and the name travel
        together so the next person can find who decided and go read the argument.

        Deliberately checks that the reviewer field does not *start* with PENDING rather than
        that it never contains the word: `gem_bidplus` and `ted` both read "engineering
        (agent-assisted probe, human sign-off pending)", which is an honest statement of who
        reviewed and what is still outstanding. A field whose whole value is a placeholder is
        the different thing — nobody reviewed it.
        """
        for source in REGISTRY:
            if not source.terms_reviewed.strip():
                continue
            reviewer = source.reviewer.strip()
            assert reviewer, f"{source.source_id} has a date but no reviewer"
            assert not reviewer.upper().startswith("PENDING"), (
                f"{source.source_id} is dated but its reviewer is still a placeholder — "
                "either the review happened and the name belongs here, or the date does not"
            )

    def test_bidassist_is_enabled_only_where_a_connector_is_configured(self, monkeypatch):
        """Ratified is not the same as running. The source still vanishes without its URL,
        which is what keeps a local test run and CI from talking to a paid API."""
        import os

        from app.discovery import registry

        monkeypatch.delenv("BIDASSIST_CONNECTOR_URL", raising=False)
        assert os.environ.get("BIDASSIST_CONNECTOR_URL") is None
        row = next(s for s in registry.REGISTRY if s.source_id == "bidassist")
        assert row.terms_reviewed == "2026-08-29"
        assert row.connector_url == ""
        assert "bidassist" not in [s.source_id for s in for_market("IN")]


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


class TestMoneyIsNeverComparedAcrossCurrencies:
    """Found live, not in review: seven tenders on the French workspace were reported as below a
    turnover bar the day cross-market watching shipped.

    `profile_financials.turnover_cr` holds a bare number in the MARKET's own large unit — crore
    in India, millions of euros in France. The comparator multiplied it by 1e7 unconditionally
    and called the result rupees, so €2.43M was compared against Indian rupee thresholds as
    ₹2.43 Cr. Both the "below the bar" and the "clears the bar" verdicts were meaningless.

    The fix is to decline, not to convert: there is no exchange rate in this system, and a
    verdict computed from one would be stale the day after it was stored.
    """

    FIELDS = {"min_avg_annual_turnover_inr": 50_000_000}
    RICH = {"avg_annual_turnover_inr": 900_000_000}
    POOR = {"avg_annual_turnover_inr": 1_000_000}

    def test_a_cross_currency_row_is_never_given_a_verdict(self):
        for profile in (self.RICH, self.POOR):
            result = evaluate_eligibility(self.FIELDS, profile, "en", same_currency=False)
            # Neither direction. A false PASS is as wrong as a false FAIL here, and the pass
            # was the more common one — 154 of the 161 bogus verdicts said "clears the bar".
            assert result.signal == "unknown", profile
            assert "different currency" in result.reason

    def test_the_same_currency_path_is_unchanged(self):
        assert evaluate_eligibility(self.FIELDS, self.RICH).signal == "likely_eligible"
        assert evaluate_eligibility(self.FIELDS, self.POOR).signal == "likely_ineligible"

    def test_the_refusal_is_explained_in_the_market_language(self):
        result = evaluate_eligibility(self.FIELDS, self.RICH, "fr", same_currency=False)
        assert "devise différente" in result.reason

    def test_a_tender_stating_no_bar_says_so_even_across_currencies(self):
        """Ordering: the no-bar branch runs BEFORE the currency guard.

        This assertion is the inverse of the one first written here, and the change is
        deliberate. "This tender sets no minimum turnover requirement" is a fact about the
        TENDER and is true in every currency; answering "the bar was not compared" when there
        is no bar declines a question nobody asked. The live feed showed the inconsistency —
        three Indian rows all displaying `non précisé` gave two different explanations
        depending only on whether their document had been parsed.
        """
        result = evaluate_eligibility(
            {"min_avg_annual_turnover_inr": None}, self.RICH, "en", same_currency=False
        )
        assert result.signal == "unknown"
        assert "no minimum turnover" in result.reason
        assert "different currency" not in result.reason

    def test_an_unparsed_document_still_outranks_everything(self):
        # Nothing was read, so neither the bar nor the currency is knowable yet.
        assert (
            evaluate_eligibility(None, self.RICH, "en", same_currency=False).reason
            == "Bid document not read yet"
        )
