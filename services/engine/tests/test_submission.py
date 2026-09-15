"""One readiness figure that reconciles — four contradictory counters became one."""

from app.deterministic.submission import STAGES, compute

CLEAR = dict(
    confirm_open=0, p0_blocking=0, sections_total=17, sections_placeholder=0,
    narrative_unapproved=0, approvals_done=2, approvals_required=2,
)


def test_a_finished_bid_is_submittable_at_100_percent():
    s = compute(**CLEAR)
    assert s.can_submit
    assert s.percent == 100
    assert s.blockers == ()


def test_every_blocker_names_its_stage_and_a_readable_detail():
    s = compute(**{**CLEAR, "confirm_open": 3, "p0_blocking": 1,
                   "narrative_unapproved": 9, "approvals_done": 0})
    assert s.blocker_count == 4
    for b in s.blockers:
        assert b.stage in dict(STAGES)
        assert len(b.detail) > 10
        assert not b.detail.isupper()


def test_the_count_and_the_list_can_never_disagree():
    """The original defect: the export gate said '13 blockers' and nothing on screen listed
    13 of anything — the breakdown existed only in raw JSON."""
    s = compute(**{**CLEAR, "confirm_open": 2, "p0_blocking": 1, "sections_placeholder": 3,
                   "narrative_unapproved": 9, "approvals_done": 1})
    assert s.blocker_count == len(s.blockers)
    assert s.blocker_count == 5


def test_the_current_stage_is_the_earliest_incomplete_one():
    s = compute(**{**CLEAR, "confirm_open": 1, "narrative_unapproved": 9})
    assert s.stage == "requirements"
    assert s.stage_label == "Requirements confirmed"


def test_progress_reflects_stages_actually_cleared():
    assert compute(**{**CLEAR, "approvals_done": 0}).percent == 80
    assert compute(**{**CLEAR, "confirm_open": 1, "p0_blocking": 1, "sections_total": 0,
                      "narrative_unapproved": 4, "approvals_done": 0}).percent == 0


def test_an_ungenerated_proposal_blocks_the_document_stage():
    s = compute(**{**CLEAR, "sections_total": 0})
    assert any(b.stage == "document" for b in s.blockers)
    assert not s.can_submit


def test_hard_blockers_are_included_and_prevent_submission():
    s = compute(**CLEAR, hard_blockers=["uncited financial claim in solution"])
    assert not s.can_submit
    assert any("uncited financial" in b.detail for b in s.blockers)


def test_stage_labels_are_human_not_internal_keys():
    for key, label in STAGES:
        assert key.islower() and "_" not in label
        assert label[0].isupper()


# --- readiness and the export gate answer the same question ---------------------------------


def test_a_gate_blocker_the_counters_cannot_see_still_blocks_submission():
    """Codex C3, reproduced: readiness reported 100% and can_submit while export refused the
    same proposal. The counters here summarise SECTIONS and APPROVALS; a mandatory criterion
    whose response is still a placeholder lives in neither, so a fully-approved document with
    an unanswered mandatory requirement read as ready."""
    state = compute(
        confirm_open=0, p0_blocking=0,
        sections_total=17, sections_placeholder=0, narrative_unapproved=0,
        approvals_done=2, approvals_required=2,
        mandatory_unanswered=3,
    )
    assert state.can_submit is False
    assert state.percent < 100
    assert any("3 mandatory requirement(s) still have no answer" == b.detail
               for b in state.blockers)


def test_unanswered_mandatory_requirements_are_one_counted_line_not_one_row_each():
    """The first cut appended the gate's own strings: 24 rows on a real tender, 11 of them a
    bare UUID and three restating the line above. A "how close am I" meter cannot also be the
    itemised list."""
    state = compute(
        confirm_open=0, p0_blocking=0,
        sections_total=17, sections_placeholder=0, narrative_unapproved=9,
        approvals_done=1, approvals_required=2,
        mandatory_unanswered=11,
    )
    assert len(state.blockers) == 3
    assert not any("-" in b.detail and len(b.detail) > 100 for b in state.blockers)


def test_a_clean_proposal_with_no_gate_blockers_can_submit():
    """The control: the guard must not make submission unreachable."""
    state = compute(
        confirm_open=0, p0_blocking=0,
        sections_total=17, sections_placeholder=0, narrative_unapproved=0,
        approvals_done=2, approvals_required=2,
    )
    assert state.can_submit is True
    assert state.percent == 100


# --- was the document actually read? ---------------------------------------------------------


def _clean(**over):
    base = dict(confirm_open=0, p0_blocking=0, sections_total=17, sections_placeholder=0,
                narrative_unapproved=0, approvals_done=2, approvals_required=2)
    base.update(over)
    return compute(**base)


def test_pages_nobody_could_read_block_submission():
    """The illegible list lived only in the upload response and was never persisted, so once
    that screen closed nothing anywhere recorded that part of the tender had never been read.
    "Ready to submit" could be true with a third of the package unreadable."""
    state = _clean(pages_unread=17)
    assert state.can_submit is False
    assert any("17 page(s) of the package could not be read" == b.detail for b in state.blockers)


def test_requirement_sentences_that_became_no_criterion_block_submission():
    """G-FR2's denominator had exactly one consumer — the matrix screen's own badge — so a
    proposal could pass every gate with a backlog of obligations nothing had answered."""
    state = _clean(open_unmapped=4)
    assert state.can_submit is False
    assert any("4 requirement sentence(s)" in b.detail for b in state.blockers)


def test_both_belong_to_the_reading_stage_not_the_review_stage():
    """Whether the document was read precedes whether its requirements were confirmed, so a
    meter that puts these under "Sections approved" sends the user to the wrong screen."""
    state = _clean(pages_unread=2, open_unmapped=1)
    assert {b.stage for b in state.blockers} == {"requirements"}


def test_a_fully_read_package_adds_no_blocker():
    """The control: these must not become a permanent floor."""
    assert _clean(pages_unread=0, open_unmapped=0).can_submit is True
