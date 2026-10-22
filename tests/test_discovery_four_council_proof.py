"""Four fixed scopes; reconstructed HTML/locator doubles, never council markup.

Actual Requests boundary, source readers, classifier and private child wiring.
No database or council access. Retained artifact tests make no new source claim.
"""
import asyncio
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import zipfile
import pytest
import requests
from playwright.async_api import TimeoutError as LocatorTimeout
from verification.discovery import four_council_proof as proof, idox_window, finite_acceptance as finite
from verification.discovery import arcus_ui_window as ui
from verification.discovery.arcus_ui_config import ROCHDALE, dated_config
from tests.test_discovery_idox_window import Response, page
from verification.bolton_recon.fixtures import FORM, TOKEN

SCOPES=[('bury','RECEIVED','2026-10-08','2026-10-14'),
        ('oldham','RECEIVED','2026-10-08','2026-10-14'),
        ('tameside','RECEIVED','2026-10-01','2026-10-07')]

@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    for key in list(__import__('os').environ):
        if any(s in key for s in ('DATABASE','SUPABASE','OPENAI','ANTHROPIC')):monkeypatch.delenv(key,raising=False)

def config(scope):
    c,s,a,b=scope
    return idox_window.WindowConfig(c,s,date.fromisoformat(a),date.fromisoformat(b),max_transport_retries=0)

def bodies(scope,*,pager=True):
    c,s,a,b=scope
    body=page(pager=pager).replace(b'Mon 28 Sep 2026',datetime_literal(a))
    if c=='bury':
        body=body.replace(b'keyVal=K0',b'keyVal=_BURY_DCAPR_1').replace(b'keyVal=K1',b'keyVal=_BURY_DCAPR_2')
    echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',('name="date(applicationReceivedStart)" value="'+date.fromisoformat(a).strftime('%d/%m/%Y')+'"').encode()).replace(b'name="date(applicationReceivedEnd)" value=""',('name="date(applicationReceivedEnd)" value="'+date.fromisoformat(b).strftime('%d/%m/%Y')+'"').encode())
    return [FORM,body,body,echo]

def async_run(coro):
    # The repository's seccomp wrapper denies even AF_UNIX sockets. A single-threaded
    # timer/selector loop needs no wakeup socket; actual coroutine/timeouts still run.
    class SocketFreeLoop(asyncio.SelectorEventLoop):
        def _make_self_pipe(self):pass
        def _close_self_pipe(self):pass
        def _write_to_self(self):pass
    with asyncio.Runner(loop_factory=SocketFreeLoop) as runner:return runner.run(coro)


def datetime_literal(a):
    return date.fromisoformat(a).strftime('%a %d %b %Y').encode()

def run(scope,values,enabled=True):
    calls=[];responses=[]
    def dispatch(*args,**kwargs):
        calls.append(args)
        v=values[len(calls)-1]
        if isinstance(v,Exception):raise v
        r=Response(v[1] if isinstance(v,tuple) else v)
        if isinstance(v,tuple):r.status_code=v[0]
        responses.append(r);return r
    out=idox_window.run(dispatch,config(scope),retain_proof=enabled)
    assert all(r.closed for r in responses)
    return out,calls

@pytest.mark.parametrize('scope',SCOPES)
def test_complete_reader_decision_and_limits_unchanged(scope,record_property):
    before,calls=run(scope,bodies(scope),False);after,newcalls=run(scope,bodies(scope))
    for k in ('enumeration_evidence','completeness','applied_interval','records','pages','cleanup'):
        assert before[k]==after[k]
    assert len(calls)==len(newcalls)==4 and after['resource']['retries']==0
    assert before['resource']['received_bytes']==after['resource']['received_bytes']
    p=proof.validate_proof(after['retained_proof'])
    assert len(p['events'])==4
    assert p['events'][-1]['sanitised_evidence']['criteria']['Start']['matches_requested']
    assert p['events'][2]['sanitised_evidence']['pagers'][0]['count_marker']==[1,2,2]
    assert TOKEN not in json.dumps(p)
    record_property('audit_bytes',len(proof.encoded(after)));record_property('proof_bytes',len(proof.encoded(p)));record_property('fixture_requests',len(newcalls))


