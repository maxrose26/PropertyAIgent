"""Tests for Sprint 4.5b ("Entity Search + Allocation Card Refinement") -
app.reporting.allocation_discovery's linked-application tag/detail changes
(Parts 1-3) and app.reporting.entity_search's new deterministic search
layer (Parts 4-13). Follows the same "unit-test the pure helpers a page
delegates to" convention as tests/test_allocation_discovery.py.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import event

from app.db.models import Application, LocalPlan, LocalPlanSite, SchemeIntelligence, Site
from app.reporting.allocation_discovery import (
    ALLOCATION_DETAIL_NO_APPLICATION_MESSAGE,
    ALLOCATION_DETAIL_NO_APPLICATION_NOTE,
    LINKED_APPLICATION_TAG_LABEL,
    apply_filters,
    build_allocation_card,
    build_linked_application_summaries,
    build_matching_attributes,
    build_summary_metrics,
    compute_categories,
    has_trusted_linked_application,
    has_trusted_site_match,
)
from app.reporting.entity_search import (
    DEFAULT_RESULT_LIMIT,
    SEARCH_SCOPES,
    search_allocation_entities,
    search_entities,
    search_planning_site_entities,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_local_plan(session, council_code="testcouncil", status="adopted", plan_name="Test Local Plan", **kwargs) -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name=plan_name, status=status, raw_status=status, **kwargs)
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, local_plan_id, *, council_code="testcouncil", policy_reference="HOM 1.1",
                      site_name="Land off Test Road", review_status="auto_applied", **kwargs) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=local_plan_id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Test Local Plan", plan_status="adopted", review_status=review_status, **kwargs,
    )
    session.add(allocation)
    session.commit()
    return allocation


def _make_site(session, *, address="1 Test Street", **kwargs) -> Site:
    site = Site(council_code="testcouncil", canonical_address=address.lower(), display_address=address, **kwargs)
    session.add(site)
    session.commit()
    return site


def _make_app(session, site_id, reference="APP/1", **kwargs) -> Application:
    app = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kwargs)
    session.add(app)
    session.commit()
    return app


def _make_scheme_intelligence(session, application_id, total_units_final=None) -> SchemeIntelligence:
    si = SchemeIntelligence(application_id=application_id, total_units_final=total_units_final)
    session.add(si)
    session.commit()
    return si


def _build_card_for(session, allocation, *, matched_site=None, linked_applications=None):
    return build_allocation_card(
        allocation, plan=allocation.local_plan, council_name="Test Council", council_codes_on_plan=["testcouncil"],
        matched_site=matched_site, linked_applications=linked_applications or [],
        visual_summary={"status": "none", "primary": None, "others": []}, visual_fallback=None,
        council_five_year_supply=None,
    )


# --- Part 1/2 - allocation card: no panel, compact tag only when confirmed --


def test_allocation_card_no_longer_renders_the_old_big_panel():
    """Part 1 - the removed render_alert("opportunity_signal", ...) call
    must not exist in allocation_card() any more."""
    source = (REPO_ROOT / "app" / "ui" / "shell.py").read_text(encoding="utf-8")
    # Locate allocation_card's own body, not the whole file, so this can't
    # pass just because some OTHER function still happens to avoid the
    # phrase.
    start = source.index("def allocation_card(")
    end = source.index("\ndef ", start + 1)
    body = source[start:end]
    assert 'render_alert(\n                "opportunity_signal"' not in body
    assert "opportunity_signal" not in body


def test_allocation_card_badge_row_includes_linked_application_tag_conditionally():
    source = (REPO_ROOT / "app" / "ui" / "shell.py").read_text(encoding="utf-8")
    start = source.index("def allocation_card(")
    end = source.index("\ndef ", start + 1)
    body = source[start:end]
    assert 'show_linked_application_tag' in body
    assert '"linked_application"' in body


# --- Canonical trusted-linked-Application definition (Product Owner
# amendment, Part 5-9) - has_trusted_linked_application is THE ONE
# function every caller below (badge, filter, category, matching
# attributes, KPI) must read, so the badge and the filter can never
# disagree - the exact defect the Product Owner review found. -----------


def test_has_trusted_linked_application_true_when_confirmed_link_exists():
    card = {"linked_application_count": 1, "review_status": "confirmed"}
    assert has_trusted_linked_application(card) is True


def test_has_trusted_linked_application_true_for_auto_applied_match():
    """auto_applied is the platform's own deterministic match outcome, not
    a human-unreviewed guess - it is trusted the same way card["matched"]
    already is everywhere else."""
    card = {"linked_application_count": 1, "review_status": "auto_applied"}
    assert has_trusted_linked_application(card) is True


def test_has_trusted_linked_application_false_when_no_link():
    card = {"linked_application_count": 0, "review_status": "confirmed"}
    assert has_trusted_linked_application(card) is False


def test_has_trusted_linked_application_false_for_unconfirmed_fuzzy_match():
    """Part 2/5: "no fuzzy suggestion should be presented as confirmed" -
    even with a real linked Application, a needs_confirmation allocation-
    to-Site match must not count as a trusted link."""
    card = {"linked_application_count": 1, "review_status": "needs_confirmation"}
    assert has_trusted_linked_application(card) is False


def test_linked_application_tag_label_is_the_specified_wording():
    assert LINKED_APPLICATION_TAG_LABEL == "Planning application linked"


def _matching_card(**overrides) -> dict:
    """A minimal card dict covering exactly the fields apply_filters/
    CATEGORY_DEFINITIONS/build_matching_attributes/build_summary_metrics
    read, for testing the canonical-definition fix without needing a full
    build_allocation_card() assembly."""
    base = {
        "id": 1, "council_code": "testcouncil", "council_name": "Test Council", "local_plan_id": 1,
        "plan_status_bucket": "adopted", "intended_use": "residential",
        "capacity": {"value": 100, "kind": "minimum"}, "matched": True, "matched_site_id": 1,
        "linked_application_count": 1, "review_status": "needs_confirmation",
        "visual_status": "none", "visual_fallback": None, "review_states": None,
        "is_multi_authority": False, "cross_boundary_councils": [], "major_housing": False,
        "duplicate_classification": None, "plan_name": "Test Plan", "build_status": None,
        "plan_status": "adopted", "kpi_capacity_contribution": {"value": 100, "is_estimate": False},
        "lapse_status": None, "council_five_year_supply": None,
    }
    base.update(overrides)
    return base


def test_apply_filters_linked_excludes_needs_confirmation():
    """The correctness defect: filtering "Linked" must never return an
    allocation that shows no badge - both now read
    has_trusted_linked_application."""
    unconfirmed = _matching_card(id=1, linked_application_count=1, review_status="needs_confirmation")
    confirmed = _matching_card(id=2, linked_application_count=1, review_status="confirmed")
    result = apply_filters([unconfirmed, confirmed], {"application_linkage": "linked"})
    assert [c["id"] for c in result] == [2]


def test_apply_filters_not_linked_includes_needs_confirmation():
    """The negation: "Not linked" must include a needs_confirmation match
    with a real Application row, since it isn't a TRUSTED link either."""
    unconfirmed = _matching_card(id=1, linked_application_count=1, review_status="needs_confirmation")
    confirmed = _matching_card(id=2, linked_application_count=1, review_status="confirmed")
    zero_apps = _matching_card(id=3, linked_application_count=0, review_status="confirmed")
    result = apply_filters([unconfirmed, confirmed, zero_apps], {"application_linkage": "not_linked"})
    assert sorted(c["id"] for c in result) == [1, 3]


