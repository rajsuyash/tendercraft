"""RFP page text -> published criteria with confidence and anchors.

Ported by copy from the bidder extractor (F13: no shared module). Same contract in both
products: AI proposes, deterministic code decides. Sub-0.80 confidence is flagged for human
confirmation; the model never self-certifies, and an empty or failed extraction returns []
so the caller routes to manual entry rather than inventing a criterion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..ingest import CONFIRM_THRESHOLD
from .client import ModelError, generate_json
from .schemas import CRITERIA_SCHEMA

_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "extract_criteria.md"
_VALID_OPS = {">=", "<=", "=", "present"}


@dataclass(frozen=True)
class ExtractedCriterion:
    text: str
    kind: str                  # "pq" | "technical"
    max_marks: int
    compare_kind: str
    compare_op: str | None
    compare_value: str | None
    anchor_page: int
    anchor_clause: str
    confidence: float

    @property
    def needs_confirmation(self) -> bool:
        return self.confidence < CONFIRM_THRESHOLD


def _clause(v) -> str:
    """Bare clause number: "Cl. 3.1(a)" and "Clause 3.1(a)" both become "3.1(a)"."""
    s = str(v or "").strip()
    return re.sub(r"^(cl(ause)?\.?\s*)", "", s, flags=re.I)[:40]


def _clamp01(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def extract_from_page(page_number: int, page_text: str) -> list[ExtractedCriterion]:
    """Criteria on one page. [] on any failure — the caller routes to manual entry."""
    try:
        prompt = _PROMPT.read_text()
    except OSError:
        return []
    prompt = prompt.replace("{{PAGE_NUMBER}}", str(page_number)).replace(
        "{{PAGE_TEXT}}", page_text[:12000]
    )
    try:
        result = generate_json(prompt, CRITERIA_SCHEMA)
    except ModelError:
        return []

    out: list[ExtractedCriterion] = []
    for c in result.get("criteria", []):
        text = str(c.get("text", "")).strip()
        if not text:
            continue
        kind = c.get("kind") if c.get("kind") in ("pq", "technical") else "pq"
        ck = c.get("compare_kind")
        if ck not in ("numeric", "date", "boolean", "qualitative"):
            ck = "qualitative"
        op = c.get("compare_op") if c.get("compare_op") in _VALID_OPS else None
        # A comparison is only usable when BOTH an operator and a value survived validation.
        # Half a rule would make screening.py compare against nothing and silently return
        # Not stated for every bidder.
        val = str(c["compare_value"]) if c.get("compare_value") not in (None, "") else None

        # One-directional safety coercion, toward the STRICTER reading.
        #
        # `present` only asks whether a value exists, so on a date or numeric criterion it is
        # permissive to the point of being wrong: a live run extracted "certificate valid as on
        # 20/07/2026" as `present 2026-07-20`, which would have passed a certificate that
        # expired five months before the deadline. If the model gave a real threshold, the
        # comparison it meant is `>=`; if it gave none, the rule is not usable and a human sets
        # it. Never coerce the other way — turning a comparison into `present` would let a
        # failing bidder through, and that is the error this product cannot make.
        if ck in ("numeric", "date") and op == "present":
            op = ">=" if val is not None else None

        if ck != "qualitative" and (op is None or val is None):
            ck, op, val = "qualitative", None, None
        try:
            marks = int(float(c.get("max_marks") or 0))
        except (TypeError, ValueError):
            marks = 0
        out.append(ExtractedCriterion(
            text=text, kind=kind, max_marks=max(0, marks), compare_kind=ck,
            compare_op=op, compare_value=val, anchor_page=page_number,
            # The model often echoes the "Cl." label with the number. Seeded data stores the
            # bare number, and the UI adds the label — so keeping it produces "Cl. Cl. 3.1(a)".
            # Normalise at ingest so one convention reaches the database.
            anchor_clause=_clause(c.get("anchor_clause", "")),
            confidence=_clamp01(c.get("confidence", 0.0)),
        ))
    return out
