"""Current-application AH may not inherit a sibling's old count or legal label."""
from dataclasses import replace
from types import SimpleNamespace
from app.db.models import Application, SchemeIntelligence, Site
from app.policy.ah_assessment import AHAssessment, AHClaim
from app.policy.buyer_matching import (build_planning_delivery_matching_facts_from_operative,
    build_planning_delivery_matching_facts, B2MatchingContext, PLANNING_DELIVERY)
from app.reporting.scheme_reconciliation import build_operative_planning_facts
from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet, UNKNOWN


def _apps(session, prior_count=0):
    site=Site(council_code='testcouncil', canonical_address='scope-test', display_address='Scope test')
    session.add(site);session.flush()
    apps=[]
    for ref,date,count,decision in [('DC/095922','Sun 01 Jan 2023',prior_count,'Withdrawn'),('DC/098428','Wed 01 Jan 2025',None,None)]:
        app=Application(site_id=site.id,council_code='testcouncil',reference=ref,
            proposal='Erection of 82 dwellings',application_received=date,decision=decision,
            status=decision or 'Under consideration')
        session.add(app);session.flush()
        app.scheme_intelligence=SchemeIntelligence(application_id=app.id,core_intelligence_complete=True,
            total_units_final=82, affordable_units_final=count,
            affordable_percentage_final=0 if count==0 else None,
            affordable_housing_status='legally_secured' if count is not None else None,
            affordable_tenure_split_final='Prior shared ownership' if count is not None else None)
        apps.append(app)
    session.commit();return site,apps


def test_matching_current_unknown_does_not_inherit_prior_zero_or_large_count(session):
    site,apps=_apps(session)
    facts=build_planning_delivery_matching_facts_from_operative(build_operative_planning_facts(apps),apps)
    assert facts.affordable_unit_count is None
    assert facts.affordable_percentage is None and not facts.affordable_percentage_trusted
    apps[0].scheme_intelligence.affordable_units_final=147
    facts=build_planning_delivery_matching_facts_from_operative(build_operative_planning_facts(apps),apps)
    assert facts.affordable_unit_count is None


def test_feed_matching_facts_use_current_scope_and_do_not_mutate_prior(session):
    site,apps=_apps(session)
    cards=[{'params':{'site_id':str(site.id)}}]
    _attach_planning_delivery_matching_facts(session,cards)
    assert cards[0]['matching_facts'].affordable_unit_count is None
    assert apps[0].scheme_intelligence.affordable_units_final==0
    assert not session.dirty


def test_packet_ignores_legacy_fingerprint_count_and_sibling_legal_status(session):
    site,apps=_apps(session)
    legacy=build_planning_delivery_matching_facts(apps[0].scheme_intelligence)
    assert legacy.affordable_unit_count==0  # historical fingerprint construction is untouched
    opportunity=SimpleNamespace(opportunity_id=f'planning_delivery:site:{site.id}',
        opportunity_type=PLANNING_DELIVERY,matching_facts=legacy)
    packet=build_opportunity_intelligence_packet(session,opportunity,
        context=B2MatchingContext(council_code='testcouncil'))
    assert packet.affordable_units.state==UNKNOWN
    assert packet.affordable_percentage.state==UNKNOWN
    assert packet.affordable_housing_status.state==UNKNOWN
    assert apps[0].scheme_intelligence.affordable_units_final==0
    assert not session.dirty


def test_qualified_exact_same_application_can_enter_point_matching_contract(session):
    site,apps=_apps(session)
    current=apps[1]
    current.scheme_intelligence.affordable_units_final=72
    operative=build_operative_planning_facts(apps)
    position=operative.affordable_housing.active_whole_site
    assert position and position.application_reference==current.reference
    claim=AHClaim(value=72,qualifier='exact',state='verified',application_reference=current.reference,
        scope_type='whole_site',scope_label='Whole scheme',document_id='local-source',
        passage='72 affordable homes',document_date='2025-01-01')
    position=replace(position,assessment=AHAssessment(count=claim))
    operative=replace(operative,affordable_housing=replace(operative.affordable_housing,active_whole_site=position))
    facts=build_planning_delivery_matching_facts_from_operative(operative,apps)
    assert facts.affordable_unit_count==72
    assert facts.affordable_percentage is None


def test_bound_is_not_fabricated_into_point_only_buyer_fit_or_legacy_unknown_zero(session):
    site,apps=_apps(session)
    current=apps[1]
    current.scheme_intelligence.affordable_units_final=72
    operative=build_operative_planning_facts(apps)
    position=operative.affordable_housing.active_whole_site
    claim=AHClaim(lower=70,qualifier='at_least',state='estimated',application_reference=current.reference,
        scope_type='whole_site',scope_label='Whole scheme',document_id='local-source',passage='At least 70 affordable homes')
    assessment=AHAssessment(count=claim)
    assert assessment.search(minimum=70)=='likely_meets'
    assert assessment.search(maximum=100)=='investigate'
    position=replace(position,assessment=assessment)
    operative=replace(operative,affordable_housing=replace(operative.affordable_housing,active_whole_site=position))
    assert build_planning_delivery_matching_facts_from_operative(operative,apps).affordable_unit_count is None


