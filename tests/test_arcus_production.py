"""Admission and narrow schema scope only; no network/production credentials."""
from unittest.mock import MagicMock,patch
import pytest
from verification.direct_reference import arcus_production as p

SHA='a'*40

def admitted_env():
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',
        GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_REF='refs/heads/master',
        ARCUS_WORKFLOW_SHA=SHA,GITHUB_RUN_ID='123',
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p.WORKFLOW+'@refs/heads/master')

@pytest.mark.parametrize('key,value', [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),
    ('GITHUB_REF','refs/heads/other'),('ARCUS_WORKFLOW_SHA','b'*40),('GITHUB_RUN_ID','')])
def test_wrong_admission_fails_without_db(key,value):
    env=admitted_env();env[key]=value
    with patch.dict(p.os.environ,env,clear=True),patch.object(p,'production_engine') as db:
        with pytest.raises(ValueError):p.admit(SHA)
        db.assert_not_called()

def test_exact_clean_candidate_admitted():
    with patch.dict(p.os.environ,admitted_env(),clear=True),patch.object(p.subprocess,'check_output',side_effect=[SHA+'\n','']):p.admit(SHA)

@pytest.mark.parametrize('existing',[None,('text','YES',None)])
def test_only_additive_nullable_column_is_migrated(existing):
    engine=MagicMock();transaction=engine.begin.return_value.__enter__.return_value
    transaction.execute.return_value.one_or_none.return_value=existing
    engine.connect.return_value.__enter__.return_value.execute.return_value.one.return_value=('text','YES',None)
    with patch.object(p,'production_engine',return_value=engine):result=p.migrate_column()
    sql=[str(c.args[0]) for c in transaction.execute.call_args_list]
    assert all(not any(word in s.upper() for word in ('UPDATE ','DELETE ','INSERT ','DROP ')) for s in sql)
    assert sum(s.startswith('ALTER TABLE') for s in sql)==int(existing is None)
    assert result['backfill'] is False and result['readback']=='MATCH'
    engine.dispose.assert_called_once()

def test_catchup_requires_completed_same_invocation_validation(tmp_path):
    from verification.direct_reference import batch,arcus_batch
    proof=batch.run(SHA,'123-validation',lambda *_:None,spec=arcus_batch.CONTEXTS['validation'])
    file=tmp_path/'validation.json';file.write_bytes(batch.encode(proof))
    with patch.dict(p.os.environ,dict(GITHUB_RUN_ID='123'),clear=True):
        with pytest.raises(ValueError,match='FAMILY_NOT_OPERATIONAL'):p.execute(SHA,'catchup_a',tmp_path/'out.json',file)

@pytest.mark.parametrize('timeout,appname',[(60001,'stage4_arcus_b2_once'),(60000,'unrelated')])
def test_database_idle_extension_is_closed(timeout,appname):
    from verification.direct_reference.oldham_production import production_engine
    with pytest.raises(ValueError,match='DB_IDLE'):
        production_engine(application_name=appname,idle_transaction_ms=timeout)

def test_workflow_manual_only_and_credentials_confined():
    import yaml
    from pathlib import Path
    w=yaml.load(Path(p.WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'live'}
    assert w['permissions']=={'contents':'read'}
    assert w['concurrency']['cancel-in-progress']=='false'
    job=w['jobs']['live'];assert job['environment']=='stage4-production-canary'
    assert 'env' not in w and 'env' not in job
    secrets=[step for step in job['steps'] if 'secrets.' in str(step)]
    assert len(secrets)==1
    assert secrets[0]['env']['BATCH_DATABASE_URL']=='${{ secrets.DATABASE_URL }}'
    run=secrets[0]['run']
    assert run.index('run_arcus --migrate')<run.index('run_arcus --phase validation')<run.index('for phase')
    assert '--validation' in run and 'env -i ' in run
    assert 'trafford' not in run.lower()
