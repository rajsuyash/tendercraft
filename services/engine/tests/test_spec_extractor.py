"""The model component of Module H — and the guarantee that it decides nothing.

Two things are pinned here that no eval can pin, because they are structural rather than
behavioural: the output schema has no verdict field, and a model failure produces silence
rather than a fabricated answer.
"""

from __future__ import annotations

import pytest

from app.deterministic.spec_match import ParamValue, SpecMatch, match_parameter
from app.deterministic.spec_params import ParamKind
from pipeline import spec_extractor
from pipeline.client import ModelError
from pipeline.schemas import SPEC_PARAMS_SCHEMA

ITEM = SPEC_PARAMS_SCHEMA["properties"]["parameters"]["items"]


def row(key, kind="numeric", **kw):
    return {"param_key": key, "kind": kind, "raw_text": kw.pop("raw", "x"),
            "confidence": kw.pop("confidence", 0.9), **kw}


# ── the structural guarantees ────────────────────────────────────────────────────────

def test_the_schema_has_no_verdict_field_of_any_kind():
    """The decisive structural test. CRITERION_EVAL_SCHEMA carries `model_verdict` and
    app/analysis.py still lets it decide every non-numeric criterion. Module H must not
    reacquire that shape by a well-meaning edit."""
    banned = ("verdict", "match", "decision", "passes", "eligible", "can_supply", "deviation")
    assert not [k for k in ITEM["properties"] if any(b in k for b in banned)]


def test_the_schema_has_no_equivalence_field():
    """Whether a requirement permits an equivalent is derived in Python from its own text.
    A model-reported flag here would be the `is_financial` defect again — the model setting
    the field that softens its own result."""
    assert not [k for k in ITEM["properties"] if "equiv" in k]


def test_param_key_is_a_closed_allowlist_rendered_from_the_registry():
    from app.deterministic.spec_params import PARAM_KEYS
    assert ITEM["properties"]["param_key"]["enum"] == list(PARAM_KEYS)


def test_raw_text_is_required_so_no_parameter_arrives_without_a_source():
    assert "raw_text" in ITEM["required"]


# ── a model failure is silence, never invention ──────────────────────────────────────

def test_a_model_error_yields_no_parameters_and_does_not_raise(monkeypatch):
    def boom(*_a, **_k):
        raise ModelError("upstream timeout")
    monkeypatch.setattr(spec_extractor, "generate_json", boom)
    assert spec_extractor.extract_parameters("Wire rope 20mm") == ()


def test_silence_becomes_unknown_at_the_comparator_never_a_deviation(monkeypatch):
    """The end-to-end consequence of the line above, which is the part that matters: an outage
    must not tell a manufacturer they cannot make their own product."""
    monkeypatch.setattr(spec_extractor, "generate_json",
                        lambda *_a, **_k: (_ for _ in ()).throw(ModelError("down")))
    extracted = spec_extractor.extract_parameters("Wire rope 20mm")
    capability = ParamValue("diameter", ParamKind.NUMERIC, unit="mm", num_min=6, num_max=60)
    assert extracted == ()
    # Nothing extracted -> nothing compared -> the line asks a human, and no verdict is reached.
    assert match_parameter(ParamValue("diameter", ParamKind.NUMERIC, num_min=20, num_max=20),
                           None).match is SpecMatch.UNKNOWN
    assert capability.num_max == 60  # untouched


@pytest.mark.parametrize("garbage", [None, {}, {"parameters": None}, {"parameters": "nope"}, []])
def test_a_malformed_response_yields_no_parameters(monkeypatch, garbage):
    monkeypatch.setattr(spec_extractor, "generate_json", lambda *_a, **_k: garbage)
    assert spec_extractor.extract_parameters("Wire rope 20mm") == ()


def test_non_dict_entries_inside_the_array_are_skipped(monkeypatch):
    monkeypatch.setattr(spec_extractor, "generate_json",
                        lambda *_a, **_k: {"parameters": ["junk", row("diameter", num_min=20)]})
    assert [p.key for p in spec_extractor.extract_parameters("x")] == ["diameter"]


