"""GM Allocation <-> Site dry-run candidate matching harness tests (Stage 2A).

Every test runs against the shared in-memory SQLite `session` fixture
(tests/conftest.py) - never the real production database. Nothing here
calls app.db.session.get_engine/get_session.
"""
from __future__ import annotations

import inspect

import pytest
from sqlalchemy import select

from app.db.models import Council, LocalPlanSite, Site
from app.extraction import local_plan as local_plan_module
from app.policy import allocation_site_dry_run_matching as dry_run_module
from app.policy.allocation_site_dry_run_matching import (
    AMBIGUOUS,
    HIGH_CONFIDENCE_CANDIDATE,
    NO_CANDIDATE,
    REVIEW_CANDIDATE,
    evaluate_allocation,
    run_dry_run_matching,
    summarize_results,
)


def _make_council(session, code: str) -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))


def _make_site(session, council_code: str, address: str) -> Site:
    site = Site(council_code=council_code, canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_allocation(session, council_code: str, site_name: str, *, policy_reference: str | None = "REF1",
                      minimum_dwellings: int | None = 100, matched_site_id: int | None = None,
                      review_status: str = "auto_applied") -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, policy_reference=policy_reference, site_name=site_name,
        minimum_dwellings=minimum_dwellings, plan_name="Test Local Plan", plan_status="adopted",
        matched_site_id=matched_site_id, review_status=review_status,
    )
    session.add(allocation)
    session.flush()
    return allocation


# ---------------------------------------------------------------------------
# 1. Zero mutations
# ---------------------------------------------------------------------------


