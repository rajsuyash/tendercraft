"""The instrument the Free-tier decision is made from.

Supabase blocked this project's API at 12.89 GB against a 5.5 GB quota and nothing in the
engine had ever counted a byte. These tests cover the three halves of the fix: the logging
configuration that lets an INFO line exist at all, the ledger arithmetic, and the deep health
check that turns a quota block into a failing check instead of an email two days later.

The HTTP client is mocked everywhere. Production is returning 402 and must not be called.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app import cron_auth, db, http, main
from app.config import get_settings
from app.deterministic import egress
from app.envelope import ApiError
from app.main import configure_logging, create_app


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    """The suite supplies its own config.

    `config._load_dotenv` reads the repo-root `.env`, which is production — a test whose
    target depends on what happens to be on the developer's disk is not one you can read a
    result from (docs/known-pitfalls.md). `.invalid` is RFC 2606: nothing can resolve it, so
    an unmocked request fails loudly instead of reaching a real project.
    """
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://engine-unit-tests.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_JWT", "test-service-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

# --- logging configuration ------------------------------------------------------------


def _emit(capsys, level_name: str, message: str) -> list[dict]:
    """Log one line through the real logger and return whatever reached stdout, parsed."""
    configure_logging()
    getattr(logging.getLogger("tendercraft.engine"), level_name)(message)
    out = capsys.readouterr().out.strip()
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def test_info_from_the_engine_logger_is_emitted_at_the_default_level(monkeypatch, capsys):
    """The defect this fixes: root sat at WARNING, so no application INFO ever shipped."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    lines = _emit(capsys, "info", "hello from the engine")
    assert [line["message"] for line in lines] == ["hello from the engine"]
    assert lines[0]["severity"] == "INFO"  # Cloud Logging reads this key, not the text
    assert lines[0]["logger"] == "tendercraft.engine"


def test_log_level_warning_drops_info_and_still_emits_warning(monkeypatch, capsys):
    """The other side of the check: a configured level that filters must still let its own
    level through, or 'nothing was logged' and 'logging is broken' look identical."""
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    assert _emit(capsys, "info", "suppressed") == []
    warned = _emit(capsys, "warning", "still here")
    assert [line["severity"] for line in warned] == ["WARNING"]


def test_an_unreadable_log_level_falls_back_to_info(monkeypatch, capsys):
    monkeypatch.setenv("LOG_LEVEL", "getLogger")  # a real attribute of the logging module
    assert [line["message"] for line in _emit(capsys, "info", "kept")] == ["kept"]


def test_extra_fields_and_exceptions_are_carried_into_the_json(monkeypatch, capsys):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    log = logging.getLogger("tendercraft.engine")
    log.info("supabase egress", extra={"fields": {"table": "opportunities", "bytes": 12}})
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("unhandled error")
    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert lines[0]["table"] == "opportunities" and lines[0]["bytes"] == 12
    assert "ValueError: boom" in lines[1]["exception"]


def test_httpx_request_logging_stays_off(monkeypatch, capsys):
    """Turning the root logger on turns httpx's own per-request INFO on with it.

    Found by running the real path rather than a test: every ledger line arrived twice, the
    duplicate spelling out the full query string (workspace ids, filters) and costing a second
    billed log line for information the ledger already reports.
    """
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    logging.getLogger("httpx").info("HTTP Request: GET https://…?workspace_id=eq.w1")
    assert capsys.readouterr().out == ""


