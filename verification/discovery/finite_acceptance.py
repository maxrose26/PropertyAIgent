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

def read(row):
    if row['council'] not in ARCUS:
        with tempfile.TemporaryDirectory(prefix='discovery-finite-idox-') as td:
            path=Path(td)/'source.json'
            env=dict(PATH='/usr/bin:/bin',HOME=td,TMPDIR=td,PYTHONDONTWRITEBYTECODE='1')
            code,expired=supervise([sys.executable,'-m','verification.discovery.finite_acceptance','--idox-worker',row['council'],row['start'],row['end'],'--output',str(path)],env=env,deadline=50)
            if expired or code!=0 or not path.is_file() or path.stat().st_size>512000:raise ValueError('bounded worker failure')
            return json.loads(path.read_bytes())
    from verification.direct_reference.instrumented_probe import supervised
    case='discovery_'+row['council']+'_ui_window'
    with tempfile.TemporaryDirectory(prefix='discovery-finite-') as td:
        path=Path(td)/'source.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):
            supervised(case,path,window=(row['start'],row['end']))
        if not path.is_file() or path.stat().st_size>=65536:raise ValueError('bounded audit')
        return json.loads(path.read_bytes())

def classify(row,a):
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
        try:validate_arcus(a,dated_config(UI_CASES['discovery_'+row['council']+'_ui_window'],row['start'],row['end']))
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
    a=p.parse_args();c,start,end=a.idox_worker
    if c not in COUNCILS-ARCUS or a.output.exists():raise ValueError('bounded child')
    if any(k in os.environ for k in ('DATABASE_URL','COMMITTEE_DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY')):raise ValueError('credential-free')
    result=live(WindowConfig(c,SEMANTICS[c],date.fromisoformat(start),date.fromisoformat(end)))
    raw=json.dumps(result,sort_keys=True).encode()
    if len(raw)>512000:raise ValueError('bounded child audit')
    a.output.write_bytes(raw)

if __name__=='__main__':main()
