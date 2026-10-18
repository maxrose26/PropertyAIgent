"""Credential-safe, stage-attributed preparation before any database connection.

The operational wrapper prepares a Runner in ordered stages (registration expiry, exact route, password presence, reviewed CA, bounded DNS, driver import,
Runner components, Runner construction). Each stage reports only a fixed stage code, a fixed reason code and bounded non-secret flags. No exception message,
URL, password, token, SCRAM verifier, environment value or query text is ever exported; an unclassified failure stays reason UNEXPECTED_EXCEPTION with an
allow-listed exception class name (else OTHER). A stage name identifies WHERE preparation stopped; it does not establish why beyond the fixed reason.
"""
import ipaddress,json,subprocess,sys,time
from contextlib import contextmanager
from datetime import datetime,timezone
from types import SimpleNamespace
from .connection_diagnostics import PreparationFailure,STAGES,kind_of
from .tls_trust import verified_trust

STARTUP_OPTIONS='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000'
DNS_HOST='aws-0-eu-west-2.pooler.supabase.com'
DNS_PORT=5432
DNS_TIMEOUT_SECONDS=3
DNS_STDOUT_BOUND_BYTES=4096
DNS_ENVIRONMENT={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
CA_REASONS=frozenset({'REVIEWED_CA_MISSING','REVIEWED_CA_HASH_MISMATCH','REVIEWED_CA_NOT_SIGNING_CA','REVIEWED_CA_VALIDITY_REVIEW_REQUIRED','REVIEWED_CA_DER_MISMATCH'})


def dns_command():
    """Credential-free exec so a stuck libc lookup cannot survive its hard timeout. Evaluated per call so the interpreter path is the live one."""
    return [sys.executable,'-c',"import socket,json;print(json.dumps(sorted({x[4][0] for x in socket.getaddrinfo('%s',%d,family=socket.AF_INET,type=socket.SOCK_STREAM)})))"%(DNS_HOST,DNS_PORT)]


class Progress:
    """Mutable, non-secret preparation record shared with the session so a failure at any boundary exports exact stage accounting."""
    def __init__(self):
        self.current=None;self.completed=[];self.started=time.monotonic()
        self.dns=dict(subprocess_started=False,subprocess_spawned=False,subprocess_completed=False,exit_code=None,stdout_bytes=None,address_count=None)
        self.database_connection_calls=0

    @contextmanager
    def stage(self,name):
        if name not in STAGES:raise ValueError('PREPARATION_STAGE')
        self.current=name
        try:yield
        except PreparationFailure:raise
        except Exception as exc:
            # Only the class name (allow-listed) escapes; the message and chain are discarded.
            raise PreparationFailure(name,'UNEXPECTED_EXCEPTION',exception_kind=kind_of(exc)) from None
        self.completed.append(name);self.current=None   # between stages nothing is current; a later interruption is reported as such, never blamed on a finished stage

    def report(self):
        return dict(current_stage=self.current,completed_stages=list(self.completed),dns=dict(self.dns),
                    database_connection_calls=self.database_connection_calls,
                    elapsed_seconds=round(time.monotonic()-self.started,6))

    def work(self):
        """Total work performed, distinct from the (empty) runtime slot table. Bases: the DNS subprocess and the connect closure are MEASURED here; the GitHub client,
        source reader and statements are structurally NOT_STARTED because preparation never invokes them (they are handed to the Runner uninvoked)."""
        spawned=bool(self.dns['subprocess_spawned'])
        return dict(database_connections=dict(value=self.database_connection_calls,basis='MEASURED'),
                    database_statements=dict(value=0,basis='NOT_STARTED'),github_cli_invocations=dict(value=0,basis='NOT_STARTED'),source_requests=dict(value=0,basis='NOT_STARTED'),
                    dns_subprocesses_spawned=dict(value=1 if spawned else 0,basis='MEASURED',scope='PREPARATION_DNS_CHILD_ONLY'),
                    state='PREPARATION_ONLY_NO_DATABASE_GITHUB_OR_SOURCE_WORK' if not self.database_connection_calls else 'CONNECT_CLOSURE_INVOKED_AFTER_PREPARATION')


def resolve_addresses(progress,*,command=None,run=subprocess.run,timeout=DNS_TIMEOUT_SECONDS):
    """Bounded IPv4 resolution in a credential-free subprocess. The exit status is checked BEFORE the output is parsed."""
    command=command or dns_command()
    progress.dns['subprocess_started']=True
    try:
        done=run(command,env=DNS_ENVIRONMENT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
    except subprocess.TimeoutExpired:
        progress.dns['subprocess_spawned']=True   # a timeout can only follow a successful spawn; subprocess.run kills and reaps the child
        raise PreparationFailure('DNS_RESOLUTION','DNS_TIMEOUT') from None
    except OSError:raise PreparationFailure('DNS_RESOLUTION','DNS_SUBPROCESS_SPAWN_FAILED') from None
    progress.dns.update(subprocess_spawned=True,subprocess_completed=True,exit_code=done.returncode if isinstance(done.returncode,int) and -255<=done.returncode<=255 else None,
                        stdout_bytes=len(done.stdout) if isinstance(done.stdout,(bytes,bytearray)) else None)
    if done.returncode!=0:raise PreparationFailure('DNS_RESOLUTION','DNS_NONZERO_EXIT',exit_code=progress.dns['exit_code'])
    if not isinstance(done.stdout,(bytes,bytearray)) or len(done.stdout)>DNS_STDOUT_BOUND_BYTES:raise PreparationFailure('DNS_RESOLUTION','DNS_OUTPUT_BOUND')
    if not done.stdout.strip():raise PreparationFailure('DNS_RESOLUTION','DNS_EMPTY_OUTPUT')
    try:addresses=json.loads(done.stdout)
    except ValueError:raise PreparationFailure('DNS_RESOLUTION','DNS_MALFORMED_OUTPUT') from None
    if not isinstance(addresses,list) or not all(isinstance(x,str) for x in addresses):raise PreparationFailure('DNS_RESOLUTION','DNS_MALFORMED_OUTPUT')
    progress.dns['address_count']=len(addresses)
    if not addresses:raise PreparationFailure('DNS_RESOLUTION','DNS_NO_ADDRESS')
    if len(addresses)>32:raise PreparationFailure('DNS_RESOLUTION','DNS_TOO_MANY_ADDRESSES')
    parsed=[]
    for text in addresses:
        try:parsed.append(ipaddress.ip_address(text))
        except ValueError:raise PreparationFailure('DNS_RESOLUTION','DNS_INVALID_ADDRESS') from None
    if any(a.version!=4 for a in parsed):raise PreparationFailure('DNS_RESOLUTION','REVIEWED_IPV4_ONLY')
    return sorted(str(a) for a in parsed)[0]


def prepare_connection(r,raw,*,progress,dns_run=subprocess.run,dns_command=None):
    """The credential-dependent, connection-free preparation shared by every operational path: expiry, exact route, password presence, reviewed CA, bounded DNS, driver import.

    Returns the parsed route, the CA path, the selected address and a `connect` closure. No connection is made here; `connect` only counts and opens when a caller invokes it.
    The startup options are the previously reviewed values and are deliberately unchanged."""
    with progress.stage('REGISTRATION_EXPIRY'):
        if datetime.now(timezone.utc)>=datetime.fromisoformat(r['expires_at']):raise PreparationFailure('REGISTRATION_EXPIRY','REGISTRATION_EXPIRED')
    with progress.stage('ROUTE_VALIDATION'):
        from verification.discovery.route_validation import validate_route,RouteRejection
        try:u=validate_route(raw)
        except RouteRejection as rejection:raise PreparationFailure('ROUTE_VALIDATION','ROUTE_'+rejection.code) from None
    with progress.stage('PASSWORD_PRESENCE'):
        if not isinstance(u.password,str) or not u.password:raise PreparationFailure('PASSWORD_PRESENCE','PASSWORD_ABSENT')
    with progress.stage('CA_TRUST'):
        try:ca,_=verified_trust()
        except ValueError as exc:
            # The reviewed trust module raises only fixed REVIEWED_CA_* codes; anything else stays an unclassified exception.
            if str(exc) in CA_REASONS:raise PreparationFailure('CA_TRUST',str(exc)) from None
            raise
    with progress.stage('DNS_RESOLUTION'):
        selected=resolve_addresses(progress,command=dns_command,run=dns_run)
    with progress.stage('DRIVER_IMPORT'):
        try:import psycopg
        except ImportError:raise PreparationFailure('DRIVER_IMPORT','DRIVER_IMPORT_FAILED') from None
    def connect():
        progress.database_connection_calls+=1
        return psycopg.connect(host=u.host,hostaddr=selected,port=u.port,dbname=u.database,user=u.username,password=u.password,sslmode='verify-full',sslrootcert=str(ca),connect_timeout=3,prepare_threshold=None,autocommit=True,options=STARTUP_OPTIONS)
    return SimpleNamespace(route=u,ca=ca,hostaddr=selected,connect=connect)
