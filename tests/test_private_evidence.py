"""PA-D002: offline receipt contract checks; all evidence/SQL stubs disposable."""
import hashlib
import json

import pytest

from app.ingestion.batching import archive_capture
from app.ingestion.ledger import Denied
from app.ingestion.private_evidence import (
    BACKEND, verified_private_capture, require_private_receipt,
)

PERIOD = 'offline-pa-d002'
RUN = 'a' * 32
NAME = 'capture-1/source.json'
SOURCE = {'case': 'synthetic', 'listing_records': [{'reference': 'TEST-ONLY'}]}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def verified_stubs(raw):
    calls = []
    persisted = {}

    def write(body):
        calls.append('write')
        persisted['raw'] = body
        return {'backend': 'POSTGRES_PILOT_V1', 'period': PERIOD,
                'run_id': RUN, 'name': NAME,
                'path': ('docs/design/ingestion-operational-execution-daily-intake/'
                         + PERIOD + '/' + RUN + '/' + NAME),
                'sha256': hashlib.sha256(body).hexdigest(),
                'bytes': len(body), 'readback_verified': False}

    def readback():
        calls.append('read')
        return persisted['raw']

    return write, readback, calls, persisted


def test_verified_private_receipt_requires_actual_exact_source_readback():
    raw = canonical(SOURCE)
    write, read, calls, persisted = verified_stubs(raw)
    receipt = verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                       write=write, readback=read)
    assert calls == ['write', 'read']
    assert receipt == {'backend': BACKEND, 'period': PERIOD, 'run_id': RUN,
                       'name': NAME, 'sha256': hashlib.sha256(raw).hexdigest(),
                       'bytes': len(raw), 'readback_verified': True}
    assert 'listing_records' not in str(receipt)
    assert require_private_receipt(receipt, raw) == receipt


def test_private_receipt_passes_existing_archive_capture_without_fake_git_commit():
    raw = canonical(SOURCE)
    write, read, calls, _ = verified_stubs(raw)
    receipt = archive_capture(
        SOURCE,
        lambda body: verified_private_capture(body, period=PERIOD, run_id=RUN,
                                              name=NAME, write=write, readback=read),
    )
    assert receipt['backend'] == BACKEND
    assert 'commit' not in receipt and 'path' not in receipt
    assert calls == ['write', 'read']


def test_historical_git_receipt_validation_is_unchanged():
    raw = canonical(SOURCE)
    legacy = {'commit': 'b' * 40, 'path': 'docs/design/historical/capture-1/source.json',
              'sha256': hashlib.sha256(raw).hexdigest(),
              'bytes': len(raw), 'readback_verified': True}
    assert archive_capture(SOURCE, lambda _: legacy) == legacy
    for changed in ({**legacy, 'commit': 'x' * 40},
                    {**legacy, 'path': '../sneaky/source.json'},
                    {**legacy, 'readback_verified': False},
                    {**legacy, 'backend': 'GIT_V1'}):
        with pytest.raises(Denied, match='DURABLE_ARCHIVE_NOT_VERIFIED'):
            archive_capture(SOURCE, lambda _: changed)


@pytest.mark.parametrize('name', [
    'capture-3/source.json', 'capture-1/../source.json', 'final/result-before-publication.json',
])
def test_wrong_source_capture_slot_refused_before_write(name):
    raw = canonical(SOURCE)
    write, read, calls, _ = verified_stubs(raw)
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_SCOPE_BOUND'):
        verified_private_capture(raw, period=PERIOD, run_id=RUN, name=name,
                                 write=write, readback=read)
    assert calls == []


@pytest.mark.parametrize('period,run_id', [
    ('bad/period', RUN), (PERIOD, 'not-a-run'), ('', RUN), (PERIOD, 'a' * 40),
])
def test_invalid_scope_refused_before_write(period, run_id):
    raw = canonical(SOURCE)
    write, read, calls, _ = verified_stubs(raw)
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_SCOPE_BOUND'):
        verified_private_capture(raw, period=period, run_id=run_id, name=NAME,
                                 write=write, readback=read)
    assert calls == []


def test_oversized_original_never_written_or_truncated():
    raw = b'x' * (524288 + 1)
    write, read, calls, _ = verified_stubs(raw)
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_SOURCE_BOUND'):
        verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                 write=write, readback=read)
    assert calls == []


