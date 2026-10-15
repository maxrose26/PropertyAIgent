"""Exact reviewed registrations: two capabilities, no interchangeable context."""
import hashlib
from pathlib import Path
import pytest
import yaml
from verification.discovery import r0_identity_comparison as c
from verification.discovery import r0_recovery_proposal as r

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs/design/stage4-r0-execution/executable-proposals'
PINS={
    'comparison':(c.WORKFLOW,'comparison-workflow.yml','e69dce37d39310549c376e976325daf0f7725e924e387f29e220fd1253c9a7c2'),
    'recovery':(r.WORKFLOW,'recovery-workflow.yml','9a7d50267abe60c11113d9edcf20e062f41e1f83a58760679924e09688f2e4bc'),
}


def assert_registered(kind,text):
    _,_,digest=PINS[kind]
    assert hashlib.sha256(text.encode()).hexdigest()==digest
    w=yaml.load(text,Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'}
    assert set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha','authority'}
    assert w['permissions']=={'contents':'read'}
    assert w['concurrency']['cancel-in-progress']=='false'
    assert 'env' not in w
    jobname='comparison' if kind=='comparison' else 'observation'
    assert set(w['jobs'])=={jobname}
    job=w['jobs'][jobname]
    assert 'env' not in job and job['runs-on']=='ubuntu-24.04'
    checkout=next(s for s in job['steps'] if s.get('uses')=='actions/checkout@v4')
    assert checkout['with']=={'ref':'${{ inputs.reviewed_sha }}','persist-credentials':'false'}
    if kind=='comparison':
        assert job['environment']=='stage4-production-canary' and job['timeout-minutes']=='5'
        assert text.count('secrets.')==1
        secret=[s for s in job['steps'] if 'secrets.' in str(s)]
        assert len(secret)==1 and secret[0]['env']['COMPARISON_DATABASE_URL']=='${{ secrets.DATABASE_URL }}'
        assert secret[0]['env']['GITHUB_WORKFLOW_SHA']=='${{ github.workflow_sha }}'
        assert 'verification.discovery.r0_identity_comparison' in secret[0]['run']
        assert '60s' in secret[0]['run']
    else:
        assert 'environment' not in job and job['timeout-minutes']=='38'
        assert 'secrets.' not in text and 'DATABASE_URL' not in text
        parents=[s for s in job['steps'] if 'env' in s]
        assert len(parents)==2
        assert all(s['env']['GITHUB_WORKFLOW_SHA']=='${{ github.workflow_sha }}' for s in parents)
        assert 'verification.discovery.r0_recovery_proposal' in parents[-1]['run']
        assert '1930s' in parents[-1]['run']
    return w


@pytest.mark.parametrize('kind',PINS)
def test_registered_exact_template_and_controls(kind):
    path,template,_=PINS[kind]
    assert (ROOT/path).read_bytes()==(DOC/template).read_bytes()
    assert_registered(kind,(ROOT/path).read_text())


@pytest.mark.parametrize('kind,old,new',[
    ('comparison','stage4-production-canary','other-environment'),
    ('comparison','${{ secrets.DATABASE_URL }}','${{ secrets.OTHER_SECRET }}'),
    ('comparison','60s','600s'),
    ('comparison','${{ github.workflow_sha }}','${{ github.sha }}'),
    ('recovery','1930s','3930s'),
    ('recovery','verification.discovery.r0_recovery_proposal','verification.discovery.r0_proposal'),
    ('recovery','${{ github.workflow_sha }}','${{ github.sha }}'),
    ('recovery','    runs-on:','    environment: stage4-production-canary\n    runs-on:'),
    ('recovery','persist-credentials: false','persist-credentials: true'),
])
def test_registered_mutations_fail_closed(kind,old,new):
    path,_,_=PINS[kind];text=(ROOT/path).read_text();assert old in text
    with pytest.raises(AssertionError):assert_registered(kind,text.replace(old,new))


def context(module):
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_REF='refs/heads/master',GITHUB_SHA='a'*40,
        GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',
        GITHUB_WORKFLOW_REF=f'maxrose26/PropertyAIgent/{module.WORKFLOW}@refs/heads/master')


def test_actual_comparison_execution_environment_mapping():
    w=assert_registered('comparison',(ROOT/c.WORKFLOW).read_text())
    step=next(s for s in w['jobs']['comparison']['steps'] if 'COMPARISON_DATABASE_URL' in s.get('env',{}))
    values={'${{ inputs.reviewed_sha }}':'a'*40,'${{ inputs.authority }}':c.AUTHORITY,
            '${{ inputs.manifest_sha }}':c.MANIFEST_SHA,'${{ github.workflow_sha }}':'a'*40,
            '${{ secrets.DATABASE_URL }}':'synthetic-not-connected'}
    mapped={k:values[v] for k,v in step['env'].items()};env=dict(context(c),**mapped)
    c.admit(env,mapped['PIN'],mapped['MANIFEST_SHA'],mapped['AUTHORITY'])
    for key,value in [('GITHUB_WORKFLOW_SHA',None),('GITHUB_WORKFLOW_SHA','b'*40),
                      ('GITHUB_SHA','b'*40),('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),
                      ('GITHUB_WORKFLOW_REF',context(r)['GITHUB_WORKFLOW_REF'])]:
        bad=dict(env)
        if value is None:bad.pop(key)
        else:bad[key]=value
        with pytest.raises(ValueError):c.admit(bad,mapped['PIN'],mapped['MANIFEST_SHA'],mapped['AUTHORITY'])
    with pytest.raises(ValueError):c.admit(env,mapped['PIN'],r.PLAN_HASH,c.AUTHORITY)
    with pytest.raises(ValueError):c.admit(env,mapped['PIN'],c.MANIFEST_SHA,r.AUTHORITY)


def test_recovery_cannot_accept_comparison_revision_or_manifest_context():
    env=dict(context(r),GITHUB_WORKFLOW_SHA='a'*40,RECOVERY_AUTHORITY=r.AUTHORITY)
    r.admit(env,'a'*40,r.PLAN_HASH)
    with pytest.raises(ValueError):r.admit(env,'a'*40,c.MANIFEST_SHA)
    with pytest.raises(ValueError):r.admit(dict(env,GITHUB_SHA='b'*40),'a'*40,r.PLAN_HASH)
    with pytest.raises(ValueError):r.admit(dict(env,RECOVERY_AUTHORITY=c.AUTHORITY),'a'*40,r.PLAN_HASH)


def test_ci_triggers_and_actual_suite_invocations_cover_registrations():
    for filename in ('stage4-discovery-offline.yml','stage4-batch-offline.yml'):
        text=(ROOT/'.github/workflows'/filename).read_text()
        for path,_,_ in PINS.values():assert "'"+path+"'" in text
        assert 'tests/test_discovery_r0_registration.py' in text
    text=(ROOT/'.github/workflows/stage4-discovery-offline.yml').read_text()
    assert 'tests/test_discovery_r0_executable_proposals.py' in text
    assert "'verification/discovery/**'" in text and "'tests/test_discovery_*.py'" in text
