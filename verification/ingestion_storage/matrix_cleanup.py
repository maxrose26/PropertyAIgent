"""Single-use cleanup of the temporary access left by the restricted-connection matrix. NOT a mode of the operational Runner; no ingestion capability exists here.

Exactly: (1) re-read the two logins' flags, memberships and sessions (no query text, no credentials); (2) end AT MOST ONE named worker session, only if the fresh read shows it is the
only session of those logins and its pid, role and backend start time still match, in a single statement whose predicate repeats all three; (3) verify no session remains;
(4) delete exactly the two temporary secrets and read the secret NAMES back. It changes no role, password, membership, grant, control or ledger row.

Disabling a login (NOLOGIN, NULL password, no membership) stops NEW logins; it does not end a session that already exists, which is why the session step exists. Every
claim of closure needs its own positive readback; anything not read back is reported UNCERTAIN, never closed.
"""
import argparse,hashlib,json,os,re,resource,subprocess,sys,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .connection_diagnostics import safe_failure,PreparationFailure
from .operational_journal import Journal
from .operational_outcome import session,early_closure,ACCOUNTING_SCHEMA
from .operational_preparation import Progress,prepare_connection
from .tls_trust import owned_resources,PEM_SHA256

MODE='RESTRICTED_MATRIX_CLEANUP_ONLY'
AUTHORITY='AUTHORISE_RESTRICTED_MATRIX_CLEANUP_ONCE_20261018'
STATUS='OWNER_APPROVED_RESTRICTED_MATRIX_CLEANUP_ONCE'
STATE='operational-restricted-matrix-cleanup-once-20261018'
EVIDENCE_DIRECTORY='docs/design/ingestion-matrix-cleanup-20261018'
MATRIX_STATE='operational-restricted-connection-matrix-once-20261018'
ROLES=('ingestion_effect_login','ingestion_worker_login')
SECRETS=('INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL')
PRESERVED='DATABASE_URL'
SECRET_PATH='repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets'
IDENT_SQL="SELECT current_user,session_user,pg_catalog.pg_has_role(current_user,'pg_read_all_stats','MEMBER'),pg_catalog.pg_has_role(current_user,'pg_signal_backend','MEMBER')"
STATE_SQL="""SELECT jsonb_build_object(
 'roles',(SELECT coalesce(jsonb_agg(jsonb_build_array(r.rolname,r.rolcanlogin,a.rolpassword IS NULL,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication) ORDER BY r.rolname),'[]'::jsonb)
  FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s)),
 'memberships',(SELECT coalesce(jsonb_agg(jsonb_build_array(m.member::regrole::text,m.roleid::regrole::text) ORDER BY m.member::regrole::text,m.roleid::regrole::text),'[]'::jsonb)
  FROM pg_catalog.pg_auth_members m WHERE m.member=ANY(%s::regrole[])),
 'sessions',(SELECT coalesce(jsonb_agg(jsonb_build_object('pid',pid,'usename',usename,'state',state,'backend_start',backend_start) ORDER BY pid),'[]'::jsonb)
  FROM pg_catalog.pg_stat_activity WHERE usename=ANY(%s)))"""
TERMINATE_SQL="SELECT pg_terminate_backend(pid) FROM pg_catalog.pg_stat_activity WHERE pid=%s AND usename=%s AND backend_start=%s::timestamptz"
ALLOWED_SQL=(IDENT_SQL,STATE_SQL,TERMINATE_SQL)
LIMITS=dict(database_connections=2,driver_commands=20,database_active_seconds=30,session_terminations=1,github_requests=3,github_deletions=2,github_name_reads=1,
            hidden_input_seconds=120,active_seconds=60,outer_seconds=210,returned_data_value_bytes=8192,controller_memory_bytes=256*1024**2,aggregate_memory_bytes=1536*1024**2,
            termination_polls=3,persisted_evidence_bytes=65536)
TIMING=dict(input_seconds=120,active_seconds=60,work_seconds=50,diagnostic_seconds=5,report_seconds=5,outer_seconds=210)
ABSENT_CAPABILITIES=('role_or_password_change','membership_or_grant_change','control_or_ledger_change','credential_generation','secret_creation','restricted_login_connection',
                     'council_or_source_request','application_writer','termination_of_any_other_session')
