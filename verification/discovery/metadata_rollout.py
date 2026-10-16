"""Single-use,13-observation sequential listing-only authority. No DB interface."""
import argparse
from datetime import datetime,timezone
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from .screening_assessment import PROFILE,assess
ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/'docs/design/stage4-r0-execution/metadata-rollout-20261016'
WORKFLOW='.github/workflows/stage4-metadata-rollout-once.yml'
AUTHORITY='AUTHORISE_METADATA_13_SEQUENTIAL_20261016_ONCE'
MANIFEST_SHA='db867ad45e1425c603edd9729efe1127f2eb6a38998baf0cbdcf8631b79bd5d1'


def manifest():
    raw=(PACK/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('MANIFEST_REJECTED')
    return json.loads(raw)


def scope(index):
    if type(index) is not int or not 0<=index<13:raise ValueError('SCOPE_REJECTED')
    return manifest()['scopes'][index]


def plan(index):
    scope(index)
    return dict(scope='metadata-rollout',index=index,manifest_sha256=MANIFEST_SHA,
                limits={k:PROFILE[k] for k in ('calls','requests','bytes','seconds','output_bytes')})


def validate_plan(value):
    if value!=plan(value.get('index')):raise ValueError('PLAN_REJECTED')
    return PROFILE


def admit(sha,mh,authority,env,index,workflow_bytes=None):
    from .r0_fixed80_qualification import credential_free
    credential_free(env);scope(index)
    expected=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',
        GITHUB_JOB=f'scope_{index:02d}',SCOPE_INDEX=str(index),PREVIOUS_GO='GENESIS' if index==0 else 'GO')
    if (not re.fullmatch('[0-9a-f]{40}',sha or '') or mh!=MANIFEST_SHA or authority!=AUTHORITY
        or any(env.get(k)!=v for k,v in expected.items())):raise ValueError('BINDING_REJECTED')
    if not re.fullmatch('[0-9]{10}',env.get('JOB_STARTED_EPOCH','')) or not 0<=time.time()-int(env['JOB_STARTED_EPOCH'])<=260:
        raise ValueError('SETUP_BOUND')
    raw=(ROOT/WORKFLOW).read_bytes() if workflow_bytes is None else workflow_bytes
    if raw!=(PACK/'registered-workflow.yml.txt').read_bytes():raise ValueError('WORKFLOW_CONTENT')


def read(index):
    from verification.direct_reference.instrumented_probe import supervised
    s=scope(index)
    with tempfile.TemporaryDirectory(prefix='metadata-rollout-') as td:
        p=Path(td)/'source.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):
            supervised(s['case'],p,window=(s['start'],s['end']),metadata=True)
        if not p.is_file() or p.stat().st_size>=512000:raise ValueError('SOURCE_AUDIT_BOUND')
        source=json.loads(p.read_bytes())
    return source


def evaluate(source,index):
    from .arcus_ui_config import METADATA_ROLLOUT_CONFIGS
    from .arcus_ui_window import qualify_segment
    s=scope(index);config=METADATA_ROLLOUT_CONFIGS[s['case']]
    certain=True
    try:
        for row in source.get('listing_records',[]):
            fields=[dict(label='Reference',value=row['reference'])]
            if config.row_date:fields.append(dict(label='Valid Date',value=row['validated_date']['literal']))
            card=dict(fields=fields,links=[dict(text=row['reference'],href=row['source_url'])],assessment_capture=row['assessment_capture'])
            qualified=qualify_segment('Showing 1 to 1 of 1 results',[card],1,config=config)[3][0]
            if qualified!=row:raise ValueError('ROW_PROJECTION_OR_IDENTITY')
    except (ValueError,KeyError,TypeError):certain=False
    result=assess(source,config=config,case=s['case'],interval=[s['start'],s['end']],historical_context=s['historical_context'])
    result.update(scope_index=index,council=s['council'],window=[s['start'],s['end']],purpose=s['purpose'],row_evidence_revalidated=certain)
    if not certain:result.update(outcome='NO_GO',stop_reason='ROW_EVIDENCE_NOT_REVALIDATED')
    return result


