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
    }
)


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
        return EligibilityResult(
            "likely_eligible",
            f"Requires average annual turnover of {_inr(required)}; "
            f"your profile shows {_inr(actual)}",
        )

    # Never a bare "ineligible": an MSE/startup relaxation can reverse it, and the bidder needs
    # to see that before skipping the tender.
    relaxation = eligibility_fields.get("mse_turnover_relaxation")
    tail = " — an MSE turnover relaxation is offered on this bid" if relaxation else ""
    return EligibilityResult(
        "likely_ineligible",
        f"Requires average annual turnover of {_inr(required)}; "
        f"your profile shows {_inr(actual)}{tail}",
    )


def _inr(amount: float | int) -> str:
    """Indian units, because ₹25,00,00,000 is unreadable and '25 Cr' is not."""
    value = float(amount)
    if value >= 10_000_000:
        return f"₹{value / 10_000_000:.2f} Cr".replace(".00 ", " ")
    if value >= 100_000:
        return f"₹{value / 100_000:.2f} L".replace(".00 ", " ")
    return f"₹{value:,.0f}"
