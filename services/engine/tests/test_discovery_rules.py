"""F-AC6 — nothing leaves the primary feed except by a named, user-authored rule.

Required to exist by tools/check-discovery-guardrails.sh, following the sealed-bid precedent: a
green suite that never exercised the catastrophic gate is worse than a red one. The gate here is
ET-7, the discovery miss — the only failure in this product with no natural feedback signal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.deterministic.discovery import (
    RULE_KINDS,
    EligibilityResult,
    Rule,
    evaluate_eligibility,
    evaluate_gate,
    keyword_relevance,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def record(**overrides):
    base = {
        "portal_ref_no": "GEM/2026/R/706528",
        "title": "Stationary Valve Regulated Lead Acid Batteries",
        "authority": "Ministry of Defence · Department of Military Affairs",
        "category_codes": ["home_powe_batt_batt_st87064165"],
        "closing_at": (NOW + timedelta(days=30)).isoformat(),
        "estimated_value": None,
        "geography": None,
    }
    return base | overrides


class TestNothingIsHiddenWithoutANamedRule:
    def test_no_rules_means_everything_is_in_scope(self):
        result = evaluate_gate(record(), [], now=NOW)
        assert result.in_scope is True
        assert result.excluded_by_rule is None

    def test_an_exclusion_always_names_its_rule(self):
        rule = Rule(name="Defence only", kind="authority_not_contains",
                    spec={"needles": ["Ministry of Railways"]})
        result = evaluate_gate(record(), [rule], now=NOW)
        assert result.in_scope is False
        assert result.excluded_by_rule == "Defence only"

    def test_a_disabled_rule_cannot_exclude(self):
        rule = Rule(name="off", kind="category_prefix_not_in",
                    spec={"prefixes": ["nothing_matches_"]}, enabled=False)
        assert evaluate_gate(record(), [rule], now=NOW).in_scope is True

    def test_an_unknown_rule_kind_is_inert_rather_than_excluding(self):
        # A rule kind this build does not understand — e.g. written by a newer UI — must not
        # remove tenders from someone's world on the way to being ignored.
        rule = Rule(name="from the future", kind="semantic_similarity", spec={"q": "batteries"})
        assert evaluate_gate(record(), [rule], now=NOW).in_scope is True

    def test_a_malformed_spec_is_inert(self):
        for kind in sorted(RULE_KINDS):
            rule = Rule(name=f"empty {kind}", kind=kind, spec={})
            assert evaluate_gate(record(), [rule], now=NOW).in_scope is True, kind

    def test_the_first_firing_rule_is_the_one_reported(self):
        rules = [
            Rule(name="A", kind="authority_contains", spec={"needles": ["Defence"]}),
            Rule(name="B", kind="authority_contains", spec={"needles": ["Ministry"]}),
        ]
        assert evaluate_gate(record(), rules, now=NOW).excluded_by_rule == "A"


class TestMissingDataNeverCausesAnExclusion:
    """Absence must stay absence. Every one of these would be a tender hidden by a rule the user
    did not write, which is F-AC6's definition of a breach."""

    def test_no_closing_date_is_not_treated_as_closing_today(self):
        rule = Rule(name="7+ days", kind="min_days_to_close", spec={"days": 7})
        assert evaluate_gate(record(closing_at=None), [rule], now=NOW).in_scope is True

    def test_an_unparseable_closing_date_does_not_exclude(self):
        rule = Rule(name="7+ days", kind="min_days_to_close", spec={"days": 7})
        assert evaluate_gate(record(closing_at="not a date"), [rule], now=NOW).in_scope is True

    def test_an_absent_estimated_value_does_not_exclude(self):
        # GeM omits estimated value on most listings — it is in the document, not the feed. A
        # value rule that excluded on absence would hide most of the feed.
        rule = Rule(name="₹1L+", kind="value_between", spec={"min": 100_000})
        assert evaluate_gate(record(estimated_value=None), [rule], now=NOW).in_scope is True

    def test_an_empty_authority_does_not_match_a_contains_rule(self):
        rule = Rule(name="defence", kind="authority_contains", spec={"needles": ["Defence"]})
        assert evaluate_gate(record(authority=None), [rule], now=NOW).in_scope is True


