"""GeM listing → the F-FR1 normalized record.

Two responsibilities, kept apart on purpose:

`normalize()` and `normalize_ref()` are **pure functions** over one Solr document. They are
where every field mapping decision lives, they touch no network, and they carry the whole of
this phase's test surface. The sweep around them is thin by design.

**The rule that shapes this file (F-FR1).** A field the source does not provide is `None` —
never inferred, never guessed, never back-filled from the title. Three fields are permanently
`None` here and the tests pin them:

  * `estimated_value` and `emd` — GeM publishes these in the bid *document*, not the listing.
    A deterministic value-band rule reads `estimated_value`, so a guess here becomes a wrong
    exclusion, and F-AC6 counts that as an item hidden by something other than a user rule.
  * `geography` — `deptName` often contains a state ("Higher Education Department Jammu and
    Kashmir"), and substring-matching state names out of it is exactly the plausible inference
    that ET-7 punishes: a bidder filtering by state silently loses every tender whose
    department string we parsed wrong, and a discovery miss produces no error message anywhere.

Phase 2 fills `estimated_value` and `emd` from the document, where they are labelled facts
rather than inferences.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SOURCE_ID = "gem_bidplus"
BASE_URL = "https://bidplus.gem.gov.in"

# The CSRF token appears seven times in the /all-bids HTML, always the same 32-hex value.
_CSRF_RE = re.compile(r"csrf_bd_gem_nk['\"]?\s*[:=]\s*['\"]?([a-f0-9]{32})")

# F-FR6: merge on an exact normalized ref and nothing else. Separators vary between the portal
# ("GEM/2026/R/706528") and forwarded emails ("GEM-2026-R-706528"), so they collapse to a
# single form — but no edit distance, no fuzzy matching, no token reordering. A wrong merge
# deletes a tender from the user's world with no error message (ET-8, F-AC4 = 0).
_REF_SEPARATORS = re.compile(r"[\s\-_/\\.]+")


def normalize_ref(raw: str | None) -> str | None:
    """The dedup key. Idempotent, and only ever collapses whitespace/case/separators."""
    if raw is None:
        return None
    collapsed = _REF_SEPARATORS.sub("/", raw.strip().upper())
    return collapsed.strip("/") or None


def extract_csrf_token(html: str) -> str:
    match = _CSRF_RE.search(html)
    if not match:
        # Fail loudly. A silently-missing token means every subsequent POST 403s, which would
        # look like "the portal blocked us" rather than "our parser broke" (EC-8).
        raise ValueError("no csrf_bd_gem_nk found in /all-bids HTML — page structure changed")
    return match.group(1)


def _first(value: Any) -> Any:
    """Solr wraps nearly every field in a list. Take the single value or None — never join,
    never pick 'the best one', because a silent choice here is an untraceable field value."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _snapshot_ref(doc: dict[str, Any]) -> str:
    """F-FR2: a stable content hash of the raw record.

    The snapshot itself is retained privately as an audit record — GeM's copyright policy
    forbids reproduction without written permission, so it is never served to a customer
    (docs/discovery/source-gem.md §8). This ref is what makes a feed row reproducible.
    """
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize(doc: dict[str, Any]) -> dict[str, Any]:
    """One Solr document → one F-FR1 record. Pure."""
    ref = normalize_ref(_first(doc.get("b_bid_number")))

    # The document lives under the bid's own id when the record IS a bid (`GEM/…/B/…`), and
    # under `b_id_parent` when it is a reverse-auction entry (`GEM/…/R/…`) pointing back at one.
    #
    # Both shapes appear in the same feed and the split is not cosmetic: an R record's own id is
    # the auction, whose document endpoint is not the bid document. Preferring the parent and
    # falling back to the own id covers both, and getting it backwards returns a 200 carrying a
    # DIFFERENT bid's PDF rather than an error — confident eligibility facts about the wrong
    # tender. Both branches are pinned by tests.
    document_id = _first(doc.get("b_id_parent")) or _first(doc.get("b_id"))
    document_urls = [f"{BASE_URL}/showbidDocument/{document_id}"] if document_id else []

    # bd_category_name carries the full item list; b_category_name is a truncated display
    # string. Prefer the complete one, fall back rather than concatenate.
    title = _first(doc.get("bd_category_name")) or _first(doc.get("b_category_name"))

    ministry = _first(doc.get("ba_official_details_minName"))
    department = _first(doc.get("ba_official_details_deptName"))
    # "NA" is GeM's own placeholder for an absent department; it is not an authority name.
    parts = [p for p in (ministry, department) if p and p.strip().upper() != "NA"]

    raw_codes = _first(doc.get("b_cat_id")) or ""
    category_codes = [c for c in (code.strip() for code in raw_codes.split(",")) if c]

    return {
        "source_id": SOURCE_ID,
        "portal_ref_no": ref,
        "title": title,
        "authority": " · ".join(parts) or None,
        "category_codes": category_codes,
        "geography": None,  # never inferred from deptName — see module docstring
        "estimated_value": None,  # in the document, not the listing (phase 2)
        "emd": None,  # in the document, not the listing (phase 2)
        "published_at": _first(doc.get("final_start_date_sort")),
        "closing_at": _first(doc.get("final_end_date_sort")),
        "prebid_at": None,  # GeM's listing does not publish a pre-bid datetime
        "document_urls": document_urls,
        "raw_snapshot_ref": _snapshot_ref(doc),
        # Secondary gate inputs the listing does provide, kept namespaced so they can never be
        # confused with an F-FR1 field a rule engine treats as canonical.
        "source_fields": {
            "total_quantity": _first(doc.get("b_total_quantity")),
            "is_high_value": _first(doc.get("is_high_value")),
            "bid_type": _first(doc.get("b_type")),
            "eval_type": _first(doc.get("b_eval_type")),
            "is_global_tendering": _first(doc.get("ba_is_global_tendering")),
            "is_rate_contract": _first(doc.get("is_rc_bid")),
            "is_boq": _first(doc.get("bd_details_is_boq")),
            "parent_ref_no": normalize_ref(_first(doc.get("b_bid_number_parent"))),
            "document_id": document_id,
        },
    }


