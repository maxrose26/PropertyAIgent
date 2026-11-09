"""Physical PostgreSQL 17 PA-D002 private receipt test, fixed disposable only.

Exercises Runtime.archive / archive_private_final against the reviewed real SQL
definitions and restricted login, not mocked SQL. The full daily-intake command,
public Git receipt, expiry/stop orchestration and deletion are NOT proved here.
"""
import copy
import hashlib
import json
import re
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ingestion.ledger import Denied
from tests.e2e_pg_world import disposable_world
from verification.ingestion_storage.daily_intake_runtime import Runtime

PERIOD = 'test-pa-d002-physical'
RUN = 'a' * 32
ROOT = 'b' * 64
AUTH = 'offline-test-only'


def test_actual_restricted_sql_source_and_final_readback():
    # Verifies 127.0.0.1:5432, ingestion_provisioning_test, PG >=17 and
    # disposable bootstrap login; teardown always cleans SQL/roles.
    for world in disposable_world():
        boot = world['boot']
        boot.execute(Path('tests/fixtures/pa_d002_private_postgres.sql').read_text())
        now = time.time()
        policy = dict(evidence_backend='POSTGRES_PILOT_V1', max_runs=1,
                      expires_at=now+900, execution_binding={'revision':'offline'})
        ctl = copy.deepcopy(world['control'])
        ctl['intake_periods'] = {PERIOD: policy}
        ctl['intake_run'] = dict(id=RUN,period=PERIOD,state='OPEN')
        ctl['grants'] = {AUTH: dict(intake_period=PERIOD,intake_run=RUN,
             capture_key=ROOT,execution_binding=policy['execution_binding'],
             expires_at=now+800)}
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                     "WHERE key=repeat('0',64)", (json.dumps(ctl),))
        scope = dict(kind='DISCOVERY_SCOPE',council='tameside',
             start='2026-11-02',end='2026-11-08',semantics='RECEIVED')
        boot.execute("""INSERT INTO public.ingestion_work_items
            (key,subject,task,contract,revision,dependencies,priority,eligible_at,
             state,reason,next_action,limits,authority,attempt_count,max_attempts,
             fence,owner,lease_until,phase,checkpoint,outcome)
            VALUES (%s,%s::json,'DISCOVERY','tameside-screening-metadata-five-v1',
             'offline',%s::json,50,0,'CLAIMED',NULL,'RECONCILE',%s::json,
             %s,1,1,1,'offline',%s,'SOURCE_INTENT',NULL,NULL)""",
             (ROOT,json.dumps(scope),'[]','{}',AUTH,now+800))
        class SQL:
            def __init__(self,pg): self.pg=pg
            def execute(self,statement,params=None):
                query=re.sub(r'(?<!:):([a-z_][a-z0-9_]*)',
                             lambda m:'%('+m.group(1)+')s',str(statement))
                cur=self.pg.execute(query,params or {})
                return SimpleNamespace(all=lambda:cur.fetchall(),
                     scalar_one=lambda:cur.fetchone()[0])
        transactions=[]
        @contextmanager
        def restricted(*,seconds=90):
            assert seconds==30
            with world['connect']('ingestion_worker_login') as pg:
                transactions.append('COMMITTED_SEPARATE_SESSION')
                yield SQL(pg),None
        rt=Runtime.__new__(Runtime)
        rt.test=True;rt.policy={'evidence_backend':'POSTGRES_PILOT_V1'}
        rt.args=SimpleNamespace(period=PERIOD);rt.run_id=RUN
        rt.archive_ordinal=0;rt.connection=restricted
        # The SQL function performs the real authority and expiry enforcement;
        # the full command's policy_read preflight is NOT covered by this test.
        rt.policy_read=lambda *_a,**_kw:None
        rt.run=SimpleNamespace(publication=lambda *_a:None)
        source=dict(council='tameside',date_semantics='RECEIVED',
            requested_interval=['2026-11-02','2026-11-08'],
            listing_records=[dict(reference='SYNTHETIC-ONLY')])
        data=json.dumps(source,sort_keys=True,separators=(',',':')).encode()
        receipt=rt.archive(data)
        assert receipt==dict(backend='PRIVATE_POSTGRES_V1',period=PERIOD,
            run_id=RUN,name='capture-1/source.json',
            sha256=hashlib.sha256(data).hexdigest(),
            bytes=len(data),readback_verified=True)
        assert len(transactions)==2
        with world['connect']('ingestion_worker_login') as worker:
            assert worker.execute(
                'SELECT public.ingestion_intake_evidence_read(%s,%s,%s)',
                (PERIOD,RUN,'capture-1/source.json')).fetchone()[0]==data
        # Real SQL refuses conflicting write at original name, no overwrite.
        rt.archive_ordinal=0
        with pytest.raises(Exception,match='EVIDENCE_CONFLICT_NO_OVERWRITE'):
            rt.archive(json.dumps({**source,'failure':'CHANGED'}).encode())
        with world['connect']('ingestion_worker_login') as worker:
            assert worker.execute(
                'SELECT public.ingestion_intake_evidence_read(%s,%s,%s)',
                (PERIOD,RUN,'capture-1/source.json')).fetchone()[0]==data
        # Close source authority in disposable controller; no source replay.
        ctl['grants'][AUTH]['expires_at']=0
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                     "WHERE key=repeat('0',64)",(json.dumps(ctl),))
        rt.archive_ordinal=1
        with pytest.raises(Exception,match='EVIDENCE_SOURCE_AUTHORITY'):
            rt.archive(data)
        result=json.dumps({'status':'INCOMPLETE','private':'FAKE ADDRESS'}).encode()
        events=json.dumps([{'private':'FAKE ADDRESS'}]).encode()
        receipts=rt.archive_private_final(result,events)
        assert len(receipts)==2
        assert all(r['readback_verified'] is True for r in receipts.values())
        assert len(transactions)==8 # source(2), conflict(1), closed(1), finals(4)
        with world['connect']('ingestion_worker_login') as worker:
            for name,expected in (
                ('final/result-before-publication.json',result),
                ('final/events-before-publication.json',events)):
                assert worker.execute(
                    'SELECT public.ingestion_intake_evidence_read(%s,%s,%s)',
                    (PERIOD,RUN,name)).fetchone()[0]==expected
        assert boot.execute('SELECT count(*) FROM public.ingestion_run_evidence '
             'WHERE period=%s AND run_id=%s',(PERIOD,RUN)).fetchone()[0]==3
        rt.test=False
        with pytest.raises(Denied,match='PRIVATE_EVIDENCE_OFFLINE_ONLY'):
            rt.archive_private_final(result,events)
