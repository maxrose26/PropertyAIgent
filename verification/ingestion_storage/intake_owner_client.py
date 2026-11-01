"""Owner terminal client. INACTIVE. Existing bounded capture, anonymous secret pipe.

No child/reconnect/retry other than exactly one selected phase process.
"""
import argparse,getpass,hashlib,json,os,selectors,shutil,signal,subprocess,sys,time,warnings
from pathlib import Path
LIMIT=65536
MODULE='verification.ingestion_storage.intake_owner_client'

def capture(command, environment, *, seconds=60, ceiling=LIMIT, pass_fds=()):
    """One process, combined pipe, finite bytes; TERM at deadline-2, KILL at -1."""
    start = time.monotonic()
    p = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True, pass_fds=pass_fds)
    data = bytearray()
    reason = None
    term = None
    eof = False
    try:
        with selectors.DefaultSelector() as poll:
            poll.register(p.stdout, selectors.EVENT_READ)
            while not eof or p.poll() is None:
                now = time.monotonic()
                if reason is None and now-start >= seconds-2:
                    reason = 'DEADLINE'
                if reason and term is None:
                    term = now
                    try: os.killpg(p.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                if term is not None and now-term >= 1:
                    try: os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                if now-start >= seconds-.2:
                    reason = reason or 'CLOSURE_UNCERTAIN'
                    break
                for key, _ in poll.select(.025):
                    chunk = os.read(key.fd, 4096)
                    if not chunk:
                        poll.unregister(key.fileobj)
                        eof = True
                    else:
                        remaining = ceiling-len(data)
                        data.extend(chunk[:remaining])
                        if len(chunk)>remaining: reason = 'OUTPUT_OVERFLOW'
        p.stdout.close()
        if p.poll() is None:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        try: code = p.wait(timeout=.1)
        except subprocess.TimeoutExpired: code = None
    finally:
        # Also reap on local exceptions/cancellation. This is not remote proof.
        if p.poll() is None:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            try: p.wait(timeout=.1)
            except subprocess.TimeoutExpired: pass
        p.stdout.close()
    return bytes(data), dict(exit_code=code, reason=reason,
        client_closed=code is not None, output_bytes=len(data),
        remote_closure='NOT_ACKNOWLEDGED' if reason or code else 'NORMAL_PSQL_EXIT',
        classification='INCOMPLETE' if reason or code else 'OBSERVATIONS_REQUIRE_REVIEW')


PHASES = ('activate', 'qualify', 'close', 'stop-disposition', 'readback', 'handoff',
          'handoff-reconcile', 'handoff-restore', 'publication-close', 'inspect',
          'period', 'publication-arm', 'publication-revoke')


# Fixed reviewed failure identifiers. Never format an exception, inspect its cause,
# DSN, environment or arbitrary driver message. New/unrecognised failures stay unknown.
FAILURE_REASONS = frozenset("""
PERIOD_EXACT_TEMPORARY_ISSUER PERIOD_COMMIT_ACK_UNCERTAIN TOKEN_REVOKE_ACK_UNCERTAIN OPERATION_VAULT_BINDING PERIOD_EXACT_POLICY PERIOD_POLICY_HASH PERIOD_SINGLE_RUN PERIOD_REVIEWED_BINDINGS PERIOD_ROUTE_EXPIRY PERIOD_PROFILE PERIOD_PRIVILEGE_RESTORATION PERIOD_LEDGER_POSTCONDITION PERIOD_COMMITTED_READBACK PERIOD_EXISTING_ISSUER_ADMIN_ONLY PERIOD_STOP_CHANGED PERIOD_ALREADY_EXISTS_NO_RETRY PERIOD_SERVER_EXPIRY PERIOD_REGISTRATION_READBACK PERIOD_JOURNAL_BINDING INSTALLATION_TOKEN_ONLY TOKEN_REVIEWED_SCOPE_REQUIRED TOKEN_PRIOR_INTENT_RECONCILE_NO_RETRY TOKEN_PRIVATE_BINDING INDEPENDENT_PUBLICATION_REVOKE_REQUIRED
ACCEPTED_STORAGE_ACCESS_CHANGED
ACCESS_DISABLED_BUT_MEMBERSHIP_RECONCILIATION_REQUIRED
ACCESS_DISABLE_READBACK
ACTIVATION_COMMITTED_READBACK
ACTIVATION_GATE_DERIVATION
ACTIVATION_LEDGER_CHANGED
ACTIVATION_MEMBERSHIP_POSTCONDITION
ACTIVATION_SETTINGS_POSTCONDITION
ACTIVATION_STOP_CHANGED
ADMIN_COMMAND_BOUND
ADMIN_CONNECTION_BOUND
ARGUMENTS_REFUSED
AUTH_PROBE
BINDING_NOT_EXECUTABLE_REVIEW_REQUIRED
BINDING_FILE_REFUSED
BINDING_HASH_REFUSED
BOTH_EXPLICIT_STOP_DECISIONS_REQUIRED
CLOSURE_AUTHORITY_BINDING
CLOSURE_AUTHORITY_BOUND
CLOSURE_AUTHORITY_READBACK
CLOSURE_CONTROL_POSTCONDITION
CLOSURE_RUN_BINDING
CLOSURE_SETTINGS_DRIFT
CLOSURE_SETTINGS_POSTCONDITION
CLOSURE_STATE
CLOSURE_UNRELATED_MEMBERSHIP_DRIFT
COMPLETE_JOB_INVENTORY_REQUIRED
CONNECTION_BOUND
CONTROL_SHAPE
DATABASE_BYTE_CEILING
DATABASE_CLOSURE_FIRST
DATABASE_RETURNED_VALUE_BOUND
DRIVER_STATEMENT_BOUND
EXACT_EMPTY_OPERATIONAL_MAPPINGS_REQUIRED
EXACT_GENERATION5_STOP_REQUIRED
EXACT_RENDER_PROFILE_FIELDS_AND_LIMITS
EXACT_RESTRICTED_ROUTE_AND_ROLE
EXACT_REVIEWED_APPLICATION_REQUIRED
EXACT_STORAGE_STOP_STATE
EXISTING_PASSWORD_BOOLEAN_READ_UNAVAILABLE
EXISTING_PIPELINE_SESSION
EXISTING_RUNTIME_ADMIN_CAPABILITIES_REQUIRED
EXPLICIT_PHASE_APPROVAL_REQUIRED
FINITE_OWNER_VALIDITY
HIDDEN_OWNER_TTY_REQUIRED
FINITE_SELF_REVOCABLE_PUBLICATION_TOKEN
GITHUB_REQUEST_BOUND
HANDOFF_CREDENTIAL_WINDOW
HANDOFF_RECONCILIATION_REQUIRED
HANDOFF_SINGLE_USE
INDEPENDENT_ARCHIVE_OR_ZERO
INDEPENDENT_AUTHORITY_CLOSURE
INDEPENDENT_BOTH_CAPTURE_AUTHORITIES
INDEPENDENT_CAPTURE
INDEPENDENT_COUNCILS
INDEPENDENT_FINALISATION_BINDING
INDEPENDENT_PUBLICATION_BINDING
INDEPENDENT_SCREENING_BATCHES
INDIRECT_RUNTIME_CAPABILITY
INSTALLATION_ALREADY_EXISTS_NO_REPLAY
INTAKE_FUNCTION_INVENTORY
INTAKE_OWNER_CAPABILITY_ACL
INTAKE_OWNER_FUNCTION_INVENTORY
JOB_EXISTS_REQUIRES_NAMED_TERMINAL_READBACK
LIBPQ_ENVIRONMENT_OVERRIDE
MIGRATION_IDENTITY
MIGRATION_OWNERSHIP_OR_GRANT_OPTIONS
OLDHAM_HISTORICAL_BINDING_CHANGED
OLDHAM_HISTORICAL_ROOT_CHANGED
OLDHAM_RETAINED_BINDINGS_HASH
OLDHAM_REVOKED_STATE_CHANGED
OWNED_FD_BOUND
OWNED_PROCESS_IDENTITY_CHANGED
OWNED_THREAD_BOUND
OWNER_ADMIN_IPV4
OWNER_ADMIN_ONLY_BASELINE
OWNER_BINDING
OWNER_CODE_BINDING
OWNER_IDENTITY
OWNER_IPV4
OWNER_PERIOD
OWNER_ROUTE
OWNER_SESSION_VISIBILITY
OWNER_STOP_BINDING
PASSWORD_ENTROPY_BOUND
PHASE_REFUSED
PINNED_REVIEWED_ADDRESS_REQUIRED
PREEXISTING_RUNTIME_SESSIONS
PRIVATE_VAULT_REQUIRED
PUBLICATION_BYTES
PUBLICATION_CLOSE_STATE_OR_PRIOR_UNCERTAINTY
QUALIFICATION_CLOSURE_UNCERTAIN
QUALIFICATION_FINITE_WINDOW
READBACK_EXPORT_BOUND
READBACK_RUN_ID
READ_ITEMS_BOUND
RECOVERED_ATTEMPT_CHANGED
RECOVERED_ATTEMPT_MISSING
RECOVERED_ROOT_CHANGED
REGISTRAR_NARROW_ACL
RENDER_BOUND_INTEGER_PROFILE
RENDER_COMMAND_SCHEDULE
RENDER_COMPLETE_ENV_PAGE_REQUIRED
RENDER_ENV_SHAPE
RENDER_FINITE_BOUND
RENDER_FIXED_OPERATION
RENDER_HANDOFF_READBACK
RENDER_JOB_NOT_TERMINAL
RENDER_PROFILE_MAPPING_REQUIRED
RENDER_RESPONSE_BOUND
RENDER_RESPONSE_UNCERTAIN
RENDER_RESPONSE_UNCERTAIN_NO_RETRY
RENDER_RESTORE_DRIFT
RENDER_RESTORE_READBACK
RENDER_REVIEWED_CONFIGURATION
RENDER_SAFETY_CONTROLS
RESTRICTED_ROUTE_MISMATCH
RESULT_BOUND
REUSED_RUNTIME_FLAGS_CHANGED
REUSED_RUNTIME_MEMBERSHIPS_CHANGED
REVIEWED_CA_DER_MISMATCH
REVIEWED_CA_HASH_MISMATCH
REVIEWED_CA_MISSING
REVIEWED_CA_NOT_SIGNING_CA
REVIEWED_CA_VALIDITY_REVIEW_REQUIRED
REVIEWED_CONNECTION_CONFIGURATION_REQUIRED
REVIEWED_FUNCTION_INVENTORY
REVIEWED_INHERITED_BOUNDARY_REQUIRED
REVIEWED_TLS_ENDPOINT_REQUIRED
ROLE_DATABASE_SPECIFIC_SETTINGS_PRESENT
ROLE_SETTINGS_ROLES_MISSING
ROLE_SETTINGS_SCOPE
ROLE_SETTINGS_VALUE
ROLE_SETTING_PRIOR_VALUE_UNSUPPORTED
RUNTIME_MEMBERSHIP_PRESENT
RUNTIME_NOT_DORMANT
SELF_REVOCABLE_INSTALLATION_TOKEN_REQUIRED
SECRET_FORMAT_REFUSED
SECRET_PIPE_BOUND
SERVER_FINITE_VALIDITY
SERVER_TIMEOUT_OR_RESTRICTED_IDENTITY_PROFILE
SESSIONS_UNRESOLVED
STATEMENT_HARD_DEADLINE
STOP_COMMITTED_READBACK
STOP_POSTCONDITION
STOP_PRIVILEGE_CLEANUP
STORAGE_MEMBERSHIP_CHANGED
TEMPORARY_OWNER_CAPABILITY_REMAINS
TERMINAL_JOB_ID_REQUIRED
UNEXPIRED_OR_UNREADABLE_AUTHORITY
UNFINISHED_INTAKE_RUN
UNKNOWN_PHASE
UNRESOLVED_EFFECT_INTENT
VAULT_32K_BOUND
VAULT_BINDING_CHANGED
VAULT_CONFIRMATION_REFUSED
VAULT_INCOMPLETE
VAULT_PASSPHRASE_LENGTH
""".split())
DIAGNOSTIC_BYTES = 1024


def failure_record(phase, exc):
    from app.ingestion.ledger import Denied
    reason = 'UNKNOWN_FAILURE'
    # Exact exception types prevent unknown subclasses/objects from furnishing
    # arbitrary printable fields. Only exact single literal identifiers survive.
    if type(exc) in (Denied, ValueError, RuntimeError, SystemExit):
        args = exc.args
        if len(args) == 1 and type(args[0]) is str and args[0] in FAILURE_REASONS:
            reason = args[0]
    return dict(status='STOP_PHASE_REQUIRES_REVIEW_NO_RETRY',
                phase=phase if type(phase) is str and phase in PHASES else 'UNKNOWN_PHASE',
                failure_reason=reason, retry=False,
                transaction_outcome='NOT_INFERRED_RECONCILE_NO_RETRY')


def failure_output(phase, exc):
    # All values are fixed enums/boolean; lengths cannot depend on exception size.
    raw = json.dumps(failure_record(phase, exc), sort_keys=True)
    assert len(raw.encode()) + 1 <= DIAGNOSTIC_BYTES
    return raw


def hidden(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        value = getpass.getpass(prompt)
    if not value or any(x in value for x in '\r\n\0'):
        raise SystemExit('SECRET_FORMAT_REFUSED')
    return value


def loaded(path, expected):
    p=Path(path).expanduser()
    if p.is_symlink() or not p.is_file() or p.stat().st_size>32768:
        raise SystemExit('BINDING_FILE_REFUSED')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:
        raise SystemExit('BINDING_HASH_REFUSED')
    return json.loads(raw)


def worker(phase, binding, secrets_input, vault_path, expected):
    from . import intake_owner as op
    from .intake_owner_io import Vault, Render, handoff, reconcile_handoff, restore_handoff
    from .tls_trust import verified_trust
    op.validate_binding(binding, opening=phase=='activate')
    save=lambda _:None;state=None
    from . import intake_owner_operations as extra
    if phase in ('period','publication-arm','publication-revoke'):
        key='period_vault_path' if phase=='period' else 'publication_vault_path'
        extra.private_path(binding,key,vault_path)
        vault=Vault(vault_path,secrets_input['vault_key'],create=phase in ('period','publication-arm'))
        save=vault.save
        if phase=='publication-arm':return extra.token_arm(binding,secrets_input['publication_token'],save)
        if phase=='publication-revoke':return extra.token_revoke(binding,vault.load(),save)
        extra.validate_policy(binding,expected)
        state=dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=binding,policy=expected)
        save(state)
    if phase=='publication-close' and binding.get('publication_vault_path'):
        op.require(False,'INDEPENDENT_PUBLICATION_REVOKE_REQUIRED')
    if phase in ('activate','qualify','close','handoff','handoff-reconcile','handoff-restore','publication-close','inspect'):
        vault=Vault(vault_path,secrets_input['vault_key'],create=phase=='activate')
        save=vault.save
        if phase!='activate':
            state=vault.load()
            op.require(state['binding']==binding,'VAULT_BINDING_CHANGED')
    if phase=='inspect':
        r=state.get('render',{})
        return dict(status='LOCAL_ENCRYPTED_STATE_INSPECTION',period=binding['period'],
                    state=state.get('state'),membership_closure=state.get('membership_closure'),
                    render_state=r.get('state'),publication_state=r.get('publication_state'),
                    production_connections=0,source_requests=0,provider_calls=0)
    if phase.startswith('handoff'):
        api=Render(secrets_input['render_token'])
        try:
            if phase=='handoff':
                token=secrets_input.get('publication_token')
                if binding.get('publication_vault_path'):
                    extra.private_path(binding,'publication_vault_path',binding['publication_vault_path'])
                    token=extra.token_load(binding,Vault(binding['publication_vault_path'],secrets_input['vault_key']).load())
                return handoff(api,state,save,token)
            if phase=='handoff-reconcile':return reconcile_handoff(api,state,save)
            return restore_handoff(api,state,save,expected.get('job_id'))
        finally:api.session.close()
    if phase=='publication-close':
        # Existing bounded GitHub publisher transport, with only the exact token
        # inherited by its owner-local gh child. Installation tokens self-revoke.
        from .operational_publication import GitHub
        token=state['render']['publication_token']
        op.require(extra.installation_token_allowed(token),'SELF_REVOCABLE_INSTALLATION_TOKEN_REQUIRED')
        op.require(state.get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED' and
                   state['render'].get('state')=='RESTORATION_ACKNOWLEDGED' and
                   state['render'].get('publication_state')=='ACTIVE','PUBLICATION_CLOSE_STATE_OR_PRIOR_UNCERTAINTY')
        state['render']['publication_state']='REVOKE_INTENT_NO_RETRY';save(state)
        def runner(command,**kw):
            return subprocess.run(command,env={'PATH':'/usr/bin:/bin','HOME':str(Path.home()),
                'GH_TOKEN':token,'GH_PROMPT_DISABLED':'1'},**kw)
        GitHub(lambda *_:None,lambda:None,runner=runner,bound=1).call('DELETE','installation/token')
        state['render']['publication_state']='REVOKED_ACKNOWLEDGED';state['render']['publication_token']='';save(state)
        return dict(status='PUBLICATION_TOKEN_REVOCATION_ACKNOWLEDGED',calls=1)
    ca,_=verified_trust()
    if phase=='qualify':
        op.require(time.time()+60<binding['valid_until'],'QUALIFICATION_FINITE_WINDOW')
        from .restricted_route import url
        from .operational_controller import DatabaseBudget
        out=[]
        for role in op.ROLES:
            budget=DatabaseBudget(seconds=25,statements=20,connections=1,returned_bytes=2048)
            try:
                e=budget.engine(url(binding['route'],role,state['passwords'][role]),
                    ssl={'sslmode':'verify-full','sslrootcert':str(ca)},hostaddr=binding['hostaddr'],route=binding['route'])
                from sqlalchemy import text
                with e.connect() as c:
                    c.execute(text('BEGIN READ ONLY'));op.require(c.execute(text('SELECT 1')).scalar_one()==1,'AUTH_PROBE');c.rollback()
            finally:budget.close([])
            op.require(all(c.closed for c in budget.opened) and budget.failed_native_closed,'QUALIFICATION_CLOSURE_UNCERTAIN')
            out.append(dict(role=role,attempts=budget.attempts,closed=True))
        return dict(status='TWO_SINGLE_ATTEMPT_RESTRICTED_AUTHENTICATIONS_CLOSED',roles=out,retry=False)
    import psycopg
    with psycopg.connect(host='aws-0-eu-west-2.pooler.supabase.com',hostaddr=binding['owner_hostaddr'],
        port=5432,dbname='postgres',user='postgres.zcikcfgpblzuzpanpdqd',password=secrets_input['owner_password'],
        sslmode='verify-full',sslrootcert=str(ca),gssencmode='disable',connect_timeout=5,prepare_threshold=None,
        autocommit=True,options='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000') as c:
        if phase=='period':return extra.issue_period(c,binding,expected,state,save)
        if phase=='activate':return op.activate(c,binding,save)
        if phase=='close':return op.close(c,state,save)
        if phase=='stop-disposition':return op.stop_disposition(c,binding.get('stop_decisions',[]))
        if phase=='readback':return op.finalisation(c,binding,expected)
    raise SystemExit('UNKNOWN_PHASE')


def _main(argv, context):
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('--child',action='store_true');p.add_argument('--secrets-fd',type=int)
    p.add_argument('--phase',choices=PHASES);p.add_argument('--binding');p.add_argument('--binding-sha256')
    p.add_argument('--vault');p.add_argument('--expected');p.add_argument('--expected-sha256')
    def argument_error(_):
        raise SystemExit('ARGUMENTS_REFUSED')
    p.error=argument_error
    a=p.parse_args(argv)
    context[0]=a.phase
    if a.child:
        try:
            secret=json.loads(os.read(a.secrets_fd,4096));os.close(a.secrets_fd)
            b=loaded(a.binding,a.binding_sha256)
            expected=loaded(a.expected,a.expected_sha256) if a.expected else {}
            result=worker(a.phase,b,secret,a.vault,expected)
            raw=json.dumps(result,sort_keys=True).encode()
            if len(raw)>30000:raise ValueError('RESULT_BOUND')
            print(raw.decode());return 0
        except BaseException as exc:
            print(failure_output(a.phase, exc));return 2
    if not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('HIDDEN_OWNER_TTY_REQUIRED')
    phase=a.phase or input('Approved phase: ').strip()
    context[0]=phase
    if phase not in PHASES:raise SystemExit('PHASE_REFUSED')
    path=str(Path(a.binding or input('Reviewed binding file: ').strip()).expanduser().resolve())
    h=a.binding_sha256 or input('Reviewed binding SHA-256: ').strip()
    b=loaded(path,h)
    try:
        from .intake_owner import validate_binding
        validate_binding(b,opening=phase=='activate')
    except BaseException as exc:
        print(failure_output(phase, exc));return 2
    if phase!='inspect' and input('Approval phrase (EXECUTE_EXACT_'+phase.upper().replace('-','_')+'_ONCE): ').strip()!= 'EXECUTE_EXACT_'+phase.upper().replace('-','_')+'_ONCE':
        raise SystemExit('EXPLICIT_PHASE_APPROVAL_REQUIRED')
    output=Path(input('NEW private phase evidence directory: ').strip()).expanduser();output.mkdir(mode=0o700)
    vault=a.vault
    if phase in ('activate','qualify','close','handoff','handoff-reconcile','handoff-restore','publication-close','inspect','period','publication-arm','publication-revoke'):
        vault=str(Path(vault or input('Owner-local encrypted vault path (NEW for activate): ').strip()).expanduser().resolve())
    expected=a.expected;eh=a.expected_sha256
    if phase in ('readback','handoff-restore','period'):
        expected=str(Path(expected or input('Reviewed nonsecret expected receipt file: ').strip()).expanduser().resolve())
        eh=eh or input('Expected receipt SHA-256: ').strip();loaded(expected,eh)
    if phase=='period':
        from .intake_owner_operations import validate_policy,private_path
        validate_policy(b,loaded(expected,eh));private_path(b,'period_vault_path',vault)
    secret={}
    if phase in ('activate','close','stop-disposition','readback','period'):secret['owner_password']=hidden('Existing owner password (hidden): ')
    if vault:
        secret['vault_key']=hidden('Vault passphrase, at least 24 characters (hidden): ')
        if phase in ('activate','period','publication-arm') and hidden('Confirm vault passphrase (hidden): ')!=secret['vault_key']:
            raise SystemExit('VAULT_CONFIRMATION_REFUSED')
    if phase.startswith('handoff'):secret['render_token']=hidden('Existing owner-local Render token (hidden): ')
    if phase=='publication-arm' or (phase=='handoff' and not b.get('publication_vault_path')):
        secret['publication_token']=hidden('Reviewed short-lived GitHub installation token (hidden): ')
        from .intake_owner_operations import installation_token_allowed
        if not installation_token_allowed(secret['publication_token']):raise SystemExit('INSTALLATION_TOKEN_ONLY')
    raw=json.dumps(secret).encode()
    if len(raw)>4000:raise SystemExit('SECRET_PIPE_BOUND')
    readfd,writefd=os.pipe()
    try:
        os.write(writefd,raw);os.close(writefd)
        command=[sys.executable,'-B','-m',MODULE,'--child','--secrets-fd',str(readfd),'--phase',phase,
                 '--binding',path,'--binding-sha256',h]
        if vault:command+=['--vault',vault]
        if expected:command+=['--expected',expected,'--expected-sha256',eh]
        data,status=capture(command,{'PATH':'/usr/bin:/bin','HOME':str(Path.home()),'LANG':'C.UTF-8',
            'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1'},ceiling=30720,pass_fds=(readfd,))
    finally:os.close(readfd)
    status.update(phase=phase,connection_policy='NO_RECONNECT_NO_RETRY',
        transaction_outcome='RECONCILE' if status['reason'] or status['exit_code'] else 'ACKNOWLEDGED_SEE_RESULT',
        remote_closure='UNKNOWN_AFTER_FORCED_EXIT' if status['reason'] or status['exit_code'] else 'NORMAL_PHASE_EXIT_SEE_RESULT')
    (output/'output.txt').write_bytes(data);(output/'status.json').write_text(json.dumps(status,sort_keys=True)+'\n')
    print('PHASE_REQUIRES_LOCAL_EVIDENCE_REVIEW' if not status['reason'] and status['exit_code']==0 else 'STOP_RECONCILE_NO_RETRY')
    return 0 if status['exit_code']==0 and not status['reason'] else 2


def main(argv=None):
    context=[None]
    try:
        return _main(argv, context)
    except BaseException as exc:
        if type(exc) is SystemExit and exc.code == 0:
            return 0
        print(failure_output(context[0], exc))
        return 2


if __name__=='__main__':raise SystemExit(main())

