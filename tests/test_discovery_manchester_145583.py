"""Single frozen Manchester caller; disposable DB only."""
from pathlib import Path
from unittest.mock import patch
import pytest
import yaml
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db.models import Application
from tests.test_discovery_admission import engine
from tests.test_discovery_committee_exact import seed,synthetic_source
from verification.discovery.manchester_145583 import cohort,execute,absence,WORKFLOW,AUTHORITY,admitted
from verification.discovery.committee_exact import _validate_cohort


def test_one_reference_and_no_other_source_call(engine):
    seed(engine);calls=[]
    def source(row,app_id):
        calls.append(row['reference']);return synthetic_source(row,app_id)
    assert [r['reference'] for r in cohort()]==['145583/FO/2026']
    _validate_cohort(cohort(),source)
    result=execute(engine,'disposable',source_retrieve=source)
    assert calls==['145583/FO/2026','145583/FO/2026']
    assert len(result)==1 and result[0]['transaction']=='COMMIT_READBACK_CONFIRMED'
    assert result[0]['verification_scope']=='INITIAL_STATUS_ONLY'
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Application))==1
        app=session.scalar(select(Application));assert app.site_id is None
    with patch('verification.discovery.manchester_145583._run_cohort',side_effect=AssertionError('duplicate admission')):
        with pytest.raises(RuntimeError,match='ALREADY_EXISTS_AT_EXECUTION'):execute(engine,'overlap')
    assert len(absence(engine))==1


def test_workflow_closed_and_shared_writer():
    w=yaml.load(Path(WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'transport','admission'}
    assert 'secrets.' not in str(w['jobs']['transport'])
    assert w['jobs']['admission']['needs']=='transport'
    assert w['jobs']['admission']['environment']=='stage4-production-canary'
    assert str(w).count('secrets.DATABASE_URL')==1
    env=dict(COMMITTEE_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',
        GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master')
    assert admitted('a'*40,AUTHORITY,env)
    assert not admitted('a'*40,AUTHORITY,dict(env,GITHUB_RUN_NUMBER='2'))
    assert not admitted('a'*40,AUTHORITY,dict(env,GITHUB_RUN_ATTEMPT='2'))