def test_live_hyde_shape_retains_old_zero_without_current_numeric_signal(session):
    from app.reporting.scheme_reconciliation import resolve_operative_filter_facts
    site,apps=_apps(session)
    for a in apps:
        a.decision='Objection (Consult with Neighbour Auth)';a.status='Unknown';a.application_type=None
    apps[0].application_received='Thu 22 May 2025'
    apps[1].application_received='Tue 24 Feb 2026'
    session.delete(apps[1].scheme_intelligence);apps[1].scheme_intelligence=None;session.flush()
    operative=build_operative_planning_facts(apps)
    result=resolve_operative_filter_facts(operative)
    assert result.affordable_assessment.count.application_reference=='DC/098428'
    assert result.affordable_assessment.count.value is None
    assert result.affordable_assessment.search(maximum=0)=='unknown'
    assert result.affordable_assessment.search(minimum=50)=='unknown'
    assert operative.affordable_housing.active_whole_site.application_reference=='DC/095922'
    assert operative.affordable_housing.active_whole_site.units==0


def test_embedded_other_application_claim_and_cross_council_identity_rejected(session):
    from app.reporting.scheme_reconciliation import resolve_operative_filter_facts
    site,apps=_apps(session)
    apps[1].scheme_intelligence.affordable_units_final=72
    operative=build_operative_planning_facts(apps)
    p=operative.affordable_housing.active_whole_site
    wrong=AHClaim(value=72,qualifier='exact',state='verified',application_reference=apps[0].reference,
        scope_type='whole_site',scope_label='Whole scheme',document_id='x',passage='72 homes')
    changed=replace(operative,affordable_housing=replace(operative.affordable_housing,
        active_whole_site=replace(p,assessment=AHAssessment(count=wrong))))
    assert resolve_operative_filter_facts(changed).affordable_assessment.count.value is None
    apps[0].council_code='other-council'
    assert resolve_operative_filter_facts(operative).affordable_assessment.count.value is None


def test_explicit_current_nonzero_stays_separate_from_old_consent_zero(session):
    from app.reporting.scheme_reconciliation import resolve_operative_filter_facts
    site,apps=_apps(session)
    apps[0].decision='Granted';apps[0].status='Decided'
    apps[1].scheme_intelligence.affordable_units_final=72
    operative=build_operative_planning_facts(apps)
    assessment=resolve_operative_filter_facts(operative,application_reference=apps[1].reference).affordable_assessment
    assert assessment.count.application_reference==apps[1].reference and assessment.count.value==72
    assert assessment.search(minimum=50)=='unknown'  # still legacy, not source-qualified
    assert operative.affordable_housing.whole_site.units==0


def test_actual_hyde_objection_unknown_no_current_intelligence_shape(session):
    site,apps=_apps(session)
    prior,current=apps
    prior.status=current.status='Unknown'
    prior.decision=current.decision='Objection (Consult with Neighbour Auth)'
    prior.application_received='2025-05-22'
    current.application_received='2026-02-24'
    prior.application_type=current.application_type=None
    prior.application_category=current.application_category='full'
    prior.scheme_intelligence.total_units_final=440
    prior.proposal='Residential development of 440 homes'
    current.proposal='Residential development of 440 homes'  # synthetic substantive proposal; not an inspected portal quote
    session.delete(current.scheme_intelligence)
    session.commit();session.expire_all()
    assert current.scheme_intelligence is None
    cards=[{'params':{'site_id':str(site.id)}}]
    _attach_planning_delivery_matching_facts(session,cards)
    assert cards[0]['matching_facts'].affordable_unit_count is None
    legacy=build_planning_delivery_matching_facts(prior.scheme_intelligence)
    assert legacy.affordable_unit_count==0
    opportunity=SimpleNamespace(opportunity_id=f'planning_delivery:site:{site.id}',opportunity_type=PLANNING_DELIVERY,matching_facts=legacy)
    packet=build_opportunity_intelligence_packet(session,opportunity,context=B2MatchingContext(council_code='testcouncil'))
    assert packet.affordable_units.state==UNKNOWN
    assert packet.affordable_percentage.state==UNKNOWN
    assert packet.affordable_housing_status.state==UNKNOWN
    assert prior.scheme_intelligence.affordable_units_final==0


