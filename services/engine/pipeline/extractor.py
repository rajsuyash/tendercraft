"""Extractor — tender page text -> schema-valid criteria with confidence + anchors.

PRD Module A / §5.1. AI proposes; deterministic gates decide downstream. Sub-0.80
confidence is flagged for the human verification queue (A-FR4/A-AC5) — the model never
self-certifies. Empty/failed extraction returns [] so the caller routes to manual review
(never invents a criterion).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.deterministic.types import EXTRACTION_CONFIRM_THRESHOLD

from .client import ModelError, generate_json
from .schemas import CRITERIA_SCHEMA

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "extractor.md").read_text()


@dataclass(frozen=True)
class ExtractedCriterion:
    verbatim_text: str
    category: str
    requirement_level: str
    confidence: float
    anchor_page: int
    anchor_clause: str
    evidence_required: str
    evaluation_weight: float | None
    needs_confirmation: bool


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def extract_from_page(page_text: str, page_number: int) -> list[ExtractedCriterion]:
    """Extract criteria from one page. Returns [] on model failure (routes to manual review)."""
    prompt = _PROMPT.replace("{{PAGE_NUMBER}}", str(page_number)).replace(
        "{{PAGE_TEXT}}", page_text
    )
    try:
        result = generate_json(prompt, CRITERIA_SCHEMA)
    except ModelError:
        return []

    out: list[ExtractedCriterion] = []
    for c in result.get("criteria", []):
        conf = _clamp01(c.get("confidence", 0.0))
        out.append(
            ExtractedCriterion(
                verbatim_text=c["verbatim_text"],
                category=c["category"],
                requirement_level=c["requirement_level"],
                confidence=conf,
                anchor_page=page_number,
                anchor_clause=c.get("anchor_clause", ""),
                evidence_required=c.get("evidence_required", ""),
                evaluation_weight=c.get("evaluation_weight"),
                needs_confirmation=conf < EXTRACTION_CONFIRM_THRESHOLD,
            )
        )
    return out
