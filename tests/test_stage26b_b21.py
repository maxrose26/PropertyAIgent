"""B2.1: synthetic offline presentation/eligibility cases; no historical-cause claims."""
import datetime as dt
from dataclasses import replace
from types import SimpleNamespace as S
from sqlalchemy import event
import pytest
from app.db.models import Application
from app.reporting.planning_freshness import (present_planning_freshness, present_planning_fact_freshness,
    present_operative_planning_freshness, planning_freshness_report_columns)
from app.reporting.scheme_reconciliation import build_operative_planning_facts, planning_facts_for_scope
from app.reporting import allocation_intelligence_summary as ais
from app.reporting.allocation_report import build_allocation_report_context, to_csv_rows
from tests.test_allocation_report import (_make_local_plan, _make_allocation, _make_summary,
    _make_site, _make_relationship, _make_app)
NOW=dt.datetime(2026,10,9,tzinfo=dt.timezone.utc)
OLD=dt.datetime(2026,9,18,5,20,51,tzinfo=dt.timezone.utc)


def application(**kw):
    fields=dict(id=1,reference='SYN/1',council_code='testcouncil',site_id=1,
                status='Awaiting decision',decision=None,decision_issued_date=None,
                status_verified_at=OLD,proposal='Erection of 68 dwellings',estimated_unit_count=68,
                summary_url='https://example.invalid/planning/SYN1')
    fields.update(kw)
    return Application(**fields)


def test_failsworth_prospective_dates_distinct_and_southlink_pending():
    f=present_planning_freshness(application(reference='FUL/355686/26',status='Decided',decision='Refused',
             decision_issued_date='2026-09-25',status_verified_at=dt.datetime(2026,10,8,tzinfo=dt.timezone.utc)),now=NOW)
    assert f.planning_state=='refused' and f.source_fact_date=='2026-09-25'
    assert f.last_successful_verification.date()==dt.date(2026,10,8)
    assert f.freshness=='verified_as_of'
    s=present_planning_freshness(application(reference='FUL/355201/25',status_verified_at=dt.datetime(2026,9,10)),now=NOW)
    assert s.planning_state=='not_yet_decided' and s.source_fact_date is None
    assert s.freshness=='verified_as_of'


@pytest.mark.parametrize('stamp',[None,OLD,NOW+dt.timedelta(days=1)])
def test_legacy_records_never_fabricate_current_verification(stamp):
    a=application(status_verified_at=stamp);f=present_planning_freshness(a,now=NOW)
    assert f.planning_state=='not_yet_decided' and a.status=='Awaiting decision'
    assert f.freshness in {'verification_unavailable','verified_as_of'}
    assert f.freshness!='verified_within_policy'
    assert f.last_successful_verification==stamp


def test_policy_specific_age_and_current_failure_only_exact_reference():
    a=application()
    assert present_planning_freshness(a,now=NOW,cadence_days=7).freshness=='requires_refresh'
    outcome=S(application_reference=a.reference,outcome='fetch_failed')
    f=present_planning_freshness(a,now=NOW,current_outcome=outcome,attempted_at=NOW)
    assert f.freshness=='currently_unverifiable' and f.last_successful_verification==OLD
    outcome.outcome='conflicting_source'
    assert present_planning_freshness(a,now=NOW,current_outcome=outcome,attempted_at=NOW).freshness=='conflicting'
    outcome.application_reference='OTHER'
    with pytest.raises(ValueError):present_planning_freshness(a,now=NOW,current_outcome=outcome,attempted_at=NOW)
    assert present_planning_freshness(a,now=NOW).attempt_visibility=='unavailable'


def test_older_failure_does_not_override_later_success():
    a=application(status_verified_at=NOW)
    f=present_planning_freshness(a,now=NOW,current_outcome=S(application_reference=a.reference,outcome='fetch_failed'),attempted_at=OLD)
    assert f.freshness=='verified_as_of'


def test_committee_resolution_not_issued_permission():
    a=application(status='Committee resolution',decision='Approved subject to S106')
    f=present_planning_freshness(a,now=NOW)
    assert f.planning_state=='committee_resolution_unissued' and f.source_fact_date is None


def test_parent_phase_and_related_dates_do_not_transfer():
    parent=application(id=1,reference='OUT/1',proposal='Outline erection of 500 dwellings',decision='Granted',decision_issued_date='2026-01-01',status_verified_at=OLD)
    child=application(id=2,reference='RM/1',proposal='Reserved matters Phase 1 erection of 68 dwellings pursuant to OUT/1',decision='Granted',decision_issued_date='2026-02-01',status_verified_at=NOW)
    facts=build_operative_planning_facts([parent,child])
    resolved=next(r for r in facts.resolved_applications if r.id==child.id)
    phase=planning_facts_for_scope(facts,resolved.scope_type,resolved.scope_label)
    rows=present_operative_planning_freshness(phase,[parent,child],now=NOW)
    assert rows[0][1]=='RM/1' and rows[0][2].last_successful_verification==NOW
    parent_rows=present_operative_planning_freshness(facts,[parent,child],now=NOW)
    assert parent_rows[0][1]=='OUT/1' and parent_rows[0][2].last_successful_verification==OLD
    # Missing exact source cannot borrow parent's or a duplicate reference's time.
    f=present_planning_fact_freshness(phase.consented_position.planning_status,[parent],now=NOW)
    assert f.last_successful_verification is None and f.freshness=='verification_unavailable'
    impostor=application(id=3,reference='RM/1',status_verified_at=NOW)
    assert present_planning_fact_freshness(phase.consented_position.planning_status,[parent,impostor],now=NOW).last_successful_verification is None


