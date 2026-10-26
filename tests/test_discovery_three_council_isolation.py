"""Fixed successor through the real launcher/publisher; reconstructed sources only."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from verification.discovery import four_council_release as r
from verification.ingestion_storage.operational_publication import GitHub, canonical
from tests.test_discovery_four_council_release import API, Memory, audit
from tests.test_discovery_four_council_proof import (
    SCOPES, bodies, config, RenderedPage, async_run,
)


def registration():
    issued=r.now()-timedelta(minutes=1)
    return r.render('three-council-offline-fixture','a'*40,'b'*40,'1'*40,
        issued.isoformat(),(issued+timedelta(hours=2)).isoformat(),released=True,successor=True)


def local_audit(index,kind=None,*,execution_budget=None):
    """Actual source parsing/timeout classification; no real council markup.

    execution_budget: run the budgeted reader (fresh observation deadline) and declare it as the
    probe does; the untruncated result-marker timeout must remain the typed local timeout."""
    if index==1:
        value=audit(1)
        from verification.discovery import arcus_ui_window as ui
        from verification.discovery.arcus_ui_config import ROCHDALE,dated_config
        from verification.direct_reference.instrumented_probe import classify_ui_enumeration
        cfg=dated_config(ROCHDALE,'2026-10-08','2026-10-14')
        budgeted={}
        if execution_budget is not None:
            from verification.discovery.execution_budget import Deadline,select
            budget=select(execution_budget)
            budgeted=dict(budget=budget,deadline=Deadline(budget['worker_seconds']-budget['finalisation_reserve_seconds']))
            value.update(execution_budget=execution_budget,stage_timings={'NAVIGATION':1000})
        async_run(ui.enumerate_ui(RenderedPage(cfg),value,asyncio.Event(),cfg,retain_proof=True,**budgeted))
        classify_ui_enumeration(value,lambda reason:(_ for _ in ()).throw(AssertionError(reason)))
        value.update(containment_accounting_verified=True,requested_origins=['https://'+cfg.host],
            navigated_origins=['https://'+cfg.host],navigation_mismatch=None,
            blocked_actions=[],blocked_action_metadata=[],blocked_posts=0)
        return value
    from verification.discovery import idox_window
    from tests.test_discovery_idox_window import Response
    scope=next(s for s in SCOPES if s[0]==r.ROWS[index]['council'])
    values=bodies(scope)
    if kind=='selector':values=[values[0],b'<html><form></form></html>']
    elif kind=='search':values=values[:1]+[requests.Timeout('PRIVATE_CREDENTIAL_AND_URL')]
    else:values=values[:2]+[requests.Timeout('PRIVATE_CREDENTIAL_AND_URL')]
    values=iter(values)
    class Session:
        closed=False
        def __enter__(self):return self
        def __exit__(self,*_):self.closed=True
        def mount(self,*_):pass
        def request(self,*_,**kwargs):
            assert kwargs['timeout']==(3,8)
            value=next(values)
            if isinstance(value,Exception):raise value
            return Response(value)
    session=Session()
    with patch.object(idox_window.requests,'Session',return_value=session),patch.object(idox_window.time,'sleep',lambda _:None):
        value=idox_window.live(config(scope),retain_proof=True)
    assert session.closed and 'PRIVATE_CREDENTIAL' not in json.dumps(value)
    return value


class Source:
    def __init__(self):self.calls=[];self.values={};self.after=None;self.owned=True
    def run(self,index,check):
        self.calls.append(index);check()
        if self.after:self.after(index)
        return deepcopy(self.values.get(index) or audit(index)),dict(source_group_closed=self.owned,supervised_seconds=.01)


@pytest.fixture
def world(tmp_path,monkeypatch):
    reg=registration();api=API(reg);memory=Memory(tmp_path);source=Source();holder={};events=[]
    monkeypatch.setattr('psutil.Process',lambda:type('Process',(),{'children':lambda self,recursive:[]})())
    github=GitHub(lambda *x:events.append(x),lambda:holder['launch'].deadline(),runner=api.runner,bound=320)
    launch=r.Launcher(reg,tmp_path,github=github,memory=memory,source=source,emit=lambda *x:events.append(x));holder['launch']=launch
    return reg,api,memory,source,launch,events


def test_exact_successor_binding_default_off_and_four_unchanged():
    reg=registration();r.validate(reg,checkout=False)
    assert [x['council'] for x in reg['manifest']['rows']]==['rochdale','tameside','oldham']
    assert reg['stop_treatment']==r.SUCCESSOR_PERMIT
    assert r.manifest()['stop_policy']=='STOP_ALL_NON_COMPLETE' and len(r.manifest()['rows'])==4
    for key,value in r.SUCCESSOR_LIMITS.items():
        assert value<=r.LIMITS[key]
    inactive=r.render(reg['release_id'],reg['revision'],reg['tree'],reg['evidence_head'],reg['issued_at'],reg['expires_at'],successor=True)
    with pytest.raises(r.Stop):r.validate(inactive,checkout=False)
    for key in ('manifest','version','stop_treatment','dependencies','packages'):
        changed=deepcopy(reg);changed[key]=r.VERSION if key=='version' else {} if isinstance(reg[key],dict) else 'WRONG'
        with pytest.raises(r.Stop):r.validate(changed,checkout=False)


def test_three_complete_no_bury_and_fresh_consumed_marker(world):
    reg,api,memory,source,launch,_=world;out=launch.execute()
    assert source.calls==[1,2,3] and out['status']=='THREE_COMPLETE'
    assert out['continued_after_source_local']==[] and not out['not_attempted']
    assert out['database_connections']==out['application_writes']==0 and out['coverage_advance'] is False
    assert launch.publication_calls==46


@pytest.mark.parametrize('index,kind,code',[(1,None,r.LOCAL_OUTCOMES[0]),
    (2,'search',r.LOCAL_OUTCOMES[1]),(2,'sort',r.LOCAL_OUTCOMES[1]),
    (3,'search',r.LOCAL_OUTCOMES[1]),(3,'sort',r.LOCAL_OUTCOMES[1]),(3,'selector',r.LOCAL_OUTCOMES[2])])
def test_every_allowed_failure_continues_without_rewriting_outcome(world,index,kind,code):
    reg,api,memory,source,launch,events=world;source.values[index]=local_audit(index,kind)
    original=deepcopy(source.values[index]);out=launch.execute()
    assert source.calls==[1,2,3] and out['status']=='OBSERVATIONS_FINISHED_WITH_GAPS'
    receipt=out['results'][index-1]
    assert receipt['continuation_code']==code and receipt['source_outcome']=='FAILED'
    assert receipt['outcome']==('UNKNOWN' if index==1 else 'FAILED')
    assert out['coverage_advance'] is False and source.values[index]==original
    assert out['accounting_complete'] and launch.publication_calls==46
    if index<3:
        event=next(x for x in events if x[0]=='source_local_continuation')
        head=event[1]['publication_head'];tree=api.trees[api.commits[head]]
        assert reg['directory']+f'/slot-{index-1}/source.json' in tree


def test_three_contained_failures_keep_all_gaps(world):
    *_,source,launch,events=world
    source.values={1:local_audit(1),2:local_audit(2,'sort'),3:local_audit(3,'selector')}
    out=launch.execute();assert source.calls==[1,2,3]
    assert [x['outcome'] for x in out['results']]==['UNKNOWN','FAILED','FAILED']
    assert out['status']=='OBSERVATIONS_FINISHED_WITH_GAPS' and len(out['continued_after_source_local'])==2


@pytest.mark.parametrize('index',[1,2,3])
@pytest.mark.parametrize('change',[
    lambda a:a.update(accounting_complete=False),
    lambda a:a.update(safety_failure=True),
    lambda a:a.update(safety_events=['IDENTITY_MISMATCH']),
    lambda a:a.update(applied_interval=['2026-10-01','2026-10-07']),
    lambda a:a.update(proof_retention_failure='PROOF_RETENTION_FAILED'),
    lambda a:a.update(requested_interval=['2026-01-01','2026-01-02']),
    lambda a:a.update(cleanup='UNCERTAIN'),
    lambda a:a['retained_proof']['events'][0].update(sanitised_sha256='0'*64),
    lambda a:a.update(failure='UNCLASSIFIED_FAILURE'),
])
def test_global_or_unclassified_failure_stops_at_each_position(world,index,change):
    *_,source,launch,events=world;a=local_audit(index);change(a);source.values[index]=a
    out=launch.execute();assert source.calls==list(range(1,index+1))
    assert out['status']=='STOP_RECONCILE_NO_RETRY' and len(out['not_attempted'])==3-index


@pytest.mark.parametrize('index',[1,2,3])
def test_generic_unknown_and_incomplete_do_not_continue(world,index):
    *_,source,launch,events=world
    a=audit(index);a.update(completeness='INCOMPLETE',capped=True)
    source.values[index]=a;out=launch.execute()
    assert source.calls==list(range(1,index+1)) and out['status']=='STOP_RECONCILE_NO_RETRY'


@pytest.mark.parametrize('kind',['timeout','lost_ack','bad_readback'])
@pytest.mark.parametrize('index',[1,2,3])
def test_failed_publication_never_allows_next_source(world,index,kind):
    reg,api,memory,source,launch,_=world;source.values[index]=local_audit(index)
    original=api.runner
    def transport(command,**kwargs):
        if source.calls and source.calls[-1]==index:
            if kind=='timeout' and command[3]=='POST':raise TimeoutError()
            if kind=='lost_ack':api.lost=True
        result=original(command,**kwargs)
        if kind=='bad_readback' and command[3]=='GET' and f'/slot-{index-1}/' in command[4]:
            return __import__('subprocess').CompletedProcess(command,0,canonical({'sha':'0'*40,'content':''}),b'')
        return result
    launch.github.runner=transport;out=launch.execute()
    assert source.calls==list(range(1,index+1)) and out['status']=='STOP_RECONCILE_NO_RETRY'
    if kind=='lost_ack':
        patch_at=max(i for i,x in enumerate(api.calls) if x[0]=='PATCH')
        assert not any(m!='GET' for m,p in api.calls[patch_at+1:])


@pytest.mark.parametrize('fault',['owned','children','socket','containment'])
def test_per_slot_closure_before_continuation(world,monkeypatch,fault):
    *_,source,launch,events=world;source.values[1]=local_audit(1)
    if fault=='owned':source.owned=False
    elif fault=='children':monkeypatch.setattr('psutil.Process',lambda:type('Process',(),{'children':lambda self,recursive:[object()]})())
    elif fault=='socket':monkeypatch.setattr(r,'sockets',lambda:launch.baseline|{'socket:new'})
    else:launch.memory.snapshot=lambda:(_ for _ in ()).throw(r.Stop('MEMORY_ENFORCEMENT_LOST'))
    out=launch.execute();assert len(source.calls)<=1 and out['status']=='STOP_RECONCILE_NO_RETRY'


@pytest.mark.parametrize('contained',[False,True])
@pytest.mark.parametrize('fault',['cancel','expiry','expiry_soon','active','export','requests','time'])
def test_between_slot_control_and_budget_failure_stops(world,fault,contained):
    reg,api,memory,source,launch,_=world
    if contained:source.values[1]=local_audit(1)
    original=launch.publish
    def publish(files,part):
        original(files,part)
        if part=='slot-0':
            if fault=='cancel':api.ref_moved=True
            elif fault=='expiry':launch.wall=lambda:r.stamp(reg['expires_at'])
            elif fault=='expiry_soon':launch.wall=lambda:r.stamp(reg['expires_at'])-timedelta(seconds=60)
            elif fault=='active':launch.active_seconds=121
            elif fault=='export':launch.exported=launch.limits['exported_bytes']
            elif fault=='requests':launch.github.requests=310
            else:launch.clock=lambda:launch.start+1000
    launch.publish=publish;out=launch.execute()
    assert source.calls==[1] and out['status']=='STOP_RECONCILE_NO_RETRY'


def test_consumed_history_and_inactive_authority_never_start_source(world):
    reg,api,memory,source,launch,_=world
    api.trees['2'*40][reg['directory']+'/claim/consumed.json']=api.blob(b'{}')
    out=launch.execute();assert source.calls==[] and out['reason']=='REGISTRATION_ALREADY_CONSUMED'


def test_successor_source_command_maps_rochdale_and_rejects_bury(tmp_path,monkeypatch):
    memory=Memory(tmp_path);memory.source=tmp_path/'source';source=r.Source(memory,registration(),tmp_path)
    command=source.command(1,tmp_path/'out')
    assert command[4]=='1' and command[-1]=='--three-council-successor'
    with pytest.raises(r.Stop):r.worker(0,tmp_path/'out',memory.source,successor=True)


def test_final_gap_status_is_not_success_and_closes(world,tmp_path):
    *_,source,launch,events=world;source.values[1]=local_audit(1)
    out=launch.execute();journal=r.Journal(tmp_path/'events.jsonl')
    assert r.finish(launch,journal,out,tmp_path)==1
    final=json.loads((tmp_path/'final-result.json').read_bytes())
    assert final['status']=='OBSERVATIONS_FINISHED_WITH_GAPS' and final['cleanup']=='CLOSED'
    assert final['final_publication']=='VERIFIED' and final['accounting']['publication_requests']==58


@pytest.mark.parametrize('index,kind,field,value',[
    (1,None,'containment_accounting_verified',False),
    (1,None,'supervisor_limit_hit',True),
    (1,None,'criteria_control_timeout',{'code':'SOURCE_LOCAL_CRITERIA_CONTROL_TIMEOUT','operation':'VALID_FROM','exception_contract':'PLAYWRIGHT_LOCATOR_TIMEOUT_V1'}),
    (1,None,'listing_failure','UNCLASSIFIED_FAILURE'),
    (1,None,'measured_public_ui_posts',0),
    (2,'sort','proof_failure_operation','PAGE_REQUEST'),
    (2,'search','failure','TimeoutError'),
    (3,'selector','proof_failure_operation','SEARCH_REQUEST'),
])
def test_allowlist_near_misses_never_continue(world,index,kind,field,value):
    *_,source,launch,events=world;a=local_audit(index,kind);a[field]=value;source.values[index]=a
    out=launch.execute();assert source.calls==list(range(1,index+1))
    assert out['status']=='STOP_RECONCILE_NO_RETRY'


@pytest.mark.parametrize('fault',['criteria','retry','budget','diagnostic','provenance'])
def test_rehashed_proof_or_transport_inconsistency_stops(world,fault):
    *_,source,launch,events=world;a=local_audit(3,'selector');p=a['retained_proof']
    if fault=='criteria':
        p['events'][1]['sanitised_evidence']['criteria']['Start']={'controls':1,'matches_requested':False}
        p['events'][1]['sanitised_sha256']=r.sha(canonical(p['events'][1]['sanitised_evidence']))
        p['events_sha256']=r.sha(canonical(p['events']))
    elif fault=='retry':a['resource']['retries']=1
    elif fault=='budget':a['resource']['budget_exhaustion']=True
    elif fault=='diagnostic':a['failure_diagnostic']['body_sha256']='0'*64
    else:a['response_provenance'][-1]['body_sha256']='0'*64
    source.values[3]=a;out=launch.execute()
    assert out['status']=='STOP_RECONCILE_NO_RETRY'
    if fault=='provenance':assert len(out['results'])==2 and out['returned_evidence'][-1]['export']=='HELD_UNVALIDATED'
    else:assert out['results'][-1]['outcome']=='FAILED'


def test_missing_owned_closure_remains_uncertain_in_final_receipt(world,tmp_path):
    *_,source,launch,events=world;source.owned=False;source.values[1]=local_audit(1)
    out=launch.execute();journal=r.Journal(tmp_path/'events.jsonl');r.finish(launch,journal,out,tmp_path)
    assert json.loads((tmp_path/'final-result.json').read_bytes())['cleanup']=='UNCERTAIN'


@pytest.mark.parametrize('fault',['none','local-all','local-0','local-1','local-2','unavailable'])
def test_complete_cli_successor_without_source_contact(tmp_path,fault):
    import os,subprocess,sys
    root=tmp_path/fault;env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');env.pop('DATABASE_URL',None)
    p=subprocess.run([sys.executable,'-m','tests.four_council_release_fixture_cli','--successor',
        '--root',str(root),'--fault',fault],env=env,capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stdout+'\n'+p.stderr
    final=json.loads((root/'rehearsal.json').read_bytes())
    assert final['cleanup']=='CLOSED' and final['database_connections']==final['application_writes']==0
    assert final['accounting']['github_requests']<=320 and final['accounting']['publication_requests']<=80
    if fault!='unavailable':
        assert [x['scope']['council'] for x in final['results']]==['rochdale','tameside','oldham']


@pytest.mark.parametrize('field,value',[
    ('requested_origins',['https://wrong.invalid']),('navigated_origins',[]),
    ('navigation_mismatch',{}),('blocked_actions',['PRIVATE']),
    ('blocked_action_metadata',[{}]),('blocked_posts',1),
])
def test_existing_arcus_security_fields_cannot_be_bypassed(world,field,value):
    *_,source,launch,events=world;a=local_audit(1);a[field]=value;source.values[1]=a
    out=launch.execute();assert source.calls==[1] and out['status']=='STOP_RECONCILE_NO_RETRY'


@pytest.mark.parametrize('index',[2,3])
@pytest.mark.parametrize('count',[1,2])
def test_sort_timeout_with_rehashed_mismatched_or_ambiguous_criteria_stops(world,index,count):
    *_,source,launch,events=world;a=local_audit(index,'sort');p=a['retained_proof'];e=p['events'][1]
    e['sanitised_evidence']['criteria']['Start']={'controls':count,'matches_requested':False}
    e['sanitised_sha256']=r.sha(canonical(e['sanitised_evidence']));p['events_sha256']=r.sha(canonical(p['events']))
    source.values[index]=a;out=launch.execute()
    assert source.calls==list(range(1,index+1)) and out['status']=='STOP_RECONCILE_NO_RETRY'


@pytest.mark.parametrize('field,value',[('council','bury'),('reference','RECEIVED:2026-01-01:2026-01-02'),
    ('adapter','arcus'),('outcome','COMPLETE'),('redirects',1)])
def test_local_resource_identity_and_accounting_consistency(world,field,value):
    *_,source,launch,events=world;a=local_audit(2,'sort');a['resource'][field]=value;source.values[2]=a
    out=launch.execute();assert source.calls==[1,2] and out['status']=='STOP_RECONCILE_NO_RETRY'


@pytest.mark.parametrize('kind',['sort','selector'])
@pytest.mark.parametrize('field,value',[('version',2),('body_bytes',-1),('body_sha256','0'*64),
    ('shape_available',None)])
def test_malformed_or_contradictory_diagnostic_refuses(world,kind,field,value):
    *_,source,launch,events=world;a=local_audit(3,kind);a['failure_diagnostic'][field]=value;source.values[3]=a
    out=launch.execute();assert out['status']=='STOP_RECONCILE_NO_RETRY'
    assert out['results'][-1]['continuation_code'] is None


def test_selector_diagnostic_counts_must_match_retained_projection(world):
    *_,source,launch,events=world;a=local_audit(3,'selector');a['failure_diagnostic']['counts']['forms']=2;source.values[3]=a
    out=launch.execute();assert out['results'][-1]['continuation_code'] is None


@pytest.mark.parametrize('index',[1,2,3])
def test_explicit_failed_source_cannot_be_promoted_by_complete_count_proof(world,index):
    *_,source,launch,events=world;a=audit(index);a['completeness']='FAILED';source.values[index]=a
    out=launch.execute();assert source.calls==list(range(1,index+1))
    assert out['status']=='STOP_RECONCILE_NO_RETRY'
    assert out['reason']==('STOP_ALL_NON_COMPLETE' if index==1 else 'SOURCE_OUTCOME_CONFLICT')


@pytest.mark.parametrize('fault',['children','socket'])
def test_complete_slot_publication_cannot_leave_survivors_before_next(world,monkeypatch,fault):
    *_,source,launch,events=world;original=launch.publish
    def publish(files,part):
        original(files,part)
        if part=='slot-0':
            if fault=='children':monkeypatch.setattr('psutil.Process',lambda:type('Process',(),{'children':lambda self,recursive:[object()]})())
            else:monkeypatch.setattr(r,'sockets',lambda:launch.baseline|{'socket:new'})
    launch.publish=publish;out=launch.execute()
    assert source.calls==[1] and out['status']=='STOP_RECONCILE_NO_RETRY'
