"""Section drafter — writes ONE long-form proposal section (Module B, document layer).

Differs from pipeline.drafter in three ways: it emits STRUCTURE (subsections with
headings), it runs under SectionKind.NARRATIVE so approach prose can stand uncited, and
it targets a real word count. The deterministic layer still decides every sentence's
class, so narrative-eligibility never becomes an escape hatch from cite-or-flag.

Model failure or thin context -> a placeholder section, never invented prose (G-5).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.deterministic.drafting import DraftSentence, validate_draft
from app.deterministic.types import SectionKind, SentenceClass

from .client import ModelError, generate_json
from .schemas import SECTION_SCHEMA

_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
_TEMPLATE = (_PROMPTS / "section_drafter.md").read_text()

_MAX_EVIDENCE_CHARS = 1500  # matches the retrieval chunk window


def _load_briefs() -> dict[str, str]:
    """Per-section briefs from one file, split on '### <key>'.

    One file rather than nine keeps the invariant rules in a single place and avoids a
    nine-way sync problem, while still honouring "prompts are files, never string literals".
    """
    briefs: dict[str, str] = {}
    key: str | None = None
    buf: list[str] = []
    for line in (_PROMPTS / "section_briefs.md").read_text().splitlines():
        if line.startswith("### "):
            if key:
                briefs[key] = "\n".join(buf).strip()
            key, buf = line[4:].strip(), []
        elif key:
            buf.append(line)
    if key:
        briefs[key] = "\n".join(buf).strip()
    return briefs


_BRIEFS = _load_briefs()


def placeholder_body(heading: str) -> str:
    return (
        f"⬚ **{heading} — not yet drafted.** The content library does not contain enough "
        "material to write this section. Upload relevant past proposals, method statements "
        "or capability documents, then regenerate."
    )


@dataclass(frozen=True)
class DraftedSection:
    key: str
    heading: str
    body_md: str
    status: str  # 'drafted' | 'placeholder' | 'unverified'
    sentences: list[dict]
    flags: list[dict]
    confidence: float
    word_count: int
    narrative_sentences: int


def _placeholder(key: str, heading: str) -> DraftedSection:
    return DraftedSection(
        key=key, heading=heading, body_md=placeholder_body(heading), status="placeholder",
        sentences=[], flags=[], confidence=0.0, word_count=0, narrative_sentences=0,
    )


def _proposed_class(s: dict) -> SentenceClass:
    """Read the model's proposed class, defaulting to the strict one on anything unexpected."""
    return (
        SentenceClass.NARRATIVE
        if s.get("proposed_class") == SentenceClass.NARRATIVE
        else SentenceClass.CLAIM
    )


def draft_section(
    key: str, heading: str, target_words: int, tender_context: str, evidence_chunks: list[dict],
    needs_bidder_evidence: bool = False,
) -> DraftedSection:
    """Draft one narrative section. `evidence_chunks`: [{id, name, text}]. Never raises.

    `needs_bidder_evidence` decides whether the model's own `has_sufficient_context: false`
    is honoured. For approach/methodology/QA/risk sections it is not: those are written from
    the tender requirements plus professional practice, and the model was observed
    self-vetoing a perfectly writable section when retrieval handed it noisy evidence.
    """
    brief = _BRIEFS.get(key)
    if not brief:
        return _placeholder(key, heading)

    evidence_str = (
        "\n\n".join(
            f"[{c['id']}] {c.get('name', '')}: {c.get('text', '')[:_MAX_EVIDENCE_CHARS]}"
            for c in evidence_chunks
        )
        or "(no evidence chunks retrieved — write the proposed approach from professional "
        "practice; do not assert bidder facts)"
    )

    prompt = (
        _TEMPLATE.replace("{{SECTION_KEY}}", key)
        .replace("{{SECTION_HEADING}}", heading)
        .replace("{{SECTION_BRIEF}}", brief)
        .replace("{{TARGET_WORDS}}", str(target_words))
        .replace("{{TENDER_CONTEXT}}", tender_context)
        .replace("{{EVIDENCE}}", evidence_str)
    )

    try:
        r = generate_json(prompt, SECTION_SCHEMA)
    except ModelError:
        return _placeholder(key, heading)

    subs = r.get("subsections") or []
    if not subs:
        return _placeholder(key, heading)
    if needs_bidder_evidence and not r.get("has_sufficient_context", False):
        return _placeholder(key, heading)

    valid_ids = {c["id"] for c in evidence_chunks}
    body_parts: list[str] = []
    all_sentences: list[DraftSentence] = []
    all_flags: list[dict] = []

    for sub in sorted(subs, key=lambda s: s.get("order", 0)):
        raw = [
            DraftSentence(
                text=s.get("text", ""),
                citations=tuple(s.get("citations", []) or ()),
                cls=_proposed_class(s),
            )
            for s in (sub.get("sentences") or [])
            if s.get("text")
        ]
        if not raw:
            continue
        # NARRATIVE section: approach prose may stand uncited, but classify_sentence still
        # coerces anything evidence-shaped back to CLAIM, so the gate cannot be dodged.
        v = validate_draft(raw, valid_ids, SectionKind.NARRATIVE)
        all_sentences.extend(v.sentences)
        all_flags.extend({"text": f.text, "reason": f.reason} for f in v.flags)
        body_parts.append(f"### {sub.get('heading', '').strip()}\n\n"
                          + " ".join(s.text for s in v.sentences))

    if not all_sentences:
        return _placeholder(key, heading)

    body_md = "\n\n".join(body_parts)
    return DraftedSection(
        key=key,
        heading=heading,
        body_md=body_md,
        status="unverified" if all_flags else "drafted",
        sentences=[
            {
                "text": s.text,
                "citations": list(s.citations),
                "cls": str(s.cls),
                "requires_citation": s.requires_citation,
                "is_financial": s.is_financial,
            }
            for s in all_sentences
        ],
        flags=all_flags,
        confidence=float(r.get("confidence", 0.0) or 0.0),
        word_count=len(body_md.split()),
        narrative_sentences=sum(
            1 for s in all_sentences if s.cls is SentenceClass.NARRATIVE
        ),
    )