REGISTRATION_KEYS=frozenset({'mode','authority','status','expires_at','revision','tree','hashes','controller_sha256','ca_sha256','evidence_directory','limits','absent_capabilities',
                             'statements_sha256','target','secrets','preserved_secret','predecessor','state_directory'})
PREDECESSOR_KEYS=frozenset({'state_directory','events_sha256','final_result_sha256'})
TARGET_KEYS=frozenset({'pid','role'})


class Halt(RuntimeError):
    """A fixed-code stop; str() is the code only."""
    CODES=frozenset({'COMMAND_BOUND','CONNECTION_BOUND','ACTIVE_SECONDS_BOUND','TERMINATION_BOUND','GITHUB_BOUND','EXACT_ROUTE_REQUIRED','STATEMENT_NOT_ALLOWED','RESPONSE_SHAPE',
                     'UNEXPECTED_ADMIN_IDENTITY','ROLES_NOT_DISABLED_NO_CHANGE','TERMINATION_RESPONSE_UNEXPECTED','DELETE_ACK_UNCERTAIN','NAMES_READBACK_UNCERTAIN','CLOSE_UNCERTAIN',
                     'RETURNED_BYTES_BOUND','FINAL_STATE_NOT_VERIFIED','SESSION_VISIBILITY_INSUFFICIENT'})
    def __init__(self,code):
        if code not in self.CODES:raise ValueError('HALT_CODE')
        self.code=code;super().__init__(code)


def statements_digest():return hashlib.sha256(json.dumps(list(ALLOWED_SQL)).encode()).hexdigest()
def measured(value):return dict(value=value,basis='MEASURED')
EXPECTED_DISABLED=[[r,False,True,False,False,False,False,False] for r in ROLES]


