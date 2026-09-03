"""The stored-corpus side of ask 5's date window.

The query-shape tests exist because PostgREST's failure mode here is silent: two conditions on
one column expressed as two dict keys keeps only the last, so a lower bound simply vanishes and
the response is a normal-looking page of the wrong years.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import AuthedUser, get_current_user
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="w1", role="admin",
    )
    return TestClient(app)


@pytest.fixture
def captured(monkeypatch):
    """Capture the params `search_award_results` actually sends to PostgREST."""
    seen = {}

    def fake_rest(method, path, **kwargs):
        seen["method"], seen["path"] = method, path
        seen["params"] = kwargs.get("params") or {}
        return []

    monkeypatch.setattr(db, "_rest", fake_rest)
    return seen


# ---------- the query PostgREST receives ----------

def test_no_window_leaves_the_query_untouched(captured):
    """Additive: every existing caller must be unaffected."""
    db.search_award_results("wire rope", limit=60)

    assert "observed_date" not in captured["params"]
    assert "and" not in captured["params"]


def test_a_lower_bound_alone_is_a_plain_condition(captured):
    db.search_award_results("wire rope", from_date="2021-04-01")
    assert captured["params"]["observed_date"] == "gte.2021-04-01"


def test_an_upper_bound_alone_is_a_plain_condition(captured):
    db.search_award_results("wire rope", to_date="2026-03-31")
    assert captured["params"]["and"] == "(observed_date.lte.2026-03-31)"


def test_BOTH_bounds_survive_as_one_and_clause(captured):
    """The bug this guards: two `observed_date` keys in a dict keeps the LAST one, so the lower
    bound disappears and a five-year window silently becomes "everything up to 2026"."""
    db.search_award_results("wire rope", from_date="2021-04-01", to_date="2026-03-31")

    assert captured["params"]["and"] == "(observed_date.gte.2021-04-01,observed_date.lte.2026-03-31)"
    # The plain key must be GONE, not merely overridden — leaving it would send a third,
    # contradictory condition alongside the pair.
    assert "observed_date" not in captured["params"]


def test_the_window_is_applied_alongside_the_category_match(captured):
    """Both conditions survive together. The category form is taken from `postgrest_filter`
    rather than spelled out here — a copy would be a third place the matching rule lives."""
    from app.deterministic.price_history import postgrest_filter

    db.search_award_results("wire rope", from_date="2021-04-01", to_date="2026-03-31")

    assert captured["params"]["category"] == postgrest_filter("wire rope")["category"]
    assert "and" in captured["params"]


def test_the_window_is_in_the_QUERY_not_applied_after_the_limit(captured):
    """Filtering a newest-first page that was already truncated would return nothing for any
    window not touching the present — which is every window someone opens this screen for."""
    db.search_award_results("wire rope", limit=60, from_date="2021-04-01")

    assert captured["params"]["limit"] == "60"
    assert captured["params"]["observed_date"] == "gte.2021-04-01"


# ---------- the boundary ----------

def test_a_malformed_date_is_a_400_not_a_blank_filter(client, monkeypatch):
    """Coercing it to "" would silently widen the window to everything and report success."""
    monkeypatch.setattr(db, "search_award_results", lambda *a, **k: [])
    r = client.get("/api/price-history?q=rope&from_date=01-04-2021")

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_DATE"


def test_a_reversed_window_is_refused(client, monkeypatch):
    """An inverted range matches nothing, which reads on screen as "no awards in this
    category" — a wrong answer about the market rather than about the request."""
    monkeypatch.setattr(db, "search_award_results", lambda *a, **k: [])
    r = client.get("/api/price-history?q=rope&from_date=2026-01-01&to_date=2021-01-01")

    assert r.status_code == 400
    assert "after" in r.json()["error"]["message"]


def test_a_valid_window_reaches_the_query_and_is_echoed_back(client, monkeypatch):
    """Echoed so the screen can state the window it is showing — a price benchmark with an
    unstated period is not interpretable."""
    seen = {}
    monkeypatch.setattr(db, "search_award_results",
                        lambda q, limit, from_date, to_date: seen.update(
                            q=q, from_date=from_date, to_date=to_date) or [])

    body = client.get(
        "/api/price-history?q=rope&from_date=2021-04-01&to_date=2026-03-31"
    ).json()["data"]

    assert seen == {"q": "rope", "from_date": "2021-04-01", "to_date": "2026-03-31"}
    assert body["window"] == {"from": "2021-04-01", "to": "2026-03-31"}


def test_no_window_still_returns_a_window_field(client, monkeypatch):
    """Nulls rather than an absent key: the caller should not have to distinguish
    "unbounded" from "this deployment does not support windows"."""
    monkeypatch.setattr(db, "search_award_results", lambda *a, **k: [])
    body = client.get("/api/price-history?q=rope").json()["data"]
    assert body["window"] == {"from": None, "to": None}
