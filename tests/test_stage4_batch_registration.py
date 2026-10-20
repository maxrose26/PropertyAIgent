import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest
import yaml
from verification.direct_reference import batch_production as p,batch as b

SHA='a'*40

def env():
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='123',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_REF='refs/heads/master',BATCH_WORKFLOW_SHA=SHA,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p.WORKFLOW+'@refs/heads/master')

@pytest.mark.parametrize('key,value',[('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','pull_request'),
    ('GITHUB_REF','refs/heads/feature'),('BATCH_WORKFLOW_SHA','b'*40),('GITHUB_WORKFLOW_REF','alternate'),('GITHUB_REPOSITORY','other/repo'),('RUNNER_ENVIRONMENT','self-hosted'),('GITHUB_RUN_ID','')])
def test_exact_admission(key,value):
    e=env();e[key]=value
    with patch.object(p.subprocess,'check_output',side_effect=[SHA,'']),pytest.raises(ValueError):p.admit(SHA,b.MANIFEST_SHA256,p.AUTHORITY,e)

def test_digest_authority_checkout():
    with patch.object(p.subprocess,'check_output',side_effect=[SHA,'']):assert len(p.admit(SHA,b.MANIFEST_SHA256,p.AUTHORITY,env()))==20
    for sha,digest,authority in [(SHA,'0'*64,p.AUTHORITY),(SHA,b.MANIFEST_SHA256,'NOT_AUTHORISED'),('bad',b.MANIFEST_SHA256,p.AUTHORITY)]:
        with pytest.raises(ValueError):p.admit(sha,digest,authority,env())
    for outputs in ([SHA,'dirty'],['b'*40,'']):
        with patch.object(p.subprocess,'check_output',side_effect=outputs),pytest.raises(ValueError):p.admit(SHA,b.MANIFEST_SHA256,p.AUTHORITY,env())