def test_bury_sparse_does_not_complete_and_pins_original_and_sanitised_hashes():
    out,_=run(SCOPES[0],bodies(SCOPES[0],pager=False))
    assert out['enumeration_evidence']=='TOTAL_UNKNOWN' and out['completeness']=='UNKNOWN'
    e=out['retained_proof']['events'][2]
    assert e['sanitised_evidence']['pagers']==[] and e['sanitised_evidence']['result_rows']==2
    assert e['original_response_sha256']==hashlib.sha256(bodies(SCOPES[0],pager=False)[2]).hexdigest()
    assert e['sanitised_sha256']==proof.sha(proof.encoded(e['sanitised_evidence']))
    assert e['original_response_sha256']!=e['sanitised_sha256']


def test_oldham_missing_sort_does_not_infer_zero_or_error_cause():
    body=b'<html><form><input type="hidden" value="PRIVATE_TOKEN"></form></html>'
    out,calls=run(SCOPES[1],[FORM,body])
    assert len(calls)==2 and out['failure']=='ListingError:sort selector'
    assert out['applied_interval'] is None and not out['records']
    assert out['proof_failure_operation']=='SORT_FORM_PARSE'
    e=out['retained_proof']['events'][1]['sanitised_evidence']
    assert e['order_by_selects']==0 and e['forms']==1 and e['zero_literal_matches']==0
    assert 'PRIVATE_TOKEN' not in json.dumps(out)


def test_tameside_sort_request_failure_has_no_invented_body_and_reuses_transport():
    out,calls=run(SCOPES[2],bodies(SCOPES[2])[:2]+[requests.Timeout('PRIVATE_URL_AND_TOKEN')])
    assert len(calls)==3 and out['failure_diagnostic']['stage']=='SORT_REQUEST'
    p=proof.validate_proof(out['retained_proof']);e=p['events'][-1]
    assert e['original_response_sha256'] is None and e['body_bytes'] is None
    assert e['sanitised_evidence']=={'availability':'UNAVAILABLE'}
    assert e['transport']==out['failure_diagnostic']['transport']
    assert e['transport']['rejection_reason'] is not None
    assert 'PRIVATE_URL_AND_TOKEN' not in json.dumps(out)
    assert out['completeness']=='FAILED' and out['resource']['retries']==0


@pytest.mark.parametrize('mutation',[lambda b:b.replace(b'Thu 08 Oct 2026',b'Thu 15 Oct 2026'),
    lambda b:b.replace(b'keyVal=K1',b'keyVal=K0'),lambda b:b.replace(b'</html>',b'')])
def test_malformed_and_duplicate_reader_failures_not_promoted(mutation):
    values=bodies(SCOPES[1]);values[2]=mutation(values[2])
    out,_=run(SCOPES[1],values)
    assert out['failure'] and out['completeness']!='COMPLETE'


@pytest.mark.parametrize('scope',[('bolton','RECEIVED','2026-10-08','2026-10-14'),
    ('oldham','VALIDATED','2026-10-08','2026-10-14'),('bury','RECEIVED','2026-10-07','2026-10-14')])
def test_wrong_scope_refused_before_any_request(scope):
    called=[]
    with pytest.raises(proof.ProofError):
        idox_window.run(lambda *a,**k:called.append(a),config(scope),retain_proof=True)
    assert called==[]


def test_retry_enablement_and_nonboolean_selection_refused():
    with pytest.raises(ValueError):idox_window.run(None,idox_window.WindowConfig('bury'),retain_proof=True)
    with pytest.raises(ValueError):idox_window.run(None,config(SCOPES[0]),retain_proof=1)


def test_projection_never_exports_hidden_cookie_contact_arbitrary_text():
    body=b'''<html><h1>PRIVATE_CONTACT</h1><form><input type="hidden" name="csrf" value="SECRET"><input name="email" value="private@example.test"><textarea>COOKIE_PRIVATE</textarea></form><p class="pager">UNTRUSTED_TOKEN</p><select name="orderBy"><option selected value="TOKEN">PRIVATE</option></select></html>'''
    p=proof.ProofLog(*SCOPES[1]);p.add(body,'SEARCH',transport={'http_status':200,'media_type':'text/html','redirect':'NONE','cookie':'SECRET'})
    out=json.dumps(proof.validate_proof(p.result()))
    for v in ('SECRET','PRIVATE_CONTACT','private@example.test','COOKIE_PRIVATE','UNTRUSTED_TOKEN','TOKEN'):assert v not in out
    assert 'UNKNOWN_OR_OTHER' in out