class Cleanup:
    def __init__(self,journal,connect,progress,memory,*,target,github_runner=subprocess.run,baseline=None,started=None,clock=time.monotonic,sleep=time.sleep):
        self.journal=journal;self.emit=journal.emit;self.connect=connect;self.progress=progress;self.memory=memory;self.target=dict(target);self.github_runner=github_runner
        self.baseline=baseline;self.started=started if started is not None else clock();self.clock=clock;self.sleep=sleep
        self.connections=0;self.opened=0;self.closed=0;self.commands=0;self.returned=0;self.db_seconds=0.0;self.terminations=0;self.github=dict(requests=0,deletions=0,reads=0)
        self.disposition=dict(roles='UNVERIFIED',memberships='UNVERIFIED',sessions='UNVERIFIED',termination='NOT_ATTEMPTED',secrets_deleted='NOT_ATTEMPTED',secrets_absent='UNVERIFIED',database_url='UNVERIFIED')
        self.readbacks={};self.termination=dict(attempted=False);self.deleted=[];self.phase='START';self.can_signal=False

    # ---- bounded primitives ---------------------------------------------------------------------------------------------------------------------------
    def check(self):
        if self.memory is not None:self.memory.snapshot()
        if self.clock()-self.started>=LIMITS['active_seconds']-10:raise Halt('ACTIVE_SECONDS_BOUND')
        if self.db_seconds>=LIMITS['database_active_seconds']:raise Halt('ACTIVE_SECONDS_BOUND')

    def accounting(self):
        gh=self.github
        return dict(database=dict(connections=measured(self.connections),connections_opened=measured(self.opened),connections_closed=measured(self.closed),driver_commands=measured(self.commands),
                                  returned_data_value_bytes=measured(self.returned),active_seconds=measured(round(self.db_seconds,6)),session_terminations=measured(self.terminations),
                                  role_or_membership_or_ledger_changes=dict(value=0,basis='CAPABILITY_ABSENT')),
                    github=dict(requests=measured(gh['requests']),deletions=measured(gh['deletions']),name_reads=measured(gh['reads'])),
                    preparation=dict(scope='PREPARATION_ONLY',dns_subprocesses_spawned=self.progress.work()['dns_subprocesses_spawned']),historical_accounting_gaps='PRESERVED_NOT_RECONSTRUCTED')

    def q(self,c,label,statement,params=None):
        if statement not in ALLOWED_SQL:raise Halt('STATEMENT_NOT_ALLOWED')
        self.check()
        if self.commands>=LIMITS['driver_commands']:raise Halt('COMMAND_BOUND')
        self.commands+=1;self.phase=label;self.emit('database_intent',dict(operation=label))
        began=self.clock()
        try:
            cursor=c.execute(statement,params);rows=cursor.fetchall() if cursor.description else []
            result=cursor.pgresult
            if result is not None:self.returned+=sum(len(result.get_value(r,k) or b'') for r in range(result.ntuples) for k in range(result.nfields))
        finally:self.db_seconds+=self.clock()-began
        if self.returned>LIMITS['returned_data_value_bytes']:raise Halt('RETURNED_BYTES_BOUND')
        self.emit('database_ack',dict(operation=label));return rows

    class _Conn:
        def __init__(self,outer):self.o=outer;self.c=None
        def __enter__(self):
            o=self.o;o.check()
            if o.connections>=LIMITS['database_connections']:raise Halt('CONNECTION_BOUND')
            o.connections+=1;o.phase='DATABASE_CONNECT_%d'%o.connections;o.emit('connection_intent',dict(ordinal=o.connections));began=o.clock()
            try:self.c=o.connect();o.opened+=1
            finally:o.db_seconds+=o.clock()-began
            o.emit('connection_open',dict(ordinal=o.connections));return self.c
        def __exit__(self,*exc):
            o=self.o
            if self.c is not None:
                began=o.clock()
                try:self.c.close()
                finally:o.db_seconds+=o.clock()-began
                if not getattr(self.c,'closed',False):raise Halt('CLOSE_UNCERTAIN')
                o.closed+=1;o.emit('connection_closed',dict(ordinal=o.connections))
            return False

    def connection(self):return Cleanup._Conn(self)

    def read_state(self,c,label):
        value=self.q(c,label,STATE_SQL,(list(ROLES),list(ROLES),list(ROLES)))
        if len(value)!=1 or len(value[0])!=1 or not isinstance(value[0][0],dict) or set(value[0][0])!={'roles','memberships','sessions'}:raise Halt('RESPONSE_SHAPE')
        state=value[0][0]
        if any(s.get('pid') is None or s.get('usename') is None or s.get('state') is None or s.get('backend_start') is None for s in state['sessions']):raise Halt('SESSION_VISIBILITY_INSUFFICIENT')
        self.readbacks[label]=dict(roles=state['roles'],memberships=state['memberships'],sessions=[dict(pid=s['pid'],usename=s['usename'],state=s['state'],backend_start=s['backend_start']) for s in state['sessions']])
        self.emit('access_readback',dict(label=label,**self.readbacks[label]));return state

    def check_disabled(self,state,*,require_no_sessions):
        roles_ok=state['roles']==EXPECTED_DISABLED;memberships_ok=state['memberships']==[];sessions_ok=state['sessions']==[]
        self.disposition['roles']='VERIFIED' if roles_ok else 'NOT_DISABLED';self.disposition['memberships']='VERIFIED' if memberships_ok else 'REMAIN'
        self.disposition['sessions']='VERIFIED_NONE' if sessions_ok else 'PRESENT'
        return roles_ok and memberships_ok and (sessions_ok or not require_no_sessions)

    def api(self,method,path):
        self.check();gh=self.github
        if gh['requests']>=LIMITS['github_requests']:raise Halt('GITHUB_BOUND')
        if method=='DELETE':
            if path not in [SECRET_PATH+'/'+n for n in SECRETS] or gh['deletions']>=LIMITS['github_deletions']:raise Halt('EXACT_ROUTE_REQUIRED')
            gh['deletions']+=1
        elif method=='GET':
            if path!=SECRET_PATH+'?per_page=100' or gh['reads']>=LIMITS['github_name_reads']:raise Halt('EXACT_ROUTE_REQUIRED')
            gh['reads']+=1
        else:raise Halt('EXACT_ROUTE_REQUIRED')
        gh['requests']+=1;self.phase='GITHUB_'+method;self.emit('github_intent',dict(method=method,path=path))
        command=['gh','api','--method',method,path]+(['--include','--silent'] if method=='DELETE' else [])
        try:
            result=self.github_runner(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(1.0,min(8.0,LIMITS['active_seconds']-10-(self.clock()-self.started)-2)))
            if result.returncode or len(result.stdout)+len(result.stderr)>65536:raise ValueError('ack')
            if method=='DELETE':
                if re.findall(rb'^HTTP/\S+\s+(\d{3})(?:\s|$)',result.stdout,re.M)!=[b'204']:raise ValueError('ack')
                value=None
            else:value=json.loads(result.stdout)
        except BaseException:
            raise Halt('DELETE_ACK_UNCERTAIN' if method=='DELETE' else 'NAMES_READBACK_UNCERTAIN') from None
        self.emit('github_ack',dict(method=method,path=path))
        if method=='DELETE':self.deleted.append(path.rsplit('/',1)[1])
        return value

    # ---- the cleanup ------------------------------------------------------------------------------------------------------------------------------------
    def terminate_if_exactly_the_target(self,c,first):
        sessions=first['sessions'];target=self.target
        if sessions and not self.can_signal:
            self.termination=dict(attempted=False,outcome='SIGNAL_PRIVILEGE_ABSENT_NOT_TERMINATED');self.disposition['termination']='PRIVILEGE_ABSENT_NOT_TERMINATED';self.emit('session_discrepancy',self.termination);return
        if not sessions:
            self.termination=dict(attempted=False,outcome='TARGET_ALREADY_ABSENT');self.disposition['termination']='NOT_NEEDED_NO_SESSION';return
        match=[s for s in sessions if s['pid']==target['pid'] and s['usename']==target['role']]
        if len(sessions)!=1 or len(match)!=1:
            self.termination=dict(attempted=False,outcome='DISCREPANCY_NOT_TERMINATED',observed=[dict(pid=s['pid'],usename=s['usename'],state=s['state']) for s in sessions])
            self.disposition['termination']='DISCREPANCY_NOT_TERMINATED';self.emit('session_discrepancy',self.termination);return
        observed=match[0]
        # immediate re-read before the single terminating statement: same pid, role and backend start, still the only session
        again=self.read_state(c,'before_termination')
        if again['sessions']!=sessions or again['roles']!=EXPECTED_DISABLED or again['memberships']!=[]:
            self.termination=dict(attempted=False,outcome='CHANGED_BEFORE_TERMINATION_NOT_TERMINATED');self.disposition['termination']='DISCREPANCY_NOT_TERMINATED';self.emit('session_discrepancy',self.termination);return
        if self.terminations>=LIMITS['session_terminations']:raise Halt('TERMINATION_BOUND')
        self.terminations+=1
        self.termination=dict(attempted=True,pid=observed['pid'],role=observed['usename'],state_at_observation=observed['state'],observed_backend_start=observed['backend_start'])
        self.emit('termination_intent',dict(self.termination))
        response=self.q(c,'terminate_exact_session',TERMINATE_SQL,(observed['pid'],observed['usename'],observed['backend_start']))
        if response==[]:
            # the statement matched no row: the session exited (or no longer matches) between the re-read and the signal. Re-read; never assume.
            gone=self.read_state(c,'after_unmatched_termination')
            if gone['sessions']==[]:
                self.termination['outcome']='EXITED_BEFORE_SIGNAL_ABSENT';self.disposition['termination']='EXITED_BEFORE_SIGNAL_VERIFIED_ABSENT';return
            self.termination['outcome']='NO_MATCH_SESSIONS_REMAIN_NOT_TERMINATED';self.disposition['termination']='DISCREPANCY_NOT_TERMINATED';self.emit('session_discrepancy',self.termination);return
        if response!=[(True,)]:
            self.termination['outcome']='SIGNAL_NOT_ACCEPTED';self.disposition['termination']='UNVERIFIED';raise Halt('TERMINATION_RESPONSE_UNEXPECTED')
        self.termination['signal_acknowledged']=True;self.emit('termination_acknowledged',dict(pid=observed['pid']))
        for attempt in range(LIMITS['termination_polls']):
            self.sleep(.5)
            after=self.read_state(c,'after_termination_%d'%(attempt+1))
            if after['sessions']==[]:
                self.termination['outcome']='TERMINATED_AND_ABSENT';self.disposition['termination']='TERMINATED_VERIFIED_ABSENT';return
        self.termination['outcome']='SIGNALLED_STILL_PRESENT';self.disposition['termination']='SIGNALLED_NOT_VERIFIED_ABSENT'

    def execute(self):
        try:
            with self.connection() as c:
                ident=self.q(c,'admin_identity',IDENT_SQL)
                if len(ident)!=1 or ident[0][:2]!=('postgres','postgres'):raise Halt('UNEXPECTED_ADMIN_IDENTITY')
                if ident[0][2] is not True:raise Halt('SESSION_VISIBILITY_INSUFFICIENT')      # without it an unseen session would read as none
                self.can_signal=ident[0][3] is True
                first=self.read_state(c,'before_cleanup')
                if not self.check_disabled(first,require_no_sessions=False):raise Halt('ROLES_NOT_DISABLED_NO_CHANGE')
                self.terminate_if_exactly_the_target(c,first)
            # the secret names are removed whenever the logins were verified disabled, independently of the session outcome. The FIRST reads only gate this; every closure claim below
            # is re-derived from the FINAL readback alone, so a failed or missing final read can never leave a stale 'verified' behind.
            for k in ('roles','memberships','sessions'):self.disposition[k]='UNVERIFIED'
            self.phase='SECRET_DELETION'
            for name in SECRETS:self.api('DELETE',SECRET_PATH+'/'+name)
            self.disposition['secrets_deleted']='ACKNOWLEDGED_204_BOTH'
            value=self.api('GET',SECRET_PATH+'?per_page=100')
            names=[s.get('name') for s in value.get('secrets',[])] if isinstance(value,dict) else None
            if names is None or type(value.get('total_count')) is not int or len(names)!=value['total_count'] or any(not isinstance(n,str) for n in names):raise Halt('NAMES_READBACK_UNCERTAIN')
            self.disposition['secrets_absent']='VERIFIED' if not set(SECRETS)&set(names) else 'STILL_PRESENT'
            self.disposition['database_url']='PRESERVED_VERIFIED' if PRESERVED in names else 'MISSING'
            self.emit('secret_names_observed',dict(temporary_absent=self.disposition['secrets_absent']=='VERIFIED',preserved_present=PRESERVED in names,count=len(names)))
            with self.connection() as c:
                ident=self.q(c,'admin_identity_final',IDENT_SQL)
                if len(ident)!=1 or ident[0][:2]!=('postgres','postgres') or ident[0][2] is not True:raise Halt('UNEXPECTED_ADMIN_IDENTITY')
                final=self.read_state(c,'final_state')
                self.check_disabled(final,require_no_sessions=True)
            return self.finish()
        except BaseException as exc:return self.failed(exc)

    # ---- result -----------------------------------------------------------------------------------------------------------------------------------------
    def closure(self):
        proof=None
        try:
            if self.memory is not None:proof=self.memory.close()
        except BaseException:proof=dict(owned_groups_removed=False,owned_survivors=None)
        process=early_closure(self.baseline,proof,self.progress)['process']
        connection=dict(status='CLOSED' if self.opened==self.closed and process.get('new_socket_count')==0 else 'UNCERTAIN',opened=self.opened,closed=self.closed)
        d=self.disposition
        access_verified=(d['roles']=='VERIFIED' and d['memberships']=='VERIFIED' and d['sessions']=='VERIFIED_NONE' and d['secrets_absent']=='VERIFIED' and d['database_url']=='PRESERVED_VERIFIED')
        access=dict(status='DISABLED_VERIFIED' if access_verified else 'UNRECONCILED',**d)
        overall='CLOSED' if access_verified and connection['status']=='CLOSED' and process['status']=='CLOSED' else 'UNCERTAIN'
        return dict(access=access,connections=connection,process=process,overall=overall,outer_scope_removal='NOT_VERIFIABLE_BEFORE_CONTROLLER_EXIT')

    def common(self,components):
        return dict(cleanup=components['overall'],closure_components=components,access=components['access']['status'],termination=dict(self.termination),readbacks=self.readbacks,deleted_secrets=list(self.deleted),
                    accounting=self.accounting(),accounting_schema=ACCOUNTING_SCHEMA,preparation=self.progress.report(),owned_cleanup=components['process'],mode=MODE,
                    application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True,
                    note='Disabling a login stops new logins only; an existing session is not ended by NOLOGIN or password removal.')

    def finish(self):
        components=self.closure()
        status='RESTRICTED_MATRIX_CLEANUP_VERIFIED' if components['overall']=='CLOSED' else 'RESTRICTED_MATRIX_CLEANUP_INCOMPLETE_RECONCILE'
        return dict(status=status,**self.common(components))

    def failed(self,exc):
        components=self.closure()
        if isinstance(exc,Halt):failure=dict(phase=self.phase,exception_kind='OTHER',sqlstate=None,reason_code=exc.code,classification_source='FIXED_CLEANUP_CODE',message_exported=False,underlying_cause='UNDETERMINED')
        else:
            try:failure=safe_failure(exc,'EXECUTION')
            except BaseException:failure=dict(phase=self.phase,exception_kind='OTHER',sqlstate=None,reason_code='UNKNOWN',classification_source='NONE',message_exported=False,underlying_cause='UNDETERMINED')
        result=dict(status='STOP_RECONCILE_NO_RETRY',failure=failure,**self.common(components))
        try:self.emit('stopped',dict(result))
        except BaseException:result['audit_stop_record']='UNCERTAIN'
        return result


