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
          'period', 'publication-arm', 'publication-revoke', 'submission-check')


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
MINT_RECEIPT_BINDING
MINT_B_AND_CLOSURE_WINDOW
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


FAILURE_REASONS=FAILURE_REASONS | frozenset(('FINITE_TIMING_POLICY','FINITE_FIXED_DEADLINE','SETUP_TEN_MINUTE_BOUND','PERIOD_FIXED_DEADLINE','OPERATION_OBSERVATION_BINDING','OPERATION_OBSERVATION_STALE','OPERATION_OBSERVATION_DRIFT','SUBMISSION_HANDOFF_REQUIRED','SUBMISSION_PRIOR_INTENT_NO_RETRY','SUBMISSION_CURRENT_STATE_DRIFT','SUBMISSION_INTENT_PATH','TIMING_RELEASE_UNBOUND','ATTENDED_TIMER_CONFLICT'))

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


# Fixed local-only input feedback; never include an input or exception value.
LOCAL_INPUT_MESSAGES = {
    'FORMAT': 'LOCAL_INPUT_FORMAT: use bounded text without CR, LF or NUL (maximum 1024 JSON-encoded bytes for passwords).',
    'LENGTH': 'LOCAL_VAULT_LENGTH: use at least 24 characters.',
    'CONFIRM': 'LOCAL_CONFIRMATION_MISMATCH: enter and confirm again.',
    'UNLOCK': 'LOCAL_VAULT_UNLOCK_REFUSED: check the existing Vault passphrase; no provider request.',
    'TOKEN': 'LOCAL_INSTALLATION_TOKEN_FORMAT_REFUSED: use only the reviewed bounded installation token.',
    'KEY': 'LOCAL_KEY_UNLOCK_REFUSED: check PropertyAIgent — GitHub signing-key passphrase; no provider request.',
}


def private_input(prompt, *, minimum=1, maximum=1024, confirm=False, validator=None, unlock_code='UNLOCK'):
    """Correct local input in this parent, before child/operation reservation.

    Validator returns a boolean for recognised local decryption refusal only;
    unexpected errors propagate to the fixed outer failure reporter. No retry of
    child, network, mutation or unknown error is performed here.
    """
    while True:
        try:
            value=hidden(prompt)
        except SystemExit as exc:
            if exc.code != 'SECRET_FORMAT_REFUSED': raise
            print(LOCAL_INPUT_MESSAGES['FORMAT'],file=sys.stderr); continue
        if type(value) is not str or not value or len(json.dumps(value).encode())-2>maximum or any(c in value for c in '\r\n\0'):
            print(LOCAL_INPUT_MESSAGES['FORMAT'],file=sys.stderr); continue
        if len(value)<minimum:
            print(LOCAL_INPUT_MESSAGES['LENGTH'],file=sys.stderr); continue
        if confirm:
            try: other=hidden('Confirm B-state Vault passphrase (hidden): ')
            except SystemExit as exc:
                if exc.code != 'SECRET_FORMAT_REFUSED': raise
                print(LOCAL_INPUT_MESSAGES['CONFIRM'],file=sys.stderr); continue
            if other!=value:
                print(LOCAL_INPUT_MESSAGES['CONFIRM'],file=sys.stderr); continue
        if validator is not None and not validator(value):
            print(LOCAL_INPUT_MESSAGES[unlock_code],file=sys.stderr); continue
        return value


def vault_unlock(path, password):
    from cryptography.fernet import InvalidToken
    from .intake_owner_io import Vault
    try: Vault(path,password).load()
    except InvalidToken: return False
    return True


