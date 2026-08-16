"""Did this bid move, and is the move worth telling someone about? Pure — no I/O, no model.

UML ask 4. GeM publishes a bid's evaluation lifecycle on a public surface, so a seller can be
told their bid reached technical evaluation without anyone logging in to their account.

**The sentence this module exists to keep honest:** we detect the STAGE, never the document
request. The clarification itself lives behind the GeM seller login (G-1/G-8). This is the
alarm clock, not the letter, and every message rendered here says so — a bidder who believed
otherwise would stop checking the portal inbox where the request actually arrives, which would
make the feature worse than nothing.

Two rules the transition logic turns on:

1. **A first sighting is never an alert.** `last_stage` is NULL until something checks, and
   NULL means "never looked", not "not evaluated". Treating the first observation as a change
   would announce every watched bid once, on the day watching was switched on, for bids that
   may have been sitting at the same stage for a month. The first check establishes a baseline.

2. **Only forward moves alert.** The portal can report a bid at an earlier stage than last
   seen — a re-evaluation, or our own most-advanced-first probe resolving differently on a
   flaky page. Announcing "your bid went backwards" on portal noise costs the user's trust in
   every later alert.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The lifecycle, in order, exactly as GeM's own `loadBids()` names it:
#: ["Not Evaluated", "Technical Evaluation", "Financial Evaluation", "Bid Award"].
STAGES = ("not_evaluated", "tech_evaluated", "fin_evaluated", "bid_awarded")
_ORDER = {stage: i for i, stage in enumerate(STAGES)}

#: What each stage means for the bidder, in their terms rather than the portal's.
_MEANING = {
    "tech_evaluated": (
        "Technical evaluation has started. This is when buyers raise clarifications and ask "
        "for additional documents"
    ),
    "fin_evaluated": (
        "Financial evaluation has started — the technical stage is behind you and price is "
        "being compared"
    ),
    "bid_awarded": "The bid has been awarded. The result page now names the sellers and prices",
}


@dataclass(frozen=True)
class Transition:
    portal_ref_no: str
    previous: str | None
    current: str
    #: False on a first sighting or a non-forward move — see the module docstring.
    alertable: bool
    reason: str

    @property
    def kind(self) -> str:
        """The notifications_sent key. Per-stage, so each move announces exactly once."""
        return f"stage:{self.current}"


def classify(portal_ref_no: str, previous: str | None, current: str) -> Transition:
    """Decide whether this observation is worth an email."""
    if current not in _ORDER:
        return Transition(portal_ref_no, previous, current, False,
                          f"unknown stage {current!r}")
    if previous is None:
        return Transition(portal_ref_no, previous, current, False,
                          "first check — recording a baseline, not announcing it")
    if previous == current:
        return Transition(portal_ref_no, previous, current, False, "no change")
    if _ORDER.get(previous, -1) > _ORDER[current]:
        return Transition(portal_ref_no, previous, current, False,
                          "portal reported an earlier stage than last seen — not announced")
    return Transition(portal_ref_no, previous, current, True,
                      f"moved from {previous} to {current}")


def render_stage_alert(
    transition: Transition, title: str, app_url: str, source_url: str | None = None,
) -> tuple[str, str]:
    """(subject, plain-text body). Says what moved, what it means, and what we cannot see."""
    label = transition.current.replace("_", " ")
    subject = f"Bid update — {label}: {title}".replace("\r", " ").replace("\n", " ")[:160]
    lines = [
        f"{transition.portal_ref_no} has moved to {label}.",
        "",
        f"• {title}",
        f"  {_MEANING.get(transition.current, 'The bid has changed stage on GeM.')}.",
        "",
    ]
    if transition.current == "tech_evaluated":
        lines += [
            "Check your GeM seller account for any clarification or document request, and",
            "note the response window — these usually close fast.",
            "",
        ]
    # The limitation, in the message itself rather than in documentation nobody opens.
    lines += [
        "We read this from GeM's public bid pages. We cannot see the request itself —",
        "that is only in your GeM seller account, and we do not hold portal logins.",
        "",
    ]
    if source_url:
        lines += [f"Public bid page: {source_url}"]
    lines += [f"Your feed: {app_url}/opportunities"]
    return subject, "\n".join(lines)
