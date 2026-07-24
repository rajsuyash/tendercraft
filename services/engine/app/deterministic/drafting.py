"""Cite-or-flag validation + coverage — the deterministic half of Module B.

The Drafter (AI) proposes narrative sentences, each tagged with the citations it used and
whether it states a fact needing one. THIS module decides what may stand:
  - B-FR1 cite-or-flag: a fact-stating sentence with no resolvable citation is flagged
    "unverified" and cannot pass the export gate unattested
  - B-AC4: a sentence carrying a financial/numeric claim that isn't a transclusion token
    is a HARD flag (a model must never author a money figure — that comes via transclusion)
  - B-AC2: mandatory-criteria coverage = addressed (drafted or explicit placeholder) / total
Pure functions over the model's tagged output — no I/O, fully testable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class DraftSentence:
    text: str
    citations: tuple[str, ...]  # library chunk ids the model cited
    requires_citation: bool  # model says this states a fact
    is_financial: bool  # states a numeric/financial value
    is_transcluded: bool  # the value came via a transclusion token, not model text


@dataclass(frozen=True)
class SentenceFlag:
    text: str
    reason: str  # "unverified" | "uncited_financial"


def validate_citations(
    sentences: Sequence[DraftSentence], valid_chunk_ids: set[str]
) -> tuple[SentenceFlag, ...]:
    """Return a flag for every sentence that may not stand as written."""
    flags: list[SentenceFlag] = []
    for s in sentences:
        # B-AC4 (hard): a model-authored financial claim that isn't transcluded
        if s.is_financial and not s.is_transcluded:
            flags.append(SentenceFlag(s.text, "uncited_financial"))
            continue
        # B-FR1: a fact needing a citation whose citation doesn't resolve
        if s.requires_citation:
            resolved = [c for c in s.citations if c in valid_chunk_ids]
            if not resolved:
                flags.append(SentenceFlag(s.text, "unverified"))
    return tuple(flags)


def claim_verifiability(sentences: Sequence[DraftSentence], valid_chunk_ids: set[str]) -> float:
    """B-AC3: fraction of fact-stating sentences whose citation resolves to a chunk."""
    facts = [s for s in sentences if s.requires_citation]
    if not facts:
        return 1.0
    ok = sum(1 for s in facts if any(c in valid_chunk_ids for c in s.citations))
    return ok / len(facts)


# --- coverage (B-AC2) ---
ADDRESSED_STATUSES = {"drafted", "placeholder"}  # placeholder counts as addressed per B-AC2


def mandatory_coverage(criteria: Sequence[dict]) -> float:
    """Fraction of mandatory criteria addressed (drafted or explicit placeholder)."""
    mandatory = [c for c in criteria if c.get("requirement_level") == "mandatory"]
    if not mandatory:
        return 1.0
    addressed = sum(1 for c in mandatory if c.get("draft_status") in ADDRESSED_STATUSES)
    return addressed / len(mandatory)
