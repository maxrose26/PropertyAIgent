"""Buyer Profiles V1 - tests for app.policy.buyer_profiles / app.policy.
buyer_matching / app.reporting.opportunity_feed's buyer-aware selection.

Follows this codebase's own established convention: unit-test the pure
matching logic against real-shaped fixtures (Focus School's and Elton
Reservoir's own real figures, hand-built here exactly as the Buyer
Profiles V1 investigation report recorded them), never a Streamlit page
script, never an LLM.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import Application, LocalPlan, LocalPlanSite, Site, SchemeIntelligence
from app.policy.buyer_profiles import (
    AFFORDABLE_UNITS,
    BUYER_PROFILES,
    BUYER_PROFILE_ORDER,
    HOUSING_ASSOCIATION,
    NATIONAL_HOUSEBUILDER,
    NESTEN_HOMES,
    STRATEGIC_LAND_BUYER,
    TOTAL_UNITS,
)
from app.policy.buyer_matching import (
    INSUFFICIENT_EVIDENCE,
    NOT_SUITABLE,
    STRONG_FIT,
    MatchingFacts,
    PLANNING_DELIVERY,
    STRATEGIC_LAND,
    assess_buyer_fit,
    build_planning_delivery_matching_facts,
    build_strategic_land_matching_facts,
)
from app.reporting.allocation_development_coverage import build_allocation_development_coverage
from app.reporting.opportunity_feed import build_opportunity_feed


# --- Zero-LLM safety ----------------------------------------------------------

def test_matching_modules_make_no_llm_or_network_calls():
    """Structural safety check (task Section: "no LLM in the matching
    path"): the two new modules' own source imports nothing from
    app.ai/app.extraction's LLM-calling code, nor any HTTP client -
    matching is pure, deterministic Python over already-extracted
    evidence, full stop."""
    import ast
    import inspect

    import app.policy.buyer_matching as buyer_matching
    import app.policy.buyer_profiles as buyer_profiles

    forbidden_substrings = ("openai", "anthropic", "requests", "httpx", "urllib", "app.ai")
    for module in (buyer_matching, buyer_profiles):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        imported_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.append(node.module)
        for name in imported_names:
            lowered = name.lower()
            assert not any(f in lowered for f in forbidden_substrings), f"{module.__name__} imports {name!r}"


# --- Buyer profile configuration ---------------------------------------------

def test_exactly_four_pilot_profiles_with_correct_ranges_and_appetite():
    assert set(BUYER_PROFILES) == {"nesten_homes", "strategic_land_buyer", "national_housebuilder", "housing_association"}
    assert len(BUYER_PROFILE_ORDER) == 4

    assert (NESTEN_HOMES.target_unit_min, NESTEN_HOMES.target_unit_max) == (50, 100)
    assert (STRATEGIC_LAND_BUYER.target_unit_min, STRATEGIC_LAND_BUYER.target_unit_max) == (100, 300)
    assert (NATIONAL_HOUSEBUILDER.target_unit_min, NATIONAL_HOUSEBUILDER.target_unit_max) == (200, 500)
    assert (HOUSING_ASSOCIATION.target_unit_min, HOUSING_ASSOCIATION.target_unit_max) == (50, 300)

    assert "permission_granted" in NESTEN_HOMES.accepted_planning_states
    assert "adopted_allocation" in NESTEN_HOMES.accepted_planning_states
    # Strategic Land Buyer's own brief: "Planning permission is NOT required" -
    # confirmed here as genuinely absent from its accepted states, not merely untested.
    assert "permission_granted" not in STRATEGIC_LAND_BUYER.accepted_planning_states
    assert "adopted_allocation" in STRATEGIC_LAND_BUYER.accepted_planning_states
    assert "emerging_allocation" in STRATEGIC_LAND_BUYER.accepted_planning_states
    assert "permission_granted" in NATIONAL_HOUSEBUILDER.accepted_planning_states
    assert "adopted_allocation" in NATIONAL_HOUSEBUILDER.accepted_planning_states
    assert "emerging_allocation" in NATIONAL_HOUSEBUILDER.accepted_planning_states

    assert STRATEGIC_LAND_BUYER.treats_no_activity_as_positive is True
    assert NESTEN_HOMES.treats_no_activity_as_positive is False
    assert NATIONAL_HOUSEBUILDER.treats_no_activity_as_positive is False
    assert HOUSING_ASSOCIATION.treats_no_activity_as_positive is False
    assert STRATEGIC_LAND_BUYER.large_allocation_is_self_qualifying is True
    assert NESTEN_HOMES.large_allocation_is_self_qualifying is False
    assert NATIONAL_HOUSEBUILDER.large_allocation_is_self_qualifying is False
    assert HOUSING_ASSOCIATION.large_allocation_is_self_qualifying is False


def test_scale_metric_configuration():
    """The generic scale-metric concept (Housing Association amendment):
    every housebuilder profile is measured against TOTAL_UNITS (unchanged),
    only Housing Association against AFFORDABLE_UNITS."""
    for profile in (NESTEN_HOMES, STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER):
        assert profile.scale_metric == TOTAL_UNITS
    assert HOUSING_ASSOCIATION.scale_metric == AFFORDABLE_UNITS


def test_housing_association_reverses_the_housebuilder_exclusion_polarity():
    """Housing Association amendment: the three profile-level flags this
    amendment introduces must have exactly the opposite polarity from every
    housebuilder profile - not merely "unset", a deliberate reversal."""
    for profile in (NESTEN_HOMES, STRATEGIC_LAND_BUYER, NATIONAL_HOUSEBUILDER):
        assert profile.specialist_development_is_exclusion is True
        assert profile.wholly_affordable_is_exclusion is True
        assert profile.below_minimum_scale_is_exclusion is False
    assert HOUSING_ASSOCIATION.specialist_development_is_exclusion is False
    assert HOUSING_ASSOCIATION.wholly_affordable_is_exclusion is False
    assert HOUSING_ASSOCIATION.below_minimum_scale_is_exclusion is True


# --- Core matching rules, against synthetic MatchingFacts (no DB needed) ----

def _facts(**overrides) -> MatchingFacts:
    base = dict(
        opportunity_type=PLANNING_DELIVERY, unit_count=75, development_type_raw="houses",
        is_specialist_development=False, affordable_percentage=30.0, affordable_percentage_trusted=True,
        affordable_unit_count=None, planning_state="permission_granted", has_identified_planning_activity=True,
        has_phasing_evidence=False, matched_to_site=True,
    )
    base.update(overrides)
    return MatchingFacts(**base)


def test_in_range_positive_match():
    result = assess_buyer_fit(NESTEN_HOMES, _facts(unit_count=82))
    assert result.classification == STRONG_FIT
    assert any("82" in m for m in result.matches)


def test_development_type_exclusion():
    result = assess_buyer_fit(NESTEN_HOMES, _facts(is_specialist_development=True, development_type_raw="retirement_living"))
    assert result.classification == NOT_SUITABLE
    assert any("specialist" in r for r in result.does_not_match)


def test_wholly_affordable_exclusion():
    result = assess_buyer_fit(NESTEN_HOMES, _facts(affordable_percentage=100.0))
    assert result.classification == NOT_SUITABLE
    assert any("100%" in r for r in result.does_not_match)


def test_normal_mixed_affordable_scheme_is_not_excluded():
    # Policy-compliant affordable housing (e.g. 30%) inside an otherwise
    # open-market scheme must never itself be treated as a disqualifier -
    # the brief's own explicit instruction.
    result = assess_buyer_fit(NESTEN_HOMES, _facts(affordable_percentage=30.0, unit_count=80))
    assert result.classification == STRONG_FIT
    assert not result.does_not_match


def test_missing_affordable_evidence_never_becomes_zero_percent():
    result = assess_buyer_fit(NESTEN_HOMES, _facts(affordable_percentage=None, affordable_percentage_trusted=False, unit_count=80))
    assert result.classification != NOT_SUITABLE  # never excluded on an assumed 0%
    assert any("not assumed to be 0%" in u for u in result.unknown)


def test_missing_phasing_does_not_become_phaseable():
    # An oversized opportunity with NO phasing evidence must never read as
    # "a suitable phase exists" - it must stay an open question.
    result = assess_buyer_fit(NESTEN_HOMES, _facts(unit_count=3500, has_phasing_evidence=False, opportunity_type=STRATEGIC_LAND))
    assert result.classification != STRONG_FIT
    assert not any("phase" in m.lower() and "exists" in m.lower() for m in result.matches)
    assert result.is_investigative_exception is True


def test_oversized_allocation_does_not_automatically_become_not_suitable():
    result = assess_buyer_fit(NESTEN_HOMES, _facts(unit_count=3500, opportunity_type=STRATEGIC_LAND, planning_state="adopted_allocation"))
    assert result.classification != NOT_SUITABLE
    assert result.classification == INSUFFICIENT_EVIDENCE
    assert result.is_investigative_exception is True


def test_insufficient_parcel_evidence_preserves_uncertainty_not_certainty():
    result = assess_buyer_fit(NESTEN_HOMES, _facts(unit_count=3500, opportunity_type=STRATEGIC_LAND, has_phasing_evidence=False))
    assert any("no phasing/parcel evidence exists" in u for u in result.unknown)


def test_different_profiles_produce_different_conclusions_from_the_same_opportunity():
    facts = _facts(unit_count=3500, opportunity_type=STRATEGIC_LAND, planning_state="adopted_allocation", has_identified_planning_activity=False)
    nesten = assess_buyer_fit(NESTEN_HOMES, facts)
    strategic = assess_buyer_fit(STRATEGIC_LAND_BUYER, facts)
    national = assess_buyer_fit(NATIONAL_HOUSEBUILDER, facts)
    # Strategic Land Buyer's own risk appetite genuinely changes the
    # substance of the reasoning, even when the top-level classification
    # coincides with the other two - never claim identical reasoning.
    assert strategic.matches != nesten.matches
    assert strategic.matches != national.matches
    assert len(strategic.matches) > len(nesten.matches)


# --- Required acceptance case: Focus School (real figures) ------------------

def test_focus_school_is_not_a_strong_nesten_fit(session):
    """Real Focus School figures (see the Buyer Profiles V1 investigation
    report): 82 total units, granted permission, development_type
    'mixed_retirement_and_market_housing', 100% affordable, applicant
    Anwyl Partnerships. Nesten must not classify this as a strong fit -
    the reasoning must name the trusted disqualifying evidence."""
    site = Site(council_code="stockport", canonical_address="focus school", display_address="Focus School 237 Didsbury Road")
    session.add(site)
    session.flush()
    app = Application(council_code="stockport", reference="DC/085997", site_id=site.id, status="Decided", decision="Granted")
    session.add(app)
    session.flush()
    si = SchemeIntelligence(
        application_id=app.id, total_units_final=82, affordable_units_final=72, affordable_percentage_final=100.0,
        affordable_missing=False, development_type="mixed_retirement_and_market_housing",
        applicant_company="Anwyl Partnerships", core_intelligence_complete=True,
    )
    session.add(si)
    session.commit()

    facts = build_planning_delivery_matching_facts(si)
    result = assess_buyer_fit(NESTEN_HOMES, facts)

    assert result.classification == NOT_SUITABLE
    assert any("specialist" in r for r in result.does_not_match)
    assert any("100%" in r for r in result.does_not_match)
    # Must not fabricate ownership/control certainty from the applicant's
    # name alone (the brief's own explicit instruction) - no reason
    # anywhere in this assessment claims Anwyl proves ownership/control.
    assert not any("Anwyl" in r and ("owner" in r.lower() or "control" in r.lower()) for r in (result.matches + result.does_not_match))


def test_focus_school_with_missing_scheme_intelligence_reads_as_unknown_not_excluded():
    """If SchemeIntelligence had never been extracted at all, the result
    must be INSUFFICIENT_EVIDENCE, never a confident STRONG_FIT or
    NOT_SUITABLE fabricated from nothing."""
    facts = build_planning_delivery_matching_facts(None)
    result = assess_buyer_fit(NESTEN_HOMES, facts)
    assert result.classification == INSUFFICIENT_EVIDENCE


# --- Required acceptance case (Housing Association amendment, Section 13):
#     same site, opposite buyer effect ------------------------------------

def _focus_school_scheme_intelligence(session) -> SchemeIntelligence:
    """Real Focus School figures - see test_focus_school_is_not_a_strong_
    nesten_fit's own docstring and this amendment's live production check
    (72 affordable of 82 total, 100% affordable, mixed_retirement_and_
    market_housing, applicant Anwyl Partnerships)."""
    site = Site(council_code="stockport", canonical_address="focus school ha", display_address="Focus School 237 Didsbury Road")
    session.add(site)
    session.flush()
    app = Application(council_code="stockport", reference="DC/085997-HA", site_id=site.id, status="Decided", decision="Granted")
    session.add(app)
    session.flush()
    si = SchemeIntelligence(
        application_id=app.id, total_units_final=82, affordable_units_final=72, affordable_percentage_final=100.0,
        affordable_missing=False, development_type="mixed_retirement_and_market_housing",
        applicant_company="Anwyl Partnerships", core_intelligence_complete=True,
    )
    session.add(si)
    session.commit()
    return si


def test_focus_school_same_evidence_opposite_buyer_effect(session):
    """Required acceptance case (Housing Association amendment, Section 13):
    the SAME trusted evidence (Focus School) must be a hard negative for
    Nesten Homes but NOT a negative for Housing Association - proving
    buyer-fit is genuinely buyer-relative, not a universal opportunity
    quality judgement."""
    si = _focus_school_scheme_intelligence(session)
    facts = build_planning_delivery_matching_facts(si)

    nesten = assess_buyer_fit(NESTEN_HOMES, facts)
    housing_association = assess_buyer_fit(HOUSING_ASSOCIATION, facts)

    # Nesten: 100% affordable remains a hard exclusion (unchanged).
    assert nesten.classification == NOT_SUITABLE
    assert any("100%" in r for r in nesten.does_not_match)

    # Housing Association: 100% affordable is NOT a negative - it is
    # explicit positive evidence instead.
    assert not any("100%" in r for r in housing_association.does_not_match)
    assert any("100%" in r and "affordable-housing focus" in r for r in housing_association.matches)

    # Its scale is assessed against the 72 AFFORDABLE homes (not the 82
    # total) - within the 50-300 affordable-home target range.
    assert any("72" in r and "affordable homes" in r for r in housing_association.matches)

    # An unresolved criterion (the buyer's own specialist/retirement
    # appetite was never specified) correctly prevents STRONG_FIT without
    # inventing a hard exclusion the brief never asked for.
    assert housing_association.classification == INSUFFICIENT_EVIDENCE
    assert any("specialist" in u and "not been specified" in u for u in housing_association.unknown)
    assert not any("specialist" in r for r in housing_association.does_not_match)


def test_focus_school_housing_association_does_not_fabricate_ownership(session):
    """Same non-fabrication requirement as the Nesten acceptance case -
    Anwyl's applicant role must never be read as ownership/control proof,
    for any buyer, including Housing Association."""
    si = _focus_school_scheme_intelligence(session)
    facts = build_planning_delivery_matching_facts(si)
    result = assess_buyer_fit(HOUSING_ASSOCIATION, facts)
    all_reasons = result.matches + result.does_not_match + result.unknown + result.investigate
    assert not any("Anwyl" in r for r in all_reasons)
    assert not any("owner" in r.lower() or "control" in r.lower() for r in all_reasons)


# --- Required acceptance case (Housing Association amendment, Section 14):
#     affordable component within range despite a large total scheme -----

def test_affordable_component_in_range_despite_total_exceeding_housing_association_max():
    """400 total homes / 120 affordable homes: Housing Association must
    NOT be rejected because the TOTAL (400) exceeds its 300-unit maximum -
    120 affordable homes is the relevant scale, and sits within its 50-300
    target. Existing housebuilder profiles continue to assess the SAME
    opportunity using their own total-unit requirements, from the exact
    same underlying facts."""
    facts = _facts(
        unit_count=400, affordable_unit_count=120, affordable_percentage=30.0, affordable_percentage_trusted=True,
        development_type_raw="mixed_apartments_and_houses",
    )
    housing_association = assess_buyer_fit(HOUSING_ASSOCIATION, facts)
    assert housing_association.classification != NOT_SUITABLE
    assert any("120" in m and "affordable homes" in m for m in housing_association.matches)
    assert not any("400" in u or "exceeds" in u for u in housing_association.unknown)

    # National Housebuilder (200-500 total): 400 total homes matches its
    # own range directly - a different metric, same underlying facts.
    national = assess_buyer_fit(NATIONAL_HOUSEBUILDER, facts)
    assert any("400" in m and "homes" in m for m in national.matches)

    # Nesten (50-100 total): 400 total homes is oversized on ITS OWN metric
    # - correctly investigated, never silently matched.
    nesten = assess_buyer_fit(NESTEN_HOMES, facts)
    assert nesten.is_investigative_exception is True
    assert nesten.classification != STRONG_FIT


# --- Required acceptance case (Housing Association amendment, Section 15):
#     below the affordable-unit minimum -------------------------------------

def test_below_affordable_minimum_is_not_suitable_for_housing_association():
    """80 total homes / 20 affordable homes: Housing Association's own
    brief states this is NOT SUITABLE (fewer than 50 affordable homes) -
    unlike the housebuilder profiles' own "below minimum" handling, this is
    a genuine hard exclusion for this buyer, with a reason naming both the
    evidenced figure and the stated minimum."""
    facts = _facts(unit_count=80, affordable_unit_count=20, development_type_raw="houses")
    result = assess_buyer_fit(HOUSING_ASSOCIATION, facts)
    assert result.classification == NOT_SUITABLE
    assert any("20" in r and "50" in r for r in result.does_not_match)


# --- Required acceptance case (Housing Association amendment, Section 16):
#     missing affordable evidence never becomes zero ------------------------

def test_missing_affordable_evidence_is_insufficient_not_not_suitable_for_housing_association():
    """Total units known, affordable-unit provision genuinely unknown -
    Housing Association must return INSUFFICIENT_EVIDENCE, never
    NOT_SUITABLE, and must never assume 0 affordable homes."""
    facts = _facts(
        unit_count=150, affordable_unit_count=None, affordable_percentage=None, affordable_percentage_trusted=False,
        development_type_raw="houses",
    )
    result = assess_buyer_fit(HOUSING_ASSOCIATION, facts)
    assert result.classification == INSUFFICIENT_EVIDENCE
    assert any("affordable-unit count is available" in u for u in result.unknown)


# --- Non-residential (employment) allocations stay excluded for every
#     buyer, including Housing Association --------------------------------

def test_employment_allocation_excluded_for_housing_association_too():
    """A genuinely non-residential (employment) Local Plan allocation is a
    universal exclusion for every pilot profile - Housing Association's own
    relaxed specialist-development handling (Section 8) is about an
    UNSTATED specialist-residential-product appetite, never about accepting
    non-residential land."""
    facts = _facts(
        opportunity_type=STRATEGIC_LAND, is_specialist_development=True, development_type_raw="employment",
        affordable_unit_count=None, affordable_percentage=None, affordable_percentage_trusted=False,
    )
    result = assess_buyer_fit(HOUSING_ASSOCIATION, facts)
    assert result.classification == NOT_SUITABLE
    assert any("employment" in r for r in result.does_not_match)


# --- Housing Association appears in and uses the same widened-pool
#     personalisation architecture as every other pilot buyer -------------

def test_housing_association_uses_the_shared_buyer_feed_architecture(session):
    """Not a separate Housing Association dashboard/pipeline - the same
    build_opportunity_feed(buyer_key=...) entry point every other pilot
    buyer already uses."""
    feed = build_opportunity_feed(session, limit=6, buyer_key="housing_association")
    assert feed["buyer_key"] == "housing_association"
    assert "excluded_not_suitable" in feed["counts"]


# --- Required acceptance case: Elton Reservoir (real shape) ------------------

def _make_elton_like_allocation(session) -> LocalPlanSite:
    plan = LocalPlan(council_code="bury", plan_name="Places for Everyone Joint Development Plan (Bury allocations)", status="adopted", raw_status="adopted")
    session.add(plan)
    session.commit()
    alloc = LocalPlanSite(
        council_code="bury", local_plan_id=plan.id, policy_reference="JPA 7", site_name="Elton Reservoir",
        plan_name=plan.plan_name, plan_status="adopted", intended_use="residential", minimum_dwellings=3500,
        allocation_status="adopted_allocation", matched_site_id=None,
    )
    session.add(alloc)
    session.commit()
    return alloc


def test_elton_reservoir_produces_materially_different_conclusions_per_buyer(session):
    alloc = _make_elton_like_allocation(session)
    result = build_allocation_development_coverage(session, [alloc])[alloc.id]
    facts = build_strategic_land_matching_facts(alloc, result["coverage"], result["phasing"])

    assert facts.unit_count == 3500
    assert facts.has_phasing_evidence is False
    assert facts.matched_to_site is False

    nesten = assess_buyer_fit(NESTEN_HOMES, facts)
    strategic = assess_buyer_fit(STRATEGIC_LAND_BUYER, facts)
    national = assess_buyer_fit(NATIONAL_HOUSEBUILDER, facts)
    housing_association = assess_buyer_fit(HOUSING_ASSOCIATION, facts)

    # None is a hard mismatch - the allocation itself is genuinely
    # residential and adopted, matching every profile's planning appetite.
    assert nesten.classification == INSUFFICIENT_EVIDENCE and nesten.is_investigative_exception
    assert strategic.classification == INSUFFICIENT_EVIDENCE and strategic.is_investigative_exception
    assert national.classification == INSUFFICIENT_EVIDENCE and national.is_investigative_exception

    # Housing Association (Section 10): no scheme-specific affordable-unit
    # evidence exists at all for a Local Plan allocation - correctly
    # INSUFFICIENT_EVIDENCE, never a fabricated affordable-unit estimate
    # from Local Plan/NPPF policy percentages applied to allocation
    # capacity. Not flagged as an "investigative exception" - that flag is
    # specific to the oversized-scale branch, which this buyer's own scale
    # metric (affordable units) never reaches here.
    assert housing_association.classification == INSUFFICIENT_EVIDENCE
    assert any("affordable-unit count is available" in u for u in housing_association.unknown)

    # Nesten: allocation matches, scale materially exceeds target, no
    # parcel evidence -> investigation required (never claimed to fit).
    assert any("materially exceeds" in u for u in nesten.unknown)
    assert not any("meaningful strategic-land position" in m for m in nesten.matches)

    # Strategic Land Buyer: the same evidence reads as materially more
    # relevant - no-activity framed positively, and the allocation's own
    # scale is itself a match, not an open question.
    assert any("meaningful strategic-land position" in m for m in strategic.matches)
    assert any("early-stage position" in m for m in strategic.matches)
    assert not any("materially exceeds" in u for u in strategic.unknown)

    # National Housebuilder: same shape as Nesten (no self-qualifying-scale
    # appetite for this profile) but against its own different range.
    assert any("materially exceeds" in u for u in national.unknown)
    assert not any("meaningful strategic-land position" in m for m in national.matches)

    # Ownership/control is a structural gap - present for every buyer,
    # never invented as known for any of them.
    for assessment in (nesten, strategic, national):
        assert any("Ownership/control has not been established" in u for u in assessment.unknown)


# --- Generic mode is unaffected ----------------------------------------------

def test_generic_mode_feed_unchanged_by_buyer_profiles_v1(session):
    feed = build_opportunity_feed(session, limit=6)
    assert feed["buyer_key"] is None
    assert "excluded_not_suitable" not in feed["counts"]
    for card in feed["cards"]:
        assert card.get("buyer_fit") is None


# --- Candidate-pool personalisation (not a re-filter of the generic six) ---

def test_buyer_mode_selects_from_a_larger_pool_than_the_generic_feed(session):
    """Proves personalisation happens before final truncation (the brief's
    own "Critical Feed Requirement", opportunity_feed.py's own
    _buyer_selection docstring): build 3 small, in-range, general-needs
    planning/delivery candidates ("Nesten Fit Site N") shaped to be a
    Nesten STRONG_FIT, but make them the LEAST urgent lapse cards in the
    dataset by adding 10 noise sites that are all more urgent (lower
    days-left) and carry no SchemeIntelligence at all (so they read as
    INSUFFICIENT_EVIDENCE for Nesten, never crowding out a genuine strong
    fit). Generic mode's own candidate query is bounded to exactly `limit`
    (see build_opportunity_feed's own pool_limit rule), so with limit=6 and
    10 more-urgent noise cards ahead of them in that query's own sort
    order, the 3 Nesten-fit sites are never even fetched into the generic
    pool - proving any Nesten-mode appearance came from the widened pool,
    not a re-filter of the generic six."""
    today = dt.date.today()

    def _make_lapse_site(label: str, days_left: int) -> Site:
        decision_date = today - dt.timedelta(days=3 * 365 - days_left)
        site = Site(council_code="testcouncil", canonical_address=f"{label}-addr", display_address=label)
        session.add(site)
        session.flush()
        session.add(Application(
            council_code="testcouncil", reference=f"REF-{label}", site_id=site.id, status="Decided", decision="Granted",
            proposal="Full planning application for the erection of residential dwellings.",
            decision_issued_date=decision_date.strftime("%a %d %b %Y"), first_seen_at=dt.datetime.now(dt.timezone.utc),
        ))
        session.flush()
        return site

    for i in range(10):
        _make_lapse_site(f"Noise Site {i}", days_left=5 + i)  # more urgent than every Nesten-fit site below

    nesten_fit_sites = []
    for i in range(3):
        site = _make_lapse_site(f"Nesten Fit Site {i}", days_left=170)  # least urgent - last in the sorted pool
        app = session.execute(select(Application).where(Application.site_id == site.id)).scalars().first()
        session.add(SchemeIntelligence(
            application_id=app.id, total_units_final=70 + i, development_type="houses",
            affordable_percentage_final=25.0, affordable_missing=False, core_intelligence_complete=True,
        ))
        nesten_fit_sites.append(site)
    session.commit()

    generic_feed = build_opportunity_feed(session, limit=6)
    generic_titles = {c["title"] for c in generic_feed["cards"]}
    assert not ({s.display_address for s in nesten_fit_sites} & generic_titles)  # confirms the pool truly excluded them

    nesten_feed = build_opportunity_feed(session, limit=6, buyer_key="nesten_homes")
    nesten_strong_fits = [c for c in nesten_feed["cards"] if c.get("buyer_fit") and c["buyer_fit"].classification == STRONG_FIT]
    assert len(nesten_strong_fits) >= 1
    # At least one of these must be a candidate the generic feed's own
    # top-6 never included - proving the selection happened over the
    # wider pool, not a filter of the already-truncated generic output.
    assert any(c["title"] not in generic_titles for c in nesten_strong_fits)
