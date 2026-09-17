"""Pin every narrowed PostgREST select to the consumers that read its rows.

`db.get_criteria`, `db.get_sections` and `db.get_valid_library_docs` used to select `*`, so a
consumer could read any column and nothing would notice. Narrowing them saves real egress
(measured 2026-09-17: `requirement` is 40% of a criteria row set, `original_md` 37% of a
sections one, `text_content` 99% of a library one) and moves the failure from review time to
production: a caller reading a key the select omitted gets a `KeyError` on a live request.

So the narrow lists are asserted two ways, and BOTH are needed:

1. **Every key a real consumer touches is in the select.** A `Spy` row records each lookup and
   the consumers are the actual functions, not stubs. `docs/known-pitfalls.md` has the entry —
   "a stub that returns MORE than the real query does is not a test": nine green tests passed
   against a stub carrying `verbatim_text` while the real query selected `id` alone, and the
   first live call 500'd. A hand-written list of expected keys would repeat that mistake.

2. **Every column in the select exists in the schema.** A typo in a select list is not a
   `KeyError` — PostgREST answers 400 for the whole request, so the endpoint dies rather than
   degrading. The migration chain is the only source of truth for what a column is called.
"""

from __future__ import annotations

import re
from pathlib import Path

from app import db, export_service, matrix_routes, readiness_routes
from app.deterministic import export_gate, learning, lock
from app.deterministic import readiness as det_readiness

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


class Spy(dict):
    """A row that records every key looked up on it, however it is looked up."""

    def __init__(self, data: dict, seen: set[str]):
        super().__init__(data)
        self._seen = seen

    def __getitem__(self, key):
        self._seen.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._seen.add(key)
        return super().get(key, default)

    def __contains__(self, key):
        self._seen.add(key)
        return super().__contains__(key)


def _columns(select: str) -> list[str]:
    return [c.strip() for c in select.split(",") if c.strip()]


def _schema_columns(table: str) -> set[str]:
    """Column names the migration chain declares for `table`, from the SQL itself.

    Deliberately not a hardcoded list and not a live database: the chain is the contract, and
    a column that only exists in somebody's head is the failure this catches.

    One rename has to be handled by rule rather than by reading. 0010 renames `tenant_id` to
    `workspace_id` on EVERY table carrying it, inside `execute format('alter table public.%I
    rename column tenant_id to workspace_id', t)` in a loop — so there is no per-table
    statement any parser could find, and pretending otherwise would either break this check or
    quietly widen it. The rule is exact and narrow: a table that declared `tenant_id` has
    `workspace_id` after 0010, and no other name is granted.
    """
    found: set[str] = set()
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text()
        for body in re.findall(
            rf"create table (?:if not exists )?(?:public\.)?{table}\s*\((.*?)\n\);",
            sql, re.S | re.I,
        ):
            for line in body.splitlines():
                m = re.match(r"\s*([a-z_]+)\s+\S", line)
                if m and m.group(1) not in ("primary", "unique", "constraint", "foreign",
                                            "check", "references"):
                    found.add(m.group(1))
        for col in re.findall(
            rf"alter table (?:public\.)?{table}\s+add column (?:if not exists )?([a-z_]+)",
            sql, re.I,
        ):
            found.add(col)
        for _old, new in re.findall(
            rf"alter table (?:public\.)?{table}\s+rename column ([a-z_]+) to ([a-z_]+)",
            sql, re.I,
        ):
            found.add(new)
    if "tenant_id" in found:
        found.add("workspace_id")  # migration 0010, applied in a loop — see the docstring
    return found


def _criterion_row(select: str) -> dict:
    """A criteria row carrying ONLY the selected columns — the shape PostgREST returns."""
    full = {
        "id": "c1", "tender_id": "t1", "workspace_id": "w1",
        "verbatim_text": "The bidder shall hold a valid ISO 9001 certificate.",
        "category": "eligibility", "requirement_level": "mandatory",
        "evidence_required": "Certificate copy", "evaluation_weight": 5,
        "confidence": 0.91, "confirmed": True, "anchor_page": 12,
        "anchor_clause": "4.1(a)", "anchor_document": "NIT.pdf", "kind_override": None,
        "created_at": "2026-09-17T00:00:00Z", "requirement": {"kind": "boolean"},
        "requirement_hash": "h1",
    }
    return {k: full[k] for k in _columns(select)} if select != "*" else full