@pytest.mark.parametrize('alter', [
    lambda raw: b'wrong',
    lambda raw: raw[:-1] + b'Z',
    lambda raw: None,
])
def test_acknowledged_but_mismatched_or_unavailable_sql_readback_refused(alter):
    raw = canonical(SOURCE)
    write, _, calls, persisted = verified_stubs(raw)
    def stale_read():
        calls.append('read')
        return alter(raw)
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_READBACK_MISMATCH'):
        verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                 write=write, readback=stale_read)
    assert calls == ['write', 'read']


@pytest.mark.parametrize('tamper', [
    lambda ack: {**ack, 'readback_verified': True},
    lambda ack: {**ack, 'backend': 'FAKE'},
    lambda ack: {**ack, 'period': 'other'},
    lambda ack: {**ack, 'run_id': 'b' * 32},
    lambda ack: {**ack, 'name': 'capture-2/source.json'},
    lambda ack: {**ack, 'path': 'docs/design/sneaky'},
    lambda ack: {**ack, 'sha256': '0' * 64},
    lambda ack: {**ack, 'bytes': True},
    lambda ack: {**ack, 'bytes': ack['bytes'] + 1},
    lambda ack: None,
])
def test_invalid_sql_write_ack_refused_without_false_verified_receipt(tamper):
    raw = canonical(SOURCE)
    write, read, calls, _ = verified_stubs(raw)
    def bad_write(body):
        return tamper(write(body))
    with pytest.raises(Denied, match='PRIVATE_EVIDENCE_WRITE_ACK_UNVERIFIED'):
        verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                 write=bad_write, readback=read)
    assert calls == ['write']


def test_unknown_or_mixed_backend_receipts_cannot_pass_archive_capture():
    raw = canonical(SOURCE)
    write, read, _, _ = verified_stubs(raw)
    valid = verified_private_capture(raw, period=PERIOD, run_id=RUN, name=NAME,
                                     write=write, readback=read)
    for changed in ({**valid, 'backend': 'UNKNOWN'},
                    {**valid, 'commit': 'a' * 40},
                    {**valid, 'path': 'docs/design/fake'},
                    {**valid, 'readback_verified': False},
                    {**valid, 'sha256': 'f' * 64},
                    {**valid, 'period': 'evil/path'},
                    {**valid, 'run_id': '1'},
                    {**valid, 'name': 'capture-3/source.json'}):
        with pytest.raises(Denied, match='DURABLE_ARCHIVE_NOT_VERIFIED'):
            archive_capture(SOURCE, lambda _: changed)

