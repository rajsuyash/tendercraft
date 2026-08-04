"""Section drafter — structure, narrative-eligibility, and fallbacks (no live model)."""

from __future__ import annotations

from pipeline import section_drafter as sd

CHUNKS = [{"id": "c1", "name": "past-proposal.pdf", "text": "our delivery methodology"}]
CTX = "Tender: e-Office Software Implementation"


def _stub(payload):
    return lambda prompt, schema, **kw: payload


def _sub(heading, sentences, order=1):
    return {"heading": heading, "order": order, "sentences": sentences}


def _sent(text, citations=(), cls="narrative"):
    return {"text": text, "citations": list(citations), "proposed_class": cls}


def _draft(monkeypatch, payload, key="approach_methodology"):
    monkeypatch.setattr(sd, "generate_json", _stub(payload))
    spec_heading = "Form 7(c): Technical Approach and Methodology"
    return sd.draft_section(key, spec_heading, 2500, CTX, CHUNKS)


def test_every_narrative_key_has_a_brief():
    from app.sections import NARRATIVE_KEYS

    missing = [k for k in NARRATIVE_KEYS if k not in sd._BRIEFS]
    assert missing == [], f"narrative sections with no brief: {missing}"


def test_briefs_are_substantive():
    assert all(len(b.split()) > 30 for b in sd._BRIEFS.values())


def test_unknown_key_is_a_placeholder_not_a_crash():
    r = sd.draft_section("not_a_section", "X", 100, CTX, CHUNKS)
    assert r.status == "placeholder"


def test_model_error_falls_back_to_placeholder(monkeypatch):
    def boom(*a, **k):
        raise sd.ModelError("down")

    monkeypatch.setattr(sd, "generate_json", boom)
    r = sd.draft_section("qa", "QA", 1200, CTX, CHUNKS)
    assert r.status == "placeholder"
    assert "not yet drafted" in r.body_md


def test_insufficient_context_is_a_placeholder(monkeypatch):
    r = _draft(monkeypatch, {"has_sufficient_context": False, "confidence": 0.2,
                             "subsections": []})
    assert r.status == "placeholder"


def test_model_self_veto_is_overridden_for_evidence_free_sections(monkeypatch):
    """Regression from live run 3: 'understanding' returned has_sufficient_context:false and
    placeholdered to 0 words, despite drafting 5 subsections happily when given no evidence
    at all. Whether a section may bail is a deterministic call, not the model's."""
    monkeypatch.setattr(sd, "generate_json", _stub({
        "has_sufficient_context": False, "confidence": 0.4,
        "subsections": [_sub("Scope", [_sent("The department requires workflow automation.")])],
    }))
    r = sd.draft_section("understanding", "Understanding", 1500, CTX, CHUNKS,
                         needs_bidder_evidence=False)
    assert r.status == "drafted"
    assert r.word_count > 0


def test_model_self_veto_is_honoured_when_bidder_facts_are_required(monkeypatch):
    monkeypatch.setattr(sd, "generate_json", _stub({
        "has_sufficient_context": False, "confidence": 0.4,
        "subsections": [_sub("Profile", [_sent("The bidder is experienced.")])],
    }))
    r = sd.draft_section("letter_of_proposal", "Letter", 400, CTX, CHUNKS,
                         needs_bidder_evidence=True)
    assert r.status == "placeholder"


def test_structure_is_emitted_as_headed_markdown(monkeypatch):
    r = _draft(monkeypatch, {
        "has_sufficient_context": True, "confidence": 0.8,
        "subsections": [
            _sub("Delivery phases", [_sent("Work proceeds in phased tranches.")], order=1),
            _sub("Governance", [_sent("A steering committee reviews progress.")], order=2),
        ],
    })
    assert r.status == "drafted"
    assert "### Delivery phases" in r.body_md
    assert "### Governance" in r.body_md
    assert r.word_count > 0


def test_subsections_are_ordered(monkeypatch):
    r = _draft(monkeypatch, {
        "has_sufficient_context": True, "confidence": 0.8,
        "subsections": [
            _sub("Second", [_sent("Later prose.")], order=2),
            _sub("First", [_sent("Earlier prose.")], order=1),
        ],
    })
    assert r.body_md.index("### First") < r.body_md.index("### Second")


