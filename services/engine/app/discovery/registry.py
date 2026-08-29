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
        source_id="bidassist",
        market="IN",
        connector_url=os.environ.get("BIDASSIST_CONNECTOR_URL", ""),
        # Not T1 (open data) and not T2 (crawled). A licensed feed is its own tier: the data
        # arrives because a contract says it may, which is a stronger permission than either
        # of the others and a different set of obligations.
        tier="T1-licensed",
        terms_reviewed="2026-08-29",
        reviewer="owner (G-8 divergence ratified; contract read pending for onward display)",
        notes=(
            "Licensed aggregator (Nexizo/BidAssist partner API, key issued to DONNA AI LABS). "
            "Ten Indian portals observed in one 120-row sample, ireps.gov.in largest at 46% "
            "and bidplus.gem.gov.in second at 43% — so roughly half of this feed duplicates "
            "what gem_bidplus already sweeps, deliberately and visibly (records carry "
            "source_fields.overlaps_source). "
            "G-8 RULED ON 2026-08-29 by the decision owner: the guardrail's subject is a "
            "PORTAL — a system whose operator never agreed to be read — and a licensed "
            "vendor's own API key is categorically unlike a portal credential. We still hold "
            "no portal credential and no customer credential; G-1 is untouched. "
            "STILL OPEN, and narrower than the ruling: nobody has read the partner agreement, "
            "which governs showing this data to a THIRD PARTY (UML are not the licensee). "
            "Reading it for our own workspace is squarely within any licence; onward display "
            "is not yet cleared. "
            "ALSO OPEN (G-9): the FEED_SOURCE_ID is a saved query held on the vendor's side — "
            "every sampled row was about wire rope — so feed scope is an exclusion we neither "
            "authored nor can inspect. Re-verify whenever Nexizo changes it. "
            "See docs/discovery/source-bidassist.md."
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
    a source that silently returns nothing is the ET-7 failure mode.

    A source is enabled only when it has BOTH a connector URL and a terms-review date. The
    docstring at the top of this file has always said a blank date means DO NOT ENABLE, and
    until the first unreviewed row arrived nothing made that true — setting one environment
    variable would have been enough to start crawling a source whose terms nobody had read.
    The comment was the guardrail; now the code is.
    """
    return tuple(
        s for s in REGISTRY
        if s.market == market and s.connector_url and s.terms_reviewed.strip()
    )
