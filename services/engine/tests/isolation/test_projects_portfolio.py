"""Projects + portfolio pagination — the 51st tender was permanently unreachable.

The tenders page did .limit(50) with no cursor, no search, no filter. A firm running 40
concurrent pursuits was already at the edge. Seeds 60 rows and pages past the old wall.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .conftest import (
    SERVICE_KEY,
    admin_create_user,
    admin_delete_user,
    admin_delete_users_by_email,
    grant_membership,
    requires_supabase,
    rest,
    sign_in,
)

PW = "Portfolio-Test-Pw-24!"
EMAIL = "portfolio-admin@tendercraft.test"
N = 60


@pytest.fixture(scope="module")
def workspace_with_many_tenders():
    users, ws = [], []
    try:
        admin_delete_users_by_email(EMAIL)
        _, w = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                    body={"name": "Portfolio Workspace"})
        workspace_id = w[0]["id"]
        ws.append(workspace_id)
        uid = admin_create_user(EMAIL, PW)
        users.append(uid)
        grant_membership(uid, workspace_id, "admin")

        _, p = rest("POST", "projects", bearer=SERVICE_KEY, key=SERVICE_KEY,
                    body={"workspace_id": workspace_id, "name": "Airtel FY27 refresh"})
        project_id = p[0]["id"]

        rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body=[{"workspace_id": workspace_id, "title": f"Pursuit {i:03d}",
                    "authority": "MahaIT" if i % 2 else "NIC",
                    "project_id": project_id if i < 5 else None}
                   for i in range(N)])
        yield {"jwt": sign_in(EMAIL, PW), "workspace_id": workspace_id,
               "project_id": project_id}
    finally:
        for uid in users:
            admin_delete_user(uid)
        for w_id in ws:
            rest("DELETE", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?workspace_id=eq.{w_id}")
            rest("DELETE", "projects", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?workspace_id=eq.{w_id}")
            rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?id=eq.{w_id}")


def _get(f, path):
    from app.main import app

    return TestClient(app, raise_server_exceptions=False).get(
        path, headers={"Authorization": f"Bearer {f['jwt']}"}
    )


@requires_supabase
def test_every_tender_is_reachable_by_paging(workspace_with_many_tenders):
    """The whole point: row 51 and row 60 must be retrievable, not just the first page."""
    f = workspace_with_many_tenders
    seen, cursor, pages = [], None, 0
    while pages < 10:
        r = _get(f, f"/api/tenders?limit=25{f'&cursor={cursor}' if cursor else ''}")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        seen += [t["title"] for t in data["tenders"]]
        cursor = data["next_cursor"]
        pages += 1
        if not cursor:
            break
    assert len(seen) == N, f"paged {len(seen)} of {N} in {pages} pages"
    assert len(set(seen)) == N, "keyset paging returned duplicates"
    assert "Pursuit 000" in seen and "Pursuit 059" in seen


@requires_supabase
def test_search_finds_a_tender_beyond_the_first_page(workspace_with_many_tenders):
    r = _get(workspace_with_many_tenders, "/api/tenders?q=Pursuit%20057")
    assert r.status_code == 200, r.text
    assert [t["title"] for t in r.json()["data"]["tenders"]] == ["Pursuit 057"]


@requires_supabase
def test_filter_by_project(workspace_with_many_tenders):
    f = workspace_with_many_tenders
    r = _get(f, f"/api/tenders?project_id={f['project_id']}")
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]["tenders"]) == 5


@requires_supabase
def test_search_matches_the_authority_too(workspace_with_many_tenders):
    r = _get(workspace_with_many_tenders, "/api/tenders?q=MahaIT&limit=100")
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]["tenders"]) == N // 2


@requires_supabase
def test_limit_is_bounded(workspace_with_many_tenders):
    """An unbounded limit is the same pitfall as no pagination, pointed the other way."""
    r = _get(workspace_with_many_tenders, "/api/tenders?limit=100000")
    assert r.status_code == 200
    assert len(r.json()["data"]["tenders"]) <= 100


@requires_supabase
def test_projects_are_workspace_scoped(workspace_with_many_tenders):
    r = _get(workspace_with_many_tenders, "/api/projects")
    assert r.status_code == 200, r.text
    assert [p["name"] for p in r.json()["data"]["projects"]] == ["Airtel FY27 refresh"]
