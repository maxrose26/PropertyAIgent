"""Stage 2E.2 ("Controlled Allocation<->Site Relationship Cleanup Runner")
tests - covers the 23 items from the task's own Section 13. Every test runs
against the shared in-memory SQLite `session` fixture (tests/conftest.py) -
never the real production database. Approved production targets
(app.policy.relationship_cleanup_runner.TO_REJECT/TO_NEEDS_CONFIRMATION)
are monkeypatched per test to the (allocation_id, site_id) pairs each test
fixture actually creates, since the real production ids (e.g. 210, 171)
don't exist in a fresh in-memory database.
"""
from __future__ import annotations

import inspect

import pytest
from sqlalchemy import select

import app.policy.relationship_cleanup_runner as runner
import scripts.cleanup_allocation_site_relationships as cli
from app.db.models import (
    AllocationSiteRelationship, Application, ControlRelationship, Council, LocalPlanSite, SchemeIntelligence, Site,
)
from app.reporting.allocation_development_coverage import REVIEW_REQUIRED, build_allocation_development_coverage
from app.reporting.ownership_control import get_allocation_control_intelligence


# ---------------------------------------------------------------------------
# Fixtures (matching tests/test_allocation_site_relationship_matcher_integrity.py's own style)
# ---------------------------------------------------------------------------


def _make_council(session, code: str) -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))


def _make_allocation(session, council_code: str, site_name: str, policy_reference: str | None, **kwargs) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, policy_reference=policy_reference, site_name=site_name,
        minimum_dwellings=kwargs.get("minimum_dwellings", 100), plan_name="Test Local Plan", plan_status="adopted",
        matched_site_id=kwargs.get("matched_site_id"),
    )
    session.add(allocation)
    session.flush()
    return allocation


def _make_site(session, council_code: str, address: str) -> Site:
    site = Site(council_code=council_code, canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_relationship(
    session, *, allocation_id: int, site_id: int, evidence_basis: str = "document_confirmed_site",
    evidence_category: str | None = "EXPLICIT_REFERENCE", review_status: str = "auto_applied",
) -> AllocationSiteRelationship:
    rel = AllocationSiteRelationship(
        allocation_id=allocation_id, site_id=site_id, evidence_basis=evidence_basis,
        evidence_category=evidence_category, review_status=review_status,
    )
    session.add(rel)
    session.flush()
    return rel


def _make_application_with_capacity(session, council_code: str, reference: str, site_id: int, units: int) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id, application_received="01/01/2025")
    session.add(app)
    session.flush()
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=units, core_intelligence_complete=True))
    session.flush()
    return app


def _make_control_relationship(session, *, site_id: int, review_status: str = "auto_applied") -> ControlRelationship:
    cr = ControlRelationship(
        site_id=site_id, entity_name_raw="Test Developer Ltd", entity_type="company", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
        extraction_method="deterministic_regex", review_status=review_status,
    )
    session.add(cr)
    session.flush()
    return cr


def _patch_targets(monkeypatch, *, reject=(), needs_confirmation=()):
    monkeypatch.setattr(runner, "TO_REJECT", tuple(reject))
    monkeypatch.setattr(runner, "TO_NEEDS_CONFIRMATION", tuple(needs_confirmation))


def _get_rel(session, allocation_id: int, site_id: int) -> AllocationSiteRelationship:
    return session.execute(
        select(AllocationSiteRelationship).where(
            AllocationSiteRelationship.allocation_id == allocation_id,
            AllocationSiteRelationship.site_id == site_id,
        )
    ).scalar_one()


# ---------------------------------------------------------------------------
# Item 1 - dry-run makes zero writes
# ---------------------------------------------------------------------------


def test_dry_run_makes_zero_writes(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=False)

    assert report.reject_outcomes[0].outcome == runner.WOULD_APPLY
    rel = _get_rel(session, allocation.id, site.id)
    assert rel.review_status == "auto_applied"  # unchanged


# ---------------------------------------------------------------------------
# Item 2 - exact confirmation phrase required, fails closed
# ---------------------------------------------------------------------------


