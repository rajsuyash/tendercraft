"""Shared typed structures + PRD-cited constants for the deterministic engine.

Constants live here once so the UI and engine never drift (known-pitfalls: scattered
magic numbers). Each is cited to the PRD clause that fixes it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

# The extractor often returns a clause that already says what it is ("Annexure-VII",
# "Clause 4.1"). Prefixing "Cl." onto those produced "Cl. Annexure-VII" on real tenders.
_CLAUSE_PREFIXED = re.compile(r"^(cl\.?|clause|annexure|section|para)\b", re.I)

# --- Thresholds (single source of truth, cited to tendercraft-PRD.md) ---
# A-FR4 / A-AC5: sub-0.80 extractions must be human-confirmed before a TOM can lock
EXTRACTION_CONFIRM_THRESHOLD = 0.80
# C-FR2 / C-AC5: sub-0.75 fuzzy matches -> needs_review, never auto-pass
FUZZY_REVIEW_THRESHOLD = 0.75
# D-FR2 / Appendix C #4: cold-start suppression floor (tunable per cluster)
SUPPRESSION_MIN_OUTCOMES = 30
# RB-4: below this cluster directional accuracy, suppress estimates until recalibrated
MIN_DIRECTIONAL_ACCURACY = 0.70


class SentenceClass(StrEnum):
    """What a drafted sentence IS — decides whether it needs a citation (B-FR1).

    The model may only ever *propose* CLAIM or NARRATIVE. ASSEMBLED and PLACEHOLDER are
    emitted by Python alone, so the model can never claim to be a transclusion (B-FR3)
    or to be an explicit sourcing placeholder (B-FR2).
    """

    CLAIM = "claim"  # asserts a verifiable fact about the bidder -> must cite
    NARRATIVE = "narrative"  # the bidder's proposed approach; nothing exists yet to cite
    ASSEMBLED = "assembled"  # emitted by a deterministic assembler from a structured row
    PLACEHOLDER = "placeholder"  # explicit sourcing instruction


class CheckType(StrEnum):
    """What a pre-bid gate actually tests. The model names one of these and nothing else —
    the enum IS the G-6 allowlist, the same shape `spec_params.PARAM_KEYS` uses."""

    TURNOVER_AVG = "turnover_avg"
    NET_WORTH = "net_worth"
    WORKING_CAPITAL = "working_capital"
    EXPERIENCE_COUNT = "experience_count"
    CERTIFICATION_VALID = "certification_valid"
    REGISTRATION_PRESENT = "registration_present"
    NONE = "none"  # nothing checkable was stated


class RequirementKind(StrEnum):
    """What a bidder is supposed to DO about a requirement — and so whether it may vote.

    Orthogonal to `criterion_category`, which says what SUBJECT a requirement belongs to. A
    financial requirement can be a gate ("average annual turnover of ₹10 Cr") or an
    instruction ("quote rates inclusive of taxes"); on the live wire-rope bid all four
    mandatory financial rows were instructions. See `deterministic/requirement_kind.py`.
    """

    GATE = "gate"  # a pre-bid condition — the only kind that votes on bid/no-bid
    OBLIGATION = "obligation"  # a duty that binds after award
    INSTRUCTION = "instruction"  # how to prepare or submit; can neither pass nor fail
    FORM = "form"  # a template to fill and attach
    SPEC = "spec"  # a technical parameter belonging to the schedule


class SectionKind(StrEnum):
    """Whether a section is allowed to contain uncited narrative at all."""

    COMPLIANCE = "compliance"  # per-criterion responses, experience, team — claims only
    NARRATIVE = "narrative"  # methodology, solution, QA, training, risk — narrative allowed


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


class RequirementLevel(StrEnum):
    MANDATORY = "mandatory"
    DESIRABLE = "desirable"
    SELF_ATTESTATION = "self_attestation"


class Recommendation(StrEnum):
    BID = "bid"
    NO_BID = "no_bid"
    NEEDS_REVIEW = "needs_review"
    #: The tender states no pre-bid eligibility gate at all. Distinct from NEEDS_REVIEW,
    #: which asks a human to resolve something: here there is nothing to resolve, because
    #: nothing in the tender can disqualify this bidder. Common rather than exotic — the
    #: live wire-rope bid has eighteen mandatory criteria and zero gates.
    NO_GATES = "no_gates"


class CoverageStatus(StrEnum):
    COVERED = "covered"
    PLACEHOLDER = "placeholder"  # B-FR2: blocks export
    UNVERIFIED = "unverified"  # B-FR1: uncited claim, blocks export
    MANUAL = "manual"  # original-required item (B-FR5): human handles, does not auto-block
    MISSING = "missing"


@dataclass(frozen=True)
class SourceAnchor:
    """A-AC3: every locked criterion must resolve back to where it came from.

    A page is required. A clause identifier is NOT, and requiring it was a defect: on a real
    81-page NABARD RFP, 12 of 192 criteria came from prose that states an obligation without
    numbering it ("Note: Certificate should be in official letterhead..."). The gate refused
    the lock, and since nothing in the product lets a human supply a clause number the
    document never had, every prose-style tender was permanently unlockable.

    A page plus the stored verbatim text is a resolvable anchor: a human can open that page and
    find that sentence, which is the whole point of A-AC3. A clause identifier is a convenience
    the document supplies or does not.
    """

    page: int
    clause: str
    #: Which document of the package the page belongs to ("Annexure-II.pdf", "BOQ.xlsx · Sheet1").
    #: Empty on single-document tenders, where the page alone already resolves.
    document: str = ""

    def is_resolvable(self) -> bool:
        return self.page > 0

    def label(self) -> str:
        """"Annexure-II.pdf · p.4 · Cl. 3.1" — the parts the document actually supplied."""
        parts = [p for p in (self.document, f"p.{self.page}" if self.page else "") if p]
        if self.clause:
            prefixed = _CLAUSE_PREFIXED.match(self.clause)
            parts.append(self.clause if prefixed else f"Cl. {self.clause}")
        return " · ".join(parts) or "no anchor"


@dataclass(frozen=True)
class Criterion:
    id: str
    confidence: float
    confirmed: bool
    requirement_level: RequirementLevel
    anchor: SourceAnchor | None = None


@dataclass(frozen=True)
class ComplianceRow:
    """One row of the export compliance matrix (B-FR generation pipeline output)."""

    criterion_id: str
    requirement_level: RequirementLevel
    status: CoverageStatus
    has_uncited_financial_claim: bool = False  # B-AC4 hard gate


@dataclass(frozen=True)
class GateResult:
    """Uniform result for every deterministic gate: a decision plus its reasons."""

    ok: bool
    blockers: tuple[str, ...] = field(default_factory=tuple)
