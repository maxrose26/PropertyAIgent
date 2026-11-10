"""Closed profiles and real reader projections over synthetic inputs; no source qualification."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from app.ingestion.ledger import DEFAULT_LIMITS,Denied,digest
from app.ingestion.listing_screening import screen_row,RULE_V3
from tests.source_profile_support import selection,registration,audit
from tests.e2e_connection_support import idox_contract,arcus_contract,outer
from tests.test_discovery_four_council_release import API,Memory
from verification.discovery import source_profiles as p, finite_acceptance as f, four_council_release as r, four_council_proof as proof
from verification.ingestion_storage.operational_publication import GitHub,canonical

ROWS=f.manifest('2026-11-01','2026-11-07','PROSPECTIVE')['rows']
EXPECTED={
 'bolton':('IDOX','RECEIVED','paplanning.bolton.gov.uk'),
 'bury':('IDOX','RECEIVED','planning.bury.gov.uk'),
 'manchester':('ARCUS_UI','VALIDATED','arcusbe.manchester.gov.uk'),
 'oldham':('IDOX','RECEIVED','planningpa.oldham.gov.uk'),
 'rochdale':('ARCUS_UI','VALIDATED','account.rochdale.gov.uk'),
 'salford':('ARCUS_UI','VALIDATED','salfordcitycouncil.my.site.com'),
 'stockport':('IDOX','VALIDATED','planning.stockport.gov.uk'),
 'tameside':('IDOX','RECEIVED','publicaccess.tameside.gov.uk'),
 'wigan':('IDOX','RECEIVED','planning.wigan.gov.uk'),
}


@pytest.mark.parametrize('row',ROWS,ids=lambda x:x['council'])
@pytest.mark.parametrize('mode',sorted(p.MODES))
def test_all_nine_profiles_real_reader_projection_and_parent_agree(row,mode,tmp_path):
    reg=registration(selection((row['council'],),mode));profile=reg['manifest']['source_profiles'][0]
    family,basis,host=EXPECTED[row['council']]
    assert (profile['family'],profile['semantics'],profile['host'])==(family,basis,host)
    assert profile['collection_mode']==mode and profile['sha256']==digest({k:v for k,v in profile.items() if k!='sha256'})
    assert profile['execution_budget']==('BROWSER_SOURCE_V2' if family=='ARCUS_UI' else None)
    a=audit(row,mode)
    with proof.manifest_scope(row,profile):proof.validate_audit(a,tuple(row[k] for k in ('council','semantics','start','end')))
    launch=r.Launcher(reg,tmp_path,github=None,memory=None,source=None)
    assert launch.accept(0,a)=='COMPLETE'
    r.validate(reg,checkout=False)
    assert len(canonical(a))<65536 if family=='ARCUS_UI' else len(canonical(a))<512000


@pytest.mark.parametrize('field,value',[
 ('council','wigan'),('destination','https://example.org/'),('collection_mode','OTHER'),
 ('execution_budget',None),('host','example.org'),('validator','OTHER'),('proof','OTHER'),('case','OTHER')])
def test_profile_transplants_and_arbitrary_fields_refused(field,value):
    profile=p.profile(ROWS[2],'SCREENING_METADATA');profile[field]=value
    with pytest.raises((ValueError,KeyError)):p.validate(profile,ROWS[2])
    reg=registration();reg['manifest']['source_profiles'][1][field]=value
    with pytest.raises((ValueError,r.Stop)):r.validate(reg,checkout=False)


@pytest.mark.parametrize('mode',sorted(p.MODES))
@pytest.mark.parametrize('council',('manchester','rochdale','salford'))
def test_probe_supervisor_binds_real_case_mode_and_scope_before_start(council,mode,tmp_path,monkeypatch):
    from verification.direct_reference import instrumented_probe as probe
    row=next(x for x in ROWS if x['council']==council);profile=p.profile(row,mode)
    with proof.manifest_scope(row,profile):
        for case,window,budget,metadata in [(profile['case'],('2026-10-01','2026-10-07'),'BROWSER_SOURCE_V2',False),
            ('discovery_rochdale_ui_window' if council!='rochdale' else 'discovery_manchester_ui_window',tuple(profile['interval']),'BROWSER_SOURCE_V2',False),
            (profile['case'],tuple(profile['interval']),None,False),(profile['case'],tuple(profile['interval']),'BROWSER_SOURCE_V2',True)]:
            with pytest.raises(ValueError,match='PROFILE_PROBE_BINDING'):
                probe.supervised(case,tmp_path/'out',window=window,metadata=metadata,retain_proof=True,execution_budget=budget)


@pytest.mark.parametrize('row',ROWS,ids=lambda x:x['council'])
def test_actual_finite_caller_child_configuration_and_mode_return(row,tmp_path,monkeypatch):
    profile=p.profile(row,'SCREENING_METADATA');expected=audit(row)
    if row['council'] in f.ARCUS:
        from verification.direct_reference import instrumented_probe as probe
        def supervisor(case,path,**kw):
            assert case==profile['case'] and kw==dict(execution_mode='four-council-owner-local',window=tuple(profile['interval']),retain_proof=True,execution_budget='BROWSER_SOURCE_V2')
            assert proof.current_collection_profile()==profile
            path.write_bytes(canonical(expected))
        monkeypatch.setattr(probe,'supervised',supervisor)
    else:
        def child(command,**kw):
            i=command.index('--collection-profile');assert json.loads(command[i+1])==profile
            assert command[command.index('--idox-worker')+1:command.index('--idox-worker')+4]==[row['council'],row['start'],row['end']]
            path=Path(command[-1]);path.write_bytes(canonical(expected));return 0,False
        monkeypatch.setattr(f,'supervise',child)
    result=f.read(row,campaign_scope=row,collection_profile=profile,retain_proof=True,no_transport_retry=True,fixed_four_rows=True,
        execution_mode='four-council-owner-local' if row['council'] in f.ARCUS else None,
        execution_budget='BROWSER_SOURCE_V2' if row['council'] in f.ARCUS else None)
    assert result['collection_profile']==profile
    launch=r.Launcher(registration(selection((row['council'],))),tmp_path,github=None,memory=None,source=None)
    assert launch.accept(0,result)=='COMPLETE'


@pytest.mark.parametrize('row',ROWS,ids=lambda x:x['council'])
def test_metadata_capture_contract_and_v3_input_identity_mode_refused(row):
    a=audit(row);c=row['council'];start,end=map(date.fromisoformat,(row['start'],row['end']))
    contract=arcus_contract(c,start,end,budget='BROWSER_SOURCE_V2') if c in f.ARCUS else idox_contract(c,start,end)
    limits=dict(DEFAULT_LIMITS,worker_seconds=75,source_rss=1536*1024**2)
    receipt=contract.project(a,outer(),limits)
    result=screen_row(receipt['records'][0],rule_version=RULE_V3,council=c)
    assert result['count_assessment']['admission']=='ADMIT_SCHEME'
    a=audit(row,'IDENTITY_ONLY')
    with pytest.raises(Denied,match='SCREENING_COLLECTION_MODE_REQUIRED'):contract.project(a,outer(),limits)
    a=audit(row);a['collection_profile']['collection_mode']='IDENTITY_ONLY'
    with pytest.raises(Denied):contract.project(a,outer(),limits)
    a=audit(row)
    with pytest.raises((Denied,AttributeError)):contract.project(a,None,limits)


@pytest.mark.parametrize('field',('collection_profile','destination','case','execution_budget','assessment_capture'))
def test_source_substitution_refused_by_parent(field,tmp_path):
    row=ROWS[2];reg=registration(selection(('manchester',)));a=audit(row)
    if field=='assessment_capture':a['listing_records'][0].pop(field)
    elif field=='collection_profile':a[field]=p.profile(ROWS[4],'SCREENING_METADATA')
    else:a[field]='OTHER'
    with pytest.raises((r.Stop,ValueError,KeyError)):
        r.Launcher(reg,tmp_path,github=None,memory=None,source=None).accept(0,a)


def test_capacity_preclaim_full_nine_and_two_arcus_refused():
    for councils in (tuple(EXPECTED),('manchester','salford'),('bolton','bury','oldham','stockport')):
        with pytest.raises(r.Stop,match='CAMPAIGN_MANIFEST_OR_CAPACITY'):registration(selection(councils))
    reg=registration();assert len(reg['manifest']['rows'])==3
    from verification.discovery.campaign_manifest import capacity
    cost=capacity(reg['manifest']['rows'],r.SUCCESSOR_V2_LIMITS,profiled=True)
    assert cost['requests']==100 and cost['mixed_source_bytes']==26_971_520 and cost['exported_bytes']==2*1024**2


@pytest.mark.parametrize('row',ROWS,ids=lambda x:x['council'])
def test_continuation_does_not_expand_from_rochdale_or_idox_family(row,tmp_path):
    reg=registration(selection((row['council'],)));launch=r.Launcher(reg,tmp_path,github=None,memory=None,source=None)
    a=audit(row);a.update(completeness='FAILED',applied_interval=None,listing_failure='TimeoutError',listing_records=[],listing_segments=[])
    # A label alone is insufficient, even at the council with a reviewed exception.
    assert launch.local_outcome(0,a,'FAILED') is None


def test_identity_only_cannot_enter_enabled_partial_screening_capture():
    from dataclasses import replace
    row=ROWS[0];a=audit(row,'IDENTITY_ONLY');start,end=map(date.fromisoformat,(row['start'],row['end']))
    contract=replace(idox_contract('bolton',start,end),partial_observation=True)
    with pytest.raises(Denied,match='SCREENING_COLLECTION_MODE_REQUIRED'):
        contract.observe(a,outer(),DEFAULT_LIMITS,observed_at='2026-11-08T00:00:00+00:00')


@pytest.mark.parametrize('council',('manchester','rochdale','salford'))
@pytest.mark.parametrize('kind',('unknown','conflicting','truncated'))
def test_arcus_capture_preserves_uncertain_metadata_through_v3(council,kind):
    from tests.e2e_connection_support import arcus_audit,entry,SCHEME
    row=next(x for x in ROWS if x['council']==council)
    start,end=map(date.fromisoformat,(row['start'],row['end']))
    e=entry('SYNTHETIC/1',None if kind=='unknown' else SCHEME+'x'*9000 if kind=='truncated' else SCHEME)
    if kind=='conflicting':e['both_labels']=True
    a=arcus_audit(council,[e],start,end,budget='BROWSER_SOURCE_V2');a['date_semantics']='VALIDATED'
    a=p.bind_audit(p.profile(row,'SCREENING_METADATA'),a)
    receipt=arcus_contract(council,start,end,budget='BROWSER_SOURCE_V2').project(a,outer(),dict(DEFAULT_LIMITS,worker_seconds=75))
    field=receipt['records'][0]['fields']['proposal']
    assert field['truncated'] if kind=='truncated' else field['state']==('UNKNOWN' if kind=='unknown' else 'CONFLICTING')
    result=screen_row(receipt['records'][0],rule_version=RULE_V3,council=council)
    assert result['count_assessment']['admission']=='RETAIN_UNUSABLE_PROPOSAL'


@pytest.mark.parametrize('council',('manchester','rochdale','salford'))
@pytest.mark.parametrize('mode',sorted(p.MODES))
def test_positive_supervised_command_to_real_probe_config(council,mode,tmp_path,monkeypatch):
    """Synthetic process boundary; real CLI context + probe config before Playwright entry. No browser/network."""
    import asyncio,os,sys
    import psutil
    from verification.direct_reference import instrumented_probe as probe
    from tests.test_discovery_four_council_proof import async_run
    row=next(x for x in ROWS if x['council']==council);profile=p.profile(row,mode)
    expected=audit(row,mode);seen=[]
    class AtBrowserEntry(BaseException):pass
    class BrowserBoundary:
        async def __aenter__(self):raise AtBrowserEntry()
        async def __aexit__(self,*args):pass
    def entry():return BrowserBoundary()
    original_config=p.config
    def config(value):
        result=original_config(value);seen.append(result)
        assert value==profile and result.assessment_metadata==(mode=='SCREENING_METADATA')
        assert result.capture_metadata==(mode=='SCREENING_METADATA')
        return result
    class Child:
        pid=12345;returncode=0
        def poll(self):return 0
        def wait(self,**kw):return 0
    def popen(command,**kwargs):
        assert not any('TOKEN' in k or 'DATABASE' in k for k in kwargs['env'])
        assert json.loads(command[command.index('--collection-profile')+1])==profile
        assert '--metadata' not in command
        # Real main() consumes the same arguments the actual subprocess would receive.
        args=command[command.index('--worker'):]
        with patch.dict(os.environ,kwargs['env'],clear=True),patch.object(sys,'argv',['probe',*args]),patch('playwright.async_api.async_playwright',entry),patch.object(p,'config',config),patch.object(probe.asyncio,'run',async_run):
            with pytest.raises(AtBrowserEntry):probe.main()
        Path(command[command.index('--output')+1]).write_bytes(canonical(expected))
        return Child()
    # Process guard is deliberately simulated here; authentic cgroup proof is hosted separately.
    class Stat:
        def read_text(self):return str(os.getpid())+' rest'
    original_path=probe.Path
    def path_factory(x):return Stat() if str(x)=='/proc/self/stat' else original_path(x)
    path_factory.home=original_path.home
    monkeypatch.setattr(probe,'Path',path_factory)
    monkeypatch.setattr(probe.subprocess,'Popen',popen)
    monkeypatch.setattr(psutil,'Process',lambda pid:type('Process',(),{})())
    monkeypatch.setattr(r,'owner_source_context',lambda budget:None)
    out=tmp_path/'out'
    with proof.manifest_scope(row,profile):
        assert probe.supervised(profile['case'],out,execution_mode='four-council-owner-local',window=tuple(profile['interval']),retain_proof=True,execution_budget='BROWSER_SOURCE_V2')==0
    assert seen and json.loads(out.read_bytes())['collection_profile']==profile


@pytest.mark.parametrize('fault',('none','cancel','publication','accounting','cleanup','outer','profile','expiry'))
def test_profiled_launcher_publication_and_safety_boundaries(tmp_path,monkeypatch,fault):
    reg=registration();api=API(reg);memory=Memory(tmp_path);calls=[];holder={}
    from verification.discovery.outer_evidence import outer_supervisor
    class Source:
        last_outer=None
        def run(self,index,check):
            calls.append(index)
            if fault=='cancel':api.ref_moved=True
            if fault=='expiry':holder['launch'].wall=lambda:r.stamp(reg['expires_at'])
            check()
            value=audit(reg['manifest']['rows'][index]);closure=dict(source_group_closed=True,child_reaped=True,failures=[])
            self.last_outer=outer_supervisor(exit_code=0,elapsed_seconds=.01,closure=closure,peak_owned_rss=100,live_owned_survivors=0,deadline_seconds=79)
            if fault=='accounting':value['resource']['requests_attempted']=None
            if fault=='cleanup':closure['source_group_closed']=False
            if fault=='outer':self.last_outer=None
            if fault=='profile':value['collection_profile']['collection_mode']='IDENTITY_ONLY'
            return value,closure
    source=Source()
    monkeypatch.setattr('psutil.Process',lambda:type('Process',(),{'children':lambda self,recursive:[]})())
    github=GitHub(lambda *_:None,lambda:holder['launch'].deadline(),runner=api.runner,bound=320)
    launch=r.Launcher(reg,tmp_path,github=github,memory=memory,source=source);holder['launch']=launch
    if fault=='publication':api.lost=True
    out=launch.execute()
    if fault=='none':
        assert calls==[0,1,2] and out['status']=='MANIFEST_OBSERVATIONS_COMPLETE'
        assert len(out['results'])==3 and all(x['outer_supervisor']['cleanup']=='CLOSED' for x in out['results'])
    else:
        assert len(calls)<=1 and out['status']=='STOP_RECONCILE_NO_RETRY'
    assert out['database_connections']==out['application_writes']==0 and not out['coverage_advance']


@pytest.mark.parametrize('row',ROWS,ids=lambda x:x['council'])
def test_real_registration_worker_selects_profile_and_budget(row,tmp_path,monkeypatch):
    import os
    reg=registration(selection((row['council'],)));path=tmp_path/'registration';path.write_bytes(canonical(reg))
    group=tmp_path/'source';group.mkdir();(group/'cgroup.procs').touch()
    calls=[]
    def read(actual,**kw):
        assert actual==row and kw['collection_profile']==reg['manifest']['source_profiles'][0]
        assert kw['execution_budget']==('BROWSER_SOURCE_V2' if row['council'] in f.ARCUS else None)
        calls.append(1);return audit(row)
    monkeypatch.setattr(r,'owner_source_context',lambda budget:None)
    monkeypatch.setattr(f,'read',read)
    r.worker(0,tmp_path/'out',group,campaign_registration=path,campaign_registration_sha256=r.sha(path.read_bytes()))
    assert calls==[1] and json.loads((tmp_path/'out').read_bytes())['collection_profile']==reg['manifest']['source_profiles'][0]
    # Temporary cgroup.procs here is an argument-wiring double, never kernel evidence.


@pytest.mark.parametrize('council,local,code',[
    ('rochdale','timeout','ROCHDALE_RESULT_MARKER_TIMEOUT'),
    ('tameside','timeout','IDOX_SEARCH_OR_SORT_TIMEOUT'),
    ('oldham','timeout','IDOX_SEARCH_OR_SORT_TIMEOUT'),
    ('oldham','selector','OLDHAM_SORT_SELECTOR_ABSENT')])
def test_exact_existing_continuation_predicates_survive_profile_selection(council,local,code,tmp_path):
    from tests.campaign_release_support import audit as old_audit
    row=next(x for x in ROWS if x['council']==council);profile=p.profile(row,'SCREENING_METADATA')
    value=p.bind_audit(profile,old_audit(row,local=local))
    reg=registration(selection((council,)));launch=r.Launcher(reg,tmp_path,github=None,memory=None,source=None)
    state=launch.accept(0,value)
    assert state in {'UNKNOWN','FAILED'} and launch.local_outcome(0,value,state)==code


@pytest.mark.parametrize('row',ROWS,ids=lambda x:x['council'])
def test_wrong_destination_in_records_refuses(row):
    value=audit(row);key='listing_records' if row['council'] in f.ARCUS else 'records'
    value[key][0]['source_url']='https://example.org/record'
    with pytest.raises(ValueError):p.validate_audit(value['collection_profile'],value)


@pytest.mark.parametrize('kind',('unknown_state','missing_date','wrong_date','wrong_key'))
def test_unsupported_idox_metadata_shape_refuses_parent(kind,tmp_path):
    row=ROWS[0];value=audit(row);record=value['records'][0]
    if kind=='unknown_state':record['fields']['proposal']['state']='INVENTED'
    elif kind=='missing_date':record['fields'].pop('received_date')
    elif kind=='wrong_date':record['fields']['received_date']['value']='Thu 01 Jan 2026'
    else:record['source_key']='OTHER'
    with pytest.raises((r.Stop,ValueError,KeyError)):
        r.Launcher(registration(selection(('bolton',))),tmp_path,github=None,memory=None,source=None).accept(0,value)

def test_28_day_nine_council_partition_fits_only_separate_source_only_packages():
    """Prove bounded reuse, not operational 28-day collection or SQL authority."""
    from verification.discovery import campaign_manifest as campaign
    plan=f.manifest('2026-10-01','2026-10-28','PROSPECTIVE')
    arcus=[i for i,row in enumerate(plan['rows']) if row['council'] in f.ARCUS]
    idox=[i for i,row in enumerate(plan['rows']) if row['council'] not in f.ARCUS]
    assert len(plan['rows'])==36 and len(arcus)==12 and len(idox)==24
    checked=set()
    for index in range(12):
        ordinals=sorted([arcus[index],*idox[2*index:2*index+2]])
        payload=dict(finite_manifest=plan,finite_manifest_sha256=f.digest(plan),
                     selected_ordinals=ordinals,collection_mode='SCREENING_METADATA')
        rows=campaign.select(payload,profiled=True)
        assert len(rows)==3 and sum(row['council'] in f.ARCUS for row in rows)==1
        limits=campaign.capacity(rows,r.SUCCESSOR_V2_LIMITS,profiled=True)
        assert limits['requests']==100 and limits['observations']==3
        reg=registration(payload)
        assert reg['manifest']['rows']==rows and reg['manifest']['persistence'] is False
        checked.update(ordinals)
    assert checked==set(range(36))
    full=dict(finite_manifest=plan,finite_manifest_sha256=f.digest(plan),
              selected_ordinals=list(range(36)),collection_mode='SCREENING_METADATA')
    with pytest.raises(r.Stop,match='CAMPAIGN_MANIFEST_OR_CAPACITY'):
        registration(full)


def test_initial_two_slot_packages_cover_nine_councils_including_bolton_without_authority():
    from verification.discovery import campaign_manifest as campaign
    plan=f.manifest('2026-10-01','2026-10-28','PROSPECTIVE')
    result=campaign.initial_two_slot_packages(plan,f.digest(plan))
    assert result['version']==campaign.INITIAL_TWO_SLOT_VERSION
    assert result['window']==['2026-10-01','2026-10-28']
    assert len(result['packages'])==20
    assert sum(len(p['selected_ordinals'])==1 for p in result['packages'])==4
    assert all(result[k] is False for k in ('sql_issuer_qualified','source_qualified',
                                           'initial_capture_authorised','operationally_usable'))
    indexes=[i for pkg in result['packages'] for i in pkg['selected_ordinals']]
    assert sorted(indexes)==list(range(36)) and len(set(indexes))==36
    seen={c:0 for c in f.SEMANTICS}
    for pkg in result['packages']:
        assert 1<=len(pkg['selected_ordinals'])<=2
        assert pkg['reservation']['observations']==len(pkg['selected_ordinals'])
        rows=[plan['rows'][i] for i in pkg['selected_ordinals']]
        assert len({row['end'] for row in rows})==1
        assert len({row['council'] for row in rows})==len(rows)
        assert pkg['reservation']['requests']<=100
        for i in pkg['selected_ordinals']:
            row=plan['rows'][i]
            assert (date.fromisoformat(row['end'])-date.fromisoformat(row['start'])).days==6
            seen[row['council']]+=1
    assert seen=={c:4 for c in f.SEMANTICS}
    assert seen['bolton']==4 and 'trafford' not in seen


@pytest.mark.parametrize('fault',['wrong_hash','missing_bolton','duplicate_scope',
                                   'wrong_semantics','too_short','wrong_purpose','trafford'])
def test_initial_two_slot_packages_fail_closed_on_unreviewed_manifest(fault):
    from verification.discovery import campaign_manifest as campaign
    plan=f.manifest('2026-10-01','2026-10-28','PROSPECTIVE')
    expected=f.digest(plan)
    if fault=='wrong_hash':expected='0'*64
    elif fault=='missing_bolton':plan['rows']=[r for r in plan['rows'] if r['council']!='bolton']
    elif fault=='duplicate_scope':plan['rows'][1]=dict(plan['rows'][0])
    elif fault=='wrong_semantics':plan['rows'][0]['semantics']='INVALID'
    elif fault=='too_short':plan=f.manifest('2026-10-02','2026-10-28','PROSPECTIVE')
    elif fault=='wrong_purpose':plan=f.manifest('2026-10-01','2026-10-28','BACKFILL_AUDIT')
    else:plan['rows'][0]['council']='trafford'
    with pytest.raises(ValueError,match='INITIAL_28_MANIFEST_UNVERIFIED'):
        campaign.initial_two_slot_packages(plan,expected)



def test_shutdown_gap_offline_plan_all_ten_with_57_day_window_and_no_authority():
    """Actual 10 Nov scope; shape proof is NOT a database/council outcome."""
    from datetime import datetime,timezone,timedelta
    from verification.discovery import campaign_manifest as campaign
    value=campaign.shutdown_gap_source_packages(datetime(2026,11,10,12,4,tzinfo=timezone.utc))
    assert value['version']==campaign.SHUTDOWN_GAP_SOURCE_VERSION
    assert value['fallback_start']=='2026-09-15' and value['endpoint_date']=='2026-11-10'
    assert value['total_date_scopes']==90 and value['nine_source_shape_scopes']==81
    assert value['trafford_unqualified_scopes']==9 and len(value['windows'])==9
    assert len(value['required_councils'])==10
    assert sum(len(x['packages']) for x in value['windows'])==45
    assert value['windows'][-1]['start']==value['windows'][-1]['end']=='2026-11-10'
    assert sum(len(x['packages'][-1]['selected_ordinals'])==1 for x in value['windows'])==9
    assert all(value[k] is False for k in ('fallback_is_verified_shutdown',
        'earlier_proven_gaps_reconciled','sql_issuer_qualified','source_qualified',
        'collection_authorised','stored_records_verified','entire_day_coverage_proven'))
    previous=date(2026,9,14)
    for window in value['windows']:
        start,end=map(date.fromisoformat,(window['start'],window['end']))
        assert start==previous+timedelta(days=1) and 0<=(end-start).days<=6
        assert window['finite_manifest']['purpose']=='SUSPENSION_CATCHUP'
        assert f.digest(window['finite_manifest'])==window['finite_manifest_sha256']
        assert window['end_day_incomplete']==(end==date(2026,11,10))
        seen=[]
        for package in window['packages']:
            payload=dict(finite_manifest=window['finite_manifest'],
                finite_manifest_sha256=window['finite_manifest_sha256'],
                selected_ordinals=package['selected_ordinals'],
                collection_mode='SCREENING_METADATA')
            rows=__import__('verification.discovery.campaign_manifest',fromlist=['select']).select(payload,profiled=True)
            assert len(rows)<=2 and len({r['council'] for r in rows})==len(rows)
            assert package['reservation']['requests']<=100
            seen.extend(row['council'] for row in rows)
        assert sorted(seen)==sorted(f.SEMANTICS)
        tenth=window['unqualified_tenth']
        assert tenth['council']=='trafford' and tenth['status']=='SOURCE_CONTRACT_AND_SQL_SCOPE_UNQUALIFIED'
        assert (tenth['start'],tenth['end'])==(window['start'],window['end'])
        previous=end
    assert previous==date(2026,11,10)


def test_shutdown_gap_rolls_endpoint_and_does_not_silently_advance_older_manifest():
    from datetime import datetime,timezone
    from verification.discovery import campaign_manifest as campaign
    a=campaign.shutdown_gap_source_packages(datetime(2026,11,10,12,tzinfo=timezone.utc))
    b=campaign.shutdown_gap_source_packages(datetime(2026,11,11,12,tzinfo=timezone.utc))
    assert a['windows'][:-1]==b['windows'][:-1]
    assert a['windows'][-1]['end']=='2026-11-10' and b['windows'][-1]['end']=='2026-11-11'
    assert a['windows'][-1]['finite_manifest_sha256']!=b['windows'][-1]['finite_manifest_sha256']
    assert b['total_date_scopes']==a['total_date_scopes']
    assert b['entire_day_coverage_proven'] is False


@pytest.mark.parametrize('clock',[
    None,'2026-11-10',date(2026,11,10)])
def test_shutdown_gap_rejects_non_datetime_clock(clock):
    from verification.discovery import campaign_manifest as campaign
    with pytest.raises(ValueError,match='SHUTDOWN_AWARE_CLOCK_REQUIRED'):
        campaign.shutdown_gap_source_packages(clock)


def test_shutdown_gap_rejects_naive_and_earlier_clock_and_handles_london_date():
    from datetime import datetime,timezone
    from verification.discovery import campaign_manifest as campaign
    for clock,reason in [(datetime(2026,11,10), 'SHUTDOWN_AWARE_CLOCK_REQUIRED'),
                         (datetime(2026,9,14,12,tzinfo=timezone.utc), 'SHUTDOWN_DATE_BEFORE_FALLBACK')]:
        with pytest.raises(ValueError,match=reason):
            campaign.shutdown_gap_source_packages(clock)
    # UTC can still be 10 November while Europe/London has entered 11 Nov in summer.
    summer=campaign.shutdown_gap_source_packages(datetime(2026,9,14,23,30,tzinfo=timezone.utc))
    assert summer['endpoint_date']=='2026-09-15'
    assert summer['total_date_scopes']==10 and summer['trafford_unqualified_scopes']==1


def test_shutdown_gap_blocks_unreviewed_registry_expansion(monkeypatch):
    from datetime import datetime,timezone
    from verification.discovery import campaign_manifest as campaign
    with monkeypatch.context() as m:
        m.setattr(f,'SEMANTICS',dict(f.SEMANTICS,trafford='RECEIVED'))
        with pytest.raises(ValueError,match='SHUTDOWN_SOURCE_REGISTRY_CHANGED'):
            campaign.shutdown_gap_source_packages(datetime(2026,11,10,tzinfo=timezone.utc))
