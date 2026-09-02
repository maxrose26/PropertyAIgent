"""LPDI V1 Gate 1 ("Greater Manchester Document Discovery Closure") - this
gate made NO code changes to app.policy.sources, app.policy.report_discovery,
app.policy.document_selection, app.extraction.plan_evidence, or any database
model. The only new artefact is config/policy_sources.yaml registration for
8 previously-unregistered/under-registered councils (bolton, manchester,
oldham, rochdale, tameside, wigan - new; bury, salford, trafford - extended
with a monitoring_page/amr_page source they previously lacked).

These tests lock the two things genuinely at risk from a pure config change:

1. Every new/extended council's source entries parse and register correctly
   through the EXISTING app.policy.sources architecture (idempotent, no
   disturbance to any pre-existing council's rows), against the `session`
   fixture (an isolated in-memory test database - never production, same
   discipline as tests/test_salford_trafford_reg19_sources.py's own
   established precedent for this exact scenario).
2. The real link text/URL patterns actually found on each council's real
   monitoring page (captured verbatim during live verification, not
   invented) are classified correctly by the EXISTING, unmodified
   app.policy.report_discovery.classify_report_type - proving the existing
   discovery/classification architecture is fundamentally capable, never
   requiring the "new document type" or "new classification rule" escape
   hatches this gate's own task explicitly gates behind a STOP condition.

No schema change, no new ingestion module, no new document-type vocabulary,
no OpenAI/web-search code was introduced - see this gate's own specification
for the full architecture audit."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db.models import LocalPlan, MonitoredSource
from app.policy.document_selection import DOCUMENT_TYPE_TO_CATEGORIES
from app.policy.report_discovery import classify_report_type
from app.policy.sources import load_source_config, register_sources_for_council

REAL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "policy_sources.yaml"

NEW_OR_EXTENDED_COUNCILS = ["bolton", "manchester", "oldham", "rochdale", "tameside", "wigan"]
PREVIOUSLY_EXISTING_COUNCILS = ["stockport", "bury", "salford", "trafford"]


def _real_config() -> dict:
    return load_source_config(REAL_CONFIG_PATH)


def _make_local_plan(session, council_code: str, plan_name: str, plan_version: str | None) -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name=plan_name, plan_version=plan_version, status="unknown", raw_status="unknown")
    session.add(plan)
    session.commit()
    return plan


# --- A/B. Config shape for every new/extended council -------------------------


def test_every_new_or_extended_council_has_at_least_one_monitoring_source():
    config = _real_config()
    for code in NEW_OR_EXTENDED_COUNCILS:
        sources = config["councils"][code]["sources"]
        assert sources, f"{code} has no sources registered"
        monitoring_types = {"monitoring_page", "amr_page", "housing_land_supply_page", "authority_monitoring_report", "housing_land_supply_statement"}
        assert any(s["source_type"] in monitoring_types for s in sources), f"{code} has no monitoring-shaped source"


def test_bury_salford_trafford_gained_exactly_one_new_monitoring_source_each():
    config = _real_config()
    # Pre-existing counts from tests/test_salford_trafford_reg19_sources.py's
    # own established baseline (stockport=2, bury=3, salford=2, trafford=2) -
    # each of bury/salford/trafford must have grown by exactly one.
    assert len(config["councils"]["bury"]["sources"]) == 4
    assert len(config["councils"]["salford"]["sources"]) == 3
    assert len(config["councils"]["trafford"]["sources"]) == 3
    assert len(config["councils"]["stockport"]["sources"]) == 2  # untouched by this gate


def test_tameside_sources_deliberately_carry_no_plan_name():
    """Section 6/12 of this gate's own task - do not invent a supersession/
    attribution rule where the architecture doesn't safely support one.
    Tameside has two LocalPlan rows (plus Places for Everyone) and no safe
    way to disambiguate from the monitoring page alone - registered as a
    council-level source on purpose, not by omission. Still true; untouched
    by LPDI V1 Gate 3J ("Normal Authority Cohort Activation")."""
    config = _real_config()
    for source in config["councils"]["tameside"]["sources"]:
        assert source.get("plan_name") is None, f"tameside source unexpectedly carries a plan_name: {source}"


def test_rochdale_amr_page_source_still_deliberately_carries_no_plan_name():
    """Rochdale's ORIGINAL amr_page source (this gate) - genuinely
    untouched by LPDI V1 Gate 3J, which explicitly preserves it rather than
    force-linking it (see config/policy_sources.yaml's own comment on this
    entry). It still carries no plan_name for the same reason as when this
    test was first written: its own AMR figures have not been independently
    verified as belonging to Rochdale's own plan rather than being genuinely
    authority-wide content, so it stays council-level pending that check."""
    config = _real_config()
    amr_sources = [s for s in config["councils"]["rochdale"]["sources"] if s["source_type"] == "amr_page"]
    assert len(amr_sources) == 1
    assert amr_sources[0].get("plan_name") is None


def test_rochdale_emerging_plan_source_deliberately_now_carries_a_plan_name():
    """UPDATE (LPDI V1 Gate 3J, "Normal Authority Cohort Activation"): unlike
    the amr_page source above, Rochdale's own directly-verified Publication
    Local Plan document IS explicitly plan-linked - Gate 3I/3J established
    Rochdale genuinely has its own current plan (Regulation 19 Publication,
    a live consultation as of this gate), independent of Places for
    Everyone, with a verified direct PDF - see this gate's own Rochdale
    onboarding step, which creates the matching LocalPlan row THIS source
    entry resolves against. This is the deliberate exception to the
    Section 6/12 "do not invent attribution" rule above: it isn't inventing
    anything - it's stating a real, independently-verified plan identity,
    exactly the same as every other council's plan-linked source."""
    config = _real_config()
    emerging_sources = [s for s in config["councils"]["rochdale"]["sources"] if s["source_type"] == "emerging_plan"]
    assert len(emerging_sources) == 1
    assert emerging_sources[0]["plan_name"] == "Rochdale Local Plan"
    assert emerging_sources[0]["plan_version"] == "Regulation 19 Publication"


