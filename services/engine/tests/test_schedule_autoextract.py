"""Extraction must run on its own, and must never be able to break an upload.

Measured 2026-09-14: the extractor works — nine correctly typed parameters out of a real rope
line, zero out of "Bidder shall submit test certificates" — and had produced nothing in
production because it sat behind a button on a screen nobody opened. `docs/known-pitfalls.md`
already records the shape: a feature reachable only by a button is a feature that silently
stops.

It runs in the BACKGROUND, not inside the request. `POST /api/tenders/ingest` awaits
`_process_ingest` in a threadpool, so the user is waiting on it; 48 model calls added there
turns a slow upload into a timeout.
"""

from __future__ import annotations

from app import tenders


def test_ingest_schedules_extraction_as_a_background_task(monkeypatch):
    scheduled: list[tuple] = []

    class FakeBackground:
        def add_task(self, fn, *args, **kwargs):
            scheduled.append((fn, args, kwargs))

    monkeypatch.setattr(tenders, "_process_ingest",
                        lambda ws, docs, name, pursuit: {"tender_id": "t-1"})

    tenders._schedule_extraction(FakeBackground(), "ws-1", "t-1")

    assert len(scheduled) == 1, "extraction must be queued, not run inline"
    assert scheduled[0][1] == ("ws-1", "t-1")


def test_background_extraction_swallows_its_own_failure(monkeypatch, caplog):
    # An upload that succeeded must not be reported as failed because a later, optional read
    # of the schedule fell over. Same reasoning as harvest_quietly on the export path.
    #
    # And it must leave the tender UNSTAMPED: a read that raised did not happen, so NULL is
    # the true value and a stamp would assert one that did not. A try/finally around the
    # stamp would break exactly this, which is why the stamp sits inside the try.
    stamped: list[tuple] = []

    def boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(tenders.db, "get_line_items", boom)
    monkeypatch.setattr(tenders.db, "mark_specs_extracted",
                        lambda ws, t: stamped.append((ws, t)))

    tenders._extract_quietly("ws-1", "t-1")  # must not raise

    assert stamped == [], "a read that failed must not be recorded as a read that happened"


def test_background_extraction_stamps_the_tender(monkeypatch):
    stamped: list[tuple] = []
    monkeypatch.setattr(tenders.db, "get_line_items",
                        lambda t, w: [{"id": "l1", "description": "Steel Wire Rope 20mm"}])
    monkeypatch.setattr(tenders.spec_service, "extract_schedule",
                        lambda ws, items, **k: {"distinct": 1, "read": 1, "skipped": 0,
                                                "populated": 1})
    monkeypatch.setattr(tenders.db, "mark_specs_extracted",
                        lambda ws, t: stamped.append((ws, t)))

    tenders._extract_quietly("ws-1", "t-1")

    assert stamped == [("ws-1", "t-1")]


def test_a_partial_read_does_not_stamp_the_tender(monkeypatch):
    # A schedule bigger than the extraction budget reads only part of it. Stamping anyway would
    # tell the fit screen "these lines state no specification" about lines nobody read.
    stamped: list[tuple] = []
    monkeypatch.setattr(tenders.db, "get_line_items",
                        lambda t, w: [{"id": "l1", "description": "Steel Wire Rope 20mm"}])
    monkeypatch.setattr(tenders.spec_service, "extract_schedule",
                        lambda ws, items, **k: {"distinct": 100, "read": 80, "skipped": 20,
                                                "populated": 80, "budget": 80})
    monkeypatch.setattr(tenders.db, "mark_specs_extracted",
                        lambda ws, t: stamped.append((ws, t)))

    tenders._extract_quietly("ws-1", "t-1")

    assert stamped == [], "a partial read must leave the tender unstamped"


def test_a_tender_with_no_schedule_is_stamped_too(monkeypatch):
    # "Read it, there was nothing there" is a real answer and the screen needs to be able to
    # give it. Leaving the stamp NULL would make an empty schedule permanently indistinguishable
    # from one that was never read.
    stamped: list[tuple] = []
    monkeypatch.setattr(tenders.db, "get_line_items", lambda t, w: [])
    monkeypatch.setattr(tenders.db, "mark_specs_extracted",
                        lambda ws, t: stamped.append((ws, t)))

    tenders._extract_quietly("ws-1", "t-1")

    assert stamped == [("ws-1", "t-1")]


def test_the_ingest_ROUTE_actually_runs_the_read_after_responding(monkeypatch):
    """The four tests above exercise the helpers directly, so the route could be left unwired
    and every one of them would still pass — which is precisely the failure this task exists to
    fix (a code path nothing reaches). This one goes through FastAPI: real request, real
    BackgroundTasks, and the read happens after the 200 rather than inside it."""
    from fastapi.testclient import TestClient

    from app.auth import AuthedUser, get_current_user
    from app.main import create_app

    ran: list[tuple] = []
    monkeypatch.setattr(tenders, "_process_ingest",
                        lambda ws, docs, name, pursuit: {"tender_id": "t-9", "pages": 1})
    monkeypatch.setattr(tenders, "_extract_quietly",
                        lambda ws, t: ran.append((ws, t)))

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="ws-9", role="admin",
    )
    with TestClient(app) as client:
        r = client.post("/api/tenders/ingest", files={"file": ("nit.pdf", b"%PDF-1.4")})

    assert r.status_code == 200 and r.json()["ok"] is True
    assert ran == [("ws-9", "t-9")], "ingest must queue the schedule read"


def test_a_lost_stamp_never_discards_a_completed_extraction(monkeypatch):
    """The manual button spends the model calls and persists the parameters BEFORE stamping.
    If the stamp write fails — which it does on every press until 0040 is applied — a
    propagating 502 would throw away work that actually succeeded. Losing the stamp costs a
    re-read; losing the read costs the spend that produced it."""
    from fastapi.testclient import TestClient

    from app import db, spec_service
    from app.auth import AuthedUser, get_current_user
    from app.main import create_app

    monkeypatch.setattr(db, "get_tender", lambda t, w: {"id": t})
    monkeypatch.setattr(db, "get_line_items",
                        lambda t, w: [{"id": "i1", "description": "d", "spec_parameters": []}])
    monkeypatch.setattr(db, "get_capability_specs", lambda w: [])
    monkeypatch.setattr(spec_service, "extract_schedule",
                        lambda ws, items, **k: {"distinct": 1, "read": 1, "skipped": 0,
                                                "populated": 1})

    def unstamped(*a, **k):
        raise RuntimeError("column specs_extracted_at does not exist")

    monkeypatch.setattr(db, "mark_specs_extracted", unstamped)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="ws-1", role="admin",
    )
    with TestClient(app) as client:
        r = client.post("/api/tenders/t-1/schedule/extract")

    assert r.status_code == 200, "a lost stamp must not discard a completed extraction"
    assert r.json()["data"]["populated"] == 1
