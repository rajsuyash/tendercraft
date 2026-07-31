"""Source registry — which connector feeds which market, and who reviewed its terms.

`tools/check-discovery-guardrails.sh` requires this file to exist once source adapters do, and
requires every adapter to appear in it: an adapter absent from the registry is an adapter whose
terms were never reviewed, and if a file can crawl without being listed here then the review step
is optional in practice.

It is also what makes `market` a routing decision rather than a branch. Adding Germany is a row
in this table plus a query parameter, because TED is EU-wide — not a new service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    source_id: str
    market: str
    connector_url: str
    tier: str
    #: Who checked the terms of use and when. A blank date means DO NOT ENABLE.
    terms_reviewed: str
    reviewer: str
    notes: str = ""


REGISTRY: tuple[Source, ...] = (
    Source(
        source_id="gem_bidplus",
        market="IN",
        connector_url=os.environ.get("GEM_CONNECTOR_URL", ""),
        tier="T2",
        terms_reviewed="2026-07-30",
        reviewer="engineering (agent-assisted probe, human sign-off pending)",
        notes=(
            "Listing is session-gated; the anonymous WAF cookie is argued against G-8 in "
            "docs/discovery/source-gem.md. Content is copyright-restricted, so the feed shows "
            "facts and deep links rather than reproducing tender text."
        ),
    ),
    Source(
        source_id="ted",
        market="FR",
        connector_url=os.environ.get("TED_CONNECTOR_URL", ""),
        tier="T1",
        terms_reviewed="2026-07-31",
        reviewer="engineering (agent-assisted probe, human sign-off pending)",
        notes=(
            "EU open data. No robots restrictions on api.ted.europa.eu, no authentication, no "
            "reproduction clause. Above EU threshold only, so smaller French tenders are out of "
            "reach. BOAMP would cover them but disallows /api/ for every agent but Googlebot — "
            "recorded as a decision for a human, not resolved unilaterally."
        ),
    ),
)


def for_market(market: str) -> tuple[Source, ...]:
    """Every enabled source for a market. Empty is a configuration error, not an empty feed —
    a source that silently returns nothing is the ET-7 failure mode."""
    return tuple(s for s in REGISTRY if s.market == market and s.connector_url)
