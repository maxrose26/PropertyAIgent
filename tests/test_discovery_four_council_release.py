"""Actual fixed launcher, real publisher algorithm; synthetic source/control APIs.

No council, production DB or GitHub contact. Fixture markup is reconstructed.
"""
import base64
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
import pytest
from verification.discovery import four_council_release as r
from verification.ingestion_storage.operational_publication import GitHub, canonical
from tests.test_discovery_four_council_proof import run, bodies, SCOPES, async_run
from tests.test_discovery_four_council_proof import RenderedPage
import asyncio
from verification.discovery import arcus_ui_window as ui
from verification.discovery.arcus_ui_config import ROCHDALE, dated_config


def registration():
    issued=r.now()-timedelta(minutes=1)
    return r.render('four-council-fixture-once','a'*40,'b'*40,'1'*40,issued.isoformat(),(issued+timedelta(hours=2)).isoformat(),released=True)

class Memory:
    """Contract double only; actual cgroup proof is a separate native CI test."""
    def __init__(self,root):
        self.root=root/'memory';self.root.mkdir();self.closed=False
        (self.root/'memory.max').write_text(str(1536*1024**2))
        (self.root/'memory.swap.max').write_text('0')
    def snapshot(self):
        assert not self.closed
        return {'fixture':True}
    def close(self):
        self.closed=True
        return dict(owned_groups_removed=True,owned_survivors=0,memory={'fixture':True})

class API:
    """Git-shaped fixture executing the existing publisher including CAS/readback."""
    def __init__(self,registration):
        self.head=registration['evidence_head'];self.trees={'2'*40:{}};self.commits={self.head:'2'*40};self.blobs={};self.calls=[]
        self.fail=None;self.lost=False;self.ref_moved=False
        raw=canonical(r.control(registration,enabled=True));blob=self.blob(raw)
        self.trees['2'*40][registration['directory']+'/control.json']=blob
    def blob(self,raw):
        sha=__import__('hashlib').sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        self.blobs[sha]={'sha':sha,'content':base64.b64encode(raw).decode()};return sha
    def runner(self,command,*,input=None,**kwargs):
        assert command[:2]==['gh','api'];method=command[3];path=command[4]
        self.calls.append((method,path))
        assert not any(s in path for s in ('secrets','database','password','token'))
        if self.fail and self.fail(method,path):raise TimeoutError('DO_NOT_EXPORT_ARBITRARY_EXCEPTION')
        body=json.loads(input) if input else None;prefix=r.REPO
        if method=='GET' and '/git/ref/heads/' in path:value={'object':{'sha':'f'*40 if self.ref_moved else self.head}}
        elif method=='GET' and '/git/commits/' in path:value={'tree':{'sha':self.commits[path.split('/')[-1]]}}
        elif method=='GET' and '/contents/' in path:
            relative=path.split('/contents/')[1].split('?')[0];ref=path.split('?ref=')[1]
            tree=self.trees[self.commits[ref]]
            if relative not in tree:return subprocess.CompletedProcess(command,1,b'',b'not found (HTTP 404)')
            value=self.blobs[tree[relative]]
        elif method=='POST' and path.endswith('/git/blobs'):
            raw=base64.b64decode(body['content']);value={'sha':self.blob(raw)}
        elif method=='POST' and path.endswith('/git/trees'):
            tree=deepcopy(self.trees[body['base_tree']]);tree.update({e['path']:e['sha'] for e in body['tree']});key=r.sha(canonical(tree))[:40];self.trees[key]=tree;value={'sha':key}
        elif method=='POST' and path.endswith('/git/commits'):
            key=r.sha(canonical(body))[:40];self.commits[key]=body['tree'];value={'sha':key}
        elif method=='PATCH':
            assert body['force'] is False
            self.head=body['sha']
            if self.lost:raise TimeoutError('lost ACK after real fixture ref effect')
            value={}
        else:raise AssertionError((method,path))
        return subprocess.CompletedProcess(command,0,canonical(value),b'')


