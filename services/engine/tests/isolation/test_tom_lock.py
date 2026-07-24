"""A-AC5 end-to-end (live) — a TOM cannot lock while a sub-0.80 item is unconfirmed.

Exercises the real flow: create tender -> add criteria -> lock (blocked) -> confirm the
low-confidence item -> lock (succeeds). The deterministic gate is the boundary; this proves
it holds through the API against the live DB.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import requires_supabase, rest, sign_in


def _client():
    from app.main import app

    return TestClient(app)


HIGH = {
    "verbatim_text": "Average annual turnover >= Rs 10 Cr",
    "category": "eligibility",
    "requirement_level": "mandatory",
    "confidence": 0.95,
    "confirmed": True,
    "anchor_page": 12,
    "anchor_clause": "4.1(a)",
}
LOW = {
    "verbatim_text": "OEM MAF in Annexure-VII",
    "category": "eligibility",
    "requirement_level": "mandatory",
    "confidence": 0.61,
    "confirmed": False,
    "anchor_page": 22,
    "anchor_clause": "Annexure-VII",
}


@requires_supabase
def test_lock_blocked_until_low_confidence_confirmed(one_user):
    jwt = sign_in(one_user["email"], one_user["password"])
    h = {"Authorization": f"Bearer {jwt}"}
    c = _client()
    tenant_id = one_user["tenant_id"]
    tender_id = None
    try:
        r = c.post("/api/tenders", json={"title": "500 Desktops"}, headers=h)
        assert r.status_code == 200, r.text
        tender_id = r.json()["data"]["id"]

        r = c.post(f"/api/tenders/{tender_id}/criteria", json=[HIGH, LOW], headers=h)
        assert r.status_code == 200
        crits = r.json()["data"]["criteria"]
        assert len(crits) == 2
        low_id = next(x["id"] for x in crits if not x["confirmed"])

        # lock must be refused while the 0.61 item is unconfirmed (A-AC5)
        r = c.post(f"/api/tenders/{tender_id}/lock", headers=h)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "LOCK_BLOCKED"
        assert "A-AC5" in r.json()["error"]["message"]

        # confirm it, then the gate opens
        r = c.post(f"/api/criteria/{low_id}/confirm", headers=h)
        assert r.status_code == 200

        r = c.post(f"/api/tenders/{tender_id}/lock", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "locked"
    finally:
        # teardown via service role (bypasses RLS); tenant + user removed by one_user fixture
        if tender_id:
            from .conftest import SERVICE_KEY

            rest("DELETE", "criteria", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?tender_id=eq.{tender_id}")
            rest("DELETE", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{tender_id}")
        _ = tenant_id


@requires_supabase
def test_lock_blocked_on_missing_anchor(one_user):
    jwt = sign_in(one_user["email"], one_user["password"])
    h = {"Authorization": f"Bearer {jwt}"}
    c = _client()
    tender_id = None
    try:
        tender_id = c.post("/api/tenders", json={"title": "No-anchor"}, headers=h).json()["data"]["id"]
        no_anchor = {**HIGH, "anchor_page": None, "anchor_clause": None}
        c.post(f"/api/tenders/{tender_id}/criteria", json=[no_anchor], headers=h)
        r = c.post(f"/api/tenders/{tender_id}/lock", headers=h)
        assert r.status_code == 409
        assert "A-AC3" in r.json()["error"]["message"]  # unanchored criterion blocks lock
    finally:
        if tender_id:
            from .conftest import SERVICE_KEY

            rest("DELETE", "criteria", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?tender_id=eq.{tender_id}")
            rest("DELETE", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{tender_id}")
