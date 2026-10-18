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

PHASES = {'ROUTE_VALIDATION','DRIVER_CONNECT','SERVER_IDENTITY','ENGINE_CHECKOUT','EXECUTION'}
KINDS = {'OperationalError','InterfaceError','ProgrammingError','InternalError',
         'InvalidPassword','InvalidAuthorizationSpecification','ConnectionTimeout',
         'Denied','ValueError','TimeoutError','ConnectionRefusedError','OSError'}

def safe_failure(exc, phase):
    if phase not in PHASES: raise ValueError('DIAGNOSTIC_PHASE')
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
