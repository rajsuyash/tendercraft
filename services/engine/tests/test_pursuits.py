"""Pursuits (0039) — the link between a found opportunity and the bid against it.

The engine writes with the service role, which bypasses RLS, so every assertion here is about
the scope column appearing in the key and in the filter. RLS is the second line; these tests
pin the first. Cross-workspace behaviour against real policies lives in
tests/isolation/test_pursuit_isolation.py.

The stubs below take `prefer=`, which is what `db._rest` actually accepts. They used to take
`headers=` — and so did the two production calls, which `_rest` has never had a parameter for,
so `create_pursuit` and `link_pursuit_tender` raised TypeError on every real invocation while
these tests stayed green against a stub that agreed with them. `tenders._apply_pursuit_context`
swallows every exception into a log line, so nothing anywhere reported it. A stub's signature
is an assumption about a function in another file: copy it from that file.
"""

from app import db


def test_create_pursuit_scopes_the_conflict_target(monkeypatch):
    """A conflict target omitting workspace_id can reassign another workspace's row (0027)."""
    captured: dict = {}

    def _fake_rest(method, table, params=None, json=None, prefer=None):
        captured.update({"method": method, "table": table,
                         "params": params or {}, "json": json, "prefer": prefer})
        return [{"id": "p-1", "workspace_id": "ws-1", "opportunity_id": "o-1",
                 "tender_id": None, "state": "pursuing"}]

    monkeypatch.setattr(db, "_rest", _fake_rest)
    row = db.create_pursuit("ws-1", "o-1", "user-1")

    assert row["id"] == "p-1"
    assert captured["method"] == "POST"
    assert captured["table"] == "pursuits"
    assert captured["params"]["on_conflict"] == "workspace_id,opportunity_id"
    assert captured["json"]["workspace_id"] == "ws-1"
    assert captured["json"]["opportunity_id"] == "o-1"
    assert captured["json"]["created_by"] == "user-1"


def test_create_pursuit_merges_rather_than_erroring(monkeypatch):
    """Idempotency is the unique key plus this Prefer header, not a read-then-write race."""
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, prefer=None: (
            captured.update({"prefer": prefer}) or [{"id": "p-1"}]
        ),
    )
    db.create_pursuit("ws-1", "o-1", "user-1")
    assert "merge-duplicates" in (captured["prefer"] or "")


def test_create_pursuit_returns_empty_when_the_write_returns_nothing(monkeypatch):
    """PostgREST can answer with no representation; the caller must not IndexError."""
    monkeypatch.setattr(db, "_rest",
                        lambda m, t, params=None, json=None, prefer=None: [])
    assert db.create_pursuit("ws-1", "o-1", "user-1") == {}


def test_link_tender_filters_on_workspace(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, prefer=None: (
            captured.update({"method": m, "params": params or {}, "json": json})
            or [{"id": "p-1", "tender_id": "t-9", "state": "ingested"}]
        ),
    )
    db.link_pursuit_tender("ws-1", "p-1", "t-9")

    assert captured["method"] == "PATCH"
    assert captured["params"]["workspace_id"] == "eq.ws-1"
    assert captured["params"]["id"] == "eq.p-1"
    assert captured["json"]["tender_id"] == "t-9"
    # The state and the tender move together, or `pursuits_ingested_has_a_tender` is a lie
    # that happens to be satisfied.
    assert captured["json"]["state"] == "ingested"


def test_get_pursuit_is_workspace_scoped(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, prefer=None: (
            captured.update({"params": params or {}}) or []
        ),
    )
    assert db.get_pursuit("ws-1", "p-1") is None
    assert captured["params"]["workspace_id"] == "eq.ws-1"
    assert captured["params"]["id"] == "eq.p-1"


def test_get_pursuit_embeds_the_opportunity(monkeypatch):
    """The caller needs the portal reference and authority in the same round trip — the whole
    point is not making the user re-type them."""
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, prefer=None: (
            captured.update({"params": params or {}})
            or [{"id": "p-1", "opportunities": {"portal_ref_no": "GEM/2026/B/1"}}]
        ),
    )
    row = db.get_pursuit("ws-1", "p-1")
    assert "opportunities(" in captured["params"]["select"]
    assert row["opportunities"]["portal_ref_no"] == "GEM/2026/B/1"


