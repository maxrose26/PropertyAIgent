"""Frozen three-record shared caller; disposable inputs/databases only."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import pytest
import yaml
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db.models import Application,Council
from tests.test_discovery_admission import engine
from tests.test_discovery_committee_exact import seed
from verification.direct_reference.refresh import Observation
from verification.discovery.material_admission import cohort,execute,retrieve,current_identity,admitted,AUTHORITY,MANIFEST_SHA,WORKFLOW,IDENTITIES


def seed_material(engine):
    seed(engine)
    with Session(engine) as s:
        s.add(Council(code='tameside',name='Tameside',base_url='https://publicaccess.tameside.gov.uk/online-applications',date_field_mode='validated',doc_system='idox'));s.commit()


def source(row,app_id):
    pending=row['reference']=='145583/FO/2026'
    tameside=row['council']=='tameside'
    fields={'Reference':row['reference'],'Status':'Under Consideration' if pending else 'Decided' if tameside else 'Final',
        'Decision':None if pending else 'Approve','Decision Issued Date':None if pending else '2026-07-28' if tameside else '2026-09-28'}
    states=dict(reference='PRESENT_VALUE',status='PRESENT_VALUE',decision='UNKNOWN' if pending else 'PRESENT_VALUE',decision_date='UNKNOWN' if pending else 'PRESENT_VALUE')
    literals={k:v for k,v in fields.items() if v is not None}
    if tameside:literals['Decision Issued Date']='Tue 28 Jul 2026'
    obs=Observation(app_id,row['reference'],row['source_url'],fields,states,'UNKNOWN_UNMAPPED' if pending else 'granted','a'*64,literals,
        b2_eligible=True,verification_scope='INITIAL_STATUS_ONLY' if pending else 'COUPLED')
    obs.field_evidence={k:dict(state=states[k],value=literals.get(label)) for k,label in
        {'reference':'Reference','status':'Status','decision':'Decision','decision_date':'Decision Issued Date'}.items()}
    return dict(observation=obs,failure=None,audit=dict(cleanup_state='CLOSED',budget_state='WITHIN_LIMITS'))


def test_frozen_three_supported_only_and_workflow_bounds():
    assert tuple((r['council'],r['reference']) for r in cohort())==IDENTITIES
    assert all('documents/' in r['trigger_url'] or 'ieListDocuments.aspx' in r['trigger_url'] for r in cohort())
    assert cohort()[2]['trigger_sha256']=='66fb4b05f108ff7ffac17e824a29afddabcfae55feeae5d58c74b05c75f0698e'
    w=yaml.load(Path(WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'admission'}
    assert set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','authority','manifest_sha256'}
    job=w['jobs']['admission'];assert job['environment']=='stage4-production-canary'
    assert job['timeout-minutes']=='8' and str(job).count('secrets.DATABASE_URL')==1
    assert 'qualify(' not in Path('verification/discovery/material_admission.py').read_text()
    env=dict(COMMITTEE_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master')
    assert admitted('a'*40,AUTHORITY,MANIFEST_SHA,env)
    assert not admitted('a'*40,AUTHORITY,'b'*64,env)
    assert not admitted('a'*40,AUTHORITY,MANIFEST_SHA,dict(env,GITHUB_RUN_ATTEMPT='2'))


def test_actual_id_projection_preserves_all_source_evidence():
    row=cohort()[2];resource=source(row,None);original=resource['observation']
    with patch('verification.discovery.material_admission.source_retrieve',return_value=resource):
        projected=retrieve(row,1234)['observation']
    assert projected.application_id==1234 and original.application_id is None
    assert replace(projected,application_id=None)==original
    assert projected.literal_fields['Decision Issued Date']=='Tue 28 Jul 2026'
    bad=source(row,None);bad['observation'].reference='WRONG'
    with patch('verification.discovery.material_admission.source_retrieve',return_value=bad),pytest.raises(ValueError):retrieve(row,1234)


def test_shared_three_admission_scope_date_unknown_and_duplicates(engine):
    seed_material(engine)
    result=execute(engine,'offline',retrieve_evidence=source)
    assert [r['outcome'] for r in result]==['CREATED']*3
    assert [r['verification_scope'] for r in result]==['COUPLED','INITIAL_STATUS_ONLY','COUPLED']
    assert all(r['transaction']=='COMMIT_READBACK_CONFIRMED' for r in result)
    assert result[2]['readback']['decision_issued_date']=='2026-07-28'
    assert all(r['readback']['site_id'] is None and r['readback']['unit_confirmation_status']=='discovery_pending' for r in result)
    again=execute(engine,'overlap',retrieve_evidence=lambda *_:pytest.fail('known source request'))
    assert all(r['outcome']=='ALREADY_EXISTS_AT_EXECUTION' for r in again)
    assert all(r['transaction']=='READ_ONLY_EXISTENCE_CONFIRMED' for r in again)
    with Session(engine) as s:assert s.scalar(select(func.count()).select_from(Application))==3


def test_record_local_safe_rejection_does_not_become_fact_verification(engine):
    seed_material(engine);calls=[]
    def local(row,app_id):
        calls.append(row['reference'])
        if len(calls)==1:return dict(observation=None,failure='AMBIGUOUS_SOURCE_RESULT',audit=dict(cleanup_state='CLOSED',budget_state='WITHIN_LIMITS'))
        return source(row,app_id)
    results=execute(engine,'offline',retrieve_evidence=local)
    assert len(results)==len(calls)==3
    first=results[0];assert first['transaction']=='COMMIT_READBACK_CONFIRMED'
    assert first['planning_observation']=='AMBIGUOUS_SOURCE_RESULT'
    assert first['readback']['status'] is None and first['readback']['status_verified_at'] is None
    assert first['admission']['outcome']=='CREATED_PENDING' # identity created from already-qualified frozen evidence; no facts certified


def test_resource_failure_stops_and_uncertain_commit_never_retries(engine):
    seed_material(engine);progress=[]
    def failed(row,app_id):return dict(observation=None,failure='CLEANUP_FAILURE',audit=dict(cleanup_state='FAILED',budget_state='WITHIN_LIMITS'))
    with pytest.raises(RuntimeError,match='source supervision unresolved'):execute(engine,'offline',results=progress,retrieve_evidence=failed)
    assert len(progress)==1 and progress[0]['transaction']=='COMMIT_READBACK_CONFIRMED'


def test_uncertain_identity_commit_preserves_provenance_and_stops(engine):
    from app.pipeline.discovery_admission import admit_identity,UncertainDiscoveryCommit
    seed_material(engine);calls=[];progress=[]
    def controlled(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise UncertainDiscoveryCommit('synthetic lost acknowledgement')
        return admit_identity(*args,**kwargs)
    with patch('verification.discovery.committee_exact.admit_identity',side_effect=controlled):
        with pytest.raises(UncertainDiscoveryCommit):execute(engine,'offline',progress,source)
    assert len(progress)==len(calls)==2
    assert progress[1]['transaction']=='IDENTITY_ADMISSION_STARTED_UNCONFIRMED'
    assert progress[1]['trigger_provenance']['sha256_subject']=='RETAINED_OFFICER_REPORT_BYTES'


def test_tameside_trigger_audit_distinguishes_report_from_container(engine):
    seed_material(engine);result=execute(engine,'offline',retrieve_evidence=source)
    proof=result[2]['admission']['trigger']['provenance_qualification']
    assert proof['direct_report_url']=='UNKNOWN'
    assert proof['sha256_subject']=='RETAINED_OFFICER_REPORT_BYTES'
    assert proof['report_sha256']=='66fb4b05f108ff7ffac17e824a29afddabcfae55feeae5d58c74b05c75f0698e'
    assert 'ieListDocuments.aspx' in proof['source_container_or_document_url']
