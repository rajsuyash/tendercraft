"""Authorization — the layer that did not exist.

`role` was stored on every profile, echoed by /api/me, and rendered as a coloured pill.
It was consulted by ZERO authorization decisions. Consequences, all live until this module:
any authenticated writer could pass `?override=true` and clear every override-able export
blocker, and `?stage=` was unvalidated free text so one person satisfied the whole approval
chain with two curls using invented stage names.

Roles are per-WORKSPACE (workspace_members.role). Org-level authority is a separate
boolean (profiles.is_org_admin) rather than a second enum — one flag beats a parallel
hierarchy.

Deterministic by construction: a dict and a membership test. No model input reaches here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from .auth import AuthedUser, get_current_user
from .envelope import ApiError

# The approval chain. Fixed, and validated at the boundary — `stage` used to be free text,
# so two calls with invented names cleared a gate that requires two approvals.
# ponytail: fixed chain. Per-workspace configurable chains when a customer actually asks;
# today nothing writes proposals.approvals_required either.
APPROVAL_STAGES: tuple[str, ...] = ("review", "compliance", "legal", "final")

READ = "read"
DRAFT = "draft"
UPLOAD = "upload"
MANAGE_MEMBERS = "manage:members"
OVERRIDE_EXPORT = "override:export"

# Six roles kept as-is: they already encode the bid-team workflow and the UI renders them.
# `viewer` added — an engagement partner with visibility across pursuits who must never
# touch a draft is a real Big Four role and had nowhere to sit.
PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({READ}),
    "writer": frozenset({READ, DRAFT, UPLOAD}),
    "reviewer": frozenset({READ, DRAFT, UPLOAD, "approve:review"}),
    "compliance_checker": frozenset({READ, "approve:compliance"}),
    "legal": frozenset({READ, "approve:legal"}),
    "approver": frozenset({READ, "approve:final"}),
    "admin": frozenset(
        {READ, DRAFT, UPLOAD, MANAGE_MEMBERS, OVERRIDE_EXPORT}
        | {f"approve:{s}" for s in APPROVAL_STAGES}
    ),
}


def permissions_for(user: AuthedUser) -> frozenset[str]:
    return PERMISSIONS.get(user.role, frozenset())


def can(user: AuthedUser, action: str) -> bool:
    return action in permissions_for(user)


def check(user: AuthedUser, action: str) -> None:
    """Raise 403 unless the caller's workspace role grants `action`.

    Used inline where a gate is CONDITIONAL — `?override=true` is only privileged when it
    is actually true, and a dependency cannot see the query parameter cleanly.
    """
    if not can(user, action):
        raise ApiError(
            403, "FORBIDDEN", f"role '{user.role}' may not perform this action ({action})"
        )


def requires(action: str):
    """FastAPI dependency for endpoints gated unconditionally."""

    def dep(user: Annotated[AuthedUser, Depends(get_current_user)]) -> AuthedUser:
        check(user, action)
        return user

    return dep
