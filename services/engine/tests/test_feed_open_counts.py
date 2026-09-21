"""The coverage strip counted history above a list that shows only open tenders.

Measured live on 2026-09-21 for the Usha Martin workspace: the tiles read *swept 7968, 4313 in
your feed, 3390 hidden by your rules* directly above a table holding **47 rows**. Neither number
was wrong — `count_feed` counts the bucket since the corpus began, and `get_feed` drops closed
tenders in the database before the limit (it has to: closed rows sort by band like any other and
would otherwise eat the page). They answer different questions, and the strip never said which.

So the counts get an open-only sibling, using the SAME predicate `get_feed` filters with. Two
properties are worth pinning rather than reading:

* the open count and the all-time count must actually differ on a corpus with history — a
  parameter that reaches PostgREST and changes nothing looks identical to one that works;
* `closing_at is null` stays INSIDE the open set. A portal that never filled the field has not
  told us the tender is over, and treating unknown as closed is the same silent miss arriving
  through the fix (docs/known-pitfalls.md).

The fake transport below deliberately reproduces the embed trap: a filter on an embedded
resource only DROPS rows when the select says `!inner`; without it PostgREST nulls the embedded
object and counts the row anyway. So a `count_feed` that forgot the join would come back with
the all-time number here, and the first test would fail — which is the point.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db, http
from app.auth import AuthedUser, get_current_user
from app.main import create_app

#: The fake's clock. Rows are plain ISO strings so the comparison is the same string ordering
#: PostgREST would do on a timestamptz.
NOW = "2026-09-21"

OPEN = {"state": "in_scope", "closing_at": "2026-12-01"}
CLOSED = {"state": "in_scope", "closing_at": "2026-07-04"}
NO_DEADLINE = {"state": "in_scope", "closing_at": None}
EXCLUDED_OPEN = {"state": "excluded", "closing_at": "2026-12-01"}
EXCLUDED_CLOSED = {"state": "excluded", "closing_at": "2026-01-09"}


class _CountResponse:
    """Just enough of an httpx response for `_count_matches`: the answer is in a header."""

    def __init__(self, count: int) -> None:
        self.headers = {"Content-Range": f"0-0/{count}"}
        self.content = b"[]"

    def raise_for_status(self) -> None:  # pragma: no cover - never fails here
        return None


def _postgrest(rows: list[dict], seen: list[dict] | None = None):
    """A three-clause PostgREST: workspace, state, and the open-window predicate."""

    def request(method, url, *, headers=None, params=None, timeout=None, **kw):
        if seen is not None:
            seen.append(dict(params or {}))
        kept = [r for r in rows if r["state"] == (params or {})["state"].removeprefix("eq.")]
        window = (params or {}).get("opportunities.or")
        # The trap, faithfully: without `!inner` the embedded filter nulls the embed and the
        # row survives. A count that forgot the join therefore reads as the all-time count.
        if window and "!inner" in (params or {}).get("select", ""):
            kept = [r for r in kept if r["closing_at"] is None or r["closing_at"] >= NOW]
        return _CountResponse(len(kept))

    return request


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(db, "_headers", lambda: {})
    monkeypatch.setattr(http, "note_egress", lambda *a, **k: None)


def test_the_open_count_and_the_all_time_count_differ(monkeypatch):
    """The defect, stated as a number: one closed tender and one open one is 2 all-time and 1
    open. If these two ever agree on a corpus with history, the parameter is doing nothing."""
    monkeypatch.setattr(http.client, "request", _postgrest([OPEN, CLOSED]))

    assert db.count_feed("ws-1", "in_scope", ["IN"]) == 2
    assert db.count_feed("ws-1", "in_scope", ["IN"], open_only=True) == 1


def test_a_tender_with_no_stated_deadline_counts_as_open(monkeypatch):
    """Unknown is not closed. Dropping it would be the silent miss arriving through the fix."""
    monkeypatch.setattr(http.client, "request", _postgrest([NO_DEADLINE, CLOSED]))

    assert db.count_feed("ws-1", "in_scope", ["IN"], open_only=True) == 1


def test_the_open_count_uses_the_same_predicate_as_the_feed_list(monkeypatch):
    """The tile has to describe the list. Two spellings of "open" is how a strip ends up
    naming a number nothing on screen explains (docs/known-pitfalls.md)."""
    seen: list[dict] = []
    monkeypatch.setattr(http.client, "request", _postgrest([OPEN], seen))
    db.count_feed("ws-1", "in_scope", ["IN"], open_only=True)

    assert seen[0]["opportunities.or"] == "(closing_at.is.null,closing_at.gte.now())"
    # Without this the filter is inert — see the module docstring.
    assert "opportunities!inner" in seen[0]["select"]


def test_the_all_time_count_is_unchanged(monkeypatch):
    """The existing row must keep counting history: the two rows together are the explanation,
    and an all-time tile that quietly became open-only would just move the confusion."""
    seen: list[dict] = []
    monkeypatch.setattr(http.client, "request", _postgrest([OPEN, CLOSED], seen))
    assert db.count_feed("ws-1", "in_scope", ["IN"]) == 2
    assert "opportunities.or" not in seen[0]


# --- the route: additive keys, and a swept figure derived the same way the old one is --------


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


@pytest.fixture
def feed_route(monkeypatch):
    rows = [OPEN, CLOSED, NO_DEADLINE, EXCLUDED_OPEN, EXCLUDED_CLOSED]
    monkeypatch.setattr(http.client, "request", _postgrest(rows))
    monkeypatch.setattr(db, "get_workspace_markets", lambda ws: ["IN"])
    monkeypatch.setattr(db, "get_feed", lambda *a, **k: [])
    monkeypatch.setattr(db, "count_eligible", lambda *a, **k: 0)
    monkeypatch.setattr(db, "count_comparable", lambda *a, **k: 0)
    monkeypatch.setattr(db, "count_feed_closed", lambda *a, **k: 1)
    monkeypatch.setattr(db, "last_swept_at", lambda markets: {})
    monkeypatch.setattr(db, "get_discovery_rules", lambda ws: [])
    monkeypatch.setattr(db, "get_workspace_members", lambda ws: [])
    return _client()


def test_the_route_serves_open_counts_beside_the_all_time_ones(feed_route):
    counts = feed_route.get("/api/opportunities").json()["data"]["counts"]

    # All-time, unchanged: 3 in-scope rows and 2 excluded, closed ones included.
    assert (counts["in_scope"], counts["excluded"]) == (3, 2)
    # Open now: the closed row drops from each bucket, the undated one stays in.
    assert (counts["in_scope_open"], counts["excluded_open"]) == (2, 1)


def test_swept_open_is_the_sum_of_the_two_open_buckets(feed_route):
    """`swept` on the strip has always been in_scope + excluded, computed in the browser. The
    open row is derived the same way on purpose: a second definition of "swept" beside the first
    is the confusion this change exists to remove."""
    counts = feed_route.get("/api/opportunities").json()["data"]["counts"]

    assert counts["swept_open"] == counts["in_scope_open"] + counts["excluded_open"] == 3