def test_dry_run_makes_zero_mutations(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West")
    session.commit()

    before_matched_id = allocation.matched_site_id
    before_review_status = allocation.review_status
    before_lat, before_lon = allocation.latitude, allocation.longitude
    before_site_count = len(session.execute(select(Site)).scalars().all())
    before_allocation_count = len(session.execute(select(LocalPlanSite)).scalars().all())

    run_dry_run_matching(session)

    session.expire_all()
    refreshed = session.get(LocalPlanSite, allocation.id)
    assert refreshed.matched_site_id == before_matched_id
    assert refreshed.review_status == before_review_status
    assert refreshed.latitude == before_lat
    assert refreshed.longitude == before_lon
    assert len(session.execute(select(Site)).scalars().all()) == before_site_count
    assert len(session.execute(select(LocalPlanSite)).scalars().all()) == before_allocation_count


def test_dry_run_functions_never_call_session_add_flush_commit():
    # Scoped to the dry-run functions specifically, not the whole module -
    # Stage 2B added run_controlled_write() to this same file, which
    # legitimately does call session.commit() (see
    # test_allocation_site_controlled_write.py for its own coverage).
    for fn in (
        dry_run_module.run_dry_run_matching,
        dry_run_module.evaluate_allocation,
        dry_run_module.summarize_results,
        dry_run_module._iterative_matches,
        dry_run_module._near_miss_candidates,
        dry_run_module._site_candidate,
    ):
        source = inspect.getsource(fn)
        assert "session.add(" not in source
        assert "session.flush()" not in source
        assert "session.commit()" not in source


# ---------------------------------------------------------------------------
# 2. Existing matcher reused, not duplicated
# ---------------------------------------------------------------------------


def test_module_does_not_redefine_match_to_existing_site():
    source = inspect.getsource(dry_run_module)
    assert "def match_to_existing_site" not in source


def test_evaluate_allocation_delegates_decision_to_existing_matcher(session, monkeypatch):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Anything")
    session.commit()

    calls = []

    def _stub_match(site_name, candidates):
        calls.append((site_name, candidates))
        # Mirrors the real function's own contract: no candidates left
        # (or none plausible) means no match - only the FIRST call (with
        # the real candidate list) should ever produce a winner here.
        if not candidates:
            return None, 0.0
        return site, 99.9

    monkeypatch.setattr(dry_run_module, "match_to_existing_site", _stub_match)

    result = evaluate_allocation(session, allocation, [site])

    assert len(calls) >= 1
    assert result.classification == HIGH_CONFIDENCE_CANDIDATE
    assert result.candidates[0].site_id == site.id
    assert result.candidates[0].score == 99.9


def test_geocode_local_plan_site_never_imported_or_called_by_dry_run_module():
    source = inspect.getsource(dry_run_module)
    # The module docstring explains IN PROSE why geocoding is never called -
    # that mention is fine. What must never appear is an actual import or
    # call of it.
    assert "import geocode_local_plan_site" not in source
    assert "geocode_local_plan_site(" not in source
    assert "geocode_address" not in source


# ---------------------------------------------------------------------------
# 3. Already-matched allocations skipped
# ---------------------------------------------------------------------------


def test_already_matched_allocations_are_excluded_from_dry_run(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "matched site address")
    matched_allocation = _make_allocation(session, "testcouncil", "Matched One", matched_site_id=site.id)
    unmatched_allocation = _make_allocation(session, "testcouncil", "Unmatched One", policy_reference="REF2")
    session.commit()

    dry_run = run_dry_run_matching(session)

    evaluated_ids = {r.allocation_id for r in dry_run["results"]}
    assert matched_allocation.id not in evaluated_ids
    assert unmatched_allocation.id in evaluated_ids
    assert dry_run["already_matched"] == 1
    assert dry_run["unmatched_evaluated"] == 1
    assert dry_run["total_allocations"] == 2


# ---------------------------------------------------------------------------
# 4. Council scoping retained
# ---------------------------------------------------------------------------


def test_council_scoping_prevents_cross_council_matching(session):
    _make_council(session, "testcouncil")
    _make_council(session, "othercouncil")
    # A perfect textual match exists, but in the WRONG council - must never
    # be considered, exactly mirroring app.extraction.local_plan's own
    # council-scoped candidate selection (ingest_local_plan.py).
    _make_site(session, "othercouncil", "riverside gardens perfect match")
    allocation = _make_allocation(session, "testcouncil", "Riverside Gardens Perfect Match")
    session.commit()

    dry_run = run_dry_run_matching(session)
    result = next(r for r in dry_run["results"] if r.allocation_id == allocation.id)

    assert result.classification == NO_CANDIDATE
    assert result.candidates == []
    assert result.near_miss_candidates == []


# ---------------------------------------------------------------------------
# 3 (false-positive safety). Direction veto, generic names, locality alone
# ---------------------------------------------------------------------------


def test_east_west_direction_veto_is_preserved(session):
    _make_council(session, "testcouncil")
    site_west = _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    _make_site(session, "testcouncil", "heald green east retail park testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West")
    session.commit()

    result = evaluate_allocation(session, allocation, [
        session.get(Site, site_west.id),
        session.execute(select(Site).where(Site.canonical_address.like("%east%"))).scalar_one(),
    ])

    assert result.classification == HIGH_CONFIDENCE_CANDIDATE
    assert len(result.candidates) == 1
    assert result.candidates[0].site_id == site_west.id


def test_north_south_direction_veto_is_preserved(session):
    _make_council(session, "testcouncil")
    site_north = _make_site(session, "testcouncil", "phoenix park north testcouncil")
    _make_site(session, "testcouncil", "phoenix park south testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Phoenix Park North")
    session.commit()

    candidates = session.execute(select(Site)).scalars().all()
    result = evaluate_allocation(session, allocation, candidates)

    assert result.classification == HIGH_CONFIDENCE_CANDIDATE
    assert result.candidates[0].site_id == site_north.id


def test_generic_shared_road_name_does_not_force_a_false_high_confidence_match(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "12 chester road stretford testcouncil")
    _make_site(session, "testcouncil", "984 chester road timperley testcouncil district")
    allocation = _make_allocation(session, "testcouncil", "Chester Road")
    session.commit()

    candidates = session.execute(select(Site)).scalars().all()
    result = evaluate_allocation(session, allocation, candidates)

    # A bare generic road name shared by two genuinely different addresses
    # scores equally (100.0) against both under token_set_ratio - the
    # multi-site safeguard must surface this as AMBIGUOUS, never silently
    # pick one as a confident single winner.
    assert result.classification == AMBIGUOUS
    assert len(result.candidates) == 2


def test_broad_locality_alone_is_insufficient_for_a_confident_match(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "42 unrelated close elsewhere district")
    allocation = _make_allocation(session, "testcouncil", "Greater Manchester")  # locality name only
    session.commit()

    candidates = session.execute(select(Site)).scalars().all()
    result = evaluate_allocation(session, allocation, candidates)

    assert result.classification == NO_CANDIDATE


def test_matcher_uses_no_developer_or_company_signal():
    # Structural safeguard, not a data-driven test: the existing matcher
    # (and this dry-run harness) never references any entity/company field -
    # "same developer alone" literally cannot influence a match, because no
    # such signal is wired in anywhere in this call path.
    matcher_source = inspect.getsource(local_plan_module.match_to_existing_site)
    harness_source = inspect.getsource(dry_run_module)
    for forbidden in ("developer", "applicant_company", "landowner", "Company"):
        assert forbidden not in matcher_source
        assert forbidden not in harness_source


# ---------------------------------------------------------------------------
# No-candidate / ambiguous / multiple-plausible-Site handling
# ---------------------------------------------------------------------------


def test_no_candidate_when_council_has_no_sites_at_all(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Nothing Here")
    session.commit()

    result = evaluate_allocation(session, allocation, [])

    assert result.classification == NO_CANDIDATE
    assert "no Sites recorded" in result.reason


def test_review_candidate_for_a_near_miss_below_auto_threshold(session):
    _make_council(session, "testcouncil")
    # Chosen to land in the site_linking review band (>=70) but below
    # local_plan's own 80 auto-match threshold - a genuine near-miss.
    _make_site(session, "testcouncil", "land off mottram old road hyde")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    candidates = session.execute(select(Site)).scalars().all()
    result = evaluate_allocation(session, allocation, candidates)

    # normalise_address('Land off Midland Road') vs the Site's canonical
    # address scores ~76.5 (rapidfuzz token_set_ratio) - above
    # site_linking's own 70 review threshold, below local_plan's 80
    # auto-match threshold - a genuine, deterministic near-miss.
    assert result.classification == REVIEW_CANDIDATE
    assert result.near_miss_candidates
    assert result.candidates == []


def test_ambiguous_when_multiple_sites_independently_clear_threshold(session):
    _make_council(session, "testcouncil")
    site_a = _make_site(session, "testcouncil", "jacksons lane hazel grove stockport")
    site_b = _make_site(session, "testcouncil", "land bounded by jacksons lane hazel grove stockport")
    allocation = _make_allocation(session, "testcouncil", "Mill Lane (Hazel Grove)")
    session.commit()
    # Use the allocation's real name directly against these two near-
    # identical addresses - both score identically high (same real GM
    # production case, allocation 27 / Stockport HOM 2.28).
    candidates = session.execute(select(Site)).scalars().all()

    result = evaluate_allocation(session, allocation, candidates)

    assert result.classification == AMBIGUOUS
    assert len(result.candidates) >= 2
    site_ids = {c.site_id for c in result.candidates}
    assert site_a.id in site_ids or site_b.id in site_ids


def test_multiple_plausible_sites_uses_black_box_repeated_calls_not_new_scoring(session, monkeypatch):
    """Confirms MULTIPLE_PLAUSIBLE_SITES detection is driven purely by
    calling the existing match_to_existing_site() repeatedly (excluding
    prior winners) - never a second, independently-implemented scoring
    algorithm."""
    _make_council(session, "testcouncil")
    site_1 = _make_site(session, "testcouncil", "site one")
    site_2 = _make_site(session, "testcouncil", "site two")
    allocation = _make_allocation(session, "testcouncil", "Anything")
    session.commit()

    call_log = []
    remaining_winners = [(site_1, 95.0), (site_2, 90.0)]

    def _stub_match(site_name, candidates):
        call_log.append([c.id for c in candidates])
        for site, score in list(remaining_winners):
            if any(c.id == site.id for c in candidates):
                remaining_winners.remove((site, score))
                return site, score
        return None, 0.0

    monkeypatch.setattr(dry_run_module, "match_to_existing_site", _stub_match)

    result = evaluate_allocation(session, allocation, [site_1, site_2])

    assert result.classification == AMBIGUOUS
    assert len(result.candidates) == 2
    # Second call's candidate list must have excluded the first winner -
    # proof this is iterative black-box reuse, not a parallel algorithm.
    assert site_1.id not in call_log[1] or site_2.id not in call_log[1]


# ---------------------------------------------------------------------------
# No allocation-capacity conclusion
# ---------------------------------------------------------------------------


def test_no_allocation_capacity_conclusion_is_ever_produced(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "heald green west testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West", minimum_dwellings=500)
    session.commit()

    result = evaluate_allocation(session, allocation, [site])

    # allocation_capacity is a pure pass-through of the allocation's own
    # stated figure - never derived from, or compared against, candidate
    # Site data.
    assert result.allocation_capacity == 500
    result_fields = {f for f in result.__dataclass_fields__}
    assert "coverage" not in result_fields
    assert "remaining_capacity" not in result_fields
    assert "delivery_scope" not in result_fields

    source = inspect.getsource(dry_run_module)
    assert "assess_delivery_scope" not in source
    assert "available" not in source.lower()


# ---------------------------------------------------------------------------
# No OpenAI, no schema change
# ---------------------------------------------------------------------------


def test_no_openai_dependency():
    source = inspect.getsource(dry_run_module)
    assert "openai" not in source.lower()
    assert "OpenAI(" not in source


def test_no_schema_change_local_plan_site_and_site_columns_unchanged():
    # UPDATE (Gate 4A): see the identical note in
    # tests/test_allocation_document_evidence.py - three columns were
    # added, explicitly authorised by Gate 4A's own schema-decision
    # checkpoint, not by this module.
    expected_local_plan_site_columns = {
        "id", "council_code", "local_plan_id", "policy_reference", "site_name", "intended_use",
        "minimum_dwellings", "indicative_capacity", "maximum_capacity", "category", "allocation_status",
        "raw_allocation_status", "plan_name", "plan_status", "source_document_url", "source_page",
        "geometry_placeholder", "matched_site_id", "match_confidence", "confirmed_by", "confirmed_at",
        "match_review_note", "review_status", "duplicate_classification", "duplicate_classification_note",
        "progression_signal", "progression_reasons", "progression_computed_at", "latitude", "longitude",
        "extracted_at", "updated_at",
        "site_area_hectares", "green_belt_status", "source_excerpt",
    }
    expected_site_columns = {
        "id", "council_code", "canonical_address", "display_address", "postcode", "latitude", "longitude",
        "build_status", "build_status_checked_at", "epc_dwellings_found", "status_summary",
        "status_summary_updated_at", "excluded", "excluded_reason", "excluded_at", "first_seen_at", "updated_at",
    }
    assert {c.name for c in LocalPlanSite.__table__.columns} == expected_local_plan_site_columns
    assert {c.name for c in Site.__table__.columns} == expected_site_columns


# ---------------------------------------------------------------------------
# Summarize + real-shape sanity
# ---------------------------------------------------------------------------


def test_summarize_results_counts_match_classifications(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "heald green west testcouncil")
    _make_allocation(session, "testcouncil", "Heald Green West")
    _make_allocation(session, "testcouncil", "Nothing Like It At All Whatsoever", policy_reference="REF2")
    session.commit()

    dry_run = run_dry_run_matching(session)
    summary = summarize_results(dry_run)

    assert summary["unmatched_evaluated"] == 2
    assert (
        summary["high_confidence_candidates"] + summary["review_candidates"]
        + summary["ambiguous_candidates"] + summary["no_candidate"] == 2
    )
    assert "testcouncil" in summary["by_council"]
