"""Module H orchestration — schedule assembly and the fit assessment over stored rows.

The comparator is proven in test_spec_match.py. What is proven here is the wiring: that both
sources of a schedule reach the same table, that a stored row becomes the value it claims to be,
and that the fit screen's counts come from one function so they cannot disagree.
"""

from __future__ import annotations

import pytest

from app import spec_service
from app.deterministic.boq import BoqRow

WS = "ws-1"
TENDER = "tender-1"


def boq(description="Wire rope 20mm 6x36", row_number=5, **kw):
    return BoqRow(document=kw.pop("document", "BOQ.xlsx · Schedule-A"),
                  sheet_index=kw.pop("sheet_index", 1), row_number=row_number,
                  description=description, **kw)


def criterion(text="Rope shall be 20mm 6x36 IWRC", category="technical", id="crit-1", **kw):
    return {"id": id, "verbatim_text": text, "category": category,
            "anchor_page": kw.pop("anchor_page", 12),
            "anchor_document": kw.pop("anchor_document", "NIT.pdf"), **kw}


def param(key, kind="numeric", **kw):
    return {"param_key": key, "kind": kind, "unit": kw.pop("unit", None),
            "num_min": kw.pop("num_min", None), "num_max": kw.pop("num_max", None),
            "allowed_values": kw.pop("allowed_values", []),
            "raw_text": kw.pop("raw_text", "x")}


def line_row(id="line-1", params=(), **kw):
    return {"id": id, "description": kw.pop("description", "Wire rope 20mm"),
            "schedule_ref": kw.pop("schedule_ref", "Schedule-A"),
            "item_ref": kw.pop("item_ref", "1"), "quantity": kw.pop("quantity", 5000),
            "uom": kw.pop("uom", "m"), "anchor_document": kw.pop("anchor_document", "BOQ.xlsx"),
            "anchor_page": kw.pop("anchor_page", 1), "anchor_row": kw.pop("anchor_row", 5),
            "spec_parameters": list(params), **kw}


def spec_row(id, kind="envelope", label="Rope plant", params=(), gem=None):
    return {"id": id, "spec_kind": kind, "label": label, "gem_catalogue_id": gem,
            "spec_parameters": list(params)}


@pytest.fixture
def stub_db(monkeypatch):
    state = {"lines": [], "specs": []}
    monkeypatch.setattr(spec_service.db, "get_line_items", lambda t, w: state["lines"])
    monkeypatch.setattr(spec_service.db, "get_capability_specs", lambda w: state["specs"])
    return state


# ── a schedule comes from two places ─────────────────────────────────────────────────

def test_a_boq_row_becomes_a_line_item_anchored_to_its_worksheet_row():
    (row,) = spec_service.schedule_rows([boq()], [])
    assert row["anchor_row"] == 5
    assert row["anchor_document"] == "BOQ.xlsx · Schedule-A"
    assert row["source_criterion_id"] is None if "source_criterion_id" in row else True


def test_a_technical_criterion_also_becomes_a_line_item():
    """Most GeM rope bids state the specification in NIT prose and ship no BOQ at all. A
    schedule built only from spreadsheets would work on roughly one tender in five."""
    (row,) = spec_service.schedule_rows([], [criterion()])
    assert row["source_criterion_id"] == "crit-1"
    assert row["description"].startswith("Rope shall be")


@pytest.mark.parametrize("category", ["eligibility", "financial", "terms"])
def test_only_technical_criteria_become_line_items(category):
    """A turnover threshold is not a thing anyone manufactures. Turning every criterion into a
    schedule line would bury two real items under forty."""
    assert spec_service.schedule_rows([], [criterion(category=category)]) == []


def test_a_criterion_with_no_text_is_skipped():
    assert spec_service.schedule_rows([], [criterion(text="   ")]) == []


def test_both_sources_land_in_one_schedule():
    rows = spec_service.schedule_rows([boq(), boq(row_number=6)], [criterion()])
    assert len(rows) == 3


