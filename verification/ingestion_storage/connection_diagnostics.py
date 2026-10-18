"""Fixed observations only; native text may be matched locally, never exported.

A phase identifies the failed boundary, not its underlying cause. In particular,
SQLSTATE=None and OperationalError do not establish TLS/authentication failure.
"""
import re

STATES = {'28P01':'AUTHENTICATION_REJECTED', '28000':'AUTHORIZATION_REJECTED',
          '42501':'PERMISSION_DENIED', '53300':'CONNECTION_CAPACITY',
          '57P03':'SERVER_NOT_READY', '3D000':'DATABASE_NOT_FOUND',
          '57014':'STATEMENT_CANCELLED', '08006':'CONNECTION_FAILURE'}
# These are observations of libpq/provider wording, not independently verified
# root causes. No variable capture group, matched text or exception repr escapes.
PATTERNS = (
    ('TLS_HOSTNAME_MISMATCH', r'(?:does not match host name|does not match hostname|hostname mismatch)'),
    ('TLS_CA_UNAVAILABLE', r'root certificate file[^\n]{0,512}(?:does not exist|could not read|permission denied)'),
    ('TLS_CHAIN_REJECTED', r'(?:certificate verify failed|certificate verification failed)'),
    ('AUTHENTICATION_REJECTED', r'password authentication failed for user'),
    ('ROUTING_IDENTITY_REJECTED', r'\btenant or user not found\b'),
    ('AUTHORIZATION_REJECTED', r'\bno pg_hba.conf entry\b'),
    ('PERMISSION_DENIED', r'permission denied for database'),
    ('CONNECTION_CAPACITY', r'(?:too many clients already|max client connections reached)'),
    ('CONNECTION_TIMEOUT', r'(?:\btimeout expired\b|\bconnection timeout expired\b)'),
    ('CONNECTION_REFUSED', r'\bconnection refused\b'),
    ('DNS_LOOKUP_FAILED', r'could not translate host name'),
)

def classify_native(original, state):
    import psycopg
    if not isinstance(original, psycopg.Error):return 'UNKNOWN','NONE'
    if state in STATES:return STATES[state],'SQLSTATE'
    # Work only on bounded native messages. Do not truncate a huge message and
    # then classify a misleading prefix. Unknown/ambiguous remains UNKNOWN.
    if not original.args or not isinstance(original.args[0],str):return 'UNKNOWN','NONE'
    message=original.args[0]
    if len(message)>16384:return 'UNKNOWN','NONE'
    matched={code for code,pattern in PATTERNS if re.search(pattern,message,re.I)}
    return (matched.pop(),'LOCAL_ALLOWLIST') if len(matched)==1 else ('UNKNOWN','NONE')

PHASES = {'PREPARATION','ROUTE_VALIDATION','DRIVER_CONNECT','SERVER_IDENTITY','ENGINE_CHECKOUT','EXECUTION'}
# Ordered client-side preparation boundaries (before any database connection). SESSION_INPUT/REGISTRATION_EXPIRY precede preparation proper.
STAGES = ('SESSION_INPUT','REGISTRATION_EXPIRY','ROUTE_VALIDATION','PASSWORD_PRESENCE','CA_TRUST','DNS_RESOLUTION','ADDRESS_POLICY','DRIVER_IMPORT',
          'RUNNER_COMPONENTS','RUNNER_CONSTRUCTION')
PREPARATION_REASONS = frozenset({'REGISTRATION_EXPIRED','PASSWORD_ABSENT','UNEXPECTED_EXCEPTION','DNS_TIMEOUT','DNS_SUBPROCESS_SPAWN_FAILED','DNS_NONZERO_EXIT',
    'DNS_OUTPUT_BOUND','DNS_EMPTY_OUTPUT','DNS_MALFORMED_OUTPUT','DNS_NO_ADDRESS','DNS_TOO_MANY_ADDRESSES','DNS_INVALID_ADDRESS','REVIEWED_IPV4_ONLY',
    'ROUTE_DRIVER_MISMATCH','ROUTE_HOST_MISMATCH','ROUTE_PORT_MISMATCH','ROUTE_DATABASE_MISMATCH','ROUTE_USERNAME_MISMATCH','ROUTE_QUERY_FORBIDDEN',
    'ROUTE_MALFORMED_INPUT','REVIEWED_CA_MISSING','REVIEWED_CA_HASH_MISMATCH','REVIEWED_CA_NOT_SIGNING_CA','REVIEWED_CA_VALIDITY_REVIEW_REQUIRED',
    'REVIEWED_CA_DER_MISMATCH','DRIVER_IMPORT_FAILED','COMPONENT_IMPORT_FAILED','RUNNER_CONSTRUCTION_FAILED'})
KINDS = {'OperationalError','InterfaceError','ProgrammingError','InternalError',
         'InvalidPassword','InvalidAuthorizationSpecification','ConnectionTimeout',
         'Denied','ValueError','TimeoutError','ConnectionRefusedError','OSError',
         # preparation-stage classes (class names only; never messages)
         'RouteRejection','JSONDecodeError','TimeoutExpired','ImportError','ModuleNotFoundError','FileNotFoundError','InvalidSignature','KeyError','AttributeError','TypeError',
         'PreparationFailure','Uncertain'}


def kind_of(exc):
    kind=type(getattr(exc,'orig',exc)).__name__
    return kind if kind in KINDS else 'OTHER'


class PreparationFailure(Exception):
    """A preparation boundary failed. Carries ONLY a fixed stage, a fixed reason and bounded non-secret flags; str() is the fixed codes."""
    def __init__(self,stage,reason,**flags):
        if stage not in STAGES or reason not in PREPARATION_REASONS:raise ValueError('PREPARATION_CODE')
        self.stage=stage;self.reason=reason
        self.flags={k:v for k,v in flags.items() if k in {'exit_code','exception_kind'} and (v is None or isinstance(v,int) and not isinstance(v,bool) and -255<=v<=255 or k=='exception_kind' and v in KINDS|{'OTHER'})}
        super().__init__(stage+':'+reason)

def safe_failure(exc, phase):
    if phase not in PHASES: raise ValueError('DIAGNOSTIC_PHASE')
    if isinstance(exc,PreparationFailure):
        return dict(phase='PREPARATION',stage=exc.stage,exception_kind='PreparationFailure',sqlstate=None,reason_code=exc.reason,classification_source='FIXED_PREPARATION_CODE',
                    failed_native_connection_finished=False,underlying_cause='UNDETERMINED',message_exported=False,flags=dict(exc.flags))
    original = getattr(exc, 'orig', exc)
    kind = type(original).__name__
    state = getattr(original, 'sqlstate', None)
    if state is None:
        state=getattr(getattr(original,'diag',None),'sqlstate',None)
    if not isinstance(state,str) or not re.fullmatch('[0-9A-Z]{5}',state): state=None
    reason,source=classify_native(original,state)
    from psycopg.errors import FinishedPGconn
    finished=isinstance(getattr(original,'pgconn',None),FinishedPGconn)
    return dict(phase=phase,exception_kind=kind if kind in KINDS else 'OTHER',
                sqlstate=state,reason_code=reason,classification_source=source,
                failed_native_connection_finished=finished,
                underlying_cause='UNDETERMINED',message_exported=False)
