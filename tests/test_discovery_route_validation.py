"""Synthetic inputs only; never uses a real secret or database."""
import json
from pathlib import Path
import traceback
from unittest.mock import patch
import pytest
import yaml
from verification.discovery.route_validation import validate_route,route_audit,RouteRejection,CODES
from verification.discovery.route_preflight import evaluate,admitted,AUTHORITY,WORKFLOW
from verification.discovery.committee_exact import checked_engine

BASE='postgresql+psycopg://postgres.zcikcfgpblzuzpanpdqd:synthetic-only@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'

@pytest.mark.parametrize('raw',[BASE,BASE.replace('postgresql+psycopg://','postgresql://'),BASE.replace('postgresql+psycopg://','postgres://'),BASE.replace(':5432/postgres','/postgres')])
def test_equivalent_routes_use_existing_normalizer(raw):
    with patch('app.db.session.create_engine',side_effect=AssertionError('pure validator engine')):
        u=validate_route(raw)
    assert (u.drivername,u.host,u.port,u.database,u.username)==('postgresql+psycopg','aws-0-eu-west-2.pooler.supabase.com',5432,'postgres','postgres.zcikcfgpblzuzpanpdqd')
    with patch('verification.discovery.committee_exact.create_engine',return_value=object()) as factory:
        checked_engine(raw)
    assert factory.call_count==1
    assert factory.call_args.kwargs['connect_args']['sslmode']=='require'
    assert factory.call_args.kwargs['connect_args']['options']=='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=40000'

@pytest.mark.parametrize('raw,code',[
 (BASE.replace('postgresql+psycopg','postgresql+psycopg2'),'DRIVER_MISMATCH'),
 (BASE.replace('aws-0-eu-west-2.pooler.supabase.com','other.invalid'),'HOST_MISMATCH'),
 (BASE.replace(':5432/',':6543/'),'PORT_MISMATCH'),
 (BASE.replace('/postgres','/other'),'DATABASE_MISMATCH'),
 (BASE.replace('postgres.zcikcfgpblzuzpanpdqd:','other:'),'USERNAME_MISMATCH'),
 (BASE+'?secret=DO_NOT_EXPORT','QUERY_FORBIDDEN'),
 ('password=DO_NOT_EXPORT','MALFORMED_INPUT'),
 (BASE.replace(':5432/',':DO_NOT_EXPORT/'),'MALFORMED_INPUT'),
 (None,'MALFORMED_INPUT')])
def test_rejection_is_safe_before_engine(raw,code):
    with patch('verification.discovery.committee_exact.create_engine',side_effect=AssertionError('engine')) as factory:
        with pytest.raises(RouteRejection) as caught:checked_engine(raw)
    assert factory.call_count==0 and caught.value.code==code
    formatted=''.join(traceback.format_exception(caught.type,caught.value,caught.tb))
    assert 'DO_NOT_EXPORT' not in formatted
    audit=route_audit(raw)
    assert audit==dict(phase='REJECTED_BEFORE_ENGINE_CREATION',result='REJECTED',reason_code=code,driver_normalization_applied=None,default_port_applied=None)
    assert 'DO_NOT_EXPORT' not in json.dumps(audit)


def test_connection_free_entry_has_no_capabilities():
    with patch('app.db.session.create_engine',side_effect=AssertionError('engine')):
        result=evaluate(BASE)
    assert result['route_validation']['phase']=='ROUTE_VALIDATED_NO_ENGINE'
    assert result['authentication']==result['connectivity']=='NOT_TESTED'
    assert all(result[k]==0 for k in ('database_connections','production_reads','production_writes','source_requests','admission_calls'))
    assert not result['engine_construction']
    assert 'synthetic-only' not in json.dumps(result)


