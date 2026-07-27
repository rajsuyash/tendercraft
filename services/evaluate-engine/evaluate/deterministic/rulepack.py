"""Regulatory checks over a draft tender (F23). No model in this path — ever.

A model that decides whether a tender is lawful is the defect the agent contract names. So the
rules are DATA (`rulepacks/*.json`, ENV-13) and the check kinds are arithmetic here.

Two design points that matter more than the arithmetic:

**Unknown check kinds report `not_evaluated`, never `pass`.** A rulepack that gains a rule this
code cannot run must make that visible. Silently treating it as satisfied is how a draft
acquires a clean bill of health it never earned.

**A missing input is also `not_evaluated`.** If the officer has not entered the estimated
value, R1 cannot say whether the turnover bar is proportionate — and saying "fine" would be a
lie about the one thing the rule exists to catch.

Severity comes from the rulepack, not from here: `blocking` stops publication, `advisory` is
dismissible with a recorded reason (D13).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


class RulepackError(Exception):
    """Raised at load time. Never swallowed — a rule-less draft workspace looks like it is
    checking and is not, which is the worst degradation available in this module."""


@dataclass(frozen=True)
class Finding:
    rule_id: str
    title: str
    severity: str            # blocking | advisory
    citation: str
    state: str               # open | not_evaluated
    observed: str | None = None
    expected: str | None = None
    target_kind: str | None = None
    target_id: str | None = None
    reason: str | None = None   # why it could not be evaluated


def load_rulepack(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise RulepackError(
            f"rulepack not found at {p} — set EVAL_RULEPACK_PATH. Refusing to run a draft "
            f"workspace with no regulatory checks.")
    try:
        pack = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise RulepackError(f"rulepack at {p} is not valid JSON: {exc}") from exc
    if not pack.get("rules"):
        raise RulepackError(f"rulepack at {p} declares no rules")
    return pack


def _dec(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _inr(v: Decimal) -> str:
    """Indian grouping, so a finding reads the way the officer wrote the number."""
    s = str(int(v))
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    # `head` is non-empty here by construction: the early return handled len(s) <= 3, and the
    # loop exits at 1 or 2 remaining characters, never 0.
    parts.insert(0, head)
    return "₹" + ",".join(parts + [tail])


def _na(rule: dict, reason: str) -> Finding:
    return Finding(rule["id"], rule["title"], rule["severity"], rule.get("citation", ""),
                   "not_evaluated", reason=reason)


def _hit(rule: dict, observed: str, expected: str,
         target_kind: str | None = None, target_id: str | None = None) -> Finding:
    return Finding(rule["id"], rule["title"], rule["severity"], rule.get("citation", ""),
                   "open", observed, expected, target_kind, target_id)


# ── check kinds ────────────────────────────────────────────────────────────────
def _ratio_ceiling(rule: dict, draft: dict, criteria: list[dict]) -> list[Finding]:
    c = rule["check"]
    against = _dec(draft.get(c["against"]))
    if against is None:
        return [_na(rule, f"{c['against'].replace('_', ' ')} has not been entered")]
    ceiling = against * Decimal(str(c["max_multiple"]))

    out = []
    for crit in criteria:
        if crit.get("compare_field") != c["field"]:
            continue
        value = _dec(crit.get("compare_value"))
        if value is None:
            out.append(_na(rule, f"criterion '{crit['text'][:40]}' states no numeric value"))
            continue
        if value > ceiling:
            out.append(_hit(rule, f"{_inr(value)} required",
                            f"at most {_inr(ceiling)} "
                            f"({c['max_multiple']}× {_inr(against)})",
                            "criterion", crit.get("id")))
    return out


def _min_days(rule: dict, draft: dict, _criteria) -> list[Finding]:
    c = rule["check"]
    days = _dec(draft.get(c["field"]))
    if days is None:
        return [_na(rule, "the submission window has not been entered")]
    floor = Decimal(str(c.get("minimum", 21)))
    if days < floor:
        return [_hit(rule, f"{int(days)} days", f"at least {int(floor)} days")]
    return []


def _required_above_threshold(rule: dict, draft: dict, _criteria) -> list[Finding]:
    c = rule["check"]
    value = _dec(draft.get(c["threshold_field"]))
    threshold = _dec(c.get("threshold", 0)) or Decimal(0)
    if value is None:
        return [_na(rule, "the estimated value has not been entered")]
    if value <= threshold:
        return []
    if draft.get(c["field"]) != c["expected"]:
        return [_hit(rule, str(draft.get(c["field"]) or "not set"),
                     f"{c['expected']} above {_inr(threshold)}")]
    return []


def _text_pattern_requires_qualifier(rule: dict, _draft, criteria: list[dict]) -> list[Finding]:
    """R4 — a brand name with no 'or equivalent'. The clause most often cited in a challenge."""
    c = rule["check"]
    qualifier = c["qualifier"].lower()
    brands = re.compile(
        r"\b(cisco|dell|hp|hpe|lenovo|oracle|microsoft|ibm|juniper|fortinet|vmware|"
        r"intel|amd|nvidia|samsung|sony|bosch|siemens|schneider|honeywell|hikvision|dahua)\b",
        re.IGNORECASE)
    out = []
    for crit in criteria:
        text = crit.get("text") or ""
        found = brands.search(text)
        if found and qualifier not in text.lower():
            out.append(_hit(rule, f"names “{found.group(0)}” with no “{c['qualifier']}”",
                            f"describe the requirement generically, or add “{c['qualifier']}”",
                            "criterion", crit.get("id")))
    return out


def _percentage_band(rule: dict, draft: dict, _criteria) -> list[Finding]:
    c = rule["check"]
    amount = _dec(draft.get(c["field"]))
    against = _dec(draft.get(c["against"]))
    if amount is None or against is None or against == 0:
        return [_na(rule, "the EMD amount or the estimated value has not been entered")]
    pct = (amount / against) * 100
    lo, hi = (Decimal(str(x)) for x in c.get("band", [1, 3]))
    out = []
    if pct > hi or pct < lo:
        out.append(_hit(rule, f"{_inr(amount)} ({pct:.2f}% of value)",
                        f"between {lo}% and {hi}% of the estimated value"))
    if c.get("requires_exemption_clause") and not draft.get("emd_exemption_stated"):
        out.append(_hit(rule, "no MSE / startup exemption clause",
                        "state the MSE and startup EMD exemptions"))
    return out


def _required_above_threshold_with_margin(rule: dict, draft: dict, _criteria) -> list[Finding]:
    c = rule["check"]
    margin = int(c.get("margin_days_before_deadline", 7))
    stated = draft.get(c["field"])
    if not stated:
        return [_hit(rule, "no pre-bid meeting scheduled",
                     f"schedule one at least {margin} days before the deadline")]
    days_before = _dec(draft.get("pre_bid_days_before_deadline"))
    if days_before is None:
        return [_na(rule, "the pre-bid meeting date relative to the deadline is not known")]
    if days_before < margin:
        return [_hit(rule, f"{int(days_before)} days before the deadline",
                     f"at least {margin} days before the deadline")]
    return []


def _framework_arithmetic(rule: dict, draft: dict, criteria: list[dict]) -> list[Finding]:
    c = rule["check"]
    out = []
    technical = [x for x in criteria if x.get("kind") == "technical"]
    marks = sum(int(x.get("max_marks") or 0) for x in technical)
    if technical and marks != int(c.get("weights_sum", 100)):
        out.append(_hit(rule, f"technical marks total {marks}",
                        f"technical marks must total {c.get('weights_sum', 100)}"))
    for field in c.get("requires", []):
        if draft.get(field) in (None, "", 0):
            out.append(_hit(rule, f"{field.replace('_', ' ')} not stated",
                            f"state the {field.replace('_', ' ')}"))
    tw = _dec(draft.get("technical_weight"))
    if tw is not None:
        lo, hi = (Decimal(str(x)) for x in c.get("qcbs_technical_band", [60, 90]))
        if tw < lo or tw > hi:
            out.append(_hit(rule, f"technical weight {tw}",
                            f"between {lo} and {hi}"))
    return out


def _field_present(rule: dict, _draft, criteria: list[dict]) -> list[Finding]:
    c = rule["check"]
    return [
        _hit(rule, f"“{(crit.get('text') or '')[:50]}” states no evaluation method",
             "state how this criterion will be evaluated and marked", "criterion", crit.get("id"))
        for crit in criteria
        if crit.get("kind") == "technical" and not (crit.get(c["field"]) or "").strip()
    ]


_KINDS = {
    "ratio_ceiling": _ratio_ceiling,
    "min_days": _min_days,
    "required_above_threshold": _required_above_threshold,
    "text_pattern_requires_qualifier": _text_pattern_requires_qualifier,
    "percentage_band": _percentage_band,
    "required_above_threshold_with_margin": _required_above_threshold_with_margin,
    "framework_arithmetic": _framework_arithmetic,
    "field_present": _field_present,
}


def check_draft(pack: dict, draft: dict, criteria: list[dict]) -> list[Finding]:
    """Every applicable rule against one draft. Order follows the rulepack."""
    category = draft.get("category")
    out: list[Finding] = []
    for rule in pack["rules"]:
        applies = rule.get("applies_to")
        if applies and category and category not in applies:
            continue
        fn = _KINDS.get(rule["check"]["kind"])
        if fn is None:
            # Visible, not silent: this rulepack asks for a check this build cannot run.
            out.append(_na(rule, f"check kind '{rule['check']['kind']}' is not implemented "
                                 f"in this build"))
            continue
        out.extend(fn(rule, draft, criteria))
    return out


def blocking_findings(findings: list[Finding]) -> tuple[Finding, ...]:
    """What stops publication. `not_evaluated` never blocks — it is a gap in our checking, not
    a defect in the draft, and blocking on it would make a missing field unfixable."""
    return tuple(f for f in findings if f.state == "open" and f.severity == "blocking")
