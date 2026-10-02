"""Match predicted requirements to golden requirements, within one tender.

Two conditions must BOTH hold for a (predicted, golden) pair to be a candidate match:

  1. Page-range overlap — the predicted and golden `[page_number, page_end]` ranges intersect.
     This is a hard gate, not a score bonus: a requirement correctly worded but anchored to the
     wrong page is not a match (IMPLEMENTATION_PLAN §M-j control (c): shifting every anchor by
     +1 must collapse recall, which it can only do if page agreement is required).
  2. Token coverage ≥ TOKEN_MATCH_THRESHOLD — the fraction of the GOLDEN requirement's
     (normalised) words that also appear in the prediction. ARCHITECTURE §7 names this
     threshold directly for mandatory-recall ("≥0.8 token overlap") and the recall/precision
     row reuses "the same matcher". A paraphrase sharing no vocabulary scores 0 and is reported
     as a miss (control (b)), never silently credited via the page match alone.

Among all candidate pairs, assignment is GREEDY BY SCORE: highest-coverage pairs are taken
first, each golden/predicted row used at most once. This is a stated simplification, not an
optimal (Hungarian) assignment — for the corpus sizes here (tens of rows per tender) a
greedy pass over a small candidate set gives the same answer as an optimal one in the
overwhelmingly common case (each requirement has at most one plausible counterpart), and an
exact assignment solver is not worth the code for a starter harness.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

TOKEN_MATCH_THRESHOLD = 0.8

_TOKEN_RE = re.compile(r"[a-z]{2,}|\d+(?:\.\d+)?")


def normalize_tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return set(_TOKEN_RE.findall(text))


def page_range(row: dict) -> tuple[int, int]:
    p0 = int(row["page_number"])
    p1 = int(row.get("page_end") or p0)
    return (min(p0, p1), max(p0, p1))


def ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def token_coverage(gold_tokens: set[str], pred_tokens: set[str]) -> float:
    """Fraction of gold_tokens also present in pred_tokens. Asymmetric on purpose: a longer,
    more verbose prediction that still contains every golden word is a full match; a shorter
    one missing golden vocabulary is not, regardless of what else it adds."""
    if not gold_tokens:
        return 0.0
    return len(gold_tokens & pred_tokens) / len(gold_tokens)


@dataclass(frozen=True)
class MatchResult:
    matched: dict[str, str]  # golden requirement_id -> predicted requirement_id
    unmatched_gold: list[str]
    unmatched_pred: list[str]


def match_requirements(golds: list[dict], preds: list[dict]) -> MatchResult:
    pairs: list[tuple[float, int, int]] = []
    pred_tokens_cache = [normalize_tokens(p["requirement_text"]) for p in preds]
    pred_ranges_cache = [page_range(p) for p in preds]

    for gi, g in enumerate(golds):
        gtok = normalize_tokens(g["requirement_text"])
        grange = page_range(g)
        for pi in range(len(preds)):
            if not ranges_overlap(grange, pred_ranges_cache[pi]):
                continue
            cov = token_coverage(gtok, pred_tokens_cache[pi])
            if cov >= TOKEN_MATCH_THRESHOLD:
                pairs.append((cov, gi, pi))

    pairs.sort(key=lambda t: -t[0])
    used_g: set[int] = set()
    used_p: set[int] = set()
    matched: dict[str, str] = {}
    for _cov, gi, pi in pairs:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        matched[golds[gi]["requirement_id"]] = preds[pi]["requirement_id"]

    unmatched_gold = [g["requirement_id"] for i, g in enumerate(golds) if i not in used_g]
    unmatched_pred = [p["requirement_id"] for i, p in enumerate(preds) if i not in used_p]
    return MatchResult(matched, unmatched_gold, unmatched_pred)
