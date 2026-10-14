"""Rejected scope observability; offline only, no new eligibility rules."""
import copy
from pathlib import Path
from unittest.mock import patch
import pytest
import yaml
from tests.test_discovery_committee_exact import synthetic_source
from verification.discovery.committee_exact import targets,validate_sources
from verification.discovery.rejection_audit import observation_audit
from verification.discovery.salford_diagnostic import diagnose,admitted,AUTHORITY,WORKFLOW


@pytest.mark.parametrize('state',['NOT_PRESENT','CONFLICTING','UNPARSEABLE','UNKNOWN','MISSING_FIELD'])
def test_rejected_observation_keeps_bounded_reason_without_changing_eligibility(state):
    row=targets()[0];resource=synthetic_source(row,None);obs=resource['observation']
    obs.b2_eligible=False
    if state=='MISSING_FIELD':obs.field_states.pop('status')
    else:obs.field_states['status']=state
    obs.literal_fields.pop('Status',None)
    obs.raw_html='private';obs.cookies='private';obs.literal_fields['Applicant']='private'
    before=copy.deepcopy(obs.__dict__)
    audit=observation_audit(row,resource)
    assert audit['b2_eligible'] is False and audit['field_states']['status']==state
    assert audit['rejection_reason']=='B2_EVIDENCE_SCOPE_INELIGIBLE'
    assert 'STATUS_'+state in audit['diagnostic_conditions']
    assert 'private' not in str(audit) and obs.__dict__==before
    progress=[]
    with pytest.raises(RuntimeError):validate_sources(lambda *_:resource,progress)
    assert progress[0]['observation_evidence']==audit or progress[0]['observation_evidence']['field_states']==audit['field_states']


def test_scope_and_literal_bounds_and_accepted_observation_unchanged():
    row=targets()[0];resource=synthetic_source(row,None);obs=resource['observation']
    before=copy.deepcopy(obs.__dict__);audit=observation_audit(row,resource)
    assert audit['rejection_reason'] is None and audit['b2_eligible'] is True
    assert obs.__dict__==before
    obs.b2_eligible=False;obs.verification_scope='unreviewed'
    assert 'UNSUPPORTED_VERIFICATION_SCOPE' in observation_audit(row,resource)['diagnostic_conditions']
    obs.literal_fields['Status']='x'*161
    with pytest.raises(ValueError,match='literal bound'):observation_audit(row,resource)


def test_diagnostic_exact_salford_only_no_database_or_admission():
    calls=[]
    def source(row,app_id):
        calls.append((row['council'],row['reference'],app_id))
        return synthetic_source(row,app_id)
    with patch('verification.discovery.committee_exact.checked_engine',side_effect=AssertionError('DB forbidden')),patch('verification.discovery.committee_exact.admit_identity',side_effect=AssertionError('admission forbidden')):
        audit=diagnose(source)
    assert calls==[('salford','PA/2025/1506',None)]
    assert audit['database_connections']==audit['database_reads']==audit['database_writes']==audit['admission_attempts']==0


def test_diagnostic_single_use_secret_free_workflow():
    workflow=yaml.load(Path(WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(workflow['on'])=={'workflow_dispatch'} and set(workflow['jobs'])=={'transport'}
    assert not any(x in str(workflow) for x in ('secrets.','DATABASE_URL','environment:','schedule:'))
    assert str(workflow).count(AUTHORITY)==2
    env=dict(DIAGNOSTIC_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',
        GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master')
    assert admitted('a'*40,AUTHORITY,env)
    for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('DATABASE_URL','never-read'),('SUPABASE_KEY','never-read')]:
        assert not admitted('a'*40,AUTHORITY,dict(env,**{key:value}))
