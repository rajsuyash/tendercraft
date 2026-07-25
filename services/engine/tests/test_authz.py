"""Per-workspace RBAC — the authorization layer that did not exist.

Before this module `role` was stored, echoed by /api/me, rendered as a coloured pill, and
consulted by zero authorization decisions. These tests are a table test for a table: the
full role x action cross-product, so a permission added to the wrong role fails loudly.
"""

import pytest

from app import authz
from app.auth import AuthedUser
from app.envelope import ApiError

ROLES = tuple(authz.PERMISSIONS)


def _u(role: str, is_org_admin: bool = False) -> AuthedUser:
    return AuthedUser(user_id="u1", workspace_id="ws1", role=role, is_org_admin=is_org_admin)


# --- shape ---


def test_every_enum_role_has_a_permission_set():
    # Mirrors public.user_role after migration 0012. A role in the DB with no entry here
    # would silently resolve to "no permissions at all".
    assert set(ROLES) == {
        "viewer", "writer", "reviewer", "compliance_checker", "legal", "approver", "admin",
    }


def test_every_role_can_read():
    assert all(authz.can(_u(r), authz.READ) for r in ROLES)


def test_approval_stages_are_a_closed_set():
    assert authz.APPROVAL_STAGES == ("review", "compliance", "legal", "final")


# --- the controls that were unenforced ---


def test_only_admin_may_override_the_export_gate():
    """The live defect: any authenticated user could pass ?override=true and clear every
    override-able blocker, including the entire approval chain."""
    allowed = {r for r in ROLES if authz.can(_u(r), authz.OVERRIDE_EXPORT)}
    assert allowed == {"admin"}


def test_only_admin_may_manage_members():
    allowed = {r for r in ROLES if authz.can(_u(r), authz.MANAGE_MEMBERS)}
    assert allowed == {"admin"}


def test_a_writer_cannot_approve_any_stage():
    for stage in authz.APPROVAL_STAGES:
        assert not authz.can(_u("writer"), f"approve:{stage}"), stage


def test_each_reviewer_role_holds_only_its_own_stage():
    for role, stage in (("reviewer", "review"), ("compliance_checker", "compliance"),
                        ("legal", "legal"), ("approver", "final")):
        held = {s for s in authz.APPROVAL_STAGES if authz.can(_u(role), f"approve:{s}")}
        assert held == {stage}, f"{role} holds {held}"


def test_admin_holds_every_stage():
    assert all(authz.can(_u("admin"), f"approve:{s}") for s in authz.APPROVAL_STAGES)


def test_viewer_is_read_only():
    assert authz.permissions_for(_u("viewer")) == frozenset({authz.READ})


def test_viewer_cannot_draft_or_upload():
    assert not authz.can(_u("viewer"), authz.DRAFT)
    assert not authz.can(_u("viewer"), authz.UPLOAD)


def test_compliance_and_legal_cannot_draft():
    """Segregation of duties in the role set itself: a signer is not an author."""
    for role in ("compliance_checker", "legal", "approver"):
        assert not authz.can(_u(role), authz.DRAFT), role


# --- enforcement ---


def test_check_raises_403_with_a_stable_code():
    with pytest.raises(ApiError) as exc:
        authz.check(_u("writer"), authz.OVERRIDE_EXPORT)
    assert exc.value.status == 403
    assert exc.value.code == "FORBIDDEN"


def test_check_passes_silently_when_permitted():
    assert authz.check(_u("admin"), authz.OVERRIDE_EXPORT) is None


def test_an_unknown_role_grants_nothing():
    """Fail closed: a role added to the DB enum but not here must not inherit anything."""
    assert authz.permissions_for(_u("chief_bid_wizard")) == frozenset()
    with pytest.raises(ApiError):
        authz.check(_u("chief_bid_wizard"), authz.READ)


def test_unknown_action_is_denied_for_every_role():
    assert not any(authz.can(_u(r), "delete:everything") for r in ROLES)


def test_requires_dependency_enforces_and_returns_the_user():
    dep = authz.requires(authz.DRAFT)
    assert dep(_u("writer")).role == "writer"
    with pytest.raises(ApiError):
        dep(_u("viewer"))
