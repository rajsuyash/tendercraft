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
from dataclasses import dataclass, replace

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

#: Acceptance nudges ties too, on the same principle and for the same reason. An answer a human
#: has taken four times is EVIDENCE, not proof — the fourth tender may simply have resembled
#: the first three — so the boost is small and saturates fast. `answer_usages` has been written
#: since 0027 and read by nothing; this is what makes the receipts do work.
_USAGE_STEP = 0.03
_USAGE_CAP = 5

#: Two answers this similar are the same answer under two bid names. Above the floor because a
#: wrong merge hides a genuinely different answer behind a count nobody expands.
_DUPLICATE_FLOOR = 0.85


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
    #: How many times a human has accepted this answer into a draft (answer_usages).
    times_used: int = 0
    #: How many OTHER bids carried a near-identical answer, collapsed behind this one. Shown as
    #: "also in N bids" — the same repetition that used to read as noise, reading as confidence.
    also_in_bids: int = 0


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

    Near-identical answers are collapsed BEFORE the limit is applied. Doing it after would
    truncate three duplicates off one bid and then dedupe them to one, filling a three-slot
    panel with a single answer — which is how a workspace's sixth tender ends up with a
    suggestion panel less useful than its second.
    """
    scored: list[tuple[float, str, Suggestion]] = []
    for row in answers:
        if section_key and row.get("section_key") and row["section_key"] != section_key:
            continue
        raw = similarity(requirement_text, row.get("requirement_text", ""))
        if raw < _MIN_SIMILARITY:
            continue
        outcome = row.get("outcome") or "unknown"
        used = int(row.get("times_used") or 0)
        scored.append((
            raw
            * _OUTCOME_WEIGHT.get(outcome, _OUTCOME_WEIGHT["unknown"])
            * (1.0 + min(used, _USAGE_CAP) * _USAGE_STEP),
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
                times_used=used,
            ),
        ))
    # Weighted score first, then recency — a newer answer to an equally-matching requirement
    # is the one whose facts are likeliest to still hold.
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return collapse_duplicates([s for _, _, s in scored])[:limit]


def _near_duplicate(a: str, b: str) -> bool:
    """Are these the same answer under two bid names?

    Both directions, and the WEAKER one decides. `similarity` is deliberately asymmetric (it
    asks what fraction of the first text's distinctive words the second contains), so a
    two-line answer fully contained in a three-page one scores 1.0 one way round. Taking the
    minimum means a short answer is never swallowed by a long one that merely mentions it.
    """
    return min(similarity(a, b), similarity(b, a)) >= _DUPLICATE_FLOOR


def collapse_duplicates(ranked: Sequence[Suggestion]) -> tuple[Suggestion, ...]:
    """Fold near-identical answers into the best-ranked one, carrying a count.

    After six tenders a workspace holds six near-identical answers to "Understanding of the
    Project" — one per bid, all scoring within a few points. The panel showed three of them,
    the user learned it was noise, and stopped reading it. Growth has to mean convergence.

    The head is the one the ranking already chose, so outcome, recency and acceptance all still
    decide WHICH version is offered. What the fold adds is that repetition now reads as
    confidence ("also in 3 bids") instead of as three wasted rows.
    """
    kept: list[Suggestion] = []
    extra: dict[str, int] = {}
    for s in ranked:
        head = next((k for k in kept if _near_duplicate(k.answer_text, s.answer_text)), None)
        if head is None:
            kept.append(s)
            continue
        extra[head.answer_id] = extra.get(head.answer_id, 0) + 1
    return tuple(
        replace(k, also_in_bids=extra[k.answer_id]) if k.answer_id in extra else k for k in kept
    )


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
