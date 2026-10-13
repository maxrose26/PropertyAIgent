import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest
import yaml
from verification.direct_reference import batch as b, batch_production as p, catchup_production as c

SHA='a'*40
A_IDS=[1068,24,28,29,31,32,39,40,354,390,392,393,403,106,174,58,59,60,446,290]
B_IDS=[309,310,317,318,342,345,572,589,597,775]

def environment(ctx):
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='123',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_REF='refs/heads/master',BATCH_WORKFLOW_SHA=SHA,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+ctx.workflow+'@refs/heads/master')

def test_coverage_partition_and_exclusions():
    l=c.reconcile()
    assert l['census_admitted_policy_due_count']==39
    assert l['successfully_refreshed_due_ids']==[381,409,468]
    assert l['completeness_withheld_due_ids']==[41,53,56]
    assert l['timeout_due_ids']==[305,783]
    assert l['previously_retrieved_without_persistence_due_ids']==[78]
    assert l['oldham42_already_fresh_at_census'] is True
    assert l['batch_a_ids']==A_IDS and l['batch_b_ids']==B_IDS
    assert len(l['unattempted_ids'])==30 and set(l['unattempted_ids']).isdisjoint(c.PREVIOUSLY_ATTEMPTED)
    for ctx,ids in [(c.A,A_IDS),(c.B,B_IDS)]:
        rows=b.manifest(ctx.manifest)
        assert [r['identity']['application_id'] for r in rows]==ids
        assert all(r['policy']=='A' for r in rows)
        assert all('status_verified_at' in r['prior_facts'] for r in rows)
        assert hashlib.sha256(Path(b.__file__).with_name(ctx.manifest.filename).read_bytes()).hexdigest()==ctx.manifest.digest

@pytest.mark.parametrize('ctx',[c.A,c.B])
def test_exact_admission_and_no_cross_cohort(ctx):
    e=environment(ctx);assert c.context(e)==ctx
    with patch.object(p.subprocess,'check_output',side_effect=[SHA,'']):
        assert len(p.admit(SHA,ctx.manifest.digest,ctx.authority,e,context=ctx))==ctx.manifest.count
    other=c.B if ctx==c.A else c.A
    for digest,auth in [(other.manifest.digest,ctx.authority),(ctx.manifest.digest,other.authority),(ctx.manifest.digest,'NOT_AUTHORISED')]:
        with pytest.raises(ValueError):p.admit(SHA,digest,auth,e,context=ctx)
    for key,value in [('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_REF','refs/heads/feature'),('GITHUB_EVENT_NAME','push'),('BATCH_WORKFLOW_SHA','b'*40),('GITHUB_WORKFLOW_REF',environment(other)['GITHUB_WORKFLOW_REF'])]:
        bad=dict(e);bad[key]=value
        with pytest.raises(ValueError):p.admit(SHA,ctx.manifest.digest,ctx.authority,bad,context=ctx)
    for ref in ('arbitrary',e['GITHUB_WORKFLOW_REF'].replace('master','feature')):
        with pytest.raises(ValueError):c.context(dict(e,GITHUB_WORKFLOW_REF=ref))
    with patch.object(p.subprocess,'check_output',side_effect=[SHA,'dirty']),pytest.raises(ValueError):p.admit(SHA,ctx.manifest.digest,ctx.authority,e,context=ctx)

@pytest.mark.parametrize('ctx',[c.A,c.B])
def test_frozen_hash_identity_and_prior_input_rejected(ctx):
    path=Path(b.__file__).with_name(ctx.manifest.filename);raw=path.read_bytes()
    bad=json.loads(raw);bad['rows'][0]['identity']['application_id']=42
    with patch.object(Path,'read_bytes',return_value=json.dumps(bad).encode()),pytest.raises(ValueError):b.manifest(ctx.manifest)
    # Even a recomputed hash cannot admit a substituted identity under the route contract.
    badraw=json.dumps(bad).encode();spec=b.ManifestSpec(ctx.manifest.filename,hashlib.sha256(badraw).hexdigest(),ctx.manifest.count,True)
    with patch.object(Path,'read_bytes',return_value=badraw),pytest.raises(ValueError):b.manifest(spec)
    a=b.run(SHA,'123',lambda *args:(_ for _ in ()).throw(ValueError()),spec=ctx.manifest)
    p.validate(a,SHA,'123',context=ctx)
    assert len(a['records'])==ctx.manifest.count and a['records'][0]['transaction']=='UNKNOWN'
    assert all(r['disposition']=='NOT_ATTEMPTED' for r in a['records'][1:])
    assert a['carried_ids']==[] and a['parent_audit_sha256'] is None
    with pytest.raises(ValueError):b.validate(a) # cannot mislabel catch-up as representative20
    with pytest.raises(ValueError):b.run(SHA,'next',lambda *args:None,prior=a,prior_sha256=hashlib.sha256(b.encode(a)).hexdigest(),spec=ctx.manifest)
    bad=copy.deepcopy(a);bad['records'][0]['prior_facts']={}
    with pytest.raises(ValueError):p.validate(bad,SHA,'123',context=ctx)