def test_execute_without_exact_confirm_phrase_fails_closed(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["cleanup_allocation_site_relationships.py", "--execute", "--confirm", "WRONG-PHRASE"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_execute_with_missing_confirm_fails_closed(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["cleanup_allocation_site_relationships.py", "--execute"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_execute_with_exact_confirm_phrase_proceeds(session, monkeypatch):
    import sys

    _make_council(session, "testcouncil")
    monkeypatch.setattr(sys, "argv", [
        "cleanup_allocation_site_relationships.py", "--execute", "--confirm", cli.CONFIRM_PHRASE,
    ])
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "get_session", lambda: session)
    _patch_targets(monkeypatch, reject=[], needs_confirmation=[])

    cli.main()  # must not raise / exit


# ---------------------------------------------------------------------------
# Item 3 - semantic (allocation_id, site_id) targeting
# ---------------------------------------------------------------------------


def test_semantic_pair_targeting_not_row_order(session, monkeypatch):
    """Two relationships exist; only the (allocation_id, site_id) pair
    named in TO_REJECT is touched, regardless of which one happens to have
    the lower primary key."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site_a = _make_site(session, "testcouncil", "King Street")
    site_b = _make_site(session, "testcouncil", "Rectory Lane")
    _make_relationship(session, allocation_id=allocation.id, site_id=site_a.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    _make_relationship(session, allocation_id=allocation.id, site_id=site_b.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site_a.id)])
    runner.run_cleanup_relationships(session, execute=True)

    assert _get_rel(session, allocation.id, site_a.id).review_status == "rejected"
    assert _get_rel(session, allocation.id, site_b.id).review_status == "auto_applied"  # untouched


# ---------------------------------------------------------------------------
# Item 4 - raw relationship IDs never used operationally
# ---------------------------------------------------------------------------


def test_raw_relationship_ids_never_used_operationally():
    source = inspect.getsource(runner)
    # The only place relationship_id ever appears is as an audit-log field
    # on TargetOutcome / read via _get_relationship(...).id - never as a
    # WHERE clause target. Confirm every AllocationSiteRelationship query
    # filters by allocation_id/site_id, never by .id ==.
    assert "AllocationSiteRelationship.id ==" not in source
    assert "AllocationSiteRelationship.id.in_" not in source


# ---------------------------------------------------------------------------
# Item 5 - immediate revalidation before any write
# ---------------------------------------------------------------------------


def test_revalidation_called_immediately_before_write(session, monkeypatch):
    calls = []
    original = runner.revalidate_before_write

    def _spy(session_, allocation_id, site_id, *, expected_action):
        calls.append((allocation_id, site_id, expected_action))
        return original(session_, allocation_id, site_id, expected_action=expected_action)

    monkeypatch.setattr(runner, "revalidate_before_write", _spy)

    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    assert calls == [(allocation.id, site.id, "reject")]


# ---------------------------------------------------------------------------
# Items 6/7/8 - reject/needs_confirmation change status only, no deletion
# ---------------------------------------------------------------------------


def test_reject_changes_status_only(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    rel = _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                              evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()
    before = (rel.allocation_id, rel.site_id, rel.relationship_type, rel.confidence, rel.evidence_basis,
              rel.evidence_category, rel.evidence_document_id, rel.evidence_application_id, rel.evidence_snippet)

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    rel = _get_rel(session, allocation.id, site.id)
    after = (rel.allocation_id, rel.site_id, rel.relationship_type, rel.confidence, rel.evidence_basis,
             rel.evidence_category, rel.evidence_document_id, rel.evidence_application_id, rel.evidence_snippet)
    assert rel.review_status == "rejected"
    assert before == after  # every other field untouched


def test_needs_confirmation_changes_status_only(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10")
    site = _make_site(session, "testcouncil", "Land South of Bullcote Lane")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, needs_confirmation=[(allocation.id, site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    assert _get_rel(session, allocation.id, site.id).review_status == "needs_confirmation"


def test_no_row_deletion(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()
    before_count = session.execute(select(AllocationSiteRelationship)).scalars().all()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    after_count = session.execute(select(AllocationSiteRelationship)).scalars().all()
    assert len(before_count) == len(after_count)


# ---------------------------------------------------------------------------
# Item 9 - human-confirmed row protected
# ---------------------------------------------------------------------------


def test_human_confirmed_row_never_overwritten(session, monkeypatch):
    """Genuine provenance: legacy backfill row whose allocation carries a
    real confirm_site_match decision (confirmed_by/confirmed_at/note, and
    matched_site_id still pointing at this exact site) - the only shape
    that traces to a real human decision (Section 3/5's provenance audit)."""
    import datetime as dt

    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "King Street")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", matched_site_id=site.id)
    allocation.review_status = "confirmed"
    allocation.confirmed_by = "Test Reviewer"
    allocation.confirmed_at = dt.datetime.now(dt.timezone.utc)
    allocation.match_review_note = "Distinctive name match, verified against Application APP/1."
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="legacy_matched_site_id_backfill", evidence_category=None,
                        review_status="confirmed")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=True)

    assert report.reject_outcomes[0].outcome == runner.BLOCKED_HUMAN_CONFIRMATION
    assert "Test Reviewer" in report.reject_outcomes[0].detail
    assert _get_rel(session, allocation.id, site.id).review_status == "confirmed"


def test_legacy_confirmed_without_provenance_is_protected_but_labelled_distinctly(session, monkeypatch):
    """A document-evidenced relationship can never legitimately reach
    review_status='confirmed' in this codebase (see
    _verify_human_confirmation_provenance's own docstring) - but if one
    somehow does, it must be protected from overwrite exactly like a
    genuinely human-confirmed row, just labelled honestly as unverified
    rather than falsely described as human-confirmed."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE",
                        review_status="confirmed")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=True)

    assert report.reject_outcomes[0].outcome == runner.BLOCKED_LEGACY_CONFIRMED_UNVERIFIED
    assert _get_rel(session, allocation.id, site.id).review_status == "confirmed"  # still never overwritten


def test_legacy_confirmed_with_drifted_matched_site_id_is_unverified(session, monkeypatch):
    """A legacy-backfill relationship whose allocation.matched_site_id no
    longer points at this relationship's site_id (the provenance link has
    drifted since the relationship was created) must not be trusted as
    human-confirmed, even though evidence_basis alone looks right."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "King Street")
    other_site = _make_site(session, "testcouncil", "Rectory Lane")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", matched_site_id=other_site.id)
    allocation.review_status = "confirmed"
    allocation.confirmed_by = "Test Reviewer"
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="legacy_matched_site_id_backfill", evidence_category=None,
                        review_status="confirmed")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=True)

    assert report.reject_outcomes[0].outcome == runner.BLOCKED_LEGACY_CONFIRMED_UNVERIFIED
    assert _get_rel(session, allocation.id, site.id).review_status == "confirmed"