def audit(index, *, complete=True):
    if index!=1:
        scope=next(s for s in SCOPES if s[0]==r.ROWS[index]['council'])
        from tests.test_discovery_four_council_proof import config
        from tests.test_discovery_idox_window import Response
        from verification.discovery import idox_window
        responses=iter(bodies(scope,pager=complete))
        class Session:
            closed=False
            def __enter__(self):return self
            def __exit__(self,*_):self.closed=True
            def mount(self,*_):pass
            def request(self,*args,**kwargs):return Response(next(responses))
        session=Session()
        with patch.object(idox_window.requests,'Session',return_value=session),patch.object(idox_window.time,'sleep',lambda _:None):
            value=idox_window.live(config(scope),retain_proof=True)
        assert session.closed
        return value
    cfg=dated_config(ROCHDALE,'2026-10-08','2026-10-14')
    from tests.test_discovery_arcus_ui import card
    async def cards(page,config):
        values=[]
        for i in range(2):
            c=card(f'TEST/{i}',key='a'*15+f'{i:03d}',valid='08/10/2026')
            c['links'][0]['href']=c['links'][0]['href'].replace('arcusbe.manchester.gov.uk',config.host)
            values.append(c)
        return values
    a=dict(case='discovery_rochdale_ui_window',destination=cfg.destination,persistence=False,
        requested_interval=[cfg.start,cfg.end],date_semantics='VALIDATED',
        requests=2,decoded_bytes=1000,encoded_bytes=1000,outbound_payload_bytes=0,
        cleanup='CONTEXT_BROWSER_CLOSED',process_cleanup='CLOSED',live_owned_survivors=0,supervisor_seconds=.01,
        supervisor_limit_hit=False,pages=1,navigations=1,public_ui_posts=1,measured_public_ui_posts=1,
        failure=None,safety_failure=False,safety_events=[],accounting_complete=True)
    with patch.object(ui,'read_cards',cards):
        async_run(ui.enumerate_ui(RenderedPage(cfg,failure=False,total=2),a,asyncio.Event(),cfg,retain_proof=True))
    return a

class FixtureSource:
    def __init__(self,api,*,unknown=False,fault=None):self.calls=[];self.api=api;self.unknown=unknown;self.fault=fault
    def run(self,index,check):
        self.calls.append(index)
        if self.fault==('cancel',index):self.api.ref_moved=True;check()
        if self.fault==('raise',index):raise RuntimeError('PRIVATE_FAILURE')
        return audit(index,complete=not(self.unknown and index==0)),dict(source_group_closed=True,supervised_seconds=.01)

@pytest.fixture
def world(tmp_path,monkeypatch):
    reg=registration();api=API(reg);memory=Memory(tmp_path);source=FixtureSource(api);events=[];holder={}
    # This container exposes host /proc PIDs. Native CI separately proves closure.
    monkeypatch.setattr('psutil.Process',lambda: type('Process',(),{'children':lambda self,recursive:[]})())
    github=GitHub(lambda *args:events.append(args),lambda:holder['launcher'].deadline(),runner=api.runner,bound=r.LIMITS['github_requests'])
    launch=r.Launcher(reg,tmp_path,github=github,memory=memory,source=source,emit=lambda *x:events.append(x));holder['launcher']=launch
    return reg,api,memory,source,launch


def test_four_successful_scopes_in_order(world,record_property):
    reg,api,memory,source,launch=world;out=launch.execute()
    assert out['status']=='FOUR_COMPLETE' and out['cleanup']=='CLOSED'
    assert source.calls==[0,1,2,3] and memory.closed
    assert out['database_connections']==out['application_writes']==0
    assert launch.github.requests<320 and launch.publication_calls<=80
    assert out['accounting']['observed_requests']==14
    for key,value in out['accounting'].items():record_property(key,json.dumps(value))
    record_property('simulation','publisher subprocess boundary and Arcus audit fixture; no live evidence')


def test_bury_unknown_never_starts_other_council(world):
    *_,source,launch=world;source.unknown=True;out=launch.execute()
    assert source.calls==[0] and out['reason']=='STOP_ALL_NON_COMPLETE'
    assert out['results'][0]['outcome']=='UNKNOWN' and len(out['not_attempted'])==3
    assert out['cleanup']=='CLOSED'

@pytest.mark.parametrize('index',range(4))
def test_source_failure_each_position(world,index):
    *_,source,launch=world;source.fault=('raise',index);out=launch.execute()
    assert source.calls==list(range(index+1)) and not out['accounting_complete']
    assert out['status']=='STOP_RECONCILE_NO_RETRY' and 'PRIVATE' not in json.dumps(out)

