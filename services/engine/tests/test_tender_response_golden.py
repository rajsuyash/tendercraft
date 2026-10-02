"""evals/tender_response/golden.py — loading, date parsing, vault_as_of, page-text resolution.

Uses the synthetic fixtures under evals/tender_response/fixtures/ (NOT customer data — a tiny
invented tender). CI must never need $TC_GOLDEN_DIR; every test here points it at the fixtures
dir via monkeypatch/tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.tender_response import golden

FIXTURES = Path(__file__).parent.parent / "evals" / "tender_response" / "fixtures"


def test_golden_dir_requires_env_var(monkeypatch):
    monkeypatch.delenv(golden.ENV_VAR, raising=False)
    with pytest.raises(golden.GoldenError, match=golden.ENV_VAR):
        golden.golden_dir()


def test_golden_dir_rejects_nonexistent_path(monkeypatch, tmp_path):
    monkeypatch.setenv(golden.ENV_VAR, str(tmp_path / "does-not-exist"))
    with pytest.raises(golden.GoldenError):
        golden.golden_dir()


def test_golden_dir_rejects_wrong_directory(monkeypatch, tmp_path):
    # exists, but has no requirements/ — a cheap "wrong path" guard
    monkeypatch.setenv(golden.ENV_VAR, str(tmp_path))
    with pytest.raises(golden.GoldenError, match="requirements"):
        golden.golden_dir()


def test_golden_dir_accepts_fixtures(monkeypatch):
    monkeypatch.setenv(golden.ENV_VAR, str(FIXTURES))
    assert golden.golden_dir() == FIXTURES


def test_list_tenders_finds_the_fixture_tender():
    assert golden.list_tenders(FIXTURES) == ["FIX_DEMO_001"]


def test_load_tender_reads_all_three_files():
    t = golden.load_tender(FIXTURES, "FIX_DEMO_001")
    assert t.slug == "FIX_DEMO_001"
    assert len(t.requirements) == 3
    assert len(t.submission_documents) == 3
    assert len(t.mapping) == 3


def test_load_tender_missing_file_raises_named_error(tmp_path):
    (tmp_path / "requirements").mkdir()
    (tmp_path / "submission_documents").mkdir()
    (tmp_path / "mapping").mkdir()
    (tmp_path / "requirements" / "GHOST.json").write_text("[]")
    with pytest.raises(golden.GoldenError, match="missing golden file"):
        golden.load_tender(tmp_path, "GHOST")


def test_malformed_json_raises_named_error(tmp_path):
    (tmp_path / "requirements").mkdir()
    (tmp_path / "submission_documents").mkdir()
    (tmp_path / "mapping").mkdir()
    (tmp_path / "requirements" / "BROKEN.json").write_text("{not valid json")
    (tmp_path / "submission_documents" / "BROKEN.json").write_text("[]")
    (tmp_path / "mapping" / "BROKEN.json").write_text("[]")
    with pytest.raises(golden.GoldenError, match="failed to parse"):
        golden.load_tender(tmp_path, "BROKEN")


def test_load_shared_reads_every_shared_file():
    shared = golden.load_shared(FIXTURES)
    assert len(shared.company_facts) == 2
    assert len(shared.template_candidates) == 1
    assert len(shared.missing_information_patterns) == 2
    assert len(shared.evidence_library["evidence"]) == 1
    assert len(shared.tenders) == 2


def test_mip_occurrences_filters_to_information_request_kind():
    shared = golden.load_shared(FIXTURES)
    occ = golden.mip_occurrences_for_tender(shared, "FIX_DEMO_001")
    assert [o["requirement_id"] for o in occ] == ["FIX-REQ-001"]  # the compliance_check row excluded


@pytest.mark.parametrize("raw,expected", [
    ("22-04-2024 11:00:00", "2024-04-22"),
    ("25.02.2026 upto 11:00 AM", "2026-02-25"),
    (None, None),
    ("not a date", None),
])
def test_parse_ddmmyyyy(raw, expected):
    assert golden.parse_ddmmyyyy(raw) == expected


class TestVaultAsOf:
    """FIX-FACT-001 is first-seen via FIX_DEMO_001 (bid_end 2024-01-01); FIX-FACT-002 only via
    FIX_DEMO_LATER (bid_end 2025-01-01) — see fixtures/tenders.json + company_facts.json."""

    def test_fact_visible_once_its_source_tender_has_bid(self):
        shared = golden.load_shared(FIXTURES)
        snap = golden.vault_as_of(shared, "2024-06-01")
        ids = {f["fact_id"] for f in snap.company_facts}
        assert "CF-FIX-001" in ids

    def test_fact_excluded_before_its_first_seen_date(self):
        shared = golden.load_shared(FIXTURES)
        # required test #5: a fact first seen after the as_of date must not be visible
        snap = golden.vault_as_of(shared, "2024-06-01")
        ids = {f["fact_id"] for f in snap.company_facts}
        assert "CF-FIX-002" not in ids

    def test_fact_becomes_visible_once_its_own_tender_has_bid(self):
        shared = golden.load_shared(FIXTURES)
        snap = golden.vault_as_of(shared, "2025-06-01")
        ids = {f["fact_id"] for f in snap.company_facts}
        assert {"CF-FIX-001", "CF-FIX-002"} <= ids

    def test_undated_fact_is_excluded_fail_closed(self, tmp_path):
        shared = golden.SharedGolden(
            template_candidates=[], missing_information_patterns=[],
            evidence_library={"evidence": [], "expiry_incidents": []},
            company_facts=[{
                "fact_id": "CF-ORPHAN", "source_document": "NOWHERE/doc.pdf",
                "also_seen_in": [],
            }],
            tenders=[],
        )
        snap = golden.vault_as_of(shared, "2099-01-01")
        assert snap.company_facts == []
        assert snap.excluded_undated_facts == 1


def test_also_seen_in_folder_style_slugs_resolve(monkeypatch):
    # also_seen_in[].tender_slug holds a FOLDER string (spaces), not the canonical slug —
    # reproduces what the real corpus does (ECL-GEM-2025-B-6929440 end 18.12.2025, etc.)
    shared = golden.SharedGolden(
        template_candidates=[], missing_information_patterns=[],
        evidence_library={"evidence": [], "expiry_incidents": []},
        company_facts=[{
            "fact_id": "CF-X", "source_document": "FIX DEMO 001/a.pdf",
            "also_seen_in": [{"tender_slug": "FIX DEMO LATER", "path": "x", "page": 1}],
        }],
        tenders=[
            {"slug": "FIX_DEMO_001", "folder": "FIX DEMO 001",
             "bid_end": {"value": "01-01-2024 00:00:00"}},
            {"slug": "FIX_DEMO_LATER", "folder": "FIX DEMO LATER",
             "bid_end": {"value": "01-01-2020 00:00:00"}},  # earlier than the primary source
        ],
    )
    snap = golden.vault_as_of(shared, "2020-06-01")
    # earliest of the two resolved tenders (2020, via also_seen_in) must win
    assert len(snap.company_facts) == 1


class TestPageTextResolution:
    def test_resolves_the_unique_directory_by_page_count_and_name(self):
        dirs = golden.candidate_dirs_for_document(FIXTURES, "FIX_DEMO_001", "BID DOC/bid.pdf")
        assert dirs == ["BidDoc"]

    def test_page_text_contains_the_cited_sentence(self):
        text = golden.page_text(FIXTURES, "FIX_DEMO_001", "BID DOC/bid.pdf", 1)
        assert "50000" in text

    def test_page_text_spans_a_page_range(self):
        text = golden.page_text(FIXTURES, "FIX_DEMO_001", "Other Doc/local.pdf", 1, 1)
        assert "16-09-2020" in text

    def test_unresolvable_file_falls_back_to_every_directory(self):
        # a source_document with no manifest entry at all still returns a list, never an error.
        dirs = golden.candidate_dirs_for_document(FIXTURES, "FIX_DEMO_001", "Ghost/nope.pdf")
        assert set(dirs) == {"BidDoc", "LocalDoc"}


@pytest.mark.parametrize("raw,norm", [
    ("GST Certificate", "gst certificate"),
    ("Declaration (Statutory)", "declaration"),
    ("Factory Licence", "factory license"),
    ("Cover Letter / Offer", "cover letter offer"),
    ("Past Performance — Tax Invoice", "past performance tax invoice"),
])
def test_normalize_document_type(raw, norm):
    assert golden.normalize_document_type(raw) == norm