def test_every_other_new_council_source_has_a_real_plan_name():
    config = _real_config()
    for code in ("bolton", "manchester", "oldham", "wigan"):
        for source in config["councils"][code]["sources"]:
            assert source.get("plan_name"), f"{code} source missing plan_name: {source}"


# --- Idempotent registration against an isolated test database ----------------


def test_new_councils_register_without_a_local_plan_existing_yet(session):
    """Mirrors test_salford_trafford_reg19_sources.py's own established
    pattern exactly - real config, session fixture (isolated test DB, never
    production). No LocalPlan rows exist in this fresh test database, so
    every source - even ones naming a real plan_name - must resolve to
    local_plan_id=None, never guess or fabricate a link."""
    config = _real_config()
    for code in NEW_OR_EXTENDED_COUNCILS:
        sources = register_sources_for_council(session, code, config=config)
        assert sources, f"{code} registered zero sources"
        assert all(s.local_plan_id is None for s in sources), f"{code} unexpectedly resolved a local_plan_id with no LocalPlan present"


def test_registration_is_idempotent_across_repeated_runs(session):
    config = _real_config()
    first_pass = {code: register_sources_for_council(session, code, config=config) for code in NEW_OR_EXTENDED_COUNCILS}
    second_pass = {code: register_sources_for_council(session, code, config=config) for code in NEW_OR_EXTENDED_COUNCILS}

    for code in NEW_OR_EXTENDED_COUNCILS:
        assert {s.id for s in first_pass[code]} == {s.id for s in second_pass[code]}

    all_rows = session.execute(select(MonitoredSource)).scalars().all()
    urls = [r.url for r in all_rows]
    assert len(urls) == len(set(urls)), "repeated registration created duplicate MonitoredSource rows"


def test_registering_new_councils_does_not_disturb_previously_existing_ones(session):
    config = _real_config()
    before = {code: register_sources_for_council(session, code, config=config) for code in PREVIOUSLY_EXISTING_COUNCILS}

    for code in NEW_OR_EXTENDED_COUNCILS:
        register_sources_for_council(session, code, config=config)

    for code in PREVIOUSLY_EXISTING_COUNCILS:
        after = session.execute(select(MonitoredSource).where(MonitoredSource.council_code == code)).scalars().all()
        assert {r.id for r in after} == {r.id for r in before[code]}