def test_persisting_an_empty_schedule_touches_nothing(monkeypatch):
    """A tender with no BOQ and no technical criteria must not DELETE an existing schedule as
    a side effect of a re-upload that read nothing."""
    called = []
    monkeypatch.setattr(spec_service.db, "replace_line_items",
                        lambda *a, **k: called.append(a))
    assert spec_service.persist_schedule(WS, TENDER, [], []) == []
    assert called == []


# ── a stored row becomes the value it claims to be ───────────────────────────────────

def test_a_numeric_row_round_trips_through_the_database_shape():
    (p,) = spec_service._params({"spec_parameters": [
        param("diameter", num_min="18", num_max="22", unit="mm")]})
    assert (p.num_min, p.num_max, p.unit) == (18.0, 22.0, "mm")


def test_an_open_ended_numeric_keeps_its_none_bound():
    (p,) = spec_service._params({"spec_parameters": [
        param("min_breaking_load", num_min=200, unit="kN")]})
    assert p.num_min == 200.0 and p.num_max is None


def test_an_enum_row_becomes_its_allowed_set():
    (p,) = spec_service._params({"spec_parameters": [
        param("core_type", "enum", allowed_values=["IWRC", "WSC"])]})
    assert p.allowed == frozenset({"IWRC", "WSC"})


@pytest.mark.parametrize("bad", [
    param("diameter"),                                  # numeric with no bounds
    param("core_type", "enum", allowed_values=[]),      # enum with no values
    param("core_type", "enum", allowed_values=["", " "]),
    param("", num_min=1),                               # no key at all
])
def test_a_row_that_cannot_decide_anything_is_dropped(bad):
    """The CHECK constraints refuse these on write. This is the guard for a row written before
    a constraint existed — it must be dropped, not silently compared as empty."""
    assert spec_service._params({"spec_parameters": [bad]}) == ()


def test_no_parameters_at_all_is_an_empty_tuple():
    assert spec_service._params({}) == ()


# ── the fit assessment ───────────────────────────────────────────────────────────────

def test_a_line_inside_a_recorded_catalogue_reports_published_with_its_sku(stub_db):
    stub_db["lines"] = [line_row(params=[param("diameter", num_min=20, num_max=20, unit="mm")])]
    stub_db["specs"] = [
        spec_row("env", params=[param("diameter", num_min=6, num_max=60, unit="mm")]),
        spec_row("cat", "catalogue", "SKU-4471", gem="GEM-CAT-4471",
                 params=[param("diameter", num_min=20, num_max=20, unit="mm")]),
    ]
    out = spec_service.assess_schedule(WS, TENDER)
    assert out["lines"][0]["catalogue_state"] == "published"
    assert out["lines"][0]["gem_catalogue_id"] == "GEM-CAT-4471"


def test_a_line_the_plant_can_make_but_has_not_listed_reports_creatable(stub_db):
    stub_db["lines"] = [line_row(params=[param("diameter", num_min=20, num_max=20, unit="mm")])]
    stub_db["specs"] = [spec_row("env", params=[param("diameter", num_min=6, num_max=60,
                                                      unit="mm")])]
    out = spec_service.assess_schedule(WS, TENDER)
    assert out["lines"][0]["catalogue_state"] == "creatable"
    assert out["lines"][0]["action_parameters"] == ["diameter"]


def test_a_line_outside_the_plant_names_the_parameter_to_clarify(stub_db):
    """Ask 2's deliverable — the pre-bid clarification list, not a verdict."""
    stub_db["lines"] = [line_row(params=[param("diameter", num_min=72, num_max=72, unit="mm")])]
    stub_db["specs"] = [spec_row("env", params=[param("diameter", num_min=6, num_max=60,
                                                      unit="mm")])]
    line = spec_service.assess_schedule(WS, TENDER)["lines"][0]
    assert line["catalogue_state"] == "not_creatable"
    assert line["action_parameters"] == ["diameter"]
    assert "outside" in line["parameters"][0]["reason"]


