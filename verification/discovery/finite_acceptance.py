"""Finite credential-free discovery caller. No workflow, persistence or scheduling.

Registration must pin the reviewed manifest/hash/revision and supervise this
caller with the declared hard outer deadline before any live execution.
"""
from datetime import date,timedelta,datetime,timezone
import hashlib,json,time
from pathlib import Path
import tempfile,contextlib,os,sys
from verification.stage26b_l1.actions_runner import supervise
from app.pipeline.discovery_contract import COUNCILS
from app.pipeline.discovery_screening import retain_screening
from .idox_window import WindowConfig,live
from .arcus_ui_config import UI_CASES,dated_config
from .arcus_ui_audit import validate as validate_arcus

ARCUS=frozenset({'manchester','rochdale','salford'})
SEMANTICS={c:'VALIDATED' if c in ARCUS|{'stockport'} else 'RECEIVED' for c in COUNCILS}
RULE='stage4-discovery-v1'
LIMITS={'calls':36,'requests':1200,'bytes':72_000_000+240*1024*1024,'seconds':1900,'output_bytes':20_000_000}

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def manifest(start,end,purpose):
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if a>b or (b-a).days>27 or purpose not in {'SUSPENSION_CATCHUP','PROSPECTIVE','BACKFILL_AUDIT'}:raise ValueError('finite interval')
    rows=[]
    for council in sorted(COUNCILS):
        cursor=a
        while cursor<=b:
            stop=min(cursor+timedelta(days=6),b)
            rows.append(dict(council=council,start=cursor.isoformat(),end=stop.isoformat(),semantics=SEMANTICS[council]))
            cursor=stop+timedelta(days=1)
    return dict(purpose=purpose,start=start,end=end,rule=RULE,limits=LIMITS.copy(),rows=rows)

def select_rows(plan,expected_hash,councils):
    """The rows of exactly the named councils from a canonical, hash-matched manifest. Nothing outside the regenerated plan can be selected."""
    if plan!=manifest(plan['start'],plan['end'],plan['purpose']) or digest(plan)!=expected_hash:raise ValueError('unreviewed manifest')
    wanted=list(councils)
    if not wanted or len(set(wanted))!=len(wanted) or any(c not in COUNCILS for c in wanted):raise ValueError('council selection')
    return [dict(row) for row in plan['rows'] if row['council'] in wanted]

def read(row, *, no_transport_retry=False, retain_proof=False, execution_mode=None, fixed_four_rows=False, execution_budget=None, campaign_scope=None, collection_profile=None):
    if collection_profile is not None:
        from .source_profiles import validate
        validate(collection_profile,row)
        if campaign_scope!=row:raise ValueError('PROFILE_REQUIRES_CAMPAIGN_SCOPE')
        expected_mode=('render-intake-v1' if execution_mode=='render-intake-v1' and row['council']=='manchester' else 'four-council-owner-local') if collection_profile['family']=='ARCUS_UI' else None
        if execution_budget!=collection_profile['execution_budget'] or execution_mode!=expected_mode:raise ValueError('PROFILE_CALLER_BUDGET_OR_MODE')
    if campaign_scope is not None:
        from .four_council_proof import manifest_scope
        if row!=campaign_scope or not retain_proof or not no_transport_retry or not fixed_four_rows:raise ValueError('CAMPAIGN_READER_BINDING')
        with manifest_scope(campaign_scope,collection_profile):
            return _read(row,no_transport_retry=no_transport_retry,retain_proof=retain_proof,execution_mode=execution_mode,fixed_four_rows=fixed_four_rows,execution_budget=execution_budget)
    return _read(row,no_transport_retry=no_transport_retry,retain_proof=retain_proof,execution_mode=execution_mode,fixed_four_rows=fixed_four_rows,execution_budget=execution_budget)


def _profiled_arcus(row):
    from .four_council_proof import current_collection_profile
    p=current_collection_profile()
    return p is not None and p['family']=='ARCUS_UI' and p['council']==row['council']