def test_workflow_scope():
    w=yaml.load(Path(p.WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'live'}
    assert w['permissions']=={'contents':'read'}
    assert set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha256','authority'}
    job=w['jobs']['live'];assert job['environment']=='stage4-production-canary'
    assert job['runs-on']=='ubuntu-24.04' and job['timeout-minutes']=='10'
    steps=job['steps'];assert 'env' not in job and 'env' not in w
    secrets=[s for s in steps if 'secrets.' in str(s)]
    assert len(secrets)==1 and secrets[0]['env']['BATCH_DATABASE_URL']=='${{ secrets.DATABASE_URL }}'
    checkout=next(s for s in steps if s.get('uses')=='actions/checkout@v4')
    assert checkout['with']=={'ref':'${{ inputs.reviewed_sha }}','persist-credentials':'false'}
    assert 'GITHUB_RUN_NUMBER' in steps[0]['run'] and 'GITHUB_RUN_ATTEMPT' in steps[0]['run']
    assert w['concurrency']['cancel-in-progress']=='false'
    for path in Path('.github/workflows').glob('*.yml'):
        if path.name=='stage4-ingestion-storage-catalogue-tls-once.yml':
            # Exact separately approved TLS successor; no general environment exemption.
            assert hashlib.sha256(path.read_bytes()).hexdigest()=='618b2f2723b7381772a27e3af75a7ff098166b22f0d7dbaafc2a1f98e3f08684'
            continue
        if path.name=='stage4-stable-credential-qualification-once.yml':
            # Exact separately authorised restricted-credential qualification (restricted secrets only; no administrative secret); no blanket exception.
            assert hashlib.sha256(path.read_bytes()).hexdigest()=='625cd29355ebae37ffa2271edd2ceb431c341b9c964d4ac246f23924b7fcb1f1'
            continue
        if path.name=='stage4-stable-pipeline-once.yml':
            # Exact separately authorised restricted-credential pipeline job (restricted secrets only; no administrative secret; write token confined to the evidence branch by code); no blanket exception.
            assert hashlib.sha256(path.read_bytes()).hexdigest()=='8e7ed37afc870ed993bcd6aae8e4b1f59982309ae188926d1d9d25343d577b20'
            continue
        if path.name=='stage4-form-probe-once.yml':
            # Exact separately authorised Bolton form-probe job (restricted secrets only; no administrative secret; write token confined to the evidence branch by code); no blanket exception.
            assert hashlib.sha256(path.read_bytes()).hexdigest()=='6a947476c83928ce0cb9c70d7edcf6626f448ae468eb2bba53d93fe36ab47828'
            continue
        if path.name=='stage4-capture-acceptance-once.yml':
            # Exact separately authorised Bolton capture-acceptance job (restricted secrets only; no administrative secret; write token confined to the evidence branch by code); no blanket exception.
            assert hashlib.sha256(path.read_bytes()).hexdigest()=='5ea2106486e8aecb793fbf894b190cdc0af16611fa5c86f2595df022056a312a'
            continue
        if path.name=='stage4-ingestion-storage-catalogue-once.yml':
            # Exact separately authorised catalogue-only access; no blanket exception.
            assert hashlib.sha256(path.read_bytes()).hexdigest()=='0ad0e1931253639e883947b996147181c23b8a0fee1845d614fa99c7b632989c'
            continue
        if path.name in {'stage4-bolton-delta3-comparison-once.yml','stage4-oldham-two-capture-once.yml'}:
            from tests.test_discovery_narrow_continuation import assert_registered
            assert_registered('comparison3' if 'comparison' in path.name else 'oldham2',path.read_bytes())
            continue
        if path.name=='stage4-catchup-completion-comparison944-once.yml':
            from tests.test_discovery_completion import assert_comparison_registered
            assert_comparison_registered(path.read_bytes())
            continue
        if path.name=='stage4-r0-selective5-admission-once.yml':
            from tests.test_discovery_autonomous_mandate import assert_selected_registered
            assert_selected_registered(path.read_bytes())
            continue
        if path.name=='stage4-r0-identity-comparison-once.yml':
            from tests.test_discovery_r0_registration import assert_registered
            assert_registered('comparison',path.read_text())
            continue
        if path.name=='stage4-route-qualified-material-admission-once.yml':
            assert hashlib.sha256(path.read_bytes()).hexdigest()=='d82a20c4b39c61866aeb59fcbc360e72843a9b4e7d0b8026c831061659ef96e3'
            continue
        if path.name=='stage4-route-preflight-once.yml':
            # Exact reviewed connection-free registration, not a blanket environment exception.
            assert hashlib.sha256(path.read_bytes()).hexdigest()=='e6142ecdbd296130cd70f6143a0a1dddfec2989651474e35e6639bf22e622773'
            continue
        if path.name in ('stage4-batch-production-once.yml','stage4-oldham-production-once.yml','stage4-catchup-a-production-once.yml','stage4-catchup-b-production-once.yml','stage4-closure-pending-production-once.yml','stage4-closure-expanded-production-once.yml','stage4-arcus-production-once.yml','stage4-salford15-production-once.yml','stage4-committee-admission-once.yml','stage4-material-cohort-admission-once.yml'):continue
        other=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
        assert 'stage4-production-canary' not in str(other)
        assert 'secrets.DATABASE_URL' not in str(other)

def test_fresh_only_no_writer_resume_or_input():
    s=Path(p.__file__).read_text()
    assert 'from .refresh import requests_session' in s and "provenance='FRESH_OFFICIAL_SUMMARY'" in s
    for forbidden in ('from .fixtures','frozen_observation','load_live','.commit(','.add(','create_all(','.execute(','--resume','--application','--url','--reference','--council'):
        assert forbidden not in s
    assert 'batch.run(sha,' in s and 'prior=' not in s
    assert 'resource_limits()' in s

@pytest.mark.parametrize('key,value',[('requests',3),('bytes',2_000_001),('seconds',41),('worker_seconds',46),('seconds',float('nan')),('requests',True)])
def test_limits_no_increase(key,value):
    limits=dict(requests=2,bytes=2_000_000,seconds=40,worker_seconds=45);limits[key]=value
    with pytest.raises(ValueError):p.limits(limits)

def test_outer_deadline_before_secret(monkeypatch,tmp_path):
    monkeypatch.setattr(p,'admit',lambda *a:b.manifest())
    for age in (-1,280,600):
        with pytest.raises(ValueError):p.execute(SHA,b.MANIFEST_SHA256,p.AUTHORITY,tmp_path/'audit',0,clock=lambda:age)

def test_first_manifest_orchestrates_no_resume(monkeypatch,tmp_path):
    monkeypatch.setattr(p,'admit',lambda *a:b.manifest())
    for k,v in env().items():monkeypatch.setenv(k,v)
    monkeypatch.setenv('BATCH_DATABASE_URL','SYNTHETIC_NOT_A_CONNECTION_STRING')
    calls=[]
    def isolated(row,limits,command,environment):
        calls.append((row['application_id'],limits,command(row,limits,tmp_path/'record'),set(environment)))
        a=b.blank(row);a.update(b2_outcome='UNKNOWN',transaction='UNKNOWN',error='INTERRUPTED',cleanup='UNKNOWN',disposition='UNCERTAIN');return a
    monkeypatch.setattr(p,'isolated',isolated)
    out=tmp_path/'audit.json'
    assert p.execute(SHA,b.MANIFEST_SHA256,p.AUTHORITY,out,0,clock=lambda:0)==1
    a=json.loads(out.read_text());p.validate(a,SHA,'123')
    assert len(calls)==1 and calls[0][0]==72 and a['carried_ids']==[] and a['parent_audit_sha256'] is None
    assert set(calls[0][3])==set(p.ENV_KEYS)|{'BATCH_DATABASE_URL'}
    assert 'SYNTHETIC_NOT_A_CONNECTION_STRING' not in out.read_text()

def test_production_rejects_synthetic_source(session):
    from tests.test_stage4_batch import seed,execute
    engine=session.get_bind();seed(engine);calls=[]
    def run(row,limits):calls.append(1);return execute(engine,row,limits)
    a=b.run(SHA,'123',run,clock=lambda:0 if not calls else 300)
    b.validate(a) # valid reviewed batch audit, rejected only by live provenance
    with pytest.raises(ValueError):p.validate(a,SHA,'123')

def test_closed_audit_privacy():
    a=b.run(SHA,'123',lambda *a:(_ for _ in ()).throw(ValueError()))
    p.validate(a,SHA,'123')
    for key in ('DATABASE_URL','html','cookies','headers','applicant'):
        bad=copy.deepcopy(a);bad[key]='private'
        with pytest.raises(ValueError):p.validate(bad,SHA,'123')
