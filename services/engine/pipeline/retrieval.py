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
_CHUNK_SIZE = 1500
_CHUNK_OVERLAP = 200


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) >= _MIN_TOKEN_LEN}


def doc_id_of(chunk_id: str) -> str:
    """The library document a chunk id belongs to ("<uuid>#3" -> "<uuid>")."""
    return chunk_id.split("#", 1)[0]


def chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split a document into overlapping windows on paragraph boundaries.

    Without this the drafter saw only the first 1200 chars of each document, so on a
    20-page past proposal it read the cover page and nothing else. Overlap keeps a fact
    that straddles a boundary intact in at least one window.
    """
    if not text:
        return []
    if len(text) <= size:
        return [text]

    out: list[str] = []
    buf = ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 2 > size and buf:
            out.append(buf)
            buf = (buf[-overlap:] + "\n\n" + para) if overlap else para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
        # A single paragraph larger than the window still has to be cut.
        while len(buf) > size:
            out.append(buf[:size])
            buf = buf[size - overlap :] if overlap else buf[size:]
    if buf.strip():
        out.append(buf)
    return out


def chunk_docs(docs: list[dict]) -> list[dict]:
    """[{id, name, text}] -> chunk dicts with ids "<doc_id>#<n>", so a citation resolves
    to the passage that actually supports it rather than to a whole document (B-AC3)."""
    out: list[dict] = []
    for d in docs:
        pieces = chunk_text(d.get("text", "") or "")
        if not pieces:  # keep zero-text docs addressable (name alone can still match)
            pieces = [""]
        for n, piece in enumerate(pieces):
            out.append({"id": f"{d['id']}#{n}", "name": d.get("name", ""), "text": piece})
    return out


def _doc_freq(docs: list[dict]) -> dict[str, int]:
    df: dict[str, int] = {}
    for d in docs:
        for t in _tokens(f"{d.get('name', '')} {d.get('text', '')}"):
            df[t] = df.get(t, 0) + 1
    return df


def _score(criterion_tokens: set[str], doc: dict, df: dict[str, int]) -> float:
    """Overlap weighted by inverse document frequency.

    Raw overlap let long boilerplate win on common words ("bidder", "tender", "shall").
    Weighting by 1/(1+df) makes the discriminating tokens — "9001", "turnover", "udyam" —
    decide the ranking.
    """
    doc_tokens = _tokens(f"{doc.get('name', '')} {doc.get('text', '')}")
    return sum(1.0 / (1 + df.get(t, 0)) for t in criterion_tokens & doc_tokens)


def select_evidence(
    criterion_text: str, docs: list[dict], pinned_id: str | None = None,
    top_k: int = _DEFAULT_TOP_K,
) -> list[dict]:
    """Evidence chunks for one criterion. `docs`: [{id, name, text}]. Pinned doc included
    (backed by relevant others), else top-K by weighted overlap, else all docs."""
    if not docs:
        return []
    crit = _tokens(criterion_text)
    df = _doc_freq(docs)
    # stable sort keeps original order among equal scores (Python sort is stable)
    scored = sorted(((_score(crit, d, df), d) for d in docs), key=lambda x: x[0], reverse=True)
    ranked = [d for s, d in scored if s > 0][:top_k]
    if pinned_id:
        # Match on the DOCUMENT, not the chunk id: the caller pins a library_documents.id
        # but ids here may be chunked ("<doc>#2"). Comparing raw would silently stop
        # pinning the moment chunking turned on.
        present = {doc_id_of(d["id"]) for d in ranked}
        if doc_id_of(pinned_id) not in present:
            pinned = next(
                (d for d in docs if doc_id_of(d["id"]) == doc_id_of(pinned_id)), None
            )
            if pinned:
                # Guarantee the attached doc is present, but keep RELEVANCE ordering — a
                # noisy/thin attachment (e.g. a letterhead scan) must not lead and bury the
                # good cert behind it.
                ranked = [*ranked, pinned][: top_k + 1]
    return ranked or docs
