"""One administrative connection probe: preparation plus at most ONE connection attempt and ONE fixed read-only statement.

This is NOT a mode of the operational Runner. The Runner's setup path mutates credentials, GitHub secrets, roles, grants and queue state; the previous
CONNECTION_DIAGNOSTIC_ONLY mode ran that setup. This controller constructs none of those capabilities: it has no GitHub client, no Owner, no credential
mapping, no source reader and no ledger. The absence is structural (nothing to call), and is additionally proven by tests that spy on every external effect.

Outcomes are stated separately and truthfully; a classified connection failure is diagnostic progress, never a qualification, and a qualified ADMINISTRATIVE
connection says nothing about restricted worker authentication.
"""
import argparse,getpass,hashlib,json,os,resource,subprocess,sys,time,warnings
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .connection_diagnostics import safe_failure,PreparationFailure
from .operational_journal import Journal
from .operational_outcome import session,early_closure,ACCOUNTING_SCHEMA
from .operational_preparation import Progress,prepare_connection
from .tls_trust import owned_resources,PEM_SHA256

MODE='ADMIN_CONNECTION_PROBE_ONLY'
AUTHORITY='AUTHORISE_INGESTION_ADMIN_CONNECTION_PROBE_ONCE_20261018'
STATUS='OWNER_APPROVED_ADMIN_CONNECTION_PROBE_ONCE'
STATE='operational-admin-connection-probe-once-20261018'
# Narrowly bound, single-use namespaces. Attempt 1 is CONSUMED (input-window stop, recorded); attempt 2 is the one successor. There is no open-ended counter: an attempt
# number outside this table is rejected, and a successor is valid only against verified predecessor evidence.
ATTEMPTS={1:dict(authority=AUTHORITY,state_directory=STATE,predecessor=None),
          2:dict(authority=AUTHORITY+'_SUCCESSOR_2',state_directory=STATE+'-successor-2',predecessor=1)}
PREDECESSOR_KEYS=frozenset({'attempt','state_directory','events_sha256','final_result_sha256'})


def probe_namespace(attempt):
    if attempt not in ATTEMPTS:raise ValueError('PROBE_ATTEMPT_NOT_AUTHORISED')
    return dict(ATTEMPTS[attempt])
EVIDENCE_DIRECTORY='docs/design/ingestion-admin-connection-probe-20261018'
STATEMENT='SELECT current_user'
EXPECTED_IDENTITY='postgres'
# Every number below is bound into the registration and enforced in code. Startup `options` (statement_timeout 10 s, lock_timeout 3 s) are inherited unchanged from
# the reviewed preparation module; connect_timeout is 3 s. The sum of the two database waits is therefore at most 13 s.
LIMITS=dict(connection_attempts=1,driver_statements=1,rollbacks=0,commits=0,returned_data_value_bytes=128,database_seconds=13,dns_subprocesses=1,dns_seconds=3,
            hidden_input_seconds=120,active_seconds=45,final_report_seconds=5,controller_memory_bytes=256*1024**2,aggregate_memory_bytes=1536*1024**2,
            persisted_evidence_bytes=65536,terminal_json_bytes=32768)
TIMING=dict(input_seconds=LIMITS['hidden_input_seconds'],active_seconds=LIMITS['active_seconds'],work_seconds=35,diagnostic_seconds=5,report_seconds=LIMITS['final_report_seconds'],outer_seconds=180)
ABSENT_CAPABILITIES=('credential_generation','protected_secret_mapping','github_access','role_or_membership_change','function_installation','grant_or_exception_issuance',
                     'queue_or_ledger_mutation','council_or_source_request','restricted_worker_authentication','application_writer')
REGISTRATION_KEYS=frozenset({'mode','authority','status','expires_at','revision','tree','hashes','controller_sha256','ca_sha256','evidence_directory','limits','absent_capabilities','statement_sha256','attempt','state_directory','predecessor'})
PROBE_REASONS=frozenset({'CONNECTION_ATTEMPT_BOUND','STATEMENT_BOUND','RESPONSE_BOUND','RESPONSE_SHAPE','ACTIVE_WINDOW_EXHAUSTED','OWNER_STOP','STATEMENT_UNEXPECTED'})


