"""The date window on published results (UML ask 5's "last five years").

Two separate things are tested here and only one of them is the portal's:
what we ASK GeM for (`portal_date`, in the payload) and what we KEEP from the answer
(`within_window`). The second exists because the first is a filter on a third-party endpoint
we cannot see inside — and a price history built from silently-unfiltered rows is a wrong
benchmark that someone prices a real bid against.
"""

from __future__ import annotations

import json

import pytest

from app.results import build_results_payload, portal_date, within_window


def window_of(payload: dict) -> dict:
    return json.loads(payload["payload"])["filter"]["byEndDate"]


# ---------- what we ask the portal for ----------

def test_iso_in_portal_format_out():
    """Callers speak ISO like everything else in this system; GeM writes DD-MM-YYYY."""
    assert portal_date("2026-09-30") == "30-09-2026"


def test_an_open_end_of_the_range_stays_blank():
    assert portal_date(None) == ""
    assert portal_date("") == ""


def test_a_malformed_date_raises_rather_than_passing_through():
    """A date GeM cannot parse is likely IGNORED rather than rejected, and an ignored filter
    returns unfiltered rows the caller would then label as a five-year window."""
    for bad in ("30-09-2026", "2026/09/30", "Sept 2026", "2026-13-01"):
        with pytest.raises(ValueError):
            portal_date(bad)


def test_the_payload_carries_the_window():
    payload = build_results_payload(1, "wire rope", "bid_awarded",
                                    "2021-04-01", "2026-03-31")
    assert window_of(payload) == {"from": "01-04-2021", "to": "31-03-2026"}


def test_no_window_keeps_the_previous_unfiltered_behaviour():
    """The parameter is additive: every existing caller must be unaffected."""
    assert window_of(build_results_payload(1, "wire rope")) == {"from": "", "to": ""}


def test_an_unknown_status_still_raises_with_a_window_supplied():
    with pytest.raises(ValueError):
        build_results_payload(1, "x", "nonsense", "2021-04-01", None)


# ---------- what we keep from the answer ----------

def test_a_record_inside_the_window_is_kept():
    assert within_window("2024-06-15T11:00:00Z", "2021-04-01", "2026-03-31")


def test_records_outside_either_edge_are_dropped():
    assert not within_window("2019-01-01T00:00:00Z", "2021-04-01", "2026-03-31")
    assert not within_window("2026-12-01T00:00:00Z", "2021-04-01", "2026-03-31")


def test_the_edges_are_inclusive():
    """A five-year window that silently excluded its own first day would under-count the
    oldest year — the one hardest to notice is missing."""
    assert within_window("2021-04-01T09:00:00Z", "2021-04-01", "2026-03-31")
    assert within_window("2026-03-31T23:59:00Z", "2021-04-01", "2026-03-31")


def test_a_record_with_no_date_is_excluded_from_a_BOUNDED_window():
    """"Date unknown" cannot be asserted to fall inside a range. A five-year claim must not
    rest on rows carrying no date at all."""
    assert not within_window(None, "2021-04-01", "2026-03-31")
    assert not within_window("", "2021-04-01", "2026-03-31")


def test_a_record_with_no_date_survives_an_UNBOUNDED_request():
    """Without a window there is no claim to violate, and dropping undated rows here would
    silently shrink the corpus every existing caller already relies on."""
    assert within_window(None, None, None)


def test_one_open_edge_is_honoured():
    assert within_window("2019-01-01T00:00:00Z", None, "2020-01-01")
    assert not within_window("2019-01-01T00:00:00Z", "2020-01-01", None)


def test_the_local_check_is_what_survives_a_portal_that_ignores_the_filter():
    """The whole point of re-checking. If GeM ever stops honouring `byEndDate` — a renamed
    key, a format change — the response looks entirely normal and carries the wrong rows.
    This is the line that turns that from a wrong number into a smaller one."""
    as_if_unfiltered = ["2019-05-01T00:00:00Z", "2024-05-01T00:00:00Z", "2026-08-01T00:00:00Z"]
    kept = [d for d in as_if_unfiltered if within_window(d, "2024-01-01", "2024-12-31")]
    assert kept == ["2024-05-01T00:00:00Z"]