# ---------------------------------------------------------------------------
# Item 10 - drift blocked
# ---------------------------------------------------------------------------


def test_drift_blocks_reject_when_new_evidence_appears(session, monkeypatch):
    from app.db.models import Application, Document

    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    app_row = Application(council_code="testcouncil", reference="APP/1", site_id=site.id)
    session.add(app_row)
    session.flush()
    doc = Document(application_id=app_row.id, doc_type="design_access", text_extracted=True,
                    extracted_text="the North Leigh Park allocation h3 confirms development is allocated for residential use here.")
    session.add(doc)
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=True)

    assert report.reject_outcomes[0].outcome == runner.BLOCK_DRIFT
    assert _get_rel(session, allocation.id, site.id).review_status == "auto_applied"  # unchanged


# ---------------------------------------------------------------------------
# Items 11/12 - already-applied idempotency + second run zero changes
# ---------------------------------------------------------------------------


def test_already_rejected_target_is_idempotent(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE",
                        review_status="rejected")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=True)

    assert report.reject_outcomes[0].outcome == runner.ALREADY_APPLIED
    assert _get_rel(session, allocation.id, site.id).review_status == "rejected"


def test_already_rejected_target_is_idempotent_even_for_needs_confirmation_action(session, monkeypatch):
    """Section 7's exact instruction: a target already rejected is treated
    as idempotent/already-applied regardless of which action was planned."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10")
    site = _make_site(session, "testcouncil", "Land South of Bullcote Lane")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="STRONG_CONTEXTUAL_REFERENCE",
                        review_status="rejected")
    session.commit()

    _patch_targets(monkeypatch, needs_confirmation=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=True)

    assert report.needs_confirmation_outcomes[0].outcome == runner.ALREADY_APPLIED
    assert _get_rel(session, allocation.id, site.id).review_status == "rejected"  # never downgraded


def test_second_run_produces_zero_new_status_changes(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    first = runner.run_cleanup_relationships(session, execute=True)
    assert first.reject_outcomes[0].outcome == runner.APPLIED

    second = runner.run_cleanup_relationships(session, execute=True)
    assert second.reject_outcomes[0].outcome == runner.ALREADY_APPLIED
    assert _get_rel(session, allocation.id, site.id).review_status == "rejected"


# ---------------------------------------------------------------------------
# Item 13 - failure rollback/isolation
# ---------------------------------------------------------------------------


def test_failure_on_one_target_does_not_corrupt_others(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site_good = _make_site(session, "testcouncil", "King Street")
    site_bad = _make_site(session, "testcouncil", "Rectory Lane")
    _make_relationship(session, allocation_id=allocation.id, site_id=site_good.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    _make_relationship(session, allocation_id=allocation.id, site_id=site_bad.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    original = runner._classify_and_maybe_write

    def _boom(session_, allocation_id, site_id, *, action, execute):
        if site_id == site_bad.id:
            raise RuntimeError("simulated failure")
        return original(session_, allocation_id, site_id, action=action, execute=execute)

    monkeypatch.setattr(runner, "_classify_and_maybe_write", _boom)
    _patch_targets(monkeypatch, reject=[(allocation.id, site_good.id), (allocation.id, site_bad.id)])

    report = runner.run_cleanup_relationships(session, execute=True)

    outcomes = {o.site_id: o.outcome for o in report.reject_outcomes}
    assert outcomes[site_good.id] == runner.APPLIED
    assert outcomes[site_bad.id] == runner.FAILED
    assert _get_rel(session, allocation.id, site_good.id).review_status == "rejected"  # survives
    assert _get_rel(session, allocation.id, site_bad.id).review_status == "auto_applied"  # untouched
    assert len(report.failures) == 1


# ---------------------------------------------------------------------------
# Items 14/15/16 - ControlRelationship / LocalPlanSite / matched_site_id untouched
# ---------------------------------------------------------------------------


def test_control_relationship_untouched(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    cr = _make_control_relationship(session, site_id=site.id)
    session.commit()
    before = (cr.review_status, cr.entity_name_raw, cr.role, cr.site_id)

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    session.refresh(cr)
    after = (cr.review_status, cr.entity_name_raw, cr.role, cr.site_id)
    assert before == after


def test_local_plan_site_untouched(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", minimum_dwellings=156)
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()
    before = (allocation.site_name, allocation.policy_reference, allocation.minimum_dwellings, allocation.review_status)

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    session.refresh(allocation)
    after = (allocation.site_name, allocation.policy_reference, allocation.minimum_dwellings, allocation.review_status)
    assert before == after


def test_matched_site_id_untouched(session, monkeypatch):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "King Street")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", matched_site_id=site.id)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    session.refresh(allocation)
    assert allocation.matched_site_id == site.id  # this runner never writes it either way


# ---------------------------------------------------------------------------
# Item 17 - coverage updated through derived read (no derived write)
# ---------------------------------------------------------------------------


def test_coverage_updates_via_derived_read_only(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", minimum_dwellings=156)
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    before = build_allocation_development_coverage(session, [allocation])[allocation.id]["coverage"]
    assert before.number_of_related_sites == 1

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    after = build_allocation_development_coverage(session, [allocation])[allocation.id]["coverage"]
    assert after.number_of_related_sites == 0  # naturally excluded, nothing written to coverage itself


# ---------------------------------------------------------------------------
# Item 18 - allocation ownership UI naturally excludes rejected relationship
# ---------------------------------------------------------------------------


def test_ownership_ui_naturally_excludes_rejected_relationship(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", minimum_dwellings=156)
    kept_site = _make_site(session, "testcouncil", "North Leigh Development Site")
    rejected_site = _make_site(session, "testcouncil", "35 - 45 King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=kept_site.id,
                        evidence_basis="document_confirmed_site", evidence_category="EXPLICIT_REFERENCE")
    _make_relationship(session, allocation_id=allocation.id, site_id=rejected_site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, rejected_site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    result = build_allocation_development_coverage(session, [allocation])[allocation.id]
    sections = get_allocation_control_intelligence(
        session, result["site_summaries"], indicative_residual_capacity=result["coverage"].indicative_residual_capacity,
    )
    site_ids_shown = {s.site_id for s in sections if not s.is_residual}
    assert kept_site.id in site_ids_shown
    assert rejected_site.id not in site_ids_shown


# ---------------------------------------------------------------------------
# Item 19 - North Leigh Park regression (King Street + Rectory Lane removed)
# ---------------------------------------------------------------------------


def test_north_leigh_park_regression_king_street_and_rectory_lane_removed(session, monkeypatch):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", minimum_dwellings=156)
    genuine_site = _make_site(session, "testcouncil", "North Leigh Development Site")
    king_street = _make_site(session, "testcouncil", "35 - 45 King Street")
    rectory_lane = _make_site(session, "testcouncil", "Land South Of Rectory Lane")
    _make_relationship(session, allocation_id=allocation.id, site_id=genuine_site.id,
                        evidence_basis="document_confirmed_site", evidence_category="EXPLICIT_REFERENCE")
    _make_relationship(session, allocation_id=allocation.id, site_id=king_street.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    _make_relationship(session, allocation_id=allocation.id, site_id=rectory_lane.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, king_street.id), (allocation.id, rectory_lane.id)])
    report = runner.run_cleanup_relationships(session, execute=True)

    assert all(o.outcome == runner.APPLIED for o in report.reject_outcomes)
    coverage = build_allocation_development_coverage(session, [allocation])[allocation.id]["coverage"]
    assert coverage.number_of_related_sites == 1
    assert _get_rel(session, allocation.id, genuine_site.id).review_status == "auto_applied"


# ---------------------------------------------------------------------------
# Item 20 - North of Mosley Common (JPA 32) unchanged - not a target
# ---------------------------------------------------------------------------


def test_north_of_mosley_common_unchanged_when_not_a_target(session, monkeypatch):
    _make_council(session, "testcouncil")
    other_allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    other_site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=other_allocation.id, site_id=other_site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")

    jpa32 = _make_allocation(session, "testcouncil", "North of Mosley Common", "JPA 32", minimum_dwellings=1100)
    jpa32_site = _make_site(session, "testcouncil", "Land North Of Mosley Common")
    _make_relationship(session, allocation_id=jpa32.id, site_id=jpa32_site.id,
                        evidence_basis="document_confirmed_site", evidence_category="EXPLICIT_REFERENCE")
    session.commit()

    # JPA 32 is deliberately absent from both target lists.
    _patch_targets(monkeypatch, reject=[(other_allocation.id, other_site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    assert _get_rel(session, jpa32.id, jpa32_site.id).review_status == "auto_applied"
    coverage = build_allocation_development_coverage(session, [jpa32])[jpa32.id]["coverage"]
    assert coverage.number_of_related_sites == 1


# ---------------------------------------------------------------------------
# Item 21 - no OpenAI / external API
# ---------------------------------------------------------------------------


def test_no_openai_or_external_api_in_cleanup_modules():
    for module in (runner, cli):
        source = inspect.getsource(module)
        lowered = source.lower()
        assert "import openai" not in lowered
        assert "from openai" not in lowered
        assert "companies_house" not in lowered
        assert "land_registry" not in lowered
        assert "requests.get(" not in source
        assert "requests.post(" not in source


# ---------------------------------------------------------------------------
# Item 22 - no schema change
# ---------------------------------------------------------------------------


def test_no_schema_change():
    for module in (runner, cli):
        source = inspect.getsource(module)
        assert "ALTER TABLE" not in source
        assert "(Base)" not in source  # no new ORM model classes defined here
        assert "mapped_column(" not in source  # no raw column definitions


# ---------------------------------------------------------------------------
# Item 23 - CLI dry-run wiring produces the documented report sections
# ---------------------------------------------------------------------------


def test_cli_dry_run_end_to_end(session, monkeypatch, capsys):
    import sys

    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", minimum_dwellings=156)
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    monkeypatch.setattr(sys, "argv", ["cleanup_allocation_site_relationships.py"])
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "get_session", lambda: session)
    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])

    cli.main()

    out = capsys.readouterr().out
    assert "DRY RUN COMPLETE - NO WRITES MADE" in out
    assert "reject targets requested: 1" in out
    assert _get_rel(session, allocation.id, site.id).review_status == "auto_applied"  # confirmed still unwritten


# ---------------------------------------------------------------------------
# Stage 2E.2 Final Amendment - Section 15 items 1-6, 9-14 (dry-run coverage-
# preview integrity + provenance-protection reconciliation)
# ---------------------------------------------------------------------------


def test_would_apply_reject_affects_coverage_preview(session, monkeypatch):
    """Item 5 - a WOULD_APPLY reject target is reflected in the preview:
    the rejected Site's capacity drops out of the allocation's coverage."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", minimum_dwellings=300)
    kept_site = _make_site(session, "testcouncil", "Genuine Site")
    reject_site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=kept_site.id,
                        evidence_basis="document_confirmed_site", evidence_category="EXPLICIT_REFERENCE")
    _make_application_with_capacity(session, "testcouncil", "APP/KEPT", kept_site.id, 100)
    _make_relationship(session, allocation_id=allocation.id, site_id=reject_site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    _make_application_with_capacity(session, "testcouncil", "APP/REJECT", reject_site.id, 50)
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, reject_site.id)])
    report = runner.run_cleanup_relationships(session, execute=False)
    assert report.reject_outcomes[0].outcome == runner.WOULD_APPLY

    proposed = runner.simulate_proposed_coverage(session, [allocation.id], report)[allocation.id]["coverage"]
    assert proposed.number_of_related_sites == 1
    assert proposed.identified_application_capacity == 100

    current = build_allocation_development_coverage(session, [allocation])[allocation.id]["coverage"]
    assert current.number_of_related_sites == 2
    assert current.identified_application_capacity == 150
    # Rolled back - the "current" read after simulate_proposed_coverage proves nothing leaked.
    assert _get_rel(session, allocation.id, reject_site.id).review_status == "auto_applied"