def execute_worker(value,output,audit_dir):
    from .r0_registered_scopes import AuditStore
    from .r0_fixed80_qualification import credential_free
    credential_free(os.environ);validate_plan(value)
    index=value['index'];s=scope(index);store=AuditStore(audit_dir,PROFILE)
    started=datetime.now(timezone.utc).isoformat();source=read(index)
    source['primary_observation']=dict(started_at=started,ended_at=datetime.now(timezone.utc).isoformat())
    store.record(source)
    result=evaluate(source,index)
    store.finish(result,output)


def verify(directory,env,index):
    from .r0_registered_scopes import audit_bytes
    scope(index)
    if audit_bytes(directory)>PROFILE['output_bytes']:raise ValueError('AUDIT_BOUND')
    for p in directory.rglob('*'):
        if p.is_file() and p.relative_to(directory).as_posix() not in {'execution.json','result.json','checkpoints/000.json'}:raise ValueError('AUDIT_PATH')
    meta=json.loads((directory/'execution.json').read_bytes())
    if meta!=dict(sha=env['GITHUB_SHA'],run_id=env['GITHUB_RUN_ID'],manifest_sha256=MANIFEST_SHA,scope_index=index,run_number=1,attempt=1,persistence=False):raise ValueError('EXECUTION_IDENTITY')
    result=json.loads((directory/'result.json').read_bytes())
    hashes=result.get('checkpoint_sha256',[])
    if hashes:
        p=directory/'checkpoints/000.json'
        if hashes!=[hashlib.sha256(p.read_bytes()).hexdigest()]:raise ValueError('CHECKPOINT_HASH')
    if result.get('outcome')=='GO':
        expected=evaluate(json.loads((directory/'checkpoints/000.json').read_bytes()),index)
        if any(result.get(k)!=v for k,v in expected.items()):raise ValueError('RESULT_CHECKPOINT_READBACK')
    return result


def require_go(result,index):
    outer=result.get('outer_supervisor',{})
    if (result.get('outcome')!='GO' or result.get('scope_index')!=index or result.get('stop_reason') is not None
        or result.get('row_evidence_revalidated') is not True or result.get('accounting_complete') is not True or len(result.get('checkpoint_sha256',[]))!=1
        or outer.get('cleanup')!='CLOSED' or outer.get('live_owned_survivors')!=0
        or outer.get('expired') is not False or outer.get('limit_hit') is not None or outer.get('exit_code')!=0
        or type(outer.get('peak_owned_rss')) is not int or not 0<=outer['peak_owned_rss']<=1536*1024**2
        or not isinstance(outer.get('elapsed_seconds'),(int,float)) or not 0<=outer['elapsed_seconds']<60):
        raise ValueError('GLOBAL_STOP_NO_SUCCESSOR')


def main():
    from .r0_fixed80_qualification import credential_free
    from .r0_registered_scopes import checkout
    credential_free(os.environ)
    p=argparse.ArgumentParser();p.add_argument('--reviewed-sha');p.add_argument('--manifest-sha');p.add_argument('--authority')
    p.add_argument('--scope',type=int);p.add_argument('--worker',type=Path);p.add_argument('--audit-dir',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--verify-audit',action='store_true');p.add_argument('--require-go',action='store_true');a=p.parse_args()
    if a.verify_audit or a.require_go:
        result=verify(a.output,os.environ,a.scope)
        if a.require_go:require_go(result,a.scope)
        return
    if a.worker:
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE,(PROFILE['output_bytes'],PROFILE['output_bytes']))
        if a.worker.stat().st_size>20000 or a.output.exists() or a.audit_dir is None:raise ValueError('WORKER_CONTEXT')
        execute_worker(json.loads(a.worker.read_bytes()),a.output,a.audit_dir);return
    admit(a.reviewed_sha,a.manifest_sha,a.authority,os.environ,a.scope);checkout(a.reviewed_sha)
    a.output.mkdir(exist_ok=False)
    (a.output/'execution.json').write_text(json.dumps(dict(sha=a.reviewed_sha,run_id=os.environ['GITHUB_RUN_ID'],manifest_sha256=MANIFEST_SHA,scope_index=a.scope,run_number=1,attempt=1,persistence=False)))
    from .r0_proposal import supervise_round
    result=supervise_round(plan(a.scope),a.output/'result.json',deadline=60,worker_module='verification.discovery.metadata_rollout')
    require_go(result,a.scope)

if __name__=='__main__':raise SystemExit(main())
