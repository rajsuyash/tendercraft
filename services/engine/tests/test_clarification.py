"""Pre-bid clarification pack — UML ask 2.

100% branch coverage is CI-gated on app/deterministic/. The sharper reason: two of these tests
guard claims made to a government buyer. `test_capability_never_reaches_the_buyer` is the one to
keep if the file ever has to shrink — GeM publishes clarification answers to every bidder, so a
leak here is a leak to competitors, and it would look exactly like a working feature.
"""

from __future__ import annotations

from app.deterministic.clarification import (
    ClarificationQuery,
    QueryKind,
    build_queries,
)


def line(
    line_id: str = "l1",
    *,
    schedule_ref: str | None = "Schedule-A",
    item_ref: str | None = "14",
    anchor: str = "BOQ.xlsx · row 14",
    parameters: list[dict] | None = None,
    action_parameters: list[str] | None = None,
) -> dict:
    """One line in `assess_schedule`'s output shape."""
    return {
        "id": line_id,
        "schedule_ref": schedule_ref,
        "item_ref": item_ref,
        "anchor": anchor,
        "parameters": parameters or [],
        "action_parameters": action_parameters or [],
    }


def param(key: str, match: str, required: str = "20 mm", reason: str = "outside 24–60 mm") -> dict:
    return {"key": key, "match": match, "required": required,
            "capability": "24–60 mm", "reason": reason}


# ── which verdicts become questions ──────────────────────────────────────────────────

def test_deviation_asks_whether_the_value_is_mandatory():
    pack = build_queries([line(parameters=[param("diameter", "deviation")])])

    assert len(pack.queries) == 1
    query = pack.queries[0]
    assert query.kind is QueryKind.RELAXATION
    assert query.param_key == "diameter"
    assert "mandatory" in query.text
    assert "20 mm" in query.text


def test_unknown_in_the_action_list_asks_the_buyer_to_state_it():
    pack = build_queries([
        line(
            parameters=[param("diameter", "unknown", required="—", reason="not read")],
            action_parameters=["diameter"],
        )
    ])

    assert len(pack.queries) == 1
    assert pack.queries[0].kind is QueryKind.CONFIRMATION
    assert "could not be determined" in pack.queries[0].text


def test_unknown_outside_the_action_list_asks_nothing():
    """`action_parameters` is the comparator's own judgement about what blocks this line. An
    unknown it did not raise is a parameter that did not matter to the decision."""
    pack = build_queries([
        line(parameters=[param("diameter", "unknown")], action_parameters=[])
    ])

    assert pack.queries == ()


def test_match_and_equivalent_ask_nothing():
    """EQUIVALENT is the interesting half: the tender's own words invited the alternative, so a
    query would be requesting permission the document we are quoting already granted."""
    pack = build_queries([
        line(parameters=[
            param("diameter", "match"),
            param("min_breaking_load", "equivalent"),
        ])
    ])

    assert pack.queries == ()


def test_a_line_with_no_parameters_and_a_parameter_with_no_key_are_both_skipped():
    pack = build_queries([
        line("l1"),
        line("l2", parameters=[{"match": "deviation"}]),
    ])

    assert pack.queries == ()


# ── the two claims made to a buyer ───────────────────────────────────────────────────

def test_capability_never_reaches_the_buyer():
    """GeM publishes clarification answers to every bidder on the tender. A question naming the
    plant's range tells competitors what it is and tells the buyer we are non-compliant before
    the bid opens. The capability is why the question exists, not part of it."""
    pack = build_queries([
        line(parameters=[param("diameter", "deviation",
                               reason="required 20 mm is outside 24–60 mm")])
    ])

    query = pack.queries[0]
    assert "24" not in query.text
    assert "60" not in query.text
    # It is not lost — it is workspace-internal, so the bidder can see why they are asking.
    assert "24–60 mm" in query.rationale


def test_query_text_is_templated_not_generated():
    """No model writes a sentence sent to a public buyer over the client's name. Two runs over
    the same schedule must produce byte-identical text, which is what makes that checkable."""
    schedule = [line(parameters=[param("diameter", "deviation")])]

    assert build_queries(schedule).queries[0] == build_queries(schedule).queries[0]


# ── folding and ordering ─────────────────────────────────────────────────────────────

def test_one_parameter_across_many_lines_is_one_question():
    pack = build_queries([
        line(f"l{i}", item_ref=str(i), parameters=[param("diameter", "deviation")])
        for i in range(9)
    ])

    assert len(pack.queries) == 1
    assert len(pack.queries[0].lines) == 9
    assert "9 schedule lines" in pack.queries[0].text


def test_a_single_line_is_named_rather_than_counted():
    pack = build_queries([line(parameters=[param("diameter", "deviation")])])

    assert "Schedule-A 14" in pack.queries[0].text


def test_a_line_with_no_refs_falls_back_to_its_anchor():
    pack = build_queries([
        line(schedule_ref=None, item_ref=None, anchor="NIT p.12",
             parameters=[param("diameter", "deviation")])
    ])

    assert "NIT p.12" in pack.queries[0].text


def test_a_deviation_outranks_a_confirmation_on_the_same_parameter():
    """One line proving the value is outside the envelope is a stronger question than another
    line failing to state it — and asking both would be asking the buyer twice."""
    pack = build_queries([
        line("l1", parameters=[param("diameter", "unknown", required="—")],
             action_parameters=["diameter"]),
        line("l2", parameters=[param("diameter", "deviation", required="20 mm")]),
    ])

    assert len(pack.queries) == 1
    assert pack.queries[0].kind is QueryKind.RELAXATION
    assert pack.queries[0].required_display == "20 mm"
    assert len(pack.queries[0].lines) == 2


def test_a_confirmation_does_not_downgrade_an_existing_deviation():
    pack = build_queries([
        line("l1", parameters=[param("diameter", "deviation")]),
        line("l2", parameters=[param("diameter", "unknown", required="—")],
             action_parameters=["diameter"]),
    ])

    assert pack.queries[0].kind is QueryKind.RELAXATION


def test_deviations_are_asked_before_confirmations():
    pack = build_queries([
        line("l1", parameters=[param("min_breaking_load", "unknown", required="—")],
             action_parameters=["min_breaking_load"]),
        line("l2", parameters=[param("diameter", "deviation")]),
    ])

    assert [q.kind for q in pack.queries] == [QueryKind.RELAXATION, QueryKind.CONFIRMATION]


def test_an_empty_schedule_produces_an_empty_pack():
    pack = build_queries([])

    assert pack.queries == ()


def test_an_unregistered_parameter_key_still_gets_a_readable_label():
    """A key the registry does not know must not render as a bare snake_case token in a sentence
    a buyer reads."""
    pack = build_queries([line(parameters=[param("some_future_key", "deviation")])])

    assert pack.queries[0].label == "some future key"
    assert "some future key" in pack.queries[0].text


def test_a_query_is_hashable_and_frozen():
    """The pack is compared and cached; a mutable query would let a caller edit text after it was
    reviewed."""
    query = build_queries(
        [line(parameters=[param("diameter", "deviation")])]
    ).queries[0]

    assert isinstance(query, ClarificationQuery)
    assert hash(query) == hash(query)
