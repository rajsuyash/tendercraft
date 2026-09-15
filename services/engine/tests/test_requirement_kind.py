"""What role a requirement plays — and therefore whether it may vote on bid/no-bid.

Every sentence quoted here is real, taken from the live Oil India wire-rope bid
(GEM/2026/B/7876746) on 2026-09-15, where eighteen criteria were mandatory, all eighteen
voted, and none of them was a pre-bid eligibility gate. The card read NO-BID.
"""

import pytest

from app.deterministic.requirement_kind import classify_kind, effective_kind
from app.deterministic.types import RequirementKind as K

# --- the four post-award duties that produced the live NO-BID -------------------------------


@pytest.mark.parametrize("text", [
    "FOR ALL THE ITEMS, FULL QUANTITY PROOF LOAD TEST MUST BE CONDUCTED AND WILL BE WITNESSED "
    "BY BHEL SAFETY ENGINEER DURING PRE DESPATCH INSPECTION AT VENDORS WORKS.",
    "INTIMATION FOR INSPECTION TO BHEL SAFTETY ENGINEER SHLOULD BE GIVEN 15 DAYS IN ADVANCE.",
    "LOAD TEST MUST BE CERTIFIED BY COMPETENT PERSON (AUTHORIZED BY FACTORY INSPECTOR) & "
    "CERTIFICATE MUST BE SUBMITTED.",
])
def test_a_duty_that_binds_after_award_is_not_a_gate(text):
    assert classify_kind(text, "technical", "mandatory") is K.OBLIGATION


@pytest.mark.parametrize("text", [
    "The warranty period shall be 24 months from the date of delivery.",
    "Payment shall be made within 30 days of receipt of the material.",
    "Liquidated damages will apply for late delivery.",
    "Inspection shall be carried out at the vendor's works.",
    "The certificate is to be produced at the time of despatch.",
    "Upon award the successful bidder shall execute an agreement.",
    "Spares shall be supplied within 45 days from the order.",
    "Testing during manufacture is at the buyer's discretion.",
])
def test_every_temporal_marker_reads_as_an_obligation(text):
    assert classify_kind(text) is K.OBLIGATION


def test_a_duty_whose_object_is_the_goods_is_an_obligation():
    """No temporal marker at all, but the thing being tested is what gets supplied — which
    cannot happen before there is a contract."""
    assert classify_kind("Each coil shall be load tested before despatch.") is K.OBLIGATION
    assert classify_kind("All items are to be inspected and certified.") is K.OBLIGATION


# --- instructions: how to bid, which can neither pass nor fail ------------------------------


@pytest.mark.parametrize("text", [
    "Bidders to quote Rate / No. as defined above against the item.",
    "Bidders to note the Unit of measurement against each item as defined in QTY column above.",
    "QUOTED rates are inclusive of taxes and duties as per GEM GTC",
    "Acceptance to GEM GTC",
    "Instructions to bidders are given in Section II.",
    "The last date for submission of bids is 30/09/2026.",
    "Bid opening date will be intimated separately.",
    "A pre-bid meeting will be held on 10/09/2026.",
    "Any corrigendum will be published on the portal.",
    "Documents must be uploaded on the portal before the deadline.",
    "Bidders are advised to read the specification carefully.",
])
def test_how_to_bid_is_an_instruction(text):
    assert classify_kind(text) is K.INSTRUCTION


# --- forms: a template to fill in and attach -------------------------------------------------


def test_a_blank_declaration_template_is_a_form():
    """The strongest signal in the corpus: nothing else in a tender contains a run of
    underscores where a human is expected to write."""
    text = ("The details of the location(s) at which the local value addition is made are as "
            "follows: __________________________________________________")
    assert classify_kind(text, "terms", "mandatory") is K.FORM


@pytest.mark.parametrize("text", [
    "Make in india certificate as per format enclosed submitted duly sealed and signed",
    "Bidder has to submit the above format, duly filled & signed by authorized signatory.",
    "The undertaking shall be in the prescribed proforma.",
    "The declaration must be on the letterhead of the bidder.",
    "Submit the certificate as per annexure attached.",
])
def test_a_named_template_is_a_form(text):
    assert classify_kind(text) is K.FORM


def test_a_form_that_mentions_turnover_is_still_a_form():
    """Precedence matters: the structural signal wins over the eligibility vocabulary, or a
    blank turnover declaration would be scored as the turnover requirement itself."""
    text = "Annual turnover for the last three years: FY24 ______ FY25 ______ FY26 ______"
    assert classify_kind(text, "financial", "mandatory") is K.FORM


