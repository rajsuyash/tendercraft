"""The forwarded-email webhook: signature, tenant routing, and at-least-once delivery.

This endpoint writes rows into a named tenant on the say-so of an HTTP request, so the tests
that matter are the refusals and the duplicate handling. `test_inbound.py` covers the parsing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import db, inbound_routes
from app.main import create_app

SECRET = "s3cr3t-shared-with-the-mail-provider"
TOKEN = "a1b2c3d4e5f6"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DISCOVERY_INBOUND_SECRET", SECRET)
    return TestClient(create_app())


@pytest.fixture
def store(monkeypatch):
    """A workspace that owns TOKEN, and capture of everything written."""
    state = {"messages": [], "actions": [], "digests": set()}

    monkeypatch.setattr(db, "get_workspace_by_inbound_token",
                        lambda t: {"id": "ws-1", "name": "Usha Martin"} if t == TOKEN else None)
    monkeypatch.setattr(db, "find_opportunity_by_ref", lambda ws, ref: None)

    # These stubs mirror the real db functions, which merge workspace_id into the row before
    # writing. A stub that returns a different shape from the query it replaces is an
    # assumption about another file, and the suite then proves only that the stub agrees with
    # itself (docs/known-pitfalls.md, "Answer reuse").
    def record(ws, msg):
        if msg["content_digest"] in state["digests"]:
            return None
        state["digests"].add(msg["content_digest"])
        row = {**msg, "workspace_id": ws, "id": f"msg-{len(state['messages'])}"}
        state["messages"].append(row)
        return row

    def create(ws, action):
        row = {**action, "workspace_id": ws, "id": f"act-{len(state['actions'])}"}
        state["actions"].append(row)
        return row

    monkeypatch.setattr(db, "record_inbound_message", record)
    monkeypatch.setattr(db, "create_bid_action", create)
    return state


def post(client, payload: dict, *, secret: str = SECRET, header: str | None = None):
    raw = json.dumps(payload).encode()
    sig = header if header is not None else hmac.new(
        secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/inbound/email", content=raw,
                       headers={"X-TenderCraft-Signature": sig,
                                "Content-Type": "application/json"})


#: A deadline a week out, not a fixed date. The parser will not raise an action for a date
#: that has already passed, so a hardcoded one turns this suite red on the morning after it
#: expires — which happened, and a permanently-failing test stops being read as a signal.
_DUE = date.today() + timedelta(days=7)


def mail(**over) -> dict:
    return {"to": f"{TOKEN}@inbound.tendercraft.test",
            "from": "noreply@gem.gov.in",
            "subject": "Clarification sought on your bid",
            "text": f"Submit the following documents by {_DUE:%d-%m-%Y} "
                    "for GEM/2026/B/7876746.",
            **over}


# ---------- the boundary ----------

def test_an_unsigned_request_is_refused(client, store):
    assert post(client, mail(), header="").status_code == 401
    assert store["messages"] == []


def test_a_wrong_signature_is_refused(client, store):
    r = post(client, mail(), secret="not-the-secret")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_SIGNATURE"
    assert store["messages"] == []


def test_the_signature_covers_the_body_not_just_the_route(client, store):
    """Signed one payload, sent another — the classic replay-with-edits. The HMAC is over the
    RAW bytes precisely so a re-serialised body cannot pass."""
    raw = json.dumps(mail()).encode()
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    tampered = json.dumps(mail(to="attacker@inbound.tendercraft.test")).encode()

    r = client.post("/api/inbound/email", content=tampered,
                    headers={"X-TenderCraft-Signature": sig,
                             "Content-Type": "application/json"})

    assert r.status_code == 401
    assert store["messages"] == []


def test_a_prefixed_signature_is_accepted(client, store):
    """Providers differ on `sha256=…`. Rejecting that spelling would push reformatting into a
    vendor adapter that may not control the header."""
    raw = json.dumps(mail()).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    r = client.post("/api/inbound/email", content=raw,
                    headers={"X-TenderCraft-Signature": sig,
                             "Content-Type": "application/json"})
    assert r.status_code == 200


def test_missing_secret_fails_closed(monkeypatch, store):
    """A forgotten env var must not become an open endpoint that writes into a named tenant."""
    monkeypatch.delenv("DISCOVERY_INBOUND_SECRET", raising=False)
    r = post(TestClient(create_app()), mail())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "INBOUND_NOT_CONFIGURED"


def test_an_oversized_body_is_refused_before_it_is_parsed(client, store):
    payload = mail(text="x" * (inbound_routes.MAX_BODY_BYTES + 10))
    assert post(client, payload).status_code == 413
    assert store["messages"] == []


# ---------- tenant routing ----------

def test_an_unknown_mailbox_is_404_not_403(client, store):
    """The caller IS authenticated; it addressed a mailbox that does not exist. Distinguishing
    the two makes "we forwarded it and nothing happened" a one-look diagnosis."""
    r = post(client, mail(to="nobodyhere@inbound.tendercraft.test"))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "INBOUND_UNKNOWN_MAILBOX"


def test_the_workspace_comes_from_the_address_never_the_sender(client, store):
    """Trusting From would let anyone who learns an address file mail into that workspace by
    spoofing a header — and SPF does not survive the forwarding we ask every customer to do."""
    post(client, mail(**{"from": "attacker@evil.test"}))

    assert store["messages"][0]["workspace_id"] == "ws-1"
    assert store["messages"][0]["from_address"] == "attacker@evil.test"


def test_a_display_name_wrapped_address_still_resolves(client, store):
    """Forwarding clients rewrite To: as `Name <token@domain>`."""
    r = post(client, mail(to=f"TenderCraft <{TOKEN}@inbound.tendercraft.test>"))
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "stored"


# ---------- at-least-once delivery ----------

def test_a_retried_delivery_is_a_200_duplicate_and_raises_no_second_action(client, store):
    """Every provider retries on a non-2xx. A second action for one request makes a bidder
    respond twice to a buyer, and a non-2xx would trigger a retry storm besides."""
    first = post(client, mail())
    second = post(client, mail())

    assert first.json()["data"]["status"] == "stored"
    assert second.status_code == 200
    assert second.json()["data"] == {"status": "duplicate",
                                     "kind": "clarification_request",
                                     "action_created": False}
    assert len(store["actions"]) == 1


# ---------- what gets raised ----------

def test_a_clarification_creates_a_dated_action(client, store):
    body = post(client, mail()).json()["data"]

    assert body["action_created"] is True
    assert body["due_at"] == _DUE.isoformat()
    action = store["actions"][0]
    assert action["kind"] == "clarification_request"
    assert action["portal_ref_no"] == "GEM/2026/B/7876746"


def test_a_routine_bid_alert_creates_no_action(client, store):
    """The feed already ranks these; an action each would bury the ones carrying an obligation."""
    body = post(client, mail(subject="New bids matching your category",
                             text="3 new bids published. GEM/2026/B/7876746")).json()["data"]

    assert body["kind"] == "bid_alert"
    assert body["action_created"] is False
    assert store["actions"] == []


def test_an_unclassified_message_is_stored_even_though_it_raises_nothing(client, store):
    """The whole design premise: we have never seen a real GeM email, so "no marker matched"
    must never mean "discarded"."""
    body = post(client, mail(subject="Fwd: rope",
                             text="See attached. GEM/2026/B/7876746")).json()["data"]

    assert body["kind"] == "unclassified"
    assert body["action_created"] is False
    assert len(store["messages"]) == 1
    assert any("could not tell" in n for n in body["notes"])


def test_an_action_carries_its_caveats_into_the_summary(client, store):
    """"No deadline was readable" beside the action is the difference between a user checking
    the original mail and trusting a blank field."""
    post(client, mail(text="Please upload the following. GEM/2026/B/7876746"))

    action = store["actions"][0]
    assert action["due_at"] is None
    assert "deadline" in action["summary"]


def test_an_ambiguous_message_creates_an_unlinked_action(client, store):
    """Two tenders named: the action exists, but linking by guess would put a real deadline on
    the wrong bid."""
    post(client, mail(text="Submit the following for GEM/2026/B/7876746 and GEM/2026/B/7876747"))

    action = store["actions"][0]
    assert action["portal_ref_no"] is None
    assert action["opportunity_id"] is None
    assert "wrong tender" in action["summary"]


def test_a_malformed_body_is_a_400_not_a_500(client, store):
    raw = b"{not json"
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    r = client.post("/api/inbound/email", content=raw,
                    headers={"X-TenderCraft-Signature": sig,
                             "Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INBOUND_MALFORMED"