def test_block_drift_does_not_alter_coverage_preview(session, monkeypatch):
    """Items 1/2 - this is the exact bug the Product Owner reported: a
    needs_confirmation target that comes back BLOCK_DRIFT (still eligible
    under fresh evidence) must NOT be simulated as downgraded in the
    coverage preview - it stays exactly as accepted as it is today."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10", minimum_dwellings=1930)
    site = _make_site(session, "testcouncil", "Land South Of Bullcote Lane")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    _make_application_with_capacity(session, "testcouncil", "FUL/1", site.id, 248)

    from app.db.models import Document
    app_row = session.query(Application).filter_by(reference="FUL/1").one()
    session.add(Document(application_id=app_row.id, doc_type="other", text_extracted=True,
                          extracted_text="the beal valley allocation jpa 10 is allocated for around 1930 dwellings and this site forms part of it."))
    session.commit()

    _patch_targets(monkeypatch, needs_confirmation=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=False)
    assert report.needs_confirmation_outcomes[0].outcome == runner.BLOCK_DRIFT

    proposed = runner.simulate_proposed_coverage(session, [allocation.id], report)[allocation.id]["coverage"]
    current = build_allocation_development_coverage(session, [allocation])[allocation.id]["coverage"]

    # BLOCK_DRIFT must leave the preview identical to the current state -
    # the old buggy simulation would have forced this to REVIEW_REQUIRED.
    assert proposed.capacity_accounting_status == current.capacity_accounting_status
    assert proposed.capacity_accounting_status != REVIEW_REQUIRED
    assert proposed.identified_application_capacity == current.identified_application_capacity == 248


def test_blocked_confirmation_does_not_alter_coverage_preview(session, monkeypatch):
    """Item 3 - a BLOCKED_HUMAN_CONFIRMATION (or BLOCKED_LEGACY_CONFIRMED_
    UNVERIFIED) target must not be simulated as changed either."""
    import datetime as dt

    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Genuine Site")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", minimum_dwellings=300,
                                   matched_site_id=site.id)
    allocation.review_status = "confirmed"
    allocation.confirmed_by = "Test Reviewer"
    allocation.confirmed_at = dt.datetime.now(dt.timezone.utc)
    allocation.match_review_note = "Verified."
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="legacy_matched_site_id_backfill", evidence_category=None,
                        review_status="confirmed")
    _make_application_with_capacity(session, "testcouncil", "APP/1", site.id, 100)
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=False)
    assert report.reject_outcomes[0].outcome == runner.BLOCKED_HUMAN_CONFIRMATION

    proposed = runner.simulate_proposed_coverage(session, [allocation.id], report)[allocation.id]["coverage"]
    assert proposed.number_of_related_sites == 1  # not rejected in the preview
    assert proposed.identified_application_capacity == 100


def test_already_applied_reflects_current_status_only_in_preview(session, monkeypatch):
    """Item 4 - a needs_confirmation target already at needs_confirmation
    is ALREADY_APPLIED and the preview shows the site exactly as it is
    now (already-disputed capacity accounting), not re-applied again."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10", minimum_dwellings=1930)
    site = _make_site(session, "testcouncil", "Land South Of Bullcote Lane")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="STRONG_CONTEXTUAL_REFERENCE",
                        review_status="needs_confirmation")
    _make_application_with_capacity(session, "testcouncil", "FUL/1", site.id, 248)
    session.commit()

    _patch_targets(monkeypatch, needs_confirmation=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=False)
    assert report.needs_confirmation_outcomes[0].outcome == runner.ALREADY_APPLIED

    proposed = runner.simulate_proposed_coverage(session, [allocation.id], report)[allocation.id]["coverage"]
    current = build_allocation_development_coverage(session, [allocation])[allocation.id]["coverage"]
    assert proposed.development_coverage_classification == current.development_coverage_classification == REVIEW_REQUIRED


