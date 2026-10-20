"""The restricted GitHub-hosted half of the Bolton FORM PROBE (specification 032 section 12). Restricted credentials only: no administrative credential, no Owner, nothing that can register an authority.
One DB-gated source intent, ONE form-only request, an observation recorded in the ledger (never a capture), the result published inside the enforced scope and bounded reserve, then the scope is closed.
A council answer of any kind is an observation. It reuses the accepted hosted machinery (admission, stdin secrets, qualification, checkout binding, publication-then-closure) and differs only where the
probe differs."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
from app.ingestion.ledger import digest,Denied
from . import stable_pipeline as sp
from . import stable_qualification as sq
from .operational_journal import Journal
from .operational_owner import item,SCOPE
from .operational_runner import CONTRACT,PROBE_AUTHORITY,PROBE_EVIDENCE_DIRECTORY,PROBE_LIMITS
from .operational_publication import GitHub
from .tls_trust import verified_trust

PROBE_HOSTED_AUTHORITY='AUTHORISE_INGESTION_BOLTON_FORM_PROBE_HOSTED_ONCE_20261021'
PROBE_MANIFEST_PATH='docs/design/ingestion-form-probe-20261021/MANIFEST.json'
PROBE_HOSTED_DEADLINES=dict(job=900,diagnostic_total=960,diagnostic_window=40,admin_diagnostic=240,admin_pre=800,admin_total=890,runtime_total=120)
PROBE_GITHUB_BOUND=60      # the anchor probe, the head reads and the 10-request publication; modelled well below this


class ProbeHostedRunner(sp.HostedRunner):
    GRANT_SUFFIX='_PROBE'

    def __init__(self,urls,journal,github,source_reader,ssl,hostaddr,memory,*,evidence_head,manifest_sha256,revision,checkout_probe=None):
        super().__init__(urls,journal,github,source_reader,ssl,hostaddr,memory,evidence_head=evidence_head,manifest_sha256=manifest_sha256,revision=revision,checkout_probe=checkout_probe)
        self.authority=PROBE_AUTHORITY;self.deadlines=dict(PROBE_HOSTED_DEADLINES)
        self.r=dict(evidence_directory=PROBE_EVIDENCE_DIRECTORY,manifest_sha256=manifest_sha256,mode='BOLTON_FORM_PROBE_HOSTED')
        root=item(dict(subject=SCOPE,task='DISCOVERY',contract=CONTRACT,revision=manifest_sha256),max_attempts=1,limits=PROBE_LIMITS)
        self.capture_key=root['key'];self.capture_bindings=sp.bindings_for([root])
        self.execution=dict(revision=revision,manifest_sha256=manifest_sha256,capture_key=self.capture_key,initial_evidence_head=evidence_head,authority=PROBE_AUTHORITY)      # identical to the owner's pipeline_execution()

    def probe_once(self):
        self.operation_phase='FORM_PROBE'
        if self.capture is not None:raise Denied('PROBE_ALREADY_OBSERVED_NO_SOURCE_REPLAY')
        with self.phase_as('runtime'):
            with self.slot(self.capture_key,self.capture_bindings,self.authority+'_PROBE') as (co,budget):
                def read(row):
                    self.check();self.source_attempts+=1
                    self.source_resources={'status':'ATTEMPTED_ACCOUNTING_UNCERTAIN','attempted_requests':None,'received_body_bytes':None}
                    self.emit('source_invocation_intent',dict(ordinal=self.source_attempts))
                    observed=self.source_reader(row)
                    self.source_resources=dict(status='RETURNED',worker=observed[0].get('resource'),supervisor=observed[1])
                    self.emit('source_invocation_returned',dict(ordinal=self.source_attempts,resources=self.source_resources))
                    return observed
                self.check()
                self.capture=co.idox_form_probe(co.ledger.claim(self.capture_key,lease_seconds=165),read)
        self.emit('form_probe_observed',dict(receipt_sha256=digest(self.capture),outcome=self.capture['observation']['outcome'],transport=self.capture['observation']['transport']))

    def probe_result(self,qualification):
        components=self.closure('RESTRICTED_RUNTIME_NO_ACCESS_CHANGE',memory_close=False)      # the memory scope keeps enforcing until the result is published (finalise)
        ok=components['overall'] in ('CLOSED','PENDING_MEMORY_SCOPE_CLOSURE')
        return dict(status='BOLTON_FORM_PROBE_OBSERVED_RESTRICTED_RUNTIME_ONLY' if ok else 'STOP_RECONCILE_NO_RETRY',closure_stage='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE',execution=self.execution,
                    checkout_binding=self.checkout_binding,cleanup=components['overall'],closure_components=components,qualification=qualification,capture_sha256=digest(self.capture),
                    probe_receipt=self.capture,diagnostic_only=True,not_a_capture=True,slot_receipts=self.receipts,accounting=self.accounting(),authority_check_receipt=self.authority_check,
                    source_resources=self.source_resources,source_observations_attempted=self.source_attempts,application_writes=0,credential_changes=0,grants_issued=0,
                    client_closure_vs_server_session='CLIENT_SIDE_RECEIPTS_ONLY_SERVER_SESSIONS_ARE_AN_OWNER_READBACK',pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True,
                    memory_enforcement=dict(kind='CGROUP_V2_ACTUAL_MEMORY' if self.memory is not None else 'NOT_ESTABLISHED',aggregate_bytes=1536*1024**2 if self.memory is not None else None))

    def run(self):
        qualification=None
        try:
            self.operation_phase='CONNECTION_QUALIFICATION'
            q=sq.Qualification(self.owner.urls,emit=self.emit,ssl=self.ssl,hostaddr=self.hostaddr,stop_file=self.journal.root/'STOP')
            qualification=q.run()
            self.emit('connection_qualification_result',dict(status=qualification['status'],stop_reason=qualification.get('stop_reason'),attempts_total=qualification['attempts_total'],accounting=qualification['accounting']))
            if qualification['status']!='STABLE_CREDENTIALS_QUALIFIED':raise Denied('CONNECTION_QUALIFICATION_'+str(qualification.get('stop_reason')))
            qualification={k:qualification[k] for k in ('status','attempts_total','accounting','elapsed_seconds')}
            self.operation_phase='CAPTURE_AUTHORITY_CHECK';self.authority_check=self.authority_present()      # the named allowance exists, is unexpired, and this checkout is exactly the approved one
            self.probe_once()
            result=self.probe_result(qualification)
        except BaseException as exc:
            result=self.hosted_failure(exc,qualification)
        return result

    def publish_completed(self,result):
        self.journal.save('final-result.json',result)
        self.evidence_head=self.github.publish({'events.jsonl':self.journal.file.read_bytes(),'final-result.json':json.dumps(result,sort_keys=True,separators=(',',':')).encode()},
                                               directory=PROBE_EVIDENCE_DIRECTORY+'/completed',expected_head=self.head())
        return self.evidence_head


def run_probe_hosted(*,urls,journal,gh_runner,source_reader_factory,ssl,hostaddr,memory,evidence_head,manifest_sha256,revision,checkout_probe=None):
    """The hosted form probe over INJECTED effects (as run_hosted): production passes the reviewed implementations from main(); the disposable rehearsal passes loopback fixtures."""
    holder={}
    github=GitHub(journal.emit,lambda:holder['runner'].check(),runner=gh_runner,bound=PROBE_GITHUB_BOUND)
    runner=ProbeHostedRunner(urls,journal,github,None,ssl,hostaddr,memory,evidence_head=evidence_head,manifest_sha256=manifest_sha256,revision=revision,checkout_probe=checkout_probe);holder['runner']=runner
    runner.source_reader=source_reader_factory(runner)
    if runner.head()!=evidence_head:return sp.stop_early(journal,'EVIDENCE_HEAD_MOVED'),1
    if github.probe(sp.REPO+'/contents/'+sp.EVIDENCE_ANCHOR+'?ref='+evidence_head) is None:return sp.stop_early(journal,'EVIDENCE_BRANCH_ANCHOR_MISSING'),1
    result=runner.finalise(runner.run())      # publication first (scope still enforcing, bounded reserve), then the final closure
    print(json.dumps({k:result.get(k) for k in ('status','cleanup','publication','publication_reason')},sort_keys=True))
    return result,0 if result.get('cleanup')=='CLOSED' and result.get('status')!='STOP_RECONCILE_NO_RETRY' else 1


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    if not sp.admitted(os.environ,PROBE_HOSTED_AUTHORITY):raise SystemExit('PIPELINE_NOT_ADMITTED')
    token,urls=sp.read_secrets(sys.stdin.buffer)      # stdin only: the secrets are never in this process's environment
    journal=Journal(args.output);journal.emit('consumed',dict(authority=PROBE_HOSTED_AUTHORITY,evidence_head=os.environ['PIPELINE_EVIDENCE_HEAD']))
    sq.install_cancellation()
    from .operational_memory import OperationalMemory
    try:memory=OperationalMemory()      # kernel-enforced ACTUAL memory (cgroup v2), established BEFORE any database connection; unavailable = stop here
    except Exception as exc:
        sp.stop_early(journal,'ACTUAL_MEMORY_ENFORCEMENT_UNAVAILABLE',type(exc).__name__);raise SystemExit(1)
    journal.emit('actual_memory_enforcement_established',dict(kind='CGROUP_V2',aggregate_bytes=1536*1024**2,controller_bytes=256*1024**2,source_bytes=1024**3,swap=0))
    github_env=dict(PATH='/usr/bin:/bin',HOME=str(args.output.parent),GH_TOKEN=token,GH_HOST='github.com')
    from .operational_preparation import Progress,resolve_addresses
    progress=Progress()
    try:
        ca,_=verified_trust();hostaddr=resolve_addresses(progress)
    except BaseException as exc:
        sp.stop_early(journal,'PREPARATION_FAILED',type(exc).__name__);raise SystemExit(1)
    from .operational_source import read
    def source_reader_factory(runner):
        return lambda _row:read('form_probe',dict(council='bolton',semantics='RECEIVED',start='2026-10-16',end='2026-10-16'),root=journal.root/'source',stop_file=journal.root/'STOP',memory_group=memory.source,observe=runner.observe_source)
    result,code=run_probe_hosted(urls=urls,journal=journal,gh_runner=lambda command,**kw:subprocess.run(command,env=github_env,**kw),source_reader_factory=source_reader_factory,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},
                                 hostaddr=hostaddr,memory=memory,evidence_head=os.environ['PIPELINE_EVIDENCE_HEAD'],manifest_sha256=hashlib.sha256(Path(PROBE_MANIFEST_PATH).read_bytes()).hexdigest(),revision=os.environ['PIPELINE_REVIEWED_SHA'])
    raise SystemExit(code)


if __name__=='__main__':main()