def vault_input(path, *, create=False, mint_bound=False):
    # Authenticate the common passphrase against the existing mint Vault for
    # new access/period vaults. No additional persistence or confirmation needed.
    from . import publication_mint as mint
    authentication_path=mint.ROOT/'mint-01.vault' if mint_bound and create else path
    validate=None if create and not mint_bound else lambda password: vault_unlock(authentication_path,password)
    print('Retrieve the B-state Vault passphrase. This is distinct from the PREBUILD baseline and signing-key passphrases.',file=sys.stderr)
    return private_input('B-state Vault passphrase (hidden, >=24 characters): ',minimum=24,
                         confirm=create and not mint_bound,validator=validate)


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
    op.validate_binding(binding, opening=phase=='activate' or ('timing_policy' in binding and phase in ('period','qualify','handoff','submission-check')))
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
    if phase in ('activate','qualify','close','handoff','handoff-reconcile','handoff-restore','publication-close','inspect','submission-check'):
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
    if phase.startswith('handoff') or phase=='submission-check':
        api=Render(secrets_input['render_token'])
        try:
            if phase=='submission-check':
                from .intake_owner_io import submission_check
                return submission_check(api,state,save,expected)
            if phase=='handoff':
                token=secrets_input.get('publication_token')
                if binding.get('publication_vault_path'):
                    extra.private_path(binding,'publication_vault_path',binding['publication_vault_path'])
                    token=extra.token_load(binding,Vault(binding['publication_vault_path'],secrets_input['vault_key']).load())
                return handoff(api,state,save,token,observation=expected)
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
    p.add_argument('--vault');p.add_argument('--expected');p.add_argument('--expected-sha256');p.add_argument('--evidence');p.add_argument('--launch',action='store_true');p.add_argument('--session',action='store_true');p.add_argument('--timing-v2',action='store_true')
    def argument_error(_):
        raise SystemExit('ARGUMENTS_REFUSED')
    p.error=argument_error
    a=p.parse_args(argv)
    context[0]=a.phase
    if a.launch:
        if a.child:raise SystemExit('ARGUMENTS_REFUSED')
        if not a.session and a.phase in ('period','activate','qualify','handoff','submission-check'):
            from . import finite_release_binding as flow
            import shlex
            try:flow.use_timing_release()
            except flow.PreparationError as exc:raise SystemExit(exc.code) from None
            phase,command=flow.next_command(expect=a.phase)
            raw=list(sys.argv[1:] if argv is None else argv)
            if raw.count('--launch')!=1 or [x for x in raw if x!='--launch']!=shlex.split(command)[2:]:raise SystemExit('ARGUMENTS_REFUSED')
        elif not a.session and a.phase not in ('close','publication-revoke','handoff-reconcile','handoff-restore','inspect','readback'):raise SystemExit('PHASE_REFUSED')
    if a.session:
        if a.child or a.phase or a.binding or a.vault or a.expected or a.evidence:raise SystemExit('ARGUMENTS_REFUSED')
        from .finite_release_binding import use_timing_release
        try:use_timing_release()
        except BaseException as exc:
            if getattr(exc,'code',None)=='TIMING_RELEASE_UNBOUND':raise SystemExit('TIMING_RELEASE_UNBOUND') from None
            raise
        return attended_session()
    if a.timing_v2 and a.phase in ('period','activate','qualify','handoff','submission-check') and not a.child:
        from .finite_release_binding import use_timing_release
        use_timing_release()
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
        validate_binding(b,opening=phase=='activate' or ('timing_policy' in b and phase in ('period','qualify','handoff','submission-check')))
    except BaseException as exc:
        print(failure_output(phase, exc));return 2
    if phase!='inspect' and input('Approval phrase (EXECUTE_EXACT_'+phase.upper().replace('-','_')+'_ONCE): ').strip()!= 'EXECUTE_EXACT_'+phase.upper().replace('-','_')+'_ONCE':
        raise SystemExit('EXPLICIT_PHASE_APPROVAL_REQUIRED')
    output=Path(a.evidence or input('NEW private phase evidence directory: ').strip()).expanduser()
    if output.exists() or output.is_symlink():raise SystemExit('PRIVATE_VAULT_REQUIRED')
    vault=a.vault
    if phase in ('activate','qualify','close','handoff','handoff-reconcile','handoff-restore','publication-close','inspect','period','publication-arm','publication-revoke','submission-check'):
        vault=str(Path(vault or input('Owner-local encrypted vault path (NEW for activate): ').strip()).expanduser().resolve())
    expected=a.expected;eh=a.expected_sha256
    if phase in ('readback','handoff-restore','period','submission-check') or (phase=='handoff' and 'timing_policy' in b):
        expected=str(Path(expected or input('Reviewed nonsecret expected receipt file: ').strip()).expanduser().resolve())
        eh=eh or input('Expected receipt SHA-256: ').strip();loaded(expected,eh)
    if phase=='period':
        from .intake_owner_operations import validate_policy,private_path
        validate_policy(b,loaded(expected,eh));private_path(b,'period_vault_path',vault)
    if 'timing_policy' in b and phase in ('handoff','submission-check'):
        from .intake_owner_io import operation_observation
        from .intake_owner import validate_binding
        operation_observation(b,loaded(expected,eh),'HANDOFF' if phase=='handoff' else 'SUBMISSION');validate_binding(b,opening=True)
    secret={}
    if vault:
        secret['vault_key']=vault_input(vault,create=phase in ('activate','period','publication-arm'),
                                        mint_bound='publication_mint' in b)
    if phase in ('activate','close','stop-disposition','readback','period'):
        print('Retrieve PropertyAIgent — Supabase postgres password for the existing owner connection; local format checks do not prove server authentication.',file=sys.stderr)
        secret['owner_password']=private_input('PropertyAIgent — Supabase postgres password (hidden): ')
    if phase.startswith('handoff') or phase=='submission-check':
        print('Retrieve PropertyAIgent — Render API key. This is NOT PropertyAIgent — PREBUILD baseline passphrase.',file=sys.stderr)
        secret['render_token']=private_input('PropertyAIgent — Render API key (hidden): ')
    if phase=='publication-arm' or (phase=='handoff' and not b.get('publication_vault_path')):
        from .intake_owner_operations import installation_token_allowed
        print('Retrieve the reviewed short-lived installation token; no connector credential.',file=sys.stderr)
        secret['publication_token']=private_input('Reviewed installation token (hidden): ',maximum=2048,validator=installation_token_allowed,unlock_code='TOKEN')
    raw=json.dumps(secret).encode()
    if len(raw)>4000:raise SystemExit('SECRET_PIPE_BOUND')
    # No local credential-format/decryption refusal can consume this directory.
    output.mkdir(mode=0o700)
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
    status.update(phase=phase,binding_sha256=h,expected_sha256=eh,connection_policy='NO_RECONNECT_NO_RETRY',
        transaction_outcome='RECONCILE' if status['reason'] or status['exit_code'] else 'ACKNOWLEDGED_SEE_RESULT',
        remote_closure='UNKNOWN_AFTER_FORCED_EXIT' if status['reason'] or status['exit_code'] else 'NORMAL_PHASE_EXIT_SEE_RESULT')
    (output/'output.txt').write_bytes(data);(output/'status.json').write_text(json.dumps(status,sort_keys=True)+'\n')
    print('PHASE_REQUIRES_LOCAL_EVIDENCE_REVIEW' if not status['reason'] and status['exit_code']==0 else 'STOP_RECONCILE_NO_RETRY')
    return 0 if status['exit_code']==0 and not status['reason'] else 2