# --- gates: the only kind that votes ---------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Average annual turnover of Rs 10 Crore in the last three financial years.",
    "The bidder shall have a net worth of not less than Rs 2 Crore.",
    "Positive working capital as certified by a chartered accountant.",
    "A solvency certificate from a scheduled bank is required.",
    "Three similar works of comparable nature executed in the last five years.",
    "Experience of having successfully completed similar works.",
    "The bidder must have 5 years of past experience in this field.",
    "Valid ISO 9001 certification on the date of bid submission.",
    "The rope shall conform to IS 2266 and the bidder shall hold a valid licence.",
    "API Spec 9A monogram is required.",
    "In case of trader/agent, valid authorization certificate from OEM to be submitted.",
    "A manufacturer's authorisation form is mandatory for a dealer.",
    "MAF from the principal is required.",
    "The bidder must not be blacklisted by any government body.",
    "Firms debarred by the ministry are not eligible.",
    "EMD of Rs 3,12,000 must be furnished.",
    "Earnest money is payable as specified.",
    "Bid security declaration in lieu of EMD is acceptable.",
    "MSE bidders are exempt on production of a Udyam certificate.",
    "DPIIT recognised start-up firms may apply.",
    "A valid GST registration is required.",
    "PAN of the bidder must be furnished.",
    "CIN of the company shall be stated.",
    "The bidder should be registered with the Department of Industries.",
    "BIS licence holders only.",
])
def test_a_condition_on_the_bidder_is_a_gate(text):
    assert classify_kind(text) is K.GATE


def test_the_extractor_s_own_eligibility_judgement_is_trusted_when_no_noun_matches():
    """It read the page. Dropping a real gate because our vocabulary list is short is the one
    error this module must not make."""
    assert classify_kind("Only empanelled firms may participate.", "eligibility",
                         "mandatory") is K.GATE
    # ...but only for mandatory eligibility. A desirable one is not a gate.
    assert classify_kind("Only empanelled firms may participate.", "eligibility",
                         "desirable") is K.OBLIGATION


# --- the asymmetry ---------------------------------------------------------------------------


def test_unrecognised_text_is_an_obligation_never_a_gate():
    """The whole design, in one assertion. A requirement wrongly called an obligation still
    shows on the checklist and a human can promote it in one click. A requirement wrongly
    called a gate can produce a false NO-BID — and nobody audits the bids they were told to
    skip, so that error is invisible by construction."""
    assert classify_kind("Commercial deviations are not acceptable", "terms",
                         "mandatory") is K.OBLIGATION
    assert classify_kind("") is K.OBLIGATION
    assert classify_kind("Refer to Section 4.") is K.OBLIGATION


# --- the override ------------------------------------------------------------------------------


def test_an_override_wins_in_both_directions():
    duty = {"verbatim_text": "Each coil shall be load tested before despatch.",
            "category": "technical", "requirement_level": "mandatory"}
    assert effective_kind(duty) is K.OBLIGATION
    assert effective_kind({**duty, "kind_override": "gate"}) is K.GATE

    gate = {"verbatim_text": "Average annual turnover of Rs 10 Crore.",
            "category": "financial", "requirement_level": "mandatory"}
    assert effective_kind(gate) is K.GATE
    assert effective_kind({**gate, "kind_override": "instruction"}) is K.INSTRUCTION


def test_an_absent_override_is_not_an_override():
    row = {"verbatim_text": "Average annual turnover of Rs 10 Crore.",
           "category": "financial", "requirement_level": "mandatory", "kind_override": None}
    assert effective_kind(row) is K.GATE


def test_effective_kind_survives_a_row_missing_every_optional_field():
    assert effective_kind({}) is K.OBLIGATION


# --- the override endpoint ---------------------------------------------------------------


def test_setting_a_kind_requires_the_draft_permission_and_audits(monkeypatch):
    from fastapi.testclient import TestClient

    from app import tenders
    from app.auth import AuthedUser, get_current_user
    from app.main import create_app

    audited: list = []
    monkeypatch.setattr(tenders.db, "set_criterion_kind",
                        lambda cid, ws, kind: [{"id": cid}])
    monkeypatch.setattr(tenders.db, "write_audit",
                        lambda ws, u, ev, ent, eid, **kw: audited.append((ev, kw)))

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="ws-1", role="writer")
    with TestClient(app) as client:
        r = client.post("/api/criteria/c-1/kind", json={"kind": "gate"})
    assert r.status_code == 200
    assert audited[0][0] == "criterion_kind_set"

    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u2", workspace_id="ws-1", role="viewer")
    with TestClient(app) as client:
        assert client.post("/api/criteria/c-1/kind", json={"kind": "gate"}).status_code == 403


def test_clearing_an_override_sends_an_explicit_null(monkeypatch):
    """The payload that means "go back to the computed kind" is `null`, and a filter that
    strips nulls would make clearing unreachable — the defect this repo already shipped once
    on PATCH /api/opportunities/{id}."""
    from fastapi.testclient import TestClient

    from app import tenders
    from app.auth import AuthedUser, get_current_user
    from app.main import create_app

    sent: list = []
    monkeypatch.setattr(tenders.db, "set_criterion_kind",
                        lambda cid, ws, kind: sent.append(kind) or [{"id": cid}])
    monkeypatch.setattr(tenders.db, "write_audit", lambda *a, **k: None)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="ws-1", role="writer")
    with TestClient(app) as client:
        assert client.post("/api/criteria/c-1/kind", json={"kind": None}).status_code == 200
    assert sent == [None]


def test_an_unknown_kind_is_refused_by_the_schema(monkeypatch):
    from fastapi.testclient import TestClient

    from app import tenders
    from app.auth import AuthedUser, get_current_user
    from app.main import create_app

    monkeypatch.setattr(tenders.db, "set_criterion_kind", lambda *a: [{"id": "c"}])
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="ws-1", role="writer")
    with TestClient(app) as client:
        assert client.post("/api/criteria/c-1/kind", json={"kind": "banana"}).status_code == 422
