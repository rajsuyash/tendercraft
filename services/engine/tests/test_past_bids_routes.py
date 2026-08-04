"""Past-bid ingest: the blank-form guard, mining, and outcome honesty (G-FR3)."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import db, past_bids_routes
from app.auth import AuthedUser, get_current_user
from app.main import create_app

_ANSWER = (
    "Our implementation follows a four-phase rollout with a dedicated programme manager on "
    "site, supported by engineers who have delivered comparable state-government platforms."
)


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


@pytest.fixture
def stub_db(monkeypatch):
    stored: dict = {"answers": [], "bid": None, "doc": None}
    monkeypatch.setattr(db, "insert_library_document",
                        lambda ws, doc, actor: stored.__setitem__("doc", doc) or {"id": "d1"})

    def _bid(ws, payload, actor):
        stored["bid"] = payload
        return {"id": "b1", "name": payload["name"], "outcome": payload["outcome"]}

    monkeypatch.setattr(db, "create_past_bid", _bid)

    def _answers(ws, bid_id, rows):
        stored["answers"] = rows
        return rows

    monkeypatch.setattr(db, "upsert_answers", _answers)
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: None)
    return stored


def _pdf_like(monkeypatch, text: str):
    """Bypass pypdf — this suite is about the route, not about parsing.

    The spreadsheet case below deliberately does NOT stub, so the real parser is exercised
    end to end at least once.
    """
    from app.ingest import SourcePage

    monkeypatch.setattr(
        past_bids_routes, "parse_document_pages", lambda name, data: [SourcePage(name, 1, text)],
    )


def test_a_blank_template_is_refused_before_anything_is_stored(client, monkeypatch, stub_db):
    # An unfilled form mined into the answer library later reaches a draft WITH a citation
    # attached, which is how template prose reached a real government submission.
    _pdf_like(monkeypatch, "Form 5: Letter of Proposal\n[Insert Designation] of [Company Name]")
    r = client.post(
        "/api/past-bids",
        files={"file": ("blank.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "UNFILLED_TEMPLATE"
    assert stub_db["bid"] is None and stub_db["answers"] == []


def test_a_submitted_bid_is_mined_into_answers(client, monkeypatch, stub_db):
    _pdf_like(monkeypatch, f"Form 7(c): Technical Approach and Methodology\n{_ANSWER}")
    r = client.post(
        "/api/past-bids",
        files={"file": ("nic-2025.pdf", b"%PDF-1.4", "application/pdf")},
        data={"name": "NIC 2025", "outcome": "won", "authority": "NIC"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["answers_mined"] == 1
    assert data["sections_recognised"] == ["approach_methodology"]
    assert stub_db["bid"]["outcome"] == "won"
    # The source document stays in the library so existing retrieval is unaffected.
    assert stub_db["doc"]["doc_type"] == "past_proposal"
    # A submitted bid never expires; the claims inside it do.
    assert stub_db["doc"]["valid_to"] is None


def test_an_unreadable_outcome_is_refused_rather_than_guessed(client, monkeypatch, stub_db):
    _pdf_like(monkeypatch, f"1. Methodology\n{_ANSWER}")
    r = client.post(
        "/api/past-bids",
        files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
        data={"outcome": "probably won"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_OUTCOME"


def test_a_spreadsheet_compliance_sheet_mines_row_by_row(client, monkeypatch, stub_db):
    wb = Workbook()
    ws = wb.active
    ws.title = "PQ"
    ws.append(["Requirement", "Bidder response"])
    ws.append(["Bidder shall have executed three similar works", _ANSWER])
    buf = io.BytesIO()
    wb.save(buf)

    r = client.post(
        "/api/past-bids",
        files={"file": ("pq.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"name": "PQ sheet"},
    )
    assert r.status_code == 200
    assert stub_db["answers"][0]["mined_by"] == "table"
    assert stub_db["answers"][0]["requirement_text"].startswith("Bidder shall have executed")


def test_outcome_correction_is_audited_with_the_previous_value(client, monkeypatch):
    monkeypatch.setattr(db, "get_past_bid", lambda b, ws: {"id": "b1", "outcome": "unknown"})
    monkeypatch.setattr(db, "set_past_bid_outcome", lambda *a: None)
    audits: list = []
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: audits.append(k))
    r = client.patch("/api/past-bids/b1", json={"outcome": "won"})
    assert r.status_code == 200
    assert audits[0]["before"] == {"outcome": "unknown"}
    assert audits[0]["after"] == {"outcome": "won"}
