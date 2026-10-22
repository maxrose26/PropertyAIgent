"""Rehearsal entry for the HOSTED half of the screening-v3 RETAINED-WINDOW assessment (PR #175). DISPOSABLE LOOPBACK ONLY: it runs `stable_pipeline.run_hosted` with the REAL `ScreeningV3HostedRunner`, the restricted pooler host
translated to the disposable PostgreSQL server, the GitHub CLI pointed at the loopback fixture and the PRODUCTION checkout reader against this checkout. There is no source reader at all: any call to one fails the run. Nothing here
exists in production; production's `main()` supplies the real effects to the same `run_hosted`."""
import json,os,subprocess,sys
from pathlib import Path
import psycopg

plan=json.loads(Path(sys.argv[1]).read_text())
if plan.get('disposable')!='LOOPBACK_ONLY' or os.environ.get('INGESTION_ACCEPTANCE_DISPOSABLE')!='PG17_ONLY':raise SystemExit('DISPOSABLE_ONLY')
urls=json.loads(os.environ.pop('REHEARSAL_URLS'))
from verification.ingestion_storage import restricted_route as rr
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage import screening_v3_hosted as hosted
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
sp.SCREENING_WAIT_SECONDS=plan.get('marker_wait',60)      # the hosted wait for the owner's registration marker (a rehearsal that never registers must not leave this process polling)
if fault=='hosted_fails':      # the third batch raises: the run must stop, publish a stop, and leave the owner to invalidate
    original=orr.process_batch;count=[0]
    def failing_batch(coordinator,key,**kw):
        count[0]+=1
        if count[0]==3:raise ValueError('BATCH_FIXTURE_FAILURE')
        return original(coordinator,key,**kw)
    orr.process_batch=failing_batch
if fault=='authority_expires':      # the hosted job is slow after the marker: the allowance (registered with a very short lifetime) lapses before any claim
    import time
    original_present=hosted.ScreeningV3HostedRunner.authority_present
    def slow_present(self):
        out=original_present(self);time.sleep(float(plan['lapse_seconds']));return out
    hosted.ScreeningV3HostedRunner.authority_present=slow_present

ca,_=verified_trust()
def gh_runner(command,**kw):
    if fault=='hosted_publication_fails' and any('/completed' in str(part) for part in command):
        return subprocess.CompletedProcess(command,1,stdout=b'',stderr=b'rehearsal publication failure')
    return subprocess.run([plan['gh'],*command[1:]],env=plan['gh_env'],**kw)

journal=Journal(plan['output'])
import re
_FIXED=re.compile(r'[A-Z][A-Z0-9_]{2,79}')
_original_failure=sp.HostedRunner.hosted_failure
def _hosted_failure_with_code(self,exc,qualification):      # rehearsal only: the fixed reason code a hosted stop carries
    text=exc.args[0] if getattr(exc,'args',None) and isinstance(exc.args[0],str) else ''
    Path(plan['output']).joinpath('rehearsal-stop-code').write_text(json.dumps(dict(exception=type(exc).__name__,code=text if _FIXED.fullmatch(text) else 'NOT_A_FIXED_CODE',phase=self.operation_phase)))
    return _original_failure(self,exc,qualification)
sp.HostedRunner.hosted_failure=_hosted_failure_with_code
_gh_calls=[0]
_inner_gh_runner=gh_runner
def gh_runner(command,**kw):      # counts every GitHub request the hosted half makes, so the order against the memory-scope closure can be asserted
    _gh_calls[0]+=1
    return _inner_gh_runner(command,**kw)


class Scope:
    """A stateful stand-in for OperationalMemory with the production contract (snapshot() only while enforcing; close() once), driving the REAL controller guard and the real publication path. The real cgroup-v2
    scope is proved separately on a hosted runner (stage4-hosted-memory-proof)."""
    source=None
    def __init__(self):self.closed=False
    def snapshot(self):
        if self.closed:raise AssertionError('snapshot after close')
    def close(self):
        self.closed=True
        Path(plan['output']).joinpath('rehearsal-memory-closed-after-gh-calls').write_text(str(_gh_calls[0]))
        return dict(owned_groups_removed=True,owned_survivors=0,memory=dict(aggregate=dict(events=dict(oom_kill=0))))


calls=[]
def reader_factory(runner):
    def reader(row):
        calls.append(1);raise AssertionError('THE SCREENING-ONLY JOB MUST NEVER READ A SOURCE')
    return reader

kwargs=dict(checkout_probe=None)
if fault=='wrong_controller':      # the checkout hashes a different controller than the owner registered: the READY marker carries what this job actually runs
    from verification.ingestion_storage import stable_pipeline as _sp
    original_actual=_sp.actual_checkout
    def other_controller(root=None,manifest_path=None):
        out=original_actual(root,manifest_path);out['controller_sha256']='b'*64;return out
    kwargs['checkout_probe']=lambda:other_controller(manifest_path=hosted.SV3_MANIFEST_PATH)
result,code=sp.run_hosted(urls=urls,journal=journal,gh_runner=gh_runner,source_reader_factory=reader_factory,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},hostaddr='192.0.2.1',memory=Scope(),
                          evidence_head=plan['evidence_head'],manifest_sha256=plan['manifest_sha256'],revision=plan['revision'],runner_class=hosted.ScreeningV3HostedRunner,**kwargs)
Path(plan['output']).joinpath('rehearsal-source-calls').write_text(str(len(calls)))
Path(plan['output']).joinpath('rehearsal-gh-calls-total').write_text(str(_gh_calls[0]))
Path(plan['output']).joinpath('rehearsal-done').write_text(str(code))
raise SystemExit(code)
