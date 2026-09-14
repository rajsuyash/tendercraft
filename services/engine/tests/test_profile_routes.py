"""`PUT /api/profile` collections are omitted-means-unchanged, present-means-replace.

Regression for a field whose omission silently overwrote: `capability_keywords` was
`Field(default_factory=list)`, so a PUT that never touched the keywords box (any save from a
form editing a different section) sent `[]` anyway and wiped it. `list[str] | None = None`
restores the distinction between "the caller said nothing" and "the caller said empty".
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import AuthedUser, get_current_user
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="t1", role="admin",
    )
    return TestClient(app)


def test_omitting_capability_keywords_leaves_them_untouched(client, monkeypatch):
    patches: list[dict] = []
    monkeypatch.setattr(db, "upsert_vendor_profile", lambda ws, patch: patches.append(patch))
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: None)
    monkeypatch.setattr(db, "get_profile_context", lambda ws: {"legal_identity": {}})

    res = client.put("/api/profile", json={"legal_name": "Usha Martin Limited"})

    assert res.status_code == 200, res.text
    assert len(patches) == 1
    assert "capability_keywords" not in patches[0], \
        "an omitted field must never reach the upsert patch — it would overwrite the stored value"
    assert patches[0]["legal_name"] == "Usha Martin Limited"


def test_sending_an_empty_list_clears_capability_keywords(client, monkeypatch):
    patches: list[dict] = []
    monkeypatch.setattr(db, "upsert_vendor_profile", lambda ws, patch: patches.append(patch))
    monkeypatch.setattr(db, "write_audit", lambda *a, **k: None)
    monkeypatch.setattr(db, "get_profile_context", lambda ws: {"legal_identity": {}})

    res = client.put("/api/profile", json={"capability_keywords": []})

    assert res.status_code == 200, res.text
    assert len(patches) == 1
    assert patches[0]["capability_keywords"] == [], \
        "an explicit [] must still mean 'clear them', not 'unchanged'"