def _read(row, *, no_transport_retry=False, retain_proof=False, execution_mode=None, fixed_four_rows=False, execution_budget=None):
    if type(no_transport_retry) is not bool or type(retain_proof) is not bool:raise ValueError('retry/proof policy')
    # A named browser execution budget applies to the Arcus UI reader only.
    if execution_budget is not None and (row['council'] not in ARCUS or not isinstance(execution_budget,str)):raise ValueError('execution budget')
    if type(fixed_four_rows) is not bool or (fixed_four_rows and (not retain_proof or not no_transport_retry)):raise ValueError('fixed row policy')
    if execution_mode is not None and (execution_mode not in ('four-council-owner-local','render-intake-v1') or (execution_mode=='render-intake-v1' and row['council']!='manchester') or not retain_proof or (row['council']!='rochdale' and not _profiled_arcus(row))):
        raise ValueError('proof execution context')
    if retain_proof:
        from .four_council_proof import require_scope
        require_scope(row['council'],row['semantics'],row['start'],row['end'])
        if not no_transport_retry:raise ValueError('proof requires zero retry')
    from .four_council_proof import current_manifest_scope,current_collection_profile
    selected=current_manifest_scope();profile=current_collection_profile()
    if row['council'] not in ARCUS:
        with tempfile.TemporaryDirectory(prefix='discovery-finite-idox-') as td:
            path=Path(td)/'source.json'
            env=dict(PATH='/usr/bin:/bin',HOME=td,TMPDIR=td,PYTHONDONTWRITEBYTECODE='1')
            code,expired=supervise([sys.executable,'-m','verification.discovery.finite_acceptance','--idox-worker',row['council'],row['start'],row['end']]+(['--no-transport-retry'] if no_transport_retry else [])+(['--retain-four-council-proof'] if retain_proof else [])+(['--fixed-four-row-limit'] if fixed_four_rows else [])+(['--campaign-scope',json.dumps(selected,sort_keys=True)] if selected is not None else [])+(['--collection-profile',json.dumps(profile,sort_keys=True)] if profile is not None else [])+['--output',str(path)],env=env,deadline=50)
            if expired or code!=0 or not path.is_file() or path.stat().st_size>512000:raise ValueError('bounded worker failure')
            value=json.loads(path.read_bytes())
            if retain_proof and 'retained_proof' in value:
                from .four_council_proof import validate_audit
                validate_audit(value,(row['council'],row['semantics'],row['start'],row['end']))
            if profile is not None:
                from .source_profiles import validate_audit
                validate_audit(profile,value)
            return retain_screening(value)
    from verification.direct_reference.instrumented_probe import supervised
    case='discovery_'+row['council']+'_ui_window'
    with tempfile.TemporaryDirectory(prefix='discovery-finite-') as td:
        path=Path(td)/'source.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):
            supervised(case,path,**({'execution_mode':execution_mode} if execution_mode else {}),window=(row['start'],row['end']),**({'retain_proof':True} if retain_proof else {}),**({'execution_budget':execution_budget} if execution_budget is not None else {}))
        if not path.is_file() or path.stat().st_size>=65536:raise ValueError('bounded audit')
        value=json.loads(path.read_bytes())
        if retain_proof and 'retained_proof' in value:
            from .four_council_proof import validate_audit
            validate_audit(value,(row['council'],row['semantics'],row['start'],row['end']))
        if profile is not None:
            from .source_profiles import validate_audit
            validate_audit(profile,value)
        return retain_screening(value)

def classify(row,a,*,execution_budget=None,collection_profile=None):
    """Qualify retained count/criteria evidence; never infer success from HTTP/exit."""
    if a.get('requested_interval')!=[row['start'],row['end']]:return 'UNKNOWN'
    if row['council'] in ARCUS:
        if a.get('case')!='discovery_'+row['council']+'_ui_window':return 'UNKNOWN'
    elif a.get('council')!=row['council']:return 'UNKNOWN'
    if a.get('failure'):return 'FAILED'
    if a.get('date_semantics')!=row['semantics']:return 'UNKNOWN'
    if a.get('capped') or a.get('completeness')=='INCOMPLETE' or a.get('enumeration_evidence')=='PAGE_CAP':return 'INCOMPLETE'
    if a.get('applied_interval')!=[row['start'],row['end']]:return 'UNKNOWN'
    if row['council'] in ARCUS:
        config=dated_config(UI_CASES['discovery_'+row['council']+'_ui_window'],row['start'],row['end'])
        if collection_profile is not None:
            from .source_profiles import config as profile_config,validate_audit
            try:validate_audit(collection_profile,a);config=profile_config(collection_profile)
            except (ValueError,KeyError,TypeError):return 'UNKNOWN'
        try:validate_arcus(a,config,**({'execution_budget':execution_budget} if execution_budget is not None else {}))
        except (ValueError,KeyError,TypeError):return 'UNKNOWN'
        return 'COMPLETE'
    if (a.get('cleanup')!='SESSION_BOUNDARY_CLOSED' or a.get('enumeration_evidence')!='COUNT_RECONCILED'
        or not a.get('applied_evidence_sha256') or a.get('persistence') is not False):return 'UNKNOWN'
    pages=a.get('pages',[]);records=a.get('records',[])
    if not pages or len(pages)>6:return 'UNKNOWN'
    if not records:return 'COMPLETE' if a.get('explicit_zero_evidence') and pages[-1].get('total')==0 else 'UNKNOWN'
    refs=[r.get('reference') for r in records]
    if None in refs or len(set(refs))!=len(refs) or pages[-1].get('total')!=len(refs) or not pages[-1].get('terminal'):return 'UNKNOWN'
    return 'COMPLETE'

