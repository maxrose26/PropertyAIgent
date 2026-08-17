"""GM Allocation <-> Site controlled production write mode tests (Stage 2B,
amended - REVIEW_CANDIDATE zero-persistence-before-approval).

Every test runs against the shared in-memory SQLite `session` fixture
(tests/conftest.py) - never the real production database.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import Council, LocalPlanSite, Site
from app.extraction.local_plan import assess_delivery_scope
from app.policy import allocation_site_dry_run_matching as dry_run_module
from app.policy.allocation_site_dry_run_matching import (
    AMBIGUOUS,
    HIGH_CONFIDENCE_CANDIDATE,
    REVIEW_CANDIDATE,
    confirm_review_candidate,
    fetch_ambiguous_allocations,
    fetch_pending_review_allocations,
    reject_review_candidate,
    run_controlled_write,
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
                      match_confidence: float | None = None, review_status: str = "auto_applied") -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, policy_reference=policy_reference, site_name=site_name,
        minimum_dwellings=minimum_dwellings, plan_name="Test Local Plan", plan_status="adopted",
        matched_site_id=matched_site_id, match_confidence=match_confidence, review_status=review_status,
    )
    session.add(allocation)
    session.flush()
    return allocation


# ---------------------------------------------------------------------------
# Dry-run remains zero-writes
# ---------------------------------------------------------------------------


def test_dry_run_still_makes_zero_mutations(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West")
    session.commit()

    dry_run_module.run_dry_run_matching(session)

    session.refresh(allocation)
    assert allocation.matched_site_id is None
    assert allocation.review_status == "auto_applied"


def test_cli_requires_explicit_confirm_phrase_before_writing():
    import scripts.dry_run_gm_allocation_site_matching as cli

    assert cli.CONFIRM_PHRASE == "YES-WRITE-GM-ALLOCATION-SITE-MATCHES"

    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["prog", "--execute", "--confirm", "wrong-phrase"]
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code == 2
    finally:
        sys.argv = old_argv


# ---------------------------------------------------------------------------
# 1/2. REVIEW_CANDIDATE - zero persistence before approval
# ---------------------------------------------------------------------------


def test_review_candidate_produces_zero_persistence_via_controlled_write(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "land off mottram old road hyde")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    result = run_controlled_write(session)

    assert allocation.id not in result["written_high_confidence"]
    assert allocation.id in result["review_candidates_untouched"]
    session.refresh(allocation)
    assert allocation.matched_site_id is None
    assert allocation.match_confidence is None
    assert allocation.review_status == "auto_applied"
    assert allocation.confirmed_by is None
    assert allocation.confirmed_at is None
    assert allocation.match_review_note is None


def test_pending_review_candidates_derived_from_matching_not_review_status(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "land off mottram old road hyde")
    # review_status is the model default ("auto_applied") - proves
    # discovery does NOT depend on review_status being "needs_confirmation"
    # at all.
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road", review_status="auto_applied")
    session.commit()

    pending = fetch_pending_review_allocations(session)

    assert len(pending) == 1
    assert pending[0].allocation_id == allocation.id
    assert pending[0].classification == REVIEW_CANDIDATE


def test_unrelated_needs_confirmation_content_row_with_no_candidate_is_not_pending(session):
    # An allocation with review_status="needs_confirmation" for a
    # completely unrelated CONTENT reason, and no plausible Site at all -
    # must never appear as a pending Site-match review just because of
    # its review_status.
    _make_council(session, "testcouncil")
    _make_allocation(session, "testcouncil", "Nothing Like It At All Whatsoever",
                      policy_reference="REF2", review_status="needs_confirmation")
    session.commit()

    pending = fetch_pending_review_allocations(session)

    assert pending == []


# ---------------------------------------------------------------------------
# 3. Human confirmation revalidates against current data
# ---------------------------------------------------------------------------


def test_confirm_review_candidate_happy_path_writes_and_delegates_to_confirm_site_match(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "land off mottram old road hyde")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    pending = fetch_pending_review_allocations(session)
    candidate = pending[0].near_miss_candidates[0]
    assert candidate.site_id == site.id

    outcome = confirm_review_candidate(
        session, allocation_id=allocation.id, expected_site_id=candidate.site_id,
        confirmed_by="tester", note="verified via planning statement",
    )

    assert outcome == {"success": True}
    session.refresh(allocation)
    assert allocation.matched_site_id == site.id
    assert allocation.match_confidence == candidate.score
    assert allocation.review_status == "confirmed"
    assert allocation.confirmed_by == "tester"
    assert allocation.confirmed_at is not None
    assert allocation.match_review_note == "verified via planning statement"


# ---------------------------------------------------------------------------
# 4/5/6. Fail-closed revalidation
# ---------------------------------------------------------------------------


def test_changed_candidate_site_fails_closed_and_writes_nothing(session, monkeypatch):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "land off mottram old road hyde")
    other_site = _make_site(session, "testcouncil", "a totally different site")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    changed_result = dry_run_module.AllocationMatchResult(
        allocation_id=allocation.id, council="testcouncil", policy_reference="REF1",
        allocation_name="Land off Midland Road", allocation_capacity=100,
        current_review_status="auto_applied", classification=REVIEW_CANDIDATE,
        reason="the world changed",
        near_miss_candidates=[dry_run_module._site_candidate(session, other_site, 75.0)],
    )
    monkeypatch.setattr(dry_run_module, "evaluate_allocation", lambda *a, **kw: changed_result)

    outcome = confirm_review_candidate(
        session, allocation_id=allocation.id, expected_site_id=site.id,
        confirmed_by="tester", note="looks right",
    )

    assert outcome["success"] is False
    assert "changed" in outcome["reason"].lower()
    session.refresh(allocation)
    assert allocation.matched_site_id is None
    assert allocation.review_status == "auto_applied"


def test_candidate_becoming_ambiguous_fails_closed(session, monkeypatch):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "land off mottram old road hyde")
    other_site = _make_site(session, "testcouncil", "a second plausible site")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    ambiguous_result = dry_run_module.AllocationMatchResult(
        allocation_id=allocation.id, council="testcouncil", policy_reference="REF1",
        allocation_name="Land off Midland Road", allocation_capacity=100,
        current_review_status="auto_applied", classification=AMBIGUOUS,
        reason="now ambiguous",
        candidates=[
            dry_run_module._site_candidate(session, site, 82.0),
            dry_run_module._site_candidate(session, other_site, 81.0),
        ],
    )
    monkeypatch.setattr(dry_run_module, "evaluate_allocation", lambda *a, **kw: ambiguous_result)

    outcome = confirm_review_candidate(
        session, allocation_id=allocation.id, expected_site_id=site.id,
        confirmed_by="tester", note="looks right",
    )

    assert outcome["success"] is False
    assert "no longer a review candidate" in outcome["reason"]
    session.refresh(allocation)
    assert allocation.matched_site_id is None


def test_already_matched_allocation_fails_closed_on_confirm(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    other_site = _make_site(session, "testcouncil", "other site")
    allocation = _make_allocation(session, "testcouncil", "Anything", matched_site_id=site.id, match_confidence=100.0)
    session.commit()

    outcome = confirm_review_candidate(
        session, allocation_id=allocation.id, expected_site_id=other_site.id,
        confirmed_by="tester", note="note",
    )

    assert outcome["success"] is False
    assert "already has a matched Site" in outcome["reason"]
    session.refresh(allocation)
    assert allocation.matched_site_id == site.id  # untouched, not overwritten with other_site


def test_reject_review_candidate_also_fails_closed_on_drift(session, monkeypatch):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "land off mottram old road hyde")
    other_site = _make_site(session, "testcouncil", "a totally different site")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    changed_result = dry_run_module.AllocationMatchResult(
        allocation_id=allocation.id, council="testcouncil", policy_reference="REF1",
        allocation_name="Land off Midland Road", allocation_capacity=100,
        current_review_status="auto_applied", classification=REVIEW_CANDIDATE,
        reason="the world changed",
        near_miss_candidates=[dry_run_module._site_candidate(session, other_site, 75.0)],
    )
    monkeypatch.setattr(dry_run_module, "evaluate_allocation", lambda *a, **kw: changed_result)

    outcome = reject_review_candidate(
        session, allocation_id=allocation.id, expected_site_id=site.id,
        confirmed_by="tester", reason="not a match",
    )

    assert outcome["success"] is False
    session.refresh(allocation)
    assert allocation.matched_site_id is None
    assert allocation.review_status == "auto_applied"


def test_reject_review_candidate_happy_path_delegates_to_reject_site_match(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "land off mottram old road hyde")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    pending = fetch_pending_review_allocations(session)
    candidate = pending[0].near_miss_candidates[0]

    outcome = reject_review_candidate(
        session, allocation_id=allocation.id, expected_site_id=candidate.site_id,
        confirmed_by="tester", reason="not actually related",
    )

    assert outcome == {"success": True}
    session.refresh(allocation)
    assert allocation.matched_site_id is None  # cleared by reject_site_match
    assert allocation.review_status == "rejected"
    assert allocation.confirmed_by == "tester"


# ---------------------------------------------------------------------------
# 7/8/9. HIGH_CONFIDENCE persistence, idempotency, unrelated-status survival
# ---------------------------------------------------------------------------


def test_high_confidence_persistence_is_idempotent(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West")
    session.commit()

    first = run_controlled_write(session)
    assert allocation.id in first["written_high_confidence"]
    session.refresh(allocation)
    matched_after_first = allocation.matched_site_id

    second = run_controlled_write(session)

    assert second["written_high_confidence"] == []
    session.refresh(allocation)
    assert allocation.matched_site_id == matched_after_first
    assert len(session.execute(select(LocalPlanSite)).scalars().all()) == 1


def test_existing_unrelated_review_status_survives_high_confidence_write(session):
    # The mandatory Section 8 regression test: an allocation already
    # needs_confirmation for an UNRELATED content reason, and the matcher
    # separately finds a HIGH_CONFIDENCE_CANDIDATE for it.
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West", review_status="needs_confirmation")
    session.commit()

    result = run_controlled_write(session)

    assert allocation.id in result["written_high_confidence"]
    session.refresh(allocation)
    assert allocation.matched_site_id == site.id
    assert allocation.match_confidence == 100.0
    # Original content-review status is preserved exactly, never
    # overwritten just because a Site match was found.
    assert allocation.review_status == "needs_confirmation"
    assert allocation.confirmed_by is None  # no provenance fabricated
    assert allocation.confirmed_at is None

    # And it must NOT appear in the pending Site-match review queue merely
    # because review_status happens to be "needs_confirmation" - it's
    # matched now, so the matching harness itself excludes it.
    pending = fetch_pending_review_allocations(session)
    assert allocation.id not in {r.allocation_id for r in pending}


# ---------------------------------------------------------------------------
# 10/11. AMBIGUOUS - zero-write, no blanket rejection in the UI
# ---------------------------------------------------------------------------


def test_ambiguous_remains_zero_write(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "jacksons lane hazel grove stockport")
    _make_site(session, "testcouncil", "land bounded by jacksons lane hazel grove stockport")
    allocation = _make_allocation(session, "testcouncil", "Mill Lane (Hazel Grove)")
    session.commit()

    result = run_controlled_write(session)

    assert allocation.id not in result["written_high_confidence"]
    assert allocation.id in result["ambiguous_not_written"]
    session.refresh(allocation)
    assert allocation.matched_site_id is None


def test_ambiguous_ui_section_offers_no_action_buttons():
    page_path = Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "2b_Review_Allocation_Site_Matches.py"
    source = page_path.read_text(encoding="utf-8")

    marker = 'section_header(f"Ambiguous'
    assert marker in source
    ambiguous_section = source[source.index(marker):]
    assert "st.button(" not in ambiguous_section


def test_review_ui_page_imports_and_calls_existing_confirm_reject_helpers():
    page_path = Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "2b_Review_Allocation_Site_Matches.py"
    source = page_path.read_text(encoding="utf-8")

    assert "confirm_review_candidate" in source
    assert "reject_review_candidate" in source
    # Never a local reimplementation of the write itself.
    assert "allocation.matched_site_id = " not in source
    assert ".matched_site_id = " not in source


# ---------------------------------------------------------------------------
# 12/13. NO_CANDIDATE untouched, dry-run zero-mutation (already covered
# above/in test_allocation_site_dry_run_matching.py - kept here too since
# this task explicitly requires it in this file's own coverage).
# ---------------------------------------------------------------------------


def test_no_candidate_allocation_remains_untouched(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Nothing Like It At All Whatsoever")
    session.commit()

    result = run_controlled_write(session)

    assert allocation.id not in result["written_high_confidence"]
    assert allocation.id in result["no_candidate_untouched"]
    session.refresh(allocation)
    assert allocation.matched_site_id is None


# ---------------------------------------------------------------------------
# 14. No whole-allocation coverage conclusion
# ---------------------------------------------------------------------------


def test_confirm_and_reject_helpers_compute_no_capacity_conclusion():
    for fn in (dry_run_module.confirm_review_candidate, dry_run_module.reject_review_candidate,
               dry_run_module._revalidate_review_candidate):
        source = inspect.getsource(fn)
        assert "assess_delivery_scope" not in source
        assert "available" not in source.lower()
        assert "coverage" not in source.lower()


# ---------------------------------------------------------------------------
# 15. No "available" language reintroduced
# ---------------------------------------------------------------------------


def test_assess_delivery_scope_never_says_available_in_any_branch():
    cases = [(None, None), (300, 280), (300, 134), (300, 250)]
    for minimum_dwellings, matched_units in cases:
        result = assess_delivery_scope(minimum_dwellings, matched_units)
        assert "available" not in result["note"].lower()


# ---------------------------------------------------------------------------
# 16/17. No OpenAI dependency, no schema change
# ---------------------------------------------------------------------------


def test_no_openai_dependency_in_write_mode_module():
    source = inspect.getsource(dry_run_module)
    assert "openai" not in source.lower()


def test_no_openai_dependency_in_review_ui_page():
    page_path = Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "2b_Review_Allocation_Site_Matches.py"
    source = page_path.read_text(encoding="utf-8")
    assert "openai" not in source.lower()


def test_no_schema_change_local_plan_site_columns_unchanged():
    expected_local_plan_site_columns = {
        "id", "council_code", "local_plan_id", "policy_reference", "site_name", "intended_use",
        "minimum_dwellings", "indicative_capacity", "maximum_capacity", "category", "allocation_status",
        "raw_allocation_status", "plan_name", "plan_status", "source_document_url", "source_page",
        "geometry_placeholder", "matched_site_id", "match_confidence", "confirmed_by", "confirmed_at",
        "match_review_note", "review_status", "duplicate_classification", "duplicate_classification_note",
        "progression_signal", "progression_reasons", "progression_computed_at", "latitude", "longitude",
        "extracted_at", "updated_at",
    }
    assert {c.name for c in LocalPlanSite.__table__.columns} == expected_local_plan_site_columns
