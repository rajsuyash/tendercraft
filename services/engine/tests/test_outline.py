"""Which sections a tender's proposal actually needs.

Every clause quoted here is real, taken from the live corpus on 2026-09-15 — 2,000 criteria
across eleven tenders. The false positives have their own tests because each one cost a
section on a document where it made no sense, and a pattern that stops firing on them is the
only evidence that the tightening worked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.deterministic.outline import absent, derive, detect_signals


@dataclass(frozen=True)
class Spec:
    key: str
    heading: str = "H"
    order: int = 10
    requires: frozenset[str] = field(default_factory=frozenset)


def crit(text, **kw):
    row = {"verbatim_text": text, "anchor_page": 12, "anchor_clause": "4.1"}
    row.update(kw)
    return row


# --- the signals fire on real requirements ------------------------------------------------------


@pytest.mark.parametrize("name,text", [
    ("personnel", "Curriculum Vitae of the key personnel shall be submitted in Form 10."),
    ("personnel", "The agency shall deploy a Project Manager for the full contract period."),
    ("solution", "The agency is expected to use a CAPI system integrated with advanced "
                 "AI/ML software."),
    ("solution", "The selected Agency shall build an end-to-end data protection architecture."),
    ("training", "The field staff of the agency would have to be provided with adequate "
                 "training by the agency before commissioning the survey."),
    ("training", "Capacity building of the user department is part of the scope."),
    ("support", "In case Annual Maintenance Contract (AMC) is required, OIL intends to enter "
                "into a separate contract."),
    ("support", "A service level agreement shall govern the helpdesk response times."),
    ("workplan", "The bidder shall submit a phase-wise implementation schedule with "
                 "milestones."),
])
def test_a_real_requirement_raises_its_signal(name, text):
    assert name in detect_signals([crit(text)])


# --- and not on the things that look like them ---------------------------------------------------


@pytest.mark.parametrize("text", [
    # 23 hits across the goods tenders, every one of them the rope standard.
    "The rope shall be tested in accordance with API Specifications 9A.",
    "Bidder must have 5 years experience manufacturing under relevant API certification.",
    # Banking payment rails, named in an MSME clause and a bank-guarantee clause.
    "MSME Bidders are required to register on the TReDS platform.",
    "The Bank Guarantee must be routed through SFMS platform.",
    # A rope description.
    "For detailed technical information regarding the various types of wire ropes "
    "manufactured and their selection for various applications, refer Annexure.",
])
def test_a_wire_rope_tender_does_not_ask_for_a_software_architecture(text):
    """Each of these put a "Proposed Solution and Technical Architecture" section on a rope
    supply bid. The lesson is the one `discovery.py` already learned about bounded stems: a
    term short enough to be an acronym collides with a standard number, and only the corpus
    shows it."""
    assert "solution" not in detect_signals([crit(text)])


def test_a_bare_mention_of_training_is_not_a_training_requirement():
    assert "training" not in detect_signals([crit(
        "We confirm that the following has not been considered for calculation of local "
        "content: imported items sourced locally from resellers, and training costs.")])


def test_a_two_part_bid_system_is_not_a_system_integration():
    """`system` was measured alongside the terms that were kept and rejected for this."""
    assert detect_signals([crit("The offers shall be submitted in TWO Part Bid System.")]) == {}


def test_a_warranty_period_does_not_summon_a_support_and_sla_section():
    """Every goods tender in the corpus carries one. Matching it would put an O&M section on
    every rope bid, which is the defect rather than the fix."""
    assert "support" not in detect_signals([crit(
        "The warranty period shall be 24 months from the date of delivery.")])


def test_a_forms_boilerplate_does_not_vote_on_what_the_document_contains():
    """Measured on the live wire-rope bid: a local-content declaration saying "after sales
    service support like AMC/CMC etc." — inside a list of what is EXCLUDED from local content
    — put a Support/SLA/O&M section on a rope supply bid. A blank template is boilerplate the
    bidder fills in, not the buyer asking for something."""
    form = crit("Details of local value addition are as follows: ____________________ "
                "excluding after sales service support like AMC/CMC etc.")
    signals = detect_signals([form])
    assert "forms" in signals      # its EXISTENCE is a signal
    assert "support" not in signals  # its WORDING is not


# --- the structural signals ----------------------------------------------------------------------


def test_a_schedule_is_the_line_items_not_a_word_in_the_text():
    signals = detect_signals([], [{"schedule_ref": "Schedule-A", "item_ref": "14"}])
    assert signals["schedule"].because == "1 schedule line(s), first at Schedule-A 14"


def test_a_schedule_line_with_no_labels_still_reports_honestly():
    assert "unlabelled row" in detect_signals([], [{}])["schedule"].because


def test_a_published_evaluation_weight_raises_eval_heads():
    assert "eval_heads" in detect_signals([crit("Methodology", evaluation_weight=30)])
    assert "eval_heads" not in detect_signals([crit("Methodology", evaluation_weight=None)])


# --- every signal names the row that raised it ---------------------------------------------------


def test_a_signal_carries_the_clause_and_its_anchor():
    s = detect_signals([crit("Curriculum Vitae of key personnel are required.")])["personnel"]
    assert s.because == '“Curriculum Vitae of key personnel are required.” at p.12 · Cl. 4.1'


def test_an_unanchored_clause_says_so_rather_than_inventing_a_page():
    s = detect_signals([{"verbatim_text": "Key personnel CVs required."}])["personnel"]
    assert "unanchored" in s.because


def test_a_page_without_a_clause_is_still_a_usable_anchor():
    """The lock gate accepts a page alone, because real tenders state requirements in
    unnumbered prose. This must not be stricter than that."""
    s = detect_signals([{"verbatim_text": "Key personnel CVs required.", "anchor_page": 7}])
    assert s["personnel"].because.endswith("at p.7")


def test_a_long_clause_is_truncated_visibly():
    """A sentence silently cut at a word boundary reads as the tender's own wording."""
    s = detect_signals([crit("Capacity building " + "of the department " * 10)])["training"]
    assert s.because.startswith("“Capacity building")
    assert "…" in s.because


