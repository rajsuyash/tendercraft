"""The forwarded-email webhook — UML ask 4's other half, and ask 1's acquisition half.

A customer sets one mail rule: forward GeM to `<token>@<DISCOVERY_INBOUND_DOMAIN>`. That is the
entire integration, and it is the only route to a post-technical-evaluation document request
that does not require holding their GeM password (G-1) or automating a login (G-8).

**Provider-agnostic on purpose.** `docs/discovery/PRD.md` has carried "inbound email provider
choice" as a *blocking* TODO since 2026-08-07 — blocking two of a design partner's five asks on
a procurement decision. It is not a blocking decision if the contract is ours: this endpoint
verifies an HMAC-SHA256 of the raw body against `DISCOVERY_INBOUND_SECRET`. Cloudflare Email
Routing, SES, Mailgun and a five-line Worker can all produce that. Choosing a vendor is now a
small adapter in front of a tested endpoint rather than a prerequisite to writing one.

**Why HMAC over the RAW body and not the parsed fields.** A signature over re-serialised JSON
verifies our own serialiser, not the sender: key order, unicode escaping and float formatting
all vary, so the check either fails constantly or gets loosened until it proves nothing.

**Authenticated ≠ trusted.** A valid signature proves the mail came through our provider. It
says nothing about who wrote the email — anyone can send to a GeM seller. So the body stays
untrusted input (G-6) all the way through: `deterministic/inbound.py` matches and counts, no
model sees it, no URL in it is followed, and nothing it says can create anything other than a
row a human then reads.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from starlette.concurrency import run_in_threadpool

from . import db
from .auth import AuthedUser, get_current_user
from .deterministic.inbound import CLARIFICATION, STAGE_NOTICE, classify
from .envelope import ApiError, ok

log = logging.getLogger(__name__)

CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]

router = APIRouter()

#: A forwarded mail thread with attachments inlined gets large, and this endpoint is reachable
#: by anyone holding the secret. Cap the body rather than discover the limit as a memory spike.
MAX_BODY_BYTES = 2 * 1024 * 1024

#: Stored body cap. The full email is evidence and is kept, but a 2 MB quoted thread in a
#: database column is a page-load cost paid on every render of the actions list.
MAX_STORED_BODY = 200_000


def _verify(raw: bytes, signature: str | None) -> None:
    """Constant-time HMAC check. Unset secret fails CLOSED.

    The alternative default — accept everything when unconfigured — turns a forgotten
    environment variable into an open endpoint that writes rows into a named tenant, and
    nothing about a 200 response would look wrong.
    """
    secret = os.environ.get("DISCOVERY_INBOUND_SECRET", "").strip()
    if not secret:
        raise ApiError(503, "INBOUND_NOT_CONFIGURED",
                       "inbound email is not configured on this deployment "
                       "(DISCOVERY_INBOUND_SECRET)")
    if not signature:
        raise ApiError(401, "INVALID_SIGNATURE", "missing signature header")

    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    # Providers differ on whether they prefix the algorithm; accept both spellings rather than
    # make the vendor adapter reformat a header it may not control.
    offered = signature.split("=", 1)[1] if "=" in signature else signature
    if not hmac.compare_digest(expected, offered.strip().lower()):
        raise ApiError(401, "INVALID_SIGNATURE", "signature does not match")


def _local_part(address: str) -> str:
    """The token from `token@domain`, tolerant of `Name <token@domain>`."""
    cleaned = (address or "").strip().strip(">").split("<")[-1]
    return cleaned.split("@", 1)[0].strip().lower()


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(p or "" for p in parts).encode()).hexdigest()


@router.post("/api/inbound/email")
async def inbound_email(
    request: Request,
    x_tendercraft_signature: str | None = Header(default=None),
) -> dict:
    """Accept one forwarded email, file it, and raise an action if it asks for something.

    Returns 200 for a duplicate as well as a new message: every provider retries on a non-2xx,
    and a retry storm against a signature-verified endpoint is worse than the duplicate it is
    trying to avoid. The response says which happened.
    """
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ApiError(413, "INBOUND_TOO_LARGE",
                       f"message exceeds {MAX_BODY_BYTES} bytes")
    _verify(raw, x_tendercraft_signature)

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001 — a malformed body is the sender's fault, not a 500
        raise ApiError(400, "INBOUND_MALFORMED", "body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ApiError(400, "INBOUND_MALFORMED", "body must be a JSON object")

    to_address = str(payload.get("to") or "")
    token = _local_part(to_address)
    if not token:
        raise ApiError(400, "INBOUND_NO_RECIPIENT", "no deliverable 'to' address in payload")

    subject = str(payload.get("subject") or "")[:500]
    body_text = str(payload.get("text") or payload.get("body") or "")[:MAX_STORED_BODY]
    from_address = str(payload.get("from") or "")[:320]
    provider_id = (str(payload.get("message_id") or "").strip() or None)

    def work() -> dict:
        workspace = db.get_workspace_by_inbound_token(token)
        if workspace is None:
            # 404 rather than 403: the caller IS authenticated, it simply addressed a mailbox
            # that does not exist. Distinguishing them is what makes "we forwarded it and
            # nothing happened" a one-look diagnosis instead of a support thread.
            raise ApiError(404, "INBOUND_UNKNOWN_MAILBOX",
                           "no workspace owns that forwarding address")
        workspace_id = workspace["id"]

        parsed = classify(subject, body_text, today=datetime.now(UTC).date())
        stored = db.record_inbound_message(workspace_id, {
            "delivered_to": to_address[:320],
            "from_address": from_address,
            "subject": subject,
            "body_text": body_text,
            "provider_message_id": provider_id,
            "content_digest": _digest(to_address, from_address, subject, body_text),
            "kind": parsed.kind,
            "matched_phrases": list(parsed.matched),
            "bid_refs": list(parsed.bid_refs),
        })
        if stored is None:
            return {"status": "duplicate", "kind": parsed.kind, "action_created": False}

        action = _raise_action(workspace_id, stored["id"], parsed)
        return {
            "status": "stored",
            "message_id": stored["id"],
            "kind": parsed.kind,
            "bid_refs": list(parsed.bid_refs),
            "action_created": action is not None,
            "due_at": action["due_at"] if action else None,
            "notes": list(parsed.notes),
        }

    return ok(await run_in_threadpool(work))


def _raise_action(workspace_id: str, message_id: str, parsed) -> dict | None:  # noqa: ANN001
    """Create the thing a human must do, for the two classes that imply one.

    A bid alert creates nothing: it is a feed item, the feed already ranks, and an action per
    alert would bury the two classes that carry a real obligation. An unclassified message
    creates nothing either — but it is stored and listed, so it is still seen.
    """
    if parsed.kind not in (CLARIFICATION, STAGE_NOTICE):
        return None

    ref = parsed.primary_ref
    linked = db.find_opportunity_by_ref(workspace_id, ref) if ref else None

    summary = (
        "GeM has asked for additional documents or clarification on this bid."
        if parsed.kind == CLARIFICATION else
        "GeM sent an evaluation update for this bid."
    )
    if parsed.notes:
        # The caveats travel with the action. A user reading "no deadline was readable" beside
        # the action is the difference between checking the original mail and trusting a blank.
        summary = f"{summary} {' '.join(parsed.notes)}"

    return db.create_bid_action(workspace_id, {
        "opportunity_id": linked["opportunity_id"] if linked else None,
        "portal_ref_no": ref,
        "source_message": message_id,
        "kind": parsed.kind,
        "summary": summary[:1000],
        "due_at": parsed.due_at.isoformat() if isinstance(parsed.due_at, date) else None,
    })


@router.get("/api/bid-actions")
async def list_bid_actions(user: CurrentUser) -> dict:
    """Open actions for the caller's workspace — what GeM is waiting on from this bidder."""
    return ok({"actions": await run_in_threadpool(db.get_open_bid_actions, user.workspace_id)})