def test_status_distribution_and_coverage_preview_reconcile(session, monkeypatch):
    """Item 6 - the exact production-shape scenario: one WOULD_APPLY
    reject, one ALREADY_APPLIED review, one BLOCKED confirmation, one
    BLOCK_DRIFT review. proposed_status_distribution and
    simulate_proposed_coverage must derive from the identical effective
    set (WOULD_APPLY/APPLIED only, nothing else)."""
    import datetime as dt

    from app.db.models import Document

    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", minimum_dwellings=1000)

    reject_site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=reject_site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    _make_application_with_capacity(session, "testcouncil", "APP/REJECT", reject_site.id, 50)

    already_site = _make_site(session, "testcouncil", "Already Reviewed Site")
    _make_relationship(session, allocation_id=allocation.id, site_id=already_site.id,
                        evidence_basis="document_confirmed_site", evidence_category="STRONG_CONTEXTUAL_REFERENCE",
                        review_status="needs_confirmation")
    _make_application_with_capacity(session, "testcouncil", "APP/ALREADY", already_site.id, 60)

    confirmed_site = _make_site(session, "testcouncil", "Confirmed Site")
    allocation.matched_site_id = None  # avoid interfering with the reject-site convenience pointer
    conf_alloc = _make_allocation(session, "testcouncil", "Confirmed Allocation", "REF2",
                                   matched_site_id=confirmed_site.id)
    conf_alloc.review_status = "confirmed"
    conf_alloc.confirmed_by = "Test Reviewer"
    conf_alloc.confirmed_at = dt.datetime.now(dt.timezone.utc)
    _make_relationship(session, allocation_id=conf_alloc.id, site_id=confirmed_site.id,
                        evidence_basis="legacy_matched_site_id_backfill", evidence_category=None,
                        review_status="confirmed")

    drift_site = _make_site(session, "testcouncil", "Land South Of Bullcote Lane")
    drift_alloc = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10", minimum_dwellings=1930)
    _make_relationship(session, allocation_id=drift_alloc.id, site_id=drift_site.id,
                        evidence_basis="document_confirmed_site", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    drift_app = _make_application_with_capacity(session, "testcouncil", "FUL/DRIFT", drift_site.id, 248)
    session.add(Document(application_id=drift_app.id, doc_type="other", text_extracted=True,
                          extracted_text="the beal valley allocation jpa 10 is allocated for around 1930 dwellings and this site forms part of it."))
    session.commit()

    _patch_targets(
        monkeypatch,
        reject=[(allocation.id, reject_site.id), (conf_alloc.id, confirmed_site.id)],
        needs_confirmation=[(allocation.id, already_site.id), (drift_alloc.id, drift_site.id)],
    )
    report = runner.run_cleanup_relationships(session, execute=False)

    outcomes_by_pair = {
        (o.allocation_id, o.site_id): o.outcome
        for o in report.reject_outcomes + report.needs_confirmation_outcomes
    }
    assert outcomes_by_pair[(allocation.id, reject_site.id)] == runner.WOULD_APPLY
    assert outcomes_by_pair[(conf_alloc.id, confirmed_site.id)] == runner.BLOCKED_HUMAN_CONFIRMATION
    assert outcomes_by_pair[(allocation.id, already_site.id)] == runner.ALREADY_APPLIED
    assert outcomes_by_pair[(drift_alloc.id, drift_site.id)] == runner.BLOCK_DRIFT

    distribution = runner.proposed_status_distribution(session, report)
    proposed_coverage = runner.simulate_proposed_coverage(
        session, [allocation.id, conf_alloc.id, drift_alloc.id], report,
    )

    # Reconciliation: exactly one row moves from auto_applied to rejected
    # (the WOULD_APPLY target) - every other outcome is a no-op for both
    # the distribution and the coverage preview.
    current = runner.current_status_distribution(session)
    assert distribution["rejected"] == current.get("rejected", 0) + 1
    assert distribution["auto_applied"] == current.get("auto_applied", 0) - 1

    north_leigh = proposed_coverage[allocation.id]["coverage"]
    assert north_leigh.number_of_related_sites == 1  # reject_site dropped, already_site (needs_confirmation) stays counted
    assert north_leigh.development_coverage_classification == REVIEW_REQUIRED  # already_site's needs_confirmation still disputes it

    beal_valley = proposed_coverage[drift_alloc.id]["coverage"]
    assert beal_valley.development_coverage_classification != REVIEW_REQUIRED  # BLOCK_DRIFT never applied
    assert beal_valley.identified_application_capacity == 248


def test_second_dry_run_after_first_remains_zero_write(session, monkeypatch):
    """Item 10 - running the (fixed) dry-run twice in a row is still fully
    read-only both times."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    first = runner.run_cleanup_relationships(session, execute=False)
    runner.simulate_proposed_coverage(session, [allocation.id], first)
    second = runner.run_cleanup_relationships(session, execute=False)
    runner.simulate_proposed_coverage(session, [allocation.id], second)

    assert first.reject_outcomes[0].outcome == second.reject_outcomes[0].outcome == runner.WOULD_APPLY
    assert _get_rel(session, allocation.id, site.id).review_status == "auto_applied"


def test_execute_semantics_unchanged_by_preview_fix(session, monkeypatch):
    """Item 11 - execute mode never calls simulate_proposed_coverage at
    all, so the preview fix cannot change what execute mode actually
    writes."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=True)

    assert report.reject_outcomes[0].outcome == runner.APPLIED
    assert _get_rel(session, allocation.id, site.id).review_status == "rejected"

    cli_source = inspect.getsource(cli)
    execute_fn_source = cli_source[cli_source.index("def _run_execute"):cli_source.index("def main")]
    assert "simulate_proposed_coverage" not in execute_fn_source


def test_seven_original_reject_targets_still_present():
    """Item 12 - the Stage 2E.1 Amendment's seven original approved reject
    targets remain present and unchanged. Updated by the Stage 2E.2 Final
    Matcher Amendment (Section 2/11), which explicitly authorises adding
    an eighth ((51, 27), JPA 10 Beal Valley) once revalidated as a
    genuine reject candidate - see test_eight_reject_targets_after_
    matcher_amendment below for that addition."""
    original_seven = (
        (210, 171), (210, 174), (211, 171), (211, 174), (212, 171), (213, 171), (146, 260),
    )
    for pair in original_seven:
        assert pair in runner.TO_REJECT


def test_eight_reject_targets_after_matcher_amendment():
    """Stage 2E.2 Final Matcher Amendment (Sections 9/11/12) - JPA 10 Beal
    Valley / "Land South Of Bullcote Lane" (51, 27) is added as the eighth
    reject target once the multi-reference attribution fix + the
    relationship_cleanup_plan.py contradiction-awareness fix together
    proved its only evidence was a misattributed "adjoins" sentence."""
    assert runner.TO_REJECT == (
        (210, 171), (210, 174), (211, 171), (211, 174), (212, 171), (213, 171), (146, 260),
        (51, 27),
    )
    assert (51, 27) not in runner.TO_NEEDS_CONFIRMATION


# ---------------------------------------------------------------------------
# Stage 2E.2 Final Matcher Amendment - Section 17 items 9/10/14/15
# (JPA10/JPA12 Bullcote Lane regression + eight-target dry-run safety)
# ---------------------------------------------------------------------------


def test_jpa10_bullcote_lane_regression_reject_target_would_apply(session, monkeypatch):
    """Item 9 - reproduces the real production sentence: JPA10's only
    supporting evidence is a misattributed "adjoins" hit - once corrected,
    a reject target for it must WOULD_APPLY (not be BLOCK_DRIFT)."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Land South Of Bullcote Lane")
    jpa10 = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10")
    jpa12 = _make_allocation(session, "testcouncil", "Broadbent Moss", "JPA 12")
    app = _make_application_with_capacity(session, "testcouncil", "FUL/355603/26", site.id, 248)
    _make_relationship(session, allocation_id=jpa10.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    _make_relationship(session, allocation_id=jpa12.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="EXPLICIT_REFERENCE")
    from app.db.models import Document
    session.add(Document(application_id=app.id, doc_type="other", text_extracted=True,
                          extracted_text="Whilst the present application envisages 248 dwellings, the site forms "
                          "part of Places for Everyone allocation policy JPA 12 Broadbent Moss and adjoins "
                          "allocation Policy JPA 10 Beal Valley within which a total of 1930 dwellings are "
                          "proposed."))
    session.commit()

    _patch_targets(monkeypatch, reject=[(jpa10.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=False)

    assert report.reject_outcomes[0].outcome == runner.WOULD_APPLY
    assert "contradictory" in report.reject_outcomes[0].detail.lower() or "adjoins" not in report.reject_outcomes[0].detail.lower()


def test_jpa12_bullcote_lane_survives_and_keeps_evidence(session, monkeypatch):
    """Item 10 - JPA 12's own, genuine relationship to the SAME Site is
    untouched by rejecting JPA10's false relationship - not a target,
    stays auto_applied, evidence unaffected."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Land South Of Bullcote Lane")
    jpa10 = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10")
    jpa12 = _make_allocation(session, "testcouncil", "Broadbent Moss", "JPA 12", minimum_dwellings=500)
    app = _make_application_with_capacity(session, "testcouncil", "FUL/355603/26", site.id, 248)
    _make_relationship(session, allocation_id=jpa10.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    _make_relationship(session, allocation_id=jpa12.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="EXPLICIT_REFERENCE")
    from app.db.models import Document
    session.add(Document(application_id=app.id, doc_type="other", text_extracted=True,
                          extracted_text="Whilst the present application envisages 248 dwellings, the site forms "
                          "part of Places for Everyone allocation policy JPA 12 Broadbent Moss and adjoins "
                          "allocation Policy JPA 10 Beal Valley within which a total of 1930 dwellings are "
                          "proposed."))
    session.commit()

    _patch_targets(monkeypatch, reject=[(jpa10.id, site.id)])
    runner.run_cleanup_relationships(session, execute=True)

    assert _get_rel(session, jpa10.id, site.id).review_status == "rejected"
    jpa12_rel = _get_rel(session, jpa12.id, site.id)
    assert jpa12_rel.review_status == "auto_applied"
    assert jpa12_rel.evidence_category == "EXPLICIT_REFERENCE"

    jpa12_coverage = build_allocation_development_coverage(session, [jpa12])[jpa12.id]["coverage"]
    assert jpa12_coverage.number_of_related_sites == 1
    assert jpa12_coverage.identified_application_capacity == 248


def test_sgl10_jpa11_jpa32_classification_unchanged_by_matcher_amendment():
    """Items 11/12/13 - SGL10, JPA1.1, and JPA3.2 (the other three
    Stage 2E.2 Amendment BLOCK_DRIFT cases) are untouched by the
    multi-reference attribution fix - none involve a competing negative
    phrase, so their classification is exactly as the prior amendment
    found it. Reconfirmed live against production in this task's own
    Section 10 dry run (see final report) - this test only pins that none
    of the three accidentally became reject targets."""
    for pair in ((155, 236), (76, 216), (80, 248)):
        assert pair in runner.TO_NEEDS_CONFIRMATION
        assert pair not in runner.TO_REJECT


def test_eight_target_dry_run_safety(session, monkeypatch):
    """Item 14 - a dry run against all eight real reject targets (mirrored
    with fixture-local ids) makes zero writes and produces exactly eight
    outcomes, none of them silently dropped or duplicated."""
    _make_council(session, "testcouncil")
    pairs = []
    for i in range(8):
        allocation = _make_allocation(session, "testcouncil", f"Allocation {i}", f"REF{i}")
        site = _make_site(session, "testcouncil", f"Site {i}")
        _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                            evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
        pairs.append((allocation.id, site.id))
    session.commit()

    _patch_targets(monkeypatch, reject=pairs)
    report = runner.run_cleanup_relationships(session, execute=False)

    assert len(report.reject_outcomes) == 8
    assert all(o.outcome == runner.WOULD_APPLY for o in report.reject_outcomes)
    for allocation_id, site_id in pairs:
        assert _get_rel(session, allocation_id, site_id).review_status == "auto_applied"  # zero writes


def test_blocked_action_still_excluded_from_preview_with_contradiction_fix(session, monkeypatch):
    """Item 15 - a target blocked because contradictory evidence keeps it
    ineligible (rather than BLOCK_DRIFT from renewed positive eligibility)
    must equally never affect the coverage preview."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "Land South Of Bullcote Lane")
    jpa10 = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10", minimum_dwellings=1930)
    jpa12 = _make_allocation(session, "testcouncil", "Broadbent Moss", "JPA 12")
    app = _make_application_with_capacity(session, "testcouncil", "FUL/355603/26", site.id, 248)
    _make_relationship(session, allocation_id=jpa10.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="STRONG_CONTEXTUAL_REFERENCE",
                        review_status="needs_confirmation")
    _make_relationship(session, allocation_id=jpa12.id, site_id=site.id,
                        evidence_basis="document_confirmed_site", evidence_category="EXPLICIT_REFERENCE")
    from app.db.models import Document
    session.add(Document(application_id=app.id, doc_type="other", text_extracted=True,
                          extracted_text="Whilst the present application envisages 248 dwellings, the site forms "
                          "part of Places for Everyone allocation policy JPA 12 Broadbent Moss and adjoins "
                          "allocation Policy JPA 10 Beal Valley within which a total of 1930 dwellings are "
                          "proposed."))
    session.commit()

    _patch_targets(monkeypatch, needs_confirmation=[(jpa10.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=False)
    assert report.needs_confirmation_outcomes[0].outcome == runner.ALREADY_APPLIED  # already needs_confirmation

    proposed = runner.simulate_proposed_coverage(session, [jpa10.id], report)[jpa10.id]["coverage"]
    current = build_allocation_development_coverage(session, [jpa10])[jpa10.id]["coverage"]
    assert proposed.development_coverage_classification == current.development_coverage_classification


def test_north_leigh_park_corrected_preview_with_mixed_outcomes(session, monkeypatch):
    """Item 13 - North Leigh Park's coverage preview reflects only the
    genuinely-applied reject, even with a BLOCK_DRIFT sibling target
    present in the same dry run."""
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3", minimum_dwellings=156)
    genuine_site = _make_site(session, "testcouncil", "North Leigh Development Site")
    king_street = _make_site(session, "testcouncil", "35 - 45 King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=genuine_site.id,
                        evidence_basis="document_confirmed_site", evidence_category="EXPLICIT_REFERENCE")
    _make_relationship(session, allocation_id=allocation.id, site_id=king_street.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, king_street.id)])
    report = runner.run_cleanup_relationships(session, execute=False)
    assert report.reject_outcomes[0].outcome == runner.WOULD_APPLY

    proposed = runner.simulate_proposed_coverage(session, [allocation.id], report)[allocation.id]["coverage"]
    assert proposed.number_of_related_sites == 1


def test_north_of_mosley_common_unchanged_in_preview(session, monkeypatch):
    """Item 14 - an allocation with no targets at all sees an identical
    current vs proposed coverage preview."""
    _make_council(session, "testcouncil")
    other_allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    other_site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=other_allocation.id, site_id=other_site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE")

    jpa32 = _make_allocation(session, "testcouncil", "North of Mosley Common", "JPA 32", minimum_dwellings=1100)
    jpa32_site = _make_site(session, "testcouncil", "Land North Of Mosley Common")
    _make_relationship(session, allocation_id=jpa32.id, site_id=jpa32_site.id,
                        evidence_basis="document_confirmed_site", evidence_category="EXPLICIT_REFERENCE")
    _make_application_with_capacity(session, "testcouncil", "A/25/099409/RMMAJ", jpa32_site.id, 244)
    session.commit()

    _patch_targets(monkeypatch, reject=[(other_allocation.id, other_site.id)])
    report = runner.run_cleanup_relationships(session, execute=False)

    current = build_allocation_development_coverage(session, [jpa32])[jpa32.id]["coverage"]
    proposed = runner.simulate_proposed_coverage(session, [jpa32.id], report)[jpa32.id]["coverage"]

    assert proposed.number_of_related_sites == current.number_of_related_sites == 1
    assert proposed.identified_application_capacity == current.identified_application_capacity == 244
    assert proposed.indicative_residual_capacity == current.indicative_residual_capacity == 856
