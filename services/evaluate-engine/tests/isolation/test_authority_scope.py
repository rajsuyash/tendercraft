"""FIX-8 — authority A never sees authority B, proven where it is actually enforced.

**Why this file is not a live-stack RLS replay.** The bidder product's isolation suite signs
real users into an ephemeral Supabase and lets the policies decide, which is right for it: that
engine's queries run as the caller. This engine does not. `evaluate/db.py` opens with

    The service role BYPASSES RLS, so every function here MUST scope by authority_id explicitly
    — the code enforces what the policy would. A missing authority filter is a cross-authority
    read.

So for the path that serves this product, the RLS policies are a backstop and **the Python
filter is the control**. A suite that only exercised policies would pass while the service-role
path leaked, which is the same shape of mistake as testing the sealed-bid gate by asserting its
predicate. These tests therefore assert the two properties that actually hold the wall up:

  1. every data-access function that accepts an `authority_id` puts it in the query it sends,
     and
  2. a request for another authority's tender is refused at the API, not merely filtered.

A live-stack replay of the RLS policies is still worth having and is NOT covered here; it is
recorded as an open item in docs/evaluate/test-strategy.md rather than quietly implied by a
green suite.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evaluate import db
from evaluate.auth import AuthedUser, get_current_user
from evaluate.main import create_app

A = "a0000000-0000-4000-8000-00000000000a"
B = "a0000000-0000-4000-8000-00000000000b"
B_TENDER = "e0000000-0000-4000-8000-0000000000bb"

DB_SRC = Path(__file__).resolve().parents[2] / "evaluate" / "db.py"


def _public_functions_taking_authority() -> list[str]:
    out = []
    for name, fn in vars(db).items():
        if name.startswith("_") or not inspect.isfunction(fn):
            continue
        if fn.__module__ != db.__name__:
            continue
        if "authority_id" in inspect.signature(fn).parameters:
            out.append(name)
    return sorted(out)


def test_there_are_authority_scoped_functions_to_check():
    """Guards the two tests below against silently passing on an empty set — a refactor that
    renamed the parameter would otherwise turn this whole file green and meaningless."""
    fns = _public_functions_taking_authority()
    assert len(fns) >= 40, f"expected the full data-access surface, found {len(fns)}: {fns}"


@pytest.mark.parametrize("name", _public_functions_taking_authority())
def test_every_authority_scoped_function_uses_it(name):
    """The parameter must reach the query, not just the signature.

    Accepting `authority_id` and never referencing it is the exact defect this catches: it type
    checks, it reads correctly at the call site, and it returns every authority's rows.
    """
    source = inspect.getsource(getattr(db, name))

    # Strip the SIGNATURE before looking, then the docstring. Both found by planting a breach:
    # a function that declares `authority_id` and never uses it still contains the string in
    # its own parameter list, so the naive check passed on a deliberately leaky function. A
    # test that cannot fail on the defect it names is worse than none — it is counted as cover.
    body = source[source.index(")") + 1 :] if ")" in source else source
    body = re.sub(r'""".*?"""', "", body, flags=re.S)

    assert "authority_id" in body, (
        f"db.{name} accepts authority_id and never uses it — with the service role that is a "
        "cross-authority read, not a style problem"
    )


def test_no_query_helper_bypasses_the_scoping_convention():
    """`rest()` is the only way out to PostgREST, so a second raw client would be a second,
    unreviewed path to every authority's data."""
    src = DB_SRC.read_text()
    # One http.client call site, inside rest(). Anything else is a bypass.
    assert src.count("http.client.request") == 1, (
        "a second direct HTTP call appeared in db.py — every query must go through rest() so "
        "the authority-scoping convention has exactly one place to be broken"
    )
    for forbidden in ("httpx.get(", "httpx.post(", "httpx.request(", "requests."):
        assert forbidden not in src, f"{forbidden} bypasses the pooled client and the convention"


class TestTheApiRefusesAnotherAuthoritysTender:
    """Property 2: refusal at the handler, and a 404 rather than a 403.

    404 is deliberate and worth keeping: 403 confirms the tender exists, which tells authority A
    that authority B is running a procurement of that id. Existence is itself disclosure.
    """

    @pytest.fixture
    def client(self, monkeypatch):
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: AuthedUser(
            user_id="user-in-A", authority_id=A, role="officer")

        seen: list[tuple] = []

        def tender(tender_id: str, authority_id: str):
            seen.append((tender_id, authority_id))
            # The real query filters on both; a row belonging to B is simply not returned to A.
            return None if authority_id != B else {"id": B_TENDER, "authority_id": B}

        monkeypatch.setattr(db, "tender", tender)
        monkeypatch.setattr(db, "audit", lambda *a, **k: None)
        client = TestClient(app, raise_server_exceptions=False)
        client.seen = seen  # type: ignore[attr-defined]
        yield client
        app.dependency_overrides.clear()

    @pytest.mark.parametrize("path", [
        "", "/screening", "/technical", "/financial", "/result",
        "/report", "/award", "/audit", "/compliance", "/documents",
    ])
    def test_a_tender_in_another_authority_is_not_found(self, client, path):
        r = client.get(f"/api/tenders/{B_TENDER}{path}")
        assert r.status_code == 404, (
            f"/api/tenders/:id{path} returned {r.status_code} for another authority's tender"
        )
        body = r.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "TENDER_NOT_FOUND"

    def test_the_lookup_was_scoped_by_the_callers_own_authority(self, client):
        """Not just "it 404s" — it 404s *because* the query carried the caller's authority.

        A handler that fetched unscoped and then compared in Python would also 404 here, and
        would leak the moment someone removed the comparison. This asserts the scope is applied
        at the query, which is the property db.py's own docstring promises.
        """
        client.get(f"/api/tenders/{B_TENDER}")
        assert client.seen, "the handler never looked the tender up"  # type: ignore[attr-defined]
        for _, authority_id in client.seen:  # type: ignore[attr-defined]
            assert authority_id == A, (
                f"tender lookup used authority {authority_id}, not the caller's {A}"
            )

    def test_the_authority_is_never_taken_from_the_request(self, client):
        """Engine CLAUDE.md §4: authority id comes from the verified JWT, never the body.

        A header or body value that could override it is the entire attack: one authenticated
        user of any authority reads every authority.
        """
        r = client.get(
            f"/api/tenders/{B_TENDER}",
            headers={"X-Authority-Id": B},  # attacker-supplied
        )
        assert r.status_code == 404
        for _, authority_id in client.seen:  # type: ignore[attr-defined]
            assert authority_id == A, "a request header changed the authority scope"
