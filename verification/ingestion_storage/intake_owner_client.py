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
          'handoff-reconcile', 'handoff-restore', 'publication-close')


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
    if phase in ('activate','qualify','close','handoff','handoff-reconcile','handoff-restore','publication-close'):
        vault=Vault(vault_path,secrets_input['vault_key'],create=phase=='activate')
        save=vault.save
        if phase!='activate':
            state=vault.load()
            op.require(state['binding']==binding,'VAULT_BINDING_CHANGED')
    if phase.startswith('handoff'):
        api=Render(secrets_input['render_token'])
        try:
            if phase=='handoff':return handoff(api,state,save,secrets_input['publication_token'])
            if phase=='handoff-reconcile':return reconcile_handoff(api,state,save)
            return restore_handoff(api,state,save,expected.get('job_id'))
        finally:api.session.close()
    if phase=='publication-close':
        # Existing bounded GitHub publisher transport, with only the exact token
        # inherited by its owner-local gh child. Installation tokens self-revoke.
        from .operational_publication import GitHub
        token=state['render']['publication_token']
        op.require(token.startswith('ghs_'),'SELF_REVOCABLE_INSTALLATION_TOKEN_REQUIRED')
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
        if phase=='activate':return op.activate(c,binding,save)
        if phase=='close':return op.close(c,state,save)
        if phase=='stop-disposition':return op.stop_disposition(c,binding.get('stop_decisions',[]))
        if phase=='readback':return op.finalisation(c,binding,expected)
    raise SystemExit('UNKNOWN_PHASE')


def main(argv=None):
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('--child',action='store_true');p.add_argument('--secrets-fd',type=int)
    p.add_argument('--phase',choices=PHASES);p.add_argument('--binding');p.add_argument('--binding-sha256')
    p.add_argument('--vault');p.add_argument('--expected');p.add_argument('--expected-sha256')
    a=p.parse_args(argv)
    if a.child:
        try:
            secret=json.loads(os.read(a.secrets_fd,4096));os.close(a.secrets_fd)
            b=loaded(a.binding,a.binding_sha256)
            expected=loaded(a.expected,a.expected_sha256) if a.expected else {}
            result=worker(a.phase,b,secret,a.vault,expected)
            raw=json.dumps(result,sort_keys=True).encode()
            if len(raw)>30000:raise ValueError('RESULT_BOUND')
            print(raw.decode());return 0
        except BaseException:
            print('STOP_PHASE_REQUIRES_REVIEW_NO_RETRY');return 2
    if not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('HIDDEN_OWNER_TTY_REQUIRED')
    phase=a.phase or input('Approved phase: ').strip()
    if phase not in PHASES:raise SystemExit('PHASE_REFUSED')
    path=str(Path(a.binding or input('Reviewed binding file: ').strip()).expanduser().resolve())
    h=a.binding_sha256 or input('Reviewed binding SHA-256: ').strip()
    loaded(path,h)
    if input('Approval phrase (EXECUTE_EXACT_'+phase.upper().replace('-','_')+'_ONCE): ').strip()!= 'EXECUTE_EXACT_'+phase.upper().replace('-','_')+'_ONCE':
        raise SystemExit('EXPLICIT_PHASE_APPROVAL_REQUIRED')
    output=Path(input('NEW private phase evidence directory: ').strip()).expanduser();output.mkdir(mode=0o700)
    vault=a.vault
    if phase in ('activate','qualify','close','handoff','handoff-reconcile','handoff-restore','publication-close'):
        vault=str(Path(vault or input('Owner-local encrypted vault path (NEW for activate): ').strip()).expanduser().resolve())
    expected=a.expected;eh=a.expected_sha256
    if phase in ('readback','handoff-restore'):
        expected=str(Path(expected or input('Reviewed nonsecret expected receipt file: ').strip()).expanduser().resolve())
        eh=eh or input('Expected receipt SHA-256: ').strip();loaded(expected,eh)
    secret={}
    if phase in ('activate','close','stop-disposition','readback'):secret['owner_password']=hidden('Existing owner password (hidden): ')
    if vault:secret['vault_key']=hidden('Vault passphrase, at least 24 characters (hidden): ')
    if phase.startswith('handoff'):secret['render_token']=hidden('Existing owner-local Render token (hidden): ')
    if phase=='handoff':secret['publication_token']=hidden('Reviewed short-lived GitHub installation token (hidden): ')
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


if __name__=='__main__':raise SystemExit(main())

