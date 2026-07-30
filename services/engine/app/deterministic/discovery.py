"""The feed gate: which opportunities a workspace sees, and why.

**This module is the only thing in the product permitted to hide a tender.** F-FR12/G-9 draw the
line: a model may rank and summarise, it may never decide what a human never sees. So exclusion
lives here, in `app/deterministic/`, which is model-import-free and enforced as such by CI —
and every exclusion returns the *name* of the user-authored rule that caused it. The database
carries the same rule as a check constraint (`opportunity_matches_exclusion_names_its_rule`), so
an exclusion without a named rule cannot be written even by code that tries.

The reason for that much belt-and-braces: a missed tender is the only failure in this product
with **no natural feedback signal** (ET-7). A wrong verdict gets argued with, a bad draft gets
rewritten, but a tender that never appears produces no error, no alert and no line in any
report. It is invisible until the quarter ends and the pipeline is empty.

**Every ambiguous case resolves toward showing more, ranked lower.** A false positive costs one
skimmed line. A false negative costs the bid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Closed set. Mirrored by `kind` in migrations/0019_opportunities.sql and by the rule builder in
# apps/web — if a UI array lists these, say so in a comment at both ends. A UI list mirroring a
# server enum will drift, and the drifted options 422 and look like dead buttons.
RULE_KINDS = frozenset(
    {
        "category_prefix_in",  # spec: {"prefixes": ["services_", "home_powe_"]}
        "category_prefix_not_in",
        "authority_contains",  # spec: {"needles": ["Ministry of Defence"]}
        "authority_not_contains",
        "min_days_to_close",  # spec: {"days": 7}
        "value_between",  # spec: {"min": 100000, "max": null}
        # The opt-in narrow feed. Fires when the vendor's own capability keywords match nothing
        # on the tender. spec: {"keywords": ["cctv", "networking"]}
        "keyword_match_required",
    }
)

# Bands, never decimals. F-FR11 is explicit: a decimal implies a precision this signal does not
# have, and a bidder who sees 0.62 will reason about the second digit.
BANDS = ("high", "medium", "low")


@dataclass(frozen=True)
class Rule:
    """A workspace's named, deterministic filter. Frozen: a rule that mutates during evaluation
    could exclude different items on different passes and nobody would be able to explain it."""

    name: str
    kind: str
    spec: dict[str, Any]
    enabled: bool = True


@dataclass(frozen=True)
class GateResult:
    in_scope: bool
    excluded_by_rule: str | None  # always set when in_scope is False, never set when True


def _category_codes(record: dict[str, Any]) -> list[str]:
    return [c for c in (record.get("category_codes") or []) if c]


def _days_to_close(record: dict[str, Any], now: datetime) -> float | None:
    """None when the portal published no closing date — which must NOT read as 'closes today'.

    A missing date defaulting to 0 would let a `min_days_to_close` rule exclude every item whose
    deadline the portal happened to omit. That is a model-free exclusion of a tender nobody chose
    to hide, so absence has to stay absent all the way to the rule.
    """
    raw = record.get("closing_at")
    if not raw:
        return None
    if isinstance(raw, datetime):
        closing = raw
    else:
        try:
            closing = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
    if closing.tzinfo is None:
        closing = closing.replace(tzinfo=UTC)
    return (closing - now).total_seconds() / 86400.0


@dataclass(frozen=True)
class KeywordMatch:
    band: str
    matched_terms: tuple[str, ...]

    @property
    def reason(self) -> str:
        if not self.matched_terms:
            return "No capability keyword matched this tender"
        return "Matched your keyword" + ("s " if len(self.matched_terms) > 1 else " ") + ", ".join(
            self.matched_terms
        )


# Words shorter than this must match EXACTLY; only longer ones may match on a shared prefix.
#
# Raised from 4 to 5 by production output: at 4, the keyword "desktop" matched the token "desk"
# and banded a classroom "Desk and Bench Set" as a top fit for an IT supplier. The prefix rule
# has to survive both directions — "networking" must still match "network" — so the lever is the
# length of the SHORTER word, not which side is longer. At 5, "desk" is too short to stem and
# must match exactly, while "network" (7) still stems to "networking".
_MIN_STEM = 5

# GeM's category codes are deliberately truncated to four-letter segments — `home_info_netw`,
# `home_clea_clea`. There, a four-character prefix IS the portal's own abbreviation of the word,
# so the floor is lower and the match runs one way only: the code may be a prefix of the
# vendor's keyword ("netw" -> "networking"), never the reverse.
_MIN_CODE_STEM = 4

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Words, including the parts of a GeM category code — `home_info_netw` is three tokens."""
    return set(_WORD.findall(text.lower()))


