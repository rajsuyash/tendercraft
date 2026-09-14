"""What is gating the feed, and where each term came from.

The gate uses terms from three screens. Only one of them has an input box, so a user looking
at their keywords sees a subset of what is actually excluding tenders — and a term they never
typed can now exclude nothing or everything with no way to tell which.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import AuthedUser, get_current_user
from app.discovery.ingest import capability_terms
from app.main import create_app


def test_every_term_names_its_source(monkeypatch):
    from app.discovery import ingest as ing

    monkeypatch.setattr(ing.db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_statement": "We make rope.",
        "capability_keywords": ["wire rope"],
    }})
    monkeypatch.setattr(ing.db, "list_workspace_categories", lambda ws, *, active_only: [
        {"gem_name": "Wire Rope Sling", "active": True},
    ])
    monkeypatch.setattr(ing.db, "get_capability_specs", lambda ws: [
        {"label": "Wire Rope (ONGC)", "standard_ref": "IS 4521 / API Spec 9A"},
    ])

    terms = capability_terms("ws-1")

    assert [(t.term, t.source) for t in terms] == [
        ("wire rope", "typed"),
        ("Wire Rope Sling", "category"),
        ("IS 4521", "standard"),
        ("API Spec 9A", "standard"),
    ]
    assert terms[2].origin == "Wire Rope (ONGC)", "a derived term must name the row it came from"


def test_a_duplicate_keeps_the_first_spelling_and_its_source(monkeypatch):
    # The typed box wins: it is the one the user can edit, so attributing a shared term to a
    # read-only row would send them to a field they cannot change.
    from app.discovery import ingest as ing

    monkeypatch.setattr(ing.db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_keywords": ["Steel Wire Rope"]}})
    monkeypatch.setattr(ing.db, "list_workspace_categories", lambda ws, *, active_only: [
        {"gem_name": "steel wire rope", "active": True}])
    monkeypatch.setattr(ing.db, "get_capability_specs", lambda ws: [])

    terms = capability_terms("ws-1")
    assert len(terms) == 1
    assert terms[0].term == "Steel Wire Rope" and terms[0].source == "typed"


def test_the_gate_and_the_display_use_the_same_list(monkeypatch):
    """`_capability` must be built FROM `capability_terms`, not alongside it.

    Two functions deriving one vocabulary is the drift this codebase has been bitten by twice
    (the rule spec against the profile; the engine's scope against RLS). If they can disagree,
    the screen explaining an exclusion will eventually explain the wrong one.
    """
    from app.discovery import ingest as ing

    monkeypatch.setattr(ing.db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_statement": "s", "capability_keywords": ["a", "b"]}})
    monkeypatch.setattr(ing.db, "list_workspace_categories", lambda ws, *, active_only: [
        {"gem_name": "c", "active": True}])
    monkeypatch.setattr(ing.db, "get_capability_specs", lambda ws: [
        {"label": "L", "standard_ref": "IS 1"}])

    statement, keywords = ing._capability("ws-1")
    assert statement == "s"
    assert keywords == [t.term for t in capability_terms("ws-1")]


# ── the route ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


def test_vocabulary_route_reports_reach_and_gate_state(client, monkeypatch):
    monkeypatch.setattr(db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_statement": "We make rope.",
        "capability_keywords": ["wire rope", "left-handed spanner"],
    }})
    monkeypatch.setattr(db, "list_workspace_categories", lambda ws, *, active_only: [])
    monkeypatch.setattr(db, "get_capability_specs", lambda ws: [])
    monkeypatch.setattr(db, "get_workspace_markets", lambda ws: ["IN"])
    monkeypatch.setattr(db, "get_opportunities", lambda **k: [
        {"id": "o1", "title": "Supply of wire rope for cranes", "category_codes": [],
         "authority": ""},
    ])
    monkeypatch.setattr(db, "get_discovery_rules", lambda ws: [
        {"name": "Only my capability keywords", "kind": "keyword_match_required",
         "enabled": True, "spec": {}},
    ])

    body = client.get("/api/capability/vocabulary").json()

    assert body["error"] is None
    data = body["data"]
    assert data["corpus_open"] == 1
    assert data["gate_enabled"] is True

    by_term = {t["term"]: t for t in data["terms"]}
    assert by_term["wire rope"]["source"] == "typed"
    assert by_term["wire rope"]["reach"] == 1
    assert by_term["left-handed spanner"]["reach"] == 0, \
        "a term that matches nothing must report a zero, not silently disappear"


def test_vocabulary_route_reflects_a_disabled_gate(client, monkeypatch):
    monkeypatch.setattr(db, "get_profile_context", lambda ws: {"legal_identity": {}})
    monkeypatch.setattr(db, "list_workspace_categories", lambda ws, *, active_only: [])
    monkeypatch.setattr(db, "get_capability_specs", lambda ws: [])
    monkeypatch.setattr(db, "get_workspace_markets", lambda ws: ["IN"])
    monkeypatch.setattr(db, "get_opportunities", lambda **k: [])
    monkeypatch.setattr(db, "get_discovery_rules", lambda ws: [
        {"name": "Only my capability keywords", "kind": "keyword_match_required",
         "enabled": False, "spec": {}},
    ])

    body = client.get("/api/capability/vocabulary").json()

    assert body["ok"] is True
    assert body["data"]["gate_enabled"] is False
    assert body["data"]["terms"] == []
