"""Resend's signature scheme and its two-step read.

The svix tests are mostly refusals, for the same reason as the rest of this endpoint: a
signature bug produces a 200 and looks fine.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from app import resend_inbound
from app.envelope import ApiError

SECRET = "whsec_" + base64.b64encode(b"a-shared-webhook-secret-32-bytes").decode()
NOW = 1_756_000_000


def sign(raw: bytes, msg_id: str = "msg_1", ts: int = NOW, secret: str = SECRET) -> str:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = b"%s.%s.%s" % (msg_id.encode(), str(ts).encode(), raw)
    return "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


def test_a_correctly_signed_webhook_passes():
    raw = json.dumps({"type": "email.received"}).encode()
    resend_inbound.verify_svix(raw, "msg_1", str(NOW), sign(raw), SECRET, now=NOW)


def test_a_tampered_body_is_refused():
    raw = json.dumps({"type": "email.received"}).encode()
    signature = sign(raw)
    tampered = json.dumps({"type": "email.received", "extra": True}).encode()

    with pytest.raises(ApiError) as exc:
        resend_inbound.verify_svix(tampered, "msg_1", str(NOW), signature, SECRET, now=NOW)
    assert exc.value.status == 401


def test_a_replayed_message_id_is_refused():
    """The id is inside the signed content, so replaying the body under a new id fails —
    which is the property that makes the timestamp window meaningful."""
    raw = b"{}"
    signature = sign(raw, msg_id="msg_1")

    with pytest.raises(ApiError):
        resend_inbound.verify_svix(raw, "msg_2", str(NOW), signature, SECRET, now=NOW)


def test_an_old_timestamp_is_refused_even_with_a_valid_signature():
    """Without the window a captured request stays replayable for the life of the secret."""
    raw = b"{}"
    old = NOW - resend_inbound.TIMESTAMP_TOLERANCE_S - 1

    with pytest.raises(ApiError) as exc:
        resend_inbound.verify_svix(raw, "msg_1", str(old), sign(raw, ts=old), SECRET, now=NOW)
    assert "tolerance" in exc.value.message


def test_a_non_numeric_timestamp_is_a_401_not_a_crash():
    with pytest.raises(ApiError) as exc:
        resend_inbound.verify_svix(b"{}", "msg_1", "not-a-time", "v1,x", SECRET, now=NOW)
    assert exc.value.status == 401


def test_any_signature_in_the_list_may_match():
    """Svix sends several during a secret rotation. Checking only the first breaks rotation."""
    raw = b"{}"
    header = f"v1,{base64.b64encode(b'wrong').decode()} {sign(raw)}"
    resend_inbound.verify_svix(raw, "msg_1", str(NOW), header, SECRET, now=NOW)


def test_a_secret_pasted_without_its_prefix_still_works():
    raw = b"{}"
    bare = SECRET.removeprefix("whsec_")
    resend_inbound.verify_svix(raw, "msg_1", str(NOW), sign(raw), bare, now=NOW)


# ---------- flattening the two payloads ----------

def test_the_recipient_on_our_domain_wins_over_the_first_one():
    """A GeM alert forwarded to a colleague as well as to us arrives with both addresses.
    Taking to[0] would resolve the workspace from a stranger's address and 404 the message."""
    event = {"data": {"email_id": "e1", "to": ["ops@usha.test", "abc123@inbound.aisewak.com"]}}
    body = {"subject": "Clarification", "text": "GEM/2026/B/7876746"}

    msg = resend_inbound.to_message(event, body, domain="inbound.aisewak.com")

    assert msg["to"] == "abc123@inbound.aisewak.com"
    assert msg["message_id"] == "e1"


def test_plain_text_is_preferred_over_html():
    """HTML would drag markup into phrase matching and into the evidence a human reads."""
    msg = resend_inbound.to_message(
        {"data": {"to": ["a@x.test"]}},
        {"text": "plain body", "html": "<p>markup</p>"},
        domain="x.test",
    )
    assert msg["text"] == "plain body"


def test_a_nested_sender_object_is_flattened():
    msg = resend_inbound.to_message(
        {"data": {"to": ["a@x.test"], "from": {"address": "noreply@gem.gov.in"}}},
        {}, domain="x.test",
    )
    assert msg["from"] == "noreply@gem.gov.in"


def test_a_single_string_recipient_is_accepted():
    msg = resend_inbound.to_message({"data": {"to": "a@x.test"}}, {}, domain="x.test")
    assert msg["to"] == "a@x.test"


def test_no_matching_domain_falls_back_rather_than_dropping_the_message():
    """Better to attempt delivery and 404 on an unknown mailbox than to silently discard."""
    msg = resend_inbound.to_message({"data": {"to": ["someone@elsewhere.test"]}}, {},
                                    domain="inbound.aisewak.com")
    assert msg["to"] == "someone@elsewhere.test"


def test_fetching_without_a_key_configured_fails_closed(monkeypatch):
    monkeypatch.delenv("RESEND_INBOUND_API_KEY", raising=False)
    with pytest.raises(ApiError) as exc:
        resend_inbound.fetch_received_email("e1")
    assert exc.value.code == "INBOUND_NOT_CONFIGURED"


def test_a_failed_fetch_raises_rather_than_filing_an_empty_message(monkeypatch):
    """An empty body would file as `unclassified` with no reference — which reads on screen as
    "we could not understand this email" when the truth is "we never read it"."""
    monkeypatch.setenv("RESEND_INBOUND_API_KEY", "re_test")
    monkeypatch.setattr(resend_inbound.http.client, "get",
                        lambda *a, **k: type("R", (), {"status_code": 500})())

    with pytest.raises(ApiError) as exc:
        resend_inbound.fetch_received_email("e1")
    assert exc.value.code == "INBOUND_FETCH_FAILED"
