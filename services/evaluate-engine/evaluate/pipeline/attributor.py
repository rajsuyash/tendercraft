"""Which bidder sent this file (F15). The model PROPOSES; deterministic/attribution.py decides.

The failure this component exists to avoid is not "we could not tell". It is "we were sure and
we were wrong": a file bound to the wrong bidder produces no error anywhere, and the screening
matrix still renders as complete. So the fallback on every failure path is the SAME — no
attribution, file goes to triage, a human looks at it. That costs a click. The alternative
costs an evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .client import ModelError, generate_json
from .schemas import ATTRIBUTION_SCHEMA

_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "attribute_file.md"

# Enough of the document to carry a letterhead, a cover page and a signature block. Reading
# further does not help: identity is stated at the front or it is not stated.
_LEAD_PAGES = 3
_MAX_CHARS = 6000

# A filename is the weakest possible signal, so a proposal resting on it is capped below any
# sane threshold and lands in triage by construction (F15-AC2, case attr-004).
FILENAME_ONLY_CEILING = Decimal("0.4")


@dataclass(frozen=True)
class ProposedAttribution:
    bidder_name: str | None
    document_type: str | None
    envelope: str
    confidence: Decimal
    evidence_text: str | None
    anchor_page: int | None

    @property
    def is_financial(self) -> bool:
        return self.envelope == "financial"


UNATTRIBUTED = ProposedAttribution(None, None, "unknown", Decimal("0"), None, None)


def _lead_text(pages: list[tuple[int, str]]) -> str:
    lead = [f"PAGE {n}:\n{t}" for n, t in pages[:_LEAD_PAGES]]
    return "\n\n".join(lead)[:_MAX_CHARS]


def propose(filename: str, pages: list[tuple[int, str]]) -> ProposedAttribution:
    """Read the front of the document and propose an attribution.

    Never raises. Every failure — no text, malformed output, model outage — returns
    UNATTRIBUTED, which routes the file to a human (F15-ERR3).
    """
    body = _lead_text(pages)
    if not body.strip():
        # No readable text at all. The filename is all that is left, and a filename is not
        # evidence: portal downloads arrive as bid_1.pdf twelve times over.
        return UNATTRIBUTED

    prompt = f"{_PROMPT.read_text()}\n\nFILENAME: {filename}\n\nDOCUMENT:\n{body}"
    try:
        out = generate_json(prompt, ATTRIBUTION_SCHEMA)
    except ModelError:
        return UNATTRIBUTED

    try:
        confidence = Decimal(str(out.get("confidence", 0)))
    except (ArithmeticError, ValueError):
        return UNATTRIBUTED
    confidence = max(Decimal("0"), min(Decimal("1"), confidence))

    name = (out.get("bidder_name") or "").strip() or None
    if name is None:
        # A proposal with no bidder is not a proposal. Do not let a high confidence on an
        # empty name leak through as "resolved".
        return UNATTRIBUTED

    evidence = (out.get("evidence_text") or "").strip() or None
    if evidence is None:
        # F15-AC1 requires an evidence string on every attribution: it is the only way a human
        # can catch the OEM/subcontractor/client trap. No evidence, no confidence.
        confidence = min(confidence, FILENAME_ONLY_CEILING)

    envelope = out.get("envelope") or "unknown"
    if envelope not in ("technical", "financial", "unknown"):
        envelope = "unknown"

    page = out.get("anchor_page")
    return ProposedAttribution(
        bidder_name=name,
        document_type=out.get("document_type") or "other",
        envelope=envelope,
        confidence=confidence,
        evidence_text=evidence,
        anchor_page=int(page) if isinstance(page, (int, float)) else None,
    )


# ── eval hook (evals/attribution) ──────────────────────────────────────────────
def score_eval_case(case: dict) -> tuple[bool, str]:
    """Score one golden case. The component owns its scoring: only it knows its fields."""
    from ..config import get_settings

    expect = case["expect"]
    if case.get("inject") == "model_error":
        import evaluate.pipeline.client as client_mod

        original = client_mod.generate_json
        client_mod.generate_json = _raise_model_error
        try:
            got = propose(case.get("filename", "x.pdf"), [(1, case.get("page_text", ""))])
        finally:
            client_mod.generate_json = original
        if got is not UNATTRIBUTED and got.bidder_name is not None:
            return False, "model failure produced an attribution instead of routing to triage"
        return True, ""

    pages = [(1, case.get("page_text", ""))]
    got = propose(case.get("filename", "x.pdf"), pages)
    threshold = get_settings().attribution_threshold

    if "bidder_name_contains" in expect:
        needle = expect["bidder_name_contains"].lower()
        if not got.bidder_name or needle not in got.bidder_name.lower():
            return False, f"expected bidder containing {needle!r}, got {got.bidder_name!r}"
    if "envelope" in expect and got.envelope != expect["envelope"]:
        return False, f"expected envelope {expect['envelope']}, got {got.envelope}"
    if "confidence_min" in expect and got.confidence < Decimal(str(expect["confidence_min"])):
        return False, f"confidence {got.confidence} below expected minimum"
    if "confidence_max" in expect and got.confidence > Decimal(str(expect["confidence_max"])):
        return False, f"confidence {got.confidence} above expected maximum — over-confident"
    if expect.get("goes_to_triage") and got.confidence >= threshold:
        return False, f"should have gone to triage but scored {got.confidence}"
    return True, ""


def _raise_model_error(*_args, **_kwargs):
    raise ModelError("injected")