@pytest.mark.parametrize('body,status',[(None,'UNAVAILABLE'),(b'','EMPTY'),(b'\xff','INVALID_ENCODING'),(b'x'*500001,'OVERSIZED')])
def test_missing_and_bounded_body_states_are_explicit(body,status):
    p=proof.ProofLog(*SCOPES[0]);p.add(body,'SEARCH');v=proof.validate_proof(p.result())
    assert v['events'][0]['sanitised_evidence']['availability']==status


def test_projection_event_and_structure_bounds():
    p=proof.ProofLog(*SCOPES[0])
    for _ in range(proof.MAX_EVENTS):p.add(None,'SEARCH')
    with pytest.raises(proof.ProofError):p.add(None,'SEARCH')
    with pytest.raises(proof.ProofError):proof.project(b'<html>'+b'<p class="pager"></p>'*5+b'</html>',p.scope)


@pytest.mark.parametrize('change',[lambda p:p['events'][0].update(operation='PRIVATE'),
    lambda p:p['events'][0].update(observed_at='2026-10-22'),
    lambda p:p['events'][0].update(sanitised_sha256='0'*64),
    lambda p:p['events'][0]['sanitised_evidence'].update(secret='PRIVATE')])
def test_corrupted_hash_timestamp_operation_and_projection_refused(change,tmp_path):
    p=proof.ProofLog(*SCOPES[0]);p.add(b'<html></html>','SEARCH');v=p.result();change(v)
    v['events_sha256']=proof.sha(proof.encoded(v['events']))
    with pytest.raises(proof.ProofError):proof.write_audit(tmp_path/'audit',{'retained_proof':v})
    assert not (tmp_path/'audit').exists()


def test_exclusive_export_readback_and_unwritable_cleanup(tmp_path,monkeypatch):
    p=proof.ProofLog(*SCOPES[0]);p.add(None,'SEARCH');v={'retained_proof':p.result(),'failure':'SOURCE_CONTRACT_REJECTED'}
    dest=tmp_path/'audit.json';proof.write_audit(dest,v);assert json.loads(dest.read_bytes())==v
    with pytest.raises(proof.ProofError):proof.write_audit(dest,v)
    assert json.loads(dest.read_bytes())==v
    with pytest.raises(proof.ProofError):proof.write_audit(tmp_path/'missing'/'audit.json',v)
    with pytest.raises(proof.ProofError):proof.write_audit(tmp_path/'large',dict(v,oversized='x'*proof.MAX_OBSERVATION))
    original=Path.read_bytes
    def bad_read(path):return b'WRONG' if path.name=='bad.json' else original(path)
    monkeypatch.setattr(Path,'read_bytes',bad_read)
    with pytest.raises(proof.ProofError):proof.write_audit(tmp_path/'bad.json',v)
    assert not (tmp_path/'bad.json').exists()


class RenderedPage:
    """Synthetic piercing locator view, deliberately no page.content API."""
    def __init__(self,cfg,*,failure=True,total=2,mode=None):
        self.cfg=cfg;self.failure=failure;self.total=total;self.segment=0;self.mode=mode
    def locator(self,key):return self.L(self,key)
    def get_by_label(self,label,**kw):return self.L(self,'label:'+label)
    def get_by_role(self,role,name,**kw):return self.L(self,'role:'+name)
    class L:
        def __init__(self,p,key):self.p=p;self.key=key
        def filter(self,**kw):return self
        def nth(self,i):assert i==0;return self
        async def wait_for(self,**kw):
            if self.p.failure:raise LocatorTimeout('PRIVATE_EXCEPTION')
        async def is_visible(self):return True
        async def count(self):
            if self.p.mode=='unavailable':raise RuntimeError('PRIVATE_TOKEN')
            if self.p.mode=='timeout':await asyncio.sleep(1)
            if self.p.mode=='oversized' and self.key=='p.pr-pagination__results':return 100
            if self.key=='p:text-is("No results found")':return int(self.p.failure)
            if self.key=='div[role="list"].slds-box':return 0 if self.p.failure else min(10,self.p.total-self.p.segment*10)
            if self.key=='a.pr-pagination__link':return int((self.p.segment+1)*10<self.p.total)
            if self.key=='p.pr-pagination__results':return 0 if self.p.failure else 1
            return 1
        async def input_value(self,**kw):
            name=self.key[6:]
            return date.fromisoformat(self.p.cfg.start if name=='Valid date from' else self.p.cfg.end).strftime('%d/%m/%Y') if name in ('Valid date from','Valid date to') else ''
        async def inner_text(self,**kw):
            if self.key=='p.pr-pagination__results':return f'Showing {self.p.segment*10+1} to {min((self.p.segment+1)*10,self.p.total)} of {self.p.total} results'
            return 'Planning Applications' if self.key=='role:Category' else 'Select an option'
        async def get_attribute(self,*a,**kw):return '#'
        async def click(self,**kw):
            if self.key=='a.pr-pagination__link':self.p.segment+=1