def test_a_line_nobody_has_read_is_unknown_and_never_a_deviation(stub_db):
    """The extractor being down, or a description nothing could be read from, must not tell a
    manufacturer they cannot make their own product."""
    stub_db["lines"] = [line_row(params=[])]
    stub_db["specs"] = [spec_row("env", params=[param("diameter", num_min=6, num_max=60,
                                                      unit="mm")])]
    line = spec_service.assess_schedule(WS, TENDER)["lines"][0]
    assert line["catalogue_state"] == "unknown"
    assert line["parameters_read"] == 0


def test_with_no_envelope_recorded_the_response_says_so_rather_than_rendering_empty(stub_db):
    stub_db["lines"] = [line_row(params=[param("diameter", num_min=20, unit="mm")])]
    stub_db["specs"] = []
    out = spec_service.assess_schedule(WS, TENDER)
    assert out["has_capability"] is False
    assert out["lines"][0]["catalogue_state"] == "unknown"


def test_the_response_states_whose_catalogue_this_is(stub_db):
    """G-1/G-8: we never read GeM. 'Published' means the record the bidder gave us, and the
    payload says so once so no screen has to invent the wording."""
    assert spec_service.assess_schedule(WS, TENDER)["catalogue_source"] == "recorded_by_you"


def test_the_summary_counts_come_from_the_same_rows_the_screen_shows(stub_db):
    """Four counters describing one object will disagree (docs/known-pitfalls.md). One
    function computes the figure and its breakdown."""
    env = spec_row("env", params=[param("diameter", num_min=6, num_max=60, unit="mm")])
    stub_db["specs"] = [env]
    stub_db["lines"] = [
        line_row("a", [param("diameter", num_min=20, num_max=20, unit="mm")]),
        line_row("b", [param("diameter", num_min=72, num_max=72, unit="mm")]),
        line_row("c", []),
    ]
    out = spec_service.assess_schedule(WS, TENDER)
    summary = out["summary"]
    assert summary["total"] == len(out["lines"]) == 3
    assert summary["creatable"] + summary["not_creatable"] + summary["unknown"] \
        + summary["published"] == summary["total"]


@pytest.mark.parametrize("row,expected", [
    (line_row(anchor_document="BOQ.xlsx", anchor_row=14), "BOQ.xlsx · row 14"),
    (line_row(anchor_document="NIT.pdf", anchor_row=None, anchor_page=12), "NIT.pdf · p.12"),
    (line_row(anchor_document=None, anchor_row=None, anchor_page=None), "no anchor"),
])
def test_every_line_says_where_a_human_would_go_to_check_it(row, expected):
    assert spec_service._anchor_label(row) == expected


# ── extraction writes what it read, and nothing when it read nothing ─────────────────

def test_extraction_stores_a_parameter_per_line_and_skips_the_unreadable(monkeypatch):
    from app.deterministic.spec_match import ParamValue
    from app.deterministic.spec_params import ParamKind

    written: dict[str, list] = {}
    monkeypatch.setattr(spec_service.db, "replace_line_item_parameters",
                        lambda w, lid, rows: written.__setitem__(lid, rows))
    monkeypatch.setattr(
        "pipeline.spec_extractor.extract_many",
        lambda descriptions: {
            "Wire rope 20mm": (ParamValue("diameter", ParamKind.NUMERIC, unit="mm",
                                          num_min=20, num_max=20, raw_text="20mm"),),
            "Unreadable": (),
        },
    )
    populated = spec_service.extract_schedule(WS, [
        line_row("a", description="Wire rope 20mm"),
        line_row("b", description="Unreadable"),
    ])
    assert populated == 1
    assert "b" not in written                       # nothing read -> nothing written
    assert written["a"][0]["param_key"] == "diameter"
    assert written["a"][0]["num_min"] == 20