def test_conflicting_planning_fact_has_no_borrowed_date():
    fact=S(source=None,determined=False,state='conflict',value=None)
    f=present_planning_fact_freshness(fact,[application()],now=NOW)
    assert f.freshness=='conflicting' and f.last_successful_verification is None


def test_export_preserves_per_position_dates_and_qualification():
    rows=tuple((ref,ref,present_planning_freshness(application(reference=ref,status_verified_at=stamp),now=NOW))
               for ref,stamp in [('PARENT',OLD),('CHILD',None)])
    columns=planning_freshness_report_columns(rows)
    assert 'PARENT: 2026-09-18' in columns['Planning Verified As Of']
    assert 'CHILD: Not available' in columns['Planning Verified As Of']
    assert 'Successful status verification unavailable' in columns['Planning Qualification']


def allocation_setup(session):
    plan=_make_local_plan(session);allocation=_make_allocation(session,plan.id,minimum_dwellings=300)
    site=_make_site(session);_make_relationship(session,allocation.id,site.id)
    app=_make_app(session,site.id,proposal='Erection of 68 dwellings',status='Awaiting decision',estimated_unit_count=68,status_verified_at=OLD)
    summary=_make_summary(session,allocation.id,headline='Pending scheme intelligence')
    return allocation,app,summary


def test_material_change_withholds_page_report_csv_without_writes_or_models(session,monkeypatch):
    allocation,app,summary=allocation_setup(session)
    monkeypatch.setattr(ais,'generate_allocation_intelligence_summary',lambda *a,**kw:pytest.fail('model generation'))
    assert ais.allocation_narrative_eligibility(summary,ais.build_allocation_context(session,allocation))=='available'
    app.status='Decided';app.decision='Refused';app.decision_issued_date='2026-09-25';session.commit()
    session.expire_all()
    before=summary.headline,summary.context_fingerprint
    assert ais.allocation_narrative_eligibility(summary,ais.build_allocation_context(session,allocation))=='requires_refresh'
    context=build_allocation_report_context(session,[allocation.id]);row=to_csv_rows(context)[0]
    assert not context.entries[0].ai_intelligence.available
    assert row['AI Intelligence Headline']=='' and row['AI Summary Available']=='Requires refresh'
    assert (summary.headline,summary.context_fingerprint)==before and not session.dirty


def test_timestamp_only_does_not_invalidate_narrative(session):
    allocation,app,summary=allocation_setup(session)
    fingerprint=ais.compute_context_fingerprint(ais.build_allocation_context(session,allocation))
    app.status_verified_at=NOW;session.commit()
    assert ais.compute_context_fingerprint(ais.build_allocation_context(session,allocation))==fingerprint
    assert ais.allocation_narrative_eligibility(summary,ais.build_allocation_context(session,allocation))=='available'
    assert build_allocation_report_context(session,[allocation.id]).entries[0].ai_intelligence.available


@pytest.mark.parametrize('fingerprint',[None,'','unrelated'])
def test_unverifiable_narrative_provenance_withheld(session,fingerprint):
    allocation,app,summary=allocation_setup(session);summary.context_fingerprint=fingerprint;session.commit()
    assert ais.allocation_narrative_eligibility(summary,ais.build_allocation_context(session,allocation))=='requires_refresh'
    assert not build_allocation_report_context(session,[allocation.id]).entries[0].ai_intelligence.available


def test_report_batch_context_fingerprint_identical_and_query_count_bounded(session):
    allocation,app,summary=allocation_setup(session)
    def count(ids):
        session.expire_all();queries=[]
        def observe(*args):queries.append(args[2])
        event.listen(session.bind,'before_cursor_execute',observe)
        try:build_allocation_report_context(session,ids)
        finally:event.remove(session.bind,'before_cursor_execute',observe)
        return len(queries)
    one=count([allocation.id]);ids=[allocation.id]
    for i in range(8):
        a=_make_allocation(session,allocation.local_plan_id,policy_reference=f'A{i}')
        site=_make_site(session,address=f'Site {i}');_make_relationship(session,a.id,site.id)
        _make_app(session,site.id,reference=f'BATCH/{i}',status='Awaiting decision')
        _make_summary(session,a.id);ids.append(a.id)
    many=count(ids)
    assert many==one and many<=10,(one,many)