def prepare_cleanup(r,raw,started,*,journal,memory,progress,baseline,dns_run=subprocess.run,dns_command=None,connect_factory=None,github_runner=subprocess.run):
    prepared=prepare_connection(r,raw,progress=progress,dns_run=dns_run,dns_command=dns_command);connect=prepared.connect
    if connect_factory is not None:                                  # TEST-ONLY seam; main() never passes it
        def connect():
            progress.database_connection_calls+=1;return connect_factory()
    with progress.stage('RUNNER_CONSTRUCTION'):
        try:return Cleanup(journal,connect,progress,memory,target=r['target'],github_runner=github_runner,baseline=baseline,started=started)
        except (KeyError,TypeError,ValueError,AttributeError):raise PreparationFailure('RUNNER_CONSTRUCTION','RUNNER_CONSTRUCTION_FAILED') from None


def verify_predecessor(r,state_root):
    """The matrix audit this cleanup answers: exact hashes plus the recorded unreconciled outcome naming the target session. Read-only."""
    p=r['predecessor'];directory=Path(state_root)/p['state_directory']
    if directory.is_symlink() or not directory.is_dir() or directory.resolve().parent!=Path(state_root).resolve():raise ValueError('PREDECESSOR_EVIDENCE')
    contents={}
    for name,key in (('events.jsonl','events_sha256'),('final-result.json','final_result_sha256')):
        path=directory/name
        if path.is_symlink() or not path.is_file():raise ValueError('PREDECESSOR_EVIDENCE')
        contents[name]=path.read_bytes()
        if hashlib.sha256(contents[name]).hexdigest()!=p[key]:raise ValueError('PREDECESSOR_EVIDENCE')
    recorded=json.loads(contents['final-result.json']);target=r['target']
    sessions=recorded.get('diagnostics',{}).get('sessions',[])
    if (recorded.get('status')!='STOP_RECONCILE_NO_RETRY' or recorded.get('access')!='UNRECONCILED' or recorded.get('cleanup')!='UNCERTAIN'
        or not any(s[0]==target['pid'] and s[1]==target['role'] for s in sessions) or len(sessions)!=1):raise ValueError('PREDECESSOR_OUTCOME')
    return dict(final_result_sha256=p['final_result_sha256'],recorded_sessions=len(sessions))


