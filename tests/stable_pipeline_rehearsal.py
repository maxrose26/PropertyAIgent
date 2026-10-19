"""Rehearsal entry for the HOSTED half of the stable-credential pipeline. DISPOSABLE LOOPBACK ONLY: it runs `stable_pipeline.run_hosted` (the production code path) as a separate process, with the
restricted pooler host translated to the disposable PostgreSQL server, the GitHub CLI pointed at the loopback fixture, and a synthetic source reader (no network source). Nothing here exists in
production; production's `main()` supplies the real effects to the same `run_hosted`."""
import json,os,subprocess,sys
from pathlib import Path
import psycopg

plan=json.loads(Path(sys.argv[1]).read_text())
if plan.get('disposable')!='LOOPBACK_ONLY' or os.environ.get('INGESTION_ACCEPTANCE_DISPOSABLE')!='PG17_ONLY':raise SystemExit('DISPOSABLE_ONLY')
urls=json.loads(os.environ.pop('REHEARSAL_URLS'))
from verification.ingestion_storage import restricted_route as rr
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.tls_trust import verified_trust

real_connect=psycopg.Connection.connect.__func__
def route_pooler(cls,conninfo='',**kw):
    if kw.get('host')==rr.ROUTES['POOLER']['host']:
        assert kw['user'].endswith('.'+rr.REF) and kw['sslmode']=='verify-full' and kw['hostaddr']=='192.0.2.1'
        kw=dict(kw,host='127.0.0.1',dbname=plan['dbname'],user=kw['user'].split('.')[0])
        for field in ('sslmode','sslrootcert','hostaddr'):kw.pop(field,None)
    return real_connect(cls,conninfo,**kw)
psycopg.Connection.connect=classmethod(route_pooler)

fault=plan['fault']
if fault=='screening_stops':
    def failing_batch(*a,**k):raise ValueError('BATCH_FIXTURE_FAILURE')
    orr.process_batch=failing_batch

from tests.test_discovery_ingestion_batching import sixty_rows
from tests.test_discovery_ingestion_ledger import outer
cfg,audit=sixty_rows();calls=[]
def reader_factory(runner):
    def reader(row):
        calls.append(1)
        if fault=='source_raises':raise ValueError('SOURCE_FIXTURE_FAILURE')
        return audit,outer()
    return reader

ca,_=verified_trust()
def gh_runner(command,**kw):
    return subprocess.run([plan['gh'],*command[1:]],env=plan['gh_env'],**kw)

journal=Journal(plan['output'])
# rehearsal-only diagnostic: the production failure classification deliberately exports no message; the DISPOSABLE server's own error text is recorded beside the audit
from app.ingestion import coordinator as _coordinator
_original=_coordinator.Coordinator.idox_source
def _recording(self,*a,**k):
    try:return _original(self,*a,**k)
    except BaseException as exc:
        diag=getattr(exc,'diag',None)
        analysis=None
        try:      # rehearsal-only: evaluate each component of the Bolton disposition against the control row AS THE WORKER SEES IT, at the moment of failure
            import time as _time
            from sqlalchemy.engine import make_url as _mk
            with psycopg.connect(os.environ['INGESTION_PROVISIONING_TEST_URL'],autocommit=True,connect_timeout=3) as c:      # the disposable bootstrap identity (the role has a connection limit of 1)
                ctl=c.execute("SELECT outcome::jsonb FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            authority=orr.PIPELINE_AUTHORITY+'_CAPTURE';grant=ctl.get('grants',{}).get(authority);exc=ctl.get('bolton_exceptions',{}).get(authority)
            analysis=dict(global_stop_ok=ctl.get('global_stop')=={'reason':'CONSUMED_SALFORD_GLOBAL_STOP','run':'38884069913'},generation=ctl.get('hard_stop_generation'),exception_generation=(exc or {}).get('hard_stop_generation'),
                          manual_stop=ctl.get('manual_stop'),exception_present=exc is not None,transport=(exc or {}).get('transport'),exception_expires_in=((exc or {}).get('expires_at') or 0)-_time.time(),
                          grant_present=grant is not None,grant_expires_in=((grant or {}).get('expires_at') or 0)-_time.time(),grant_source_calls=(grant or {}).get('source_calls'),
                          binding_equal=bool(exc and grant and exc.get('grant_binding')=={k:v for k,v in grant.items() if k not in ('source_calls','writes')}),
                          grant_keys_diff=sorted(set((exc or {}).get('grant_binding',{}))^set({k:v for k,v in (grant or {}).items() if k not in ('source_calls','writes')})) if exc and grant else None)
        except BaseException as inner:
            analysis=dict(analysis_failed=type(inner).__name__)
        Path(plan['output']).joinpath('rehearsal-exception').write_text(json.dumps(dict(kind=type(exc).__name__,text=str(exc)[:800],primary=getattr(diag,'message_primary',None),context=getattr(diag,'context',None),analysis=analysis)))
        raise
_coordinator.Coordinator.idox_source=_recording
from app.ingestion import sql_ledger as _sql_ledger
_steps=[]
_original_step=_sql_ledger.SQLLedger._step if hasattr(_sql_ledger,'SQLLedger') else None
if _original_step is not None:
    def _recording_step(self,op,key,fence=0,payload=None,connection=None):
        try:
            out=_original_step(self,op,key,fence,payload,connection);_steps.append((op,'OK'));return out
        except BaseException as exc:
            _steps.append((op,type(exc).__name__));Path(plan['output']).joinpath('rehearsal-steps').write_text(json.dumps(_steps));raise
    _sql_ledger.SQLLedger._step=_recording_step
result,code=sp.run_hosted(urls=urls,journal=journal,gh_runner=gh_runner,source_reader_factory=reader_factory,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},hostaddr='192.0.2.1',memory=None,
                          evidence_head=plan['evidence_head'],manifest_sha256=plan['manifest_sha256'])
Path(plan['output']).joinpath('rehearsal-source-calls').write_text(str(len(calls)))
Path(plan['output']).joinpath('rehearsal-done').write_text(str(code))
raise SystemExit(code)