@pytest.mark.parametrize('field,value',[('revision','c'*40),('tree','c'*40),('manifest',{}),('manifest_sha256','e'*64),('dependencies',{}),('packages',{}),('released',False)])
def test_wrong_registration_refused(field,value):
    reg=registration();reg[field]=value
    with pytest.raises(r.Stop):r.validate(reg,checkout=field in ('revision','tree'))


def test_expiry_and_exact_checkout():
    reg=registration()
    with pytest.raises(r.Stop):r.validate(reg,clock=lambda:r.stamp(reg['expires_at']),checkout=False)
    with pytest.raises(r.Stop):r.validate(reg)
    r.validate(reg,checkout=False)


def test_render_inactive_by_default():
    reg=registration();inactive=r.render(reg['release_id'],reg['revision'],reg['tree'],reg['evidence_head'],reg['issued_at'],reg['expires_at'])
    with pytest.raises(r.Stop):r.validate(inactive,checkout=False)
    assert r.control(inactive)['stop_treatment']=='INACTIVE'


def test_replay_remote_consumed_history(world):
    reg,api,memory,source,launch=world
    path=reg['directory']+'/claim/consumed.json';api.trees['2'*40][path]=api.blob(b'{}')
    out=launch.execute();assert not source.calls and out['reason']=='REGISTRATION_ALREADY_CONSUMED'

@pytest.mark.parametrize('when',['before','during'])
def test_cancellation(world,when):
    reg,api,memory,source,launch=world
    if when=='before':api.ref_moved=True
    else:source.fault=('cancel',0)
    out=launch.execute();assert source.calls==([] if when=='before' else [0]) and out['status']=='STOP_RECONCILE_NO_RETRY'


def test_unavailable_control_stops_without_source(world):
    reg,api,memory,source,launch=world;api.fail=lambda method,path:'/contents/' in path
    out=launch.execute();assert not source.calls and out['status']=='STOP_RECONCILE_NO_RETRY'


def test_publication_lost_ack_no_later_mutation(world):
    reg,api,memory,source,launch=world;api.lost=True
    out=launch.execute();assert not source.calls and launch.github.mutation_uncertain and out['publication']=='UNCERTAIN'
    patch=next(i for i,c in enumerate(api.calls) if c[0]=='PATCH')
    assert not any(m!='GET' for m,p in api.calls[patch+1:])


def test_publication_failure_stops(world):
    reg,api,memory,source,launch=world;api.fail=lambda method,path:method=='POST'
    out=launch.execute();assert not source.calls and out['status']=='STOP_RECONCILE_NO_RETRY'


def test_output_and_accounting_limits(world,monkeypatch):
    *_,source,launch=world
    monkeypatch.setattr(r,'resources',lambda *_:(111,1))
    out=launch.execute();assert source.calls==[0] and out['reason']=='CUMULATIVE_SOURCE_BOUND'


def test_export_bound_prevents_publication(world,monkeypatch):
    *_,source,launch=world
    launch.exported=r.LIMITS['exported_bytes']
    out=launch.execute();assert not source.calls and out['reason']=='PUBLICATION_OR_EXPORT_BOUND'


def test_cleanup_failure_not_closed(world):
    *_,source,launch=world
    launch.memory.close=lambda:(_ for _ in ()).throw(OSError())
    out=launch.execute();assert out['cleanup']=='UNCERTAIN' and out['status']=='STOP_RECONCILE_NO_RETRY'


def test_private_source_command_and_clean_environment(tmp_path,monkeypatch):
    memory=Memory(tmp_path);memory.source=tmp_path/'source-group';memory.source.mkdir()
    (memory.source/'cgroup.kill').write_text('');(memory.source/'cgroup.events').write_text('populated 0\n')
    source=r.Source(memory,registration(),tmp_path)
    assert source.command(0,tmp_path/'out')[2]=='verification.discovery.four_council_release'
    seen={}
    class Child:
        returncode=1
        def poll(self):return self.returncode
        def wait(self,timeout):return self.returncode
    def popen(command,**kwargs):seen.update(kwargs);return Child()
    monkeypatch.setattr(r.subprocess,'Popen',popen)
    monkeypatch.setenv('GH_TOKEN','DO_NOT_INHERIT');monkeypatch.setenv('DATABASE_URL','DO_NOT_INHERIT')
    with pytest.raises(r.Stop):source.run(0,lambda:None)
    assert not {'GH_TOKEN','DATABASE_URL','GITHUB_TOKEN'} & set(seen['env'])