def test_source_auto_links_to_local_plan_once_the_matching_plan_exists(session):
    """The positive case - a real LocalPlan row matching a source entry's
    own plan_name/plan_version DOES resolve local_plan_id, exactly as
    app.policy.sources._resolve_local_plan_id already guarantees for every
    other council in this file (unchanged code, exercised against new
    config data)."""
    config = _real_config()
    _make_local_plan(session, "bolton", "Bolton's Allocations Plan", "Adopted (3 December 2014, unrevised)")

    sources = register_sources_for_council(session, "bolton", config=config)

    assert all(s.local_plan_id is not None for s in sources), "bolton sources failed to auto-link to its own real LocalPlan row"


def test_rochdale_and_tameside_stay_unlinked_even_once_other_plans_exist(session):
    """Confirms the deliberate council-level registration (no plan_name)
    is inert with respect to auto-linking - even if unrelated LocalPlan
    rows exist, a source with no plan_name never resolves a local_plan_id
    by accident."""
    config = _real_config()
    _make_local_plan(session, "tameside", "Homes, Spaces, Places (Tameside Local Plan, Preferred Option)", "Regulation 18 Preferred Option (Dec 2025)")
    _make_local_plan(session, "tameside", "Tameside Unitary Development Plan (saved Policy H1)", "Adopted (saved UDP, 17 Nov 2004)")

    rochdale_sources = register_sources_for_council(session, "rochdale", config=config)
    tameside_sources = register_sources_for_council(session, "tameside", config=config)

    assert all(s.local_plan_id is None for s in rochdale_sources)
    assert all(s.local_plan_id is None for s in tameside_sources)


# --- E. Real-world report classification (existing, unmodified rules) ---------


def test_classify_report_type_handles_the_real_link_text_found_live():
    """Every (link_text, url) pair below was captured verbatim during this
    gate's own live browser verification of each council's real monitoring
    page - proving the EXISTING, unmodified classify_report_type already
    handles them correctly, with no new classification rule required."""
    cases = [
        # Bolton
        ("Bolton five year housing land supply position statement",
         "https://www.bolton.gov.uk/downloads/file/7609/bolton-five-year-housing-land-supply-position-statement",
         "housing_land_supply_statement"),
        # Tameside - the possessive "Authority's Monitoring Report" form,
        # exactly the apostrophe-stripping case classify_report_type's own
        # docstring cites as a real, previously-fixed production bug.
        ("Authority's Monitoring Report", "https://www.tameside.gov.uk/planning/ldf/planningmonitoring", "authority_monitoring_report"),
        # Trafford
        ("Authority Monitoring Report", "https://www.trafford.gov.uk/.../authority-monitoring-report", "authority_monitoring_report"),
        ("Five-year housing land position", "https://www.trafford.gov.uk/.../five-year-housing-land-position", "housing_land_supply_statement"),
        ("Housing Delivery Test", "https://www.trafford.gov.uk/.../housing-delivery-test", "housing_delivery_report"),
        # Manchester
        ("Five Year Housing Land Supply Statement 2019", "https://www.manchester.gov.uk/.../five-year-housing-land-supply-statement", "housing_land_supply_statement"),
    ]
    for link_text, url, expected_type in cases:
        report_type, matched_rule = classify_report_type(link_text, url)
        assert report_type == expected_type, f"{link_text!r} / {url!r} classified as {report_type!r}, expected {expected_type!r}"
        assert matched_rule is not None


def test_classify_report_type_correctly_defers_a_real_ambiguous_link_to_review():
    """A genuine, demonstrated finding from this gate's own live
    verification (Section 19 of the task - "differentiate failure modes,
    never convert one into a false success"): Bolton's real AMR link text
    is "2019/20 Combined Report" (no AMR keyword) and its URL slug uses
    HYPHENS ("authority-monitoring-report-2018-19"), which the existing
    keyword rules match on SPACES, not hyphens - classify_report_type
    correctly returns (None, None) rather than guessing, exactly as Part
    2.8 requires ("ambiguous classification must be queued for review,
    never guessed by an LLM"). This is the classifier working AS DESIGNED,
    not a defect - no change was made to classify_report_type for this
    gate (Section 10's own "discovery closure before extraction expansion"
    discipline). The one real document this affects was instead registered
    directly in config/policy_sources.yaml with its source_type stated
    explicitly (bypassing the crawler-only classifier entirely for this
    one already-verified document) - see this gate's own specification."""
    report_type, matched_rule = classify_report_type(
        "2019/20 Combined Report", "https://www.bolton.gov.uk/downloads/file/2549/authority-monitoring-report-2018-19",
    )
    assert report_type is None
    assert matched_rule is None


