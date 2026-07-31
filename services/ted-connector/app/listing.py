"""TED notice → the F-FR1 normalized record.

Same contract `services/gem-connector` emits, so `app/discovery/ingest.py` consumes both without
knowing which market it is looking at. That contract already existing is the whole reason a
second market costs a connector rather than a fork.

**The language decision lives here, and it is a selection, not a translation.** A TED notice
carries its title and buyer name as objects keyed by language — `{"fra": …, "eng": …, "hun": …}`
— because the EU publishes the same notice in every official language. So "tender content in
French" means *choosing* the `fra` value, never translating one. The chosen language is recorded
as `notice_language`, and that is what decides which language the drafter must write in later.
Inferring it from the market would be wrong: TED carries notices whose original is not the
buyer country's language, and it says so per notice.

**Three fields GeM could not fill**, each left null there for a reason worth remembering:
  * `geography` — real NUTS codes, not a state name guessed out of a department string.
  * `category_codes` — CPV, a hierarchical controlled vocabulary. The existing
    `category_prefix_*` rule kinds get better on it: a CPV prefix is a genuine taxonomic level,
    so `72` really does mean IT services.
  * `notice_language` — declared by the source, per the above.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SOURCE_ID = "ted"

# ISO 639-2/B (TED's keys) -> the product's 2-letter locale vocabulary.
_LANG = {
    "fra": "fr", "eng": "en", "deu": "de", "spa": "es", "ita": "it",
    "nld": "nl", "por": "pt", "pol": "pl", "swe": "sv", "dan": "da",
}

# Preferred language per market, then fallbacks. English is a fallback rather than never: a
# notice we can read imperfectly beats a notice we drop, and dropping one is ET-7.
_MARKET_LANGS = {"FR": ("fra", "eng"), "DE": ("deu", "eng"), "ES": ("spa", "eng")}

_COUNTRY = {"FR": "FRA", "DE": "DEU", "ES": "ESP", "IT": "ITA"}

_REF_SEPARATORS = re.compile(r"[\s\-_/\\.]+")


def normalize_ref(raw: str | None) -> str | None:
    """F-FR6: whitespace, case and separators only. No edit distance, no fuzzy matching —
    a wrong merge deletes a tender with no error message (F-AC4 = 0)."""
    if raw is None:
        return None
    collapsed = _REF_SEPARATORS.sub("/", str(raw).strip().upper())
    return collapsed.strip("/") or None


def market_to_country(market: str) -> str:
    return _COUNTRY.get(market, "FRA")


def pick_language(value: Any, market: str) -> tuple[str | None, str | None]:
    """→ (text, 2-letter language). Selects; never translates.

    TED returns either a plain string or `{lang: str | [str]}`. Preference is the market's own
    language, then English as a readable fallback, then whatever the notice actually carries —
    because a notice published only in Hungarian is still a notice.
    """
    if value is None:
        return None, None
    if isinstance(value, str):
        return (value or None), None
    if isinstance(value, list):
        return (str(value[0]) if value else None), None
    if not isinstance(value, dict):
        return str(value), None

    def text_of(key: str) -> str | None:
        raw = value.get(key)
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        text = str(raw).strip() if raw is not None else ""
        return text or None

    for key in (*_MARKET_LANGS.get(market, ("eng",)), *value.keys()):
        text = text_of(key)
        if text:
            return text, _LANG.get(key, key[:2].lower())
    return None, None


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _snapshot_ref(record: dict[str, Any]) -> str:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _document_url(links: Any, market: str) -> str | None:
    """Prefer the market-language HTML notice, then its PDF, then anything readable."""
    if not isinstance(links, dict):
        return None
    preferred = _MARKET_LANGS.get(market, ("eng",))[0].upper()
    for group in ("html", "pdf", "htmlDirect", "xml"):
        entry = links.get(group)
        if not isinstance(entry, dict):
            continue
        chosen = entry.get(preferred) or entry.get("ENG") or _first(list(entry.values()))
        if isinstance(chosen, dict):
            chosen = _first(list(chosen.values()))
        if chosen:
            return str(chosen)
    return None


def normalize(record: dict[str, Any], market: str = "FR") -> dict[str, Any]:
    """One TED notice → one F-FR1 record. Pure."""
    title, title_lang = pick_language(record.get("notice-title"), market)
    authority, _ = pick_language(record.get("buyer-name"), market)

    # CPV repeats main and additional classifications; order-preserving dedup keeps the main one
    # first, which is the one a prefix rule should match against.
    cpv: list[str] = []
    for code in record.get("classification-cpv") or []:
        text = str(code).strip()
        if text and text not in cpv:
            cpv.append(text)

    # place-of-performance mixes NUTS regions and countries ('FRK26', 'FRA'). Keep both: a rule
    # may reasonably target either level.
    places: list[str] = []
    for place in (record.get("place-of-performance") or []) + (record.get("buyer-country") or []):
        text = str(place).strip()
        if text and text not in places:
            places.append(text)

    document_url = _document_url(record.get("links"), market)
    titles = record.get("notice-title")

    return {
        "source_id": SOURCE_ID,
        "market": market,
        "portal_ref_no": normalize_ref(record.get("publication-number")),
        "title": title,
        "authority": authority,
        "category_codes": cpv,
        "geography": ", ".join(places) or None,
        # TED's search projection carries no monetary value. Absent stays absent — a value-band
        # rule reads this field, so a guess becomes a wrong exclusion (F-FR1).
        "estimated_value": None,
        "emd": None,
        "published_at": str(record.get("publication-date") or "") or None,
        "closing_at": _first(record.get("deadline-receipt-request")),
        "prebid_at": None,
        "document_urls": [document_url] if document_url else [],
        "raw_snapshot_ref": _snapshot_ref(record),
        "notice_language": title_lang,
        "source_fields": {
            "notice_type": record.get("notice-type"),
            "procedure_type": record.get("procedure-type"),
            "cpv": cpv,
            "places": places,
            "buyer_country": record.get("buyer-country"),
            "languages_available": sorted(titles.keys()) if isinstance(titles, dict) else [],
        },
    }


FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "deadline-receipt-request",
    "publication-date",
    "classification-cpv",
    "place-of-performance",
    "notice-type",
    "procedure-type",
    "links",
]


def build_body(page: int, page_size: int, market: str, search: str = "") -> dict[str, Any]:
    """TED expert-search query.

    `deadline-receipt-request>=today()` because TED's archive runs to the 1990s, and an
    unfiltered sweep would spend its whole budget on tenders that closed decades ago. Newest
    publication first, so new notices land on page 1 where the incremental frontier needs them.
    """
    clauses = [
        f"buyer-country={market_to_country(market)}",
        "deadline-receipt-request>=today()",
    ]
    if search.strip():
        # Acquires more, never filters — the safe direction under ET-7.
        clauses.append('notice-title~"{}"'.format(search.strip().replace('"', "")))
    return {
        "query": " AND ".join(clauses) + " SORT BY publication-date DESC",
        "limit": page_size,
        "page": page,
        "fields": FIELDS,
    }


def parse_page(body: str) -> tuple[int, list[dict[str, Any]]]:
    parsed = json.loads(body)
    if "notices" not in parsed:
        raise ValueError(f"TED response carried no notices: {str(parsed)[:160]}")
    return int(parsed.get("totalNoticeCount") or 0), list(parsed["notices"] or [])
