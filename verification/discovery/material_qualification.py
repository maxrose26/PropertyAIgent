"""Single-use fixed-five source qualification; no database or admission capability."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

MANIFEST_SHA='d706bcaf106e973e6a44cd94268c11ed653d16ff70f2efa3bf953c46fa7c6abe'
WORKFLOW='.github/workflows/stage4-material-cohort-qualification-once.yml'
AUTHORITY='AUTHORISE_FIXED_FIVE_COMMITTEE_SOURCE_QUALIFICATION_ONCE'
IDENTITIES=(('bolton','21080/25'),('manchester','143413/FO/2025'),
            ('manchester','145583/FO/2026'),('salford','PA/2025/1664'),('tameside','26/00396/FUL'))
IDOX_CASES={'material_qualification_1','material_qualification_5'}
HARD_FAILURES={'CLEANUP_FAILURE','SCOPE_ESCAPE','ACCOUNTING_FAILURE','INVALID_ARTIFACT','UNSUPPORTED_ROUTE'}


def targets():
    raw=Path(__file__).with_name('material-qualification-targets.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('manifest digest')
    rows=json.loads(raw)['targets']
    if tuple((x['council'],x['reference']) for x in rows)!=IDENTITIES:raise ValueError('fixed identities')
    return rows


def case_definitions():
    return {r['case']:(None,r['reference'],r['source_url']) for r in targets()}


def admitted(sha,authority,env):
    return (bool(re.fullmatch('[0-9a-f]{40}',sha)) and authority==AUTHORITY
        and env.get('COMMITTEE_WORKFLOW_SHA')==sha and env.get('GITHUB_REF')=='refs/heads/master'
        and env.get('GITHUB_RUN_NUMBER')=='1' and env.get('GITHUB_RUN_ATTEMPT')=='1'
        and env.get('GITHUB_EVENT_NAME')=='workflow_dispatch'
        and env.get('GITHUB_REPOSITORY')=='maxrose26/PropertyAIgent'
        and env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted'
        and env.get('GITHUB_WORKFLOW_REF')=='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master')


def credential_free(env):
    if any('DATABASE' in k or k.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')) for k in env):
        raise ValueError('credential forbidden')


def idox_worker(row):
    from verification.direct_reference.refresh import _retrieve_row,requests_session,Budget
    from verification.direct_reference.batch_supervisor import resource_limits
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    resource_limits()
    budget=Budget(request_limit=2,byte_limit=2_000_000,seconds=40)
    result=dict(case=row['case'],reference=row['reference'],destination=row['source_url'],
                application_id=None,persistence=False,observation=None,failure=None)
    start=time.monotonic();diagnostic={}
    try:
        observation=_retrieve_row(row,None,session_factory=requests_session,budget=budget,diagnostic=diagnostic)
        allowed={'Reference','Status','Decision','Decision Issued Date'}
        if (set(observation.fields)!=allowed or any(v is not None and
                (not isinstance(v,str) or len(v)>160) for v in observation.literal_fields.values())):
            raise ValueError('bounded factual literals')
        result['observation']=asdict(observation)
    except BoundaryFailure as exc:
        result['failure']=exc.outcome
    except Exception:
        result['failure']='PARSER_FAILURE'
    if result['failure'] is not None:
        from .source_diagnostics import shape
        result['failure_diagnostic']=shape(diagnostic.get('body',b''),diagnostic.get('stage','UNKNOWN'),result['failure'])
    result.update(requests=budget.requests,received_body_bytes=budget.bytes,
                  elapsed_seconds=round(time.monotonic()-start,3),retrieved_at=datetime.now(timezone.utc).isoformat())
    return result


def project_idox(row,source):
    """Validate minimized output from the SAME bounded Idox parser/transport."""
    from verification.direct_reference.refresh import Observation
    audit={k:source.get(k) for k in ('requests','received_body_bytes','elapsed_seconds','supervisor_seconds',
        'peak_owned_rss','owned_processes_seen','live_owned_survivors','retrieved_at')}
    closed=source.get('process_cleanup')=='CLOSED' and source.get('live_owned_survivors')==0
    audit['cleanup_state']='CLOSED' if closed else 'FAILED'
    bounds={'requests':2,'received_body_bytes':2_000_000,'peak_owned_rss':1024**3,
            'owned_processes_seen':256,'live_owned_survivors':0}
    bounded=all(type(source.get(k)) is int and 0<=source[k]<=limit for k,limit in bounds.items())
    bounded=bounded and all(type(source.get(k)) in (int,float) and math.isfinite(source[k])
            and 0<=source[k]<=45 for k in ('elapsed_seconds','supervisor_seconds'))
    bounded=bounded and source.get('supervisor_limit_hit') is False
    audit['budget_state']='WITHIN_LIMITS' if bounded else 'EXHAUSTED'
    if 'failure_diagnostic' in source:
        from .source_diagnostics import validate
        try:audit['failure_diagnostic']=validate(source['failure_diagnostic'])
        except ValueError:return dict(observation=None,audit=audit,failure='INVALID_ARTIFACT')
    def failed(code):return dict(observation=None,audit=audit,failure=code)
    if not closed:return failed('CLEANUP_FAILURE')
    if not bounded:return failed('ACCOUNTING_FAILURE')
    if (source.get('case')!=row['case'] or source.get('reference')!=row['reference']
            or source.get('destination')!=row['source_url'] or source.get('application_id') is not None
            or source.get('persistence') is not False):return failed('INVALID_ARTIFACT')
    if source.get('failure'):
        allowed_failures=HARD_FAILURES|{'AMBIGUOUS_SOURCE_RESULT','PARSER_FAILURE','PARTIAL_RETRIEVAL',
                                     'TIMEOUT','SOURCE_UNAVAILABLE','RATE_LIMITED'}
        return failed(source['failure'] if source['failure'] in allowed_failures else 'INVALID_ARTIFACT')
    data=source.get('observation')
    try:
        obs=Observation(**data)
        labels={'Reference','Status','Decision','Decision Issued Date'}
        states={'PRESENT_VALUE','PRESENT_BLANK','NOT_PRESENT','CONFLICTING','UNPARSEABLE','UNKNOWN'}
        if (set(obs.fields)!=labels or not set(obs.literal_fields)<=labels
            or set(obs.field_states)!={'reference','status','decision','decision_date'}
            or not set(obs.field_states.values())<=states or obs.verification_scope!='COUPLED'
            or obs.field_evidence is not None or type(obs.b2_eligible) is not bool
            or any(v is not None and (not isinstance(v,str) or len(v)>160)
                   for v in list(obs.fields.values())+list(obs.literal_fields.values()))):
            return failed('INVALID_ARTIFACT')
        if (obs.application_id is not None or obs.reference!=row['reference'] or obs.source_url!=row['source_url']
            or obs.fields.get('Reference')!=row['reference'] or obs.literal_fields.get('Reference')!=row['reference']
            or obs.field_states.get('reference')!='PRESENT_VALUE' or not obs.literal_verified
            or not re.fullmatch('[0-9a-f]{64}',obs.body_sha256)):
            return failed('AMBIGUOUS_SOURCE_RESULT')
    except (TypeError,ValueError,AttributeError):return failed('INVALID_ARTIFACT')
    audit['source_sha256']=obs.body_sha256
    return dict(observation=obs,audit=audit,failure=None)


def retrieve(row,application_id=None):
    if application_id is not None:raise ValueError('qualification only')
    if row['platform_family']=='ARCUS':
        from .committee_exact import retrieve as arcus_retrieve
        return arcus_retrieve(row,None)
    from verification.direct_reference.instrumented_probe import supervised
    import contextlib
    with tempfile.TemporaryDirectory(prefix='material-qualification-') as directory:
        path=Path(directory)/'audit.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):supervised(row['case'],path)
        if not path.is_file() or path.stat().st_size>=65536:
            return dict(observation=None,audit={},failure='INVALID_ARTIFACT')
        source=json.loads(path.read_bytes())
    return project_idox(row,source)


def qualify(source_retrieve=retrieve,results=None):
    from .rejection_audit import observation_audit
    results=[] if results is None else results
    for row in targets():
        resource=source_retrieve(row,None)
        evidence=observation_audit(row,resource)
        supported=(resource.get('failure') is None and resource.get('observation') is not None
                   and resource['observation'].literal_verified and resource['observation'].b2_eligible)
        results.append(dict(council=row['council'],reference=row['reference'],source=resource['audit'],
                            observation_evidence=evidence,failure=resource.get('failure'),
                            outcome='QUALIFIED_FOR_FREEZE_REVIEW' if supported else 'WITHHELD_FROM_FREEZE'))
        if (resource.get('failure') in HARD_FAILURES or resource['audit'].get('cleanup_state')!='CLOSED'
                or resource['audit'].get('budget_state')!='WITHIN_LIMITS'):
            raise RuntimeError('source resource/security/cleanup boundary; no subsequent source')
    return results


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha');p.add_argument('--authority');p.add_argument('--output',required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--case',choices=IDOX_CASES)
    a=p.parse_args();credential_free(os.environ)
    if Path(a.output).exists():raise ValueError('existing output')
    if a.worker:
        if not a.case:raise ValueError('fixed worker case required')
        row=next(r for r in targets() if r['case']==a.case)
        Path(a.output).write_text(json.dumps(idox_worker(row))+'\n');return
    if not a.sha or not admitted(a.sha,a.authority,os.environ):raise ValueError('single use not admitted')
    import subprocess
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.sha:
        raise ValueError('exact checkout')
    audit=dict(sha=a.sha,manifest_sha=MANIFEST_SHA,run_id=os.environ['GITHUB_RUN_ID'],
        production_database_connections=0,production_reads=0,production_writes=0,applications_created=0,
        model_calls=0,admission_cohort_frozen=False,results=[],execution='UNKNOWN')
    try:
        qualify(results=audit['results']);audit['execution']='ASSESSMENT_COMPLETED_NOT_ADMISSION'
    except BaseException:
        audit['execution']='STOP_NO_RETRY';raise
    finally:
        raw=json.dumps(audit,sort_keys=True,default=str)
        if len(raw.encode())>65536:raise ValueError('audit bound')
        Path(a.output).write_text(raw+'\n')

if __name__=='__main__':main()