class ProbeDenied(RuntimeError):
    """A fixed, allow-listed budget or shape denial; str() is the fixed code only."""
    def __init__(self,code):
        if code not in PROBE_REASONS:raise ValueError('PROBE_CODE')
        self.code=code;super().__init__(code)


def hidden_input():
    # A TTY alone does not prove echo control works; abort rather than permit getpass's echoed fallback.
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        return getpass.getpass('Existing migration credential URL (hidden; never paste into chat): ')


def measured(value):return dict(value=value,basis='MEASURED')
ABSENT=dict(value=0,basis='CAPABILITY_ABSENT')


class ProbeRunner:
    """Exactly the objects the probe needs: a connect closure, a journal, a progress record, the native-memory object. Nothing else is reachable from here."""
    def __init__(self,journal,connect,progress,memory,*,baseline,started,stop_file=None):
        self.journal=journal;self.emit=journal.emit;self.connect=connect;self.progress=progress;self.memory=memory;self.baseline=baseline;self.started=started
        self.stop_file=stop_file or journal.root/'STOP'
        self.attempts=0;self.opened=0;self.closed=0;self.statements=0;self.returned_bytes=0;self.database_seconds=0.0;self.phase=None;self.conn=None;self.identity_matches=None

    def check(self):
        if self.memory is not None:self.memory.snapshot()
        if time.monotonic()-self.started>=LIMITS['active_seconds']:raise ProbeDenied('ACTIVE_WINDOW_EXHAUSTED')
        if self.stop_file.exists():raise ProbeDenied('OWNER_STOP')

    def one_statement(self,connection,statement):
        if statement!=STATEMENT:raise ProbeDenied('STATEMENT_UNEXPECTED')           # nothing but the reviewed constant can ever be sent
        if self.statements>=LIMITS['driver_statements']:raise ProbeDenied('STATEMENT_BOUND')
        self.statements+=1
        cursor=connection.execute(statement)
        rows=cursor.fetchall()
        result=cursor.pgresult
        if result is not None:self.returned_bytes+=sum(len(result.get_value(r,k) or b'') for r in range(result.ntuples) for k in range(result.nfields))
        if self.returned_bytes>LIMITS['returned_data_value_bytes']:raise ProbeDenied('RESPONSE_BOUND')
        if len(rows)!=1 or len(rows[0])!=1 or not isinstance(rows[0][0],str):raise ProbeDenied('RESPONSE_SHAPE')
        return rows[0][0]

    def close_connection(self):
        connection=self.conn
        if connection is None:return
        try:connection.close()
        finally:
            if getattr(connection,'closed',False):self.closed+=1
            self.conn=None

    def execute(self):
        try:
            self.emit('probe_intent',dict(limits=LIMITS,statement_sha256=hashlib.sha256(STATEMENT.encode()).hexdigest(),absent_capabilities=list(ABSENT_CAPABILITIES)))
            self.check()
            if self.attempts>=LIMITS['connection_attempts']:raise ProbeDenied('CONNECTION_ATTEMPT_BOUND')
            self.attempts+=1;begun=time.monotonic();self.phase='DRIVER_CONNECT'
            try:
                self.conn=self.connect();self.opened+=1
                self.emit('connection_opened',dict(attempt=self.attempts))
                self.phase='EXECUTION'
                identity=self.one_statement(self.conn,STATEMENT)
                self.identity_matches=identity==EXPECTED_IDENTITY
            finally:
                self.database_seconds+=time.monotonic()-begun
                self.close_connection()
            return self.finish()
        except BaseException as exc:return self.failed(exc)

    def accounting(self):
        return dict(administration=dict(connection_attempts=measured(self.attempts),connections_opened=measured(self.opened),connections_closed=measured(self.closed),
                                        driver_statements=dict(value=self.statements,basis='CLIENT_COUNTED',server_observation='TEST_ONLY_NOT_AVAILABLE_IN_PRODUCTION_RESULT'),rollbacks=measured(0),commits=measured(0),returned_data_value_bytes=measured(self.returned_bytes),
                                        supervised_seconds=measured(round(self.database_seconds,6)),credential_generations=dict(ABSENT),secret_mappings=dict(ABSENT),role_changes=dict(ABSENT),
                                        function_installations=dict(ABSENT),grants_or_exceptions=dict(ABSENT),queue_mutations=dict(ABSENT),council_requests=dict(ABSENT)),
                    runtime=dict(slot_receipts={},slot_state='NO_RUNTIME_SLOT_CREATED',supervised_seconds=dict(ABSENT)),preparation=dict(scope='PREPARATION_ONLY',dns_subprocesses_spawned=self.progress.work()['dns_subprocesses_spawned']),
                    historical_accounting_gaps='PRESERVED_NOT_RECONSTRUCTED')

    def closure(self):
        proof=None
        try:
            if self.memory is not None:proof=self.memory.close()
        except BaseException:proof=dict(owned_groups_removed=False,owned_survivors=None)
        base=early_closure(self.baseline,proof,self.progress)
        process=base['process']
        # Connection closure needs positive evidence: either the object reports closed, or no connection was ever opened and no socket survived.
        if self.opened:connection_ok=self.closed==self.opened
        else:connection_ok=process.get('new_socket_count')==0
        connection=dict(status='CLOSED' if connection_ok else 'UNCERTAIN',attempts=self.attempts,opened=self.opened,closed=self.closed)
        access=dict(status='NOT_REQUIRED_NO_ACCESS_CREATED')
        overall='CLOSED' if connection_ok and process['status']=='CLOSED' else 'UNCERTAIN'
        return dict(access=access,connections=connection,process=process,overall=overall,outer_scope_removal='NOT_VERIFIABLE_BEFORE_CONTROLLER_EXIT')

    def common(self,components):
        return dict(cleanup=components['overall'],closure_components=components,authority_invalidation='NOT_REQUIRED_NO_AUTHORITY',access='NO_ACCESS_CREATED',
                    preparation=self.progress.report(),accounting=self.accounting(),accounting_schema=ACCOUNTING_SCHEMA,owned_cleanup=components['process'],
                    application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True,mode=MODE)

    def finish(self):
        components=self.closure()
        verified=components['overall']=='CLOSED'
        if self.identity_matches:
            outcome=dict(preparation='COMPLETED',administrative_connection='QUALIFIED',failure='NONE',closure='VERIFIED' if verified else 'UNCERTAIN',
                         scope='ADMIN_ROLE_CONNECTION_ONLY',worker_authentication_qualified=False,route_qualified_for_restricted_roles=False)
            return dict(status='ADMIN_CONNECTION_QUALIFIED' if verified else 'ADMIN_CONNECTION_QUALIFIED_CLOSURE_UNCERTAIN',outcome=outcome,identity_observation='MATCHES_EXPECTED_ADMIN_ROLE',**self.common(components))
        failure=dict(phase='EXECUTION',exception_kind='OTHER',sqlstate=None,reason_code='ADMIN_IDENTITY_UNEXPECTED',classification_source='FIXED_PROBE_CODE',
                     failed_native_connection_finished=False,underlying_cause='UNDETERMINED',message_exported=False)
        outcome=dict(preparation='COMPLETED',administrative_connection='FAILED_CLASSIFIED',failure='CLASSIFIED',closure='VERIFIED' if verified else 'UNCERTAIN',
                     scope='ADMIN_ROLE_CONNECTION_ONLY',worker_authentication_qualified=False,route_qualified_for_restricted_roles=False)
        return dict(status='STOP_RECONCILE_NO_RETRY',outcome=outcome,failure=failure,identity_observation='DIFFERS_FROM_EXPECTED_ADMIN_ROLE',**self.common(components))

    def failed(self,exc):
        try:self.close_connection()
        except BaseException:pass
        components=self.closure()
        admitted=self.attempts>0
        if isinstance(exc,ProbeDenied):
            failure=dict(phase=self.phase if admitted else 'PROBE_ADMISSION',exception_kind='OTHER',sqlstate=None,reason_code=exc.code,classification_source='FIXED_PROBE_CODE',
                         failed_native_connection_finished=False,underlying_cause='UNDETERMINED',message_exported=False)
        else:
            try:failure=safe_failure(exc,self.phase or 'PREPARATION')
            except BaseException:
                failure=dict(phase=self.phase or 'PROBE_ADMISSION',exception_kind='OTHER',sqlstate=None,reason_code='UNKNOWN',classification_source='NONE',failed_native_connection_finished=False,
                             underlying_cause='UNDETERMINED',message_exported=False)
        classified=failure.get('reason_code') not in (None,'UNKNOWN')
        attempt_state=('FAILED_CLASSIFIED' if classified else 'FAILED_UNCLASSIFIED') if admitted else 'NOT_ATTEMPTED'
        outcome=dict(preparation='COMPLETED',administrative_connection=attempt_state,failure='CLASSIFIED' if classified else 'UNCLASSIFIED',
                     closure='VERIFIED' if components['overall']=='CLOSED' else 'UNCERTAIN',scope='ADMIN_ROLE_CONNECTION_ONLY',worker_authentication_qualified=False,
                     route_qualified_for_restricted_roles=False)
        result=dict(status='STOP_RECONCILE_NO_RETRY',outcome=outcome,failure=failure,**self.common(components))
        try:self.emit('stopped',result)
        except BaseException:result['audit_stop_record']='UNCERTAIN'
        return result


