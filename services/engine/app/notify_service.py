"""Dispatching opportunity alerts (UML ask 1). Orchestration only — the decisions are pure.

Which tenders are worth an email lives in `deterministic/notify.py`; how an email is sent lives
in `mailer.py`. This module is the part that touches the database, and it exists to get one
ordering right:

    send, THEN record.

Recording first would mark a failed send as delivered, and the tender nobody heard about is
precisely the failure the feature exists to prevent (ET-7). Doing it this way can duplicate an
email if the process dies between the two — a duplicate is an annoyance, a silent miss is a
lost bid, and that is not a close call.

A per-recipient failure never aborts the run. Three colleagues on the digest and one bouncing
address must not cost the other two their alerts.
"""

from __future__ import annotations

import logging
import os

from . import db
from .deterministic.notify import Alertable, render_assignment, render_digest, select_for_digest
from .mailer import MailNotConfigured, is_configured, send

log = logging.getLogger(__name__)

_DEFAULT_BAND = "medium"


def _app_url() -> str:
    return os.environ.get("APP_URL", "https://tendercraft-web-eu-822379741897.europe-north1.run.app").rstrip("/")


def _flatten(match: dict) -> dict:
    """A feed row (match + embedded opportunity) as the flat shape the selector expects."""
    opp = match.get("opportunities") or {}
    return {
        "opportunity_id": match.get("opportunity_id"),
        "state": match.get("state"),
        "relevance_band": match.get("relevance_band"),
        "eligibility": match.get("eligibility"),
        "portal_ref_no": opp.get("portal_ref_no"),
        "title": opp.get("title"),
        "authority": opp.get("authority"),
        "deadline": opp.get("deadline"),
        "value_display": opp.get("value_display"),
    }


def dispatch_digest(workspace_id: str, workspace_name: str = "your workspace") -> dict:
    """Email each configured recipient the in-scope matches they have not yet been told about.

    Returns a report rather than raising on "nothing to do": a scheduler calling this hourly
    needs to distinguish "off", "configured but nothing new" and "sent 4" without parsing an
    error message.
    """
    settings = db.get_notification_settings(workspace_id) or {}
    if not settings.get("enabled"):
        return {"status": "disabled", "sent": 0, "recipients": 0}

    recipients = [r for r in (settings.get("recipients") or []) if r and "@" in r]
    if not recipients:
        return {"status": "no_recipients", "sent": 0, "recipients": 0}
    if not is_configured():
        # Enabled but unsendable is a configuration fault, and it must be loud. A "sent: 0"
        # here would look identical to a quiet week.
        raise MailNotConfigured(
            "alerts are enabled for this workspace but SMTP is not configured on this "
            "deployment — set SMTP_HOST, SMTP_USER and SMTP_PASSWORD"
        )

    matches = [_flatten(m) for m in db.get_feed(workspace_id, "in_scope", limit=200)]
    minimum = settings.get("min_band") or _DEFAULT_BAND

    sent_total, ledger = 0, []
    for recipient in recipients:
        already = db.get_notified_opportunity_ids(workspace_id, recipient, "digest")
        items = select_for_digest(matches, minimum, already)
        if not items:
            continue
        subject, body = render_digest(items, workspace_name, _app_url())
        try:
            send(recipient, subject, body)
        except Exception:  # noqa: BLE001 — one bad address must not cost the others their alert
            log.exception("digest send failed for %s", recipient)
            continue
        sent_total += 1
        ledger += [{"opportunity_id": i.opportunity_id, "recipient": recipient,
                    "kind": "digest"} for i in items]

    recorded = db.record_notifications(workspace_id, ledger)
    return {"status": "sent" if sent_total else "nothing_new", "sent": sent_total,
            "recipients": len(recipients), "opportunities_notified": recorded}


def notify_assignee(
    workspace_id: str, opportunity_id: str, assignee_id: str, assigner: str,
) -> dict:
    """"Circulated to the respective Zonal Heads", in one email. Never raises.

    Assignment is the write that matters; the email is a courtesy on top of it. A bounced
    address must not fail the PATCH and leave the tender unrouted.
    """
    try:
        settings = db.get_notification_settings(workspace_id) or {}
        if not settings.get("notify_assignee", True) or not is_configured():
            return {"emailed": False, "reason": "not configured"}

        # The membership check is the security control, not a formality: an address outside
        # this workspace must never be told what it is bidding on.
        email = db.get_member_email(workspace_id, assignee_id)
        if not email:
            return {"emailed": False, "reason": "assignee has no address in this workspace"}

        row = next((m for m in db.get_feed(workspace_id, "in_scope", limit=200)
                    if m.get("opportunity_id") == opportunity_id), None)
        if row is None:
            return {"emailed": False, "reason": "opportunity not in scope for this workspace"}
        flat = _flatten(row)
        item = Alertable(
            opportunity_id=opportunity_id, portal_ref_no=flat["portal_ref_no"],
            title=flat["title"] or "Untitled tender", band=flat["relevance_band"] or "",
            authority=flat["authority"], deadline=flat["deadline"],
            value_display=flat["value_display"], eligibility=flat["eligibility"],
        )
        subject, body = render_assignment(item, assigner, _app_url())
        send(email, subject, body)
        db.record_notifications(workspace_id, [
            {"opportunity_id": opportunity_id, "recipient": email, "kind": "assignment"},
        ])
        return {"emailed": True, "to": email}
    except Exception:  # noqa: BLE001 — the assignment itself has already succeeded
        log.exception("assignment notification failed for opportunity %s", opportunity_id)
        return {"emailed": False, "reason": "send failed"}
