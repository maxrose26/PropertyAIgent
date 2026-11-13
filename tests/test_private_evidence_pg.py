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
from datetime import datetime, timezone
from contextlib import contextmanager, nullcontext
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ingestion.ledger import Denied
from app.ingestion.retention_dry_run import assess_unverified_storage_snapshot
from tests.e2e_pg_world import disposable_world
from verification.ingestion_storage.daily_intake_runtime import Runtime, stop_snapshot

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
        policy['expected_stop'] = stop_snapshot(ctl)
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
        # A direct raw-table or body-column grant would bypass the intended
        # function-only evidence boundary. Physically falsify both in disposable
        # PostgreSQL, and restore the original ACL before any archive writes.
        with world['connect']('ingestion_worker_login') as worker:
            rt.private_evidence_inventory(SQL(worker))
        # Production read-only inspection on 11 Nov found neither function
        # executable by the restricted login. Prove the physical negative
        # path for each missing grant; the candidate must never silently
        # bypass its function-only evidence boundary or grant permissions.
        for signature in (
            'ingestion_intake_evidence_read(text,text,text)',
            'ingestion_intake_evidence_write(text,text,text,bytea)',
        ):
            boot.execute('REVOKE EXECUTE ON FUNCTION public.' + signature +
                         ' FROM ingestion_worker')
            try:
                with world['connect']('ingestion_worker_login') as worker:
                    with pytest.raises(Denied,match='PRIVATE_EVIDENCE_FUNCTION_INVENTORY'):
                        rt.private_evidence_inventory(SQL(worker))
            finally:
                boot.execute('GRANT EXECUTE ON FUNCTION public.' + signature +
                             ' TO ingestion_worker')
            with world['connect']('ingestion_worker_login') as worker:
                rt.private_evidence_inventory(SQL(worker))
        # Falsify function-level grants: the definer API must not be PUBLIC.
        for signature in (
            'ingestion_intake_evidence_read(text,text,text)',
            'ingestion_intake_evidence_write(text,text,text,bytea)',
        ):
            boot.execute('GRANT EXECUTE ON FUNCTION public.' + signature +
                         ' TO PUBLIC')
            try:
                with world['connect']('ingestion_worker_login') as worker:
                    with pytest.raises(Denied,match='PRIVATE_EVIDENCE_FUNCTION_INVENTORY'):
                        rt.private_evidence_inventory(SQL(worker))
            finally:
                boot.execute('REVOKE EXECUTE ON FUNCTION public.' + signature +
                             ' FROM PUBLIC')
            with world['connect']('ingestion_worker_login') as worker:
                rt.private_evidence_inventory(SQL(worker))
        for grant,revoke in (
            ('GRANT SELECT ON public.ingestion_run_evidence TO ingestion_worker',
             'REVOKE SELECT ON public.ingestion_run_evidence FROM ingestion_worker'),
            ('GRANT SELECT (body) ON public.ingestion_run_evidence TO ingestion_worker',
             'REVOKE SELECT (body) ON public.ingestion_run_evidence FROM ingestion_worker'),
        ):
            boot.execute(grant)
            try:
                with world['connect']('ingestion_worker_login') as worker:
                    with pytest.raises(Denied,match='PRIVATE_EVIDENCE_RAW_TABLE_ACL'):
                        rt.private_evidence_inventory(SQL(worker))
            finally:
                boot.execute(revoke)
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
        # REAL disposable-PostgreSQL metadata inventory: never read raw body
        # into the retention preview. The table alone has no authenticated
        # hold/resolution/prospective tag, so every row must remain preserved.
        metadata=boot.execute('''SELECT period, run_id, name, sha256,
                               encode(sha256(body),'hex'), octet_length(body),
                               created_at FROM public.ingestion_run_evidence
                               WHERE period=%s AND run_id=%s''',
                              (PERIOD,RUN)).fetchall()
        snapshot=[dict(period=p,run_id=r,name=n,stored_sha256=s,
                       actual_sha256=digest,bytes=size,
                       created_at=created.isoformat())
                  for p,r,n,s,digest,size,created in metadata]
        preservation=assess_unverified_storage_snapshot(
            snapshot,as_of=datetime.now(timezone.utc).isoformat())
        assert preservation['total']==1
        assert preservation['items'][0]['disposition']=='PRESERVE_HISTORICAL_OR_UNTAGGED'
        assert preservation['items'][0]['may_delete_now'] is False
        assert preservation['sql_or_delete_operations']==0
        # Idempotent read/write ACK is permitted while SOURCE_INTENT is live,
        # but the SQL ACK remains unverified until separate readback.
        with world['connect']('ingestion_worker_login') as worker:
            live_repeat = worker.execute(
                'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                (PERIOD, RUN, 'capture-1/source.json', data)).fetchone()[0]
        assert live_repeat['sha256'] == receipt['sha256']
        assert live_repeat['readback_verified'] is False
        # Physical lock-order falsification: after an owner stop-generation
        # change commits, a waiting worker cannot persist another source.
        stopped=copy.deepcopy(ctl)
        stopped['hard_stop_generation']=(ctl.get('hard_stop_generation') or 0)+1
        started=Event()
        # The restricted migrator intentionally lacks controller UPDATE.
        # Simulate the owner stop using the disposable bootstrap connection;
        # this never grants an extra permission or touches any live database.
        with nullcontext(boot) as owner:
            owner.execute('BEGIN')
            committed=False
            try:
                owner.execute(
                    "UPDATE public.ingestion_work_items SET outcome=%s::json "
                    "WHERE key=repeat('0',64)", (json.dumps(stopped),))
                def concurrent_source():
                    with world['connect']('ingestion_worker_login') as worker:
                        started.set()
                        return worker.execute(
                            'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                            (PERIOD,RUN,'capture-2/source.json',data)).fetchone()[0]
                with ThreadPoolExecutor(max_workers=1) as pool:
                    attempt=pool.submit(concurrent_source)
                    try:
                        assert started.wait(8), 'restricted writer never started'
                        assert not attempt.done(), 'worker bypassed controller lock'
                    finally:
                        owner.execute('COMMIT')
                        committed=True
                    with pytest.raises(Exception,match='EVIDENCE_STOP_CHANGED'):
                        attempt.result(timeout=20)
            finally:
                if not committed:
                    owner.execute('ROLLBACK')
        assert boot.execute(
            'SELECT count(*) FROM public.ingestion_run_evidence '
            'WHERE period=%s AND run_id=%s',(PERIOD,RUN)).fetchone()[0]==1
        # Restore the disposable fixture only; no live stop is ever cleared.
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                     "WHERE key=repeat('0',64)", (json.dumps(ctl),))
        # Genuine restricted-worker SQL refusals, not mocked callback failures.
        # An authorised Tameside capture must not accept a Bolton record,
        # an altered date window, or a capture larger than 512 KiB.
        for invalid_body, refusal in (
            (json.dumps({**source, 'council': 'bolton'}).encode(),
             'EVIDENCE_SOURCE_AUTHORITY'),
            (json.dumps({**source, 'requested_interval':
                         ['2026-11-01', '2026-11-08']}).encode(),
             'EVIDENCE_SOURCE_AUTHORITY'),
            (b'{"payload":"' + b'x' * 524289 + b'"}',
             'EVIDENCE_ARGUMENT_BOUND'),
        ):
            with pytest.raises(Exception, match=refusal):
                with world['connect']('ingestion_worker_login') as worker:
                    worker.execute(
                        'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                        (PERIOD, RUN, 'capture-2/source.json', invalid_body))
        # A third source slot is forbidden even when source authority is live.
        with pytest.raises(Exception, match='EVIDENCE_ARGUMENT_BOUND'):
            with world['connect']('ingestion_worker_login') as worker:
                worker.execute(
                    'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                    (PERIOD, RUN, 'capture-3/source.json', data))
        # Source transactions are not durable until COMMIT. In this fixture
        # restricted sessions are autocommit by default, so BEGIN/ROLLBACK
        # must be explicit (an exception in a context manager is insufficient).
        with world['connect']('ingestion_worker_login') as worker:
            worker.execute('BEGIN')
            try:
                pending = worker.execute(
                    'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                    (PERIOD, RUN, 'capture-2/source.json', data)).fetchone()[0]
                assert pending['readback_verified'] is False
            finally:
                worker.execute('ROLLBACK')
        assert boot.execute(
            'SELECT count(*) FROM public.ingestion_run_evidence '
            'WHERE period=%s AND run_id=%s', (PERIOD, RUN)).fetchone()[0] == 1
        # A final report cannot be inserted while an active source grant
        # remains open; a refusal must leave the retained source untouched.
        with pytest.raises(Exception, match='EVIDENCE_FINITE_AUTHORITIES_NOT_CLOSED'):
            with world['connect']('ingestion_worker_login') as worker:
                worker.execute(
                    'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                    (PERIOD, RUN, 'final/result-before-publication.json', b'{}'))
        # Expired period cannot gain a fresh source even if its SOURCE_INTENT
        # work item and finite grant still appear open.
        original_expiry = ctl['intake_periods'][PERIOD]['expires_at']
        ctl['intake_periods'][PERIOD]['expires_at'] = now-1
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                     "WHERE key=repeat('0',64)", (json.dumps(ctl),))
        with pytest.raises(Exception, match='EVIDENCE_SOURCE_AUTHORITY'):
            with world['connect']('ingestion_worker_login') as worker:
                worker.execute(
                    'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                    (PERIOD, RUN, 'capture-2/source.json', data))
        # Expired period cannot revive an already-retained source by replaying
        # identical bytes; reconciliation is READ ONLY through the SQL reader.
        with pytest.raises(Exception, match='EVIDENCE_SOURCE_AUTHORITY'):
            with world['connect']('ingestion_worker_login') as worker:
                worker.execute(
                    'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                    (PERIOD, RUN, 'capture-1/source.json', data))
        ctl['intake_periods'][PERIOD]['expires_at'] = original_expiry
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                     "WHERE key=repeat('0',64)", (json.dumps(ctl),))
        assert boot.execute(
            'SELECT count(*) FROM public.ingestion_run_evidence '
            'WHERE period=%s AND run_id=%s', (PERIOD, RUN)).fetchone()[0] == 1
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
        # Closed SOURCE_INTENT also refuses the identical first capture.
        with pytest.raises(Exception, match='EVIDENCE_SOURCE_AUTHORITY'):
            with world['connect']('ingestion_worker_login') as worker:
                worker.execute(
                    'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                    (PERIOD, RUN, 'capture-1/source.json', data))
        rt.archive_ordinal=1
        with pytest.raises(Exception,match='EVIDENCE_SOURCE_AUTHORITY'):
            rt.archive(data)
        # The installed function applies the 2 MiB *aggregate* limit, not
        # merely its per-object limit. A valid 2 MiB final object would exceed
        # the run budget because capture 1 already occupies private storage.
        prefix, suffix = b'{"padding":"', b'"}'
        over_total = prefix + b'x' * (2097152-len(prefix)-len(suffix)) + suffix
        assert len(over_total) == 2097152
        with pytest.raises(Exception, match='EVIDENCE_RUN_EXPORT_BOUND'):
            with world['connect']('ingestion_worker_login') as worker:
                worker.execute(
                    'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                    (PERIOD, RUN, 'final/result-before-publication.json',
                     over_total))
        assert boot.execute(
            'SELECT count(*) FROM public.ingestion_run_evidence '
            'WHERE period=%s AND run_id=%s', (PERIOD, RUN)).fetchone()[0] == 1
        # A previously verified run cannot append fresh final evidence.
        ctl['intake_run']['state'] = 'VERIFIED'
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                     "WHERE key=repeat('0',64)", (json.dumps(ctl),))
        with pytest.raises(Exception, match='EVIDENCE_RUN_CLOSED'):
            with world['connect']('ingestion_worker_login') as worker:
                worker.execute(
                    'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                    (PERIOD, RUN, 'final/result-before-publication.json', b'{}'))
        ctl['intake_run']['state'] = 'OPEN'
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                     "WHERE key=repeat('0',64)", (json.dumps(ctl),))
        assert boot.execute(
            'SELECT count(*) FROM public.ingestion_run_evidence '
            'WHERE period=%s AND run_id=%s', (PERIOD, RUN)).fetchone()[0] == 1
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



def test_committed_private_source_with_lost_ack_is_readback_only():
    """Physical lost-ACK case: persisted bytes do not authorise write replay.

    The synthetic client deliberately drops its acknowledgement AFTER the
    restricted PostgreSQL statement commits. Exact-name readback is permitted
    after authority expiry, but no automatic receipt/retry or promotion follows.
    """
    from app.ingestion.private_evidence import verified_private_capture

    for world in disposable_world():
        boot = world['boot']
        boot.execute(Path('tests/fixtures/pa_d002_private_postgres.sql').read_text())
        now = time.time()
        ctl = copy.deepcopy(world['control'])
        policy = dict(evidence_backend='POSTGRES_PILOT_V1', max_runs=1,
                      expires_at=now + 900,
                      execution_binding={'revision': 'offline'})
        policy['expected_stop'] = stop_snapshot(ctl)
        ctl['intake_periods'] = {PERIOD: policy}
        ctl['intake_run'] = dict(id=RUN, period=PERIOD, state='OPEN')
        ctl['grants'] = {AUTH: dict(intake_period=PERIOD, intake_run=RUN,
              capture_key=ROOT, execution_binding=policy['execution_binding'],
              expires_at=now + 800)}
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                     "WHERE key=repeat('0',64)", (json.dumps(ctl),))
        scope = dict(kind='DISCOVERY_SCOPE', council='tameside',
                     start='2026-11-02', end='2026-11-08', semantics='RECEIVED')
        boot.execute("""INSERT INTO public.ingestion_work_items
            (key,subject,task,contract,revision,dependencies,priority,eligible_at,
             state,reason,next_action,limits,authority,attempt_count,max_attempts,
             fence,owner,lease_until,phase,checkpoint,outcome)
            VALUES (%s,%s::json,'DISCOVERY','tameside-screening-metadata-five-v1',
             'offline',%s::json,50,0,'CLAIMED',NULL,'RECONCILE',%s::json,
             %s,1,1,1,'offline',%s,'SOURCE_INTENT',NULL,NULL)""",
             (ROOT, json.dumps(scope), '[]', '{}', AUTH, now + 800))
        raw = json.dumps(dict(council='tameside', date_semantics='RECEIVED',
            requested_interval=['2026-11-02', '2026-11-08'],
            listing_records=[dict(reference='SYNTHETIC-LOST-ACK')]),
            sort_keys=True, separators=(',', ':')).encode()
        attempts = []

        def write_then_drop_ack(body):
            attempts.append('one-physical-write')
            with world['connect']('ingestion_worker_login') as worker:
                ack = worker.execute(
                    'SELECT public.ingestion_intake_evidence_write(%s,%s,%s,%s)',
                    (PERIOD, RUN, 'capture-1/source.json', body)).fetchone()[0]
                assert ack['readback_verified'] is False
            # The SQL connection has closed: simulate lost network response,
            # without reporting a verified receipt or retrying the write.
            raise ConnectionError('SYNTHETIC_ACK_LOST_AFTER_COMMIT')

        with pytest.raises(ConnectionError,
                           match='SYNTHETIC_ACK_LOST_AFTER_COMMIT'):
            verified_private_capture(raw, period=PERIOD, run_id=RUN,
                name='capture-1/source.json', write=write_then_drop_ack,
                readback=lambda: pytest.fail('no trusted read on uncertain ack'))
        assert attempts == ['one-physical-write']
        assert boot.execute(
            'SELECT count(*) FROM public.ingestion_run_evidence '
            'WHERE period=%s AND run_id=%s', (PERIOD, RUN)).fetchone()[0] == 1

        # Expire the source permission after the missing ACK; a restricted
        # read still permits reconciliation of the exact immutable bytes.
        ctl['grants'][AUTH]['expires_at'] = 0
        ctl['intake_periods'][PERIOD]['expires_at'] = now - 1
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                     "WHERE key=repeat('0',64)", (json.dumps(ctl),))
        with world['connect']('ingestion_worker_login') as reader:
            recovered = reader.execute(
                'SELECT public.ingestion_intake_evidence_read(%s,%s,%s)',
                (PERIOD, RUN, 'capture-1/source.json')).fetchone()[0]
        assert recovered == raw
        assert hashlib.sha256(recovered).digest() == hashlib.sha256(raw).digest()
        assert attempts == ['one-physical-write']
        assert boot.execute(
            'SELECT count(*) FROM public.ingestion_run_evidence '
            'WHERE period=%s AND run_id=%s', (PERIOD, RUN)).fetchone()[0] == 1
        # This is evidence of persistence only, not intake finalisation.
        assert boot.execute(
            "SELECT outcome::jsonb->'intake_run'->>'state' "
            "FROM public.ingestion_work_items WHERE key=repeat('0',64)"
        ).fetchone()[0] == 'OPEN'


def test_actual_daily_entrypoint_private_source_and_public_summary(tmp_path):
    """CLI -> supported issuer -> PG private sources/finals -> local safe summary.

    Entirely synthetic Idox/Arcus fixtures. Real fixed disposable SQL and
    owner/worker function boundaries. No source, live Git, or production call.
    """
    from tests.test_daily_intake_runtime import reset, policy, authorise, invoke
    from verification.ingestion_storage import intake_policy

    for world in disposable_world():
        with world['connect']('provisioning_migrator') as migrator:
            migrator.execute(intake_policy.installation_script())
        world['boot'].execute(
            Path('tests/fixtures/pa_d002_private_postgres.sql').read_text())
        reset(world)
        p = policy(world)
        p['max_runs'] = 1  # Existing private SQL write function's exact bound.
        p['evidence_backend'] = 'POSTGRES_PILOT_V1'
        name = 'test-pa-d002-cli'
        authorise(world, name, p)  # Actual owner issuer in disposable PG.
        run, result, command = invoke(world, tmp_path, name, count=1)
        # On a refusal, print only synthetic fixture result codes and event
        # kinds; do not dump private source, records, message bodies or URLs.
        events_file = tmp_path / 'result' / 'events.json'
        event_names = ([e.get('event') for e in json.loads(events_file.read_text())]
                       if events_file.exists() else [])
        assert run.returncode == 0, dict(
            returncode=run.returncode, status=result.get('status'),
            failure=result.get('failure'), reason=result.get('reason'),
            publication=result.get('publication'),
            stop_readback=result.get('stop_readback'),
            scopes=[(s.get('council'), s.get('status'), s.get('failure'))
                    for s in result.get('scopes', [])],
            event_names=event_names[-20:])
        assert result['status'] == 'RETAINED_AND_SCREENED', result
        assert result['publication'] == 'TEST_PRIVATE_SUMMARY'
        assert result['authority_closure'] == 'INVALIDATED'
        assert result['cleanup'] == 'CLOSED'
        assert result['coverage_advance'] is False
        assert result['durable_finalisation']['state'] == 'VERIFIED'
        persisted = world['boot'].execute(
            'SELECT name, body, sha256 FROM public.ingestion_run_evidence '
            'WHERE period=%s ORDER BY name', (name,)).fetchall()
        assert len(persisted) == 4
        assert {r[0] for r in persisted} == {
            'capture-1/source.json', 'capture-2/source.json',
            'final/result-before-publication.json',
            'final/events-before-publication.json'}
        for record_name, body, sha in persisted:
            assert hashlib.sha256(body).hexdigest() == sha
            assert len(body) > 0
        public = (tmp_path / 'archive' /
                  (result['durable_finalisation']['id'] + '-final.json')).read_bytes()
        public_data = json.loads(public)
        assert public_data['schema'] == 'INTAKE_PUBLIC_SUMMARY_V1'
        assert len(public) < 8192
        assert b'DAILY/' not in public  # Synthetic raw reference stays private.
        assert b'listing_records' not in public
        assert b'events-before-publication.json' not in public
        assert b'PRIVATE-FIXTURE-ONLY' not in public
        assert result['durable_finalisation']['publication']['sha256'] == (
            hashlib.sha256(public).hexdigest())
        assert result['durable_finalisation']['publication']['readback_verified'] is True
        ctl = world['boot'].execute(
            "SELECT outcome FROM public.ingestion_work_items "
            "WHERE key=repeat('0',64)").fetchone()[0]
        assert ctl['global_stop'] is None and ctl['manual_stop'] is None
        assert all(g['expires_at'] == 0 for g in ctl['grants'].values())


def test_exact_inactive_writer_transition_preserves_existing_evidence_and_acl_disposable():
    """Actual installed writer -> candidate on existing PG17 table, no production.
    The migration's own preflight is expected to reject all unexpected prior
    code/roles/stops; it does not create or reset the evidence table.
    """
    migration=Path('verification/ingestion_storage/private_evidence_writer_transition.sql').read_text()
    assert 'CREATE TABLE' not in migration.upper()
    assert 'CREATE OR REPLACE FUNCTION public.ingestion_intake_evidence_write' in migration
    assert 'ingestion_intake_evidence_read(p_period' not in migration
    assert "LIVE_PRIVATE_EVIDENCE_RELEASE" not in migration
    for world in disposable_world():
        boot=world['boot']
        boot.execute(Path('tests/fixtures/pa_d002_private_postgres.sql').read_text())
        # Match the independently read existing table ACL/RLS and reader ACL.
        boot.execute('ALTER TABLE public.ingestion_run_evidence ENABLE ROW LEVEL SECURITY')
        boot.execute('ALTER TABLE public.ingestion_run_evidence FORCE ROW LEVEL SECURITY')
        boot.execute('GRANT EXECUTE ON FUNCTION public.ingestion_intake_evidence_read(text,text,text) TO postgres')
        # This is an immutable read-only capture of the installed pre-upgrade
        # function, not another migration or a production change.
        boot.execute(Path('tests/fixtures/pa_d002_installed_writer.sql').read_text())
        old=boot.execute("""SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex')
                 FROM pg_proc WHERE oid=
                'public.ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure""").fetchone()[0]
        assert old=='8ffd8fdda0692a49a776137ea6342c1378d1f513cd418b8f983a92f0fe910290'
        payload=b'{"historical":"preserve-exactly"}'
        boot.execute("""INSERT INTO public.ingestion_run_evidence
          (period,run_id,name,body,sha256)
          VALUES ('historical-private','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                  'final/result-before-publication.json',%s,
                  encode(sha256(%s),'hex'))""",(payload,payload))
        before=boot.execute("""SELECT period,run_id,name,encode(body,'hex'),sha256,
                 created_at FROM public.ingestion_run_evidence""").fetchall()
        ctl=copy.deepcopy(world['control'])
        ctl.update(global_stop=dict(reason='DAILY_INTAKE_SHARED_FAILURE'),
                   manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',
                   last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',
                   hard_stop_generation=15)
        boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",
                     (json.dumps(ctl),))
        boot.execute(migration)
        updated=boot.execute("""SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex')
                 FROM pg_proc WHERE oid=
                'public.ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure""").fetchone()[0]
        assert updated=='4ce46b98cbf986596f907b7236509b87ade6788bce7e4c9f40ebbd8167381f77'
        after=boot.execute("""SELECT period,run_id,name,encode(body,'hex'),sha256,
                 created_at FROM public.ingestion_run_evidence""").fetchall()
        assert before==after
        # Post-commit readback proves no issuer, grant, stop or period changed.
        control=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
        assert control==ctl
        # Stale/duplicate migration refuses instead of reapplying its function.
        with pytest.raises(Exception,match='PRIVATE_WRITER_TRANSITION_EXPECTED_OLD'):
            boot.execute(migration)
        boot.execute('ROLLBACK')
        assert boot.execute("""SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex')
                 FROM pg_proc WHERE oid=
                'public.ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure""").fetchone()[0]==updated
        assert boot.execute("""SELECT period,run_id,name,encode(body,'hex'),sha256,
                 created_at FROM public.ingestion_run_evidence""").fetchall()==before