def test_an_empty_description_never_reaches_the_model(monkeypatch):
    def fail(*_a, **_k):
        raise AssertionError("the model must not be called for an empty description")
    monkeypatch.setattr(spec_extractor, "generate_json", fail)
    assert spec_extractor.extract_parameters("") == ()
    assert spec_extractor.extract_parameters("   ") == ()


def test_an_overlong_description_is_truncated_before_it_is_sent(monkeypatch):
    captured = {}
    monkeypatch.setattr(spec_extractor, "generate_json",
                        lambda prompt, _s: captured.setdefault("prompt", prompt) and {})
    spec_extractor.extract_parameters("A" * 5000)
    assert "A" * 2001 not in captured["prompt"]


# ── turning rows into comparable parameters ──────────────────────────────────────────

def test_a_numeric_row_becomes_a_bounded_interval():
    (p,) = spec_extractor.parse_parameters([row("diameter", num_min=18, num_max=22, unit="mm")])
    assert (p.num_min, p.num_max, p.unit) == (18.0, 22.0, "mm")


def test_an_enum_row_becomes_a_single_allowed_value():
    (p,) = spec_extractor.parse_parameters([row("core_type", "enum", enum_value="IWRC")])
    assert p.kind is ParamKind.ENUM and p.allowed == frozenset({"IWRC"})


def test_a_numeric_with_no_bounds_is_dropped_rather_than_stored_as_undecidable():
    """The schema constrains shape, not sense. A bound-less numeric would compare as `unknown`
    forever while looking to the user like a parameter that was read."""
    assert spec_extractor.parse_parameters([row("diameter", unit="mm")]) == ()


def test_an_enum_with_no_value_is_dropped():
    assert spec_extractor.parse_parameters([row("core_type", "enum", enum_value="  ")]) == ()
    assert spec_extractor.parse_parameters([row("core_type", "enum")]) == ()


def test_an_unregistered_key_is_dropped_even_if_the_enum_let_it_through():
    assert spec_extractor.parse_parameters([row("shoe_size", num_min=9)]) == ()


def test_a_repeated_key_keeps_the_first_mention():
    """'20mm dia ... 20 mm' is one parameter. Two rows for one key make the database refuse
    the write and the whole line item fails on a duplicate the model never meant."""
    params = spec_extractor.parse_parameters([
        row("diameter", num_min=20, num_max=20, unit="mm", raw="20mm dia"),
        row("diameter", num_min=99, num_max=99, unit="mm", raw="99 mm"),
    ])
    assert len(params) == 1 and params[0].num_min == 20.0


def test_an_unparseable_number_is_treated_as_absent():
    (p,) = spec_extractor.parse_parameters([row("diameter", num_min=20, num_max="lots", unit="mm")])
    assert (p.num_min, p.num_max) == (20.0, None)


def test_a_missing_unit_is_none_not_an_empty_string():
    """describe_range appends the unit; '' would render '20 ' with a trailing space, and
    normalise_unit would have to special-case it."""
    (p,) = spec_extractor.parse_parameters([row("diameter", num_min=20, unit="")])
    assert p.unit is None


# ── batching ─────────────────────────────────────────────────────────────────────────

def test_identical_descriptions_are_extracted_once(monkeypatch):
    """A BOQ lists the same rope at four consignee sites. Four calls for one description is
    four times the model bill for one answer."""
    calls: list[str] = []

    def count(prompt, _schema):
        calls.append(prompt)
        return {"parameters": [row("diameter", num_min=20, unit="mm")]}

    monkeypatch.setattr(spec_extractor, "generate_json", count)
    out = spec_extractor.extract_many(["Rope 20mm", "Rope 20mm", " Rope 20mm ", "Rope 24mm"])
    assert len(calls) == 2
    assert set(out) == {"Rope 20mm", "Rope 24mm"}


def test_blank_descriptions_are_not_batched(monkeypatch):
    monkeypatch.setattr(spec_extractor, "generate_json", lambda *_a, **_k: {"parameters": []})
    assert spec_extractor.extract_many(["", "   ", None]) == {}