def test_apply_filters_linked_application_composes_with_council_and_plan_status():
    """Part 7: filters compose with clear AND semantics."""
    match = _matching_card(id=1, council_code="bury", plan_status_bucket="adopted", linked_application_count=1, review_status="confirmed")
    wrong_council = _matching_card(id=2, council_code="stockport", plan_status_bucket="adopted", linked_application_count=1, review_status="confirmed")
    wrong_status = _matching_card(id=3, council_code="bury", plan_status_bucket="emerging", linked_application_count=1, review_status="confirmed")
    not_trusted = _matching_card(id=4, council_code="bury", plan_status_bucket="adopted", linked_application_count=1, review_status="needs_confirmation")
    result = apply_filters(
        [match, wrong_council, wrong_status, not_trusted],
        {"councils": ["bury"], "plan_status_buckets": ["adopted"], "application_linkage": "linked"},
    )
    assert [c["id"] for c in result] == [1]


def test_no_linked_application_category_uses_canonical_definition():
    unconfirmed = _matching_card(id=1, linked_application_count=1, review_status="needs_confirmation")
    trusted = _matching_card(id=2, linked_application_count=1, review_status="confirmed")
    categories = {c["key"]: c for c in compute_categories([unconfirmed, trusted])}
    assert [c["id"] for c in categories["no_linked_application"]["cards"]] == [1]