def _section_row(select: str, **over) -> dict:
    full = {
        "id": "s1", "workspace_id": "w1", "proposal_id": "p1", "key": "methodology",
        "parent_key": None, "heading": "Methodology", "order_index": 3, "kind": "narrative",
        "body_md": "Our approach is staged. " * 40, "sentences": [], "status": "drafted",
        "confidence": 0.9, "flags": [], "word_count": 160, "approved_by": "u1",
        "approved_at": "2026-09-17T00:00:00Z", "created_at": "2026-09-17T00:00:00Z",
        "edited_by": None, "edited_at": None, "original_md": "the drafter's first version",
        "included": True,
    }
    full.update(over)
    return {k: full[k] for k in _columns(select)} if select != "*" else full


# --------------------------------------------------------------------------------------
# 1. Every key a real consumer touches must be in the select.
# --------------------------------------------------------------------------------------

def test_criteria_without_requirement_covers_every_gate_and_coverage_consumer():
    """The four consumers that now receive the narrowed criteria row, run for real."""
    select = db.CRITERIA_WITHOUT_REQUIREMENT
    allowed = set(_columns(select))

    for label, consume in [
        ("lock gate", lambda rows: lock.evaluate_lock(
            [readiness_routes._to_domain(r) for r in rows])),
        ("readiness", lambda rows: det_readiness.compute_readiness(rows, None, [], [])),
        ("export gate", lambda rows: export_service.evaluate(
            rows, [], approvals_required=0, approvals_done=0, sections=[], approvals=[])),
        ("matrix kind", lambda rows: [matrix_routes.effective_kind(r) for r in rows]),
    ]:
        seen: set[str] = set()
        consume([Spy(_criterion_row(select), seen)])
        missing = seen - allowed
        assert not missing, (
            f"{label} reads {sorted(missing)}, which CRITERIA_WITHOUT_REQUIREMENT omits — "
            f"that is a KeyError on a live request, not a test failure"
        )
        assert seen, f"{label} read no column at all — the spy is not wired in"


def test_sections_without_original_covers_the_export_gate_and_the_harvester():
    select = db.SECTIONS_WITHOUT_ORIGINAL
    allowed = set(_columns(select))

    for label, consume in [
        ("export gate", lambda rows: export_service.evaluate(
            [], [], approvals_required=0, approvals_done=0, sections=rows, approvals=[])),
        ("harvester", lambda rows: learning.harvestable(rows)),
        ("content hash", lambda rows: export_gate.content_hash(rows)),
    ]:
        seen: set[str] = set()
        consume([Spy(_section_row(select), seen)])
        missing = seen - allowed
        assert not missing, (
            f"{label} reads {sorted(missing)}, which SECTIONS_WITHOUT_ORIGINAL omits"
        )
        assert seen, f"{label} read no column at all — the spy is not wired in"


def test_library_without_text_is_enough_to_count_cvs_but_not_to_draft():
    """The narrow library select serves listings and doc_type counts — never the drafter.

    The drafter chunks `text_content`; keeping that call wide is deliberate, and this asserts
    the two lists have not been swapped.
    """
    assert "text_content" not in db.LIBRARY_WITHOUT_TEXT
    assert "doc_type" in db.LIBRARY_WITHOUT_TEXT  # cv_count in rubric_service.compute
    assert "valid_to" in db.LIBRARY_WITHOUT_TEXT  # the validity HARD-filter reads it
    assert "text_content" in db.LIBRARY_WITH_TEXT


def test_validity_filter_still_applies_under_the_narrow_select(monkeypatch):
    """Narrowing must not drop `valid_to` — an expired doc reaching retrieval is B-AC3."""
    rows = [
        {"id": "a", "name": "valid", "doc_type": "cv", "valid_to": "2099-01-01"},
        {"id": "b", "name": "expired", "doc_type": "cv", "valid_to": "2020-01-01"},
        {"id": "c", "name": "no expiry", "doc_type": "cv", "valid_to": None},
    ]
    monkeypatch.setattr(db, "_rest", lambda *a, **k: rows)
    kept = db.get_valid_library_docs("w1", "2026-09-17", select=db.LIBRARY_WITHOUT_TEXT)
    assert [d["id"] for d in kept] == ["a", "c"]