def test_classify_report_type_defers_a_second_real_ambiguous_case_plural_amr():
    """A second, independent real finding (same root-cause family as the
    hyphenated-URL case above, but distinct): Manchester's real link text
    is "The 2025 AMRs are available to download." - the plural "AMRs" does
    not match the existing " amr " bounded-word rule (which requires the
    exact singular token), and the URL again uses hyphens. Correctly
    deferred to review, not guessed - the real document behind this link
    was independently, directly verified during this gate's own browser
    research and does not need automatic classification to be usefully
    registered (see the amr_page index-page entry for manchester in
    config/policy_sources.yaml, which will surface it to a human reviewer
    on next discovery run regardless)."""
    report_type, matched_rule = classify_report_type(
        "The 2025 AMRs are available to download.", "https://www.manchester.gov.uk/planning-and-regeneration/planning/authority-monitoring-report-2025",
    )
    assert report_type is None
    assert matched_rule is None


def test_classify_report_type_does_not_misclassify_unrelated_council_links():
    # Real, unrelated link text found on the same real pages during
    # verification - must NOT be swept into a monitoring classification.
    unrelated = [
        ("Statement of Community Involvement", "https://www.bolton.gov.uk/downloads/file/4649/adopted-bolton-statement-of-community-involvement-2022"),
        ("Brownfield Land Register", "https://www.trafford.gov.uk/.../brownfield-land-register"),
    ]
    for link_text, url in unrelated:
        report_type, _ = classify_report_type(link_text, url)
        assert report_type not in ("authority_monitoring_report", "housing_land_supply_statement"), (link_text, report_type)


# --- F. Existing extraction routing already covers the new source types -------


def test_new_source_types_route_to_the_expected_extraction_categories():
    """No change to app.policy.document_selection was made - this proves
    the mapping already established for these source_type strings is what
    this gate's new config entries rely on."""
    assert DOCUMENT_TYPE_TO_CATEGORIES["authority_monitoring_report"] == frozenset({"housing_delivery", "five_year_supply"})
    assert DOCUMENT_TYPE_TO_CATEGORIES["housing_land_supply_statement"] == frozenset({"five_year_supply"})
    # Index/discovery-page types are never themselves extraction targets -
    # only the individual documents report_discovery finds ON them are.
    assert DOCUMENT_TYPE_TO_CATEGORIES["monitoring_page"] == frozenset()
    assert DOCUMENT_TYPE_TO_CATEGORIES["amr_page"] == frozenset()
    assert DOCUMENT_TYPE_TO_CATEGORIES["housing_land_supply_page"] == frozenset()


# --- G. Provenance retained on every new registration --------------------------


def test_registered_sources_retain_full_provenance(session):
    config = _real_config()
    sources = register_sources_for_council(session, "wigan", config=config)
    for source in sources:
        assert source.council_code == "wigan"
        assert source.url
        assert source.source_type
        assert source.title  # human-readable label, never blank


# --- K. No scoring/AI/scope-creep introduced -----------------------------------


def test_config_file_introduces_no_new_source_type_vocabulary():
    """Every source_type used by this gate's new entries must already be
    one of the documented, pre-existing MonitoredSource.source_type values
    (see that model's own docstring) - proving no new document-type
    vocabulary was invented, per this gate's own explicit STOP condition."""
    known_types = {
        "landing_page", "adopted_plan", "emerging_plan", "timetable", "consultation_portal",
        "examination_library", "policies_map", "evidence_library", "pdf", "other", "webpage",
        "local_development_scheme", "annual_monitoring_report", "housing_delivery_statement",
        "housing_trajectory", "five_year_supply_statement", "housing_need_assessment",
        "inspectors_report", "inspector_report", "main_modifications", "adoption_statement",
        "monitoring_page", "housing_land_supply_page", "amr_page", "policy_document_library",
        "authority_monitoring_report", "housing_land_supply_statement", "housing_delivery_report",
        "housing_delivery_test_action_plan", "local_plan",
    }
    config = _real_config()
    for code in NEW_OR_EXTENDED_COUNCILS:
        for source in config["councils"][code]["sources"]:
            assert source["source_type"] in known_types, f"{code} introduces an unrecognised source_type: {source['source_type']!r}"