def _term_hits(term: str, blob: str, tokens: set[str], *, code: bool = False) -> bool:
    """One keyword against one haystack.

    A multi-word keyword ("it services") is matched as a phrase against the raw text. A single
    word is matched against tokens with a shared-prefix rule, because the vendor and the portal
    will not agree on inflection: a vendor writes "networking" and GeM writes "Network switch
    supply". Plain substring matching misses that in one direction and only that direction,
    which is the kind of gap that looks like the feature working until someone checks.
    """
    if " " in term:
        return term in blob
    if term in tokens:
        return True
    if code:
        # One direction only: an abbreviated code may open the vendor's word.
        return any(
            len(tok) >= _MIN_CODE_STEM and term.startswith(tok) for tok in tokens
        )
    if len(term) < _MIN_STEM:
        return False
    return any(
        len(tok) >= _MIN_STEM and (tok.startswith(term) or term.startswith(tok))
        for tok in tokens
    )


def keyword_relevance(record: dict[str, Any], keywords: list[str]) -> KeywordMatch:
    """Deterministic fit between a tender and the vendor's own keywords.

    Pure, explainable, and the fallback whenever the model is unavailable — which is why it
    lives here rather than beside the model: `app/deterministic/` may not import pipeline code,
    and CI enforces that.

    An empty keyword list returns `low` with no matched terms — never an error and never a
    silent pass. The caller decides what `low` means; only a named rule may act on it.
    """
    terms = [k.strip().lower() for k in (keywords or []) if k and k.strip()]
    if not terms:
        return KeywordMatch(band="low", matched_terms=())

    title = (record.get("title") or "").lower()
    categories = " ".join(_category_codes(record)).lower()
    authority = (record.get("authority") or "").lower()

    title_tokens, category_tokens = _tokens(title), _tokens(categories)
    all_tokens = title_tokens | category_tokens | _tokens(authority)
    blob = " ".join((title, categories, authority))

    matched = tuple(
        sorted(
            {
                t
                for t in terms
                if _term_hits(t, blob, title_tokens | _tokens(authority))
                or _term_hits(t, categories, category_tokens, code=True)
            }
        )
    )
    if not matched:
        return KeywordMatch(band="low", matched_terms=())

    # A hit inside a GeM category code outranks one anywhere else: the codes are the portal's
    # own structured taxonomy, so `services_home_cust` matching "services" is a classification,
    # whereas the same word inside a buyer's department name is a coincidence.
    in_category = any(_term_hits(t, categories, category_tokens, code=True) for t in matched)
    in_title = any(_term_hits(t, title, title_tokens) for t in matched)
    if in_category or len(matched) >= 2:
        return KeywordMatch(band="high", matched_terms=matched)
    if in_title:
        return KeywordMatch(band="medium", matched_terms=matched)
    # Matched only on the buying authority's name — real, but weak evidence of fit.
    return KeywordMatch(band="low", matched_terms=matched)


def _matches(rule: Rule, record: dict[str, Any], now: datetime) -> bool:
    """True when this rule's condition FIRES on the record (i.e. the rule wants it excluded).

    An unknown `kind`, or a spec missing the field it needs, returns False — the rule simply does
    not fire. It never falls through to "exclude". A malformed rule that hid tenders would be the
    silent-miss failure arriving through the one path built to prevent it.
    """
    spec = rule.spec or {}
    codes = _category_codes(record)

    if rule.kind == "category_prefix_in":
        prefixes = spec.get("prefixes") or []
        return bool(prefixes) and any(c.startswith(tuple(prefixes)) for c in codes)

    if rule.kind == "category_prefix_not_in":
        prefixes = spec.get("prefixes") or []
        # Fires when the item matches NONE of the wanted prefixes — "keep only these categories".
        return bool(prefixes) and not any(c.startswith(tuple(prefixes)) for c in codes)

    if rule.kind in ("authority_contains", "authority_not_contains"):
        needles = [n.lower() for n in (spec.get("needles") or []) if n]
        if not needles:
            return False
        authority = (record.get("authority") or "").lower()
        hit = any(n in authority for n in needles)
        return hit if rule.kind == "authority_contains" else not hit

    if rule.kind == "min_days_to_close":
        days = spec.get("days")
        remaining = _days_to_close(record, now)
        if days is None or remaining is None:
            return False  # no date published → never excluded on this basis
        return remaining < float(days)

    if rule.kind == "keyword_match_required":
        keywords = spec.get("keywords") or []
        if not keywords:
            # Inert on an empty list, deliberately. A vendor who switched this on before filling
            # in their profile would otherwise have their ENTIRE feed hidden by a rule whose
            # name gives no clue why — a self-inflicted ET-7 with a plausible-looking cause.
            return False
        return keyword_relevance(record, keywords).band == "low"

    if rule.kind == "value_between":
        value = record.get("estimated_value")
        if value is None:
            # GeM omits estimated value on most listings; it lives in the document. Excluding on
            # an absent value would hide most of the feed on a rule the user thought was narrow.
            return False
        low, high = spec.get("min"), spec.get("max")
        if low is not None and float(value) < float(low):
            return True
        if high is not None and float(value) > float(high):
            return True
        return False

    return False  # unknown kind: inert, never excluding