def test_registered_template_and_single_use_controls():
    assert Path(WORKFLOW).read_text()==Path('verification/discovery/proposals/stage4-route-preflight-once.yml.txt').read_text()
    w=yaml.load(Path('verification/discovery/proposals/stage4-route-preflight-once.yml.txt').read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'preflight'}
    assert w['jobs']['preflight']['environment']=='stage4-production-canary'
    assert str(w).count('secrets.DATABASE_URL')==1
    assert 'ah-offline-route-preflight.py' in str(w)
    assert w['permissions']=={'contents':'read'}
    assert w['concurrency']=={'group':'stage4-knownref-closure-production','cancel-in-progress':'false'}
    assert w['jobs']['preflight']['timeout-minutes']=='5'
    steps=w['jobs']['preflight']['steps']
    assert len(steps)==5
    assert 'GITHUB_RUN_NUMBER' in steps[0]['run'] and 'GITHUB_RUN_ATTEMPT' in steps[0]['run']
    assert 'env -i' in steps[3]['run']
    assert 'DATABASE_URL' not in str(steps[:3])
    assert 'DATABASE_URL' not in str(steps[4:])
    env=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_SHA='a'*40,PREFLIGHT_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master')
    assert admitted('a'*40,AUTHORITY,env)
    assert not admitted('a'*40,AUTHORITY,dict(env,GITHUB_RUN_ATTEMPT='2'))


def test_admission_main_rejection_audit_never_enters_execution(tmp_path,monkeypatch):
    from verification.discovery import material_admission as m
    import sys
    output=tmp_path/'audit.json'
    monkeypatch.setattr(sys,'argv',['caller','--sha','a'*40,'--authority','test','--manifest-sha',m.MANIFEST_SHA,'--output',str(output)])
    monkeypatch.setenv('COMMITTEE_DATABASE_URL','DO_NOT_EXPORT')
    monkeypatch.setenv('GITHUB_RUN_ID','offline')
    with patch.object(m,'admitted',return_value=True),patch.object(m.subprocess if hasattr(m,'subprocess') else __import__('subprocess'),'check_output',return_value='a'*40),patch.object(m,'checked_engine',side_effect=AssertionError('engine')),patch.object(m,'execute',side_effect=AssertionError('execution')):
        with pytest.raises(RuntimeError,match='ADMISSION_STOP_NO_RETRY'):m.main()
    data=json.loads(output.read_text())
    assert data['phase']=='REJECTED_BEFORE_ENGINE_CREATION' and data['results']==[]
    assert data['execution']=='REJECTED_BEFORE_ENGINE_CREATION_NO_TRANSACTION'
    assert 'DO_NOT_EXPORT' not in output.read_text()


def test_seccomp_entrypoint_synthetic_subprocess(tmp_path):
    import os,subprocess,sys
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    output=tmp_path/'preflight.json'
    env=dict(PATH='/usr/bin:/bin',PYTHONDONTWRITEBYTECODE='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_SHA=sha,PREFLIGHT_WORKFLOW_SHA=sha,
        GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master',
        GITHUB_RUN_ID='synthetic-offline',PREFLIGHT_DATABASE_URL=BASE.replace('postgresql+psycopg://','postgresql://').replace(':5432/postgres','/postgres'))
    result=subprocess.run([sys.executable,'verification/ah-offline-route-preflight.py','--sha',sha,'--authority',AUTHORITY,'--output',str(output)],env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==0 and not result.stdout and 'synthetic-only' not in result.stderr
    audit=json.loads(output.read_text())
    assert audit['route_validation']['result']=='COMPATIBLE'
    assert audit['route_validation']['driver_normalization_applied'] is True
    assert audit['route_validation']['default_port_applied'] is True
    assert audit['database_connections']==0 and not audit['engine_construction']
    assert 'synthetic-only' not in output.read_text()


def test_post_validation_exception_chain_is_safe(tmp_path,monkeypatch):
    from verification.discovery import material_admission as m
    import sys
    output=tmp_path/'audit.json'
    monkeypatch.setattr(sys,'argv',['caller','--sha','a'*40,'--authority','test','--manifest-sha',m.MANIFEST_SHA,'--output',str(output)])
    monkeypatch.setenv('COMMITTEE_DATABASE_URL',BASE);monkeypatch.setenv('GITHUB_RUN_ID','offline')
    with patch.object(m,'admitted',return_value=True),patch('subprocess.check_output',return_value='a'*40),patch.object(m,'checked_engine',side_effect=RuntimeError('DO_NOT_EXPORT')):
        with pytest.raises(RuntimeError) as caught:m.main()
    assert 'DO_NOT_EXPORT' not in ''.join(traceback.format_exception(caught.type,caught.value,caught.tb))
    audit=json.loads(output.read_text())
    assert audit['phase']=='ENGINE_CONSTRUCTION_STARTED'
    assert audit['execution']=='STOP_UNCERTAIN_OR_FAILED_NO_RETRY'
    assert audit['engine_cleanup']=='NOT_CREATED'