def test_get_match_is_scoped_by_workspace_not_by_watched_markets(monkeypatch):
    """Market scope is a DISPLAY preference (see `_market_scope`); it must not decide what a
    workspace may act on. Un-ticking a country hides rows and deliberately keeps their state —
    it should not also make a tender the workspace already claimed unreachable."""
    captured: dict = {}
    monkeypatch.setattr(
        db, "_rest",
        lambda m, t, params=None, json=None, prefer=None: (
            captured.update({"params": params or {}}) or []
        ),
    )
    assert db.get_match("ws-1", "o-1") is None
    assert captured["params"]["workspace_id"] == "eq.ws-1"
    assert captured["params"]["opportunity_id"] == "eq.o-1"
    assert not any(k.startswith("opportunities.") for k in captured["params"])


# ---------- the endpoint ----------
#
# TestClient + dependency_overrides, matching tests/test_clarification_routes.py: it exercises
# the real route, the real auth dependency and the real envelope, none of which a direct call
# to the handler would touch.

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import AuthedUser, get_current_user  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


@pytest.fixture
def reader_client():
    """A member who may read but not draft."""
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u2", workspace_id="t1", role="compliance_checker",
    )
    return TestClient(app)


def test_pursue_refuses_an_opportunity_not_in_this_workspaces_feed(client, monkeypatch):
    """The corpus is shared and its ids are guessable, so a bare workspace check is not
    enough — the match row is what makes an opportunity this workspace's to act on. 404 not
    403: a distinguishable 403 confirms the row exists in someone else's feed."""
    monkeypatch.setattr(db, "get_match", lambda ws, oid: None)

    r = client.post("/api/opportunities/o-unknown/pursue")

    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_pursue_is_idempotent(client, monkeypatch):
    """A double-click is one pursuit — the unique key does it, this asserts it."""
    monkeypatch.setattr(db, "get_match", lambda ws, oid: {"opportunity_id": oid})
    monkeypatch.setattr(
        db, "create_pursuit",
        lambda ws, oid, uid: {"id": "p-1", "opportunity_id": oid, "state": "pursuing"},
    )

    first = client.post("/api/opportunities/o-1/pursue").json()
    second = client.post("/api/opportunities/o-1/pursue").json()

    assert first["ok"] is True
    assert first["data"]["id"] == second["data"]["id"] == "p-1"


def test_pursue_passes_the_caller_not_a_body_supplied_id(client, monkeypatch):
    """Tenant and actor come from the verified JWT, never the request (ET-6)."""
    seen: dict = {}
    monkeypatch.setattr(db, "get_match", lambda ws, oid: {"opportunity_id": oid})
    monkeypatch.setattr(
        db, "create_pursuit",
        lambda ws, oid, uid: seen.update({"ws": ws, "oid": oid, "uid": uid}) or {"id": "p-1"},
    )

    client.post("/api/opportunities/o-1/pursue")

    assert seen == {"ws": "t1", "oid": "o-1", "uid": "u1"}


def test_pursue_refuses_a_member_who_cannot_draft(reader_client, monkeypatch):
    """Claiming a tender is a write."""
    monkeypatch.setattr(db, "get_match", lambda ws, oid: {"opportunity_id": oid})
    monkeypatch.setattr(db, "create_pursuit", lambda ws, oid, uid: {"id": "p-1"})

    r = reader_client.post("/api/opportunities/o-1/pursue")

    assert r.status_code == 403


def test_get_pursuit_route_404s_for_another_workspaces_pursuit(client, monkeypatch):
    monkeypatch.setattr(db, "get_pursuit", lambda ws, pid: None)

    r = client.get("/api/pursuits/p-foreign")

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_get_pursuit_route_returns_the_context_the_upload_screen_needs(client, monkeypatch):
    """Reference, authority, closing date and document links — the things a user would
    otherwise re-type off the portal."""
    monkeypatch.setattr(db, "get_pursuit", lambda ws, pid: {
        "id": pid, "state": "pursuing", "tender_id": None,
        "opportunities": {
            "portal_ref_no": "GEM/2026/B/7876746",
            "authority": "South Eastern Railway",
            "title": "Supply of steel wire rope",
            "closing_at": "2026-10-01T09:30:00Z",
            "document_urls": ["https://bidplus.gem.gov.in/showbidDocument/1"],
            "source_id": "gem_bidplus",
        },
    })

    body = client.get("/api/pursuits/p-1").json()

    assert body["ok"] is True
    opp = body["data"]["opportunities"]
    assert opp["portal_ref_no"] == "GEM/2026/B/7876746"
    assert opp["document_urls"] == ["https://bidplus.gem.gov.in/showbidDocument/1"]


