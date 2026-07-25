"""Cite-or-flag validation + coverage — the deterministic half of Module B.

The Drafter (AI) proposes narrative sentences; THIS module decides what may stand:
  - B-FR1 cite-or-flag: a claim-class sentence with no resolvable citation is flagged
    "unverified" and cannot pass the export gate unattested
  - B-AC4: a sentence carrying a money figure that isn't a transclusion is a HARD flag
    (a model must never author an amount — real values come from structured rows)
  - B-AC2: mandatory-criteria coverage = addressed (drafted or explicit placeholder) / total

The model does NOT get to say whether a sentence needs a citation. It proposes a class
(claim | narrative) and `classify_sentence` decides, coercing toward CLAIM whenever the
text looks evidence-shaped or the section isn't narrative-eligible. Coercion is strictly
one-directional, so a mislabelled sentence can only ever end up under a *stricter* rule —
the model cannot buy its way out of a citation. Pure functions, no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .types import SectionKind, SentenceClass


@dataclass(frozen=True)
class DraftSentence:
    text: str
    citations: tuple[str, ...]  # library chunk ids the model cited
    cls: SentenceClass = SentenceClass.CLAIM  # resolved by validate_draft, not the caller
    source_ref: str | None = None  # "table:id.column" for ASSEMBLED sentences
    is_transcluded: bool = False  # only an assembler may set this (B-FR3)
    # Derived by validate_draft from the text + resolved class — never model-supplied.
    requires_citation: bool = False
    is_financial: bool = False


@dataclass(frozen=True)
class SentenceFlag:
    text: str
    reason: str  # "unverified" | "uncited_financial"


@dataclass(frozen=True)
class DraftValidation:
    sentences: tuple[DraftSentence, ...]  # classes + flags resolved
    flags: tuple[SentenceFlag, ...]
    status: str  # 'drafted' | 'unverified'
    claim_verifiability: float  # B-AC3
    narrative_sentences: int  # drives the section-approval export blocker (B-FR4)


# --- Deterministic classification (the model proposes; this decides) ---

# Evidence-shaped: enough to force NARRATIVE -> CLAIM. Deliberately broad — the cost of a
# false positive is only "this sentence must cite", which is never wrong for a bid.
_ANY_DIGIT = re.compile(r"\d")
_CREDENTIAL = re.compile(
    r"\b(iso|cmmi|nabl|bis|msme|udyam|dpiit|gstin?|cin|pan|empanel|certif)", re.I
)
_EVIDENTIARY = re.compile(
    r"\b(we\s+(?:have|had)\s+(?:completed|executed|delivered|supplied|implemented|"
    r"commissioned|deployed)"
    r"|has\s+been\s+(?:certified|awarded|empanelled|empaneled)"
    r"|certified\s+by|awarded\s+by|our\s+past|previously\s+delivered)\b",
    re.I,
)

# Money-shaped: a number ADJACENT to a currency or scale marker. Deliberately narrow —
# this drives the HARD, non-overridable gate, and "FY23-FY25" or "three phases" must not
# trip it. "Rs 8.2 Crore", "₹2 Cr", "50%" must.
_MONEY = re.compile(
    r"(?:(?:₹|\brs\.?\b|\binr\b)\s*[\d,]+(?:\.\d+)?)"
    r"|(?:[\d,]+(?:\.\d+)?\s*(?:cr\b|crore|lakh|lac|%))",
    re.I,
)


def is_evidence_shaped(text: str) -> bool:
    """Does this sentence look like it asserts something checkable against a document?"""
    return bool(
        _ANY_DIGIT.search(text) or _CREDENTIAL.search(text) or _EVIDENTIARY.search(text)
    )


def is_money_shaped(text: str) -> bool:
    """B-AC4: does this sentence author a money/quantity value? Narrow by design."""
    return bool(_MONEY.search(text))


def classify_sentence(
    proposed: SentenceClass, text: str, section: SectionKind
) -> SentenceClass:
    """Resolve a sentence's class. Only ever coerces TOWARD CLAIM, never away from it.

    That one-directional property is the whole safety argument: a model that mislabels a
    factual claim as narrative to dodge a citation gets a *stricter* rule, not a looser one.
    """
    # Python-only classes are passed through untouched; the model can never propose them.
    if proposed in (SentenceClass.ASSEMBLED, SentenceClass.PLACEHOLDER):
        return proposed
    if proposed is not SentenceClass.NARRATIVE:
        return SentenceClass.CLAIM
    if section is not SectionKind.NARRATIVE:
        return SentenceClass.CLAIM  # narrative is simply unavailable in compliance sections
    if is_evidence_shaped(text):
        return SentenceClass.CLAIM  # looks checkable -> it must cite
    return SentenceClass.NARRATIVE


def derive_flags(text: str, cls: SentenceClass) -> tuple[bool, bool]:
    """(requires_citation, is_financial) from the TEXT and resolved class — not model labels."""
    requires_citation = cls is SentenceClass.CLAIM
    # An assembled value is transcluded from a structured row, so it is not a model-authored
    # figure; every other class is judged on the text alone.
    is_financial = cls is not SentenceClass.ASSEMBLED and is_money_shaped(text)
    return requires_citation, is_financial


def validate_draft(
    sentences: Sequence[DraftSentence],
    valid_chunk_ids: set[str],
    section: SectionKind = SectionKind.COMPLIANCE,
) -> DraftValidation:
    """Resolve every sentence's class and flags, then decide what may stand.

    `section` defaults to COMPLIANCE — the strictest reading — so any caller that does not
    opt in to narrative gets today's behaviour exactly.
    """
    resolved: list[DraftSentence] = []
    flags: list[SentenceFlag] = []

    for s in sentences:
        cls = classify_sentence(s.cls, s.text, section)
        requires_citation, is_financial = derive_flags(s.text, cls)
        r = replace(s, cls=cls, requires_citation=requires_citation, is_financial=is_financial)
        resolved.append(r)

        # B-AC4 (hard): a money figure that isn't a transclusion. Checked before B-FR1 so a
        # fabricated amount is never merely "unverified" — it is non-overridable.
        if r.is_financial and not r.is_transcluded:
            flags.append(SentenceFlag(r.text, "uncited_financial"))
            continue
        # B-FR1: a claim whose citation doesn't resolve to a retrieved chunk.
        if r.requires_citation and not any(c in valid_chunk_ids for c in r.citations):
            flags.append(SentenceFlag(r.text, "unverified"))

    return DraftValidation(
        sentences=tuple(resolved),
        flags=tuple(flags),
        status="unverified" if flags else "drafted",
        claim_verifiability=claim_verifiability(resolved, valid_chunk_ids),
        narrative_sentences=sum(1 for s in resolved if s.cls is SentenceClass.NARRATIVE),
    )


def claim_verifiability(sentences: Sequence[DraftSentence], valid_chunk_ids: set[str]) -> float:
    """B-AC3: fraction of claim sentences whose citation resolves to a chunk."""
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