# GeM offers four sorts; this one is load-bearing. `Bid-End-Date-Oldest` is the portal's own
# default and it is the wrong frontier for a discovery feed twice over:
#
#   1. It returns the tenders closing SOONEST — the ones a bidder can least act on. A first
#      sweep against it produced 60 bids all closing within five days, i.e. a feed made
#      entirely of tenders that are already too late to win.
#   2. Newly published bids land somewhere in the middle of that ordering, so the incremental
#      "stop when a page yields nothing new" frontier never sees them first, and a daily sweep
#      would have to page deep into the corpus to find the day's new work.
#
# Sorting by latest START date puts the newly published bids on page 1, which is both what the
# user wants to see and where the incremental sweep needs them.
_SORT = "Bid-Start-Date-Latest"


def build_payload(page: int) -> dict[str, str]:
    """The exact body /all-bids-data expects, most recently published first.

    The sort must be stable across pages: a sweep paginating over a shifting order silently
    skips items, and a skipped item is ET-7.
    """
    payload = {
        "page": page,
        "param": {"searchBid": "", "searchType": "fullText"},
        "filter": {
            "bidStatusType": "ongoing_bids",
            "byType": "all",
            "highBidValue": "",
            "byEndDate": {"from": "", "to": ""},
            "sort": _SORT,
        },
    }
    return {"payload": json.dumps(payload, separators=(",", ":"))}


def parse_page(body: str) -> tuple[int, list[dict[str, Any]]]:
    """→ (total_found, raw docs). The endpoint sends JSON under a text/html content type."""
    parsed = json.loads(body)
    if parsed.get("code") != 200:
        raise ValueError(f"GeM returned code {parsed.get('code')}: {parsed.get('message')!r}")
    inner = parsed["response"]["response"]
    return int(inner["numFound"]), list(inner.get("docs") or [])
