"""Relevance band (F-FR11) — the model's fit signal for a tender against a vendor capability.

**This component ranks. It cannot hide anything.** Its output reaches `relevance_band` and
`relevance_reason` on `opportunity_matches` and nothing else; the include/exclude decision is
made by `app/deterministic/discovery.py` from user-authored rules, which is model-import-free
and enforced as such by CI. That separation is G-9, and it is the reason a wrong band here costs
a bidder one badly-ordered row rather than a tender they never saw.

Shaped like `pipeline/analyzer.py`: prompt from a file, schema-enforced JSON, one retry and a
timeout inside `client.generate_json`, and `ModelError` raised rather than a guess returned. The
caller falls back to deterministic keyword banding and records that it did.

Tenders are batched per call because a national portal produces feed-sized volumes and one call
per tender is the difference between a few paise and a real bill.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .client import ModelError, generate_json
from .schemas import RELEVANCE_SCHEMA

log = logging.getLogger("tendercraft.pipeline")

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "relevance.md").read_text()

BANDS = ("high", "medium", "low")

# One call per tender is wasteful; too many per call and a single malformed row costs the whole
# batch. Ten keeps a failed batch cheap to redo and the prompt well inside context.
BATCH_SIZE = 10


@dataclass(frozen=True)
class RelevanceResult:
    opportunity_id: str
    band: str
    rationale: str
    matched_capability: str
    confidence: float


def _clamp01(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _tender_line(opportunity: dict) -> dict:
    """What the model is allowed to see about one tender.

    Title, categories and authority only — never the bid document. The document is 100 KB of
    boilerplate whose eligibility facts are already parsed deterministically, and sending it
    would multiply the cost of this signal by two orders of magnitude for no extra judgement.
    """
    return {
        "opportunity_id": str(opportunity.get("id") or ""),
        "title": (opportunity.get("title") or "")[:400],
        "categories": ", ".join((opportunity.get("category_codes") or [])[:6]),
        "authority": opportunity.get("authority") or "",
    }


LANGUAGE_NAMES = {"fr": "French", "en": "English", "de": "German", "es": "Spanish"}


def score_batch(
    capability_statement: str,
    keywords: list[str],
    opportunities: list[dict],
    language: str = "en",
) -> list[RelevanceResult]:
    """Band one batch of tenders. Raises ModelError; never returns a guess.

    `language` is the language the RATIONALE is written in — our commentary to the bidder. It is
    deliberately not the tender's language: a French workspace reads French explanations beside
    French tender text, and the tender text itself is never translated.
    """
    if not opportunities:
        return []

    prompt = (
        _PROMPT.replace("{capability_statement}", capability_statement.strip() or "(not provided)")
        .replace("{output_language}", LANGUAGE_NAMES.get(language, "English"))
        .replace("{keywords}", ", ".join(keywords) or "(none)")
        .replace(
            "{tenders}",
            json.dumps([_tender_line(o) for o in opportunities], ensure_ascii=False, indent=1),
        )
    )

    raw = generate_json(prompt, RELEVANCE_SCHEMA)
    results = raw.get("results")
    if not isinstance(results, list):
        raise ModelError("relevance: response carried no results array")

    by_id: dict[str, RelevanceResult] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        band = str(item.get("band", "")).lower()
        if band not in BANDS:
            # The schema already constrains this; a value outside it means the provider ignored
            # the schema, and a band we cannot interpret must not become a silent "medium".
            continue
        matched = str(item.get("matched_capability") or "").strip()
        # Cite-or-drop, the same rule the drafter follows (G-5): a fit the model cannot point at
        # in the bidder's own words is not a fit. Demote rather than discard, because demoting
        # keeps the tender visible and only moves it down the page.
        if band != "low" and not matched:
            band = "low"
        by_id[str(item.get("opportunity_id"))] = RelevanceResult(
            opportunity_id=str(item.get("opportunity_id")),
            band=band,
            rationale=str(item.get("rationale") or "").strip(),
            matched_capability=matched,
            confidence=_clamp01(item.get("confidence")),
        )

    # Return in request order, skipping any the model failed to answer for. The caller bands
    # those deterministically rather than inventing one.
    ordered = [by_id[str(o.get("id"))] for o in opportunities if str(o.get("id")) in by_id]
    if not ordered:
        raise ModelError("relevance: no usable results in response")
    log.info("relevance: banded %d/%d tenders", len(ordered), len(opportunities))
    return ordered


def score(
    capability_statement: str,
    keywords: list[str],
    opportunities: list[dict],
    language: str = "en",
) -> dict[str, RelevanceResult]:
    """Band a list of tenders, batched. Partial failure is partial output, never an exception —
    a batch that fails leaves those tenders unbanded for the caller's deterministic fallback."""
    out: dict[str, RelevanceResult] = {}
    for start in range(0, len(opportunities), BATCH_SIZE):
        batch = opportunities[start : start + BATCH_SIZE]
        try:
            for result in score_batch(capability_statement, keywords, batch, language):
                out[result.opportunity_id] = result
        except ModelError as exc:
            log.warning("relevance: batch of %d failed (%s) — falling back", len(batch), exc)
    return out