# --------------------------------------------------------------------------------------
# 2. The approval trap: a narrower select must not change what a signature covers.
# --------------------------------------------------------------------------------------

def test_content_hash_is_identical_under_the_narrow_select():
    """`content_hash` reads `key` and `body_md` only, so the narrowing must be invisible.

    If it were not, every stored proposal approval would silently stop matching and every
    proposal in the product would drop back to unapproved — a data migration wearing the
    clothes of a query optimisation.
    """
    wide = [_section_row("*", key="a"), _section_row("*", key="b")]
    narrow = [_section_row(db.SECTIONS_WITHOUT_ORIGINAL, key="a"),
              _section_row(db.SECTIONS_WITHOUT_ORIGINAL, key="b")]
    assert export_gate.content_hash(wide) == export_gate.content_hash(narrow)


# --------------------------------------------------------------------------------------
# 3. Every column named actually exists. A typo here is a 400, not a KeyError.
# --------------------------------------------------------------------------------------

def test_every_narrowed_column_exists_in_the_migration_chain():
    for table, select in [
        ("criteria", db.CRITERIA_WITHOUT_REQUIREMENT),
        ("proposal_sections", db.SECTIONS_WITHOUT_ORIGINAL),
        ("library_documents", db.LIBRARY_WITHOUT_TEXT),
        ("library_documents", db.LIBRARY_WITH_TEXT),
    ]:
        schema = _schema_columns(table)
        assert schema, f"parsed no columns for {table} — the parser is broken, not the select"
        unknown = set(_columns(select)) - schema
        assert not unknown, f"{table}: select names {sorted(unknown)}, not in any migration"


def test_the_column_parser_can_fail():
    """A positive control. A parser that returns everything would pass the test above whatever
    the select said, so prove it refuses a name the migrations do not contain."""
    assert "definitely_not_a_column" not in _schema_columns("criteria")
    assert "requirement" in _schema_columns("criteria")  # added by 0045, via alter table


def test_narrowed_selects_omit_exactly_the_measured_heavy_columns():
    """The point of the change, stated as an assertion rather than only in a comment."""
    assert "requirement" not in _columns(db.CRITERIA_WITHOUT_REQUIREMENT)
    assert "requirement_hash" not in _columns(db.CRITERIA_WITHOUT_REQUIREMENT)
    assert "verbatim_text" in _columns(db.CRITERIA_WITHOUT_REQUIREMENT)
    assert "original_md" not in _columns(db.SECTIONS_WITHOUT_ORIGINAL)
    assert "body_md" in _columns(db.SECTIONS_WITHOUT_ORIGINAL)
    assert "sentences" in _columns(db.SECTIONS_WITHOUT_ORIGINAL)  # the export gate reads it


# --------------------------------------------------------------------------------------
# 4. The defaults are unchanged: a caller that did not opt in still gets the whole row.
# --------------------------------------------------------------------------------------

def test_defaults_still_select_everything(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(db, "_rest", lambda m, p, **k: sent.append(k.get("params") or {}) or [])

    db.get_criteria("t1", "w1")
    db.get_sections("p1", "w1")
    db.get_valid_library_docs("w1", "2026-09-17")

    assert sent[0]["select"] == "*"
    assert sent[1]["select"] == "*"
    assert sent[2]["select"] == db.LIBRARY_WITH_TEXT  # its previous explicit list, unchanged


def test_doc_id_narrows_the_library_read_to_one_row(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(db, "_rest", lambda m, p, **k: sent.append(k.get("params") or {}) or [])
    db.get_valid_library_docs("w1", "2026-09-17", doc_id="doc-7")
    assert sent[0]["id"] == "eq.doc-7"
    db.get_valid_library_docs("w1", "2026-09-17")
    assert "id" not in sent[1], "no doc_id must not add a filter"
