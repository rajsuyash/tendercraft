"""The document-presence gate (F18).

The test that matters most here is `test_unresolved_files_never_produce_missing`. Every other
test describes convenience; that one describes the difference between an officer chasing a
document and a bidder being removed from a public tender because our ingestion had not
finished. `MISSING` is the only verdict that costs a bidder their bid, so it is the only one
we must be certain of.
"""

import pytest

from evaluate.deterministic.presence import (
    AttributedFile,
    Presence,
    PresenceCell,
    Requirement,
    apply_override,
    evaluate_requirement,
    missing_mandatory,
    screen_bid_documents,
)

EMD = Requirement("r-emd", "Earnest Money Deposit", accepted_types=("emd",))
ISO = Requirement("r-iso", "ISO 9001 certificate", accepted_types=("certificate",))
ANY = Requirement("r-any", "Anything the officer typed but has not classified")
OPTIONAL = Requirement("r-opt", "Covering letter", mandatory=False,
                       accepted_types=("covering_letter",))


def _f(fid, dtype, confirmed=False):
    return AttributedFile(fid, dtype, confirmed)


def _cell(req, files, unresolved=False):
    return evaluate_requirement(req, files, bid_id="bid-1", has_unresolved_files=unresolved)


# ── the guard that protects a bidder ───────────────────────────────────────────
def test_unresolved_files_never_produce_missing():
    """F18-AC4. While anything of this bidder's is in triage we cannot distinguish
    'they did not send it' from 'we have not read everything yet'."""
    cell = _cell(EMD, [], unresolved=True)
    assert cell.verdict is Presence.NEEDS_REVIEW
    assert "awaiting attribution" in (cell.reason or "")


def test_missing_only_once_nothing_is_unresolved():
    assert _cell(EMD, [], unresolved=False).verdict is Presence.MISSING


def test_a_match_is_present_even_while_other_files_are_unresolved():
    """Finding the document is definitive. Only its ABSENCE is uncertain."""
    cell = _cell(EMD, [_f("f1", "emd")], unresolved=True)
    assert cell.verdict is Presence.PRESENT
    assert cell.matched_file_id == "f1"


# ── matching ───────────────────────────────────────────────────────────────────
def test_matches_on_accepted_document_type():
    assert _cell(EMD, [_f("f1", "emd")]).verdict is Presence.PRESENT
    assert _cell(EMD, [_f("f1", "certificate")]).verdict is Presence.MISSING


def test_an_unclassified_requirement_is_satisfied_by_any_document():
    """An empty accepted_types means the officer has not narrowed it — not that nothing
    can satisfy it. Reading it the other way marks every bidder missing."""
    assert _cell(ANY, [_f("f1", "covering_letter")]).verdict is Presence.PRESENT


def test_a_requirement_with_no_files_at_all_is_missing():
    assert _cell(ANY, []).verdict is Presence.MISSING


def test_a_human_confirmed_match_is_cited_over_a_model_proposed_one():
    """The cell should point at the strongest evidence available, so an officer checking it
    lands on the file a person already vouched for."""
    cell = _cell(EMD, [_f("guessed", "emd"), _f("confirmed", "emd", confirmed=True)])
    assert cell.matched_file_id == "confirmed"


def test_a_file_with_no_document_type_does_not_satisfy_a_typed_requirement():
    assert _cell(EMD, [_f("f1", None)]).verdict is Presence.MISSING


# ── whole-bid screening ────────────────────────────────────────────────────────
def test_screen_bid_documents_returns_one_cell_per_requirement_in_order():
    cells = screen_bid_documents([EMD, ISO], [_f("f1", "emd")],
                                 bid_id="bid-1", has_unresolved_files=False)
    assert [c.requirement_id for c in cells] == ["r-emd", "r-iso"]
    assert [c.verdict for c in cells] == [Presence.PRESENT, Presence.MISSING]


# ── overrides ──────────────────────────────────────────────────────────────────
def test_an_override_replaces_the_verdict_and_is_marked_as_one():
    cell = _cell(EMD, [])
    out = apply_override(cell, "present", "received in physical form at the counter")
    assert out.verdict is Presence.PRESENT
    assert out.overridden is True
    assert out.reason == "received in physical form at the counter"


def test_no_override_leaves_the_computed_cell_untouched():
    cell = _cell(EMD, [_f("f1", "emd")])
    assert apply_override(cell, None, None) is cell


# ── findings ───────────────────────────────────────────────────────────────────
def test_missing_mandatory_lists_only_definitive_mandatory_gaps():
    cells = (
        PresenceCell("r-emd", "b1", Presence.MISSING),
        PresenceCell("r-iso", "b1", Presence.NEEDS_REVIEW),   # uncertain — not a finding
        PresenceCell("r-opt", "b1", Presence.MISSING),        # optional — not a finding
    )
    assert missing_mandatory(cells, [EMD, ISO, OPTIONAL]) == ("r-emd",)


def test_missing_mandatory_is_empty_when_everything_is_present():
    cells = (PresenceCell("r-emd", "b1", Presence.PRESENT, "f1"),)
    assert missing_mandatory(cells, [EMD]) == ()


@pytest.mark.parametrize("verdict", [Presence.PRESENT, Presence.NEEDS_REVIEW])
def test_only_missing_ever_becomes_a_finding(verdict):
    cells = (PresenceCell("r-emd", "b1", verdict),)
    assert missing_mandatory(cells, [EMD]) == ()
