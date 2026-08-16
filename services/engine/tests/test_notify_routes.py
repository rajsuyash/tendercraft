"""Alert endpoints: opt-in, idempotent, and loud when configured-but-unsendable (UML ask 1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db, mailer, notify_service
from app.auth import AuthedUser, get_current_user
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


@pytest.fixture
def wired(monkeypatch):
    """A workspace with one in-scope high-relevance match and a working mailer."""
    state = {"settings": {"enabled": True, "recipients": ["ops@uml.test"],
                          "min_band": "medium", "notify_assignee": True},
             "sent": [], "ledger": [], "already": set()}
    monkeypatch.setattr(db, "get_notification_settings", lambda ws: state["settings"])
    monkeypatch.setattr(db, "get_workspace", lambda ws: {"id": ws, "name": "Usha Martin"})
    monkeypatch.setattr(db, "get_feed", lambda ws, s, limit=200, markets=None: [{
        "opportunity_id": "o1", "state": "in_scope", "relevance_band": "high",
        "eligibility": "likely_eligible",
        "opportunities": {"portal_ref_no": "GEM/2026/B/1", "title": "Wire rope, IS 2266",
                          "authority": "ONGC", "deadline": "2026-09-01T00:00:00Z",
                          "value_display": "₹1.2 Cr"},
    }])
    monkeypatch.setattr(db, "get_notified_opportunity_ids",
                        lambda ws, r, k: state["already"])
    monkeypatch.setattr(db, "record_notifications",
                        lambda ws, rows: state["ledger"].extend(rows) or len(rows))
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: None)
    monkeypatch.setattr(mailer, "is_configured", lambda: True)
    monkeypatch.setattr(notify_service, "is_configured", lambda: True)
    monkeypatch.setattr(notify_service, "send",
                        lambda to, subject, body: state["sent"].append((to, subject, body)))
    return state


def test_alerts_are_off_until_someone_turns_them_on(client, monkeypatch):
    """A product that emails people because it was deployed gets filtered to spam, after
    which every later alert is invisible too."""
    monkeypatch.setattr(db, "get_notification_settings", lambda ws: None)
    monkeypatch.setattr(mailer, "is_configured", lambda: True)
    body = client.get("/api/notifications/settings").json()["data"]
    assert body["enabled"] is False
    assert body["recipients"] == []


def test_settings_report_whether_the_deployment_can_send_at_all(client, monkeypatch):
    """Distinct from whether the workspace wants alerts — and the one that explains silence."""
    monkeypatch.setattr(db, "get_notification_settings", lambda ws: None)
    monkeypatch.setattr(mailer, "is_configured", lambda: False)
    assert client.get("/api/notifications/settings").json()["data"]["smtp_configured"] is False


def test_a_malformed_recipient_is_refused(client, monkeypatch):
    monkeypatch.setattr(db, "upsert_notification_settings", lambda ws, p, a: p)
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: None)
    r = client.put("/api/notifications/settings", json={"recipients": ["not-an-address"]})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BAD_RECIPIENT"


def test_a_dot_test_address_is_accepted(client, monkeypatch):
    """pydantic's EmailStr rejects reserved TLDs, including this repo's own fixtures."""
    saved = {}
    monkeypatch.setattr(db, "upsert_notification_settings",
                        lambda ws, p, a: saved.update(p) or p)
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: None)
    r = client.put("/api/notifications/settings", json={"recipients": ["priya@meridian.test"]})
    assert r.status_code == 200
    assert saved["recipients"] == ["priya@meridian.test"]


def test_the_digest_sends_and_records_what_it_sent(client, wired):
    data = client.post("/api/notifications/dispatch").json()["data"]
    assert data["status"] == "sent"
    assert data["sent"] == 1
    (to, subject, body) = wired["sent"][0]
    assert to == "ops@uml.test"
    assert "Usha Martin" in subject
    assert "GEM/2026/B/1" in body
    # The ledger is written AFTER the send, so a failed send is never marked delivered.
    assert wired["ledger"] == [
        {"opportunity_id": "o1", "recipient": "ops@uml.test", "kind": "digest"},
    ]


def test_a_second_dispatch_sends_nothing_new(client, wired):
    wired["already"] = {"o1"}
    data = client.post("/api/notifications/dispatch").json()["data"]
    assert data["status"] == "nothing_new"
    assert wired["sent"] == []


def test_disabled_alerts_send_nothing_and_say_so(client, wired):
    wired["settings"]["enabled"] = False
    data = client.post("/api/notifications/dispatch").json()["data"]
    assert data["status"] == "disabled"
    assert wired["sent"] == []


def test_enabled_but_unsendable_is_a_named_error_not_a_silent_zero(client, wired, monkeypatch):
    """'sent: 0' here would look identical to a quiet week. The person waiting on the alert
    has no reason to check, which is how a deadline gets missed."""
    monkeypatch.setattr(notify_service, "is_configured", lambda: False)
    r = client.post("/api/notifications/dispatch")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SMTP_NOT_CONFIGURED"


def test_one_bouncing_address_does_not_cost_the_others_their_alert(client, wired, monkeypatch):
    wired["settings"]["recipients"] = ["bounces@uml.test", "ops@uml.test"]
    delivered = []

    def _send(to, subject, body):
        if to == "bounces@uml.test":
            raise OSError("550 mailbox unavailable")
        delivered.append(to)

    monkeypatch.setattr(notify_service, "send", _send)
    data = client.post("/api/notifications/dispatch").json()["data"]
    assert delivered == ["ops@uml.test"]
    assert data["sent"] == 1


def test_assigning_a_tender_emails_the_assignee(client, wired, monkeypatch):
    """UML's ask, literally: 'circulated to the respective Zonal Heads'."""
    monkeypatch.setattr(db, "get_membership", lambda uid, ws: {"user_id": uid})
    monkeypatch.setattr(db, "set_match_flags", lambda ws, oid, p: [{"id": "m1", **p}])
    monkeypatch.setattr(db, "get_member_email", lambda ws, uid: "zonal.head@uml.test")

    r = client.patch("/api/opportunities/o1", json={"assigned_to": "u2"})
    assert r.status_code == 200
    assert r.json()["data"]["notified"] == {"emailed": True, "to": "zonal.head@uml.test"}
    assert wired["sent"][0][0] == "zonal.head@uml.test"
    assert "assigned to you" in wired["sent"][0][1]


def test_a_failed_assignment_email_never_fails_the_assignment(client, wired, monkeypatch):
    """The routing is the thing that matters; the email is a courtesy on top of it."""
    monkeypatch.setattr(db, "get_membership", lambda uid, ws: {"user_id": uid})
    monkeypatch.setattr(db, "set_match_flags", lambda ws, oid, p: [{"id": "m1", **p}])
    monkeypatch.setattr(db, "get_member_email", lambda ws, uid: "zonal.head@uml.test")
    monkeypatch.setattr(notify_service, "send",
                        lambda *a: (_ for _ in ()).throw(OSError("smtp down")))

    r = client.patch("/api/opportunities/o1", json={"assigned_to": "u2"})
    assert r.status_code == 200
    assert r.json()["data"]["notified"]["emailed"] is False


def test_a_non_member_is_never_emailed_what_this_workspace_is_bidding_on(client, wired,
                                                                        monkeypatch):
    monkeypatch.setattr(db, "get_membership", lambda uid, ws: None)
    r = client.patch("/api/opportunities/o1", json={"assigned_to": "outsider"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "NOT_A_MEMBER"
    assert wired["sent"] == []
