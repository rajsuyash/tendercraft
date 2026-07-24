"""Eligibility analyzer — model proposes, deterministic layer decides (§2.4).

Per criterion, Gemini extracts values + a proposed verdict against the profile; the
caller (app/analysis.py) then applies the deterministic comparators (numeric) and the
0.75 fuzzy router (C-AC5). Model failure -> a conservative needs_review shell, never a
fabricated pass (ET-1/G-5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .client import ModelError, generate_json
from .schemas import CRITERION_EVAL_SCHEMA

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "analyzer.md").read_text()


@dataclass(frozen=True)
class ModelEval:
    check_type: str
    model_verdict: str
    confidence: float
    rationale: str
    evidence_ids: tuple[str, ...]
    required_value_cr: float | None
    operator: str | None
    actual_value_cr: float | None
    gap_note: str
    exemption_applies: bool
    exemption_clause: str | None


def _clamp01(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def evaluate_criterion(criterion_text: str, profile_json: dict) -> ModelEval:
    """Ask the model to evaluate one criterion against the profile. Never raises."""
    prompt = _PROMPT.replace("{{CRITERION}}", criterion_text).replace(
        "{{PROFILE}}", json.dumps(profile_json, ensure_ascii=False, indent=2)
    )
    try:
        r = generate_json(prompt, CRITERION_EVAL_SCHEMA)
    except ModelError:
        # conservative fallback: unknown -> needs_review with zero confidence
        return ModelEval(
            check_type="other",
            model_verdict="needs_review",
            confidence=0.0,
            rationale="model unavailable — routed to manual review",
            evidence_ids=(),
            required_value_cr=None,
            operator=None,
            actual_value_cr=None,
            gap_note="",
            exemption_applies=False,
            exemption_clause=None,
        )
    return ModelEval(
        check_type=r.get("check_type", "other"),
        model_verdict=r.get("model_verdict", "needs_review"),
        confidence=_clamp01(r.get("confidence", 0.0)),
        rationale=r.get("rationale", ""),
        evidence_ids=tuple(r.get("evidence_ids", []) or ()),
        required_value_cr=r.get("required_value_cr"),
        operator=r.get("operator"),
        actual_value_cr=r.get("actual_value_cr"),
        gap_note=r.get("gap_note", ""),
        exemption_applies=bool(r.get("exemption_applies", False)),
        exemption_clause=r.get("exemption_clause"),
    )
