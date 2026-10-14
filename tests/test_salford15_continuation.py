"""Closed continuation admission and unchanged failure isolation; offline only."""
from pathlib import Path
from unittest.mock import patch
import pytest
import yaml
from verification.direct_reference import batch, arcus_production
from verification.direct_reference import salford15_manifest as m, salford15_production as p
from verification.direct_reference.batch_transaction import run_transaction
from tests.test_arcus_batch import seed, retrieved
from tests.test_arcus_production import admitted_env, SHA

EXPECTED = ((534,'PA/2024/1313'),(540,'PA/2024/1538'),(545,'PA/2024/1621'),
 (547,'PA/2024/1622'),(554,'PA/2025/0043'),(566,'23/81719/HYBEIA'),
 (1146,'23/81238/OUTEIA'),(1149,'23/81742/HYBEIA'),(1155,'23/82436/FUL'),
 (1156,'23/81788/FUL'),(1159,'PA/2023/0425'),(1165,'PA/2023/0550'),
 (1167,'PA/2023/0532'),(1177,'PA/2023/0556'),(1181,'20/76664/OUT'))

def test_exact_subset_and_hash():
    import hashlib
    rows = [r['identity'] for spec in m.CONTEXTS.values() for r in batch.manifest(spec)]
    assert tuple((r['application_id'],r['reference']) for r in rows) == EXPECTED
    assert len({r['application_id'] for r in rows}) == 15
    assert all(r['council']=='salford' and r['application_id']!=266 for r in rows)
    raw=Path(m.__file__).with_name('salford15-manifest.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==m.MANIFEST_SHA256

def test_tampered_manifest_fails_closed():
    with patch.object(m.Path,'read_bytes',return_value=b'{}'):
        with pytest.raises(ValueError,match='DIGEST'):batch.manifest(m.CONTEXTS['salford15_a'])

@pytest.mark.parametrize('key,value',[('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),
 ('GITHUB_REF','refs/heads/other'),('ARCUS_WORKFLOW_SHA','b'*40),
 ('GITHUB_WORKFLOW_REF','maxrose26/PropertyAIgent/'+arcus_production.WORKFLOW+'@refs/heads/master')])
def test_admission_rejects_other_workflow_or_repeat(key,value):
    env=admitted_env();env['GITHUB_WORKFLOW_REF']='maxrose26/PropertyAIgent/'+p.WORKFLOW+'@refs/heads/master'
    env[key]=value
    with patch.dict(p.os.environ,env,clear=True),patch.object(arcus_production,'production_engine') as db:
        with pytest.raises(ValueError):arcus_production.admit(SHA,workflow=p.WORKFLOW)
        db.assert_not_called()

def test_continuation_exact_admission():
    env=admitted_env();env['GITHUB_WORKFLOW_REF']='maxrose26/PropertyAIgent/'+p.WORKFLOW+'@refs/heads/master'
    with patch.dict(p.os.environ,env,clear=True),patch.object(arcus_production.subprocess,'check_output',side_effect=[SHA,'']):
        arcus_production.admit(SHA,workflow=p.WORKFLOW)

def test_unregistered_workflow_is_rejected():
    with pytest.raises(ValueError,match='WORKFLOW_SCOPE'):
        arcus_production.admit(SHA,workflow='.github/workflows/arbitrary.yml')

def test_worker_dispatch_reuses_existing_worker(tmp_path):
    import json
    output=tmp_path/'record.json'
    args=['salford15','--sha',SHA,'--authority',p.AUTHORITY,'--phase','salford15_b',
          '--output',str(output),'--worker-index','8','--limits',json.dumps(p.LIMITS)]
    with patch.object(p.sys,'argv',args),patch.object(arcus_production,'admit') as admit,patch.object(arcus_production,'worker') as worker:
        assert p.main()==0
        admit.assert_called_once_with(SHA,workflow=p.WORKFLOW)
        row,limits,path=worker.call_args.args
        assert (row['application_id'],row['reference'])==EXPECTED[-1]
        assert limits==p.LIMITS and path==output

@pytest.mark.parametrize('index,limits',[('9',p.LIMITS),('-1',p.LIMITS),('0',dict(p.LIMITS,seconds=46))])
def test_worker_scope_cannot_expand(tmp_path,index,limits):
    import json
    args=['salford15','--sha',SHA,'--authority',p.AUTHORITY,'--phase','salford15_b',
          '--output',str(tmp_path/'record.json'),'--worker-index',index,'--limits',json.dumps(limits)]
    with patch.object(p.sys,'argv',args),patch.object(arcus_production,'admit'),patch.object(arcus_production,'worker') as worker:
        assert p.main()==2
        worker.assert_not_called()

def test_identity_stop_still_stops_without_mutation(session):
    spec=m.CONTEXTS['salford15_a'];rows=[r['identity'] for r in batch.manifest(spec)]
    engine=session.get_bind();seed(engine,rows);calls=[]
    def execute(row,limits):
        calls.append(row['application_id']);source=retrieved(row)
        source.update(observation=None,failure='AMBIGUOUS_SOURCE_RESULT')
        return run_transaction(engine,row,lambda:source,limits,family='ARCUS')
    audit=batch.run(SHA,'123-salford15_a',execute,spec=spec)
    assert calls==[534] and audit['assessment']=='STOPPED_REVIEW_REQUIRED'
    r=audit['records'][0]
    assert r['transaction']=='NOT_COMMITTED' and r['before']==r['after'] and r['cleanup']=='CLOSED'
    assert r['statements']['writes']==r['statements']['commits']==0
    assert all(r['disposition']=='NOT_ATTEMPTED' for r in audit['records'][1:])

def test_field_only_and_local_rejection_reuse_b2(session):
    spec=m.CONTEXTS['salford15_a'];rows=[r['identity'] for r in batch.manifest(spec)]
    engine=session.get_bind();seed(engine,rows)
    def execute(row,limits):
        assert limits==p.LIMITS
        source=retrieved(row)
        if row['application_id']==534:source.update(observation=None,failure='PARTIAL_RETRIEVAL')
        return run_transaction(engine,row,lambda:source,limits,family='ARCUS')
    audit=batch.run(SHA,'123-salford15_a',execute,spec=spec)
    assert audit['assessment']=='ACCOUNTED'
    assert audit['records'][0]['disposition']=='SAFELY_REJECTED'
    for r in audit['records'][1:]:
        assert r['b2_outcome']=='FIELD_LEVEL_VERIFIED' and r['transaction']=='COMMITTED'
        assert all(r['before']['facts'][k]==r['after']['facts'][k] for k in ('status','decision','status_verified_at','last_seen_at'))

def test_second_batch_rejects_stopped_proof_before_credentials(tmp_path):
    audit=batch.run(SHA,'123-salford15_a',lambda *_:None,spec=m.CONTEXTS['salford15_a'])
    proof=tmp_path/'first.json';proof.write_bytes(batch.encode(audit))
    with patch.dict(p.os.environ,{'GITHUB_RUN_ID':'123'},clear=True),patch.object(p,'isolated') as worker:
        with pytest.raises(ValueError,match='PREVIOUS_NOT_ACCOUNTED'):
            p.execute(SHA,'salford15_b',tmp_path/'out.json',proof)
        worker.assert_not_called()

def test_workflow_closed_manual_scope_and_no_migration():
    w=yaml.load(Path(p.WORKFLOW).read_text(),Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'live'}
    assert set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','authority'}
    assert w['permissions']=={'contents':'read'} and w['concurrency']['cancel-in-progress']=='false'
    job=w['jobs']['live'];assert job['environment']=='stage4-production-canary'
    assert job['timeout-minutes']=='40' and 'env' not in w and 'env' not in job
    secret_steps=[s for s in job['steps'] if 'secrets.' in str(s)]
    assert len(secret_steps)==1 and secret_steps[0]['env']['BATCH_DATABASE_URL']=='${{ secrets.DATABASE_URL }}'
    run=secret_steps[0]['run']
    assert run.count('run_arcus --phase')==2 and '--migrate' not in run
    assert run.index('--phase salford15_a')<run.index('--phase salford15_b')
    assert '--previous' in run and 'env -i ' in run
    admission=job['steps'][0]['run']
    assert '$GITHUB_RUN_NUMBER" == 1' in admission and '$GITHUB_RUN_ATTEMPT" == 1' in admission
    assert 'refs/heads/master' in admission and p.AUTHORITY in admission
