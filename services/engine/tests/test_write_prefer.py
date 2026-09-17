"""Every PostgREST write asks for a body only when something reads it.

Supabase bills bytes LEAVING the database. `db._rest` defaults `Prefer` to
`return=representation`, which is NOT PostgREST's own default — the docs say "With
`Prefer: return=minimal`, no response body will be returned. This is the default mode for all
write requests" (https://docs.postgrest.org/en/v13/references/api/preferences.html). So every
POST/PATCH/DELETE in `db.py` that passes no `prefer` echoes its rows back, and until
2026-09-17 a 1200-bid GeM sweep paid ~2 MB three times a day to echo a corpus nobody read.

Two layers here, and they fail for different reasons on purpose:

  * `test_prefer_header_sent` drives the real function through a stubbed transport and asserts
    the exact `Prefer` bytes. It catches a header that was never actually sent.
  * `test_no_discarded_write_asks_for_a_representation` walks db.py's AST and catches the NEXT
    write somebody adds without a `prefer`. A table of 30 cases cannot do that, and the header
    test cannot see call sites nobody thought to add to it.

Nothing here touches the network: `http.client.request` is replaced wholesale.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app import db, http

DB_PY = Path(db.__file__)
WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


class _FakeResponse:
    """Just enough of httpx.Response for `_rest` and the egress ledger."""

    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, body: str = "[]") -> None:
        self.text = body
        self.content = body.encode()

    def raise_for_status(self) -> None:
        return None

    def json(self):  # noqa: ANN201 — mirrors httpx
        import json as _json

        return _json.loads(self.text)


@pytest.fixture
def sent(monkeypatch):
    """Capture the Prefer header of every request the call under test issues."""
    calls: list[dict] = []

    def _request(method, url, *, headers=None, params=None, json=None, timeout=None):
        calls.append({
            "method": method,
            "url": url,
            "prefer": (headers or {}).get("Prefer"),
        })
        # A representation-returning write is answered with one row so `rows[0]` works; a
        # minimal one is answered with an empty body, which is what PostgREST really sends.
        minimal = "return=minimal" in ((headers or {}).get("Prefer") or "")
        return _FakeResponse("" if minimal else '[{"id": "row-1"}]')

    monkeypatch.setattr(http.client, "request", _request)
    return calls


# ── the writes this pass narrowed: every one must send return=minimal ─────────────────────
#
# One entry per CHANGED write. `expect` lists the Prefer value of each request the call makes,
# in order — `create_invitation`, `replace_profile_collection` and `replace_award_prices` each
# issue two.

MINIMAL = "return=minimal"

NARROWED: list[tuple[str, object, list[str]]] = [
    ("save_criterion_requirements",
     lambda: db.save_criterion_requirements("ws", [{"id": "c1", "requirement": {},
                                                    "requirement_hash": "h"}]), [MINIMAL]),
    ("set_illegible_pages", lambda: db.set_illegible_pages("t", "ws", []), [MINIMAL]),
    ("set_tender_locked", lambda: db.set_tender_locked("t", "ws", "2026-09-17"), [MINIMAL]),
    ("save_proposal_outline", lambda: db.save_proposal_outline("ws", "p", {}), [MINIMAL]),
    ("set_section_included",
     lambda: db.set_section_included("ws", "p", "k", False), [MINIMAL]),
    ("approve_section",
     lambda: db.approve_section("ws", "p", "k", "u", "2026-09-17"), [MINIMAL]),
    ("set_proposal_status", lambda: db.set_proposal_status("p", "ws", "draft"), [MINIMAL]),
    ("mark_exported", lambda: db.mark_exported("p", "ws", "2026-09-17"), [MINIMAL]),
    ("set_member_role", lambda: db.set_member_role("u", "ws", "admin"), [MINIMAL]),
    ("remove_workspace_member", lambda: db.remove_workspace_member("u", "ws"), [MINIMAL]),
    ("set_active_workspace", lambda: db.set_active_workspace("u", "ws"), [MINIMAL]),
    ("clear_active_workspace", lambda: db.clear_active_workspace("u", "ws"), [MINIMAL]),
    ("create_invitation",
     lambda: db.create_invitation("ws", "a@b.test", "editor", "u", "hash"),
     [MINIMAL, MINIMAL]),
    ("mark_invitation_accepted",
     lambda: db.mark_invitation_accepted("i", "u", "2026-09-17"), [MINIMAL]),
    ("update_project", lambda: db.update_project("pr", "ws", {"name": "x"}), [MINIMAL]),
    ("set_tender_project", lambda: db.set_tender_project("t", "ws", None), [MINIMAL]),
    ("set_past_bid_outcome", lambda: db.set_past_bid_outcome("b", "ws", "won"), [MINIMAL]),
    ("set_tender_meta", lambda: db.set_tender_meta("t", "ws", "GEM/1", "Auth"), [MINIMAL]),
    ("update_tender", lambda: db.update_tender("t", "ws", {"title": "x"}), [MINIMAL]),
    ("replace_profile_collection",
     lambda: db.replace_profile_collection("ws", "financials", [{"fy": "FY25"}]),
     [MINIMAL, MINIMAL]),
    ("edit_section",
     lambda: db.edit_section("ws", "p", "k", "body", "u", "2026-09-17"), [MINIMAL]),
    ("append_reused_section_text",
     lambda: db.append_reused_section_text("ws", "p", "k", "text",
                                           {"sentences": [], "flags": []}), [MINIMAL]),
    ("set_match_stage",
     lambda: db.set_match_stage("ws", "o", "bid_awarded", "2026-09-17"), [MINIMAL]),
    ("insert_unmapped",
     lambda: db.insert_unmapped("ws", "t", [{"sentence": "s", "page": 1}]), [MINIMAL]),
    ("upsert_matrix_rows",
     lambda: db.upsert_matrix_rows("ws", "t", [{"criterion_id": "c"}]), [MINIMAL]),
    ("upsert_opportunities",
     lambda: db.upsert_opportunities([{"source_id": "gem", "portal_ref_no": "X"}]), [MINIMAL]),
    ("record_notifications",
     lambda: db.record_notifications("ws", [{"opportunity_id": "o", "recipient": "a@b.test",
                                             "kind": "digest"}]), [MINIMAL]),
    ("replace_award_prices",
     lambda: db.replace_award_prices("a", [{"seller": "X"}]), [MINIMAL, MINIMAL]),
]


@pytest.mark.parametrize("name,call,expect", NARROWED, ids=[c[0] for c in NARROWED])
def test_prefer_header_sent(sent, name, call, expect):
    call()
    # Only the writes. `edit_section` and `append_reused_section_text` read the section first
    # (PostgREST cannot write a column from another column's current value), and a GET is
    # supposed to return a body.
    actual = [c["prefer"] for c in sent if c["method"] in WRITE_METHODS]
    assert len(actual) == len(expect), f"{name} issued {len(actual)} requests, expected {expect}"
    for got, want in zip(actual, expect, strict=True):
        assert got is not None, f"{name} sent no Prefer header"
        assert want in got, f"{name} sent Prefer={got!r}, expected {want!r}"
        assert "return=representation" not in got, f"{name} still asks for a representation"


def test_upsert_opportunities_counts_what_it_sent(sent):
    """The corpus upsert no longer reads a body, so its count comes from the payload.

    Exact rather than an estimate: the write is one transaction and `merge-duplicates` writes
    every row, so a short write raises instead of returning fewer.
    """
    assert db.upsert_opportunities([{"portal_ref_no": "A"}, {"portal_ref_no": "B"}]) == 2
    assert db.upsert_opportunities([]) == 0
    # The empty case must not issue a request at all.
    assert len(sent) == 1


def test_record_notifications_counts_what_it_sent(sent):
    assert db.record_notifications("ws", [{"opportunity_id": "o"}]) == 1
    assert db.record_notifications("ws", []) == 0


def test_replace_award_prices_counts_the_ladder_it_wrote(sent):
    assert db.replace_award_prices("a", [{"seller": "X"}, {"seller": "Y"}]) == 2
    # Delete-then-insert: two requests for a non-empty ladder, one for an empty one.
    assert len(sent) == 2
    assert db.replace_award_prices("a", []) == 0
    assert len(sent) == 3


# ── the two calls that were passing a keyword `_rest` does not accept ──────────────────────

def test_pursuit_writes_reach_the_transport(sent):
    """`create_pursuit` and `link_pursuit_tender` spelled the header `headers=`, and `_rest`
    has no `headers` parameter — so both raised TypeError on every call. `tenders`
    swallows every exception from the pursuit link into a log line, so the discovery →
    pursuit → tender link failed in total silence.

    Both keep `return=representation`: the id and the workspace-guard answer come from it.
    """
    assert db.create_pursuit("ws", "o", "u") == {"id": "row-1"}
    assert db.link_pursuit_tender("ws", "p", "t") == {"id": "row-1"}
    assert len(sent) == 2
    for call in sent:
        assert "return=representation" in (call["prefer"] or "")


# ── the invariant, so the next write added cannot reintroduce the cost ────────────────────

def _write_calls() -> list[ast.Call]:
    tree = ast.parse(DB_PY.read_text())
    return [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_rest"
        and n.args
        and isinstance(n.args[0], ast.Constant)
        and n.args[0].value in WRITE_METHODS
    ]


def test_no_discarded_write_asks_for_a_representation():
    """A `_rest` write whose result is thrown away must not ask PostgREST for a body.

    Statement-expression position is the check: `_rest(...)` on a line of its own discards
    everything it returns, so any body it received was paid for and dropped. A call that omits
    `prefer` inherits `_rest`'s `return=representation` default, which is why the absence of
    the keyword is a failure here rather than a neutral fact.
    """
    tree = ast.parse(DB_PY.read_text())
    discarded = {
        (n.value.lineno, n.value.col_offset)
        for n in ast.walk(tree)
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
    }
    offenders = []
    for call in _write_calls():
        if (call.lineno, call.col_offset) not in discarded:
            continue
        prefer = next((ast.unparse(k.value) for k in call.keywords if k.arg == "prefer"), None)
        if prefer is None or "return=representation" in prefer:
            offenders.append(f"db.py:{call.lineno} prefer={prefer}")
    assert not offenders, (
        "these writes discard a body they asked PostgREST to send — pass "
        'prefer="return=minimal":\n  ' + "\n  ".join(offenders)
    )


def test_every_write_call_is_covered_by_this_file():
    """The AST test above is only as good as its reach — pin the population it walks.

    A drop to zero (a renamed `_rest`, a moved module) would make that test pass while
    checking nothing, which is the shape of failure this repo keeps rediscovering.
    """
    calls = _write_calls()
    assert len(calls) >= 80, f"only {len(calls)} write calls found — is the walk still working?"


#: Writes whose result is no longer a list of rows. `insert_unmapped` and `upsert_matrix_rows`
#: return None; the other three return an int count.
NARROWED_RETURNS = {
    "insert_unmapped", "upsert_matrix_rows",
    "upsert_opportunities", "record_notifications", "replace_award_prices",
}


def _rows_like_uses(source: str, label: str) -> list[str]:
    """Places in `source` that treat a narrowed write's return value as a sequence of rows."""
    tree = ast.parse(source)
    offenders: list[str] = []
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            if not (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)):
                continue
            if child.func.attr not in NARROWED_RETURNS:
                continue
            src = ast.unparse(child)
            if isinstance(parent, ast.Subscript):
                offenders.append(f"{label}:{child.lineno} indexes {src}")
            elif isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) \
                    and parent.func.id in {"len", "list", "sorted"}:
                offenders.append(f"{label}:{child.lineno} {parent.func.id}() of {src}")
            elif isinstance(parent, ast.comprehension | ast.For):
                offenders.append(f"{label}:{child.lineno} iterates {src}")
    return offenders


