"""One submission-readiness figure that reconciles with what the user is shown.

The journey walk found four counters describing the same bid at the same moment, none
agreeing: readiness said "0 P0 blocking", the proposal said "9 awaiting approval", the
export gate said "25% · 13 blockers", approvals said "0/2". Nothing on screen explained
where 13 came from — the answer was only visible in raw JSON.

This computes ONE number from the same inputs the gates use, and returns the itemised
breakdown alongside it, so the figure and its explanation can never drift apart. Pure.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

# Ordered by where a bidder must act. Each stage is complete or it is not; partials do not
# count, because "80% approved" still cannot be exported.
STAGES: tuple[tuple[str, str], ...] = (
    ("requirements", "Requirements confirmed"),
    ("eligibility", "Eligibility resolved"),
    ("document", "Proposal drafted"),
    ("review", "Sections approved"),
    ("signoff", "Approvals complete"),
)


@dataclass(frozen=True)
class Blocker:
    stage: str
    label: str
    detail: str


@dataclass(frozen=True)
class SubmissionState:
    stage: str
    stage_label: str
    completed_stages: int
    total_stages: int
    percent: int
    blockers: tuple[Blocker, ...] = field(default_factory=tuple)
    can_submit: bool = False

    @property
    def blocker_count(self) -> int:
        return len(self.blockers)


def compute(
    *,
    confirm_open: int,
    p0_blocking: int,
    sections_total: int,
    sections_placeholder: int,
    narrative_unapproved: int,
    approvals_done: int,
    approvals_required: int,
    hard_blockers: Sequence[str] = (),
) -> SubmissionState:
    """The single source of "how close am I", with every blocker named."""
    blockers: list[Blocker] = []

    if confirm_open:
        blockers.append(Blocker(
            "requirements", "Requirements confirmed",
            f"{confirm_open} extracted requirement(s) awaiting your confirmation"))
    if p0_blocking:
        blockers.append(Blocker("eligibility", "Eligibility resolved",
                                f"{p0_blocking} requirement(s) you do not currently meet"))
    if sections_total == 0:
        blockers.append(Blocker(
            "document", "Proposal drafted", "the proposal has not been generated"))
    elif sections_placeholder:
        blockers.append(Blocker("document", "Proposal drafted",
                                f"{sections_placeholder} section(s) still have no content"))
    if narrative_unapproved:
        blockers.append(Blocker("review", "Sections approved",
                                f"{narrative_unapproved} drafted section(s) not yet approved"))
    if approvals_done < approvals_required:
        blockers.append(Blocker("signoff", "Approvals complete",
                                f"{approvals_done} of {approvals_required} sign-offs collected"))
    for h in hard_blockers:
        # Non-overridable: an unsourced figure can never reach a submitted document.
        blockers.append(Blocker("review", "Sections approved", h))

    blocked_stages = {b.stage for b in blockers}
    completed = sum(1 for key, _ in STAGES if key not in blocked_stages)
    current = next((k for k, _ in STAGES if k in blocked_stages), "signoff")
    label = dict(STAGES)[current]

    return SubmissionState(
        stage=current,
        stage_label=label,
        completed_stages=completed,
        total_stages=len(STAGES),
        percent=round(100 * completed / len(STAGES)),
        blockers=tuple(blockers),
        can_submit=not blockers,
    )