class TestRulesThatShouldFire:
    def test_min_days_to_close_excludes_a_deadline_that_is_too_soon(self):
        rule = Rule(name="7+ days", kind="min_days_to_close", spec={"days": 7})
        soon = record(closing_at=(NOW + timedelta(days=2)).isoformat())
        assert evaluate_gate(soon, [rule], now=NOW).excluded_by_rule == "7+ days"

    def test_category_prefix_not_in_keeps_only_wanted_categories(self):
        rule = Rule(name="Services only", kind="category_prefix_not_in",
                    spec={"prefixes": ["services_"]})
        assert evaluate_gate(record(), [rule], now=NOW).in_scope is False
        services = record(category_codes=["services_home_cust"])
        assert evaluate_gate(services, [rule], now=NOW).in_scope is True

    def test_value_between_bounds(self):
        rule = Rule(name="₹1L–₹1Cr", kind="value_between",
                    spec={"min": 100_000, "max": 10_000_000})
        assert evaluate_gate(record(estimated_value=50_000), [rule], now=NOW).in_scope is False
        assert evaluate_gate(record(estimated_value=5_000_000), [rule], now=NOW).in_scope is True
        assert evaluate_gate(record(estimated_value=20_000_000), [rule], now=NOW).in_scope is False


class TestDepth1Eligibility:
    """C-AC8: a fuzzy or unknown criterion is never auto-passed at Depth 1."""

    def test_no_document_read_yet_is_unknown(self):
        assert evaluate_eligibility(None, {"avg_annual_turnover_inr": 82_000_000}).signal == "unknown"

    def test_no_turnover_requirement_is_unknown_not_eligible(self):
        result = evaluate_eligibility({"min_avg_annual_turnover_inr": None},
                                      {"avg_annual_turnover_inr": 82_000_000})
        assert result.signal == "unknown"

    def test_no_profile_turnover_is_unknown_not_ineligible(self):
        result = evaluate_eligibility({"min_avg_annual_turnover_inr": 500_000}, {})
        assert result.signal == "unknown"
        assert "no turnover on record" in result.reason

    def test_meeting_the_threshold_is_likely_eligible(self):
        result = evaluate_eligibility({"min_avg_annual_turnover_inr": 500_000},
                                      {"avg_annual_turnover_inr": 82_000_000})
        assert result.signal == "likely_eligible"

    def test_missing_the_threshold_is_likely_ineligible(self):
        result = evaluate_eligibility({"min_avg_annual_turnover_inr": 2_500_000_000},
                                      {"avg_annual_turnover_inr": 82_000_000})
        assert result.signal == "likely_ineligible"

    def test_an_mse_relaxation_is_surfaced_rather_than_silently_ignored(self):
        # A bidder who skips a tender they were actually relaxed into has lost it to a UI detail.
        result = evaluate_eligibility(
            {"min_avg_annual_turnover_inr": 2_500_000_000,
             "mse_turnover_relaxation": "Yes | Partial"},
            {"avg_annual_turnover_inr": 82_000_000},
        )
        assert result.signal == "likely_ineligible"
        assert "MSE turnover relaxation" in result.reason

    @pytest.mark.parametrize(
        ("fields", "profile"),
        [
            (None, None),
            ({}, {}),
            ({"min_avg_annual_turnover_inr": 500_000}, None),
        ],
    )
    def test_every_verdict_carries_a_reason(self, fields, profile):
        # C-AC9: a Depth-1 verdict with no deciding criterion is unexplainable and unactionable.
        result = evaluate_eligibility(fields, profile)
        assert isinstance(result, EligibilityResult)
        assert result.reason.strip()

    def test_a_pass_claims_only_what_it_compared(self):
        """The audit finding this pins: Depth-1 compares ONE criterion.

        Calling that "likely eligible" put a green pass on Adhesive Gum and vehicle spares for
        an IT services firm — true about the money, useless about the bid, and exactly the kind
        of overstatement this product refuses everywhere else. The verdict must name the bar it
        cleared and disclaim the ones it did not check.
        """
        result = evaluate_eligibility(
            {"min_avg_annual_turnover_inr": 500_000}, {"avg_annual_turnover_inr": 82_000_000}
        )
        assert result.signal == "likely_eligible"
        assert "turnover bar" in result.reason.lower()
        # It must NOT imply the bidder qualifies outright.
        assert "not yet checked" in result.reason.lower()

    def test_read_but_no_bar_is_worded_differently_from_not_read(self):
        # 56 live rows said "NEEDS THE NIT" about documents already parsed.
        not_read = evaluate_eligibility(None, {"avg_annual_turnover_inr": 1})
        no_bar = evaluate_eligibility(
            {"min_avg_annual_turnover_inr": None}, {"avg_annual_turnover_inr": 1}
        )
        assert not_read.signal == no_bar.signal == "unknown"
        assert not_read.reason != no_bar.reason
        assert "not read" in not_read.reason.lower()
        assert "states no minimum turnover" in no_bar.reason.lower()

    def test_eligibility_never_returns_an_exclusion(self):
        # Depth-1 ranks; it does not hide (C-FR9 / F-FR12). The signal vocabulary has no
        # 'excluded' member at all, and this pins that.
        for fields in ({"min_avg_annual_turnover_inr": 10**12}, {}, None):
            assert evaluate_eligibility(fields, {"avg_annual_turnover_inr": 1}).signal in {
                "likely_eligible", "likely_ineligible", "unknown",
            }


