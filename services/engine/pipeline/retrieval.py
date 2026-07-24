"""Per-criterion evidence selection (deterministic — no model, no I/O).

Picks WHICH library documents the drafter sees for one criterion. This is retrieval, not a
verdict (PRD §2.4): it never decides eligibility, only which chunks to hand the drafter.

- A document the bidder attached to this item (readiness_decisions.document_id) is PINNED FIRST,
  then backed by the most-relevant library docs — so "attach a doc" reliably steers the draft,
  but a thin/poorly-extracted attachment still gets backed by the best matching evidence.
- With no attachment the criterion gets its most lexically-relevant docs (top-K), so each
  requirement is drafted from the right evidence instead of the whole library dumped at every one.
- If nothing scores, fall back to all docs — never starve a criterion into a false placeholder.
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LEN = 4  # drop short filler ("of", "the", "not") without a stopword list
_DEFAULT_TOP_K = 4


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) >= _MIN_TOKEN_LEN}


def _score(criterion_tokens: set[str], doc: dict) -> int:
    doc_tokens = _tokens(f"{doc.get('name', '')} {doc.get('text', '')}")
    return len(criterion_tokens & doc_tokens)


def select_evidence(
    criterion_text: str, docs: list[dict], pinned_id: str | None = None,
    top_k: int = _DEFAULT_TOP_K,
) -> list[dict]:
    """Evidence chunks for one criterion. `docs`: [{id, name, text}]. Pinned doc first (backed by
    relevant others), else top-K by lexical overlap, else all docs (never empty when docs is)."""
    if not docs:
        return []
    crit = _tokens(criterion_text)
    # stable sort keeps original order among equal scores (Python sort is stable)
    scored = sorted(((_score(crit, d), d) for d in docs), key=lambda x: x[0], reverse=True)
    ranked = [d for s, d in scored if s > 0][:top_k]
    if pinned_id:
        pinned = next((d for d in docs if d.get("id") == pinned_id), None)
        if pinned and pinned["id"] not in {d["id"] for d in ranked}:
            # Guarantee the attached doc is present, but keep RELEVANCE ordering — a noisy/thin
            # attachment (e.g. a letterhead scan) must not lead and bury the good cert behind it.
            ranked = [*ranked, pinned][: top_k + 1]
    return ranked or docs