def test_build_matching_attributes_has_linked_application_uses_canonical_definition():
    unconfirmed = _matching_card(linked_application_count=1, review_status="needs_confirmation")
    assert build_matching_attributes(unconfirmed)["has_linked_application"] is False
    trusted = _matching_card(linked_application_count=1, review_status="confirmed")
    assert build_matching_attributes(trusted)["has_linked_application"] is True


def test_summary_metrics_no_linked_application_kpi_uses_canonical_definition():
    unconfirmed = _matching_card(id=1, linked_application_count=1, review_status="needs_confirmation")
    trusted = _matching_card(id=2, linked_application_count=1, review_status="confirmed")
    summary = build_summary_metrics([unconfirmed, trusted])
    assert summary["no_linked_application"] == 1


def test_summary_metrics_matched_to_sites_kpi_is_not_affected_by_trust_definition():
    """Part 8: matched_to_sites means "matched to a Site", a genuinely
    different claim from "has a trusted linked Application" - a
    needs_confirmation match still counts here."""
    unconfirmed_but_matched = _matching_card(id=1, matched=True, linked_application_count=0, review_status="needs_confirmation")
    summary = build_summary_metrics([unconfirmed_but_matched])
    assert summary["matched_to_sites"] == 1


# --- has_trusted_site_match - a deliberately separate concept (Part 8) --


def test_has_trusted_site_match_false_for_needs_confirmation():
    card = {"matched": True, "review_status": "needs_confirmation"}
    assert has_trusted_site_match(card) is False


def test_has_trusted_site_match_true_for_confirmed_even_with_zero_applications():
    """A trustworthy Site match with no Application filed yet is still a
    genuine "linked planning Site" - has_trusted_site_match doesn't
    require an Application the way has_trusted_linked_application does."""
    card = {"matched": True, "review_status": "confirmed", "linked_application_count": 0}
    assert has_trusted_site_match(card) is True


def test_has_trusted_site_match_false_when_not_matched():
    card = {"matched": False, "review_status": None}
    assert has_trusted_site_match(card) is False


# --- Part 3 - allocation detail: every linked Application, never one picked


def test_build_linked_application_summaries_empty_when_none_linked():
    assert build_linked_application_summaries([], matched_site=None) == []


