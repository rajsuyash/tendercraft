"""Workspace membership — invite, accept, change role, deprovision.

Before this module there was no way for a second human to enter a workspace: no endpoint,
no signup, no UI. Onboarding meant running a dev-only seed script that deleted the user
first.

Every write here goes through the service role, never client RLS — a client-writable
membership table lets a user grant themselves 'admin'. That is also why SSO/SCIM plugs in
cleanly later: an IdP is just another privileged writer onto the same accept path.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from . import authz, db
from .auth import AuthedUser, IdentifiedUser, get_current_user, get_identified_user
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]
# Accepting a first invitation happens BEFORE any membership exists.
AnyUser = Annotated[IdentifiedUser, Depends(get_identified_user)]

Role = Literal["viewer", "writer", "reviewer", "compliance_checker", "legal", "approver", "admin"]


class InviteIn(BaseModel):
    email: str
    role: Role = "writer"

    @field_validator("email")
    @classmethod
    def _normalise(cls, v: str) -> str:
        """Shape check + lowercase, deliberately NOT full RFC/deliverability validation.

        pydantic's EmailStr rejects reserved TLDs like .test — which would refuse the
        project's own seeded users and every staging address. And format validation is not
        the security control here: `accept` compares the invitation address to the verified
        JWT email, so a typo simply yields an invitation nobody can redeem.
        """
        v = v.strip().lower()
        local, sep, domain = v.partition("@")
        if not (sep and local and "." in domain) or any(c.isspace() for c in v):
            raise ValueError("invalid email address")
        return v


class AcceptIn(BaseModel):
    token: str


class RoleIn(BaseModel):
    role: Role


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.get("/api/workspaces")
def list_workspaces(user: CurrentUser) -> dict:
    """Every workspace this user can reach — the switcher.

    A SET is the right answer here and in the roster, and nowhere else: every DATA table
    stays scoped to the one active workspace.
    """
    return ok({
        "workspaces": db.get_user_workspaces(user.user_id),
        "active_workspace_id": user.workspace_id,
    })


@router.put("/api/me/workspace/{workspace_id}")
def switch_workspace(workspace_id: str, user: CurrentUser) -> dict:
    """Switch the active workspace. Membership is re-validated here AND again by RLS."""
    if not db.get_membership(user.user_id, workspace_id):
        raise ApiError(403, "NOT_A_MEMBER", "you are not a member of this workspace")
    db.set_active_workspace(user.user_id, workspace_id)
    db.write_audit(workspace_id, user.user_id, "workspace_switch", "profile", user.user_id,
                   after={"workspace_id": workspace_id})
    return ok({"active_workspace_id": workspace_id})


@router.get("/api/workspaces/{workspace_id}/members")
def list_members(workspace_id: str, user: CurrentUser) -> dict:
    if workspace_id != user.workspace_id:
        raise ApiError(403, "NOT_A_MEMBER", "not your active workspace")
    return ok({
        "members": db.get_workspace_members(workspace_id),
        "invitations": db.get_pending_invitations(workspace_id),
    })


@router.post("/api/workspaces/{workspace_id}/invitations")
def invite(workspace_id: str, body: InviteIn, user: CurrentUser) -> dict:
    """Create an invitation and return the raw token ONCE.

    Only the sha256 is persisted, so a database read cannot be replayed into membership.
    Email delivery is deliberately out of scope — the admin sends the link themselves.
    """
    authz.check(user, authz.MANAGE_MEMBERS)
    if workspace_id != user.workspace_id:
        raise ApiError(403, "NOT_A_MEMBER", "not your active workspace")

    token = secrets.token_urlsafe(32)
    db.create_invitation(workspace_id, body.email, body.role,
                         user.user_id, _hash(token))
    db.write_audit(workspace_id, user.user_id, "member_invited", "workspace", workspace_id,
                   after={"email": body.email, "role": body.role})
    return ok({"token": token, "email": body.email, "role": body.role})


@router.post("/api/invitations/accept")
def accept(body: AcceptIn, user: AnyUser) -> dict:
    """Redeem an invitation for the authenticated user.

    The email check is the entire security of this flow. Without it the link is a bearer
    token for workspace membership — forwarded once in Outlook, an outsider joins a client
    engagement workspace. Non-negotiable.
    """
    inv = db.get_invitation_by_hash(_hash(body.token))
    if not inv:
        raise ApiError(404, "INVITATION_NOT_FOUND", "invitation not found")
    if inv.get("accepted_at"):
        raise ApiError(409, "INVITATION_USED", "invitation has already been accepted")
    if inv["expires_at"] < datetime.now(UTC).isoformat():
        raise ApiError(409, "INVITATION_EXPIRED", "invitation has expired")

    claims_email = (db.get_user_email(user.user_id) or "").lower()
    if not claims_email or claims_email != inv["email"].lower():
        raise ApiError(403, "INVITATION_EMAIL_MISMATCH",
                       "this invitation was issued to a different email address")

    db.add_workspace_member(user.user_id, inv["workspace_id"], inv["role"], inv["invited_by"])
    db.upsert_profile_identity(user.user_id, claims_email, inv["workspace_id"])
    db.mark_invitation_accepted(inv["id"], user.user_id, datetime.now(UTC).isoformat())
    db.write_audit(inv["workspace_id"], user.user_id, "member_joined", "workspace",
                   inv["workspace_id"], after={"role": inv["role"]})
    return ok({"workspace_id": inv["workspace_id"], "role": inv["role"]})


@router.patch("/api/workspaces/{workspace_id}/members/{member_id}")
def change_role(workspace_id: str, member_id: str, body: RoleIn, user: CurrentUser) -> dict:
    authz.check(user, authz.MANAGE_MEMBERS)
    if workspace_id != user.workspace_id:
        raise ApiError(403, "NOT_A_MEMBER", "not your active workspace")
    current = db.get_membership(member_id, workspace_id)
    if not current:
        raise ApiError(404, "MEMBER_NOT_FOUND", "member not found in this workspace")
    _guard_last_admin(workspace_id, member_id, current["role"], body.role)

    db.set_member_role(member_id, workspace_id, body.role)
    db.write_audit(workspace_id, user.user_id, "member_role_changed", "workspace_member",
                   member_id, before={"role": current["role"]}, after={"role": body.role})
    return ok({"user_id": member_id, "role": body.role})


@router.delete("/api/workspaces/{workspace_id}/members/{member_id}")
def remove_member(workspace_id: str, member_id: str, user: CurrentUser) -> dict:
    """Deprovision. Deletes the MEMBERSHIP ROW only — never the user or their content.

    audit_events is append-only by trigger and proposal_sections.approved_by references
    them, so removing the person would break the trail they are part of. Deleting the
    membership is sufficient AND complete: current_workspace_id() validates against this
    table on every request, so their scope goes NULL on the very next call.
    """
    authz.check(user, authz.MANAGE_MEMBERS)
    if workspace_id != user.workspace_id:
        raise ApiError(403, "NOT_A_MEMBER", "not your active workspace")
    current = db.get_membership(member_id, workspace_id)
    if not current:
        raise ApiError(404, "MEMBER_NOT_FOUND", "member not found in this workspace")
    _guard_last_admin(workspace_id, member_id, current["role"], None)

    db.remove_workspace_member(member_id, workspace_id)
    db.clear_active_workspace(member_id, workspace_id)
    db.write_audit(workspace_id, user.user_id, "member_removed", "workspace_member",
                   member_id, before={"role": current["role"]})
    return ok({"user_id": member_id, "removed": True})


def _guard_last_admin(workspace_id: str, member_id: str, old_role: str, new_role: str | None):
    """Refuse anything that leaves a workspace with no admin — that state is unrecoverable
    through the API, since only an admin can manage members."""
    if old_role != "admin" or new_role == "admin":
        return
    admins = db.count_workspace_admins(workspace_id)
    if admins <= 1:
        raise ApiError(409, "LAST_ADMIN",
                       "this is the only admin; promote another member first")
