"""Explicit frozen #213 Database adaptation: approved DNS member, no failover.

No production authority. Call database_type(pinned_root) once before opening the
owner route; use its address unchanged in the existing package/binding/runtime.
"""
import ast
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess
import sys
from contextlib import contextmanager

HOST = 'aws-0-eu-west-2.pooler.supabase.com'
PORT = 5432
ADDRESS = '18.169.28.97'
SOURCE_SHA = 'f33439807df02e14fec167e7f3782a36af5e12e52949404c2388b610d1e61981'
CLASS_SHA = '4959d79558bd5c4a5aabb8ec6c5dd6f05c02720c23bcefa9bf6985507673b36f'
ANCHOR = 'self.address=socket.getaddrinfo(u.host,u.port,socket.AF_INET,socket.SOCK_STREAM)[0][4][0]'
# Fixed input, isolated interpreter, no credential environment or unbounded output.
DNS_CODE = """import socket,json
rows=socket.getaddrinfo('aws-0-eu-west-2.pooler.supabase.com',5432,socket.AF_INET,socket.SOCK_STREAM)
if not 0<len(rows)<=32: raise SystemExit(2)
raw=json.dumps([r[4][0] for r in rows]).encode()
if len(raw)>4096: raise SystemExit(2)
print(raw.decode())
"""


def approved_address(host, port):
    if (host, port) != (HOST, PORT):
        raise ValueError('TAMESIDE_OWNER_ROUTE_DRIFT')
    try:
        result = subprocess.run([sys.executable, '-I', '-c', DNS_CODE],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=3, check=False, env={'LANG': 'C.UTF-8'})
        if result.returncode or len(result.stdout)>4096:
            raise ValueError('TAMESIDE_DNS_RESULT')
        addresses = json.loads(result.stdout)
        if (type(addresses) is not list or not 0<len(addresses)<=32
                or any(type(a) is not str or str(ipaddress.IPv4Address(a))!=a for a in addresses)):
            raise ValueError('TAMESIDE_DNS_RESULT')
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as exc:
        raise ValueError('TAMESIDE_DNS_REFUSED') from None
    if ADDRESS not in addresses:
        raise ValueError('TAMESIDE_APPROVED_ADDRESS_ABSENT')
    return ADDRESS


def database_type(pinned_root):
    """Keep frozen route, key derivation and connection implementation byte-exact.

    Execute only the hash-verified class, not an imported mutable module. The
    original TLS trust implementation is hash-verified before use as well.
    """
    root=Path(pinned_root)
    path=root/'verification/ingestion_storage/owner_pilot.py'
    source=path.read_text()
    if hashlib.sha256(source.encode()).hexdigest()!=SOURCE_SHA:
        raise ValueError('TAMESIDE_OWNER_DATABASE_SOURCE_DRIFT')
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Database')
    original=ast.get_source_segment(source,node)
    if hashlib.sha256(original.encode()).hexdigest()!=CLASS_SHA or original.count(ANCHOR)!=1:
        raise ValueError('TAMESIDE_OWNER_DATABASE_CLASS_DRIFT')
    from . import tls_trust
    if hashlib.sha256(Path(tls_trust.__file__).read_bytes()).hexdigest()!='5b6e3dac999ad4b23efe148bb07ab43f64d4776e0c521d7303cecb9a2d47060d':
        raise ValueError('TAMESIDE_OWNER_TLS_SOURCE_DRIFT')
    verified_trust=tls_trust.verified_trust
    def require(ok, code):
        if not ok: raise ValueError(code)
    from types import SimpleNamespace
    scope=dict(os=__import__('os'), hashlib=hashlib, contextmanager=contextmanager,
               op=SimpleNamespace(require=require), verified_trust=verified_trust,
               approved_address=approved_address)
    revised=original.replace(ANCHOR,'self.address=approved_address(u.host,u.port)',1)
    exec(compile(revised,str(path)+'[approved-dns-member]','exec'),scope)
    return scope['Database']
