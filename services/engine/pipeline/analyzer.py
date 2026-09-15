"""Read what a pre-bid gate DEMANDS. Nothing about the bidder, and no verdict.

The model used to receive the whole vendor profile and return `actual_value_cr`,
`model_verdict` and `exemption_applies` — and `app/analysis.py` let all three decide. A
numeric comparison ran on two model-supplied numbers with no confidence or evidence check,
so confidence 0.01 produced a hard PASS; one `exemption_applies: true` turned NO-BID into
BID with no clause resolved.

`extract_requirement` takes NO profile argument, and that is the structural half of the fix:
the model physically cannot see the bidder's numbers, so it cannot report them. It is worth
more than any instruction in the prompt, and it makes the call a pure function of the
criterion text. `app/deterministic/facts.py` decides.

Model failure → a `none` requirement at zero confidence, which the decision layer routes to
needs_review. Never a fabricated pass (ET-1/G-5).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

from app.deterministic.facts import Requirement
from app.deterministic.types import CheckType

from .client import ModelError, generate_json
from .schemas import ELIGIBILITY_REQUIREMENT_SCHEMA

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "analyzer.md").read_text()

#: The prompt's own digest, so a prompt edit invalidates every cached reading. Derived from
#: the file rather than a hand-maintained constant: a version number someone must remember to
#: bump is a cache that silently becomes the product.
PROMPT_DIGEST = hashlib.sha256(_PROMPT.encode("utf-8")).hexdigest()[:16]


def requirement_hash(criterion_text: str) -> str:
    """Everything a reading depends on. Change any of it and it is re-read; change nothing
    and it is not — the `discovery/relevance.py::input_hash` rule."""
    material = "\x1f".join([(criterion_text or "").strip(), PROMPT_DIGEST])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def to_json(req: Requirement) -> dict:
    """A stored requirement. Enums become their values so the row is plain jsonb."""
    out = asdict(req)
    out["check"] = req.check.value
    out["fy_labels"] = list(req.fy_labels)
    out["exemption_for"] = list(req.exemption_for)
    return out


def from_json(raw: dict) -> Requirement:
    """Rehydrate a stored reading. Tolerant on purpose: a row written by an older shape must
    degrade to `none` at zero confidence — which reads needs-review — rather than raise
    inside the analysis of an unrelated tender."""
    try:
        check = CheckType(raw.get("check", "none"))
    except ValueError:
        check = CheckType.NONE
    return Requirement(
        check=check,
        operator=raw.get("operator"),
        threshold_cr=_float_or_none(raw.get("threshold_cr")),
        fy_count=_int_or_none(raw.get("fy_count")),
        fy_labels=tuple(raw.get("fy_labels") or ()),
        min_count=_int_or_none(raw.get("min_count")),
        years_window=_int_or_none(raw.get("years_window")),
        certification_name=raw.get("certification_name"),
        registration_key=raw.get("registration_key"),
        exemption_for=tuple(raw.get("exemption_for") or ()),
        exemption_clause=raw.get("exemption_clause") or "",
        raw_text=raw.get("raw_text") or "",
        confidence=_clamp01(raw.get("confidence", 0.0)),
    )


def _clamp01(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def _int_or_none(x) -> int | None:
    try:
        return int(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(x) -> float | None:
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def extract_requirement(criterion_text: str) -> Requirement:
    """Describe one eligibility gate. Never raises, never sees the bidder."""
    try:
        r = generate_json(_PROMPT.replace("{{CRITERION}}", criterion_text),
                          ELIGIBILITY_REQUIREMENT_SCHEMA)
    except ModelError:
        return Requirement(check=CheckType.NONE, raw_text=criterion_text, confidence=0.0)

    try:
        check = CheckType(r.get("check", "none"))
    except ValueError:
        # The enum is the allowlist; anything outside it is not a check we can perform.
        check = CheckType.NONE
    return Requirement(
        check=check,
        operator=r.get("operator"),
        threshold_cr=_float_or_none(r.get("threshold_cr")),
        fy_count=_int_or_none(r.get("fy_count")),
        fy_labels=tuple(r.get("fy_labels") or ()),
        min_count=_int_or_none(r.get("min_count")),
        years_window=_int_or_none(r.get("years_window")),
        certification_name=r.get("certification_name"),
        registration_key=r.get("registration_key"),
        exemption_for=tuple(r.get("exemption_for") or ()),
        exemption_clause=r.get("exemption_clause") or "",
        raw_text=r.get("raw_text") or criterion_text,
        confidence=_clamp01(r.get("confidence", 0.0)),
    )