def test_actual_cli_inactive_refusal_before_effects(tmp_path):
    reg=registration();reg['released']=False;raw=canonical(reg);path=tmp_path/'reg.json';path.write_bytes(raw)
    result=subprocess.run([sys.executable,'-m','verification.discovery.four_council_release','run','--registration',str(path),'--registration-sha256',r.sha(raw),'--enable-reviewed-source-only-stop-treatment'],capture_output=True,text=True,timeout=10)
    assert result.returncode==1 and 'REGISTRATION_INACTIVE_OR_CHANGED' in result.stdout
    assert not (tmp_path/'events.jsonl').exists()


def test_finite_reader_context_not_generalised():
    for row,proof in [(r.ROWS[0],True),(r.ROWS[1],False)]:
        with pytest.raises(ValueError):r.finite.read(row,retain_proof=proof,no_transport_retry=True,execution_mode='four-council-owner-local')


def test_owner_context_not_caller_authority():
    with pytest.raises(r.Stop):r.owner_source_context()

@pytest.mark.parametrize('fault',['none','final_publish','final_ack','final_socket'])
def test_complete_reporting_and_archive(world,tmp_path,monkeypatch,fault,record_property):
    reg,api,memory,source,launch=world
    journal=r.Journal(tmp_path/'events.jsonl');launch.emit=journal.emit;launch.github.emit=journal.emit
    out=launch.execute()
    if fault=='final_publish':api.fail=lambda method,path:method=='POST'
    if fault=='final_ack':api.lost=True
    if fault=='final_socket':monkeypatch.setattr(r,'sockets',lambda:{'socket:synthetic-new'})
    code=r.finish(launch,journal,out,tmp_path)
    final=json.loads((tmp_path/'final-result.json').read_bytes())
    if fault=='none':
        assert code==0 and final['final_publication']=='VERIFIED' and final['cleanup']=='CLOSED'
        tree=api.trees[api.commits[api.head]]
        raw=base64.b64decode(api.blobs[tree[reg['directory']+'/completed/events.jsonl']]['content'])
        assert raw==(tmp_path/'events.jsonl').read_bytes()
        for k,v in final['accounting'].items():record_property('complete_'+k,json.dumps(v))
    else:
        assert code==1 and final['status']=='STOP_RECONCILE_NO_RETRY'
        if fault in ('final_ack','final_socket'):assert final['cleanup']=='UNCERTAIN'
    assert (tmp_path/'publication-events.jsonl').is_file()


def test_registration_bootstrap_has_no_self_referential_hash():
    reg=registration();before=r.control(reg,enabled=True)
    reg['evidence_head']='9'*40
    assert before==r.control(reg,enabled=True)
    reg['tree']='8'*40
    assert before!=r.control(reg,enabled=True)


def test_modified_control_and_output_truncation(world):
    reg,api,memory,source,launch=world
    path=reg['directory']+'/control.json';value=r.control(reg,enabled=True);value['cancelled']=True
    api.trees['2'*40][path]=api.blob(canonical(value))
    assert launch.execute()['reason']=='CONTROL_CANCELLED_OR_UNAVAILABLE'
    assert not source.calls


def test_actual_finite_rochdale_context_wiring(tmp_path,monkeypatch):
    # Actual read() and supervisor selection; no browser/council request.
    seen={}
    def supervisor(case,path,**kwargs):
        seen.update(kwargs);path.write_text(json.dumps(audit(1)))
    monkeypatch.setattr('verification.direct_reference.instrumented_probe.supervised',supervisor)
    out=r.finite.read(r.ROWS[1],retain_proof=True,no_transport_retry=True,execution_mode='four-council-owner-local')
    assert seen['retain_proof'] is True and seen['execution_mode']=='four-council-owner-local' and out['retained_proof']