def test_rochdale_actual_timeout_retains_rendered_structure_without_changing_zero_contract():
    cfg=dated_config(ROCHDALE,'2026-10-08','2026-10-14');audit={}
    async_run(ui.enumerate_ui(RenderedPage(cfg),audit,asyncio.Event(),cfg,retain_proof=True))
    assert audit['listing_failure']=='TimeoutError' and audit['completeness']=='FAILED'
    assert audit['criteria_control_timeout']['operation']=='RESULT_MARKER_VISIBLE' and audit['applied_interval'] is None
    e=proof.validate_proof(audit['retained_proof'])['events'][0]
    assert e['original_response_sha256'] is None and e['rendered_dom_sha256'] is None
    assert e['sanitised_evidence']['zero_literal_matches']==1
    assert e['sanitised_evidence']['criteria']['Valid date from']=='MATCH'
    assert e['sanitised_evidence']['view']=='PLAYWRIGHT_RENDERED_LOCATORS'
    assert 'PRIVATE' not in json.dumps(audit)


@pytest.mark.parametrize('kind',['unavailable','oversized','timeout'])
def test_rochdale_failed_snapshot_cannot_complete(kind):
    cfg=dated_config(ROCHDALE,'2026-10-08','2026-10-14');audit={}
    async_run(ui.enumerate_ui(RenderedPage(cfg,mode=kind),audit,asyncio.Event(),cfg,retain_proof=True))
    assert audit['proof_retention_failure']=='PROOF_RETENTION_FAILED'
    assert audit['failure']=='PROOF_RETENTION_FAILED' and audit['completeness']=='FAILED'


@pytest.mark.parametrize('total',[2,73])
def test_rochdale_success_and_cap_have_same_decisions_and_no_extra_source_navigation(total,monkeypatch,record_property):
    from tests.test_discovery_arcus_ui import card
    cfg=dated_config(ROCHDALE,'2026-10-08','2026-10-14')
    async def cards(page,config):
        rows=[]
        for i in range(min(10,total-page.segment*10)):
            c=card(f'TEST/{page.segment*10+i}',key='a'*15+f'{page.segment*10+i:03d}',valid='08/10/2026')
            c['links'][0]['href']=c['links'][0]['href'].replace('arcusbe.manchester.gov.uk',config.host)
            # Each synthetic row has a distinct stable source key.
            c['links'][0]['href']=c['links'][0]['href'].replace('a'*18,('a'*15+f'{page.segment*10+i:03d}'))
            rows.append(c)
        return rows
    monkeypatch.setattr(ui,'read_cards',cards)
    audits=[]
    for enabled in (False,True):
        audit={};p=RenderedPage(cfg,failure=False,total=total)
        async_run(ui.enumerate_ui(p,audit,asyncio.Event(),cfg,retain_proof=enabled));audits.append(audit)
    for key in ('listing_segments','listing_records','applied_interval','enumeration_evidence','completeness'):
        assert audits[0][key]==audits[1][key]
    assert audits[1]['enumeration_evidence']==('COUNT_RECONCILED' if total==2 else 'PAGE_CAP')
    assert len(audits[1]['listing_records'])==(2 if total==2 else 60)
    assert len(proof.encoded(audits[1]))<65536
    proof.validate_proof(audits[1]['retained_proof'])
    record_property('audit_bytes',len(proof.encoded(audits[1])));record_property('proof_bytes',len(proof.encoded(audits[1]['retained_proof'])));record_property('rows',len(audits[1]['listing_records']))