def test_only_the_first_matching_clause_is_cited():
    """The outline needs ONE citable reason. Listing every match turns an explanation into a
    wall."""
    rows = [crit("Capacity building is required.", anchor_page=3),
            crit("Capacity building is also required.", anchor_page=9)]
    assert detect_signals(rows)["training"].because.endswith("at p.3 · Cl. 4.1")


# --- derivation ----------------------------------------------------------------------------------


UNIVERSAL = Spec("letter", order=10)
GATED = Spec("cvs", order=20, requires=frozenset({"personnel"}))
TWO = Spec("both", order=5, requires=frozenset({"personnel", "schedule"}))


def test_a_universal_section_is_in_every_proposal_and_needs_no_reason():
    [entry] = derive([UNIVERSAL], {})
    assert entry.key == "letter"
    assert entry.because == ""


def test_a_gated_section_appears_only_with_its_signal():
    signals = detect_signals([crit("Key personnel CVs required.")])
    assert [e.key for e in derive([UNIVERSAL, GATED], signals)] == ["letter", "cvs"]
    assert [e.key for e in derive([UNIVERSAL, GATED], {})] == ["letter"]


def test_a_section_needing_two_signals_needs_both():
    signals = detect_signals([crit("Key personnel CVs required.")])
    assert derive([TWO], signals) == ()
    both = detect_signals([crit("Key personnel CVs required.")], [{"item_ref": "1"}])
    assert [e.key for e in derive([TWO], both)] == ["both"]


def test_the_outline_is_in_catalogue_order_not_detection_order():
    signals = detect_signals([crit("Key personnel CVs required.")], [{"item_ref": "1"}])
    assert [e.order for e in derive([GATED, UNIVERSAL, TWO], signals)] == [5, 10, 20]


def test_a_spec_without_a_requires_attribute_is_treated_as_universal():
    """`getattr(spec, "requires", frozenset())` rather than an attribute access: the catalogue
    is a plain dataclass and a section added without the field must ship, not crash."""
    class Bare:
        key, heading, order = "bare", "H", 1

    assert [e.key for e in derive([Bare()], {})] == ["bare"]


def test_a_gated_section_names_the_row_that_included_it():
    signals = detect_signals([crit("Curriculum Vitae of key personnel are required.")])
    [entry] = derive([GATED], signals)
    assert "Curriculum Vitae" in entry.because


def test_what_was_left_out_names_the_missing_signal():
    """Reported rather than silently omitted: a section the user expected and did not get is
    a bug report they cannot file unless the screen says why it is gone."""
    assert [(a.key, a.missing) for a in absent([UNIVERSAL, GATED, TWO], {})] == [
        ("cvs", "personnel"), ("both", "personnel, schedule")]
    signals = detect_signals([crit("Key personnel CVs required.")])
    assert [(a.key, a.missing) for a in absent([UNIVERSAL, GATED, TWO], signals)] == [
        ("both", "schedule")]


def test_an_absent_section_is_named_by_its_heading_and_explained_in_a_sentence():
    """A user-facing list rendering `team_composition` is showing someone a database
    identifier, and three entries all reading "(personnel)" explain nothing a reader can
    act on."""
    from app.sections import SPEC_BY_KEY

    [entry] = [a for a in absent(list(SPEC_BY_KEY.values()), {}) if a.key == "cvs"]
    assert entry.heading == "Form 10: Curriculum Vitae of Key Personnel"
    assert entry.because == "it asks for no named personnel or CVs"


def test_a_signal_with_no_written_meaning_still_produces_a_sentence():
    """A new signal added without a line in the table must degrade to something readable
    rather than to a blank."""
    assert absent([Spec("x", requires=frozenset({"quantum"}))], {})[0].because == (
        "it raises no quantum signal")
