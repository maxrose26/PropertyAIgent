"""Rehearsal entry for the HOSTED half of the Bolton FORM PROBE. DISPOSABLE LOOPBACK ONLY: it runs `form_probe.run_probe_hosted` (the production code path) as a separate process, with the restricted pooler
host translated to the disposable PostgreSQL server, the GitHub CLI pointed at the loopback fixture, a stateful stand-in for the cgroup memory scope that drives the real controller guard, and a source
reader that runs the REAL `run_form_probe` against an injected dispatch (no network). Nothing here exists in production; production's `main()` supplies the real effects to the same function."""
import io,json,os,subprocess,sys
from pathlib import Path
import psycopg

plan=json.loads(Path(sys.argv[1]).read_text())
if plan.get('disposable')!='LOOPBACK_ONLY' or os.environ.get('INGESTION_ACCEPTANCE_DISPOSABLE')!='PG17_ONLY':raise SystemExit('DISPOSABLE_ONLY')
urls=json.loads(os.environ.pop('REHEARSAL_URLS'))
from verification.ingestion_storage import restricted_route as rr
from verification.ingestion_storage import form_probe as fprobe
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.tls_trust import verified_trust
from verification.discovery.idox_window import WindowConfig,run_form_probe
from verification.bolton_recon.fixtures import FORM
from datetime import date

real_connect=psycopg.Connection.connect.__func__
def route_pooler(cls,conninfo='',**kw):
    if kw.get('host')==rr.ROUTES['POOLER']['host']:
        assert kw['user'].endswith('.'+rr.REF) and kw['sslmode']=='verify-full' and kw['hostaddr']=='192.0.2.1'
        kw=dict(kw,host='127.0.0.1',dbname=plan['dbname'],user=kw['user'].split('.')[0])
        for field in ('sslmode','sslrootcert','hostaddr'):kw.pop(field,None)
    return real_connect(cls,conninfo,**kw)
psycopg.Connection.connect=classmethod(route_pooler)

fault=plan['fault']
FORM_BYTES=FORM if isinstance(FORM,bytes) else FORM.encode()
CONFIG=WindowConfig('bolton','RECEIVED',date(2026,10,16),date(2026,10,16),0)
from tests.test_discovery_ingestion_ledger import outer
calls=[]


class Resp:
    def __init__(self,status=200,ctype='text/html',body=FORM_BYTES,headers=None):
        self.status_code=status;self.headers=dict({'Content-Type':ctype},**(headers or {}));self.b=body;self.raw=io.BytesIO()
    def iter_content(self,n):yield self.b
    def close(self):pass


def dispatch(method,url,**kw):
    calls.append((method,url))
    if fault=='refused_403':return Resp(403,body=b'<html>Access denied</html>')
    return Resp()


def reader_factory(runner):
    def reader(row):
        audit=run_form_probe(dispatch,CONFIG);audit['cleanup']='SESSION_BOUNDARY_CLOSED'
        if fault=='worker_audit_malformed':audit['probe']='LISTING'
        return audit,outer()
    return reader


ca,_=verified_trust()
def gh_runner(command,**kw):
    return subprocess.run([plan['gh'],*command[1:]],env=plan['gh_env'],**kw)


_gh_calls=[0]
_inner=gh_runner
def gh_runner(command,**kw):      # every GitHub request the hosted half makes, to prove none is made after the memory scope is closed
    _gh_calls[0]+=1
    return _inner(command,**kw)


class Scope:
    """A stateful stand-in for OperationalMemory with the production contract, driving the REAL controller guard and publication path (the real cgroup scope is proved by stage4-hosted-memory-proof)."""
    source=None
    def __init__(self):self.closed=False
    def snapshot(self):
        if self.closed:raise AssertionError('snapshot after close')
    def close(self):
        self.closed=True
        Path(plan['output']).joinpath('rehearsal-memory-closed-after-gh-calls').write_text(str(_gh_calls[0]))
        return dict(owned_groups_removed=True,owned_survivors=0,memory=dict(aggregate=dict(events=dict(oom_kill=0))))


journal=Journal(plan['output'])
result,code=fprobe.run_probe_hosted(urls=urls,journal=journal,gh_runner=gh_runner,source_reader_factory=reader_factory,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},hostaddr='192.0.2.1',memory=Scope(),
                                    evidence_head=plan['evidence_head'],manifest_sha256=plan['manifest_sha256'],revision=plan['revision'])      # checkout_probe omitted: the production default reader runs against this very checkout and the mode's own manifest
Path(plan['output']).joinpath('rehearsal-source-calls').write_text(str(len(calls)))
Path(plan['output']).joinpath('rehearsal-gh-calls-total').write_text(str(_gh_calls[0]))
Path(plan['output']).joinpath('rehearsal-done').write_text(str(code))
raise SystemExit(code)