@pytest.mark.parametrize('ctx',[c.A,c.B])
def test_shared_orchestration_and_private_worker_env(ctx,monkeypatch,tmp_path):
    for k,v in environment(ctx).items():monkeypatch.setenv(k,v)
    monkeypatch.setenv('BATCH_DATABASE_URL','SYNTHETIC_NOT_A_CONNECTION_STRING')
    calls=[]
    def isolated(row,limits,command,env):
        calls.append((row,limits,command(row,limits,tmp_path/'worker'),env.copy()))
        assert 'prior_facts' not in row and 'selection_reason' not in row
        a=b.blank(row);a.update(b2_outcome='UNKNOWN',transaction='UNKNOWN',error='INTERRUPTED',cleanup='UNKNOWN',disposition='UNCERTAIN');return a
    monkeypatch.setattr(p,'isolated',isolated)
    with patch.object(p.subprocess,'check_output',side_effect=[SHA,'']):
        assert p.execute(SHA,ctx.manifest.digest,ctx.authority,tmp_path/'audit',0,clock=lambda:0,context=ctx)==1
    audit=json.loads((tmp_path/'audit').read_text());p.validate(audit,SHA,'123',context=ctx)
    assert len(calls)==1 and calls[0][0]['application_id']==(A_IDS if ctx==c.A else B_IDS)[0]
    assert calls[0][2][2]=='verification.direct_reference.catchup_production'
    assert set(calls[0][3])==set(p.ENV_KEYS)|{'BATCH_DATABASE_URL'}
    assert 'SYNTHETIC_NOT_A_CONNECTION_STRING' not in (tmp_path/'audit').read_text()
    assert calls[0][1]==dict(requests=2,bytes=2_000_000,seconds=40,worker_seconds=45)

@pytest.mark.parametrize('ctx',[c.A,c.B])
def test_registration_controls(ctx):
    w=yaml.load(Path(ctx.workflow).read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'live'}
    assert set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha256','authority'}
    assert w['permissions']=={'contents':'read'}
    assert w['concurrency']=={'group':'stage4-admitted-catchup-production','cancel-in-progress':'false'}
    job=w['jobs']['live'];assert job['environment']=='stage4-production-canary' and job['timeout-minutes']=='10'
    assert job['runs-on']=='ubuntu-24.04' and 'env' not in job and 'env' not in w
    steps=job['steps'];guard=steps[0]['run']
    assert ctx.manifest.digest in guard and ctx.authority in guard
    for text in ('"$PIN" == "$WORKFLOW_SHA"','refs/heads/master','"$GITHUB_RUN_NUMBER" == 1','"$GITHUB_RUN_ATTEMPT" == 1'):assert text in guard
    checkout=next(s for s in steps if s.get('uses')=='actions/checkout@v4')
    assert checkout['with']=={'ref':'${{ inputs.reviewed_sha }}','persist-credentials':'false'}
    secretsteps=[s for s in steps if 'secrets.' in str(s)]
    assert len(secretsteps)==1 and secretsteps[0]['env']['BATCH_DATABASE_URL']=='${{ secrets.DATABASE_URL }}'
    assert '-m verification.direct_reference.catchup_production' in secretsteps[0]['run']
    offline=Path('.github/workflows/stage4-batch-offline.yml').read_text()
    assert 'secrets.DATABASE_URL' not in offline and 'stage4-production-canary' not in offline
    assert 'verification/ah-offline-pytest.py' in offline and 'tests/test_stage4_catchup.py' in offline

def test_no_new_writer_transport_or_resume():
    s=Path(c.__file__).read_text()
    for text in ('requests_session','production_engine','run_transaction','.commit(','.execute(','--resume','--application','--url','--cohort','--manifest-file','frozen_observation'):
        assert text not in s
    assert 'batch_production.main(c)' in s
    s=Path(p.__file__).read_text()
    assert 'from .refresh import requests_session' in s and "provenance='FRESH_OFFICIAL_SUMMARY'" in s
    assert 'resource_limits()' in s and 'prior=' not in s
