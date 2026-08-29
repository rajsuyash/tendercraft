"""BidAssist row → the F-FR1 normalized record, and award row → the price ladder.

Same contract `services/gem-connector` and `services/ted-connector` emit, so
`app/discovery/ingest.py` consumes a third source without knowing it is looking at one.

**What is different about this source, and why each difference is handled the way it is.**

*It is an aggregator, not a portal.* One feed carried ten portals in a 120-row sample
(ireps.gov.in 55, bidplus.gem.gov.in 52, then Telangana, AP, Haryana, SAIL, Coal India,
Rajasthan ×2, CPPP). That is the reach we are paying for, and it is also the source of the two
hazards below.

*Reference numbers are only unique WITHIN a portal.* `tenderNoticeNo` is `"77265283"` — a
railways number that some state portal will eventually also issue. The corpus is unique on
`(source_id, portal_ref_no)`, so an unqualified ref would let two unrelated tenders collide
into one row, and F-AC4 is a zero-tolerance gate precisely because a wrong merge deletes a
tender with no error message anywhere. So the ref is host-qualified:
`IREPS.GOV.IN/77265283/TSD/AVD/SOUTHERN-RLY`. Uniqueness then comes from the portal that
issued it, which is the only authority that ever had it.

*Roughly 43% of this feed is GeM, which `gem_bidplus` already sweeps.* Those tenders will
appear twice in the corpus, once per `source_id`. That is deliberate and it is the safe
direction: a duplicate is visible and annoying, a wrong merge is invisible and destructive,
and the connector is the wrong altitude to decide which copy wins. It emits everything,
records the issuing portal in `source_fields.portal_host`, and flags the known overlap so an
engine-side merge can be written later against a field rather than a guess. **Nothing here
filters** — exclusion lives in `app/deterministic/discovery.py` and nowhere else (G-9).

*The vendor's value estimate is not the tender's value.* `isTenderValueEstimated` marks rows
where BidAssist inferred the figure. A value-band rule reads `estimated_value`, so an inferred
number there becomes a wrong exclusion — the same reasoning that leaves the field null on TED.
Inferred values stay in `source_fields` where a human can see them and no rule can act on them.

*Document links are presigned and expire.* `documentKey` carries an `Expires`/`Signature`
querystring good for about a week. Two consequences: the URL is passed through as-is but its
expiry is recorded so a stale link can be explained rather than just 403 at a user, and the
signature is stripped before hashing the snapshot — otherwise `raw_snapshot_ref` would change
on every sweep for a record that had not changed at all, which is a change-detection signal
that reports change constantly and therefore reports nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

SOURCE_ID = "bidassist"

#: The vendor caps page size at 20 and refuses anything larger with `EIPS400`. Measured
#: 2026-08-29: 20 → 200 with rows; 25, 30, 50 and 100 → `invalid page size or page number`.
#: Not a tunable — a constant that reflects somebody else's server.
PAGE_SIZE = 20

#: Portals this feed carries that we also sweep directly. Used to LABEL an overlap, never to
#: drop a row: see the module docstring.
KNOWN_OVERLAP = {"bidplus.gem.gov.in": "gem_bidplus"}

_REF_SEPARATORS = re.compile(r"[\s\-_/\\.]+")

#: Signed-URL parameters that change on every fetch without the document changing.
_VOLATILE_QUERY_KEYS = frozenset({"Expires", "Signature", "Key-Pair-Id", "Policy"})


def normalize_ref(raw: str | None) -> str | None:
    """F-FR6: whitespace, case and separators only. No edit distance, no fuzzy matching —
    a wrong merge deletes a tender with no error message (F-AC4 = 0)."""
    if raw is None:
        return None
    collapsed = _REF_SEPARATORS.sub("/", str(raw).strip().upper())
    return collapsed.strip("/") or None


def portal_host(row: dict[str, Any]) -> str | None:
    """Which portal issued this tender. `sourceUrl` is a bare host ('ireps.gov.in')."""
    raw = (row.get("sourceUrl") or "").strip().lower()
    if not raw:
        return None
    return (urlparse(raw if "//" in raw else f"//{raw}").hostname or raw) or None


def qualified_ref(row: dict[str, Any]) -> str | None:
    """Host-qualified reference: the only form that is unique across an aggregated feed.

    Falls back to the vendor's own `tenderId` UUID when the portal did not give a reference at
    all. That is a worse key — it cannot ever match the same tender arriving from another
    source — but a row with no key is a row that re-inserts itself on every sweep, and an
    unbounded corpus is a worse failure than an unmergeable one.
    """
    ref = normalize_ref(row.get("sourceTenderId") or row.get("tenderNoticeNo"))
    host = portal_host(row)
    if ref and host:
        return f"{host.upper()}/{ref}"
    if ref:
        return ref
    vendor_id = row.get("tenderId")
    return f"BIDASSIST/{vendor_id}".upper() if vendor_id else None


def iso_from_millis(value: Any) -> str | None:
    """Epoch milliseconds → an ISO-8601 UTC instant.

    Every timestamp in this payload is epoch ms. Stored UTC and converted at display, because
    Indian submission deadlines are IST-sensitive and 15:00 IST is not 15:00 UTC — a missed
    deadline is a lost bid (docs/known-pitfalls.md).
    """
    if value in (None, "", 0):
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    if millis <= 0:
        return None
    return datetime.fromtimestamp(millis / 1000, UTC).isoformat()


def money(value: Any) -> float | None:
    """A decimal string → float, or None. Never a guess, never a zero-for-missing."""
    if value in (None, "", "-"):
        return None
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _stable_url(url: str) -> str:
    """A signed URL with its signature removed — stable across fetches, useless for fetching.

    Only ever used for hashing. The live URL is what gets emitted.
    """
    parts = urlparse(url)
    kept = {k: v for k, v in parse_qs(parts.query).items() if k not in _VOLATILE_QUERY_KEYS}
    query = "&".join(f"{k}={v[0]}" for k, v in sorted(kept.items()))
    return urlunparse(parts._replace(query=query))


def _snapshot_ref(row: dict[str, Any]) -> str:
    """Content hash of the row with signed-URL noise stripped.

    Hashing the raw row would produce a new digest every sweep, because the CloudFront
    signature is regenerated per request. A change signal that always fires is not a change
    signal.
    """
    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str) and value.startswith("http") and "Signature=" in value:
            return _stable_url(value)
        return value

    canonical = json.dumps(scrub(row), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _documents(row: dict[str, Any]) -> tuple[list[str], str | None]:
    """→ (urls, earliest expiry as ISO). The expiry is what makes a dead link explainable."""
    urls: list[str] = []
    earliest: int | None = None
    for doc in row.get("documents") or []:
        url = (doc or {}).get("documentKey")
        if not url:
            continue
        urls.append(str(url))
        expires = parse_qs(urlparse(str(url)).query).get("Expires", [""])[0]
        if expires.isdigit():
            seconds = int(expires)
            earliest = seconds if earliest is None else min(earliest, seconds)
    expiry = datetime.fromtimestamp(earliest, UTC).isoformat() if earliest else None
    return urls, expiry


def _geography(row: dict[str, Any]) -> str | None:
    location = row.get("location") or {}
    parts = [str(location.get(k) or "").strip() for k in ("city", "state")]
    return ", ".join(p for p in parts if p) or None


def normalize(row: dict[str, Any], market: str = "IN") -> dict[str, Any]:
    """One BidAssist tender → one F-FR1 record. Pure."""
    host = portal_host(row)
    documents, documents_expire_at = _documents(row)

    sectors = [str(s).strip() for s in (row.get("sector") or []) if str(s).strip()]

    # The vendor's own estimate never reaches the field a value-band rule reads.
    raw_value = money(row.get("value"))
    is_estimated = bool(row.get("isTenderValueEstimated"))
    estimated_value = None if is_estimated else raw_value

    return {
        "source_id": SOURCE_ID,
        "market": market,
        # Indian portals publish in English. Declared rather than inferred downstream, because
        # this field decides what language the drafter must write in.
        "notice_language": "en",
        "portal_ref_no": qualified_ref(row),
        "title": (row.get("tenderDescription") or row.get("tenderDetails") or "").strip() or None,
        "authority": ((row.get("authority") or {}).get("name") or "").strip() or None,
        # BidAssist's own taxonomy strings ("Metals and Non-Metals"), NOT a controlled
        # vocabulary like CPV and not GeM's category names. A `category_prefix_*` rule written
        # against GeM strings will not match these; that is a fact about the source, so it is
        # recorded here rather than papered over with a mapping nobody asked for.
        "category_codes": sectors,
        "geography": _geography(row),
        "estimated_value": estimated_value,
        "emd": money(row.get("emd")),
        "published_at": iso_from_millis(row.get("postingDate")),
        "closing_at": iso_from_millis(row.get("bidDeadline")),
        "prebid_at": iso_from_millis(row.get("preBidMeetingDate")),
        "document_urls": documents,
        "raw_snapshot_ref": _snapshot_ref(row),
        "source_fields": {
            "portal_host": host,
            # Named so a later engine-side merge can key on a field instead of a guess.
            "overlaps_source": KNOWN_OVERLAP.get(host or ""),
            "vendor_tender_id": row.get("tenderId"),
            "portal_ref_raw": row.get("sourceTenderId"),
            "notice_no": row.get("tenderNoticeNo"),
            "workflow_status": row.get("workflowStatus"),
            "sectors": sectors,
            "currency": row.get("currency"),
            "value_is_vendor_estimate": is_estimated,
            "vendor_estimated_value": raw_value if is_estimated else None,
            "tender_fee": money(row.get("tenderFee")),
            "document_cost": money(row.get("documentCost")),
            "boq_item_count": row.get("boqItemsCount"),
            "boq_items_too_large": row.get("boqItemsTooLarge"),
            "corrigendum_count": len(row.get("corrigendumInfo") or []),
            "prebid_address": row.get("preBidMeetingAddress"),
            "documents_expire_at": documents_expire_at,
        },
    }


def normalize_award(row: dict[str, Any]) -> dict[str, Any]:
    """One BidAssist result → the same award shape `services/gem-connector` emits.

    **The ladder is real here, which is worth stating because it was assumed otherwise.**
    Measured on 100 award rows, 2026-08-29: 328 bidder rows, 55 awards with more than one
    bidder, 51 of those carrying an explicit `bidRank` and 44 carrying more than one priced
    bidder. This source publishes L1..Ln, not just the winner.

    Two fields are deliberately not invented:

    * **`mse` is None, never False.** BidAssist does not publish MSE status. Rendering unknown
      as False would state that a bidder is not a small enterprise, which is a claim about a
      real company nobody made — the same reason an unrecorded spec parameter reads
      `NOT ASSESSED` rather than `deviation`.
    * **`rank` is None when the source omits it.** Sorting by price and calling the result a
      rank would manufacture a ladder position the portal never published. Rows without a rank
      sort last, ordered by price, and say so by carrying `rank: None`.
    """
    ladder: list[dict[str, Any]] = []
    for bidder in row.get("bidderDetails") or []:
        bidder = bidder or {}
        name = (bidder.get("bidderName") or "").strip()
        if not name:
            continue
        rank = bidder.get("bidRank")
        try:
            rank = int(rank) if rank not in (None, "", "-") else None
        except (TypeError, ValueError):
            rank = None
        ladder.append({
            "seller": name,
            "mse": None,
            "total_price": money(bidder.get("bidValue")) or money(bidder.get("awardedValue")),
            "rank": rank,
            "offered_item": (bidder.get("offeredMake") or "").strip() or None,
            "awarded": bool(bidder.get("isAwarded")),
            "status": bidder.get("bidStatus"),
            "city": bidder.get("addressCity"),
            "state": bidder.get("addressState"),
        })

    ladder.sort(key=lambda r: (
        r["rank"] is None,
        r["rank"] if r["rank"] is not None else 0,
        r["total_price"] if r["total_price"] is not None else float("inf"),
    ))
    winners = [r for r in ladder if r["awarded"]]

    return {
        "source_id": SOURCE_ID,
        "award_ref": normalize_ref(row.get("sourceBidAwardId") or row.get("bidAwardRefNo")),
        "portal_ref_no": qualified_ref(row),
        "vendor_tender_id": row.get("tenderId"),
        "title": (row.get("aocDescription") or "").strip() or None,
        "authority": ((row.get("authority") or {}).get("name") or "").strip() or None,
        "geography": _geography(row),
        "categories": [str(c).strip() for c in (row.get("category") or []) if str(c).strip()],
        "contract_value": money(row.get("contractValue")) or money(row.get("value")),
        "contract_value_is_estimate": bool(row.get("isContractValueEstimated")),
        "contract_date": iso_from_millis(row.get("contractDate")),
        "contract_period_days": row.get("contractPeriod"),
        "ladder": ladder,
        "winner": winners[0] if winners else (ladder[0] if ladder else None),
        "participant_count": len(ladder),
        "raw_snapshot_ref": _snapshot_ref(row),
    }


def build_body(feed_source_id: str, page: int) -> dict[str, Any]:
    """The search body.

    **`FEED_SOURCE_ID` is the only filter key sent, and that is a rule rather than an
    omission.** Probed 2026-08-29: `SEARCH`, `STATE` and a deliberately invented key were all
    refused, but `KEYWORD` was ACCEPTED and returned a page byte-identical to the unfiltered
    control — the exact failure GeM's `bidStatusType` taught us to expect, where a filter the
    server ignores is worse than one it rejects because the response looks like an answer.
    Anything beyond `FEED_SOURCE_ID` has to be measured against a control and pinned by a test
    before it is sent, or the first typo silently reports the whole corpus as one filtered
    slice.

    `pageNumber` is zero-based and `pageSize` is fixed by the vendor at 20.
    """
    return {
        "filters": {"FEED_SOURCE_ID": [feed_source_id]},
        "pageNumber": page,
        "pageSize": PAGE_SIZE,
    }


def parse_page(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """→ (rows, is_last_page).

    The vendor reports no total count, only a terminal flag, so feed size can be measured but
    never read. Callers page until `last` or until their budget runs out.
    """
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError(f"BidAssist payload carried no data list: {str(payload)[:160]}")
    return rows, bool(payload.get("last"))