def validate_cleanup_registration(body,sha):
    if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('REGISTRATION_SHA256')
    r=json.loads(body)
    if not isinstance(r,dict) or set(r)!=REGISTRATION_KEYS:raise ValueError('REGISTRATION_EXACT_KEYS')
    if r['mode']!=MODE or r['authority']!=AUTHORITY or r['status']!=STATUS or r['state_directory']!=STATE or r['evidence_directory']!=EVIDENCE_DIRECTORY:raise ValueError('EXACT_CLEANUP_APPROVAL_REQUIRED')
    if (r['limits']!=LIMITS or r['absent_capabilities']!=list(ABSENT_CAPABILITIES) or r['statements_sha256']!=statements_digest() or r['secrets']!=list(SECRETS) or r['preserved_secret']!=PRESERVED):raise ValueError('CLEANUP_LIMITS_OR_BOUNDARY_BINDING')
    t=r['target']
    if not isinstance(t,dict) or set(t)!=TARGET_KEYS or type(t['pid']) is not int or t['pid']<=0 or t['role']!='ingestion_worker_login':raise ValueError('TARGET_BINDING')
    p=r['predecessor']
    if not isinstance(p,dict) or set(p)!=PREDECESSOR_KEYS or p['state_directory']!=MATRIX_STATE or not all(isinstance(p[k],str) and len(p[k])==64 for k in ('events_sha256','final_result_sha256')):raise ValueError('PREDECESSOR_BINDING')
    expiry=datetime.fromisoformat(r['expires_at']);now=datetime.now(timezone.utc)
    if expiry.tzinfo is None or not now<expiry<=now+timedelta(hours=2):raise ValueError('CLEANUP_EXPIRY')
    manifest=json.loads((Path(EVIDENCE_DIRECTORY)/'MANIFEST.json').read_text())
    if not isinstance(r['hashes'],dict) or set(r['hashes'])!=set(manifest['bound_paths']):raise ValueError('HASHES_MUST_EQUAL_MANIFEST')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if revision!=r['revision'] or subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip()!=r['tree'] or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('CLEAN_REVIEWED_CHECKOUT')
    for path,digest_ in r['hashes'].items():
        f=Path(path)
        if f.is_symlink() or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=digest_:raise ValueError('REVIEWED_CONTENT_BINDING')
    if r['controller_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest() or r['ca_sha256']!=PEM_SHA256:raise ValueError('CONTROLLER_CA_BINDING')
    return r


def hidden_input():
    import getpass,warnings
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        return getpass.getpass('Existing migration credential URL (hidden; never paste into chat): ')


def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',type=Path,required=True);p.add_argument('--registration-sha256',required=True);a=p.parse_args()
    if sys.platform!='linux' or not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('OWNER_LINUX_SECURE_TTY_REQUIRED')
    if any(k.startswith('PG') for k in os.environ):raise SystemExit('LIBPQ_ENVIRONMENT_OVERRIDE')
    if any(os.environ.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_DEBUG')):raise SystemExit('EXISTING_KEYRING_AUTH_ONLY')
    if os.environ.get('GH_HOST','github.com')!='github.com' or any(os.environ.get(k) for k in ('GH_CONFIG_DIR','GH_HTTP_UNIX_SOCKET','SSL_CERT_FILE','SSL_CERT_DIR','HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy','ALL_PROXY','all_proxy')):raise SystemExit('UNREVIEWED_GITHUB_ROUTE_OR_TRUST_OVERRIDE')
    if a.registration.is_symlink() or a.registration.stat().st_size>16384:raise SystemExit('REGISTRATION_BOUND')
    r=validate_cleanup_registration(a.registration.read_bytes(),a.registration_sha256)
    state=Path.home()/'.local/state/propertyaigent'
    verify_predecessor(r,state)
    from .operational_memory import OperationalMemory
    memory=OperationalMemory()
    state.mkdir(mode=0o700,exist_ok=True,parents=True)
    journal=Journal(state/r['state_directory'])
    journal.emit('consumed',dict(authority=r['authority'],registration_sha256=a.registration_sha256))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    progress=Progress();baseline=owned_resources()
    prepare=lambda raw,started:prepare_cleanup(r,raw,started,journal=journal,memory=memory,progress=progress,baseline=baseline)
    result=session(journal,r['expires_at'],hidden_input,prepare,memory=memory,timing=TIMING,progress=progress,baseline=baseline)
    raise SystemExit(0 if result.get('status')=='RESTRICTED_MATRIX_CLEANUP_VERIFIED' and result.get('cleanup')=='CLOSED' else 1)


if __name__=='__main__':main()
