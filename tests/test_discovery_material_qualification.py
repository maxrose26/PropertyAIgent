"""Fixed-five source-only boundary; no live source or production DB calls."""
from dataclasses import asdict
from pathlib import Path
import pytest
import yaml
from tests.test_discovery_committee_exact import synthetic_source
from verification.discovery.material_qualification import targets,qualify,admitted,credential_free,project_idox,AUTHORITY,WORKFLOW,IDENTITIES


def test_fixed_cohort_and_automatic_future_admission_boundary():
    assert tuple((r['council'],r['reference']) for r in targets())==IDENTITIES
    assert all(r['reference']!='PA/2025/1506' for r in targets())
    assert not Path('.github/workflows/stage4-manchester-145583-admission-once.yml').exists()
    w=yaml.load(Path(WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'transport'}
    assert 'secrets.' not in str(w) and 'environment' not in w['jobs']['transport']
    assert w['jobs']['transport']['timeout-minutes']=='8'
    assert 'admit_identity' not in Path('verification/discovery/material_qualification.py').read_text()


def test_run_attempt_master_repository_and_credential_controls():
    env=dict(COMMITTEE_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',
        GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master')
    assert admitted('a'*40,AUTHORITY,env)
    for k,v in [('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','push'),('GITHUB_REPOSITORY','other/repo')]:
        assert not admitted('a'*40,AUTHORITY,dict(env,**{k:v}))
    for key in ('DATABASE_URL','COMMITTEE_DATABASE_URL','SUPABASE_SERVICE_KEY','OPENAI_API_KEY'):
        with pytest.raises(ValueError):credential_free({key:'do-not-export'})


def test_record_local_rejection_preserves_evidence_and_continues():
    calls=[]
    def source(row,app_id):
        assert app_id is None;calls.append(row['reference'])
        if row['council']=='bolton':
            return dict(observation=None,failure='TIMEOUT',audit=dict(cleanup_state='CLOSED',budget_state='WITHIN_LIMITS'))
        result=synthetic_source(row,app_id)
        if row['council']=='salford':result['observation'].b2_eligible=False
        return result
    result=qualify(source)
    assert len(calls)==5 and len(result)==5
    assert result[0]['outcome']==result[3]['outcome']=='WITHHELD_FROM_FREEZE'
    assert result[3]['observation_evidence']['b2_eligible'] is False
    assert result[1]['outcome']=='QUALIFIED_FOR_FREEZE_REVIEW'


@pytest.mark.parametrize('failure',['CLEANUP_FAILURE','SCOPE_ESCAPE','ACCOUNTING_FAILURE','INVALID_ARTIFACT'])
def test_hard_failure_stops_next_source(failure):
    calls=[];progress=[]
    def source(row,_):
        calls.append(row['reference']);return dict(observation=None,failure=failure,
                audit=dict(cleanup_state='CLOSED',budget_state='WITHIN_LIMITS'))
    with pytest.raises(RuntimeError):qualify(source,progress)
    assert len(calls)==len(progress)==1


def idox_audit(row):
    obs=synthetic_source(row,None)['observation']
    data={k:v for k,v in vars(obs).items() if k!='field_evidence'}
    data['semantic_state']='UNKNOWN_UNMAPPED'
    data['verification_scope']='COUPLED'
    return dict(case=row['case'],reference=row['reference'],destination=row['source_url'],application_id=None,
        persistence=False,observation=data,failure=None,requests=1,received_body_bytes=500,
        elapsed_seconds=1.0,supervisor_seconds=1.1,peak_owned_rss=100000,owned_processes_seen=1,
        live_owned_survivors=0,process_cleanup='CLOSED',supervisor_limit_hit=False)


def test_idox_projection_identity_resources_and_literal_audit():
    row=targets()[0];data=idox_audit(row)
    assert project_idox(row,data)['observation'].reference==row['reference']
    data['observation']['fields']['Reference']='WRONG'
    assert project_idox(row,data)['failure']=='AMBIGUOUS_SOURCE_RESULT'
    data=idox_audit(row);data['live_owned_survivors']=1
    assert project_idox(row,data)['failure']=='CLEANUP_FAILURE'
    data=idox_audit(row);data['received_body_bytes']=2_000_001
    assert project_idox(row,data)['failure']=='ACCOUNTING_FAILURE'


def test_idox_worker_reuses_existing_transport_and_excludes_raw_payload(monkeypatch):
    from verification.discovery.material_qualification import idox_worker
    from verification.direct_reference.refresh import Observation
    monkeypatch.setattr('verification.direct_reference.batch_supervisor.resource_limits',lambda:None)
    row=targets()[0]
    def same_transport(r,app_id,*,session_factory,budget):
        assert r is row and app_id is None and budget.request_limit==2 and budget.seconds==40
        budget.requests=1;budget.bytes=500
        return Observation(None,r['reference'],r['source_url'],
            {'Reference':r['reference'],'Status':'Decided','Decision':'Approve subject to conditions','Decision Issued Date':'2026-08-21'},
            dict(reference='PRESENT_VALUE',status='PRESENT_VALUE',decision='PRESENT_VALUE',decision_date='PRESENT_VALUE'),
            'granted','a'*64,{'Reference':r['reference'],'Status':'Decided','Decision':'Approve subject to conditions','Decision Issued Date':'Fri 21 Aug 2026'},b2_eligible=True)
    monkeypatch.setattr('verification.direct_reference.refresh._retrieve_row',same_transport)
    result=idox_worker(row)
    assert result['observation']['b2_eligible'] is True and result['requests']==1
    assert 'raw' not in str(result) and result['persistence'] is False