# ---------- ingest links the pursuit ----------

from app import tenders  # noqa: E402


def _pursuit(**opp):
    """A pursuit in the shape `db.get_pursuit` actually selects — `*,opportunities(*)`."""
    base = {"portal_ref_no": "GEM/2026/B/7876746", "authority": "South Eastern Railway"}
    base.update(opp)
    return {"id": "p-1", "state": "pursuing", "opportunities": base}


def test_ingest_backfills_the_reference_the_document_omitted(monkeypatch):
    """The portal published the number. A package that does not restate it should not lose it."""
    captured: dict = {}
    monkeypatch.setattr(tenders.db, "get_pursuit", lambda ws, pid: _pursuit())
    monkeypatch.setattr(tenders.db, "set_tender_meta",
                        lambda tid, ws, num, auth, deadline=None: captured.update(
                            {"num": num, "auth": auth, "deadline": deadline}))
    linked: dict = {}
    monkeypatch.setattr(tenders.db, "link_pursuit_tender",
                        lambda ws, pid, tid: linked.update({"p": pid, "t": tid}))

    tenders._apply_pursuit_context("ws-1", "p-1", "t-1", tender_number="", authority="")

    assert captured == {"num": "GEM/2026/B/7876746", "auth": "South Eastern Railway",
                        "deadline": None}
    assert linked == {"p": "p-1", "t": "t-1"}


def test_the_document_wins_over_the_portal(monkeypatch):
    """The package is the legal artefact; the feed row is a listing ABOUT it. Document first."""
    captured: dict = {}
    monkeypatch.setattr(tenders.db, "get_pursuit", lambda ws, pid: _pursuit())
    monkeypatch.setattr(tenders.db, "set_tender_meta",
                        lambda tid, ws, num, auth, deadline=None: captured.update(
                            {"num": num, "auth": auth, "deadline": deadline}))
    monkeypatch.setattr(tenders.db, "link_pursuit_tender", lambda ws, pid, tid: None)

    tenders._apply_pursuit_context("ws-1", "p-1", "t-1",
                                   tender_number="DOC/REF/9", authority="Doc Authority")

    assert captured == {"num": "DOC/REF/9", "auth": "Doc Authority", "deadline": None}


def test_a_missing_pursuit_does_not_fail_the_upload(monkeypatch):
    """Bookkeeping must never be able to break ingest — the package is the product."""
    monkeypatch.setattr(tenders.db, "get_pursuit", lambda ws, pid: None)

    def _boom(*a, **k):
        raise AssertionError("must not link against a pursuit that could not be read")

    monkeypatch.setattr(tenders.db, "link_pursuit_tender", _boom)
    tenders._apply_pursuit_context("ws-1", "p-gone", "t-1", tender_number="", authority="")


def test_a_broken_link_write_does_not_fail_the_upload(monkeypatch):
    monkeypatch.setattr(tenders.db, "get_pursuit", lambda ws, pid: _pursuit())
    monkeypatch.setattr(tenders.db, "set_tender_meta", lambda *a, **k: None)

    def _boom(*a, **k):
        raise RuntimeError("postgrest is down")

    monkeypatch.setattr(tenders.db, "link_pursuit_tender", _boom)
    tenders._apply_pursuit_context("ws-1", "p-1", "t-1", tender_number="", authority="")


def test_nothing_is_written_when_neither_source_states_anything(monkeypatch):
    """An empty write is a wasted round trip and an update with nothing in it."""
    monkeypatch.setattr(tenders.db, "get_pursuit",
                        lambda ws, pid: _pursuit(portal_ref_no=None, authority=None))

    def _boom(*a, **k):
        raise AssertionError("set_tender_meta called with nothing to set")

    monkeypatch.setattr(tenders.db, "set_tender_meta", _boom)
    monkeypatch.setattr(tenders.db, "link_pursuit_tender", lambda ws, pid, tid: None)

    tenders._apply_pursuit_context("ws-1", "p-1", "t-1", tender_number="", authority="")


