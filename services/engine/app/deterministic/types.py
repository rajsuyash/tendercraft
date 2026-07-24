"""Shared typed structures + PRD-cited constants for the deterministic engine.

Constants live here once so the UI and engine never drift (known-pitfalls: scattered
magic numbers). Each is cited to the PRD clause that fixes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# --- Thresholds (single source of truth, cited to tendercraft-PRD.md) ---
# A-FR4 / A-AC5: sub-0.80 extractions must be human-confirmed before a TOM can lock
EXTRACTION_CONFIRM_THRESHOLD = 0.80
# C-FR2 / C-AC5: sub-0.75 fuzzy matches -> needs_review, never auto-pass
FUZZY_REVIEW_THRESHOLD = 0.75
# D-FR2 / Appendix C #4: cold-start suppression floor (tunable per cluster)
SUPPRESSION_MIN_OUTCOMES = 30
# RB-4: below this cluster directional accuracy, suppress estimates until recalibrated
MIN_DIRECTIONAL_ACCURACY = 0.70


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


class CoverageStatus(StrEnum):
    COVERED = "covered"
    PLACEHOLDER = "placeholder"  # B-FR2: blocks export
    UNVERIFIED = "unverified"  # B-FR1: uncited claim, blocks export
    MANUAL = "manual"  # original-required item (B-FR5): human handles, does not auto-block
    MISSING = "missing"


@dataclass(frozen=True)
class SourceAnchor:
    """A-AC3: every locked criterion must resolve to page + clause."""

    page: int
    clause: str

    def is_resolvable(self) -> bool:
        return self.page > 0 and bool(self.clause.strip())


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
