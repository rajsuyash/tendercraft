"""Authoring a tender before it is published (F22–F26, TP1).

The pain point: RFPs get written in Word from a reused template, circulated by email, and
reviewed by the legal cell after the ambiguity is already baked in. The cost lands later as
re-tendering, scope disputes, and risk premiums in the prices received.

Three things here answer that, and only the first is novel:

1. **The checks run while the officer types**, against a versioned rulepack (deterministic —
   `deterministic/rulepack.py`). A turnover bar above the GFR ceiling is flagged at the moment
   it is written, not after a bidder complains.
2. **Reviewers work in parallel** and their sign-off is a gate. Sequential email review is
   precisely why the legal cell reviews late.
3. **Publishing emits the framework, not just a document.** The criteria the officer wrote
   become the criteria bids are scored against, with no re-keying — so the published paper and
   the evaluation framework cannot drift apart.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import db
from .deterministic.rulepack import Finding, blocking_findings, check_draft, load_rulepack
from .envelope import ApiError

# Resolved from THIS file, not from the working directory. In a container the app sits at
# /app/evaluate, so a repo-relative default ("services/evaluate-engine/rulepacks/…") resolves
# to nothing and the draft workspace 500s on every request — the containerising pitfall this
# repo has already paid for once with Path.parents.
_DEFAULT_RULEPACK = (
    Path(__file__).resolve().parent.parent / "rulepacks" / "gfr-2017-manuals-2022.v1.json"
)


def _rulepack_path() -> str | Path:
    return os.environ.get("EVAL_RULEPACK_PATH") or _DEFAULT_RULEPACK


def required_signoff_roles() -> list[str]:
    raw = os.environ.get("EVAL_REQUIRED_SIGNOFF_ROLES", "legal,finance,technical")
    return [r.strip() for r in raw.split(",") if r.strip()]


def _pack() -> dict:
    """Loaded per request rather than cached: the rulepack is data an authority may update,
    and a cached copy would keep checking against rules that no longer apply. It is a small
    JSON file read from local disk."""
    try:
        return load_rulepack(_rulepack_path())
    except Exception as exc:  # noqa: BLE001 — surfaced as an envelope, never a stack trace
        raise ApiError(500, "RULEPACK_UNAVAILABLE", str(exc)) from exc


def _finding_dict(f: Finding, dismissed: set[tuple[str, str | None]]) -> dict:
    key = (f.rule_id, f.target_id)
    return {
        "rule_id": f.rule_id, "title": f.title, "severity": f.severity,
        "citation": f.citation, "state": f.state,
        "observed": f.observed, "expected": f.expected,
        "target_kind": f.target_kind, "target_id": f.target_id,
        "reason": f.reason,
        "dismissed": key in dismissed,
    }


def draft_state(draft_id: str, authority_id: str) -> dict:
    """Everything the draft workspace renders, including what is blocking publication."""
    d = db.draft(draft_id, authority_id)
    if not d:
        raise ApiError(404, "DRAFT_NOT_FOUND", "draft not found in your authority")

    crits = db.draft_criteria(draft_id, authority_id)
    reviews = db.draft_reviews(draft_id, authority_id)
    dismissals = db.draft_dismissals(draft_id, authority_id)
    dismissed = {(x["rule_id"], x.get("target_id")) for x in dismissals}

    findings = check_draft(_pack(), d, crits)
    # Blocking findings are NOT dismissible (D13) — dismissal exists for advisories only, and
    # the dismiss endpoint refuses a blocking rule. So the blocker list ignores `dismissed`
    # entirely rather than filtering by it and implying otherwise.
    open_blocking = list(blocking_findings(findings))

    required = required_signoff_roles()
    signed = {r["reviewer_role"] for r in reviews
              if r.get("signed_off_at") and not r.get("invalidated_at")}
    missing_signoffs = [r for r in required if r not in signed]

    blockers = (
        [{"kind": "finding", "detail": f"{f.rule_id}: {f.title}"} for f in open_blocking]
        + [{"kind": "signoff", "detail": f"{role} sign-off outstanding"}
           for role in missing_signoffs]
    )

    return {
        "draft": d,
        "criteria": crits,
        "reviews": reviews,
        "findings": [_finding_dict(f, dismissed) for f in findings],
        "required_signoff_roles": required,
        "missing_signoffs": missing_signoffs,
        "blockers": blockers,
        "can_publish": not blockers and d["state"] != "published",
        "rulepack_version": _pack().get("version"),
    }


def publish(draft_id: str, authority_id: str, actor: str | None) -> dict:
    """Create the tender, carrying the framework and the document checklist over verbatim.

    Refuses on any open blocking finding or missing sign-off, and creates NOTHING when it
    refuses — a partially published tender would be a live procurement missing half its rules.
    """
    state = draft_state(draft_id, authority_id)
    d = state["draft"]

    if d["state"] == "published":
        raise ApiError(409, "DRAFT_PUBLISHED", "this draft has already been published")
    if state["missing_signoffs"]:
        raise ApiError(409, "SIGNOFF_MISSING",
                       "outstanding sign-off: " + ", ".join(state["missing_signoffs"]))
    if any(b["kind"] == "finding" for b in state["blockers"]):
        raise ApiError(409, "BLOCKING_FINDINGS",
                       f"{sum(1 for b in state['blockers'] if b['kind'] == 'finding')} "
                       f"blocking regulatory finding(s) are unresolved")
    if not state["criteria"]:
        raise ApiError(422, "NO_CRITERIA", "a tender must state at least one criterion")

    tender = db.create_tender(authority_id, {
        "title": d["title"], "tender_number": d.get("tender_number"),
        "technical_weight": d["technical_weight"], "financial_weight": d["financial_weight"],
        "qualifying_marks": d.get("qualifying_marks") or 0, "quorum": d["quorum"],
    })
    if not tender:
        raise ApiError(502, "DB_ERROR", "could not create the tender")

    rows = [{
        "kind": c["kind"], "text": c["text"], "max_marks": c.get("max_marks") or 0,
        "compare_kind": c.get("compare_kind") or "qualitative",
        "compare_op": c.get("compare_op"), "compare_value": c.get("compare_value"),
        "anchor_page": None, "anchor_clause": None,
        # Confidence 1.0 and confirmed: a human WROTE these. They were never extracted, so
        # there is nothing for a person to verify against a source document.
        "confidence": 1.0, "confirmed": True,
        "order_index": c.get("order_index") or i + 1,
    } for i, c in enumerate(state["criteria"])]
    db.insert_criteria(authority_id, tender["id"], rows)

    db.update_draft(draft_id, authority_id, {
        "state": "published", "published_tender_id": tender["id"],
        "published_at": "now()", "rulepack_version": state["rulepack_version"],
    })
    db.audit(authority_id, tender["id"], actor, "tender_published_from_draft", "tender",
             tender["id"], {"draft_id": draft_id, "criteria": len(rows),
                            "rulepack_version": state["rulepack_version"]})
    return {"tender_id": tender["id"], "criteria": len(rows)}


def invalidate_signoffs(draft_id: str, authority_id: str) -> None:
    """Any substantive edit invalidates every sign-off (F25-AC4).

    Called from every mutation on a draft. A reviewer who approved wording that then changed
    has not approved what would be published, and quietly keeping their name on it is the
    failure mode this whole feature exists to prevent.
    """
    db.invalidate_draft_signoffs(draft_id, authority_id)
