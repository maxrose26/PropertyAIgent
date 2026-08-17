"""GM Allocation <-> Site controlled production write mode tests (Stage 2B).

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
    fetch_ambiguous_allocations,
    fetch_pending_review_allocations,
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
# Dry-run remains zero-writes even with the write-mode function present
# ---------------------------------------------------------------------------


def test_dry_run_still_makes_zero_mutations_after_write_mode_added(session):
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
# HIGH_CONFIDENCE_CANDIDATE writes
# ---------------------------------------------------------------------------


def test_high_confidence_candidate_persists(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West")
    session.commit()

    result = run_controlled_write(session)

    assert allocation.id in result["written_high_confidence"]
    session.refresh(allocation)
    assert allocation.matched_site_id == site.id
    assert allocation.match_confidence == 100.0
    # review_status is left completely untouched for a high-confidence
    # write - mirrors ingest_local_plan.py's own existing auto-apply
    # behaviour at this same threshold.
    assert allocation.review_status == "auto_applied"
    assert allocation.confirmed_by is None
    assert allocation.confirmed_at is None


# ---------------------------------------------------------------------------
# REVIEW_CANDIDATE writes - unconfirmed suggestion, never auto-confirmed
# ---------------------------------------------------------------------------


def test_review_candidate_written_as_unconfirmed_suggestion_not_auto_confirmed(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "land off mottram old road hyde")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    result = run_controlled_write(session)

    assert allocation.id in result["written_review_candidate"]
    assert allocation.id not in result["written_high_confidence"]
    session.refresh(allocation)
    assert allocation.matched_site_id == site.id
    assert allocation.review_status == "needs_confirmation"
    assert allocation.review_status != "confirmed"
    assert allocation.confirmed_by is None  # no human has acted yet


def test_review_candidate_becomes_actionable_via_pending_review_queue(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "land off mottram old road hyde")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    run_controlled_write(session)

    pending = fetch_pending_review_allocations(session)
    assert allocation.id in {a.id for a in pending}


def test_pending_review_queue_excludes_unrelated_needs_confirmation_content_rows(session):
    # An allocation with review_status="needs_confirmation" for an
    # unrelated CONTENT reason (e.g. migration-derived ambiguity) has no
    # matched_site_id at all - the combined filter must not surface it as
    # if it were a pending Site-match review.
    _make_council(session, "testcouncil")
    content_only = _make_allocation(session, "testcouncil", "Unrelated Content Ambiguity",
                                     policy_reference="REF2", review_status="needs_confirmation")
    session.commit()

    pending = fetch_pending_review_allocations(session)
    assert content_only.id not in {a.id for a in pending}


# ---------------------------------------------------------------------------
# AMBIGUOUS - never auto-resolved, never persisted
# ---------------------------------------------------------------------------


def test_ambiguous_candidate_not_auto_resolved_and_nothing_persisted(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "jacksons lane hazel grove stockport")
    _make_site(session, "testcouncil", "land bounded by jacksons lane hazel grove stockport")
    allocation = _make_allocation(session, "testcouncil", "Mill Lane (Hazel Grove)")
    session.commit()

    result = run_controlled_write(session)

    assert allocation.id not in result["written_high_confidence"]
    assert allocation.id not in result["written_review_candidate"]
    assert allocation.id in result["ambiguous_not_written"]
    session.refresh(allocation)
    assert allocation.matched_site_id is None
    assert allocation.review_status == "auto_applied"


def test_fetch_ambiguous_allocations_shows_all_candidates_live(session):
    _make_council(session, "testcouncil")
    site_a = _make_site(session, "testcouncil", "jacksons lane hazel grove stockport")
    site_b = _make_site(session, "testcouncil", "land bounded by jacksons lane hazel grove stockport")
    _make_allocation(session, "testcouncil", "Mill Lane (Hazel Grove)")
    session.commit()

    ambiguous = fetch_ambiguous_allocations(session)

    assert len(ambiguous) == 1
    site_ids = {c.site_id for c in ambiguous[0].candidates}
    assert site_a.id in site_ids
    assert site_b.id in site_ids


# ---------------------------------------------------------------------------
# NO_CANDIDATE - remains unmatched
# ---------------------------------------------------------------------------


def test_no_candidate_allocation_remains_unmatched(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Nothing Like It At All Whatsoever")
    session.commit()

    result = run_controlled_write(session)

    assert allocation.id not in result["written_high_confidence"]
    assert allocation.id not in result["written_review_candidate"]
    assert allocation.id in result["no_candidate_untouched"]
    session.refresh(allocation)
    assert allocation.matched_site_id is None


# ---------------------------------------------------------------------------
# Idempotency / safety (Section 7)
# ---------------------------------------------------------------------------


def test_already_confirmed_match_is_never_touched(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West",
                                   matched_site_id=site.id, match_confidence=100.0, review_status="confirmed")
    session.commit()

    result = run_controlled_write(session)

    assert result["written_high_confidence"] == []
    assert result["written_review_candidate"] == []
    session.refresh(allocation)
    assert allocation.matched_site_id == site.id
    assert allocation.review_status == "confirmed"


def test_rejected_match_is_never_rewritten(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West", review_status="rejected")
    session.commit()

    result = run_controlled_write(session)

    assert allocation.id not in result["written_high_confidence"]
    assert allocation.id not in result["written_review_candidate"]
    assert allocation.id in result["skipped_drift"]
    session.refresh(allocation)
    assert allocation.matched_site_id is None
    assert allocation.review_status == "rejected"


def test_idempotent_rerun_does_not_rewrite_or_duplicate(session):
    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "heald green west industrial estate testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Heald Green West")
    session.commit()

    first = run_controlled_write(session)
    assert allocation.id in first["written_high_confidence"]
    session.refresh(allocation)
    matched_after_first = allocation.matched_site_id
    confidence_after_first = allocation.match_confidence

    second = run_controlled_write(session)

    assert second["written_high_confidence"] == []
    assert second["written_review_candidate"] == []
    session.refresh(allocation)
    assert allocation.matched_site_id == matched_after_first
    assert allocation.match_confidence == confidence_after_first
    assert len(session.execute(select(LocalPlanSite)).scalars().all()) == 1  # no duplicate rows


def test_idempotent_rerun_after_human_confirmation_leaves_it_confirmed(session):
    from app.policy.site_match_review import confirm_site_match

    _make_council(session, "testcouncil")
    _make_site(session, "testcouncil", "land off mottram old road hyde")
    allocation = _make_allocation(session, "testcouncil", "Land off Midland Road")
    session.commit()

    run_controlled_write(session)  # writes as needs_confirmation
    confirm_site_match(session, allocation, confirmed_by="tester", note="verified via planning statement")
    session.refresh(allocation)
    assert allocation.review_status == "confirmed"

    run_controlled_write(session)  # rerun must not touch it

    session.refresh(allocation)
    assert allocation.review_status == "confirmed"
    assert allocation.confirmed_by == "tester"


# ---------------------------------------------------------------------------
# Confirm/reject reuse - the review UI never duplicates write logic
# ---------------------------------------------------------------------------


def test_review_ui_page_imports_and_calls_existing_confirm_reject_functions():
    page_path = Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "2b_Review_Allocation_Site_Matches.py"
    source = page_path.read_text(encoding="utf-8")

    assert "from app.policy.site_match_review import confirm_site_match, reject_site_match" in source
    assert "confirm_site_match(session, allocation" in source
    assert "reject_site_match(session, allocation" in source
    # Never a local reimplementation of the write itself.
    assert "allocation.matched_site_id = " not in source
    assert "allocation.review_status = " not in source


def test_review_ui_page_does_not_imply_whole_allocation_coverage():
    page_path = Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "2b_Review_Allocation_Site_Matches.py"
    source = page_path.read_text(encoding="utf-8").lower()

    for forbidden in ("matched whole site", "accounts for the whole", "entire allocation"):
        assert forbidden not in source
    assert "relates to this allocation" in source or "relating to this allocation" in source


def test_local_plan_sites_detail_page_uses_related_planning_site_wording():
    page_path = Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "3_Local_Plan_Sites.py"
    source = page_path.read_text(encoding="utf-8")

    assert "Related Planning Site" in source
    assert "MATCHED WHOLE SITE" not in source.upper()


# ---------------------------------------------------------------------------
# "available" wording removed from delivery-scope output (Section 9)
# ---------------------------------------------------------------------------


def test_assess_delivery_scope_partial_status_never_says_available():
    result = assess_delivery_scope(minimum_dwellings=300, matched_units=134)

    assert result["status"] == "partial"
    assert "available" not in result["note"].lower()
    assert "not currently accounted for by identified planning activity" in result["note"]


def test_assess_delivery_scope_never_says_available_in_any_branch():
    # Every reachable branch's OUTPUT note - the docstring may still
    # explain the rule in prose ("never asserts ... is 'available'"), but
    # nothing actually shown to a user may ever say it.
    cases = [
        (None, None),       # unknown
        (300, 280),         # full_site
        (300, 134),         # partial
        (300, 250),         # roughly_matches
    ]
    for minimum_dwellings, matched_units in cases:
        result = assess_delivery_scope(minimum_dwellings, matched_units)
        assert "available" not in result["note"].lower()


# ---------------------------------------------------------------------------
# No OpenAI dependency, no schema change
# ---------------------------------------------------------------------------


def test_no_openai_dependency_in_write_mode_module():
    source = inspect.getsource(dry_run_module)
    assert "openai" not in source.lower()


def test_no_openai_dependency_in_review_ui_page():
    page_path = Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "2b_Review_Allocation_Site_Matches.py"
    source = page_path.read_text(encoding="utf-8")
    assert "openai" not in source.lower()


def test_no_schema_change_local_plan_site_and_site_columns_unchanged():
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