def test_the_caller_scan_can_see_a_real_offender():
    """Positive control. A scan that returns nothing looks identical whether it is correct or
    broken, so prove it fires on the three shapes it exists to catch before trusting its
    silence on the real tree."""
    assert len(_rows_like_uses("x = db.upsert_opportunities(r)[0]", "probe")) == 1
    assert len(_rows_like_uses("n = len(db.record_notifications(w, r))", "probe")) == 1
    assert len(_rows_like_uses("[y for y in db.insert_unmapped(w, t, r)]", "probe")) == 1
    assert _rows_like_uses("n = db.upsert_opportunities(r)", "probe") == []


def test_no_caller_indexes_a_now_minimal_write():
    """No call site treats a narrowed write's return value as rows.

    A caller doing `len(...)`, `rows[0]` or iterating one would be a TypeError in production,
    and these live on background paths where `tenders` and `discovery/ingest` swallow every
    exception into a log line — so the failure would be silent rather than loud. Grep the
    engine rather than trusting the review.
    """
    engine = DB_PY.parent.parent  # services/engine
    offenders: list[str] = []
    scanned = 0
    for path in sorted(engine.rglob("*.py")):
        if path == DB_PY or "tests" in path.parts or ".venv" in path.parts:
            continue
        scanned += 1
        offenders += _rows_like_uses(path.read_text(), str(path.relative_to(engine)))

    assert scanned > 20, f"only {scanned} engine modules scanned — is the walk still working?"
    assert not offenders, "callers still read a narrowed write's body:\n  " + "\n  ".join(
        offenders
    )