def test_private_idox_child_wires_opt_in_to_actual_reader_and_exclusive_export(tmp_path,monkeypatch):
    seen=[]
    def live(cfg,*,retain_proof=False):
        assert retain_proof and cfg==config(SCOPES[2]);seen.append(1)
        return run(SCOPES[2],bodies(SCOPES[2]))[0]
    monkeypatch.setattr(finite,'live',live)
    monkeypatch.setattr('sys.argv',['finite','--idox-worker','tameside','2026-10-01','2026-10-07','--no-transport-retry','--retain-four-council-proof','--output',str(tmp_path/'out')])
    finite.main();out=json.loads((tmp_path/'out').read_bytes());proof.validate_proof(out['retained_proof']);assert seen==[1]


def test_supervised_reader_passes_fixed_proof_flag_and_cleans_temp_context(tmp_path,monkeypatch):
    seen=[]
    def child(command,**kwargs):
        assert '--retain-four-council-proof' in command and '--no-transport-retry' in command
        assert not any('DATABASE' in k for k in kwargs['env'])
        seen.append(Path(command[-1]).parent);Path(command[-1]).write_text(json.dumps(run(SCOPES[2],bodies(SCOPES[2]))[0]));return 0,False
    monkeypatch.setattr(finite,'supervise',child)
    out=finite.read(dict(council='tameside',semantics='RECEIVED',start='2026-10-01',end='2026-10-07'),no_transport_retry=True,retain_proof=True)
    assert out['retained_proof'] and not seen[0].exists()


def test_retained_rochdale_artifact_remains_failed_without_invented_dom():
    path=Path('docs/design/stage4-r0-execution/exact20-results-20261015/artifact-11997283579.zip')
    with zipfile.ZipFile(path) as z:data=json.loads(z.read('result.json'))
    item=next(r for r in data['results'] if r['window']['council']=='rochdale' and r['window']['start']=='2026-10-08')
    assert item['enumeration_completeness']=='FAILED' and 'retained_proof' not in item['source']


@pytest.mark.parametrize('status',[403,429,502])
def test_rejected_http_retains_status_but_does_not_claim_discarded_body(status):
    out,calls=run(SCOPES[2],bodies(SCOPES[2])[:2]+[(status,b'<html>PRIVATE_PROVIDER_ERROR</html>')])
    assert len(calls)==3 and out['failure_diagnostic']['stage']=='SORT_REQUEST'
    e=proof.validate_proof(out['retained_proof'])['events'][-1]
    assert e['transport']['http_status']==status
    assert e['original_response_availability']=='UNAVAILABLE' and e['original_response_sha256'] is None
    assert 'PRIVATE_PROVIDER_ERROR' not in json.dumps(out)


@pytest.mark.parametrize('change',[lambda v:v.update(council='oldham'),
    lambda v:v.update(requested_interval=['2026-10-01','2026-10-07']),
    lambda v:v['response_provenance'][0].update(body_sha256='0'*64)])
def test_proof_transplant_and_response_hash_binding_refused(change,tmp_path):
    value,_=run(SCOPES[0],bodies(SCOPES[0]));change(value)
    with pytest.raises(proof.ProofError):proof.write_audit(tmp_path/'out',value)
    assert not (tmp_path/'out').exists()


def test_proof_mode_arbitrary_value_error_is_not_exported():
    cfg=dated_config(ROCHDALE,'2026-10-08','2026-10-14')
    class P(RenderedPage):
        class L(RenderedPage.L):
            async def wait_for(self,**kwargs):raise ValueError('PRIVATE_TOKEN_AND_URL')
    audit={};async_run(ui.enumerate_ui(P(cfg),audit,asyncio.Event(),cfg,retain_proof=True))
    assert audit['listing_failure']=='ValueError' and 'PRIVATE_TOKEN_AND_URL' not in json.dumps(audit)


