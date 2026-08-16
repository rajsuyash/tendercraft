"""Who gets told about which tender, and what the message says. Pure — no I/O, no SMTP.

The alert threshold governs what is worth an EMAIL. It must never become a filter on the feed:
an item below the band is still fully visible in the app, still counted, still openable. A
notification setting that quietly narrowed what a bidder could see would be an exclusion no
user authored, which is the one failure in this product with no natural feedback signal
(G-9 / F-AC6 / ET-7). The feed and the inbox are two different questions.

`select_for_digest` is deliberately given the already-sent set rather than computing it: a
dispatcher that runs twice, or retries after a partial failure, must not re-send, and making
the caller pass the ledger keeps that guarantee testable without a database.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .discovery import BANDS

#: Most relevant first, so `>=` means "at least this relevant".
_RANK = {band: i for i, band in enumerate(BANDS)}

#: A subject line is a header. A newline inside one lets a portal-supplied tender title inject
#: further headers (Bcc:, Content-Type:), so titles are flattened before they go near it —
#: tender text is untrusted input everywhere else in this product and an outbound email is no
#: exception (G-6).
_NEWLINES = re.compile(r"[\r\n]+")
_MAX_SUBJECT = 160
#: Beyond this the digest is a wall of text nobody reads; the rest is one click away.
_MAX_ITEMS = 15


@dataclass(frozen=True)
class Alertable:
    """One in-scope match worth mentioning."""

    opportunity_id: str
    portal_ref_no: str | None
    title: str
    band: str
    authority: str | None
    deadline: str | None
    value_display: str | None
    eligibility: str | None


def meets_band(band: str | None, minimum: str) -> bool:
    """Is this match at least as relevant as the workspace's alert threshold?

    An unknown or missing band does NOT clear the bar, and that asymmetry is deliberate: it
    fails toward a quieter inbox, and the item is still in the feed either way. Failing the
    other way would train people to ignore the alerts, which loses the tenders that matter.
    """
    if band not in _RANK or minimum not in _RANK:
        return False
    return _RANK[band] <= _RANK[minimum]


def select_for_digest(
    matches: Sequence[dict], minimum: str, already_sent: set[str],
) -> tuple[Alertable, ...]:
    """In-scope, relevant-enough matches this recipient has not already been told about.

    Excluded matches are never alertable — but note the reason: not because the alert layer
    filters them, but because a user's own rule already removed them from scope and the email
    must agree with the screen. Two different answers to "is this tender mine" is worse than
    either answer alone.
    """
    out: list[Alertable] = []
    for m in matches:
        if m.get("state") != "in_scope":
            continue
        if m.get("opportunity_id") in already_sent:
            continue
        if not meets_band(m.get("relevance_band"), minimum):
            continue
        out.append(
            Alertable(
                opportunity_id=m["opportunity_id"],
                portal_ref_no=m.get("portal_ref_no"),
                title=_flat(m.get("title") or "Untitled tender"),
                band=m.get("relevance_band") or "",
                authority=_flat(m.get("authority")) if m.get("authority") else None,
                deadline=m.get("deadline"),
                value_display=m.get("value_display"),
                eligibility=m.get("eligibility"),
            )
        )
    # Most relevant first, then soonest deadline: the order someone should act in.
    out.sort(key=lambda a: (_RANK.get(a.band, 99), a.deadline or "9999"))
    return tuple(out)


def _flat(text: str | None) -> str:
    return _NEWLINES.sub(" ", (text or "")).strip()


def render_digest(items: Sequence[Alertable], workspace: str, app_url: str) -> tuple[str, str]:
    """(subject, plain-text body) for the workspace digest. Never called with an empty list."""
    n = len(items)
    subject = _subject(
        f"{n} new tender{'' if n == 1 else 's'} matched {workspace}"
        if n > 1 else f"New tender matched {workspace}: {items[0].title}"
    )
    lines = [
        f"{n} new opportunit{'y' if n == 1 else 'ies'} matched this workspace.",
        "",
    ]
    for a in items[:_MAX_ITEMS]:
        lines.append(f"• {a.title}")
        bits = [b for b in (
            a.portal_ref_no,
            a.authority,
            f"closes {a.deadline[:10]}" if a.deadline else None,
            a.value_display,
            f"relevance: {a.band}" if a.band else None,
        ) if b]
        lines.append(f"  {' · '.join(bits)}")
        if a.eligibility and a.eligibility != "unknown":
            # Depth-1 signal, not a verdict. Named as a signal so nobody reads it as a
            # decision the product has taken on their behalf (C-AC9).
            lines.append(f"  eligibility signal: {a.eligibility}")
        lines.append(f"  {app_url}/opportunities")
        lines.append("")
    if n > _MAX_ITEMS:
        lines.append(f"...and {n - _MAX_ITEMS} more in the feed.")
        lines.append("")
    lines += [
        "Relevance ranks what to read first. It never hides anything — every tender swept",
        "for this workspace is in the feed, including the ones below your alert threshold.",
        "",
        f"Feed: {app_url}/opportunities",
    ]
    return subject, "\n".join(lines)


def render_assignment(item: Alertable, assigner: str, app_url: str) -> tuple[str, str]:
    """(subject, body) for "this tender has been routed to you" — UML ask 1, literally."""
    subject = _subject(f"Tender assigned to you: {item.title}")
    bits = [b for b in (
        item.portal_ref_no, item.authority,
        f"closes {item.deadline[:10]}" if item.deadline else None,
        item.value_display,
    ) if b]
    body = "\n".join([
        f"{assigner} has assigned this tender to you.",
        "",
        f"• {item.title}",
        f"  {' · '.join(bits)}" if bits else "",
        "",
        f"Open it: {app_url}/opportunities",
    ])
    return subject, body


def _subject(text: str) -> str:
    flat = _flat(text)
    return flat[:_MAX_SUBJECT - 1] + "…" if len(flat) > _MAX_SUBJECT else flat