def evaluate_gate(
    record: dict[str, Any],
    rules: list[Rule],
    *,
    now: datetime | None = None,
) -> GateResult:
    """F-FR9. Returns in-scope, or excluded naming the FIRST enabled rule that fired.

    Rule order is the caller's; the first match wins so the reported reason is stable and
    explainable. Disabled rules are inert.
    """
    moment = now or datetime.now(UTC)
    for rule in rules:
        if not rule.enabled:
            continue
        if rule.kind not in RULE_KINDS:
            continue
        if _matches(rule, record, moment):
            return GateResult(in_scope=False, excluded_by_rule=rule.name)
    return GateResult(in_scope=True, excluded_by_rule=None)


# ── Depth-1 eligibility (C-FR6..C-FR9) ───────────────────────────────────────────────────

@dataclass(frozen=True)
class EligibilityResult:
    signal: str  # 'likely_eligible' | 'likely_ineligible' | 'unknown'
    reason: str


def evaluate_eligibility(
    eligibility_fields: dict[str, Any] | None,
    profile: dict[str, Any] | None,
) -> EligibilityResult:
    """Depth-1 triage over the deterministically-parsed bid document and the vendor profile.

    Deliberately narrow. It answers only what a *comparator* can answer — turnover — and returns
    `unknown` for everything else. C-FR8 forbids a separate "quick" logic path: a cheaper input
    never buys a looser rule, so this compares the same way Depth 2 does and declines to guess
    when it cannot.

    C-FR9 inverts the usual asymmetry for display ordering only: `likely_ineligible` ranks an
    item DOWN but never hides it (F-FR12). Nothing here gates anything — a Depth-1 verdict never
    feeds a Bid/No-Bid card (C-AC10).
    """
    if not eligibility_fields:
        return EligibilityResult("unknown", "Bid document not read yet")

    required = eligibility_fields.get("min_avg_annual_turnover_inr")
    if required is None:
        # Read, and it states no financial bar. That is a different fact from "not read", and
        # collapsing them into one label told 56 live rows they still needed a document we had
        # already parsed. The signal stays `unknown` because no eligibility criterion was
        # actually decided; only the wording distinguishes the two.
        return EligibilityResult(
            "unknown", "The bid document states no minimum turnover requirement"
        )

    actual = (profile or {}).get("avg_annual_turnover_inr")
    if actual is None:
        return EligibilityResult(
            "unknown",
            f"Requires average annual turnover of {_inr(required)}; "
            "your vendor profile has no turnover on record",
        )

    if float(actual) >= float(required):
        # Deliberately narrow wording. This compared ONE criterion. Saying "eligible" would
        # claim experience, certifications and supply capability were checked; they were not.
        return EligibilityResult(
            "likely_eligible",
            f"Clears the turnover bar of {_inr(required)} with your {_inr(actual)}. "
            "Experience, certifications and category fit are not yet checked at this depth.",
        )

    # Never a bare "ineligible": an MSE/startup relaxation can reverse it, and the bidder needs
    # to see that before skipping the tender.
    relaxation = eligibility_fields.get("mse_turnover_relaxation")
    tail = " — an MSE turnover relaxation is offered on this bid" if relaxation else ""
    return EligibilityResult(
        "likely_ineligible",
        f"Requires average annual turnover of {_inr(required)}; "
        f"your profile shows {_inr(actual)}{tail}. Turnover only.",
    )


def _inr(amount: float | int) -> str:
    """Indian units, because ₹25,00,00,000 is unreadable and '25 Cr' is not."""
    value = float(amount)
    if value >= 10_000_000:
        return f"₹{value / 10_000_000:.2f} Cr".replace(".00 ", " ")
    if value >= 100_000:
        return f"₹{value / 100_000:.2f} L".replace(".00 ", " ")
    return f"₹{value:,.0f}"
