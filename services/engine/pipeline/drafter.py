"""Drafter — criterion + retrieved evidence -> cited narrative (Module B, §5.1).

The model drafts and tags each sentence; the deterministic validator (app.deterministic
.drafting) then flags anything uncited or model-authored-financial (B-FR1/B-AC4). Empty
retrieval or insufficient evidence -> a placeholder, never invented prose (B-FR2/G-5).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.deterministic.drafting import DraftSentence, validate_citations

from .client import ModelError, generate_json
from .schemas import DRAFT_SCHEMA

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "drafter.md").read_text()

_PLACEHOLDER = (
    "⬚ Insert evidence for this criterion — no supporting document found in the content "
    "library. Upload the required document, then regenerate."
)


@dataclass(frozen=True)
class DraftedResponse:
    draft_text: str
    draft_status: str  # 'drafted' | 'placeholder' | 'unverified'
    sentences: list[dict]
    flags: list[dict]


def draft_response(criterion_text: str, evidence_chunks: list[dict]) -> DraftedResponse:
    """Draft one response. evidence_chunks: [{id, name, text}]. Never raises."""
    if not evidence_chunks:
        return DraftedResponse(_PLACEHOLDER, "placeholder", [], [])

    evidence_str = "\n".join(
        f"[{c['id']}] {c.get('name', '')}: {c.get('text', '')[:1200]}" for c in evidence_chunks
    )
    prompt = _PROMPT.replace("{{CRITERION}}", criterion_text).replace("{{EVIDENCE}}", evidence_str)

    try:
        r = generate_json(prompt, DRAFT_SCHEMA)
    except ModelError:
        return DraftedResponse(_PLACEHOLDER, "placeholder", [], [])

    if not r.get("has_sufficient_evidence", False) or not r.get("sentences"):
        return DraftedResponse(_PLACEHOLDER, "placeholder", [], [])

    valid_ids = {c["id"] for c in evidence_chunks}
    sentences = [
        DraftSentence(
            text=s.get("text", ""),
            citations=tuple(s.get("citations", []) or ()),
            requires_citation=bool(s.get("requires_citation", False)),
            is_financial=bool(s.get("is_financial", False)),
            is_transcluded=False,  # model text is never a transclusion (B-FR3)
        )
        for s in r["sentences"]
    ]
    flags = validate_citations(sentences, valid_ids)
    status = "unverified" if flags else "drafted"

    return DraftedResponse(
        draft_text=" ".join(s.text for s in sentences),
        draft_status=status,
        sentences=[
            {
                "text": s.text,
                "citations": list(s.citations),
                "requires_citation": s.requires_citation,
                "is_financial": s.is_financial,
            }
            for s in sentences
        ],
        flags=[{"text": f.text, "reason": f.reason} for f in flags],
    )