class TestKeywordRelevance:
    """The deterministic half of F-FR11. It ranks, and it is the fallback when the model is
    unavailable — so it must never need the model to be correct."""

    KW = ["cctv", "networking", "it services", "surveillance"]

    def test_a_category_code_hit_outranks_everything(self):
        # `home_info_netw` is GeM's own taxonomy saying this is networking. That is a
        # classification, not a coincidence of wording.
        m = keyword_relevance(record(title="Network switch supply",
                                     category_codes=["home_info_netw"]), self.KW)
        assert m.band == "high"
        assert "networking" in m.matched_terms

    def test_two_distinct_keywords_reach_high(self):
        m = keyword_relevance(record(title="CCTV Surveillance System AMC",
                                     category_codes=["services_home_cust"]), self.KW)
        assert m.band == "high"
        assert set(m.matched_terms) == {"cctv", "surveillance"}

    def test_an_unrelated_tender_bands_low_with_no_terms(self):
        for title in ("Adhesive Gum", "KRAZ TUBE INNER", "Modular Toilet"):
            m = keyword_relevance(record(title=title, category_codes=["home_univ_univ"]), self.KW)
            assert m.band == "low", title
            assert m.matched_terms == ()

    def test_inflection_is_tolerated_in_both_directions(self):
        # The vendor writes "networking"; GeM writes "Network". A plain substring test fails
        # this in exactly one direction, which looks like it works until someone checks.
        assert keyword_relevance(record(title="Network cabling"), ["networking"]).matched_terms
        assert keyword_relevance(record(title="Networking services"), ["network"]).matched_terms

    def test_a_short_word_is_not_a_stem_of_a_longer_one(self):
        # Found in production: "desktop" matched "desk" and banded a classroom Desk and Bench
        # Set as a top fit for an IT supplier.
        assert keyword_relevance(record(title="Desk and Bench Set for Classroom"),
                                 ["desktop"]).band == "low"
        # ...while the inflection case it exists for still works.
        assert keyword_relevance(record(title="Network switch"), ["networking"]).matched_terms

    def test_short_words_must_match_exactly(self):
        # Without the floor, "IT" matches item, kit, unit — a feed of confident nonsense.
        assert keyword_relevance(record(title="Item pack, kit and unit"), ["it"]).band == "low"
        assert keyword_relevance(record(title="IT hardware"), ["it"]).matched_terms == ("it",)

    def test_no_keywords_is_low_and_never_an_error(self):
        for kws in ([], None, ["", "   "]):
            m = keyword_relevance(record(), kws)
            assert m.band == "low" and m.matched_terms == ()

    def test_every_band_carries_its_evidence(self):
        # F-FR11: a band on its own is an opinion; a band with what matched is checkable.
        m = keyword_relevance(record(title="CCTV AMC", category_codes=["services_x"]), self.KW)
        assert "cctv" in m.reason.lower()
        assert keyword_relevance(record(title="Adhesive Gum"), self.KW).reason