def test_hidden_zero_visibility_is_explicit_and_not_a_zero_qualification():
    cfg=dated_config(ROCHDALE,'2026-10-08','2026-10-14')
    class P(RenderedPage):
        class L(RenderedPage.L):
            async def is_visible(self):return False
    audit={};async_run(ui.enumerate_ui(P(cfg),audit,asyncio.Event(),cfg,retain_proof=True))
    p=proof.validate_proof(audit['retained_proof'])['events'][0]['sanitised_evidence']
    assert p['zero_literal_matches']==1 and p['visibility']['zero_literal_matches']==[False]
    assert audit['completeness']=='FAILED' and audit.get('explicit_zero_evidence') is None


def test_arcus_private_entrypoint_passes_selection_and_exports_actual_reader_audit(tmp_path,monkeypatch):
    from verification.direct_reference import instrumented_probe as worker
    cfg=dated_config(ROCHDALE,'2026-10-08','2026-10-14');seen=[]
    async def probe_case(case,window,metadata,*,retain_proof=False):
        assert case=='discovery_rochdale_ui_window' and window==(cfg.start,cfg.end) and retain_proof and not metadata
        seen.append(1);audit={}
        await ui.enumerate_ui(RenderedPage(cfg),audit,asyncio.Event(),cfg,retain_proof=True)
        audit.update(case=case,date_semantics='VALIDATED',requested_interval=[cfg.start,cfg.end])
        return audit
    monkeypatch.setattr(worker,'probe',probe_case)
    monkeypatch.setattr(worker.asyncio,'run',async_run)
    monkeypatch.setattr('sys.argv',['probe','--worker','--case','discovery_rochdale_ui_window','--window-start',cfg.start,'--window-end',cfg.end,'--retain-four-council-proof','--output',str(tmp_path/'out')])
    assert worker.main()==0
    value=json.loads((tmp_path/'out').read_bytes());proof.validate_audit(value,('rochdale','VALIDATED',cfg.start,cfg.end));assert seen==[1]


def test_export_write_interruption_removes_partial_file(tmp_path,monkeypatch):
    p=proof.ProofLog(*SCOPES[0]);p.add(None,'SEARCH');value={'retained_proof':p.result(),'failure':'SOURCE_CONTRACT_REJECTED'}
    original=Path.open
    class Interrupted:
        def __init__(self,f):self.f=f
        def __enter__(self):return self
        def __exit__(self,*args):self.f.close()
        def write(self,raw):self.f.write(raw[:10]);raise OSError('PRIVATE')
    def opening(path,*args,**kwargs):
        f=original(path,*args,**kwargs)
        return Interrupted(f) if path.name=='partial' else f
    monkeypatch.setattr(Path,'open',opening)
    with pytest.raises(proof.ProofError,match='PROOF_EXPORT_FAILED'):proof.write_audit(tmp_path/'partial',value)
    assert not (tmp_path/'partial').exists()


def test_projection_failure_closes_responses_and_cannot_complete(monkeypatch):
    def broken(*args,**kwargs):raise proof.ProofError('PROOF_OUTPUT_BOUND')
    monkeypatch.setattr(proof.ProofLog,'add',broken)
    out,calls=run(SCOPES[0],bodies(SCOPES[0]))
    assert len(calls)==1 and out['completeness']=='FAILED' and out['cleanup']=='BOUNDARY_CLOSED'
    assert out['proof_retention_failure']=='PROOF_RETENTION_FAILED'


def test_missing_and_truncated_proof_export_never_returns_success(tmp_path):
    with pytest.raises(proof.ProofError,match='PROOF_MISSING'):proof.write_audit(tmp_path/'missing',{'completeness':'COMPLETE'})
    from verification.direct_reference.instrumented_probe import bounded_worker_audit
    p=tmp_path/'truncated';p.write_text('{"retained_proof":')
    with pytest.raises(json.JSONDecodeError):bounded_worker_audit(p,'discovery_rochdale_ui_window')


def test_raw_and_rendered_kind_transplant_refused(tmp_path):
    cfg=dated_config(ROCHDALE,'2026-10-08','2026-10-14');audit={}
    async_run(ui.enumerate_ui(RenderedPage(cfg),audit,asyncio.Event(),cfg,retain_proof=True))
    p=audit['retained_proof'];p['scope']=list(SCOPES[0])
    with pytest.raises(proof.ProofError,match='PROOF_RENDERED_BINDING'):proof.write_audit(tmp_path/'out',audit)