class AttendedCredentials:
    """RAM-only reuse in the current owner process; child input stays anonymous."""
    def __init__(self,vault_password=None):
        self.values={} if vault_password is None else {'vault':vault_password}
        self.expires_at=None;self.base=None;self.old_alarm=None
    @staticmethod
    def kind(prompt):
        if prompt.startswith('B-state Vault passphrase'):return 'vault'
        if prompt.startswith('PropertyAIgent — Supabase postgres password'):return 'postgres'
        if prompt.startswith('PropertyAIgent — Render API key'):return 'render'
        return None  # Never retain signing-key passphrases or arbitrary inputs.
    def arm_expiry(self,expiry):
        self.expires_at=expiry
        if expiry<=time.time():self.clear();return
        if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise SystemExit('ATTENDED_TIMER_CONFLICT')
        self.old_alarm=signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM,lambda *_:self.clear())
        signal.setitimer(signal.ITIMER_REAL,expiry-time.time())
    def clear(self):self.values.clear()  # No secure-erasure guarantee.
    def __enter__(self):
        global private_input
        self.base=private_input
        def reuse(prompt,**kw):
            key=self.kind(prompt)
            if self.expires_at is not None and time.time()>=self.expires_at:self.clear()
            value=self.values.get(key) if key is not None else None
            if value is not None:
                validator=kw.get('validator')
                if validator is None or validator(value):return value
                self.values.pop(key,None)
            value=self.base(prompt,**kw)
            if key is not None and (self.expires_at is None or time.time()<self.expires_at):self.values[key]=value
            return value
        private_input=reuse;return self
    def __exit__(self,*_):
        global private_input
        private_input=self.base;self.clear()
        if self.old_alarm is not None:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,self.old_alarm)


