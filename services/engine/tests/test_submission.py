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
