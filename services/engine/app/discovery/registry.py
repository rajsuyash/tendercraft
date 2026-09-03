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
    #: When someone confirmed this source's data may be SHOWN to a customer, and by whom.
    #:
    #: Separate from `terms_reviewed` because acquisition and onward display are separate
    #: permissions, and only a licensed source makes them come apart. Reading a public portal
    #: and putting its facts on a screen were settled by one review (GeM §8). A licensed feed
    #: is a contract between the vendor and US: reading it for our own purposes is squarely
    #: within any licence, and showing it to a customer who is not the licensee is a term
    #: somebody has to actually read. A blank date means acquire if you like, but never blend
    #: into anything a customer sees.
    display_reviewed: str = ""
    notes: str = ""


REGISTRY: tuple[Source, ...] = (
    Source(
        source_id="gem_bidplus",
        market="IN",
        connector_url=os.environ.get("GEM_CONNECTOR_URL", ""),
        tier="T2",
        terms_reviewed="2026-07-30",
        reviewer="engineering (agent-assisted probe, human sign-off pending)",
        # Facts-and-deep-links, cleared by the owner's legal review (docs/feedback/usha-martin.md).
        display_reviewed="2026-08-25",
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
        # DELIBERATELY BLANK. The G-8 ruling cleared ACQUISITION; nobody has read the partner
        # agreement, which is what governs showing this data to a customer who is not the
        # licensee. Filling this in is a human act following a contract read, not a config
        # change — see `docs/discovery/source-bidassist.md` and assumption 10 in
        # docs/feedback/usha-martin.md. Until it carries a date, the award sweep declines and
        # says so, rather than quietly blending licensed data into a customer's price screen.
        display_reviewed="",
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
        # Licence Ouverte / EU open data: reuse and redistribution are the licence's whole point.
        display_reviewed="2026-07-31",
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