def test_a_placeholder_title_is_renamed_once_the_backfill_learns_a_number(monkeypatch):
    """B3 review defect: display_title() runs BEFORE this backfill, so a scanned package can
    be stamped "Untitled tender" and then, a moment later, gain a number and authority right
    here — without the fix, the readiness header keeps stating "no number could be read"
    while the line beneath it names the tender."""
    monkeypatch.setattr(tenders.db, "get_pursuit", lambda ws, pid: _pursuit())
    monkeypatch.setattr(tenders.db, "set_tender_meta", lambda *a, **k: None)
    monkeypatch.setattr(tenders.db, "link_pursuit_tender", lambda ws, pid, tid: None)
    renamed: dict = {}
    monkeypatch.setattr(tenders.db, "set_tender_title",
                        lambda tid, ws, title: renamed.update({"tid": tid, "title": title}))

    tenders._apply_pursuit_context("ws-1", "p-1", "t-1", tender_number="", authority="",
                                   current_title="Untitled tender")

    assert renamed == {"tid": "t-1", "title": "GEM/2026/B/7876746 · South Eastern Railway"}


def test_a_real_title_is_never_overwritten_by_the_same_backfill(monkeypatch):
    """The assertion that matters: this is what stops the placeholder fix from becoming a
    different bug — a parsed title or a human-chosen filename must survive the backfill."""
    monkeypatch.setattr(tenders.db, "get_pursuit", lambda ws, pid: _pursuit())
    monkeypatch.setattr(tenders.db, "set_tender_meta", lambda *a, **k: None)
    monkeypatch.setattr(tenders.db, "link_pursuit_tender", lambda ws, pid, tid: None)

    def _boom(*a, **k):
        raise AssertionError("set_tender_title called on a tender that already had a real title")

    monkeypatch.setattr(tenders.db, "set_tender_title", _boom)

    tenders._apply_pursuit_context("ws-1", "p-1", "t-1", tender_number="", authority="",
                                   current_title="Supply of Steel Wire Rope")


def test_the_portal_closing_date_fills_a_deadline_the_document_did_not_state(monkeypatch):
    """Six live tenders read "Deadline not recorded" while their feed rows carried closing_at."""
    captured: dict = {}
    monkeypatch.setattr(tenders.db, "get_pursuit",
                        lambda ws, pid: _pursuit(closing_at="2026-09-30T14:30:00+00:00"))
    monkeypatch.setattr(tenders.db, "set_tender_meta",
                        lambda tid, ws, num, auth, deadline=None: captured.update(
                            {"deadline": deadline}))
    monkeypatch.setattr(tenders.db, "link_pursuit_tender", lambda ws, pid, tid: None)

    tenders._apply_pursuit_context("ws-1", "p-1", "t-1", tender_number="X", authority="Y")
    assert captured["deadline"] == "2026-09-30T14:30:00+00:00"


def test_a_deadline_the_document_stated_is_not_overwritten_by_the_portal(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(tenders.db, "get_pursuit",
                        lambda ws, pid: _pursuit(closing_at="2026-09-30T14:30:00+00:00"))
    monkeypatch.setattr(tenders.db, "set_tender_meta",
                        lambda tid, ws, num, auth, deadline=None: captured.update(
                            {"deadline": deadline}))
    monkeypatch.setattr(tenders.db, "link_pursuit_tender", lambda ws, pid, tid: None)

    tenders._apply_pursuit_context("ws-1", "p-1", "t-1", tender_number="X", authority="Y",
                                   deadline="2026-09-28T13:30:00+05:30")
    assert captured["deadline"] is None


def test_upload_title_and_pursuit_id_arrive_as_multipart_form_fields(monkeypatch):
    """The upload page sends both as FORM fields. Declared as bare `str` defaults they bound as
    query parameters and were empty on every upload that ever ran — a contract only a real
    multipart request can check."""
    from fastapi.testclient import TestClient

    from app import tenders
    from app.auth import AuthedUser, get_current_user
    from app.main import create_app

    seen: dict = {}
    monkeypatch.setattr(tenders, "_process_ingest",
                        lambda ws, docs, name, pursuit: seen.update(
                            {"name": name, "pursuit": pursuit}) or {
                            "tender_id": "t-9", "pages": 1, "illegible_pages": []})
    monkeypatch.setattr(tenders, "_extract_quietly", lambda ws, t: None)
    monkeypatch.setattr(tenders, "_ocr_quietly", lambda ws, t, docs: None)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="ws-9", role="admin",
    )
    with TestClient(app) as client:
        r = client.post("/api/tenders/ingest",
                        files={"file": ("nit.pdf", b"%PDF-1.4")},
                        data={"title": "Oil India wire rope NIT", "pursuit_id": "p-1"})

    assert r.status_code == 200, r.text
    assert seen == {"name": "Oil India wire rope NIT", "pursuit": "p-1"}