def test_named_phase_missing_scope_cannot_borrow_parent_verification(session):
    from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
    site=_make_site(session)
    _make_app(session,site.id,reference='PARENT/1',proposal='Outline erection of 500 dwellings',decision='Granted',decision_issued_date='2026-01-01',status_verified_at=NOW)
    cards=[{"params":{"site_id":site.id},"phase_code":"1","count_assessment":None}]
    _attach_planning_delivery_matching_facts(session,cards)
    rows=cards[0]['planning_freshness']
    assert rows[0][1] is None and rows[0][2].last_successful_verification is None


def test_prefetched_context_exact_parity_with_real_disputed_control_groups(session):
    from tests.test_allocation_report import _make_control
    from app.reporting.allocation_development_coverage import build_allocation_development_coverage
    from app.reporting.ownership_control import get_allocations_control_intelligence
    allocation,app,summary=allocation_setup(session)
    _make_control(session,site_id=app.site_id,application_id=app.id,entity_name_raw='Accepted Company',role='DEVELOPER',evidence_category='developer_indication')
    disputed=_make_site(session,address='Disputed Site')
    _make_relationship(session,allocation.id,disputed.id,review_status='needs_confirmation')
    second=_make_app(session,disputed.id,reference='DISPUTED/1',status='Awaiting decision',applicant_name_raw='Untrusted Applicant')
    _make_control(session,site_id=disputed.id,application_id=second.id,entity_name_raw='Disputed Company',role='DEVELOPER',evidence_category='developer_indication')
    _make_app(session,app.site_id,reference='VAR/1',status='Awaiting decision',application_category='condition_discharge_or_details')
    original=ais.build_allocation_context(session,allocation)
    entry=build_allocation_development_coverage(session,[allocation])[allocation.id]
    groups=get_allocations_control_intelligence(session,[app.site_id,disputed.id])
    batch=ais.build_allocation_context(session,allocation,coverage_entry=entry,control_groups_by_site=groups)
    assert batch==original
    assert ais.compute_context_fingerprint(batch)==ais.compute_context_fingerprint(original)
    assert any(o.entity_name_raw=='Accepted Company' for o in batch.ownership_entities)
    assert all(o.entity_name_raw!='Disputed Company' for o in batch.ownership_entities)
    assert batch.ownership_review_pending_count==1 and batch.disputed_site_count==1


def test_timestamp_only_actual_buyer_family_subject_explanation_and_fingerprint_invariance(session):
    from dataclasses import asdict
    from app.db.models import SchemeIntelligence
    from app.reporting.buyer_family_feed import build_buyer_opportunity_families
    from app.reporting.opportunity_universe import build_current_opportunity_universe, compute_opportunity_fingerprint
    from app.reporting.mandate_explanation import present_mandate_explanation
    site=_make_site(session)
    app=_make_app(session,site.id,reference='RES/1',proposal='Erection of 68 dwellings',decision='Granted',decision_issued_date='2026-09-25',status_verified_at=OLD)
    app.scheme_intelligence=SchemeIntelligence(total_units_final=68,development_type='houses');session.commit()
    def snapshot():
        families=build_buyer_opportunity_families(session,'nesten_homes',limit=10)
        assert families['families']
        family_view=[(f.family_key,f.representative.subject_key,[(m.subject_key,asdict(m.source['buyer_fit']),asdict(present_mandate_explanation(m.source['buyer_fit'],m.source))) for m in f.members]) for f in families['families']]
        fingerprints=[(r.opportunity_id,compute_opportunity_fingerprint(r.fingerprint_fields)) for r in build_current_opportunity_universe(session)]
        return family_view,fingerprints
    before=snapshot();app.status_verified_at=NOW;session.commit();assert snapshot()==before


def test_named_phase_valid_type_wrong_label_cannot_borrow_verification(session):
    from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
    from app.reporting.scheme_reconciliation import scoped_count_assessment
    site=_make_site(session)
    app=_make_app(session,site.id,reference='PHASE/2',proposal='Reserved matters for Phase 2 erection of 68 dwellings',decision='Granted',decision_issued_date='2026-01-01',status_verified_at=NOW)
    assessment=scoped_count_assessment([app], 'phase', 'Phase 2')
    card={"params":{"site_id":site.id},"phase_code":"1","count_assessment":assessment}
    _attach_planning_delivery_matching_facts(session,[card])
    position=card['planning_freshness'][0]
    assert position[1] is None and position[2].last_successful_verification is None
    assert position[2].freshness=='verification_unavailable'


def test_supporting_application_reads_batch_dashboard_related_subjects(session):
    from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
    sites=[]
    for i in range(9):
        site=_make_site(session,address=f'Batch supporting site {i}')
        _make_app(session,site.id,reference=f'B21/BATCH/{i}',proposal='Erection of 68 dwellings',status_verified_at=NOW)
        sites.append(site.id)
    def count(ids):
        session.expire_all();statements=[]
        def observe(*args): statements.append(args[2])
        event.listen(session.bind,'before_cursor_execute',observe)
        try:
            cards=[{'params':{'site_id':sid}} for sid in ids]
            _attach_planning_delivery_matching_facts(session,cards)
            assert all(c.get('planning_freshness') for c in cards)
        finally:event.remove(session.bind,'before_cursor_execute',observe)
        return len(statements)
    assert count(sites[:1])==count(sites)==2
