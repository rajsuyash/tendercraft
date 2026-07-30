"""Assign a relevance band to in-scope tenders: model first, deterministic keywords as fallback.

**Nothing in this file removes a tender from anything.** It writes `relevance_band`,
`relevance_reason` and `relevance_source` and stops. Ordering is the caller's; inclusion is
`app/deterministic/discovery.py`'s, from user-authored rules only (G-9). The guardrail script
fails the build if a function named exclude/suppress/hide/filter_out/drop appears here, which is
the structural version of that promise.

Two things make this affordable on a 48,000-tender portal:

  * **only in-scope items are scored** — the excluded bucket is ordered by nothing anyone reads;
  * **an input hash short-circuits re-scoring** — the band is a function of the vendor's
    capability text, their keywords and the tender's own title/categories, so if none of those
    changed the answer cannot have. Without it, every rule edit would re-band the whole feed
    (PRD §4.1's cost policy).
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import UTC, datetime
from typing import Any

from ..deterministic.discovery import keyword_relevance

log = logging.getLogger("tendercraft.engine")

# Same shape as GEM_DOC_BUDGET in ingest.py: a ceiling so a scheduler misfire cannot turn into
# an unbounded model bill.
DEFAULT_BUDGET = int(os.environ.get("RELEVANCE_BUDGET", "40"))

BAND_ORDER = {"high": 0, "medium": 1, "low": 2}


def input_hash(capability: str, keywords: list[str], opportunity: dict[str, Any]) -> str:
    """Everything the band depends on. Change any of it and the band is recomputed; change
    nothing and it is not."""
    material = "\x1f".join(
        [
            (capability or "").strip(),
            ",".join(sorted(k.strip().lower() for k in (keywords or []) if k.strip())),
            str(opportunity.get("title") or ""),
            ",".join(opportunity.get("category_codes") or []),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _deterministic_row(opportunity: dict[str, Any], keywords: list[str], digest: str) -> dict:
    match = keyword_relevance(opportunity, keywords)
    return {
        "relevance_band": match.band,
        "relevance_reason": match.reason,
        # Recorded so a model outage is visible in the UI rather than silently changing what
        # "high" means on the page (EC-6's honesty rule, applied to ranking).
        "relevance_source": "keyword",
        "relevance_input_hash": digest,
        "relevance_scored_at": datetime.now(UTC).isoformat(),
    }


def bands_for(
    opportunities: list[dict[str, Any]],
    *,
    capability_statement: str | None,
    keywords: list[str] | None,
    existing: dict[str, str] | None = None,
    budget: int = DEFAULT_BUDGET,
) -> dict[str, dict[str, Any]]:
    """→ {opportunity_id: patch}. Every opportunity gets a band; only some cost a model call.

    `existing` maps opportunity_id -> the hash already stored, so unchanged pairs are skipped
    entirely. A tender the model does not answer for falls back to keyword banding rather than
    being left blank, because a missing band would sort unpredictably and read as a bug.
    """
    keywords = [k for k in (keywords or []) if k and k.strip()]
    capability = (capability_statement or "").strip()
    existing = existing or {}

    patches: dict[str, dict[str, Any]] = {}
    stale: list[dict[str, Any]] = []
    for opportunity in opportunities:
        digest = input_hash(capability, keywords, opportunity)
        if existing.get(str(opportunity.get("id"))) == digest:
            continue  # nothing that feeds the band has changed
        stale.append(opportunity)
        patches[str(opportunity["id"])] = _deterministic_row(opportunity, keywords, digest)

    if not stale:
        return {}

    # With nothing said about the vendor there is nothing to be semantic about, and calling a
    # model to compare a tender against an empty string is a bill for a guess.
    if not capability:
        log.info("relevance: %d banded by keyword (no capability statement)", len(stale))
        return patches

    to_score = sorted(stale, key=lambda o: o.get("closing_at") or "9999")[:budget]
    try:
        from ...pipeline import relevance as model_relevance
    except ImportError:  # pragma: no cover - import shape differs only under odd packaging
        from pipeline import relevance as model_relevance  # type: ignore[no-redef]

    scored = model_relevance.score(capability, keywords, to_score)
    for opportunity_id, result in scored.items():
        patch = patches.get(opportunity_id)
        if patch is None:
            continue
        patch.update(
            {
                "relevance_band": result.band,
                # The citation, in the bidder's own words. Kept alongside the rationale so the
                # row can show WHY without the user opening anything.
                "relevance_reason": (
                    f"{result.rationale} (matches: {result.matched_capability})"
                    if result.matched_capability
                    else result.rationale
                ),
                "relevance_source": "model",
            }
        )

    log.info(
        "relevance: %d scored by model, %d by keyword fallback, %d skipped as unchanged",
        len(scored),
        len(stale) - len(scored),
        len(opportunities) - len(stale),
    )
    return patches