class TestTheOptInKeywordGate:
    KW = ["cctv", "networking"]

    _DEFAULT = object()  # distinct sentinel: None is a VALUE under test here, not "unset"

    def rule(self, keywords=_DEFAULT):
        return Rule(name="Only my capability keywords", kind="keyword_match_required",
                    spec={"keywords": self.KW if keywords is self._DEFAULT else keywords})

    def test_it_excludes_a_non_matching_tender_and_names_itself(self):
        result = evaluate_gate(record(title="Adhesive Gum"), [self.rule()], now=NOW)
        assert result.in_scope is False
        assert result.excluded_by_rule == "Only my capability keywords"

    def test_it_keeps_a_matching_tender(self):
        result = evaluate_gate(
            record(title="CCTV AMC", category_codes=["services_home_cust"]), [self.rule()], now=NOW
        )
        assert result.in_scope is True

    def test_an_empty_keyword_list_hides_NOTHING(self):
        # The trap this guards: a vendor switches the narrow feed on before filling in their
        # profile and every single tender vanishes, under a rule whose name explains nothing.
        for empty in ([], None):
            assert evaluate_gate(record(title="Adhesive Gum"),
                                 [self.rule(empty)], now=NOW).in_scope is True

    def test_the_gate_is_opt_in_and_absent_by_default(self):
        # No rule -> nothing hidden, whatever the keywords would have said.
        assert evaluate_gate(record(title="Adhesive Gum"), [], now=NOW).in_scope is True


class TestAModelBandCanNeverHideATender:
    """F-AC6 / G-9 at the unit level, and the reason the two layers are kept apart.

    A model may rank and summarise. It may never decide what a human never sees. The gate takes
    a record and RULES; a relevance band is neither, so no band on the record can reach it.
    """

    @pytest.mark.parametrize("band", ["high", "medium", "low", None, "garbage"])
    def test_a_band_on_the_record_does_not_change_the_gate(self, band):
        rules = [Rule(name="7+ days", kind="min_days_to_close", spec={"days": 1})]
        plain = evaluate_gate(record(), rules, now=NOW)
        with_band = evaluate_gate(
            record(relevance_band=band, relevance_reason="model says so"), rules, now=NOW
        )
        assert with_band.in_scope == plain.in_scope is True
        assert with_band.excluded_by_rule == plain.excluded_by_rule is None

    def test_no_rule_kind_reads_a_model_field(self):
        # If someone adds a rule kind that gates on a model band, this fails: the gate would
        # start returning different answers for records that differ only in model output.
        for kind in sorted(RULE_KINDS):
            rule = Rule(name=kind, kind=kind, spec={"keywords": ["zzz"], "days": 0,
                                                    "prefixes": ["zzz"], "needles": ["zzz"]})
            low = evaluate_gate(record(relevance_band="low"), [rule], now=NOW)
            high = evaluate_gate(record(relevance_band="high"), [rule], now=NOW)
            assert low.in_scope == high.in_scope, f"{kind} reads the model band"


class TestAFallbackBandIsNeverCached:
    """A keyword band is what we could say while the model was unavailable, not a final answer.

    Storing the input hash on it made a single transient model failure freeze that row on a
    crude keyword band FOREVER: every later run saw an unchanged hash and skipped it. The bug is
    invisible — the row keeps a plausible band and simply never improves.
    """

    def test_a_keyword_fallback_stores_no_hash(self):
        from app.discovery.relevance import bands_for

        patches = bands_for(
            [{"id": "a", "title": "CCTV AMC", "category_codes": ["services_x"]}],
            capability_statement=None,  # forces the deterministic path
            keywords=["cctv"],
        )
        assert patches["a"]["relevance_source"] == "keyword"
        assert patches["a"]["relevance_input_hash"] is None

    def test_no_internal_key_reaches_the_database_payload(self):
        from app.discovery.relevance import bands_for

        patches = bands_for(
            [{"id": "a", "title": "X", "category_codes": []}],
            capability_statement=None,
            keywords=["cctv"],
        )
        assert all(not k.startswith("_") for k in patches["a"])


