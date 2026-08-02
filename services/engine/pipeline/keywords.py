"""Propose short keywords for a vendor from their own words, their existing terms and their site.

**This component cannot change what a bidder sees.** It returns candidates to a screen; a human
ticks the ones they want and only then are they saved. That separation is not politeness, it is
G-9: capability keywords feed `keyword_match_required`, the one rule that HIDES tenders, so a
model that wrote them directly would be deciding what a bidder never sees — by a longer route
than the one the guardrail names, with the same result. The endpoint that calls this saves
nothing, and `app/deterministic/keywords.py` is the fallback when the model is unavailable.

Shaped like `pipeline/relevance.py`: prompt from a file, schema-enforced JSON, one retry and a
timeout inside `client.generate_json`, `ModelError` raised rather than a guess returned.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .client import ModelError, generate_json
from .schemas import KEYWORDS_SCHEMA

log = logging.getLogger("tendercraft.pipeline")

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "keywords.md").read_text()

#: More than this and the vendor is reviewing a list instead of choosing from one, which is how
#: an "approve all" click happens and the human confirmation becomes a formality.
DEFAULT_LIMIT = 18

#: A vendor's homepage is mostly navigation. Enough to reach the product names, capped so a
#: large site cannot turn one suggestion into an expensive call.
WEBSITE_CHARS = 6000

#: Matched whole against a tender title, so a long phrase matches nothing — the exact defect
#: this component exists to repair. Anything longer is dropped rather than shown.
MAX_WORDS = 3

SOURCES = ("statement", "existing", "website")


@dataclass(frozen=True)
class Suggestion:
    keyword: str
    source: str
    evidence: str


def suggest(
    capability_statement: str,
    existing_keywords: list[str],
    website_text: str = "",
    limit: int = DEFAULT_LIMIT,
) -> list[Suggestion]:
    """→ candidate keywords, best first.

    Empty is an answer, not an error. `ModelError` is raised only when the RESPONSE is unusable
    — the two cases must stay distinct, or a model correctly refusing an injected instruction
    gets reported to the vendor as an outage.
    """
    statement = (capability_statement or "").strip()
    existing = [k for k in (existing_keywords or []) if k and k.strip()]
    if not statement and not existing and not website_text.strip():
        # Nothing to read. Calling a model to invent keywords from an empty profile is how a
        # vendor ends up with a gate built on terms nobody chose.
        return []

    prompt = (
        _PROMPT.replace("{capability_statement}", statement or "(not provided)")
        .replace("{existing_keywords}", ", ".join(existing) or "(none)")
        .replace("{website_text}", (website_text or "").strip()[:WEBSITE_CHARS] or "(none)")
        .replace("{limit}", str(limit))
    )

    raw = generate_json(prompt, KEYWORDS_SCHEMA)
    items = raw.get("keywords")
    if not isinstance(items, list):
        raise ModelError("keywords: response carried no keywords array")

    out: list[Suggestion] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        keyword = str(item.get("keyword") or "").strip().lower()
        evidence = str(item.get("evidence") or "").strip()
        source = str(item.get("source") or "").strip()
        if not keyword or keyword in seen:
            continue
        if len(keyword.split()) > MAX_WORDS:
            # The model proposing a sentence is the very failure being repaired; drop it rather
            # than offer a term that cannot match.
            log.info("keywords: dropped an over-long proposal (%d words)", len(keyword.split()))
            continue
        if source not in SOURCES or not evidence:
            # Cite-or-drop, the rule the drafter and the relevance bander already follow. A term
            # the model cannot point at is a term it invented, and the vendor has no way to
            # check it.
            continue
        seen.add(keyword)
        out.append(Suggestion(keyword=keyword, source=source, evidence=evidence))

    if not out:
        # An empty result is a legitimate ANSWER, not a failure, and the two must not be
        # conflated: a statement with no product in it ("we supply various goods") should yield
        # nothing, and a website that tries to instruct the model should yield nothing. Raising
        # here would send both down the deterministic fallback and label the model unavailable
        # when it had in fact behaved correctly — and, for the injection case, would have
        # reported a refusal as an outage.
        if items:
            # Non-empty in, nothing out: every proposal was uncited, over-long or malformed.
            # Worth a line, because that IS a model-quality signal even though the safe response
            # is still to propose nothing.
            log.warning("keywords: all %d proposals were dropped as unusable", len(items))
        return []
    log.info("keywords: proposed %d terms", len(out))
    return out[:limit]
