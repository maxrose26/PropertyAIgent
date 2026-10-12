import copy
from pathlib import Path
from unittest.mock import patch
import pytest
from verification.direct_reference import oldham_production as p

SHA='a'*40

def env():
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_EVENT_NAME='workflow_dispatch',
      OLDHAM_WORKFLOW_SHA=SHA,GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
      GITHUB_RUN_ID='123',GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p.WORKFLOW+'@refs/heads/master')

@pytest.mark.parametrize('key,value',[('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('OLDHAM_WORKFLOW_SHA','b'*40),('GITHUB_EVENT_NAME','push'),('GITHUB_REPOSITORY','other/repo'),('GITHUB_WORKFLOW_REF','alternate')])
def test_admission_rejects(key,value):
    e=env();e[key]=value
    with pytest.raises(ValueError):p.admit(SHA,p.AUTHORITY,e)

def test_clean_sha_and_authority():
    with patch.object(p.subprocess,'check_output',side_effect=[SHA+'\n','']):p.admit(SHA,p.AUTHORITY,env())
    for outputs in ([SHA+'\n',' M dirty'],['b'*40,'']):
        with patch.object(p.subprocess,'check_output',side_effect=outputs),pytest.raises(ValueError):p.admit(SHA,p.AUTHORITY,env())
    with pytest.raises(ValueError):p.admit(SHA,'NOT_AUTHORISED',env())

def test_privacy_closed_schema():
    a=p.empty(SHA,'123');p.validate(a)
    for key in ('DATABASE_URL','headers','html','applicant','proposal'):
        b=copy.deepcopy(a);b[key]='private'
        with pytest.raises(ValueError):p.validate(b)
    for key,value in [('application_id',202),('source_url','https://elsewhere.invalid'),('source_provenance','FROZEN'),('error','credential=value')]:
        b=copy.deepcopy(a);b[key]=value
        with pytest.raises(ValueError):p.validate(b)

def test_no_frozen_loader_or_direct_writer():
    code=Path(p.__file__).read_text()
    assert 'frozen_observation' not in code and 'load_live' not in code
    assert '.commit(' not in code and '.add(' not in code and 'create_all(' not in code
    assert 'from .refresh import requests_session' in code
    assert 'validate(audit) # any failure' in code

def test_workflow_manual_minimum_secret():
    text=Path(p.WORKFLOW).read_text()
    assert 'workflow_dispatch:' in text and 'pull_request:' not in text and 'schedule:' not in text and '  push:' not in text
    assert text.count('secrets.')==1 and 'secrets.DATABASE_URL' in text
    assert 'contents: read' in text and 'persist-credentials: false' in text
    assert 'timeout-minutes: 3' in text and 'NOT_AUTHORISED' in text

@pytest.mark.parametrize('url',['','sqlite:///x','postgresql://x:y@localhost/postgres','postgresql://x:y@db.aaaaaaaaaaaaaaaaaaaa.supabase.co/other'])
def test_database_route_no_fallback(monkeypatch,url):
    monkeypatch.setenv('OLDHAM_DATABASE_URL',url)
    with pytest.raises(ValueError):p.production_engine()

def test_wrapper_transaction_local(session):
    from tests.test_stage4_direct_reference import add
    from verification.direct_reference.fixtures import Session,summary
    add(session)
    result=p.run_transaction(session.get_bind(),SHA,'123',lambda:Session(summary(p.REFERENCE,status='Decided',decision='Refuse Permission',date='Fri 25 Sep 2026')))
    assert result['transaction']=='COMMITTED',result
    assert result['materiality']=='MATERIAL'
    assert len(result['after']['events'])==1
