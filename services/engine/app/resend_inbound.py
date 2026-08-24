"""Resend's half of the inbound-email contract: its signature scheme, and its two-step read.

`inbound_routes.py` was written provider-agnostic on purpose — HMAC-SHA256 over the raw body,
which any provider or a five-line Worker can produce. Resend is the provider we chose, and it
signs with **svix** instead. Rather than weaken our own check to something Resend happens to
emit, this module implements svix properly and the route accepts either. A second provider
later adds a second verifier here and changes nothing else.

**Two Resend-specific facts drove the shape of this file.**

1. **The webhook carries metadata only — never the body.** Resend documents this: attachments
   and text are fetched separately, so serverless handlers with small request limits still
   work. So receiving a webhook is not receiving an email; there is a second authenticated GET
   before there is anything to classify.
2. **The send key cannot do it.** The key already in Secret Manager is send-only and returns
   `restricted_api_key` on every read path (measured, 2026-08-24). Reading needs its own
   credential — hence `RESEND_INBOUND_API_KEY`, separate from `RESEND_API_KEY` so the alerting
   path keeps the narrower key it has always had.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any

from . import http
from .envelope import ApiError

_RESEND_API = "https://api.resend.com"

#: Svix rejects timestamps outside this window. Without it a captured request stays replayable
#: for as long as the secret lives — and the endpoint it replays writes rows into a tenant.
TIMESTAMP_TOLERANCE_S = 5 * 60


def verify_svix(raw: bytes, msg_id: str, timestamp: str, signature: str,
                secret: str, *, now: int) -> None:
    """Verify a svix-signed webhook, or raise ApiError(401).

    Svix signs `{id}.{timestamp}.{body}` — the id and timestamp are inside the signature, which
    is what makes the replay window enforceable. A scheme that signed the body alone could not
    tell a replay from the original no matter how carefully the timestamp were checked.
    """
    try:
        age = abs(now - int(timestamp))
    except (TypeError, ValueError) as exc:
        raise ApiError(401, "INVALID_SIGNATURE", "malformed webhook timestamp") from exc
    if age > TIMESTAMP_TOLERANCE_S:
        raise ApiError(401, "INVALID_SIGNATURE", "webhook timestamp outside tolerance")

    # `whsec_` prefixes a base64 secret. Tolerate its absence: the dashboard shows it with the
    # prefix, and someone will eventually paste the value without it.
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = b"%s.%s.%s" % (msg_id.encode(), timestamp.encode(), raw)
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()

    # The header carries a space-separated list so a secret can be rotated with both live.
    # Any one match is a pass; comparing only the first would break every rotation.
    for part in signature.split():
        _, _, offered = part.partition(",")
        if offered and hmac.compare_digest(expected, offered):
            return
    raise ApiError(401, "INVALID_SIGNATURE", "signature does not match")


def fetch_received_email(email_id: str) -> dict[str, Any]:
    """The body Resend's webhook deliberately left out.

    Raises rather than returning a blank on failure: an empty body would classify as
    `unclassified` with no bid reference and file a content-free row, which reads on screen as
    "an email arrived that we could not understand" when the truth is "we never read it".
    A failure here must look like a failure so the provider retries.
    """
    key = os.environ.get("RESEND_INBOUND_API_KEY", "").strip()
    if not key:
        raise ApiError(503, "INBOUND_NOT_CONFIGURED",
                       "inbound email is not configured on this deployment "
                       "(RESEND_INBOUND_API_KEY)")
    response = http.client.get(
        f"{_RESEND_API}/emails/receiving/{email_id}",
        headers={"Authorization": f"Bearer {key}"},
        timeout=15,
    )
    if response.status_code != 200:
        raise ApiError(502, "INBOUND_FETCH_FAILED",
                       f"could not read message {email_id} from the provider "
                       f"({response.status_code})")
    return response.json()


def to_message(event: dict[str, Any], body: dict[str, Any], *, domain: str) -> dict[str, str]:
    """Flatten Resend's two payloads into the shape the route already handles.

    `to` is a LIST — a GeM alert forwarded to a colleague as well as to us arrives with both
    addresses on it. Pick the one on OUR domain rather than the first: taking `to[0]` would
    resolve the workspace from a stranger's address and 404 a message we can perfectly well
    deliver.
    """
    data = {**(event.get("data") or {}), **(body or {})}

    recipients = data.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]
    ours = next((r for r in recipients if domain and domain.lower() in str(r).lower()), None)

    sender = data.get("from") or ""
    if isinstance(sender, dict):  # some payload versions nest it
        sender = sender.get("address") or sender.get("email") or ""

    return {
        "to": str(ours or (recipients[0] if recipients else "")),
        "from": str(sender),
        "subject": str(data.get("subject") or ""),
        # Prefer text/plain. HTML would drag markup into the classifier's phrase matching and
        # into the stored evidence a human reads; Resend supplies both.
        "text": str(data.get("text") or data.get("html") or ""),
        "message_id": str(data.get("email_id") or data.get("id") or ""),
    }
