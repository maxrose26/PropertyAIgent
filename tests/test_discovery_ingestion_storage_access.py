"""Pure checks for new catalogue-only access path; never production credentials."""
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from verification.ingestion_storage.preflight import admitted,AUTHORITY,WORKFLOW,QUERIES,HASHES,run,verdict


def test_single_use_exact_context_and_package():
 sha='a'*40;env={'GITHUB_SHA':sha,'GITHUB_WORKFLOW_SHA':sha,'GITHUB_REF':'refs/heads/master','GITHUB_REPOSITORY':'maxrose26/PropertyAIgent','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_RUN_NUMBER':'1','GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKFLOW_REF':'maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master'}
 assert admitted(sha,AUTHORITY,env)
 for k in env:assert not admitted(sha,AUTHORITY,{**env,k:'wrong'})
 assert not admitted(sha,'AUTHORISE_METADATA_13_SEQUENTIAL_20261016_ONCE',env)
 import hashlib
 for p,d in HASHES.items():assert hashlib.sha256(Path('docs/design/ingestion-readiness-20261016',p).read_bytes()).hexdigest()==d


def test_only_catalogue_queries_and_no_migration_scope():
 for sql in QUERIES.values():
  assert sql.startswith('SELECT ') and not any(x in sql.upper() for x in ['INSERT ','DELETE ','UPDATE ','APPLICATIONS','SET ROLE','CREATE ','DROP '])
 workflow=Path(WORKFLOW).read_text()
 assert 'stage4-production-canary' in workflow and 'timeout-minutes: 2' in workflow
 assert 'secrets.DATABASE_URL' in workflow and workflow.count('secrets.')==1
 assert 'cancel-in-progress: false' in workflow


def test_rejected_route_never_constructs_engine_and_redacts_secret(tmp_path):
 factory=MagicMock();out=tmp_path/'out';r=run('postgresql://private_password@unapproved.invalid/db',out,engine_factory=factory)
 factory.assert_not_called();assert r['connections']==0 and r['production_writes']==0
 assert 'private_password' not in (out/'result.json').read_text()


def test_connection_failure_sanitized_disposal_and_no_fallback(tmp_path):
 engine=MagicMock();engine.connect.side_effect=RuntimeError('private_password');factory=MagicMock(return_value=engine)
 r=run('postgresql://postgres.zcikcfgpblzuzpanpdqd:private_password@aws-0-eu-west-2.pooler.supabase.com:5432/postgres',tmp_path/'out',engine_factory=factory)
 assert engine.connect.call_count==1 and engine.dispose.call_count==1
 assert 'private_password' not in (tmp_path/'out/result.json').read_text()
 kwargs=factory.call_args.kwargs['connect_args'];assert kwargs['sslmode']=='verify-full' and kwargs['prepare_threshold'] is None and kwargs['connect_timeout']==3


def test_missing_restricted_access_blocks_migration():
 session={'identity':[{'current_user':'postgres'}],'roles':[dict(rolname='postgres',rolsuper=False,rolcreaterole=True)],'objects':[dict(items=None,attempts=None,seed=None,stop=None)],'privileges':[dict(public_create=True)]}
 r=verdict([session,{}]);assert r['compatibility']=='BLOCKED' and not r['migration_executed']
 assert any('ingestion_worker_login' in b for b in r['blockers'])


def fake_engine():
 engine=MagicMock();c=engine.connect.return_value.__enter__.return_value
 data={'identity':[dict(current_user='postgres',read_only='on',isolation='read committed')], 'roles':[dict(rolname='postgres',rolsuper=False,rolcreaterole=True)],'privileges':[dict(public_create=True)],'objects':[dict(items=None,attempts=None,seed=None,stop=None)],'memberships':[],'defaults':[]}
 def execute(sql):
  r=MagicMock();r.mappings.return_value.all.return_value=next((v for k,v in data.items() if QUERIES[k]==sql),[]);return r
 c.exec_driver_sql.side_effect=execute;c.connection.driver_connection.pgconn.ssl_in_use=True
 return engine


@pytest.mark.parametrize('failure',['close','dispose'])
def test_failed_close_or_dispose_never_claims_closed(tmp_path,failure):
 engine=fake_engine()
 if failure=='close':engine.connect.return_value.__exit__.side_effect=RuntimeError('close failed')
 else:engine.dispose.side_effect=RuntimeError('dispose failed')
 r=run('postgresql://postgres.zcikcfgpblzuzpanpdqd:x@aws-0-eu-west-2.pooler.supabase.com:5432/postgres',tmp_path/'out',engine_factory=lambda *a,**k:engine)
 assert r['cleanup']=='UNCERTAIN'
 if failure=='dispose':assert r['pool_disposed'] is False


def test_second_connect_stores_intent_before_activity(tmp_path):
 engine=fake_engine();calls=[]
 def connect():
  saved=json.loads((tmp_path/'out/result.json').read_text());calls.append(saved)
  assert saved['status']=='CONNECTION_INTENT' and saved['cleanup']=='UNKNOWN'
  return engine.connect.return_value
 engine.connect.side_effect=connect
 r=run('postgresql://postgres.zcikcfgpblzuzpanpdqd:x@aws-0-eu-west-2.pooler.supabase.com:5432/postgres',tmp_path/'out',engine_factory=lambda *a,**k:engine)
 assert len(calls)==2 and calls[1]['connection_attempts']==2 and calls[1]['connections']==1
 assert r['cleanup']=='CLOSED' and r['connections']==2 and r['production_writes']==0