def test_build_linked_application_summaries_lists_every_application(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    app1 = _make_app(session, site.id, reference="APP/1", status="Pending", decision=None)
    app2 = _make_app(session, site.id, reference="APP/2", status="Decided", decision="Granted")
    _make_scheme_intelligence(session, app1.id, total_units_final=50)
    session.refresh(app1)

    summaries = build_linked_application_summaries([app1, app2], matched_site=site)

    assert len(summaries) == 2
    refs = {s["reference"] for s in summaries}
    assert refs == {"APP/1", "APP/2"}
    app1_summary = next(s for s in summaries if s["reference"] == "APP/1")
    assert app1_summary["units"] == 50
    assert app1_summary["site_address"] == site.display_address
    app2_summary = next(s for s in summaries if s["reference"] == "APP/2")
    assert app2_summary["decision"] == "Granted"


def test_build_linked_application_summaries_falls_back_to_estimated_units(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id)
    site = _make_site(session)
    app = _make_app(session, site.id, reference="APP/1", estimated_unit_count=25)

    summaries = build_linked_application_summaries([app], matched_site=site)

    assert summaries[0]["units"] == 25


def test_allocation_card_carries_detail_no_application_wording(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    card = _build_card_for(session, allocation)
    assert card["detail_no_application_message"] == ALLOCATION_DETAIL_NO_APPLICATION_MESSAGE
    assert card["detail_no_application_note"] == ALLOCATION_DETAIL_NO_APPLICATION_NOTE
    assert "currently linked to this allocation in PropertyAIgent" in card["detail_no_application_message"]
    # Never claims no Application exists in reality (Part 2's own rule).
    assert "does not exist" not in card["detail_no_application_message"].lower()


def test_allocation_card_linked_applications_field_matches_summaries(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    site = _make_site(session)
    app = _make_app(session, site.id, reference="APP/1")
    card = _build_card_for(session, allocation, matched_site=site, linked_applications=[app])
    assert card["linked_applications"] == build_linked_application_summaries([app], site)
    assert card["show_linked_application_tag"] is True


# --- Part 4-13 - Entity Search architecture ----------------------------------


def test_search_scopes_are_exactly_all_planning_sites_allocations():
    assert set(SEARCH_SCOPES) == {"all", "planning_sites", "allocations"}


def test_entity_search_module_has_no_openai_dependency():
    """Part 6/10 - "Do not use OpenAI. Do not require OPENAI_API_KEY." -
    verified at the source level: the module never imports openai, reads
    the env var, or calls out to an LLM client. Checked against actual
    code constructs, not prose - the module's own docstrings legitimately
    discuss OpenAI/AI in the negative ("no AI, no OPENAI_API_KEY
    dependency")."""
    source = (REPO_ROOT / "app" / "reporting" / "entity_search.py").read_text(encoding="utf-8")
    for banned in (
        "import openai", "from openai", "OpenAI(", ".responses.create(",
        'getenv("OPENAI_API_KEY")', "environ[\"OPENAI_API_KEY\"]",
    ):
        assert banned not in source


def test_entity_search_module_never_writes_to_the_database():
    """Part 13/16 - "no DB writes during normal search" - verified at the
    source level, mirroring the OpenAI-absence check above: this module
    should never call session.add/commit/delete at all, since every
    function here is read-only."""
    source = (REPO_ROOT / "app" / "reporting" / "entity_search.py").read_text(encoding="utf-8")
    for banned in ("session.add(", "session.commit(", "session.delete(", ".flush("):
        assert banned not in source


def test_search_allocation_entities_matches_by_policy_reference(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="JPA 8", site_name="Northern Gateway")
    _make_allocation(session, plan.id, policy_reference="HOM 2.1", site_name="Southern Fields")

    results = search_allocation_entities(session, "JPA 8")

    assert len(results) == 1
    assert results[0].entity_type == "allocation"
    assert results[0].reference == "JPA 8"
    assert results[0].match_rank == 0  # exact reference match


def test_search_allocation_entities_matches_by_name_prefix(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="HOM 1.1", site_name="Northern Gateway")

    results = search_allocation_entities(session, "Northern")

    assert len(results) == 1
    assert results[0].match_rank == 2  # prefix match on title


def test_search_allocation_entities_matches_by_council_substring_only(session):
    """council_name is resolved from app.config.load_councils() (a YAML
    file), not the test DB's Council row - so it falls back to the raw
    council_code ("testcouncil") for a code this config file doesn't
    know about, same as the rest of this codebase's card-building path."""
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="HOM 1.1", site_name="Land off Test Road")

    results = search_allocation_entities(session, "testcouncil")

    assert len(results) == 1
    assert results[0].match_rank == 3  # substring-only field, never rank 0/1/2


def test_search_allocation_entities_case_insensitive(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="JPA 8", site_name="Northern Gateway")

    assert len(search_allocation_entities(session, "jpa 8")) == 1
    assert len(search_allocation_entities(session, "NORTHERN")) == 1


def test_search_allocation_entities_destination_is_allocation_discovery(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 8")

    result = search_allocation_entities(session, "JPA 8")[0]

    assert result.destination_page == "pages/3_Local_Plan_Sites.py"
    assert result.destination_params == {"allocation_id": str(allocation.id)}


def test_search_allocation_entities_never_uses_application_data(session):
    """Part 5 - "Allocations must search LocalPlanSite / Allocation
    Discovery data directly. Do not search the Application dataset and
    then try to infer which results are allocations." An Application whose
    reference happens to match the query must never appear in allocation
    results."""
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="HOM 1.1", site_name="Land off Test Road")
    site = _make_site(session)
    _make_app(session, site.id, reference="MATCHME-123")

    results = search_allocation_entities(session, "MATCHME-123")

    assert results == []


def test_search_planning_site_entities_matches_application_reference(session):
    site = _make_site(session, address="1 Test Street")
    _make_app(session, site.id, reference="APP/2026/001")

    results = search_planning_site_entities(session, "APP/2026/001")

    assert len(results) == 1
    assert results[0].entity_type == "planning_site"
    assert results[0].reference == "APP/2026/001"
    assert results[0].match_rank == 0


def test_search_planning_site_entities_matches_address(session):
    site = _make_site(session, address="42 Example Avenue")
    _make_app(session, site.id, reference="APP/1", address="42 Example Avenue")

    results = search_planning_site_entities(session, "Example Avenue")

    assert len(results) == 1
    assert results[0].match_rank == 3  # address is a substring-only field


def test_search_planning_site_entities_blank_query_returns_nothing(session):
    site = _make_site(session)
    _make_app(session, site.id, reference="APP/1")
    assert search_planning_site_entities(session, "") == []
    assert search_planning_site_entities(session, "   ") == []


def test_search_planning_site_entities_destination_is_site_profile(session):
    site = _make_site(session)
    _make_app(session, site.id, reference="APP/2026/001")

    result = search_planning_site_entities(session, "APP/2026/001")[0]

    assert result.destination_page == "pages/1_Scheme_Detail.py"
    assert result.destination_params == {"site_id": str(site.id)}


def test_search_planning_site_entities_respects_allowed_site_ids(session):
    """Part 12 - reusing the caller's already-applied filters."""
    site_a = _make_site(session, address="1 Included Street")
    site_b = _make_site(session, address="2 Excluded Street")
    _make_app(session, site_a.id, reference="APP/INC")
    _make_app(session, site_b.id, reference="APP/EXC")

    results = search_planning_site_entities(session, "APP", allowed_site_ids={site_a.id})

    assert [r.reference for r in results] == ["APP/INC"]


def test_search_planning_site_entities_shows_linked_allocation_indicator(session):
    """Part 8 - "Linked to allocation <ref>" cross-link, only when a real
    LocalPlanSite.matched_site_id relationship exists."""
    plan = _make_local_plan(session)
    site = _make_site(session)
    _make_allocation(session, plan.id, policy_reference="JPA 8", matched_site_id=site.id)
    _make_app(session, site.id, reference="APP/2026/001")

    result = search_planning_site_entities(session, "APP/2026/001")[0]

    assert result.matched_entity_label == "Linked to allocation JPA 8"


def test_search_allocation_entities_shows_linked_planning_site_indicator(session):
    plan = _make_local_plan(session)
    site = _make_site(session)
    _make_allocation(session, plan.id, policy_reference="JPA 8", matched_site_id=site.id)

    result = search_allocation_entities(session, "JPA 8")[0]

    assert result.matched_entity_label == "Linked planning Site"


def test_search_entities_never_merges_entity_types(session):
    """Part 8 - grouped, never merged: an allocation whose name happens to
    match an Application reference string must still surface separately
    from that Application, never collapsed into one row."""
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="HOM 1.1", site_name="SharedName")
    site = _make_site(session)
    _make_app(session, site.id, reference="SharedName")

    results = search_entities(session, "SharedName", scope="all")

    assert len(results.allocations) == 1
    assert len(results.planning_sites) == 1
    assert results.allocations[0].entity_type == "allocation"
    assert results.planning_sites[0].entity_type == "planning_site"


def test_search_entities_scope_allocations_never_queries_applications(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="HOM 1.1", site_name="Land off Test Road")
    site = _make_site(session)
    _make_app(session, site.id, reference="APP/1")

    results = search_entities(session, "APP/1", scope="allocations")

    assert results.allocations == []
    assert results.planning_sites == []  # never run at all for this scope


def test_search_entities_scope_planning_sites_never_queries_allocations(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="HOM 1.1", site_name="Land off Test Road")
    site = _make_site(session)
    _make_app(session, site.id, reference="APP/1")

    results = search_entities(session, "Land off Test Road", scope="planning_sites")

    assert results.planning_sites == []
    assert results.allocations == []  # never run at all for this scope


def test_search_entities_empty_state_is_safe(session):
    results = search_entities(session, "nothing matches this at all", scope="all")
    assert results.is_empty is True
    assert results.allocations == []
    assert results.planning_sites == []


def test_search_entities_invalid_scope_raises():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        search_entities(None, "x", scope="everything")


# --- Deterministic ranking (Part 11) ------------------------------------


def test_ranking_prioritises_exact_reference_over_prefix_match(session):
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="HOM 2", site_name="A")
    _make_allocation(session, plan.id, policy_reference="HOM 2.1", site_name="B")

    results = search_allocation_entities(session, "HOM 2")

    assert results[0].reference == "HOM 2"
    assert results[0].match_rank == 0
    assert results[1].reference == "HOM 2.1"
    assert results[1].match_rank == 2


