"""Compliance matrix + export orchestration (Module E). Wires the deterministic export gate.

Maps each criterion's drafted response to a coverage status, then the built export gate
(B-AC4 non-overridable financial gate, E-AC2 override-able approvals) decides. Pure mapping
here; the decision is the deterministic gate's.
"""

from __future__ import annotations

from .deterministic.export_gate import ApprovalChain, ExportDecision, evaluate_export
from .deterministic.types import ComplianceRow, CoverageStatus, RequirementLevel

_STATUS_MAP = {
    "drafted": CoverageStatus.COVERED,
    "placeholder": CoverageStatus.PLACEHOLDER,
    "unverified": CoverageStatus.UNVERIFIED,
    "missing": CoverageStatus.MISSING,
}


def build_matrix(criteria: list[dict], responses: list[dict]) -> list[ComplianceRow]:
    """One compliance row per criterion, joined to its drafted response."""
    by_criterion = {r["criterion_id"]: r for r in responses}
    rows: list[ComplianceRow] = []
    for c in criteria:
        resp = by_criterion.get(c["id"])
        status = CoverageStatus.MISSING
        uncited_financial = False
        if resp:
            status = _STATUS_MAP.get(resp.get("draft_status"), CoverageStatus.MISSING)
            uncited_financial = any(
                f.get("reason") == "uncited_financial" for f in (resp.get("flags") or [])
            )
        rows.append(
            ComplianceRow(
                criterion_id=c["id"],
                requirement_level=RequirementLevel(c["requirement_level"]),
                status=status,
                has_uncited_financial_claim=uncited_financial,
            )
        )
    return rows


def evaluate(
    criteria: list[dict], responses: list[dict], approvals_required: int, approvals_done: int,
    admin_override: bool = False,
) -> tuple[ExportDecision, list[ComplianceRow]]:
    rows = build_matrix(criteria, responses)
    decision = evaluate_export(
        rows, ApprovalChain(required=approvals_required, completed=approvals_done), admin_override
    )
    return decision, rows
