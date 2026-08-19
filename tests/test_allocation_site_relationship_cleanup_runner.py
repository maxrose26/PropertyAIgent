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
from app.db.models import AllocationSiteRelationship, ControlRelationship, Council, LocalPlanSite, Site
from app.reporting.allocation_development_coverage import build_allocation_development_coverage
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
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id,
                        evidence_basis="multiple_document_supported_sites", evidence_category="STRONG_CONTEXTUAL_REFERENCE",
                        review_status="confirmed")
    session.commit()

    _patch_targets(monkeypatch, reject=[(allocation.id, site.id)])
    report = runner.run_cleanup_relationships(session, execute=True)

    assert report.reject_outcomes[0].outcome == runner.BLOCKED_HUMAN_CONFIRMATION
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
