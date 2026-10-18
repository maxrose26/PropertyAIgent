"""Allowlisted connection observations. Never inspect exception messages/DSNs.

A phase identifies the failed boundary, not its underlying cause. In particular,
SQLSTATE=None and OperationalError do not establish TLS/authentication failure.
"""
import re

PHASES = {'ROUTE_VALIDATION','DRIVER_CONNECT','SERVER_IDENTITY','ENGINE_CHECKOUT','EXECUTION'}
KINDS = {'OperationalError','InterfaceError','ProgrammingError','InternalError',
         'InvalidPassword','InvalidAuthorizationSpecification','ConnectionTimeout',
         'Denied','ValueError','TimeoutError','ConnectionRefusedError','OSError'}

def safe_failure(exc, phase):
    if phase not in PHASES: raise ValueError('DIAGNOSTIC_PHASE')
    original = getattr(exc, 'orig', exc)
    kind = type(original).__name__
    state = getattr(original, 'sqlstate', None)
    if not isinstance(state,str) or not re.fullmatch('[0-9A-Z]{5}',state): state=None
    return dict(phase=phase,exception_kind=kind if kind in KINDS else 'OTHER',
                sqlstate=state,underlying_cause='UNDETERMINED',message_exported=False)
