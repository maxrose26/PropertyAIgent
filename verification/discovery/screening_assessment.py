"""One fixed credential-free Manchester listing assessment, no DB interface."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import contextlib
import time

ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/'docs/design/stage4-r0-execution/manchester-screening-assessment-20261016'
WORKFLOW='.github/workflows/stage4-manchester-screening-assessment-once.yml'
AUTHORITY='AUTHORISE_MANCHESTER_METADATA_20261001_03_ONCE'
MANIFEST_SHA='8c253cad894841ab7161eff6bf371ad747c7cffce6246253059398e7d8d98931'
PROFILE=dict(calls=1,requests=80,bytes=20*1024*1024,seconds=60,output_bytes=2*1024*1024,
             record_output_bytes=512000,setup_seconds=260,job_seconds=480)


def manifest():
    raw=(PACK/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('MANIFEST_REJECTED')
    return json.loads(raw)


def plan():
    manifest()
    return dict(scope='manchester-screening',manifest_sha256=MANIFEST_SHA,
                limits={k:PROFILE[k] for k in ('calls','requests','bytes','seconds','output_bytes')})


def validate_plan(value):
    if value!=plan():raise ValueError('PLAN_REJECTED')
    return PROFILE


def admit(sha,mh,authority,env,workflow_bytes=None):
    from .r0_fixed80_qualification import credential_free
    credential_free(env)
    expected=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1')
    if (not re.fullmatch('[0-9a-f]{40}',sha or '') or mh!=MANIFEST_SHA or authority!=AUTHORITY
        or any(env.get(k)!=v for k,v in expected.items())):raise ValueError('BINDING_REJECTED')
    if not re.fullmatch('[0-9]{10}',env.get('JOB_STARTED_EPOCH','')) or not 0<=time.time()-int(env['JOB_STARTED_EPOCH'])<=260:
        raise ValueError('SETUP_BOUND')
    raw=(ROOT/WORKFLOW).read_bytes() if workflow_bytes is None else workflow_bytes
    if raw!=(PACK/'registered-workflow.yml.txt').read_bytes():raise ValueError('WORKFLOW_CONTENT')
    manifest()


def assess(source):
    from .arcus_ui_config import SCREENING_CONFIG,SCREENING_CASE
    from .arcus_ui_audit import validate
    from .arcus_ui_transport import combined_bytes
    from .screening_capture import screen_row
    enumeration='UNKNOWN'
    try:
        if source.get('case')!=SCREENING_CASE or source.get('requested_interval')!=['2026-10-01','2026-10-03']:
            raise ValueError('SOURCE_IDENTITY')
        validate(source,SCREENING_CONFIG);enumeration='COMPLETE'
    except (ValueError,KeyError,TypeError):
        enumeration='INCOMPLETE' if source.get('listing_records') else 'FAILED'
    resource_ok=(type(source.get('requests')) is int and 0<=source['requests']<=80
        and all(type(source.get(k)) is int and source[k]>=0 for k in ('decoded_bytes','encoded_bytes','outbound_payload_bytes'))
        and combined_bytes(source)<=20*1024*1024
        and source.get('process_cleanup')=='CLOSED' and source.get('cleanup')=='CONTEXT_BROWSER_CLOSED'
        and source.get('live_owned_survivors')==0 and source.get('supervisor_limit_hit') is False
        and type(source.get('peak_owned_rss')) is int and 0<=source['peak_owned_rss']<=1024**3
        and isinstance(source.get('supervisor_seconds'),(int,float)) and 0<=source['supervisor_seconds']<=45)
    rows=source.get('listing_records',[])
    screens=[];missing={};truncated={}
    for row in rows:
        if 'fields' not in row:
            row=dict(row,fields={k:dict(state='UNKNOWN',value=None) for k in ('proposal','address','application_type','received_date','validated_date')})
        fields=row['fields'];screen=screen_row(row)
        screens.append(dict(reference=row['reference'],source_record_id=row['source_record_id'],source_url=row['source_url'],screen=screen))
    for key in ('proposal','address','application_type','received_date','validated_date'):
        missing[key]=dict(Counter(r.get('fields',{}).get(key,{}).get('state','UNKNOWN') for r in rows))
        truncated[key]=sum(bool(r.get('fields',{}).get(key,{}).get('truncated')) for r in rows)
    usable=sum(r['screen']['proposal_usable'] for r in screens)
    citation_overflow=any(r['screen']['citations']['overflow'] for r in screens)
    full=enumeration=='COMPLETE' and resource_ok and bool(rows) and usable==len(rows) and not citation_overflow and not any(truncated.values())
    outcome='NO_GO' if not resource_ok else 'GO' if full else 'PARTIAL' if enumeration=='COMPLETE' or usable else 'NO_GO'
    historic={r['reference'] for r in manifest()['historical_context']};current={r['reference'] for r in rows}
    return dict(outcome=outcome,enumeration_outcome=enumeration,proposal_capture=dict(rows=len(rows),usable=usable,full_mechanism_success=full),
        field_states=missing,truncated=truncated,citation_complete=bool(rows) and usable==len(rows) and not citation_overflow and not any(truncated.values()),
        rows=screens,screening_dispositions=dict(Counter(r['screen']['disposition'] for r in screens)),
        observation_difference=dict(historical_only=sorted(historic-current),current_only=sorted(current-historic),
            meaning='CROSS_OBSERVATION_DIFFERENCE_NOT_RETROSPECTIVE_MISS_OR_ABSENCE'),
        accounting_complete=resource_ok,requests=source.get('requests'),bytes=combined_bytes(source) if resource_ok else None,
        persistence=False,completed_through_advanced=False,independent_publication_coverage='UNKNOWN',
        stop_reason=None if resource_ok and enumeration=='COMPLETE' else 'SOURCE_OR_ACCOUNTING_NOT_COMPLETE')


def read():
    from verification.direct_reference.instrumented_probe import supervised
    from .arcus_ui_config import SCREENING_CASE
    with tempfile.TemporaryDirectory(prefix='screen-assessment-') as td:
        p=Path(td)/'source.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):
            supervised(SCREENING_CASE,p,window=('2026-10-01','2026-10-03'),metadata=True)
        if not p.is_file() or p.stat().st_size>=512000:raise ValueError('SOURCE_AUDIT_BOUND')
        source=json.loads(p.read_bytes())
    return source


def execute_worker(value,output,audit_dir):
    from .r0_registered_scopes import AuditStore
    from .r0_fixed80_qualification import credential_free
    credential_free(os.environ);validate_plan(value)
    store=AuditStore(audit_dir,PROFILE)
    started=datetime.now(timezone.utc).isoformat()
    source=read()
    source['primary_observation']=dict(started_at=started,ended_at=datetime.now(timezone.utc).isoformat())
    store.record(source)
    result=assess(source)
    store.finish(result,output)


def verify(directory,env):
    from .r0_registered_scopes import audit_bytes
    if audit_bytes(directory)>PROFILE['output_bytes']:raise ValueError('AUDIT_BOUND')
    for p in directory.rglob('*'):
        if p.is_file() and p.relative_to(directory).as_posix() not in {'execution.json','result.json','checkpoints/000.json'}:
            raise ValueError('AUDIT_PATH')
    meta=json.loads((directory/'execution.json').read_bytes())
    if meta!=dict(sha=env['GITHUB_SHA'],run_id=env['GITHUB_RUN_ID'],manifest_sha256=MANIFEST_SHA,run_number=1,attempt=1,persistence=False):
        raise ValueError('EXECUTION_IDENTITY')
    result=json.loads((directory/'result.json').read_bytes())
    if result.get('checkpoint_sha256'):
        p=directory/'checkpoints/000.json'
        if result['checkpoint_sha256']!=[hashlib.sha256(p.read_bytes()).hexdigest()]:raise ValueError('CHECKPOINT_HASH')
    return result


def main():
    from .r0_fixed80_qualification import credential_free
    from .r0_registered_scopes import checkout
    credential_free(os.environ)
    p=argparse.ArgumentParser();p.add_argument('--reviewed-sha');p.add_argument('--manifest-sha');p.add_argument('--authority')
    p.add_argument('--worker',type=Path);p.add_argument('--audit-dir',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verify-audit',action='store_true');a=p.parse_args()
    if a.verify_audit:verify(a.output,os.environ);return
    if a.worker:
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE,(PROFILE['output_bytes'],PROFILE['output_bytes']))
        if a.worker.stat().st_size>20000 or a.output.exists() or a.audit_dir is None:raise ValueError('WORKER_CONTEXT')
        execute_worker(json.loads(a.worker.read_bytes()),a.output,a.audit_dir);return
    admit(a.reviewed_sha,a.manifest_sha,a.authority,os.environ);checkout(a.reviewed_sha)
    a.output.mkdir(exist_ok=False)
    (a.output/'execution.json').write_text(json.dumps(dict(sha=a.reviewed_sha,run_id=os.environ['GITHUB_RUN_ID'],manifest_sha256=MANIFEST_SHA,run_number=1,attempt=1,persistence=False)))
    from .r0_proposal import supervise_round
    result=supervise_round(plan(),a.output/'result.json',deadline=60,worker_module='verification.discovery.screening_assessment')
    return 1 if result.get('stop_reason') else 0

if __name__=='__main__':raise SystemExit(main())
