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
        Path(plan['output']).joinpath('rehearsal-exception').write_text(json.dumps(dict(kind=type(exc).__name__,text=str(exc)[:800],primary=getattr(diag,'message_primary',None),context=getattr(diag,'context',None))))
        raise
_coordinator.Coordinator.idox_source=_recording
result,code=sp.run_hosted(urls=urls,journal=journal,gh_runner=gh_runner,source_reader_factory=reader_factory,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},hostaddr='192.0.2.1',memory=None,
                          evidence_head=plan['evidence_head'],manifest_sha256=plan['manifest_sha256'])
Path(plan['output']).joinpath('rehearsal-source-calls').write_text(str(len(calls)))
Path(plan['output']).joinpath('rehearsal-done').write_text(str(code))
raise SystemExit(code)