class TestOurExplanationsFollowTheMarketLanguage:
    """The rationale is OUR commentary, so it is written in the workspace's market language.

    Load-bearing because it is stored once per (workspace, opportunity): a French workspace
    cannot be served English explanations by simply toggling the chrome, so if these come back
    in English the row is wrong in the database, not just on screen.
    """

    def test_keyword_reasons_translate(self):
        record = {"title": "Assistance à maîtrise d'ouvrage", "category_codes": [], "authority": ""}
        fr = keyword_relevance(record, ["assistance"], "fr")
        assert fr.reason.startswith("Correspond à votre mot-clé")
        assert keyword_relevance(record, ["plomberie"], "fr").reason.startswith("Aucun")
        # English stays the default for every caller that does not ask.
        assert keyword_relevance(record, ["assistance"]).reason.startswith("Matched your keyword")

    def test_eligibility_reasons_translate(self):
        assert evaluate_eligibility(None, {}, "fr").reason == "Avis de marché pas encore lu"
        below = evaluate_eligibility(
            {"min_avg_annual_turnover_inr": 50_000_000},
            {"avg_annual_turnover_inr": 10_000_000},
            "fr",
        )
        assert below.signal == "likely_ineligible"
        assert "Exige un chiffre d'affaires" in below.reason

    def test_an_unknown_language_falls_back_to_english_rather_than_raising(self):
        # A 500 on the feed would be a worse failure than an untranslated sentence.
        assert evaluate_eligibility(None, {}, "xx").reason == "Bid document not read yet"


class TestTheCapabilityGateFollowsTheProfile:
    """The opt-in narrow feed filters on a SNAPSHOT of the keywords taken when it was switched
    on, and nothing refreshed it.

    Reported from production: a workspace entered two prose "keywords", switched the gate on,
    and all 335 swept tenders were excluded. The repair — fix the keywords — changed the
    relevance ranking and left the RULE filtering on the original terms, so the feed stayed
    empty and nothing on screen explained why. Two copies of one value, and the stale one
    decided what the user saw.
    """

    RULE = {"id": "r1", "name": "Only my capability keywords",
            "kind": "keyword_match_required", "enabled": True,
            "spec": {"keywords": ["an old phrase nobody would ever match"]}}

    def test_the_stored_spec_is_refreshed_from_the_profile(self, monkeypatch):
        from app.discovery import ingest

        written: list = []
        monkeypatch.setattr(ingest.db, "get_discovery_rules", lambda w: [dict(self.RULE)])
        monkeypatch.setattr(ingest.db, "update_discovery_rule",
                            lambda rid, w, patch: written.append((rid, patch)))

        rules = ingest._rules_for("w1", ["wire rope", "crane"])
        assert rules[0].spec["keywords"] == ["wire rope", "crane"]
        # And persisted, so the Excluded bucket keeps describing what actually happened.
        assert written == [("r1", {"spec": {"keywords": ["wire rope", "crane"]}})]

    def test_an_unchanged_spec_is_not_rewritten(self, monkeypatch):
        from app.discovery import ingest

        written: list = []
        rule = dict(self.RULE, spec={"keywords": ["crane"]})
        monkeypatch.setattr(ingest.db, "get_discovery_rules", lambda w: [rule])
        monkeypatch.setattr(ingest.db, "update_discovery_rule",
                            lambda rid, w, patch: written.append(rid))
        ingest._rules_for("w1", ["crane"])
        assert written == [], "a no-op refresh must not write on every recompute"

    def test_other_rules_are_never_touched(self, monkeypatch):
        from app.discovery import ingest

        other = {"id": "r2", "name": "No defence tenders", "kind": "authority_excludes",
                 "enabled": True, "spec": {"contains": "defence"}}
        monkeypatch.setattr(ingest.db, "get_discovery_rules", lambda w: [dict(other)])
        monkeypatch.setattr(ingest.db, "update_discovery_rule",
                            lambda *a, **k: pytest.fail("a user's own rule was rewritten"))
        rules = ingest._rules_for("w1", ["crane"])
        assert rules[0].spec == {"contains": "defence"}

    def test_no_keywords_argument_leaves_every_rule_alone(self, monkeypatch):
        """Callers that do not know the profile must not blank the gate."""
        from app.discovery import ingest

        monkeypatch.setattr(ingest.db, "get_discovery_rules", lambda w: [dict(self.RULE)])
        monkeypatch.setattr(ingest.db, "update_discovery_rule",
                            lambda *a, **k: pytest.fail("rewrote the spec with no profile read"))
        rules = ingest._rules_for("w1")
        assert rules[0].spec["keywords"] == ["an old phrase nobody would ever match"]