@pytest.mark.parametrize('fault',['none','unknown','unavailable'])
def test_actual_complete_cli_with_fixture_boundaries(tmp_path,fault,record_property):
    result=subprocess.run([sys.executable,'-m','tests.four_council_release_fixture_cli','--root',str(tmp_path/'cli'),'--fault',fault],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    out=json.loads((tmp_path/'cli/rehearsal.json').read_bytes())
    assert out['database_connections']==out['application_writes']==0
    record_property('fault',fault)
    record_property('accounting',json.dumps(out['accounting']))

@pytest.mark.parametrize('fault',['accounting','identity','cleanup'])
def test_returned_failure_proof_retained_before_stop(world,fault):
    reg,api,memory,source,launch=world
    original=source.run
    def run(index,check):
        a,owned=original(index,check)
        if fault=='accounting':a['resource']['requests_attempted']=None
        elif fault=='identity':a['records'][0]['reference']=''
        else:a['cleanup']='UNCERTAIN'
        return a,owned
    source.run=run
    out=launch.execute()
    assert source.calls==[0] and out['status']=='STOP_RECONCILE_NO_RETRY'
    assert out['returned_evidence'][0]['export']=='COMMITTED_READBACK_VERIFIED'
    assert out['results'][0]['rejection']


def test_static_manifest_matches_executable():
    path=r.ROOT/'docs/design/four-council-release-20261022/manifest.json'
    assert path.read_bytes()==canonical(r.manifest())

@pytest.mark.parametrize('count',[60,61])
def test_actual_idox_fixed_row_ceiling_without_truncation(count):
    from verification.discovery.idox_window import run,WindowConfig
    from tests.test_discovery_idox_window import page,Response
    from tests.test_discovery_four_council_proof import config,bodies,SCOPES
    from dataclasses import replace
    scope=SCOPES[0];cfg=replace(config(scope),max_rows=60)
    # Reconstructed fixture: real parser accepts up to100 rows on a page.
    body=page(first=1,last=count,total=count,refs=tuple(f'{10000+i}/26' for i in range(count))).replace(b'Mon 28 Sep 2026',b'Thu 08 Oct 2026')
    import re
    body=re.sub(rb'keyVal=K(\d+)&',lambda m:b'keyVal=_BURY_DCAPR_'+str(int(m[1])+1).encode()+b'&',body)
    body=body.replace(b'value="10" selected>10',b'value="100" selected>100')
    values=iter([bodies(scope)[0],bodies(scope)[1],body,bodies(scope)[-1]])
    audit=run(lambda *_args,**_kw:Response(next(values)),cfg,retain_proof=True)
    if count==60:assert len(audit['records'])==60 and audit['enumeration_evidence']=='COUNT_RECONCILED'
    else:
        assert not audit['records'] and audit['enumeration_evidence']=='ROW_CAP' and audit['completeness']=='INCOMPLETE'
        assert audit['row_limit_exceeded']['observed_page_rows']==61


def test_private_fixed_child_selects_row_ceiling(tmp_path,monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    seen={}
    def live(config,**kwargs):seen['rows']=config.max_rows;return audit(0)
    monkeypatch.setattr(r.finite,'live',live)
    monkeypatch.setattr(sys,'argv',['finite','--idox-worker','bury','2026-10-08','2026-10-14','--no-transport-retry','--retain-four-council-proof','--fixed-four-row-limit','--output',str(tmp_path/'audit')])
    r.finite.main();assert seen['rows']==60


def test_actual_idox_cumulative_crossing_keeps_prior_rows_and_stops():
    from verification.discovery.idox_window import run
    from tests.test_discovery_idox_window import page,Response
    from tests.test_discovery_four_council_proof import config,bodies,SCOPES
    from dataclasses import replace
    import re
    scope=SCOPES[0]
    def body(first,last,offset,next_page=None):
        raw=page(first=first,last=last,total=61,refs=tuple(f'{10000+i}/26' for i in range(first,last+1)),next_page=next_page).replace(b'Mon 28 Sep 2026',b'Thu 08 Oct 2026')
        raw=re.sub(rb'keyVal=K(\d+)&',lambda m:b'keyVal=_BURY_DCAPR_'+str(int(m[1])+offset).encode()+b'&',raw)
        return raw.replace(b'value="10" selected>10',b'value="50" selected>50')
    values=iter([bodies(scope)[0],bodies(scope)[1],body(1,50,1,2),body(51,61,51),bodies(scope)[-1]])
    calls=[]
    def dispatch(*args,**kwargs):calls.append(args);return Response(next(values))
    out=run(dispatch,replace(config(scope),max_rows=60),retain_proof=True)
    assert len(calls)==5 and len(out['records'])==50 and out['enumeration_evidence']=='ROW_CAP'
    assert out['row_limit_exceeded']['previously_retained_rows']==50 and out['row_limit_exceeded']['observed_page_rows']==11
    assert out['resource']['requests_attempted']==5 and not out['resource']['budget_exhaustion']