def prepare_probe(r,raw,started,*,journal,memory,progress,baseline,dns_run=subprocess.run,dns_command=None,connect_factory=None):
    """Preparation stages shared with the operational path, then construction of the capability-free ProbeRunner.

    `connect_factory` is a TEST-ONLY seam that replaces the native connection closure with a disposable-server connection; main() never passes it."""
    prepared=prepare_connection(r,raw,progress=progress,dns_run=dns_run,dns_command=dns_command)
    connect=prepared.connect
    if connect_factory is not None:
        def connect():
            progress.database_connection_calls+=1
            return connect_factory()
    with progress.stage('RUNNER_CONSTRUCTION'):
        try:return ProbeRunner(journal,connect,progress,memory,baseline=baseline,started=started)
        except (KeyError,TypeError,ValueError,AttributeError):raise PreparationFailure('RUNNER_CONSTRUCTION','RUNNER_CONSTRUCTION_FAILED') from None


def validate_probe_registration(body,sha):
    if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('REGISTRATION_SHA256')
    r=json.loads(body)
    if not isinstance(r,dict) or set(r)!=REGISTRATION_KEYS:raise ValueError('REGISTRATION_EXACT_KEYS')
    attempt=r['attempt']
    if type(attempt) is not int or attempt not in ATTEMPTS:raise ValueError('PROBE_ATTEMPT_NOT_AUTHORISED')
    namespace=ATTEMPTS[attempt]
    if r['mode']!=MODE or r['authority']!=namespace['authority'] or r['status']!=STATUS or r['state_directory']!=namespace['state_directory']:raise ValueError('EXACT_PROBE_APPROVAL_REQUIRED')
    predecessor=r['predecessor']
    if namespace['predecessor'] is None:
        if predecessor is not None:raise ValueError('PREDECESSOR_BINDING')
    else:
        if not isinstance(predecessor,dict) or set(predecessor)!=PREDECESSOR_KEYS or type(predecessor['attempt']) is not int or predecessor['attempt']!=namespace['predecessor'] or predecessor['state_directory']!=ATTEMPTS[namespace['predecessor']]['state_directory'] \
           or not all(isinstance(predecessor[k],str) and len(predecessor[k])==64 for k in ('events_sha256','final_result_sha256')):raise ValueError('PREDECESSOR_BINDING')
    if r['limits']!=LIMITS or r['absent_capabilities']!=list(ABSENT_CAPABILITIES) or r['statement_sha256']!=hashlib.sha256(STATEMENT.encode()).hexdigest():raise ValueError('PROBE_LIMITS_OR_BOUNDARY_BINDING')
    expiry=datetime.fromisoformat(r['expires_at']);now=datetime.now(timezone.utc)
    if expiry.tzinfo is None or not now<expiry<=now+timedelta(hours=2):raise ValueError('PROBE_EXPIRY')
    if r['evidence_directory']!=EVIDENCE_DIRECTORY or not isinstance(r['hashes'],dict) or not r['hashes']:raise ValueError('EVIDENCE_BINDING')
    manifest=json.loads((Path(EVIDENCE_DIRECTORY)/'MANIFEST.json').read_text())
    if set(r['hashes'])!=set(manifest['bound_paths']):raise ValueError('HASHES_MUST_EQUAL_MANIFEST')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if revision!=r['revision'] or subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip()!=r['tree'] or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('CLEAN_REVIEWED_CHECKOUT')
    for path,digest_ in r['hashes'].items():
        p=Path(path)
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest_:raise ValueError('REVIEWED_CONTENT_BINDING')
    if r['controller_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest() or r['ca_sha256']!=PEM_SHA256:raise ValueError('CONTROLLER_CA_BINDING')
    return r


def verify_predecessor(r,state_root):
    """Positive evidence that the predecessor attempt stopped before any connection and closed: exact file hashes plus the recorded outcome. Read-only."""
    predecessor=r['predecessor']
    if predecessor is None:return None
    root=Path(state_root);directory=root/predecessor['state_directory']
    if directory.is_symlink() or not directory.is_dir() or directory.resolve().parent!=root.resolve():raise ValueError('PREDECESSOR_EVIDENCE')
    contents={}
    for name,key in (('events.jsonl','events_sha256'),('final-result.json','final_result_sha256')):
        path=directory/name
        if path.is_symlink() or not path.is_file():raise ValueError('PREDECESSOR_EVIDENCE')
        contents[name]=path.read_bytes()                                                            # read once: the bytes hashed are the bytes parsed
        if hashlib.sha256(contents[name]).hexdigest()!=predecessor[key]:raise ValueError('PREDECESSOR_EVIDENCE')
    recorded=json.loads(contents['final-result.json'])
    if recorded.get('status')!='STOP_RECONCILE_NO_RETRY' or recorded.get('cleanup')!='CLOSED' or recorded.get('failure',{}).get('stage')!='SESSION_INPUT' \
       or recorded.get('outcome',{}).get('administrative_connection')!='NOT_ATTEMPTED' or recorded.get('closure_components',{}).get('overall')!='CLOSED':raise ValueError('PREDECESSOR_OUTCOME')
    return dict(attempt=predecessor['attempt'],final_result_sha256=predecessor['final_result_sha256'],stage=recorded['failure']['stage'],closure=recorded['closure_components']['overall'])


def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',type=Path,required=True);p.add_argument('--registration-sha256',required=True);a=p.parse_args()
    if sys.platform!='linux' or not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('OWNER_LINUX_SECURE_TTY_REQUIRED')
    if any(k.startswith('PG') for k in os.environ):raise SystemExit('LIBPQ_ENVIRONMENT_OVERRIDE')
    if any(os.environ.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN')):raise SystemExit('NO_GITHUB_CREDENTIAL_PERMITTED_IN_PROBE')
    if a.registration.is_symlink() or a.registration.stat().st_size>16384:raise SystemExit('REGISTRATION_BOUND')
    r=validate_probe_registration(a.registration.read_bytes(),a.registration_sha256)
    from .operational_memory import OperationalMemory
    memory=OperationalMemory()                                                  # positive kernel enforcement BEFORE any credential is read
    state=Path.home()/'.local/state/propertyaigent';state.mkdir(mode=0o700,exist_ok=True,parents=True)
    verify_predecessor(r,state)
    journal=Journal(state/r['state_directory'])                                 # exclusive create: a second use of the same authority cannot start
    journal.emit('consumed',dict(authority=r['authority'],attempt=r['attempt'],registration_sha256=a.registration_sha256))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    progress=Progress();baseline=owned_resources()
    prepare=lambda raw,started:prepare_probe(r,raw,started,journal=journal,memory=memory,progress=progress,baseline=baseline)
    result=session(journal,r['expires_at'],hidden_input,prepare,memory=memory,timing=TIMING,progress=progress,baseline=baseline)
    ok=result.get('status')=='ADMIN_CONNECTION_QUALIFIED' and result.get('cleanup')=='CLOSED'
    raise SystemExit(0 if ok else 1)


if __name__=='__main__':main()