def execute(plan,expected_hash,reader=read,clock=time.monotonic):
    canonical=manifest(plan['start'],plan['end'],plan['purpose'])
    if plan!=canonical or digest(plan)!=expected_hash:raise ValueError('unreviewed manifest')
    if any(k in os.environ for k in ('DATABASE_URL','COMMITTEE_DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY')):raise ValueError('credential-free')
    started=clock();results=[];requests=body_bytes=0;stop=None;accounting_complete=True
    for row in plan['rows']:
        # Reserve worst-case cost before each child, never increase a cap.
        arc=row['council'] in ARCUS;rq=80 if arc else 10;by=20*1024*1024 if arc else 3_000_000
        if requests+rq>LIMITS['requests'] or body_bytes+by>LIMITS['bytes'] or clock()-started+55>LIMITS['seconds']:
            stop='ROUND_BUDGET';break
        observed_start=datetime.now(timezone.utc).isoformat()
        try:
            a=reader(row)
            a=dict(a,primary_observation=dict(started_at=observed_start,ended_at=datetime.now(timezone.utc).isoformat()))
        except Exception:
            accounting_complete=False
            results.append(dict(window=row,enumeration_completeness='FAILED',completeness='FAILED',reason='SOURCE_EXCEPTION'));stop='SOURCE_EXCEPTION';break
        resource=a if arc else a.get('resource',{})
        count=resource.get('requests',resource.get('requests_attempted'));size=(max(a.get('decoded_bytes',0),a.get('encoded_bytes',0))+a.get('outbound_payload_bytes',0)) if arc else resource.get('received_bytes')
        if type(count) is not int or type(size) is not int or not 0<=count<=rq or not 0<=size<=by:
            accounting_complete=False
            results.append(dict(window=row,enumeration_completeness='UNKNOWN',completeness='UNKNOWN',reason='RESOURCE_ACCOUNTING'));stop='RESOURCE_ACCOUNTING';break
        requests+=count;body_bytes+=size
        state=classify(row,a);results.append(dict(window=row,enumeration_completeness=state,completeness='UNKNOWN' if state=='COMPLETE' else state,source=a))
        if state!='COMPLETE':stop='NON_COMPLETE_CHILD';break
    if stop is None and clock()-started>LIMITS['seconds']:stop='ROUND_DEADLINE'
    complete=stop is None and len(results)==len(plan['rows']) and all(r['enumeration_completeness']=='COMPLETE' for r in results)
    state='COMPLETE' if complete else ('FAILED' if any(r['enumeration_completeness']=='FAILED' for r in results) else 'INCOMPLETE')
    out=dict(manifest_sha256=expected_hash,enumeration_completeness=state,completeness='UNKNOWN' if state=='COMPLETE' else state,source_contract_qualified=False,results=results,not_attempted=plan['rows'][len(results):],
        stop_reason=stop,accounting_complete=accounting_complete,requests=requests,bytes=body_bytes,persistence=False,completed_through_advanced=False)
    if len(json.dumps(out,default=str).encode())>LIMITS['output_bytes']:raise ValueError('bounded output exceeded')
    return out


def main():
    """Private child entry only; no registered round/acceptance authority."""
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--idox-worker',nargs=3,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--no-transport-retry',action='store_true');p.add_argument('--retain-four-council-proof',action='store_true');p.add_argument('--fixed-four-row-limit',action='store_true')
    p.add_argument('--campaign-scope');p.add_argument('--collection-profile')
    a=p.parse_args();c,start,end=a.idox_worker
    if a.fixed_four_row_limit and (not a.retain_four_council_proof or not a.no_transport_retry):raise ValueError('fixed row selection')
    if c not in COUNCILS-ARCUS or a.output.exists():raise ValueError('bounded child')
    if any(k in os.environ for k in ('DATABASE_URL','COMMITTEE_DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY')):raise ValueError('credential-free')
    from .four_council_proof import manifest_scope
    selected=json.loads(a.campaign_scope) if a.campaign_scope else None
    if selected is not None and (selected!=dict(council=c,semantics=SEMANTICS[c],start=start,end=end) or not a.fixed_four_row_limit):raise ValueError('CAMPAIGN_READER_BINDING')
    profile=json.loads(a.collection_profile) if a.collection_profile else None
    if profile is not None and selected is None:raise ValueError('PROFILE_REQUIRES_CAMPAIGN_SCOPE')
    with manifest_scope(selected,profile) if selected is not None else contextlib.nullcontext():
        result=live(WindowConfig(c,SEMANTICS[c],date.fromisoformat(start),date.fromisoformat(end),max_transport_retries=0 if a.no_transport_retry else 1,max_rows=60 if a.fixed_four_row_limit else None),**({'retain_proof':True} if a.retain_four_council_proof else {}))
        if profile is not None:
            from .source_profiles import bind_audit
            result=bind_audit(profile,result)
        raw=json.dumps(result,sort_keys=True).encode()
        if len(raw)>512000:raise ValueError('bounded child audit')
        if a.retain_four_council_proof:
            from .four_council_proof import write_audit
            write_audit(a.output,result)
        else:a.output.write_bytes(raw)
    return

if __name__=='__main__':main()