def test_configure_logging_leaves_foreign_handlers_alone(monkeypatch):
    """pytest's caplog installs a root handler; clobbering it stops every other test capturing."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    root = logging.getLogger()
    foreign = logging.NullHandler()
    root.addHandler(foreign)
    try:
        configure_logging()
        configure_logging()  # idempotent: ours is replaced, not stacked
        assert foreign in root.handlers
        assert len([h for h in root.handlers if getattr(h, "_tendercraft", False)]) == 1
    finally:
        root.removeHandler(foreign)


# --- ledger arithmetic (deterministic/egress.py) ---------------------------------------

DAY = date(2026, 9, 17)


def test_bytes_are_attributed_to_the_table_and_the_route():
    ledger = egress.new_ledger(DAY)
    ledger = egress.record(ledger, day=DAY, table="opportunities", route="cron:sweep", nbytes=100)
    ledger = egress.record(ledger, day=DAY, table="opportunities", route="cron:sweep", nbytes=50)
    ledger = egress.record(ledger, day=DAY, table="criteria", route="GET /api/x", nbytes=7)
    assert ledger.calls == 3 and ledger.total_bytes == 157
    assert ledger.by_table == {"opportunities": 150, "criteria": 7}
    assert ledger.by_route == {"cron:sweep": 150, "GET /api/x": 7}


def test_the_ledger_rolls_over_at_utc_midnight():
    ledger = egress.record(egress.new_ledger(DAY), day=DAY, table="t", route="r", nbytes=9)
    rolled = egress.record(ledger, day=date(2026, 9, 18), table="t", route="r", nbytes=1)
    assert (rolled.day, rolled.calls, rolled.total_bytes) == (date(2026, 9, 18), 1, 1)
    assert rolled.by_table == {"t": 1}  # yesterday's 9 bytes do not follow it over


def test_recording_does_not_mutate_the_ledger_it_was_given():
    first = egress.record(egress.new_ledger(DAY), day=DAY, table="t", route="r", nbytes=4)
    egress.record(first, day=DAY, table="t", route="r", nbytes=4)
    assert first.by_table == {"t": 4} and first.total_bytes == 4


def test_an_unnamed_bucket_is_recorded_rather_than_dropped():
    ledger = egress.record(egress.new_ledger(DAY), day=DAY, table="", route="", nbytes=3)
    assert ledger.by_table == {egress.UNKNOWN_KEY: 3}
    assert ledger.by_route == {egress.UNKNOWN_KEY: 3}


def test_the_bucket_maps_are_bounded():
    """A dict appended to on every DB call, in a container that runs for days, is a leak."""
    ledger = egress.new_ledger(DAY)
    for i in range(egress.MAX_BUCKETS + 20):
        ledger = egress.record(ledger, day=DAY, table=f"t{i}", route="r", nbytes=1)
    assert len(ledger.by_table) == egress.MAX_BUCKETS + 1  # the named overflow bucket
    assert ledger.by_table[egress.OVERFLOW_KEY] == 20
    assert ledger.total_bytes == egress.MAX_BUCKETS + 20  # nothing is lost, only merged


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/api/dashboard", "GET /api/dashboard"),
        ("POST", "/api/tenders/3f2a1b4c-5d6e-4f70-8a91-b2c3d4e5f607/lock",
         "POST /api/tenders/{id}/lock"),
        ("GET", "/api/proposals/42", "GET /api/proposals/{id}"),
        ("POST", "/internal/cron/sweep", "POST /internal/cron/sweep"),
        ("GET", "/", "GET /"),
    ],
)
def test_route_labels_collapse_identifiers(method, path, expected):
    """One bucket per tender would be exactly the unbounded growth MAX_BUCKETS guards."""
    assert egress.route_label(method, path) == expected


@pytest.mark.parametrize(
    ("path", "table"),
    [("opportunities", "opportunities"), ("criteria?select=id", "criteria"), ("", "unknown")],
)
def test_table_of(path, table):
    assert egress.table_of(path) == table


def test_summary_ranks_the_biggest_consumer_first():
    ledger = egress.new_ledger(DAY)
    ledger = egress.record(ledger, day=DAY, table="small", route="r", nbytes=1)
    ledger = egress.record(ledger, day=DAY, table="huge", route="r", nbytes=900)
    ledger = egress.record(ledger, day=DAY, table="mid", route="r", nbytes=50)
    out = egress.summary(ledger)
    assert out["day"] == "2026-09-17" and out["calls"] == 3 and out["bytes"] == 951
    assert list(out["by_table"]) == ["huge", "mid", "small"]


# --- the wiring: _rest counts, the middleware attributes -------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code, self.content, self.text = status_code, body, body.decode()
        self.headers: dict[str, str] = {}

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)  # type: ignore[arg-type]


@pytest.fixture
def ledger_reset():
    http.reset_egress()
    yield
    http.reset_egress()


def test_rest_records_the_response_bytes_against_its_table(monkeypatch, ledger_reset):
    body = json.dumps([{"id": "1"}]).encode()
    monkeypatch.setattr(http.client, "request", lambda *a, **k: _FakeResponse(200, body))
    monkeypatch.setattr(db, "_headers", lambda: {})
    db._rest("GET", "opportunities", params={"select": "id"})
    snap = http.egress_snapshot()
    assert snap["calls"] == 1 and snap["bytes"] == len(body)
    assert snap["by_table"] == {"opportunities": len(body)}


def test_a_blocked_query_is_still_counted(monkeypatch, ledger_reset):
    """A 402 body is egress too, and a quota block is the run you most want on the ledger."""
    monkeypatch.setattr(http.client, "request", lambda *a, **k: _FakeResponse(402, b'{"m":1}'))
    monkeypatch.setattr(db, "_headers", lambda: {})
    with pytest.raises(ApiError):
        db._rest("GET", "workspaces")
    assert http.egress_snapshot()["bytes"] == 7


def test_bytes_are_attributed_to_the_requesting_route(monkeypatch, ledger_reset):
    """End to end through the middleware: the by-route table is what names the spender."""
    monkeypatch.setattr(db, "_headers", lambda: {})
    monkeypatch.setattr(
        http.client, "request", lambda *a, **k: _FakeResponse(200, b'[{"id":"1"}]')
    )
    app = create_app()

    @app.get("/api/tenders/{tender_id}/probe")
    async def _probe(tender_id: str):
        db._rest("GET", "criteria")
        return {"ok": True, "data": None, "error": None}

    TestClient(app).get("/api/tenders/3f2a1b4c-5d6e-4f70-8a91-b2c3d4e5f607/probe")
    assert http.egress_snapshot()["by_route"] == {
        "GET /api/tenders/{id}/probe": len(b'[{"id":"1"}]')
    }


def test_reset_egress_stamps_the_day_it_is_given(ledger_reset):
    http.reset_egress(datetime(2020, 1, 2, tzinfo=UTC))
    assert http.egress_snapshot()["day"] == "2020-01-02"


# --- the deep health check --------------------------------------------------------------


@pytest.fixture
def probe_client(monkeypatch):
    monkeypatch.setattr(db, "_headers", lambda: {"apikey": "k"})
    return TestClient(create_app(), raise_server_exceptions=False)


def test_health_stays_shallow_while_the_database_is_blocked(monkeypatch, probe_client):
    """The whole reason the two are separate: `/health` answered 200 for two days."""
    monkeypatch.setattr(http.client, "request", lambda *a, **k: _FakeResponse(402, b"{}"))
    assert probe_client.get("/health").status_code == 200


def test_deep_health_reports_a_402_as_unhealthy(monkeypatch, probe_client):
    monkeypatch.setattr(http.client, "request", lambda *a, **k: _FakeResponse(402, b"{}"))
    r = probe_client.get("/health/deep")
    assert r.status_code == 503
    assert r.json()["ok"] is False
    assert r.json()["error"]["code"] == "DB_UNHEALTHY"
    assert "402" in r.json()["error"]["message"]


def test_deep_health_reports_a_200_as_healthy(monkeypatch, probe_client):
    monkeypatch.setattr(http.client, "request", lambda *a, **k: _FakeResponse(200, b"[]"))
    r = probe_client.get("/health/deep")
    assert r.status_code == 200
    assert r.json()["data"] == {"status": "healthy", "upstream_status": 200}


def test_deep_health_survives_a_transport_failure(monkeypatch, probe_client):
    def boom(*a, **k):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(http.client, "request", boom)
    r = probe_client.get("/health/deep")
    assert r.status_code == 503 and "no route to host" in r.json()["error"]["message"]


def test_deep_health_without_a_service_key_is_unhealthy_not_a_crash(monkeypatch):


    def no_key():
        raise ApiError(500, "ENGINE_MISCONFIGURED", "service key not configured")

    monkeypatch.setattr(db, "_headers", no_key)
    r = TestClient(create_app()).get("/health/deep")
    assert r.status_code == 503 and r.json()["error"]["code"] == "DB_UNHEALTHY"


# --- cron/health carries the ledger -----------------------------------------------------

AUDIENCE = "https://engine.test"
CALLER = "scheduler@proj.iam.gserviceaccount.com"


@pytest.fixture
def cron(monkeypatch):
    """The same symmetric-key stand-in for Google's JWKS that tests/test_cron.py uses."""
    monkeypatch.setenv("CRON_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("CRON_SERVICE_ACCOUNTS", CALLER)
    monkeypatch.setattr(
        cron_auth, "_jwks_client",
        lambda: type("K", (), {"get_signing_key_from_jwt":
                               lambda self, t: type("S", (), {"key": "secret"})()})(),
    )
    real = jwt.decode

    def decode(token, key, **kw):
        kw["algorithms"] = ["HS256"]
        return real(token, key, **kw)

    monkeypatch.setattr(jwt, "decode", decode)
    monkeypatch.setattr(db, "list_notifying_workspaces", lambda: ["w1"])
    monkeypatch.setattr(db, "list_watching_workspaces", lambda: [])
    monkeypatch.setattr(db, "_headers", lambda: {"apikey": "k"})
    token = jwt.encode(
        {"aud": AUDIENCE, "iss": "https://accounts.google.com", "email": CALLER,
         "email_verified": True, "exp": 9_999_999_999},
        "secret", algorithm="HS256",
    )
    return TestClient(create_app()), {"Authorization": f"Bearer {token}"}


def test_cron_health_reports_the_ledger_and_the_probe(monkeypatch, cron, ledger_reset):
    client, auth = cron
    monkeypatch.setattr(http.client, "request", lambda *a, **k: _FakeResponse(200, b"[]"))
    r = client.get("/internal/cron/health", headers=auth)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["caller"] == CALLER and data["database"]["healthy"] is True
    # The probe's own read is on the ledger: the instrument counts itself.
    assert data["egress"]["by_table"] == {"workspaces": 2}
    assert data["notifying_workspaces"] == 1 and data["watching_workspaces"] == 0


def test_cron_health_fails_the_check_when_the_database_is_blocked(monkeypatch, cron):
    client, auth = cron
    monkeypatch.setattr(http.client, "request", lambda *a, **k: _FakeResponse(402, b"{}"))
    r = client.get("/internal/cron/health", headers=auth)
    assert r.status_code == 503  # the scheduler's failure count is the alarm
    assert r.json()["error"]["code"] == "DB_UNHEALTHY"
    assert r.json()["data"]["egress"]["calls"] >= 1  # the payload survives the failure


def test_cron_health_still_refuses_an_unauthenticated_caller(monkeypatch, cron):
    client, _ = cron
    monkeypatch.setattr(main, "_probe_database", lambda: pytest.fail("probed before auth"))
    assert client.get("/internal/cron/health").status_code in (401, 403)
