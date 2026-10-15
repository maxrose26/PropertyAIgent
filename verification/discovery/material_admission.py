"""Frozen three-record caller of shared identity admission and sole factual B2."""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.db.models import Application
from .committee_exact import checked_engine,_run_cohort
from .material_qualification import targets as qualification_targets,retrieve as source_retrieve

MANIFEST_SHA='91be2de17f9e7fd0f4e62c7e95b611ef91bb1484673191f489f928b9879e5981'
WORKFLOW='.github/workflows/stage4-material-cohort-admission-once.yml'
AUTHORITY='AUTHORISE_THREE_QUALIFIED_MATERIAL_COHORT_ADMISSIONS_ONCE'
IDENTITIES=(('manchester','143413/FO/2025'),('manchester','145583/FO/2026'),('tameside','26/00396/FUL'))


def cohort():
    raw=Path(__file__).with_name('material-admission-targets.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('manifest digest')
    data=json.loads(raw);rows=data['targets']
    if (tuple((r['council'],r['reference']) for r in rows)!=IDENTITIES
            or data['qualification_run']!='38652271830'
            or data['qualification_json_sha256']!='08d646d0ccae55aa5d35a66848b893b7ae82cdf0ce3b6a2c64ae620f21ee4e59'):
        raise ValueError('frozen qualification identity')
    originals={(r['council'],r['reference']):r for r in qualification_targets()}
    for r in rows:
        prior=originals[(r['council'],r['reference'])]
        if any(r[k]!=prior[k] for k in ('case','source_identifier','source_url','platform_family')):
            raise ValueError('qualified destination changed')
        if r['site_relationship']!='UNKNOWN' or r['application_role']!='UNKNOWN':
            raise ValueError('relationship uncertainty')
    return rows


def admitted(sha,authority,manifest_sha,env):
    return (bool(re.fullmatch('[0-9a-f]{40}',sha)) and authority==AUTHORITY and manifest_sha==MANIFEST_SHA
        and env.get('COMMITTEE_WORKFLOW_SHA')==sha and env.get('GITHUB_REF')=='refs/heads/master'
        and env.get('GITHUB_EVENT_NAME')=='workflow_dispatch'
        and env.get('GITHUB_REPOSITORY')=='maxrose26/PropertyAIgent'
        and env.get('GITHUB_RUN_NUMBER')=='1' and env.get('GITHUB_RUN_ATTEMPT')=='1'
        and env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted'
        and env.get('GITHUB_WORKFLOW_REF')=='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master')


def retrieve(row,application_id):
    """Fresh existing source evidence; the source worker never receives a DB ID/key."""
    resource=source_retrieve(row,None)
    obs=resource.get('observation')
    if obs is not None:
        if (obs.application_id is not None or obs.reference!=row['reference']
                or obs.source_url!=row['source_url'] or not obs.literal_verified):
            raise ValueError('source projection identity')
        resource=dict(resource,observation=replace(obs,application_id=application_id))
    return resource


def current_identity(engine,row):
    with Session(engine) as s:
        if engine.dialect.name=='postgresql':
            s.execute(text('SET TRANSACTION READ ONLY'))
            s.execute(text("SET LOCAL statement_timeout = '10s'"))
        records=s.execute(select(Application.id,Application.council_code,Application.reference)
            .where(Application.council_code==row['council'],Application.reference==row['reference']).limit(2)).mappings().all()
        if len(records)>1:raise RuntimeError('duplicate identity; stop without creation')
        return [dict(r) for r in records]


def execute(engine,run_id,results=None,retrieve_evidence=retrieve):
    results=[] if results is None else results
    for row in cohort():
        before=current_identity(engine,row)
        if before:
            results.append(dict(council=row['council'],reference=row['reference'],outcome='ALREADY_EXISTS_AT_EXECUTION',
                application_id=before[0]['id'],transaction='READ_ONLY_EXISTENCE_CONFIRMED',before=before,
                planning_observation='NOT_ATTEMPTED',site_relationship='UNKNOWN',application_role='UNKNOWN'))
            continue
        # The shared transaction independently rechecks exact identity and uses
        # ON CONFLICT + committed readback. A race does not reset existing facts.
        offset=len(results)
        try:
            _run_cohort(engine,run_id,(row,),source_retrieve=retrieve_evidence,results=results)
        finally:
            if len(results)>offset:
                # Also retained if identity commit/B2 later becomes uncertain.
                results[offset]['trigger_provenance']=dict(
                    evidence_type=row['trigger_evidence_type'],source_container_or_document_url=row['trigger_url'],
                    sha256_subject='RETAINED_OFFICER_REPORT_BYTES',report_sha256=row['trigger_sha256'],
                    direct_report_url=row.get('committee_direct_report_url',row['trigger_url']),
                    portal_identity_sha256=row['portal_evidence_fingerprint'])
                if results[offset].get('admission'):
                    results[offset]['admission']['trigger']['provenance_qualification']=results[offset]['trigger_provenance']
        result=results[offset]
        result.update(pre_admission_absence_check='NO_MATCH_EXACT_COUNCIL_REFERENCE_LIMIT_2',
                      site_relationship='UNKNOWN',application_role='UNKNOWN')
        result['outcome']='CREATED' if result['admission']['outcome']=='CREATED_PENDING' else 'ALREADY_EXISTS_AT_EXECUTION'
    return results


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--authority',required=True)
    p.add_argument('--manifest-sha',required=True);p.add_argument('--output',required=True)
    a=p.parse_args()
    if not admitted(a.sha,a.authority,a.manifest_sha,os.environ):raise ValueError('single use not admitted')
    import subprocess
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.sha:
        raise ValueError('exact checkout')
    if Path(a.output).exists():raise ValueError('existing audit')
    engine=None
    audit=dict(sha=a.sha,manifest_sha=MANIFEST_SHA,run_id=os.environ['GITHUB_RUN_ID'],
        qualification_run='38652271830',results=[],model_calls=0,completed_through_advanced=False,
        site_creation=False,opportunity_creation=False,execution='UNKNOWN')
    try:
        from .route_validation import route_audit,RouteRejection
        audit['route_validation']=route_audit(os.environ.get('COMMITTEE_DATABASE_URL',''))
        if audit['route_validation']['result']=='REJECTED':
            raise RouteRejection(audit['route_validation']['reason_code']) from None
        audit['phase']='ENGINE_CONSTRUCTION_STARTED'
        engine=checked_engine(os.environ['COMMITTEE_DATABASE_URL'])
        audit['phase']='ENGINE_CREATED_NO_CONNECTION_ASSERTION'
        audit['phase']='ADMISSION_EXECUTION_STARTED'
        execute(engine,audit['run_id'],results=audit['results'])
        audit['phase']='EXECUTION_COMPLETED'
        audit['execution']='COMPLETED'
    except BaseException:
        if audit.get('route_validation',{}).get('result')=='REJECTED':
            audit['phase']='REJECTED_BEFORE_ENGINE_CREATION'
            audit['execution']='REJECTED_BEFORE_ENGINE_CREATION_NO_TRANSACTION'
        else:
            audit['execution']='STOP_UNCERTAIN_OR_FAILED_NO_RETRY'
        # Fixed exception only: never expose a secret-bearing exception chain.
        raise RuntimeError('ADMISSION_STOP_NO_RETRY') from None
    finally:
        cleanup_failed=False
        audit['engine_cleanup']='NOT_CREATED' if engine is None else 'PENDING'
        if engine is not None:
            try:
                engine.dispose();audit['engine_cleanup']='DISPOSED'
            except BaseException:
                cleanup_failed=True
                audit['engine_cleanup']='FAILED'
                audit['execution']='CLEANUP_FAILED_NO_RETRY'
        raw=json.dumps(audit,sort_keys=True,default=str)
        if len(raw.encode())>65536:raise ValueError('audit bound')
        Path(a.output).write_text(raw+'\n')
        if cleanup_failed:raise RuntimeError('ADMISSION_CLEANUP_STOP_NO_RETRY') from None

if __name__=='__main__':main()