def test_narrative_prose_stands_without_a_citation(monkeypatch):
    """The gap this closes: methodology is a forward commitment, so nothing exists to cite."""
    r = _draft(monkeypatch, {
        "has_sufficient_context": True, "confidence": 0.9,
        "subsections": [_sub("Approach", [
            _sent("Requirements are elicited through structured workshops."),
            _sent("Deployment follows a phased rollout with departmental sign-off."),
        ])],
    })
    assert r.status == "drafted"
    assert r.flags == []
    assert r.narrative_sentences == 2


def test_a_bidder_fact_in_a_narrative_section_still_needs_a_citation(monkeypatch):
    r = _draft(monkeypatch, {
        "has_sufficient_context": True, "confidence": 0.9,
        # Proposed "narrative", but evidentiary phrasing -> coerced to claim -> must cite.
        "subsections": [_sub("Approach", [_sent("We have delivered similar systems.")])],
    })
    assert r.status == "unverified"
    assert r.flags[0]["reason"] == "unverified"


def test_a_money_figure_hard_blocks_even_in_a_narrative_section(monkeypatch):
    """Without this the new sections would be a hole straight around B-AC4."""
    r = _draft(monkeypatch, {
        "has_sufficient_context": True, "confidence": 0.9,
        "subsections": [_sub("Approach", [_sent("The programme is valued at ₹8.2 Cr.")])],
    })
    assert r.flags[0]["reason"] == "uncited_financial"


def test_cited_claim_in_a_narrative_section_is_clean(monkeypatch):
    r = _draft(monkeypatch, {
        "has_sufficient_context": True, "confidence": 0.9,
        "subsections": [_sub("Approach", [
            _sent("Our methodology is documented in prior engagements.", ["c1"], cls="claim"),
        ])],
    })
    assert r.status == "drafted"
    assert r.flags == []


def test_empty_subsections_are_skipped_not_rendered(monkeypatch):
    r = _draft(monkeypatch, {
        "has_sufficient_context": True, "confidence": 0.7,
        "subsections": [_sub("Empty", []), _sub("Real", [_sent("Prose here.")])],
    })
    assert "### Empty" not in r.body_md
    assert "### Real" in r.body_md


def test_all_subsections_empty_is_a_placeholder(monkeypatch):
    r = _draft(monkeypatch, {"has_sufficient_context": True, "confidence": 0.7,
                             "subsections": [_sub("Empty", [])]})
    assert r.status == "placeholder"


def test_no_evidence_still_drafts_approach_prose(monkeypatch):
    """A methodology section is written from professional practice, not from the library."""
    monkeypatch.setattr(sd, "generate_json", _stub({
        "has_sufficient_context": True, "confidence": 0.8,
        "subsections": [_sub("Approach", [_sent("Work proceeds in phased tranches.")])],
    }))
    r = sd.draft_section("approach_methodology", "Methodology", 2500, CTX, [])
    assert r.status == "drafted"


# ---------- house style (Phase 4) ----------
def _captured_prompt(monkeypatch, style_brief=""):
    seen: dict = {}

    def _capture(prompt, schema, **kw):
        seen["prompt"] = prompt
        return {"subsections": [_sub("H", [_sent("The team will deliver in phases.")])],
                "has_sufficient_context": True}

    monkeypatch.setattr(sd, "generate_json", _capture)
    sd.draft_section("approach_methodology", "Form 7(c)", 2500, CTX, CHUNKS,
                     style_brief=style_brief)
    return seen["prompt"]


def test_a_workspace_with_no_past_bids_gets_the_prompt_unchanged():
    # The placeholder must be inert, not merely harmless: an empty brief leaves nothing behind
    # but whitespace, so drafting behaviour for existing workspaces is untouched.
    assert "{{STYLE_BRIEF}}" in sd._TEMPLATE


def test_an_empty_brief_leaves_no_style_instruction_in_the_prompt(monkeypatch):
    prompt = _captured_prompt(monkeypatch, "")
    assert "House style" not in prompt
    assert "{{STYLE_BRIEF}}" not in prompt  # substituted, never leaked as a literal


def test_a_measured_brief_reaches_the_model(monkeypatch):
    from app.deterministic.style import build_profile

    corpus = ["We have delivered platforms for state departments and retained ownership. " * 60]
    brief = build_profile(corpus)["brief"]
    prompt = _captured_prompt(monkeypatch, brief)
    assert "House style" in prompt
    # It sits with the instructions, not inside the evidence — style is never citable material.
    assert prompt.index("House style") < prompt.index("Evidence chunks available")
