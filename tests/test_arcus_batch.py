import copy
import pytest
from sqlalchemy.orm import Session
from app.db.models import Application,Council
from verification.direct_reference import batch,arcus_batch
from verification.direct_reference.batch_transaction import run_transaction
from verification.direct_reference.refresh import Observation

LIMITS=dict(requests=80,bytes=20*1024*1024,seconds=45,worker_seconds=75)
def retrieved(row):
    partial=row['council']=='salford'
    fields={'Reference':row['reference'],'Status':None if partial else 'Final',
            'Decision':None if partial else 'Approve','Decision Issued Date':'2026-08-20'}
    states={k:('NOT_PRESENT' if partial and k in {'status','decision'} else 'PRESENT_VALUE')
            for k in ('reference','status','decision','decision_date')}
    o=Observation(row['application_id'],row['reference'],row['source_url'],fields,states,
        'UNKNOWN_UNMAPPED' if partial else 'granted','a'*64,{k:v for k,v in fields.items() if v is not None},
        b2_eligible=True,verification_scope='FIELD_LEVEL_DATE_ONLY' if partial else 'COUPLED')
    labels=dict(reference='Reference',status='Status',decision='Decision',decision_date='Decision Issued Date')
    o.field_evidence={k:dict(state=states[k],value=fields[v]) for k,v in labels.items()}
    audit=dict(requests=4,redirects=0,retries=0,received_body_bytes=1000,encoded_body_bytes=500,
        elapsed_seconds=1,worker_seconds=1,peak_owned_rss=100000,owned_processes_seen=2,
        live_owned_survivors=0,navigations=1,pages=1,cleanup_state='CLOSED',budget_state='WITHIN_LIMITS',source_sha256='a'*64)
    return dict(observation=o,audit=audit,failure=None)

def seed(engine,rows):
    with Session(engine) as s:
        for row in rows:
            if not s.get(Council,row['council']):s.add(Council(code=row['council'],name=row['council'],base_url=row['source_url'],date_field_mode='received',doc_system='arcus'))
            s.add(Application(id=row['application_id'],council_code=row['council'],reference=row['reference'],status='Awaiting decision'))
        s.commit()

def test_closed_groups():
    groups=[batch.manifest(spec) for spec in arcus_batch.CONTEXTS.values()]
    ids=[r['identity']['application_id'] for group in groups for r in group]
    assert len(ids)==len(set(ids))==57
    assert ids[:3]==[688,295,252]
    assert 1100 not in ids

def test_b2_full_and_field_level_batch(session):
    spec=arcus_batch.CONTEXTS['validation']
    rows=[r['identity'] for r in batch.manifest(spec)]
    engine=session.get_bind();seed(engine,rows)
    out=batch.run('a'*40,'offline_arcus',lambda r,l:run_transaction(engine,r,lambda:retrieved(r),l,family='ARCUS'),spec=spec)
    assert out['assessment']=='ACCOUNTED',out
    assert [r['b2_outcome'] for r in out['records']]==['VERIFIED_MATERIAL_CHANGE','VERIFIED_MATERIAL_CHANGE','FIELD_LEVEL_VERIFIED']
    assert all(r['transaction']=='COMMITTED' for r in out['records'])
    assert out['records'][2]['after']['facts']['status_verified_at'] is None
    bad=copy.deepcopy(out)
    bad['records'][2]['after']['facts']['status_verified_at']='2026-01-01T00:00:00'
    with pytest.raises(ValueError):batch.validate(bad,spec=spec)

def test_failed_source_preserves_record(session):
    row=batch.manifest(arcus_batch.CONTEXTS['validation'])[2]['identity']
    engine=session.get_bind();seed(engine,[row])
    source=retrieved(row);source.update(observation=None,failure='SOURCE_UNAVAILABLE')
    result=run_transaction(engine,row,lambda:source,LIMITS,family='ARCUS')
    assert result['disposition']=='SAFELY_REJECTED',result
    assert result['before']==result['after']

def test_batch_practical_wall_limit_does_not_start_partial_allowance():
    calls=[]
    def execute(row,limits):
        calls.append(row['application_id'])
        raise AssertionError('must not start')
    ticks=iter([0,230,230,230])
    out=batch.run('a'*40,'wall_bound',execute,spec=arcus_batch.CONTEXTS['validation'],clock=lambda:next(ticks))
    assert calls==[]
    assert all(r['disposition']=='NOT_ATTEMPTED' for r in out['records'])

def test_zero_byte_bounded_failure_is_recorded():
    row=batch.manifest(arcus_batch.CONTEXTS['validation'])[0]['identity']
    source=retrieved(row)
    source.update(observation=None,failure='TIMEOUT')
    source['audit'].update(received_body_bytes=0,encoded_body_bytes=0,navigations=0,source_sha256=None)
    result=arcus_batch.source_record(source,row,LIMITS)
    assert result['outcome']=='TIMEOUT'
