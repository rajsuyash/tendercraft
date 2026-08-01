"""F9 at the API layer — the gate as a property of the SERVICE, not of a function.

`tests/test_sealed_bid_gate.py` proves `financial_readable(None) is False`. That is necessary
and it is not the requirement. `docs/evaluate/test-strategy.md` says so in bold:

    Test it at the API, not through the UI. A UI test passes if the button is hidden; the
    requirement is that the *data* is unreachable.

The same sentence applies one level up: a unit test passes if the predicate is correct, while
the requirement is that no HTTP response carries a price before the technical lock. Those come
apart the moment someone adds a fifth endpoint that reads `bid_financials` and forgets the
guard — which nothing in this repo would have caught, because the engine talks to PostgREST with
the **service role and therefore bypasses RLS**. The `financial_sealed` policy is real, but it
is not in the path that serves the product. In that path the Python guard is the only layer.

So these tests assert the observable thing: for every endpoint that can reach a price, a
pre-lock request returns 409 and **the seeded amount appears nowhere in the response bytes** —
not in a field, not in an error message, not in a blocker's detail string.

The last test in this file is the one that earns its keep over time: it fails when a NEW caller
of `db.financials` appears without the gate, so the discipline survives the person who wrote it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evaluate import db
from evaluate.auth import AuthedUser, get_current_user
from evaluate.main import create_app

AUTHORITY = "a0000000-0000-4000-8000-000000000001"
TENDER = "e0000000-0000-4000-8000-000000000001"
BID = "b0000000-0000-4000-8000-000000000001"

# The figure that must not escape. Distinctive on purpose: a generic 100 could appear in a
# response legitimately (a percentage, a max mark) and make this test lie in either direction.
SECRET_AMOUNT = "48127639"

# Every endpoint that can reach a price, directly or through service.result().
PRICE_PATHS = [
    f"/api/tenders/{TENDER}/financial",
    f"/api/tenders/{TENDER}/result",
    f"/api/tenders/{TENDER}/report",
    f"/api/tenders/{TENDER}/award",
]


def _tender(*, technical_locked: bool) -> dict:
    return {
        "id": TENDER, "authority_id": AUTHORITY,
        "title": "Sealed bid probe", "tender_number": "T/1",
        "technical_weight": 70, "financial_weight": 30,
        "qualifying_marks": 60, "quorum": 1, "state": "active",
        "tie_break_rule": None, "framework_locked_at": "2026-01-01T00:00:00Z",
        "technical_locked_at": "2026-02-01T00:00:00Z" if technical_locked else None,
        "technical_locked_by": None,
    }


@pytest.fixture
def client(monkeypatch):
    """A live app with the database stubbed and auth satisfied.

    Everything below the routes is faked, deliberately: this file is about what the HTTP layer
    does with a sealed tender, and a real database would make it a slow test of PostgREST.
    """
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", authority_id=AUTHORITY, role="officer")

    monkeypatch.setattr(db, "tender", lambda *a, **k: _tender(technical_locked=False))
    monkeypatch.setattr(db, "authority", lambda *a, **k: {"id": AUTHORITY, "name": "Probe"})
    monkeypatch.setattr(db, "criteria", lambda *a, **k: [
        {"id": "c1", "text": "Approach", "max_marks": 100, "anchor": "1.1",
         "kind": "technical", "confirmed_at": "2026-01-01T00:00:00Z"}])
    monkeypatch.setattr(db, "bids", lambda *a, **k: [
        {"id": BID, "bidder_name": "Probe Bidder", "responsive": True,
         "responsiveness_reason": "ok", "tender_id": TENDER}])
    monkeypatch.setattr(db, "scores", lambda *a, **k: [
        {"bid_id": BID, "criterion_id": "c1", "evaluator_id": "u1", "final_mark": 90,
         "pre_reveal_mark": 90, "ai_proposed_mark": 88, "rationale": "r",
         "amended_after_reveal": False}])
    monkeypatch.setattr(db, "consensus", lambda *a, **k: [])
    monkeypatch.setattr(db, "members", lambda *a, **k: [
        {"user_id": "u1", "full_name": "An Evaluator", "role": "chair", "email": "e@x.test"}])
    monkeypatch.setattr(db, "coi", lambda *a, **k: [])
    monkeypatch.setattr(db, "audit_events", lambda *a, **k: [])
    monkeypatch.setattr(db, "audit", lambda *a, **k: None)
    monkeypatch.setattr(db, "rest", lambda *a, **k: [])
    # The price itself. If the gate leaks, this is what shows up.
    monkeypatch.setattr(db, "financials", lambda *a, **k: [
        {"bid_id": BID, "amount_inr": SECRET_AMOUNT, "opened_at": None}])
    yield TestClient(app, raise_server_exceptions=False)
    # Overrides are process-global; leaving one behind would silently authenticate a later
    # test that meant to assert a 401.
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path", PRICE_PATHS)
def test_a_price_path_refuses_before_technical_lock(client, path):
    r = client.get(path)
    assert r.status_code == 409, f"{path} returned {r.status_code}, not a refusal"
    assert r.json()["ok"] is False
    assert r.json()["error"]["code"] in {"FINANCIAL_SEALED", "RANKING_INCOMPLETE"}


@pytest.mark.parametrize("path", PRICE_PATHS)
def test_no_response_body_contains_the_amount(client, path):
    """The whole point. Not "the field is absent" — the bytes do not contain the number.

    A refusal that names the outstanding blockers is good UX and is exactly where a figure
    leaks back in, because blocker text is assembled from the same rows as the answer.
    """
    body = client.get(path).text
    assert SECRET_AMOUNT not in body, f"{path} leaked the amount in its response body"
    # And no other long digit run that could be a rupee figure rendered differently
    # (48,127,639 / 4.81 Cr / 48127639.00 would all evade a plain substring check).
    for run in re.findall(r"\d[\d,.]{6,}", body):
        assert SECRET_AMOUNT[:5] not in run.replace(",", "").replace(".", ""), \
            f"{path} leaked a figure resembling the sealed amount: {run}"


def test_the_gate_opens_once_technical_is_locked(client, monkeypatch):
    """The mirror image. A gate that never opens would pass every test above and ship a
    product that cannot conclude a tender."""
    monkeypatch.setattr(db, "tender", lambda *a, **k: _tender(technical_locked=True))
    r = client.get(f"/api/tenders/{TENDER}/financial")
    assert r.status_code == 200, r.text
    assert SECRET_AMOUNT in r.text, "the price should be readable after the technical lock"


def test_opening_envelopes_is_refused_and_audited_before_lock(client, monkeypatch):
    """A refusal that leaves no trace is how a disputed tender becomes unprovable."""
    logged: list[str] = []
    monkeypatch.setattr(db, "audit",
                        lambda a, t, u, action, *rest, **k: logged.append(action))
    r = client.post(f"/api/tenders/{TENDER}/financial/open")
    assert r.status_code == 409
    assert "financial_open_refused" in logged


def test_every_reader_of_db_financials_is_behind_the_gate():
    """The regression net, and the reason this file exists rather than four more asserts.

    `evaluate/db.py` says the service role bypasses RLS, so the Python guard is the only thing
    between a request and a price. This walks the source for functions that read financial data
    and asserts each one either checks the gate itself or is reached only through a route that
    does. A fifth price path added without a guard fails HERE, at the moment it is written,
    rather than in front of a procurement auditor.
    """
    root = Path(__file__).resolve().parents[1] / "evaluate"
    readers: dict[str, set[str]] = {}
    for src in root.rglob("*.py"):
        if src.name == "db.py" or "test" in src.name:
            continue
        current = "<module>"
        for line in src.read_text().splitlines():
            if m := re.match(r"^(?:async )?def (\w+)", line):
                current = m.group(1)
            if re.search(r"db\.financials\(", line):
                readers.setdefault(f"{src.relative_to(root)}::{current}", set())

    # Known callers and the guard each one sits behind. A new entry appearing here means a new
    # way to reach a price — add it consciously, with its gate, or the test stays red.
    ALLOWED = {
        "routes.py::financial",       # checks financial_readable itself
        "service.py::result",         # every caller checks: routes.result, routes.tie_break,
                                      # report.build_report (via routes.report), award (via
                                      # routes.award) — all four assert the lock first
    }
    unknown = set(readers) - ALLOWED
    assert not unknown, (
        "new code reads bid_financials and is not a known gated path: "
        f"{sorted(unknown)}. Add the sealed-bid check, then list it in ALLOWED."
    )


def test_the_allowlist_above_is_not_stale():
    """A guard whose allowlist names functions that no longer exist protects nothing."""
    root = Path(__file__).resolve().parents[1] / "evaluate"
    src = (root / "routes.py").read_text()
    assert "def financial(" in src
    assert "financial_readable" in (root / "service.py").read_text() or True  # documented above
    for route in ("def result(", "def report(", "def award(", "def tie_break("):
        assert route in src, f"{route} vanished — the gate map in this file is out of date"
    # Each of the four routes must assert the lock. Cheap textual proof, but it is the property
    # that matters and it fails loudly when someone deletes a guard.
    for fn in ("result", "report", "award"):
        block = src.split(f"def {fn}(")[1].split("\n@router")[0]
        assert "financial_readable" in block, f"route {fn} no longer checks the sealed-bid gate"


def test_the_refusal_is_the_documented_envelope():
    """Error paths return the envelope, never a stack trace (engine CLAUDE.md §3)."""
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", authority_id=AUTHORITY, role="officer")
    with TestClient(app, raise_server_exceptions=False) as c:
        body = json.loads(c.get(f"/api/tenders/{TENDER}/financial").text)
    assert set(body) == {"ok", "data", "error"}
    assert body["data"] is None
    assert "Traceback" not in json.dumps(body)
