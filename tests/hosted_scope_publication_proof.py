"""Hosted proof (run inside the real cgroup-v2 scope by .github/workflows/stage4-hosted-memory-proof.yml): the hosted job's final result is published while the REAL OperationalMemory scope is still
enforcing, inside the bounded publication reserve; only then is the scope closed; and after that the unchanged closed-envelope guard denies every further GitHub call. GitHub itself is a local counter:
no network, no credential, no database."""
import os,subprocess,sys
from pathlib import Path
sys.path.insert(0,os.getcwd())
from app.ingestion.ledger import Denied
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_memory import OperationalMemory
from verification.ingestion_storage.operational_publication import GitHub

out=Path(os.environ['PROOF_DIR']);out.mkdir(parents=True,exist_ok=True)
memory=OperationalMemory()
urls={r:'postgresql://%s:x@h/db'%r for r in oo.ROLES}
runner=sp.HostedRunner(urls,Journal(out/'j'),None,None,{},'192.0.2.1',memory,evidence_head='1'*40,manifest_sha256='c'*64,revision='a'*40)
calls=[]
def fake_gh(command,**kw):
    calls.append(command);return subprocess.CompletedProcess(command,0,stdout=b'{}',stderr=b'')
runner.github=GitHub(runner.emit,lambda:runner.check(),runner=fake_gh,bound=140)
state={}
def publish(result):
    state['scope_closed_during_publication']=hasattr(runner,'memory_closure')
    state['reserve_active']=runner.github.reserve is not None
    for _ in range(4):runner.github.call('GET','x')
    state['snapshot_peak']=memory.snapshot()['aggregate']['peak_bytes']
runner.publish_completed=publish
result=runner.hosted_failure(RuntimeError('proof'),None)
assert result['cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE' and result['closure_stage']=='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE',result
sealed=runner.finalise(result)
assert state['scope_closed_during_publication'] is False and state['reserve_active'] is True and len(calls)==4,(state,len(calls))
assert sealed['publication']=='PUBLISHED' and sealed['cleanup']=='CLOSED' and sealed['closure_components']['process']['memory']['owned_groups_removed'] is True,sealed
try:
    runner.github.call('GET','x')
    raise SystemExit('NOT DENIED AFTER CLOSURE')
except Denied as exc:
    assert exc.args[0]=='RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS',exc.args
assert len(calls)==4
print('publication-inside-scope proof ok; calls during publication:',len(calls),'peak aggregate bytes:',state['snapshot_peak'])
