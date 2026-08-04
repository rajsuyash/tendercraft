"""Which prior answer to suggest, and what is no longer true in it (G-FR3). Pure, no I/O.

This is a gate, not a nicety. Two rules it exists to hold:

1. **A suggestion is a suggestion.** Ranking never inserts anything; the only path that writes
   reused text is the accept endpoint, which records a usage row (G-AC6).
2. **Yesterday's true sentence is today's false statement.** A 2024 bid asserting a valid ISO
   9001 is a lie in 2026 if the certificate lapsed. `validate_draft` already catches this
   generically — an expired document is hard-excluded from retrieval, so the claim fails to
   re-cite — but "unverified" without a reason is a shrug. `stale_claims` names the document
   and the date it expired, which is the difference between a flag a bid manager acts on and
   one they dismiss.

Scoring is lexical, matching pipeline/retrieval.py. There is no embedding index in this
codebase and evidence selection already works this way; adding one is an optimisation with a
measurable trigger, not a prerequisite for reuse.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .drafting import _CREDENTIAL

_TOKEN = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LEN = 4
#: A fifth of the requirement's distinctive words must appear in the prior requirement. Below
#: this the suggestion is noise, and noise in a reuse panel trains the user to ignore it —
#: which costs more than showing nothing.
_MIN_SIMILARITY = 0.20
_DEFAULT_LIMIT = 3

#: Outcome nudges ties; it never overrides a materially better textual match. A losing bid's
#: answer to a requirement nobody disputed is still the right answer.
_OUTCOME_WEIGHT = {"won": 1.0, "unknown": 0.92, "lost": 0.85}


@dataclass(frozen=True)
class Suggestion:
    answer_id: str
    requirement_text: str
    answer_text: str
    score: float
    bid_name: str
    authority: str | None
    submitted_on: str | None
    outcome: str
    section_key: str | None


@dataclass(frozen=True)
class StaleClaim:
    """A sentence in a prior answer that leans on a document which has since expired."""

    quote: str
    document: str
    expired_on: str


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) >= _MIN_TOKEN_LEN}


def similarity(a: str, b: str) -> float:
    """Fraction of the NEW requirement's distinctive words present in the prior one.

    Deliberately asymmetric — not Jaccard. A short new requirement fully covered by a long
    prior one is a strong match; Jaccard would punish it for the prior answer's extra words,
    which is exactly backwards for reuse.
    """
    want, have = _tokens(a), _tokens(b)
    if not want:
        return 0.0
    return len(want & have) / len(want)


def rank_answers(
    requirement_text: str,
    answers: Sequence[dict],
    limit: int = _DEFAULT_LIMIT,
    section_key: str | None = None,
) -> tuple[Suggestion, ...]:
    """Top prior answers for one requirement, best first. Empty when nothing clears the floor.

    `answers` rows carry the answer joined to its past bid (see db.get_answers_with_bids).
    A `section_key` narrows to answers mined from the same section when one is known — a
    methodology answer must not be offered for a pre-qualification requirement.
    """
    scored: list[tuple[float, str, Suggestion]] = []
    for row in answers:
        if section_key and row.get("section_key") and row["section_key"] != section_key:
            continue
        raw = similarity(requirement_text, row.get("requirement_text", ""))
        if raw < _MIN_SIMILARITY:
            continue
        outcome = row.get("outcome") or "unknown"
        scored.append((
            raw * _OUTCOME_WEIGHT.get(outcome, _OUTCOME_WEIGHT["unknown"]),
            row.get("submitted_on") or "",
            Suggestion(
                answer_id=row["id"],
                requirement_text=row.get("requirement_text", ""),
                answer_text=row.get("answer_text", ""),
                score=round(raw, 3),
                bid_name=row.get("bid_name") or "",
                authority=row.get("authority"),
                submitted_on=row.get("submitted_on"),
                outcome=outcome,
                section_key=row.get("section_key"),
            ),
        ))
    # Weighted score first, then recency — a newer answer to an equally-matching requirement
    # is the one whose facts are likeliest to still hold.
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return tuple(s for _, _, s in scored[:limit])


def _name_tokens(name: str) -> set[str]:
    """Distinctive words of a document name ("ISO 9001:2015 Certificate" -> iso, 9001, 2015)."""
    return {t for t in _TOKEN.findall(name.lower()) if len(t) >= 3 and t not in _NOISE}


#: Words that appear in half the library and so cannot identify a document.
_NOISE = {"certificate", "certification", "copy", "final", "signed", "document", "pdf", "scan"}


def stale_claims(
    text: str, expired_docs: Sequence[dict], today_iso: str = ""
) -> tuple[StaleClaim, ...]:
    """Sentences in a prior answer that name a credential whose document has expired.

    `expired_docs` is library rows with a `valid_to` already in the past (the caller filters —
    `db.get_valid_library_docs` does the inverse and this reads its rejects). Matching is on
    the document's own distinctive words, so it can only fire on a document the workspace
    actually holds: we never assert that some certification "expired" on the strength of a
    regex alone.
    """
    del today_iso  # the caller decides "today"; kept in the signature for call-site clarity
    found: list[StaleClaim] = []
    seen: set[tuple[str, str]] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if not _CREDENTIAL.search(sentence):
            continue
        words = _tokens(sentence) | {t for t in _TOKEN.findall(sentence.lower()) if len(t) >= 3}
        for doc in expired_docs:
            marks = _name_tokens(doc.get("name") or "")
            # Two matching words, not one: "certificate" alone links nothing, and a single
            # shared token would flag every sentence mentioning ISO against every ISO document.
            if len(marks & words) < 2:
                continue
            key = (sentence[:80], doc.get("name") or "")
            if key in seen:
                continue
            seen.add(key)
            found.append(
                StaleClaim(
                    quote=sentence.strip(),
                    document=doc.get("name") or "",
                    expired_on=doc.get("valid_to") or "",
                )
            )
    return tuple(found)
