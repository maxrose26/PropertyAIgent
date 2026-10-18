"""Credential-safe, stage-attributed preparation before any database connection.

The operational wrapper prepares a Runner in ordered stages (registration expiry, exact route, password presence, reviewed CA, bounded DNS, driver import,
Runner components, Runner construction). Each stage reports only a fixed stage code, a fixed reason code and bounded non-secret flags. No exception message,
URL, password, token, SCRAM verifier, environment value or query text is ever exported; an unclassified failure stays reason UNEXPECTED_EXCEPTION with an
allow-listed exception class name (else OTHER). A stage name identifies WHERE preparation stopped; it does not establish why beyond the fixed reason.
"""
import ipaddress,json,subprocess,sys,time
from contextlib import contextmanager
from .connection_diagnostics import PreparationFailure,STAGES,kind_of

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
        self.dns=dict(subprocess_started=False,subprocess_completed=False,exit_code=None,stdout_bytes=None,address_count=None)
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
        self.completed.append(name)

    def report(self):
        return dict(current_stage=self.current,completed_stages=list(self.completed),dns=dict(self.dns),
                    database_connection_calls=self.database_connection_calls,
                    elapsed_seconds=round(time.monotonic()-self.started,6))

    def work(self):
        """Total work performed, distinct from the (empty) runtime slot table. Bases: the DNS subprocess and the connect closure are MEASURED here; the GitHub client,
        source reader and statements are structurally NOT_STARTED because preparation never invokes them (they are handed to the Runner uninvoked)."""
        started=bool(self.dns['subprocess_started'])
        return dict(database_connections=dict(value=self.database_connection_calls,basis='MEASURED'),
                    database_statements=dict(value=0,basis='NOT_STARTED'),github_cli_invocations=dict(value=0,basis='NOT_STARTED'),source_requests=dict(value=0,basis='NOT_STARTED'),
                    local_subprocesses=dict(value=1 if started else 0,basis='MEASURED'),
                    state='PREPARATION_ONLY_NO_DATABASE_GITHUB_OR_SOURCE_WORK' if not self.database_connection_calls else 'DATABASE_CONNECT_CALLED_DURING_PREPARATION')


def resolve_addresses(progress,*,command=None,run=subprocess.run,timeout=DNS_TIMEOUT_SECONDS):
    """Bounded IPv4 resolution in a credential-free subprocess. The exit status is checked BEFORE the output is parsed."""
    command=command or dns_command()
    progress.dns['subprocess_started']=True
    try:
        done=run(command,env=DNS_ENVIRONMENT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
    except subprocess.TimeoutExpired:raise PreparationFailure('DNS_RESOLUTION','DNS_TIMEOUT') from None
    except OSError:raise PreparationFailure('DNS_RESOLUTION','DNS_SUBPROCESS_SPAWN_FAILED') from None
    progress.dns.update(subprocess_completed=True,exit_code=done.returncode if isinstance(done.returncode,int) and -255<=done.returncode<=255 else None,
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
    if any(a.version!=4 for a in parsed):raise PreparationFailure('ADDRESS_POLICY','REVIEWED_IPV4_ONLY')
    return sorted(str(a) for a in parsed)[0]
