"""What is gating the feed, and where each term came from.

The gate uses terms from three screens. Only one of them has an input box, so a user looking
at their keywords sees a subset of what is actually excluding tenders — and a term they never
typed can now exclude nothing or everything with no way to tell which.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db, spec_routes
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

@pytest.fixture(autouse=True)
def _clear_corpus_cache():
    """`spec_routes._open_corpus` is a process-global lru_cache keyed on (markets, time bucket).

    Without this, the second test in this file reads the first test's corpus and its
    monkeypatched `get_opportunities` is never called — which is the cache working exactly as
    designed, and exactly why a test that shares a process with another must clear it.
    """
    spec_routes._open_corpus.cache_clear()
    yield
    spec_routes._open_corpus.cache_clear()


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


def test_vocabulary_route_pages_the_corpus_to_exhaustion(client, monkeypatch):
    """A single `limit=RECOMPUTE_WINDOW` read silently truncated the India corpus to its
    closed-first slice until 2026-09-14 (known-pitfalls). This endpoint's whole purpose is
    catching a term that reaches nothing — it must not itself be reading a truncated corpus."""
    from app.discovery.ingest import RECOMPUTE_WINDOW

    monkeypatch.setattr(db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_keywords": ["wire rope"]}})
    monkeypatch.setattr(db, "list_workspace_categories", lambda ws, *, active_only: [])
    monkeypatch.setattr(db, "get_capability_specs", lambda ws: [])
    monkeypatch.setattr(db, "get_workspace_markets", lambda ws: ["IN"])
    monkeypatch.setattr(db, "get_discovery_rules", lambda ws: [])

    pages: list[int] = []

    def fake_get_opportunities(*, limit, markets, open_only, offset=0, **_):
        pages.append(offset)
        if offset == 0:
            return [{"id": f"o{i}", "title": "irrelevant BOQ item", "category_codes": [],
                     "authority": ""} for i in range(RECOMPUTE_WINDOW)]
        if offset == RECOMPUTE_WINDOW:
            return [{"id": "o-last", "title": "Supply of wire rope", "category_codes": [],
                     "authority": ""}]
        return []

    monkeypatch.setattr(db, "get_opportunities", fake_get_opportunities)

    body = client.get("/api/capability/vocabulary").json()["data"]

    assert pages == [0, RECOMPUTE_WINDOW], "must read a second page rather than stop at one"
    assert body["corpus_open"] == RECOMPUTE_WINDOW + 1
    assert next(t for t in body["terms"] if t["term"] == "wire rope")["reach"] == 1, \
        "the match living past the first page must still be counted"


def test_vocabulary_route_asks_for_the_narrow_projection(client, monkeypatch):
    """A silent regression to `select=*` would be invisible otherwise — the route would still
    work, just pull every column of the whole open corpus on every render for two fields."""
    monkeypatch.setattr(db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_keywords": ["wire rope"]}})
    monkeypatch.setattr(db, "list_workspace_categories", lambda ws, *, active_only: [])
    monkeypatch.setattr(db, "get_capability_specs", lambda ws: [])
    monkeypatch.setattr(db, "get_workspace_markets", lambda ws: ["IN"])
    monkeypatch.setattr(db, "get_discovery_rules", lambda ws: [])

    selects: list[str] = []

    def fake_get_opportunities(*, limit, markets, open_only, offset=0, select="*", **_):
        selects.append(select)
        return []

    monkeypatch.setattr(db, "get_opportunities", fake_get_opportunities)

    client.get("/api/capability/vocabulary")

    assert selects == ["title,category_codes"]
    fields = set(selects[0].split(","))
    # keyword_reach reads exactly these two — NOT authority, which only keyword_relevance uses
    # to demote (never promote) a band. Getting this wrong makes reach numbers silently wrong.
    assert fields == {"title", "category_codes"}


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


# ── the corpus memo ────────────────────────────────────────────────────────────────────────
#
# `/capability` is force-dynamic with no cache, so every render re-pulled the whole open
# corpus. The projection was already minimal; the repetition was not. Measured 2026-09-17
# against a 1,251-row open Indian corpus: 242,218 bytes per render, identical on the second.


def _vocabulary_stubs(monkeypatch, corpus):
    monkeypatch.setattr(db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_keywords": ["wire rope"]}})
    monkeypatch.setattr(db, "list_workspace_categories", lambda ws, *, active_only: [])
    monkeypatch.setattr(db, "get_capability_specs", lambda ws: [])
    monkeypatch.setattr(db, "get_discovery_rules", lambda ws: [])
    reads: list[dict] = []

    def fake(**kw):
        reads.append(kw)
        return corpus if kw.get("offset", 0) == 0 else []

    monkeypatch.setattr(db, "get_opportunities", fake)
    return reads


def test_a_second_render_in_the_same_window_re_reads_nothing(client, monkeypatch):
    monkeypatch.setattr(db, "get_workspace_markets", lambda ws: ["IN"])
    reads = _vocabulary_stubs(monkeypatch, [
        {"id": "o1", "title": "Supply of wire rope", "category_codes": [], "authority": ""},
    ])

    first = client.get("/api/capability/vocabulary").json()["data"]
    after_first = len(reads)
    second = client.get("/api/capability/vocabulary").json()["data"]

    assert after_first > 0, "the first render must actually read the corpus"
    assert len(reads) == after_first, "the second render must not re-read the corpus"
    assert second == first


def test_a_new_time_bucket_re_reads_the_corpus(client, monkeypatch):
    """The expiry half. A cache that never misses is a stale corpus, not a fast one — so the
    bucket has to actually change the key, in the direction that costs bytes."""
    monkeypatch.setattr(db, "get_workspace_markets", lambda ws: ["IN"])
    reads = _vocabulary_stubs(monkeypatch, [])

    now = [1_000_000]
    monkeypatch.setattr(spec_routes.time, "time", lambda: now[0])

    client.get("/api/capability/vocabulary")
    after_first = len(reads)
    now[0] += spec_routes._CORPUS_TTL_SECONDS + 1
    client.get("/api/capability/vocabulary")

    assert len(reads) > after_first, "a render past the TTL must read the corpus again"


def test_a_different_market_does_not_serve_another_markets_corpus(client, monkeypatch):
    """The key has to carry the markets. Serving France's corpus to an Indian workspace would
    report reach against tenders that workspace cannot see."""
    markets = ["IN"]
    monkeypatch.setattr(db, "get_workspace_markets", lambda ws: list(markets))
    reads = _vocabulary_stubs(monkeypatch, [])

    client.get("/api/capability/vocabulary")
    after_first = len(reads)
    markets[:] = ["FR"]
    client.get("/api/capability/vocabulary")

    assert len(reads) > after_first, "a different market must not hit the cached corpus"
    assert reads[-1]["markets"] == ["FR"], "the market must reach the query, not just the key"


def test_terms_are_not_cached_so_an_edit_shows_immediately(client, monkeypatch):
    """The corpus is memoised; reach is not. A user editing their keywords is the entire point
    of this screen, and a cached answer there would make the feature look broken."""
    monkeypatch.setattr(db, "get_workspace_markets", lambda ws: ["IN"])
    _vocabulary_stubs(monkeypatch, [
        {"id": "o1", "title": "Supply of wire rope", "category_codes": [], "authority": ""},
    ])

    first = client.get("/api/capability/vocabulary").json()["data"]
    assert [t["term"] for t in first["terms"]] == ["wire rope"]

    monkeypatch.setattr(db, "get_profile_context", lambda ws: {"legal_identity": {
        "capability_keywords": ["left-handed spanner"]}})
    second = client.get("/api/capability/vocabulary").json()["data"]

    assert [t["term"] for t in second["terms"]] == ["left-handed spanner"]
    assert second["terms"][0]["reach"] == 0