def test_runtime_archive_private_worker_receipt_is_verified_across_transactions():
    """Simulated SQL seam: actual Runtime.archive with distinct readback."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    from verification.ingestion_storage.daily_intake_runtime import Runtime
    from app.ingestion.private_evidence import READ_FUNCTION_SHA256,WRITE_FUNCTION_SHA256
    saved={};events=[]
    period='test-private-20261109';run='a'*32
    class SQL:
        inventory=[
            ('ingestion_intake_evidence_read',READ_FUNCTION_SHA256,
             'ingestion_storage_owner',True,['search_path=pg_catalog'],
             'p_period text, p_run text, p_name text',True),
            ('ingestion_intake_evidence_write',WRITE_FUNCTION_SHA256,
             'ingestion_storage_owner',True,['search_path=pg_catalog'],
             'p_period text, p_run text, p_name text, p_body bytea',True)]
        def execute(self,stmt,args=None):
            q=str(stmt)
            if 'FROM pg_catalog.pg_proc' in q:
                events.append('inventory')
                return SimpleNamespace(all=lambda:self.inventory)
            assert args['period']==period and args['run_id']==run
            assert args['name']=='capture-1/source.json'
            if 'ingestion_intake_evidence_write(' in q:
                events.append('write')
                saved['data']=args['body']
                ack=dict(backend='POSTGRES_PILOT_V1',period=period,run_id=run,
                    name=args['name'],path='docs/design/ingestion-operational-execution-daily-intake/'
                    +period+'/'+run+'/'+args['name'],sha256=hashlib.sha256(args['body']).hexdigest(),
                    bytes=len(args['body']),readback_verified=False)
                return SimpleNamespace(scalar_one=lambda:ack)
            if 'ingestion_intake_evidence_read(' in q:
                events.append('read')
                return SimpleNamespace(scalar_one=lambda:saved['data'])
            raise AssertionError(q)
    db=SQL()
    @contextmanager
    def connection(*,seconds=90):
        assert seconds==30
        events.append('new_transaction')
        yield db,None
    runtime=Runtime.__new__(Runtime)
    runtime.test=True;runtime.policy={'evidence_backend':'POSTGRES_PILOT_V1'}
    runtime.args=SimpleNamespace(period=period);runtime.run_id=run
    runtime.archive_ordinal=0;runtime.connection=connection
    runtime.policy_read=lambda conn:events.append('policy_checked')
    runtime.run=SimpleNamespace(publication=lambda *_:None)
    source={'requested_interval':['2026-11-02','2026-11-08'],'council':'tameside'}
    raw=json.dumps(source,sort_keys=True,separators=(',',':')).encode()
    receipt=runtime.archive(raw)
    assert receipt==dict(backend='PRIVATE_POSTGRES_V1',period=period,run_id=run,
                        name='capture-1/source.json',sha256=hashlib.sha256(raw).hexdigest(),
                        bytes=len(raw),readback_verified=True)
    assert events==['new_transaction','policy_checked','inventory','write',
                    'new_transaction','inventory','read']
    assert saved['data']==raw
    runtime.archive_ordinal=2
    with pytest.raises(Denied,match='PRIVATE_EVIDENCE_CAPTURE_SLOT_BOUND'):
        runtime.archive(raw)
    assert events.count('write')==1

def test_runtime_archive_private_refuses_inventory_drift_and_live_fallback():
    from contextlib import contextmanager
    from types import SimpleNamespace
    from verification.ingestion_storage.daily_intake_runtime import Runtime
    raw=b'{"council":"tameside"}';events=[]
    class SQL:
        def execute(self,stmt,args=None):
            events.append(str(stmt))
            return SimpleNamespace(all=lambda:[])  # no approved function identities
    @contextmanager
    def connection(*,seconds=90):
        yield SQL(),None
    runtime=Runtime.__new__(Runtime)
    runtime.test=True;runtime.policy={'evidence_backend':'POSTGRES_PILOT_V1'}
    runtime.args=SimpleNamespace(period='test-private-20261109')
    runtime.run_id='a'*32;runtime.archive_ordinal=0
    runtime.connection=connection;runtime.policy_read=lambda _:None
    runtime.run=SimpleNamespace(publication=lambda *_:None)
    with pytest.raises(Denied,match='PRIVATE_EVIDENCE_FUNCTION_INVENTORY'):
        runtime.archive(raw)
    assert len(events)==1 and 'FROM pg_catalog.pg_proc' in events[0]
    runtime.test=False
    with pytest.raises(Denied,match='PRIVATE_EVIDENCE_OFFLINE_ONLY'):
        runtime.archive(raw)
    runtime.test=True;runtime.policy={'evidence_backend':'UNKNOWN'}
    with pytest.raises(Denied,match='PRIVATE_EVIDENCE_BACKEND_UNKNOWN'):
        runtime.archive(raw)
    assert len(events)==1


def test_private_incomplete_audit_is_evidence_only_and_still_stops_before_screening():
    """A failed counted-window source cannot become a captured record."""
    from app.ingestion.daily_intake import intake_slot
    events=[];claim=object()
    scope=dict(kind='DISCOVERY_SCOPE',council='tameside',
               start='2026-11-02',end='2026-11-08',semantics='RECEIVED')
    root=dict(state='QUEUED',attempt_count=0,checkpoint=None,subject=scope)
    class Caller:
        intake_only=True
        def preflight(self,key):events.append('preflight')
        def read_intake_items(self,keys):return [root]
        def claim_intake_capture(self):events.append('claim');return claim
        contained_failure=lambda self,*args:None
        def retain_unqualified_source(self,source,outer,original):
            assert source['failure']=='CALIBRATION_PAGE_CAP'
            assert original is root
            events.append('private_evidence_verified')
        def capture(self,*args,**kwargs):raise AssertionError('PARTIAL_CAPTURE_FORBIDDEN')
        def settle_intake_failure(self,*args,**kwargs):raise AssertionError('UNQUALIFIED_SETTLEMENT_FORBIDDEN')
        def screen(self):raise AssertionError('PARTIAL_SCREEN_FORBIDDEN')
    source=dict(council='tameside',requested_interval=[scope['start'],scope['end']],
                failure='CALIBRATION_PAGE_CAP',completeness='FAILED',
                listing_records=[{'reference':'SYNTHETIC/26'}])
    with pytest.raises(Denied,match='INTAKE_UNQUALIFIED_SOURCE_EVIDENCE_ONLY'):
        intake_slot(Caller(),'synthetic-root',lambda _: (source,{}),
                    lambda _: (_ for _ in ()).throw(AssertionError('UNSAFE_PUBLIC_ARCHIVE')),
                    lambda _: (_ for _ in ()).throw(AssertionError('UNSAFE_SCREENING_REGISTRATION')))
    assert events==['preflight','claim','private_evidence_verified']


def test_runtime_unqualified_retention_is_disposable_scope_bound_and_minimal():
    from verification.ingestion_storage.daily_intake_runtime import Runtime
    from app.ingestion.private_evidence import BACKEND
    rt=Runtime.__new__(Runtime)
    rt.test=True;rt.policy={'evidence_backend':'POSTGRES_PILOT_V1'}
    archived=[];exported=[]
    def archive(raw):
        archived.append(raw)
        return dict(backend=BACKEND,sha256=hashlib.sha256(raw).hexdigest(),
                    bytes=len(raw),readback_verified=True)
    rt.archive=archive;rt.emit=lambda kind,data:exported.append((kind,data))
    scope=dict(kind='DISCOVERY_SCOPE',council='tameside',
               start='2026-11-02',end='2026-11-08')
    root=dict(subject=scope,limits=dict(aggregate_rss=1024,outer_seconds=30))
    source=dict(council='tameside',requested_interval=[scope['start'],scope['end']],
                failure='CALIBRATION_PAGE_CAP',records=[dict(address='PRIVATE ADDRESS')])
    outer=dict(exit_code=0,peak_owned_rss=0,elapsed_seconds=1,cleanup='CLOSED',
               live_owned_survivors=0,expired=False,limit_hit=None)
    result=rt.retain_unqualified_source(source,outer,root)
    assert result['backend']==BACKEND and len(archived)==1
    assert archived[0]==canonical(source)
    assert len(exported)==1 and exported[0][0]=='unqualified_private_evidence_retained'
    assert 'PRIVATE ADDRESS' not in json.dumps(exported)
    assert exported[0][1]['coverage_advance'] is False and exported[0][1]['screened'] is False
    for bad_source,bad_outer in [
        ({**source,'council':'manchester'},outer),
        ({**source,'requested_interval':['2026-10-01','2026-10-07']},outer),
        (source,{**outer,'cleanup':'UNCERTAIN'}),
        (source,{**outer,'live_owned_survivors':1}),
    ]:
        with pytest.raises(Denied):
            rt.retain_unqualified_source(bad_source,bad_outer,root)
    assert len(archived)==1
    rt.test=False
    with pytest.raises(Denied,match='PRIVATE_EVIDENCE_OFFLINE_ONLY'):
        rt.retain_unqualified_source(source,outer,root)
    assert len(archived)==1

def test_private_final_receipts_refuse_unknown_ack_and_unverified_storage():
    from app.ingestion.private_evidence import verified_private_final
    period='test-final';run_id='a'*32
    for name,body in [
        ('final/result-before-publication.json',{'raw':'PRIVATE_ADDRESS'}),
        ('final/events-before-publication.json',[{'raw':'PRIVATE_ADDRESS'}])]:
        raw=canonical(body);calls=[]
        def write(data):
            calls.append('write')
            return dict(backend='POSTGRES_PILOT_V1',period=period,run_id=run_id,
                name=name,path='docs/design/ingestion-operational-execution-daily-intake/'
                +period+'/'+run_id+'/'+name,
                sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
                readback_verified=False)
        def readback():
            calls.append('read');return raw
        receipt=verified_private_final(raw,period=period,run_id=run_id,
                                       name=name,write=write,readback=readback)
        assert receipt['readback_verified'] is True
        assert calls==['write','read']
        with pytest.raises(Denied,match='PRIVATE_FINAL_WRITE_ACK_UNVERIFIED'):
            verified_private_final(raw,period=period,run_id=run_id,name=name,
                write=lambda data:{**write(data),'path':'wrong'},readback=readback)
        with pytest.raises(Denied,match='PRIVATE_FINAL_READBACK_MISMATCH'):
            verified_private_final(raw,period=period,run_id=run_id,name=name,
                write=write,readback=lambda:b'{"mutated":"value"}')
    with pytest.raises(Denied,match='PRIVATE_FINAL_BODY_BOUND'):
        verified_private_final(b'{"secret":"a"}',period=period,run_id=run_id,
            name='capture-1/source.json',write=lambda _:pytest.fail('write'),
            readback=lambda:pytest.fail('read'))
    with pytest.raises(Denied,match='PRIVATE_FINAL_BODY_BOUND'):
        verified_private_final(b'[]',period=period,run_id=run_id,
            name='final/result-before-publication.json',write=lambda _:pytest.fail('write'),
            readback=lambda:pytest.fail('read'))

def test_runtime_private_final_commits_and_reads_both_objects_separately():
    """Simulated SQL only; physical disposable PG still needs a separate test."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    from app.ingestion.private_evidence import READ_FUNCTION_SHA256,WRITE_FUNCTION_SHA256
    from verification.ingestion_storage.daily_intake_runtime import Runtime
    period='test-final';run='a'*32;saved={};calls=[]
    inventory=[
        ('ingestion_intake_evidence_read',READ_FUNCTION_SHA256,'ingestion_storage_owner',
         True,['search_path=pg_catalog'],'p_period text, p_run text, p_name text',True),
        ('ingestion_intake_evidence_write',WRITE_FUNCTION_SHA256,'ingestion_storage_owner',
         True,['search_path=pg_catalog'],
         'p_period text, p_run text, p_name text, p_body bytea',True)]
    class SQL:
        def execute(self,statement,args=None):
            q=str(statement)
            if 'FROM pg_catalog.pg_proc' in q:
                calls.append('inventory')
                return SimpleNamespace(all=lambda:inventory)
            assert args['period']==period and args['run_id']==run
            if 'ingestion_intake_evidence_write(' in q:
                calls.append('write');saved[args['name']]=args['body']
                ack=dict(backend='POSTGRES_PILOT_V1',period=period,run_id=run,
                    name=args['name'],path='docs/design/ingestion-operational-execution-daily-intake/'
                    +period+'/'+run+'/'+args['name'],
                    sha256=hashlib.sha256(args['body']).hexdigest(),bytes=len(args['body']),
                    readback_verified=False)
                return SimpleNamespace(scalar_one=lambda:ack)
            if 'ingestion_intake_evidence_read(' in q:
                calls.append('read')
                return SimpleNamespace(scalar_one=lambda:saved[args['name']])
            raise AssertionError(q)
    @contextmanager
    def connection(*,seconds=90):
        assert seconds==30
        calls.append('new_transaction')
        yield SQL(),None
    runtime=Runtime.__new__(Runtime)
    runtime.test=True;runtime.policy={'evidence_backend':'POSTGRES_PILOT_V1'}
    runtime.args=SimpleNamespace(period=period);runtime.run_id=run
    runtime.connection=connection
    runtime.policy_read=lambda c,*,read_only=False:(
        calls.append('policy_read_only') if read_only else pytest.fail('fresh source grant forbidden'))
    result=canonical({'private':'PRIVATE_ADDRESS'})
    events=canonical([{'private':'PRIVATE_ADDRESS'}])
    receipts=runtime.archive_private_final(result,events)
    assert len(receipts)==2 and all(r['readback_verified'] for r in receipts.values())
    assert saved['final/result-before-publication.json']==result
    assert saved['final/events-before-publication.json']==events
    assert calls.count('new_transaction')==4
    assert calls.count('read')==calls.count('write')==2
    assert calls.count('policy_read_only')==2
    runtime.test=False
    with pytest.raises(Denied,match='PRIVATE_EVIDENCE_OFFLINE_ONLY'):
        runtime.archive_private_final(result,events)
    assert calls.count('write')==2
