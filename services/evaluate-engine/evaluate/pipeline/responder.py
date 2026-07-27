"""A bidder's answer to one published criterion, located in their submission.

Genuinely new — the bidder product WRITES proposals, it never reads someone else's. What
matters here is the failure mode: when the value cannot be found, this returns nothing, which
`deterministic/screening.py` renders as `Not stated` and routes to a human. It must never
guess, because the value it returns decides whether a bidder is disqualified.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .client import ModelError, generate_json
from .schemas import RESPONSE_SCHEMA

_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "extract_response.md"
_MAX_PAGES_PER_CALL = 12


@dataclass(frozen=True)
class ExtractedResponse:
    criterion_id: str
    stated_value: str | None
    excerpt: str
    anchor_page: int | None
    confidence: float


def _relevant(pages: list[tuple[int, str]], criterion_text: str) -> list[tuple[int, str]]:
    """Cheap keyword pre-filter so a 200-page bid is not sent whole for every criterion.

    Deliberately generous: it is far worse to miss the page holding the answer (the bidder
    then reads as `Not stated`) than to include a few irrelevant ones.
    """
    words = {w.lower().strip(".,;:()") for w in criterion_text.split() if len(w) > 5}
    if not words:
        return pages[:_MAX_PAGES_PER_CALL]
    scored = sorted(
        pages,
        key=lambda pt: -sum(1 for w in words if w in pt[1].lower()),
    )
    top = [p for p in scored[:_MAX_PAGES_PER_CALL] if any(w in p[1].lower() for w in words)]
    return top or pages[:_MAX_PAGES_PER_CALL]


def extract_response(
    criterion_id: str, criterion_text: str, required: str | None,
    pages: list[tuple[int, str]],
) -> ExtractedResponse:
    none = ExtractedResponse(criterion_id, None, "", None, 0.0)
    try:
        tmpl = _PROMPT.read_text()
    except OSError:
        return none

    chosen = _relevant(pages, criterion_text)
    if not chosen:
        return none
    body = "\n\n".join(f"--- PAGE {p} ---\n{t[:4000]}" for p, t in chosen)
    prompt = (tmpl.replace("{{CRITERION}}", criterion_text)
                  .replace("{{REQUIRED}}", required or "(not specified)")
                  .replace("{{PAGES}}", body))
    try:
        out = generate_json(prompt, RESPONSE_SCHEMA)
    except ModelError:
        return none

    if not out.get("found"):
        return none
    value = str(out.get("stated_value", "")).strip()
    if not value:
        return none
    excerpt = str(out.get("excerpt", ""))[:600]
    # Anchor the answer to the page whose text actually contains the excerpt, rather than
    # trusting a page number the model reports. A citation that points at the wrong page is
    # worse than no citation — an officer checks it, finds nothing, and stops trusting all of them.
    page = None
    probe = excerpt[:60].strip()
    if probe:
        page = next((p for p, t in chosen if probe and probe in t), None)
    if page is None:
        page = chosen[0][0]
    try:
        conf = max(0.0, min(1.0, float(out.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0
    return ExtractedResponse(criterion_id, value, excerpt, page, conf)