def attended_session(*,vault_password=None):
    """Attended mode of this existing client; no automatic phase or retry."""
    from . import finite_release_binding as flow,publication_mint as mint
    import shlex
    if not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('HIDDEN_OWNER_TTY_REQUIRED')
    s=flow.static();op=__import__(__package__+'.intake_owner',fromlist=['validate_binding'])
    op.require(s.get('version')=='FINITE_TIMING_V2_STATIC' and s.get('execution_day') and s.get('mint_journal_path'),'TIMING_RELEASE_UNBOUND')
    failed=False;closed=set()
    with AttendedCredentials(vault_password) as memory:
        if vault_password is None:vault_input(s['mint_journal_path'])
        record=flow.private_json(flow.MINT_RESULT,'MINT_RESULT_REQUIRED');memory.arm_expiry(record['expiry'])
        while True:
            action=input('Attended action (preview/bind/next/close/publication-revoke/handoff-reconcile/handoff-restore/readback/exit): ').strip()
            if action=='exit':
                print('ATTENDED_SESSION_EXIT: local memory cleared; remote closure is established only by its separate receipts.')
                return 0 if {'close','publication-revoke','handoff-restore'}<=closed else 2
            if action in ('preview','bind','next') and failed:
                print('OPENING_STOPPED_USE_INDEPENDENT_CLOSURE_OR_RECONCILIATION');continue
            if action=='preview':
                review_path=flow.ROOT/'ACTUAL-MINT-REVIEW.json'
                if review_path.exists():
                    review=flow.private_json(review_path,'MINT_REVIEW_REQUIRED')
                    if review.get('mint_result_sha256')!=__import__('hashlib').sha256(flow.MINT_RESULT.read_bytes()).hexdigest():raise SystemExit('TIMING_RELEASE_UNBOUND')
                    print(json.dumps(review,sort_keys=True));continue
                if flow.main(['preview'])!=0:failed=True
                continue
            if action=='bind':
                if any((flow.ROOT/n).exists() or (flow.ROOT/n).is_symlink() for n in ('owner-binding.json','period-policy.json','FROZEN.json')):
                    try:
                        existing,_,_=flow.frozen_binding(opening=False)
                        print('FIXED_BINDING_ALREADY_EXISTS_NO_REBIND; D='+str(existing['valid_until']))
                    except BaseException:
                        print('PARTIAL_BINDING_REQUIRES_REVIEW_NO_RETRY');failed=True;memory.clear()
                    continue
                # Collect once before the35-minute clock, never in command arguments.
                print('Retrieve PropertyAIgent — Supabase postgres password for the reviewed owner connections; retained only in this attended process.',file=sys.stderr)
                private_input('PropertyAIgent — Supabase postgres password (hidden): ')
                print('Retrieve PropertyAIgent — Render API key for handoff/readback/restoration; not the PREBUILD passphrase.',file=sys.stderr)
                private_input('PropertyAIgent — Render API key (hidden): ')
                if flow.main(['bind'])!=0:failed=True;memory.clear()
                continue
            if action=='next':
                try:
                    phase,command=flow.next_command()
                    if phase.startswith('observe-'):
                        print(json.dumps(flow.record_observation(phase[8:].upper()),sort_keys=True));continue
                    args=shlex.split(command)[2:]
                    print('Prepared phase: '+phase+'; normal expected output is not an approval phrase.')
                    code=mint.main(args) if phase=='seal' else main(args)
                    if code!=0:failed=True;memory.clear();continue
                    # Read-only result checks before another phase can be offered.
                    try:flow.next_command()
                    except flow.PreparationError as exc:
                        if exc.code!='NEXT_SUBMISSION_REVIEW_REQUIRED':raise
                    if phase=='submission-check':print('ONE_SUBMISSION_INTENT_SAVED: use the reviewed suspended Dashboard action once, before D-1500; never retry a lost acknowledgement.')
                except BaseException as exc:
                    print(failure_output('UNKNOWN_PHASE',exc));failed=True;memory.clear()
                continue
            if action in ('close','publication-revoke','handoff-reconcile','handoff-restore','readback'):
                # No opening/freshness/E guard: original independent closure remains usable.
                bpath=flow.ROOT/'owner-binding.json';bh=__import__('hashlib').sha256(bpath.read_bytes()).hexdigest();b=loaded(str(bpath),bh)
                args=['--phase',action,'--binding',str(bpath),'--binding-sha256',bh,'--evidence',str(flow.ROOT/(action+'-evidence'))]
                if action!='readback':args+=['--vault',b['publication_vault_path'] if action=='publication-revoke' else s['access_vault']]
                if main(args)==0:closed.add(action)
                if {'close','publication-revoke','handoff-restore'}<=closed:memory.clear()
                continue
            print('ATTENDED_ACTION_REFUSED')


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