def test_ranking_never_uses_ai_or_opportunity_scoring():
    """Part 11 - the ranking function signature/behaviour is purely
    positional string matching; every SearchResult only ever carries
    match_rank/tie_break_id, never a scoring field. Checked against actual
    field/attribute names, not prose - the module's own docstrings
    legitimately discuss "no opportunity/relevance scoring" in the
    negative."""
    source = (REPO_ROOT / "app" / "reporting" / "entity_search.py").read_text(encoding="utf-8")
    for banned in ("opportunity_score", "relevance_score", "relevance_model", ".predict("):
        assert banned not in source.lower()


def test_ranking_tie_breaks_on_stable_id(session):
    plan = _make_local_plan(session)
    a = _make_allocation(session, plan.id, policy_reference="REF-A", site_name="Zeta")
    b = _make_allocation(session, plan.id, policy_reference="REF-B", site_name="Zeta")

    results = search_allocation_entities(session, "Zeta")

    assert [r.entity_id for r in results] == sorted([a.id, b.id])


# --- Bounded queries / no N+1 (Part 13) --------------------------------------


def _count_select_statements(session, fn):
    engine = session.get_bind()
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    return statements


def test_search_planning_site_entities_issues_bounded_query_count(session):
    sites = [_make_site(session, address=f"{n} Test Street") for n in range(1, 6)]
    for i, site in enumerate(sites):
        _make_app(session, site.id, reference=f"APP/BOUND-{i}")

    statements = _count_select_statements(session, lambda: search_planning_site_entities(session, "APP/BOUND"))

    # Three SELECTs total, regardless of match count: the Applications
    # themselves, one batched selectinload of their scheme_intelligence
    # rows, and one batched reverse-lookup for allocation cross-links -
    # never one query per Application result (which would be 5+ for the
    # 5 sites/apps seeded above).
    assert len(statements) == 3


def test_search_planning_site_entities_query_count_independent_of_result_count(session):
    for n in range(1, 21):
        site = _make_site(session, address=f"{n} Scale Street")
        _make_app(session, site.id, reference=f"APP/SCALE-{n}")

    statements = _count_select_statements(session, lambda: search_planning_site_entities(session, "SCALE"))
    assert len(statements) == 3


def test_search_allocation_entities_respects_default_result_limit(session):
    plan = _make_local_plan(session)
    for n in range(DEFAULT_RESULT_LIMIT + 10):
        _make_allocation(session, plan.id, policy_reference=f"REF-{n}", site_name=f"Bounded Site {n}")

    results = search_allocation_entities(session, "Bounded Site")

    assert len(results) <= DEFAULT_RESULT_LIMIT


def test_search_planning_site_entities_respects_limit_argument(session):
    for n in range(30):
        site = _make_site(session, address=f"{n} Limit Street")
        _make_app(session, site.id, reference=f"APP/LIMIT-{n}")

    results = search_planning_site_entities(session, "Limit Street", limit=5)
    assert len(results) <= 5
