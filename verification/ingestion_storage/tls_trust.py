"""Reviewed Supabase CA trust; no download, credential or endpoint selection."""
from pathlib import Path
import hashlib
from datetime import datetime,timezone,timedelta
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
ROOT=Path(__file__).resolve().parent/'trust'/'supabase-prod-ca-2021.crt'
PEM_SHA256='700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7'
DER_SHA256='807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa'
PROVENANCE='https://github.com/supabase/supabase/blob/bc27d2661edd09a5d0b8d76ce33da6d4071a756e/apps/studio/hooks/custom-content/custom-content.json'


def verified_trust(now=None):
    if ROOT.is_symlink() or not ROOT.is_file():raise ValueError('REVIEWED_CA_MISSING')
    raw=ROOT.read_bytes()
    if len(raw)>16384 or hashlib.sha256(raw).hexdigest()!=PEM_SHA256:raise ValueError('REVIEWED_CA_HASH_MISMATCH')
    cert=x509.load_pem_x509_certificate(raw)
    if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca or not cert.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign:raise ValueError('REVIEWED_CA_NOT_SIGNING_CA')
    cert.public_key().verify(cert.signature,cert.tbs_certificate_bytes,padding.PKCS1v15(),cert.signature_hash_algorithm)
    now=now or datetime.now(timezone.utc)
    if now<cert.not_valid_before_utc or now+timedelta(days=90)>=cert.not_valid_after_utc:raise ValueError('REVIEWED_CA_VALIDITY_REVIEW_REQUIRED')
    if cert.fingerprint(hashes.SHA256()).hex()!=DER_SHA256:raise ValueError('REVIEWED_CA_DER_MISMATCH')
    return ROOT,dict(pem_sha256=PEM_SHA256,der_sha256=DER_SHA256,not_after=cert.not_valid_after_utc.isoformat(),provenance=PROVENANCE)


def failure_evidence(exc):
    """Allowlisted categories and closure receipt only; never dump PGconn/DSN."""
    from psycopg.errors import FinishedPGconn
    native=getattr(exc,'orig',exc);message=str(native).lower()
    if 'does not match host name' in message or 'does not match hostname' in message or 'hostname mismatch' in message:category='TLS_HOSTNAME_MISMATCH'
    elif 'root certificate file' in message and ('does not exist' in message or 'could not read' in message):category='TLS_CA_FILE_MISSING_OR_UNREADABLE'
    elif 'certificate verify failed' in message:category='TLS_CHAIN_VERIFICATION_FAILED_DETAIL_UNAVAILABLE'
    elif 'password authentication failed' in message:category='AUTHENTICATION_FAILED'
    elif 'timeout' in message:category='CONNECTION_TIMEOUT'
    else:category='REDACTED_FAILURE'
    # FinishedPGconn is a deliberately unusable snapshot created AFTER PQfinish.
    closed=isinstance(getattr(native,'pgconn',None),FinishedPGconn)
    return dict(reason_code=category,failed_native_connection_finished=closed)


def owned_resources():
    """Linux /proc/self works even when psutil's PID namespace differs."""
    sockets=set();children=set();fds=list(Path('/proc/self/fd').iterdir())
    if len(fds)>256:raise ValueError('OWNED_FD_BOUND')
    for fd in fds:
        try:target=fd.readlink().as_posix()
        except FileNotFoundError:continue # descriptor closed during enumeration
        if target.startswith('socket:['):sockets.add((fd.name,target))
    tasks=list(Path('/proc/self/task').iterdir())
    if len(tasks)>256:raise ValueError('OWNED_THREAD_BOUND')
    missing_children=False
    for task in tasks:
        try:children.update((task/'children').read_text().split())
        except FileNotFoundError:missing_children=True
    if missing_children:
        # Reuse the accepted process supervisor's PPID graph. Some supported
        # kernels omit task/children; absence is not evidence of zero children.
        from app.security.document_process import own_host_pid,descendants,proc_info
        host=own_host_pid();before=proc_info(host)
        graph=descendants(host)
        if proc_info(host)['start']!=before['start']:raise ValueError('OWNED_PROCESS_IDENTITY_CHANGED')
        children.update(str(pid) for pid in graph if pid!=host)
    return dict(socket_fds=sockets,children=children)