def test_exact_component_is_not_a_whole_scheme_point_for_buyer_maximum(session):
    site,apps=_apps(session)
    apps[1].scheme_intelligence.affordable_units_final=72
    operative=build_operative_planning_facts(apps)
    position=operative.affordable_housing.active_whole_site
    claim=AHClaim(value=72,qualifier='exact',state='verified',application_reference=apps[1].reference,
        scope_type='component',scope_label='Retirement apartments',document_id='local',passage='72 retirement apartments')
    assessment=AHAssessment(count=claim)
    assert assessment.search(minimum=70)=='meets'
    assert assessment.search(maximum=75)=='investigate'
    position=replace(position,assessment=assessment)
    operative=replace(operative,affordable_housing=replace(operative.affordable_housing,active_whole_site=position))
    assert build_planning_delivery_matching_facts_from_operative(operative,apps).affordable_unit_count is None


def test_feed_caches_by_application_and_phase_not_just_site(session):
    site,apps=_apps(session)
    cards=[{'params':{'site_id':str(site.id)},'application_reference':a.reference} for a in apps]
    cards.append({'params':{'site_id':str(site.id)},'application_reference':apps[1].reference,'phase_code':'Phase A'})
    _attach_planning_delivery_matching_facts(session,cards)
    assert cards[0]['matching_facts'] is not cards[1]['matching_facts']
    assert cards[1]['matching_facts'] is not cards[2]['matching_facts']
    assert all(c['matching_facts'].affordable_unit_count is None for c in cards)
    assert apps[0].scheme_intelligence.affordable_units_final==0


def test_qualified_historical_claim_stays_investigation_not_current_buyer_signal(session):
    site,apps=_apps(session,prior_count=72)
    operative=build_operative_planning_facts(apps)
    historical=operative.affordable_housing.historical[0]
    claim=AHClaim(value=72,qualifier='exact',state='verified',application_reference=apps[0].reference,
        scope_type='whole_site',scope_label='Whole scheme',document_id='prior-source',passage='72 homes')
    historical=replace(historical,assessment=AHAssessment(count=claim))
    operative=replace(operative,affordable_housing=replace(operative.affordable_housing,historical=(historical,)))
    facts=build_planning_delivery_matching_facts_from_operative(operative,apps,application_reference=apps[0].reference)
    assert facts.affordable_unit_count is None
    assert historical.assessment.count.value==72


def test_same_application_reviewed_revision_remains_selectable_and_unreviewed_ambiguity_does_not(session):
    from app.reporting.scheme_reconciliation import resolve_operative_filter_facts
    site,apps=_apps(session)
    current=apps[1];current.scheme_intelligence.affordable_units_final=74
    operative=build_operative_planning_facts(apps);position=operative.affordable_housing.active_whole_site
    claim=AHClaim(value=74,qualifier='exact',state='verified',application_reference=current.reference,
        scope_type='whole_site',scope_label='Whole scheme',source_url='https://example.invalid/revised.pdf',
        document_date='2025-03-01',passage='Revised provision: 74 affordable homes')
    old=replace(claim,value=71,document_date='2025-01-01',source_url='https://example.invalid/original.pdf')
    selected=AHAssessment(count=claim,source_claims=({'value':71,'application':current.reference},
        {'value':74,'application':current.reference}),relationships=({'action':'supersedes','from':'earlier71','to':'revised74','reason':'Reviewed same-application revision'},))
    revised=replace(position,scope_label='AH source selection',assessment=selected,units=74)
    summary=replace(operative.affordable_housing,source_positions=(revised,))
    result=resolve_operative_filter_facts(replace(operative,affordable_housing=summary))
    assert result.affordable_assessment.count.value==74
    assert result.affordable_assessment.search(minimum=74)=='meets'
    assert result.affordable_assessment.relationships==selected.relationships
    ambiguous=replace(summary,source_positions=(revised,replace(revised,assessment=AHAssessment(count=old),units=71)))
    assert resolve_operative_filter_facts(replace(operative,affordable_housing=ambiguous)).affordable_assessment.count.value is None


def test_narrow_packet_without_application_identity_does_not_borrow_site_status(session):
    site,apps=_apps(session)
    apps[1].scheme_intelligence.affordable_units_final=72
    apps[1].scheme_intelligence.affordable_housing_status='legally_secured'
    session.commit()
    legacy=build_planning_delivery_matching_facts(apps[1].scheme_intelligence)
    opportunity=SimpleNamespace(opportunity_id=f'planning_delivery:recent_permission:{site.id}',opportunity_type=PLANNING_DELIVERY,matching_facts=legacy)
    packet=build_opportunity_intelligence_packet(session,opportunity,context=B2MatchingContext(council_code='testcouncil'))
    assert packet.affordable_units.state==UNKNOWN
    assert packet.affordable_housing_status.state==UNKNOWN
