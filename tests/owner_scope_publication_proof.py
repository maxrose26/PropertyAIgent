"""Owner proof (run inside the REAL cgroup-v2 scope by .github/workflows/stage4-hosted-memory-proof.yml): the owner's definitive result is published while the REAL OperationalMemory scope is still enforcing, inside the
bounded publication reserve; only then is the scope closed; the sealed local record follows; and afterwards the unchanged closed-envelope guard denies every further GitHub call. GitHub itself is a local counter:
no network, no credential, no database."""
import json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,os.getcwd())
from app.ingestion.ledger import Denied
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_memory import OperationalMemory
from verification.ingestion_storage.operational_publication import GitHub
import tests.test_ingestion_window_demonstration_owner as helpers

out=Path(os.environ['PROOF_DIR']);out.mkdir(parents=True,exist_ok=True)
memory=OperationalMemory()
runner=orr.Runner(helpers.registration('window'),Journal(out/'j'),lambda:None,source_reader=None,github=None,url_factory=None,memory=memory)
calls=[]
def fake_gh(command,**kw):
    calls.append(command);return subprocess.CompletedProcess(command,0,stdout=b'{}',stderr=b'')
runner.github=GitHub(runner.emit,lambda:runner.check(),runner=fake_gh,bound=orr.PIPELINE_GITHUB_BOUND)
pending=runner.closure('AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED',memory_close=False)
assert pending['overall']=='PENDING_MEMORY_SCOPE_CLOSURE' and pending['process']['memory']=='ENFORCED_PENDING_CLOSURE' and not hasattr(runner,'memory_closure'),pending
result=dict(status='STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED',authority_invalidation='ACKNOWLEDGED_READBACK',cleanup=pending['overall'],closure_components=pending,
            access='AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED',application_writes=0,stage4='OPEN',pipeline_retry='HELD')
state={}
def publish(record):
    state['scope_closed_during_publication']=hasattr(runner,'memory_closure')
    state['reserve_active']=runner.github.reserve is not None
    state['stage']=record['closure_stage']
    for _ in range(6):runner.github.call('GET','x')
    state['snapshot_peak']=memory.snapshot()['aggregate']['peak_bytes']
sealed=runner.seal_owner_result(result,publish)
assert state['scope_closed_during_publication'] is False and state['reserve_active'] is True and state['stage']=='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE' and len(calls)==6,(state,len(calls))
assert sealed['closure_stage']=='FINAL_AFTER_PUBLICATION' and sealed['publication']=='PUBLISHED' and sealed['cleanup']=='CLOSED' and sealed['closure_components']['process']['memory']['owned_groups_removed'] is True,sealed
assert sealed['authority_invalidation']=='ACKNOWLEDGED_READBACK' and orr.exit_status(sealed)==0
assert json.loads((out/'j'/'final-result.json').read_bytes())['closure_stage']=='FINAL_AFTER_PUBLICATION'
try:
    runner.github.call('GET','x')
    raise SystemExit('NOT DENIED AFTER CLOSURE')
except Denied as exc:
    assert exc.args[0]=='RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS',exc.args
assert len(calls)==6
print('owner publication-inside-scope proof ok; calls during publication:',len(calls),'peak aggregate bytes:',state['snapshot_peak'])
