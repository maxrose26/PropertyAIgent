"""Single-use owner-local STORAGE ONLY controller. No source or application APIs.

The supervisor owns the cumulative clock and fsynced hash-chain journal. Its
worker owns at most one SQL connection, keeps credentials only in memory, and
must receive a durable acknowledgement before each external effect. An unknown
outcome stops; this executable deliberately has no resume/retry/repair switch.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import resource
import signal
import socket
import subprocess
import sys
import time

from . import credential_mapping as mapping
from .tls_trust import verified_trust, owned_resources
from .memory_enforcement import WorkerMemory, owner_scope, MemoryUnavailable

AUTHORITY = mapping.AUTHORITY
CONTROLLER = 'verification.ingestion_storage.storage_controller'
CONSUMED_CONTROLLER_BINDING = 'cfc38625cca22de33d973f42851d3ea908d0b35f2a9e2ccc7e7000e52b42b082'
PRIOR_AUDIT_SHA256 = '5dda1e97c8dfc2a9a899c839e9c60d88f3c08bff05d5172579ad2efe1ade279e'
PRIOR_SUPERVISED_SECONDS = 0.11050213100043038 + 1.1728088340005343
PRIOR_CONNECTIONS = 1
PRIOR_COMMANDS = 4
PRIOR_DB_ACTIVE_SECONDS = 0.26088705100028164
PRIOR_RETURNED_BYTES = 39
ORIGINAL_EXPIRY = '2026-10-18T08:54:58.469465Z'
MIGRATION_FLAGS = dict(rolsuper=False,rolcreaterole=True,rolcreatedb=True,rolbypassrls=True)
PRIOR_ATTEMPTS = [
    dict(directory='storage-acceptance-once-20261016',bytes=1573,sha256='f509bd0d5a53282d099ca68b6d5ceb0e60047dd500991395779ba483621aafc0',registration_sha256='802a4eae09ec897c1cc9c27704abeb9f6913eaeb919252ed64e98a452a055279',cleanup='UNCERTAIN'),
    dict(directory='storage-acceptance-memory-successor-20261017',bytes=7005,sha256=PRIOR_AUDIT_SHA256,registration_sha256=CONSUMED_CONTROLLER_BINDING,cleanup='UNCERTAIN'),
]
PRIOR_EXPORT_RESERVED_BYTES = 16384
RETIRED_BINDING = 'e685c79086758f5b52bf5ceff5a8ad34fb2d9e2598e8670485b3ce3a07d7252d'
PACKAGE = Path('docs/design/ingestion-provisioning-20261016')
MANIFEST = Path('docs/design/ingestion-readiness-20261016/three-items.json')
LIMITS = dict(mapping.LIMITS, storage_commands=40, storage_connections=8,
              storage_active_seconds=30, provisioning_seconds=90,
              storage_seconds=120, teardown_seconds=30, teardown_commands=10, teardown_active_seconds=10)
FILES = ['verification/ingestion_storage/storage_controller.py',
         'verification/ingestion_storage/memory_enforcement.py',
         'verification/ingestion_storage/owner-requirements.txt',
         'verification/stage1-requirements.lock',
         'verification/ingestion_storage/credential_mapping.py',
         'verification/ingestion_storage/tls_trust.py',
         'verification/discovery/route_validation.py',
         'verification/ingestion_storage/trust/supabase-prod-ca-2021.crt',
         *(str(PACKAGE / f) for f in ('install.sql','activate.sql','revoke.sql','storage-readback.sql')),
         str(MANIFEST)]
ROLE_NAMES = tuple(mapping.MAPPINGS)
SECRETS = tuple(mapping.MAPPINGS.values())
CONTROL_KEY = '0' * 64
SUPERVISED_SECONDS = 240 - PRIOR_SUPERVISED_SECONDS
CLOSURE_SECONDS = 2


def safe_failure(exc):
    import re
    code=str(exc) if isinstance(exc,(Stop,MemoryUnavailable)) and re.fullmatch(r'[A-Z_]{1,80}',str(exc)) else 'CONTROLLER_EXCEPTION'
    state=getattr(exc,'sqlstate',None)
    return dict(reason=code,sqlstate=state if isinstance(state,str) and re.fullmatch(r'[A-Z0-9]{5}',state) else None)


class Stop(Exception):
    """Only fixed reason codes may cross the worker boundary."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def split_sql(source):
    """Split only top-level SQL; preserve dollar bodies, strings and comments.

    Driver statements are counted individually, not hidden behind a multi-SQL
    execute. Commands inside reviewed DO/functions remain server-side work and
    are not falsely labelled separate driver calls.
    """
    import re
    parts=[]; start=0; i=0; quote=None; comment=0
    while i < len(source):
        if comment:
            if source.startswith('/*', i): comment+=1; i+=2
            elif source.startswith('*/', i): comment-=1; i+=2
            else: i+=1
        elif quote:
            if source.startswith(quote, i):
                if quote in ("'", '"') and source.startswith(quote*2, i): i+=2
                else: i+=len(quote); quote=None
            else: i+=1
        elif source.startswith('--', i):
            newline=source.find('\n', i); i=len(source) if newline<0 else newline+1
        elif source.startswith('/*', i): comment=1; i+=2
        elif source[i] in "'\"": quote=source[i]; i+=1
        elif source[i]=='$' and (match:=re.match(r'\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$',source[i:])):
            quote=match[0]; i+=len(quote)
        elif source[i]==';':
            parts.append(source[start:i+1]); start=i+1; i+=1
        else: i+=1
    if quote or comment: raise Stop('SQL_BOUNDARY')
    tail=source[start:]
    if re.sub(r'--[^\n]*|/\*.*?\*/','',tail,flags=re.S).strip(): raise Stop('SQL_TERMINATOR')
    return parts


def validate_registration(body, revision, now=None):
    now=now or datetime.now(timezone.utc)
    value=json.loads(body)
    expected=dict(authority=AUTHORITY, controller=CONTROLLER,
                  risk_acceptance=mapping.RISK, roles=list(ROLE_NAMES),
                  endpoint='aws-0-eu-west-2.pooler.supabase.com:5432/postgres',
                  project='zcikcfgpblzuzpanpdqd', environment=mapping.ENVIRONMENT,
                  method='CLIENT_GENERATED_SCRAM_SHA_256_MEMORY_TO_PROTECTED_SECRET',
                  revision=revision, limits=LIMITS, retired_mapping_sha256=RETIRED_BINDING,
                  consumed_controller_sha256=CONSUMED_CONTROLLER_BINDING,
                  memory_enforcement='CGROUP_V2_FROM_EXEC_256M_SWAP_ZERO',
                  prior_audit_sha256=PRIOR_AUDIT_SHA256,
                  prior_supervised_seconds=PRIOR_SUPERVISED_SECONDS,
                  prior_export_reserved_bytes=PRIOR_EXPORT_RESERVED_BYTES,
                  prior_attempts=PRIOR_ATTEMPTS,prior_connections=PRIOR_CONNECTIONS,
                  prior_commands=PRIOR_COMMANDS,prior_db_active_seconds=PRIOR_DB_ACTIVE_SECONDS,
                  prior_returned_bytes=PRIOR_RETURNED_BYTES,
                  migration_flags=MIGRATION_FLAGS,expires_at=ORIGINAL_EXPIRY)
    if set(value)!=set(expected)|{'expires_at','hashes'} or any(value.get(k)!=v for k,v in expected.items()):
        raise Stop('EXACT_STORAGE_BINDING_REQUIRED')
    expiry=datetime.fromisoformat(value['expires_at'])
    if expiry.tzinfo is None or not now<expiry or (expiry-now).total_seconds()>86400:
        raise Stop('REGISTRATION_EXPIRY')
    if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision): raise Stop('REVISION')
    if set(value['hashes'])!=set(FILES): raise Stop('BOUND_FILES')
    for path, digest in value['hashes'].items():
        file=Path(path)
        if file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest()!=digest: raise Stop('CONTENT_CHANGED')
    return value


def mapping_binding(registration):
    # Same exact credential method and validation; controller binding is a
    # strict superset. Never accept the retired predecessor as an entrypoint.
    return {**{k:registration[k] for k in ('authority','risk_acceptance','roles','endpoint','project','environment','method','revision','expires_at')},
            'controller':mapping.CONTROLLER, 'limits':mapping.LIMITS,
            'hashes':{k:v for k,v in registration['hashes'].items() if k in (
                'verification/ingestion_storage/credential_mapping.py',
                'verification/ingestion_storage/tls_trust.py', str(MANIFEST),
                *(str(PACKAGE/f) for f in ('install.sql','activate.sql','revoke.sql','storage-readback.sql')))}}


@dataclass
class Budget:
    emit: object
    clock: object = time.monotonic
    started: float = field(default_factory=time.monotonic)
    phase: str = 'provisioning'
    phase_started: float = 0
    connections: int = PRIOR_CONNECTIONS
    commands: int = PRIOR_COMMANDS
    storage_commands: int = 0
    storage_connections: int = 0
    teardown_commands: int = 0
    active: float = PRIOR_DB_ACTIVE_SECONDS
    storage_active: float = 0
    teardown_active: float = 0
    returned_data_value_bytes: int = PRIOR_RETURNED_BYTES
    open_connections: int = 0

    def __post_init__(self): self.phase_started=self.started-PRIOR_SUPERVISED_SECONDS

    def check(self):
        elapsed=self.clock()-self.started
        # 2s of the TOTAL 240s is reserved for owned-process closure.
        ceiling={'provisioning':90,'storage':120,'teardown':28}[self.phase]
        if elapsed>=SUPERVISED_SECONDS-CLOSURE_SECONDS or self.clock()-self.phase_started>=ceiling: raise Stop('DEADLINE')
        if self.phase!='teardown' and elapsed>=210-PRIOR_SUPERVISED_SECONDS: raise Stop('TEARDOWN_RESERVE')

    def enter(self, phase):
        self.check(); self.phase=phase; self.phase_started=self.clock()
        self.emit('phase', dict(phase=phase))

    def snapshot(self):
        return dict(phase=self.phase, connections=self.connections, commands=self.commands,
                    storage_commands=self.storage_commands, storage_connections=self.storage_connections,
                    teardown_commands=self.teardown_commands, active_seconds=self.active,
                    storage_active_seconds=self.storage_active, teardown_active_seconds=self.teardown_active,
                    returned_database_data_value_bytes=self.returned_data_value_bytes,
                    elapsed_seconds=self.clock()-self.started,
                    cumulative_supervised_seconds=self.clock()-self.started+PRIOR_SUPERVISED_SECONDS,
                    open_connections=self.open_connections)

    def before(self, operation):
        self.check()
        if operation=='connect':
            if self.open_connections: raise Stop('CONNECTION_STACKING')
            limit=13 if self.phase=='teardown' else 12
            if self.connections>=limit: raise Stop('CONNECTION_LIMIT')
            if self.phase=='storage' and self.storage_connections>=8: raise Stop('STORAGE_CONNECTION_LIMIT')
            if self.phase=='provisioning' and self.connections>=4: raise Stop('PROVISION_CONNECTION_LIMIT')
            self.connections+=1
            if self.phase=='storage': self.storage_connections+=1
        else:
            if self.phase=='storage':
                if self.storage_commands>=40: raise Stop('STORAGE_COMMAND_LIMIT')
                self.storage_commands+=1
            if self.phase=='teardown':
                if self.teardown_commands>=10: raise Stop('TEARDOWN_COMMAND_LIMIT')
                self.teardown_commands+=1
            self.commands+=1
        self.emit('budget',self.snapshot())

    def duration(self, started):
        elapsed=self.clock()-started; self.active+=elapsed
        if self.phase=='storage':
            self.storage_active+=elapsed
            if self.storage_active>30: raise Stop('STORAGE_ACTIVE_LIMIT')
        if self.phase=='teardown':
            self.teardown_active+=elapsed
            if self.teardown_active>10: raise Stop('TEARDOWN_ACTIVE_LIMIT')
        self.check()

    def account(self, rows):
        # Serialized values only; never labelled wire/driver protocol bytes.
        size=len(canonical(rows)); self.returned_data_value_bytes+=size
        if size>32768 or self.returned_data_value_bytes>262144: raise Stop('DATABASE_RESULT_BOUND')


class Cursor:
    def __init__(self, native, budget): self.native=native; self.budget=budget
    def fetchone(self):
        value=self.native.fetchone(); self.budget.account(value); return value
    def fetchall(self):
        value=self.native.fetchall(); self.budget.account(value); return value


class Connection:
    """Count and fence every driver statement including helper-issued SQL."""
    def __init__(self, native, budget): self.native=native; self.budget=budget; self.credential_transaction=0
    @property
    def info(self): return self.native.info
    @property
    def pgconn(self): return self.native.pgconn
    def execute(self, statement, params=None):
        self.budget.before('command'); began=self.budget.clock()
        try: return Cursor(self.native.execute(statement,params),self.budget)
        finally: self.budget.duration(began)
    @contextmanager
    def transaction(self):
        # Existing credential helper reuses this facade: BEGIN/COMMIT are real
        # counted calls; uncertain COMMIT never gets an automatic ROLLBACK.
        if self.credential_transaction>=2: raise Stop('CREDENTIAL_TRANSACTION_BOUND')
        role=ROLE_NAMES[self.credential_transaction]; self.credential_transaction+=1
        self.budget.emit('effect_intent',dict(effect='credential_transaction',role=role))
        self.execute('BEGIN')
        try: yield self
        except BaseException:
            raise
        else:
            self.execute('COMMIT')
            self.budget.emit('effect_ack',dict(effect='credential_transaction',role=role))


def script(connection, name):
    result=None
    for statement in split_sql((PACKAGE/name).read_text()):
        result=connection.execute(statement)
    return result


def storage_identity(c, role):
    row=c.execute("""SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,
        rolreplication,rolbypassrls,rolconnlimit,
        (SELECT jsonb_agg(jsonb_build_array(r.rolname,m.admin_option,m.inherit_option,m.set_option) ORDER BY r.rolname)
         FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid WHERE m.member=p.oid)
        FROM pg_roles p WHERE rolname=current_user""").fetchone()
    capability='ingestion_worker' if role==ROLE_NAMES[0] else 'ingestion_storage_operator'
    if row!=(role,role,False,False,False,False,False,1,[[capability,False,True,False]]): raise Stop('RESTRICTED_IDENTITY')


def start_storage_transaction(c, role):
    # Session-scoped timeouts intentionally persist after COMMIT so subsequent
    # expected-denial probes are bounded. Three SETs + identity + BEGIN + fixed
    # function + COMMIT = 7, same reservation as six-command tx + identity.
    for setting in ("SET statement_timeout='10s'", "SET lock_timeout='3s'", "SET idle_in_transaction_session_timeout='10s'"):
        c.execute(setting)
    storage_identity(c,role)
    c.execute('BEGIN')


def readback(c, role, *, seeded, stopped):
    statements=split_sql((PACKAGE/'storage-readback.sql').read_text())
    result=None
    for statement in statements:
        cursor=c.execute(statement)
        if 'SELECT jsonb_build_object' in statement: result=cursor.fetchone()[0]
    if not isinstance(result,dict) or result['current_user']!=role or result['session_user']!=role: raise Stop('READBACK_IDENTITY')
    rows=result['rows']
    expected=sorted(json.loads(MANIFEST.read_text())['items'],key=lambda r:r['key'])
    actual=sorted([r for r in rows if r['key']!=CONTROL_KEY],key=lambda r:r['key'])
    if actual!=(expected if seeded else []): raise Stop('MANIFEST_READBACK')
    control=[r for r in rows if r['key']==CONTROL_KEY]
    if len(control)!=1 or len(rows)!=(4 if seeded else 1) or result['attempts']!=0: raise Stop('STORAGE_COUNTS')
    outcome={'global_stop':{'reason':'CONSUMED_SALFORD_GLOBAL_STOP','run':'38884069913'},'grants':{}}
    if stopped: outcome['manual_stop']='STORAGE_TEST_STOP'
    if control[0]['outcome']!=outcome: raise Stop('CONTROL_READBACK')
    if control[0]['state']!='CONTROL' or control[0]['authority'] is not None or control[0]['attempt_count']!=0: raise Stop('CONTROL_STATE')
    if not 0<result['serialized_bytes']<=32768 or not 0<result['physical_bytes']<=1048576: raise Stop('STORAGE_SIZE')
    return result


def deny(c, statement):
    import psycopg
    try: c.execute(statement)
    except psycopg.Error as exc:
        if exc.sqlstate!='42501': raise Stop('DENIAL_SQLSTATE') from None
    else: raise Stop('DENIAL_UNEXPECTED_SUCCESS')


def migration_gate(c, emit, name='postgres'):
    """One bounded catalogue read; safe identity/prerequisites precede effects."""
    import re
    row=c.execute("""SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,
        current_setting('server_version_num')::integer>=170000,
        has_schema_privilege(current_user,'public','CREATE WITH GRANT OPTION'),
        has_schema_privilege(current_user,'public','USAGE WITH GRANT OPTION'),
        has_database_privilege(current_user,current_database(),'CONNECT WITH GRANT OPTION'),
        NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN
          ('ingestion_storage_owner','ingestion_storage_operator','ingestion_worker',
           'ingestion_authority_issuer','ingestion_barrier_releaser','ingestion_worker_login','ingestion_storage_login')),
        to_regclass('public.ingestion_work_items') IS NULL AND
        to_regclass('public.ingestion_work_attempts') IS NULL AND
        to_regprocedure('public.ingestion_seed_storage_test()') IS NULL AND
        to_regprocedure('public.ingestion_raise_stop(text)') IS NULL
        FROM pg_roles WHERE rolname=current_user""").fetchone()
    fields=('current_user','session_user',*MIGRATION_FLAGS,
            'postgres17','schema_create_grant_option','schema_usage_grant_option',
            'database_connect_grant_option','role_names_unused','ledger_objects_absent')
    # Never serialize an unexpected arbitrary driver value or exception.
    shaped=isinstance(row,(tuple,list)) and len(row)==len(fields)
    identity={}
    for i,key in enumerate(fields):
        value=row[i] if shaped else None
        identity[key]=value if (i<2 and isinstance(value,str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,62}',value)) or (i>=2 and type(value) is bool) else None
    emit('migration_identity',identity)
    if not shaped or row[:2]!=(name,name) or any(type(row[i+2]) is not bool or row[i+2]!=value for i,value in enumerate(MIGRATION_FLAGS.values())):
        raise Stop('MIGRATION_IDENTITY')
    if any(value is not True for value in row[6:]):
        raise Stop('MIGRATION_PREREQUISITES')


def execute_sequence(connect, secret_operation, registration, emit, *, fault=None, clock=time.monotonic, migration_identity='postgres', aggregate_started=None):
    """Same coordinator in production and tests; injected transports are private.

    Production CLI never accepts transport hooks, fixture URLs or fault flags.
    Tests use non-superuser fixture logins and a fake protected-secret boundary.
    """
    budget=Budget(emit,clock=clock,started=clock() if aggregate_started is None else aggregate_started); credentials={}; open_native=None
    def event(name, payload): emit(name,payload)
    @contextmanager
    def connection(role):
        nonlocal open_native
        budget.before('connect'); began=clock()
        try:
            open_native=connect(role,credentials.get(role))
            budget.open_connections=1
            budget.duration(began)
            yield Connection(open_native,budget)
        finally:
            if open_native is not None:
                open_native.close()
                if not open_native.closed: raise Stop('CONNECTION_CLOSURE')
                open_native=None; budget.open_connections=0
                event('connection_closed',dict(role=role,**budget.snapshot()))
    def checkpoint(phase, state):
        event('checkpoint',{**budget.snapshot(),'phase':phase,'state':state})
        if fault: fault(phase,state)
    def external_secret(operation, name, value=None):
        budget.check(); event('effect_intent',dict(effect='secret_'+operation,name=name))
        secret_operation(operation,name,value)
        budget.check(); event('effect_ack',dict(effect='secret_'+operation,name=name))
    try:
        checkpoint('installation','INTENT')
        with connection('migration') as c:
            for setting in ("SET statement_timeout='10s'", "SET lock_timeout='3s'", "SET idle_in_transaction_session_timeout='10s'"):
                c.execute(setting)
            migration_gate(c,event,migration_identity)
            # Exact install.sql includes prerequisite/ownership gates and one
            # transaction. No writes precede its own reviewed preconditions.
            script(c,'install.sql')
        checkpoint('installation','COMMITTED')
        with connection('migration') as c:
            for setting in ("SET statement_timeout='10s'", "SET lock_timeout='3s'", "SET idle_in_transaction_session_timeout='10s'"):
                c.execute(setting)
            row=c.execute("""SELECT current_user,session_user,
                pg_has_role(current_user,'ingestion_storage_owner','USAGE'),
                pg_has_role(current_user,'ingestion_storage_owner','SET'),
                has_schema_privilege('ingestion_storage_owner','public','CREATE'),
                (SELECT count(*) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_storage_login') AND NOT rolcanlogin),
                (SELECT bool_and(admin_option AND NOT inherit_option AND NOT set_option) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user) AND roleid='ingestion_storage_owner'::regrole)
            """).fetchone()
            # Fixture principal differs only in the fixed disposable connector.
            if row[:2]!=(migration_identity,migration_identity) or row[2:]!=(False,False,False,2,True): raise Stop('INSTALL_COMMITTED_READBACK')
            checkpoint('installation_readback','VERIFIED')
            # Activation gates read-only before credential generation.
            gate=(PACKAGE/'activate.sql').read_text().split('ALTER ROLE ingestion_worker_login LOGIN;')[0].replace('BEGIN;','BEGIN READ ONLY;',1)+'ROLLBACK;'
            for statement in split_sql(gate): c.execute(statement)
            checkpoint('mapping','INTENT')
            def secret_runner(command, **kwargs):
                from types import SimpleNamespace
                name=command[3]
                uri=kwargs['input'].decode()
                role=next(r for r,n in mapping.MAPPINGS.items() if n==name)
                from urllib.parse import urlsplit,unquote
                # In-memory custody only; no secret values enter event payloads.
                credentials[role]=unquote(urlsplit(uri).password)
                external_secret('set',name,uri)
                return SimpleNamespace(returncode=0)
            receipts=mapping.install_mapping(c,risk_binding=mapping_binding(registration),
                                             revision=registration['revision'],runner=secret_runner)
            if len(receipts)!=2: raise Stop('MAPPING_RECEIPTS')
            checkpoint('mapping','MAPPED_NOLOGIN')
            checkpoint('activation','INTENT');script(c,'activate.sql')
        checkpoint('activation','COMMITTED')
        budget.enter('storage');checkpoint('storage','INTENT')
        with connection(ROLE_NAMES[1]) as c:
            start_storage_transaction(c,ROLE_NAMES[1])
            if c.execute('SELECT public.ingestion_seed_storage_test()').fetchone()!=(3,): raise Stop('SEED_RESULT')
            c.execute('COMMIT');checkpoint('first_seed','COMMITTED')
            for statement in ('BEGIN',"SET LOCAL statement_timeout='10s'","SET LOCAL lock_timeout='3s'","SET LOCAL idle_in_transaction_session_timeout='10s'"):
                c.execute(statement)
            if c.execute('SELECT public.ingestion_seed_storage_test()').fetchone()!=(3,): raise Stop('DUPLICATE_RESULT')
            c.execute('COMMIT');checkpoint('duplicate_seed','COMMITTED')
            deny(c,"SELECT public.ingestion_raise_stop('UNAUTHORISED')")
            deny(c,"UPDATE public.ingestion_work_items SET outcome='{}'")
        with connection(ROLE_NAMES[0]) as c:
            start_storage_transaction(c,ROLE_NAMES[0])
            c.execute("SELECT public.ingestion_raise_stop('STORAGE_TEST_STOP')");c.execute('COMMIT')
            for statement in ('SELECT public.ingestion_seed_storage_test()',
                              "UPDATE public.ingestion_work_items SET outcome='{}' WHERE key=repeat('0',64)",
                              "INSERT INTO public.ingestion_work_attempts(work_key) VALUES('x')",
                              'SET ROLE ingestion_storage_owner','SET ROLE ingestion_authority_issuer','SET ROLE ingestion_barrier_releaser'):
                deny(c,statement)
        readbacks=[]
        for role in ROLE_NAMES:
            with connection(role) as c: readbacks.append(readback(c,role,seeded=True,stopped=True))
        if readbacks[0]['rows']!=readbacks[1]['rows']: raise Stop('RECONNECTION_MISMATCH')
        if budget.storage_commands!=40: raise Stop('STORAGE_ACCOUNTING')
        event('storage_readback',dict(rows=readbacks[0]['rows'],attempts=0,executable_grants=0,
              serialized_bytes=readbacks[0]['serialized_bytes'],physical_bytes=readbacks[0]['physical_bytes'],denials=8,duplicate_seed='NO_OP'))
        checkpoint('storage','VERIFIED')
        budget.enter('teardown');checkpoint('revocation','INTENT')
        with connection('migration') as c:
            c.execute("SET statement_timeout='10s'")
            script(c,'revoke.sql')
            # No pg_authid access or verifier retrieval. Password NULL is proven
            # by the exact acknowledged revocation transaction; independent
            # catalogue readback proves NOLOGIN, no membership and no sessions.
            row=c.execute("""SELECT
                (SELECT count(*) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_storage_login') AND NOT rolcanlogin),
                (SELECT count(*) FROM pg_auth_members WHERE member IN ('ingestion_worker_login'::regrole,'ingestion_storage_login'::regrole)),
                (SELECT count(*) FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_storage_login'))
            """).fetchone()
            if row!=(2,0,0): raise Stop('TEARDOWN_READBACK')
        checkpoint('revocation','VERIFIED')
        for name in SECRETS: external_secret('delete',name)
        # Secret removal is checked separately, without reading secret values.
        event('effect_intent',dict(effect='secret_metadata_verify'))
        secret_operation('verify_absent',None,None)
        event('effect_ack',dict(effect='secret_metadata_verify'))
        checkpoint('teardown','VERIFIED')
        event('result',dict(status='STORAGE_SEQUENCE_VERIFIED_CLOSURE_PENDING',**budget.snapshot()))
        return budget
    except BaseException as exc:
        # No automatic replay, no finally-block DDL or secret compensation.
        # The journal's last intent/ack is authoritative for reconciliation.
        event('stop',dict(**safe_failure(exc),**budget.snapshot()))
        raise
    finally:
        credentials.clear()


class Journal:
    def __init__(self, root, registration_sha256):
        self.root=Path(root)
        # Fixed owner-local run directory is also the durable single-use latch.
        # A different path is not a new authority; CLI does not offer one.
        self.root.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root.mkdir(mode=0o700,exist_ok=False)
        self.stream=(self.root/'events.jsonl').open('xb',buffering=0)
        root_fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(root_fd)
        finally: os.close(root_fd)
        directory=os.open(self.root.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
        self.head='0'*64;self.sequence=0;self.bytes=0
        self.append('consumed',dict(registration_sha256=registration_sha256,authority=AUTHORITY))
    def append(self,event,payload):
        entry=dict(sequence=self.sequence,previous_sha256=self.head,event=event,payload=payload)
        digest=hashlib.sha256(canonical(entry)).hexdigest()
        line=canonical(dict(entry,sha256=digest))+b'\n'
        if len(line)>16384 or self.bytes+len(line)>2*1024**2-PRIOR_EXPORT_RESERVED_BYTES-32768: raise Stop('AUDIT_BOUND')
        self.stream.write(line);os.fsync(self.stream.fileno())
        self.head=digest;self.sequence+=1;self.bytes+=len(line)
    def close(self): self.stream.close()


def production_transport(raw, selected_address, root):
    import psycopg
    from .credential_mapping import validate_route
    u=validate_route(raw)
    if not isinstance(u.password,str) or not u.password: raise Stop('MIGRATION_PASSWORD_REQUIRED')
    def connect(role,password):
        login=u.username if role=='migration' else role+'.zcikcfgpblzuzpanpdqd'
        return psycopg.connect(host=u.host,hostaddr=selected_address,port=u.port,
            dbname=u.database,user=login,password=u.password if role=='migration' else password,
            sslmode='verify-full',sslrootcert=str(root),connect_timeout=3,
            prepare_threshold=None,autocommit=True)
    return connect


def metadata_command(command, seconds=10):
    """Bounded credential-free stdout only; never used for token retrieval."""
    import selectors
    env={**os.environ,'GH_HOST':'github.com','GH_DEBUG':'','GH_PROMPT_DISABLED':'1'}
    p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env)
    data=bytearray();start=time.monotonic();selector=selectors.DefaultSelector()
    selector.register(p.stdout,selectors.EVENT_READ)
    try:
        while selector.get_map():
            if time.monotonic()-start>=seconds: raise Stop('GITHUB_METADATA_TIMEOUT')
            for key,_ in selector.select(.025):
                chunk=os.read(key.fd,4096)
                if not chunk: selector.unregister(key.fileobj)
                else:
                    data.extend(chunk)
                    if len(data)>32768: raise Stop('GITHUB_METADATA_BOUND')
        code=p.wait(timeout=max(.01,seconds-(time.monotonic()-start)))
        if code: raise Stop('GITHUB_METADATA_ACCESS')
        return bytes(data)
    finally:
        selector.close();p.stdout.close()
        if p.poll() is None:p.kill()
        p.wait(timeout=1)


def production_secrets(operation,name,value):
    env={**os.environ,'GH_HOST':'github.com','GH_DEBUG':'','GH_PROMPT_DISABLED':'1'}
    if operation=='set':
        mapping.put_secret(name,value)
    elif operation=='delete':
        result=subprocess.run(['gh','secret','delete',name,'--repo',mapping.REPO,'--env',mapping.ENVIRONMENT],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,env=env)
        if result.returncode: raise Stop('SECRET_DELETE_UNCERTAIN')
    elif operation=='verify_absent':
        data=metadata_command(['gh','secret','list','--repo',mapping.REPO,'--env',mapping.ENVIRONMENT,'--json','name'],seconds=5)
        if set(SECRETS)&{r['name'] for r in json.loads(data)}: raise Stop('SECRET_REMAINS')
    else: raise Stop('SECRET_OPERATION')


def worker(pipe, raw, registration, aggregate_started):
    os.setsid()
    sys.dont_write_bytecode=True
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    # Audit belongs to parent; file payload writes are disabled in worker/gh.
    # Address-space reservation is not physical memory. Inherited cgroup-v2
    # limits, not RLIMIT_AS, constrain gh and every descendant together.
    for fd in (1,2):
        null=os.open(os.devnull,os.O_WRONLY);os.dup2(null,fd);os.close(null)
    baseline=owned_resources()
    def emit(event,payload):
        pipe.send_bytes(canonical(dict(event=event,payload=payload)))
        if pipe.recv_bytes(16)!=b'DURABLE': raise Stop('JOURNAL_ACK')
    try:
        emit('worker_ready',dict(pid=os.getpid()))
        began=aggregate_started
        emit('checkpoint',dict(phase='owner_access',state='INTENT'))
        local_preflight()
        emit('checkpoint',dict(phase='owner_access',state='VERIFIED'))
        u=mapping.validate_route(raw);root,_=verified_trust()
        answers=socket.getaddrinfo(u.host,u.port,family=socket.AF_INET,type=socket.SOCK_STREAM)
        if not answers or len(answers)>32: raise Stop('DNS_BOUND')
        selected=sorted({a[4][0] for a in answers})[0]
        emit('route',dict(host=u.host,port=u.port,database=u.database,selected_address=selected,tls='verify-full'))
        execute_sequence(production_transport(raw,selected,root),production_secrets,registration,emit,aggregate_started=aggregate_started)
        after=owned_resources()
        if after['socket_fds']-baseline['socket_fds'] or after['children']: raise Stop('CLEANUP_UNCERTAIN')
        emit('worker_closed',dict(cleanup='CLOSED',new_socket_fds=0,live_children=0,dns_and_execution_seconds=time.monotonic()-began))
    except BaseException as exc:
        try: emit('worker_failed',dict(**safe_failure(exc),cleanup='UNCERTAIN'))
        except BaseException: pass
        raise SystemExit(1) from None
    finally: pipe.close()


def _contained_worker(group, pipe, raw, registration, started):
    try:
        group.enter()
    except BaseException:
        pipe.close()
        raise SystemExit(1) from None
    worker(pipe, raw, registration, started)


def supervise(raw, registration, journal):
    import psutil
    # Fork keeps the credential off argv/env/files and avoids pickling to disk.
    parent,child=multiprocessing.get_context('fork').Pipe(duplex=True)
    started=time.monotonic()
    group=None;p=None;seen={};peak=0;closed=False;accepted=False;reason=None;phase='provisioning';phase_started=started-PRIOR_SUPERVISED_SECONDS
    try:
        group=WorkerMemory.create()
        journal.append('memory_enforcement',dict(kind='CGROUP_V2',memory_max=256*1024**2,swap_max=0,oom_group=1))
        p=multiprocessing.get_context('fork').Process(target=_contained_worker,args=(group,child,raw,registration,started))
        p.start();child.close()
        while p.is_alive() or parent.poll():
            elapsed=time.monotonic()-started
            if elapsed>=SUPERVISED_SECONDS-CLOSURE_SECONDS: raise Stop('SUPERVISED_DEADLINE')
            if time.monotonic()-phase_started>={'provisioning':90,'storage':120,'teardown':28}[phase]: raise Stop('PHASE_DEADLINE')
            if (journal.root/'STOP').exists(): raise Stop('OWNER_STOP')
            memory=group.snapshot()
            if any(memory[k] for k in ('kernel_memory_max_events','kernel_memory_oom','kernel_memory_oom_kill','outer_memory_max_events','outer_memory_oom','outer_memory_oom_kill')):
                raise Stop('KERNEL_MEMORY_LIMIT')
            try:
                process=psutil.Process(p.pid)
                owned=[process]+process.children(recursive=True)
            except psutil.NoSuchProcess:
                if p.is_alive(): raise Stop('PROCESS_ACCOUNTING')
                owned=[]
            rss=0
            for item in owned:
                try:
                    seen[item.pid]=item.create_time()
                    if item.status()!=psutil.STATUS_ZOMBIE: rss+=item.memory_info().rss
                except psutil.NoSuchProcess: pass
            peak=max(peak,rss)
            if rss>256*1024**2: raise Stop('OWNED_RSS_LIMIT')
            if parent.poll(.025):
                try: message=json.loads(parent.recv_bytes(16384))
                except EOFError: break
                if set(message)!={'event','payload'}: raise Stop('AUDIT_PROTOCOL')
                event=message['event'];payload=message['payload']
                journal.append(event,payload)
                if event=='phase': phase=payload['phase'];phase_started=time.monotonic()
                if event=='result': accepted=payload['status']=='STORAGE_SEQUENCE_VERIFIED_CLOSURE_PENDING'
                if event=='worker_closed': closed=payload['cleanup']=='CLOSED'
                if event=='worker_failed': reason=payload['reason']
                parent.send_bytes(b'DURABLE')
    except BaseException as exc:
        reason=safe_failure(exc)['reason']
    finally:
        # Session/process ownership is checked before group signals. Never
        # touch an unrelated process or the owner's keyring daemon.
        if p is not None and p.pid is not None and closed and accepted and not reason: p.join(timeout=min(.2,max(0,SUPERVISED_SECONDS-(time.monotonic()-started))))
        if p is not None and p.pid is not None and p.is_alive():
            try:
                if os.getpgid(p.pid)==p.pid: os.killpg(p.pid,signal.SIGTERM)
                else: p.terminate()
            except ProcessLookupError: pass
        if p is not None and p.pid is not None: p.join(timeout=min(1,max(0,SUPERVISED_SECONDS-(time.monotonic()-started))))
        for pid,born in seen.items():
            try:
                proc=psutil.Process(pid)
                if proc.create_time()==born and proc.status()!=psutil.STATUS_ZOMBIE:
                    proc.kill()
                    reason=reason or 'OWNED_PROCESS_REQUIRED_KILL'
            except psutil.NoSuchProcess: pass
            except Exception: reason='CLEANUP_UNCERTAIN'
        if p is not None and p.pid is not None: p.join(timeout=min(.5,max(0,SUPERVISED_SECONDS-(time.monotonic()-started))))
        survivors=[]
        for pid,born in seen.items():
            try:
                proc=psutil.Process(pid)
                if proc.create_time()==born and proc.status()!=psutil.STATUS_ZOMBIE: survivors.append(pid)
            except psutil.NoSuchProcess: pass
            except Exception: reason='CLEANUP_UNCERTAIN'
        try:
            for item in psutil.process_iter(['pid','status']):
                try:
                    if item.info['status']!=psutil.STATUS_ZOMBIE and p is not None and p.pid is not None and os.getpgid(item.pid)==p.pid:
                        item.kill();survivors.append(item.pid);reason='UNEXPECTED_OWNED_PROCESS'
                except (ProcessLookupError,psutil.NoSuchProcess): pass
        except Exception: reason='CLEANUP_UNCERTAIN'
        memory={}
        try:
            if group is not None: memory=group.close(started+SUPERVISED_SECONDS)
            if any(memory.get(k) for k in ('kernel_memory_max_events','kernel_memory_oom','kernel_memory_oom_kill','outer_memory_max_events','outer_memory_oom','outer_memory_oom_kill')):
                reason='KERNEL_MEMORY_LIMIT'
            if memory.get('kernel_memory_forced_cleanup'): reason=reason or 'OWNED_PROCESS_REQUIRED_KILL'
            if memory.get('kernel_memory_accounting_uncertain'): reason='MEMORY_CLEANUP_UNCERTAIN'
        except BaseException: reason='MEMORY_CLEANUP_UNCERTAIN'
        parent.close();child.close()
        elapsed=time.monotonic()-started
        passed=accepted and closed and p is not None and p.exitcode==0 and not reason and not survivors and elapsed<=SUPERVISED_SECONDS
        result=dict(status='STORAGE_ACCEPTED_ACCESS_DISABLED' if passed else 'STOP_RECONCILE_NO_RETRY',
                    worker_exit=p.exitcode if p is not None else None,elapsed_seconds=elapsed,peak_owned_rss_bytes=peak,
                    cumulative_supervised_seconds=elapsed+PRIOR_SUPERVISED_SECONDS,
                    live_owned_survivors=len(survivors),cleanup='CLOSED' if passed else 'UNCERTAIN',
                    reason=reason,audit_prefix_bytes=journal.bytes,**memory)
        journal.append('supervisor_result',result)
        result.update(audit_bytes=journal.bytes,audit_chain_head=journal.head,
                      audit_sha256=hashlib.sha256((journal.root/'events.jsonl').read_bytes()).hexdigest())
        return result


def local_preflight():
    """Existing owner authentication/secret metadata only; no DB calls."""
    env={**os.environ,'GH_HOST':'github.com','GH_DEBUG':'','GH_PROMPT_DISABLED':'1'}
    if any(os.environ.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_DEBUG')): raise Stop('KEYRING_AUTH_REQUIRED')
    if any(os.environ.get(k) for k in ('PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGPASSFILE','PGPASSWORD','PGSSLCERT','PGSSLKEY')): raise Stop('LIBPQ_ENVIRONMENT_OVERRIDE')
    commands=[(['gh','api','user','--jq','.login'],lambda b:b.strip()==b'maxrose26'),
              (['gh','api','--paginate','repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets','--jq','.secrets[].name'],
               lambda b:not set(SECRETS)&set(b.decode().splitlines()))]
    for command,valid in commands:
        data=metadata_command(command)
        if not valid(data): raise Stop('OWNER_ACCESS_OR_PREEXISTING_SECRET')
    # Read access to secret metadata is NOT described as proof of write access.


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--authority',required=True)
    parser.add_argument('--revision',required=True)
    parser.add_argument('--binding',type=Path,required=True)
    parser.add_argument('--binding-sha256',required=True)
    parser.add_argument('--accept-verifier-retention',action='store_true')
    args=parser.parse_args()
    try:
        if args.authority!=AUTHORITY or not args.accept_verifier_retention: raise Stop('OWNER_AUTHORITY')
        if sys.platform!='linux' or not sys.stdin.isatty() or not sys.stderr.isatty(): raise Stop('OWNER_SECURE_TTY_REQUIRED')
        if args.binding.is_symlink() or args.binding.stat().st_size>16384: raise Stop('REGISTRATION_BOUND')
        body=args.binding.read_bytes()
        if hashlib.sha256(body).hexdigest()!=args.binding_sha256: raise Stop('REGISTRATION_HASH')
        registration=validate_registration(body,args.revision)
        if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=args.revision or subprocess.check_output(['git','status','--porcelain'],text=True).strip(): raise Stop('CLEAN_EXACT_CHECKOUT_REQUIRED')
        verified_trust()
        if int(Path('/proc/self/stat').read_text().split(' ',1)[0])!=os.getpid(): raise Stop('PROCESS_NAMESPACE_UNSUPPORTED')
        # Availability is checked before credential entry or authority use.
        owner_scope()
        for attempt in PRIOR_ATTEMPTS:
            prior=Path.home()/'.local/state/propertyaigent'/attempt['directory']/'events.jsonl'
            if prior.is_symlink() or prior.stat().st_size!=attempt['bytes'] or hashlib.sha256(prior.read_bytes()).hexdigest()!=attempt['sha256']:
                raise Stop('PRIOR_ATTEMPT_EVIDENCE_REQUIRED')
        root=Path.home()/'.local/state/propertyaigent/storage-acceptance-identity-successor-20261017'
        journal=Journal(root,args.binding_sha256)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        try:
            raw=mapping.secure_migration_input()
            # Recheck expiry after unbounded human input; no DB effect on expiry.
            validate_registration(body,args.revision)
            mapping.validate_route(raw)
            result=supervise(raw,registration,journal)
            del raw
            print(json.dumps(result,sort_keys=True))
            print('Credential-free audit:',root/'events.jsonl')
            raise SystemExit(0 if result['status']=='STORAGE_ACCEPTED_ACCESS_DISABLED' else 1)
        finally: journal.close()
    except SystemExit: raise
    except BaseException:
        print('STORAGE_CONTROLLER_STOP_RECONCILE_NO_RETRY',file=sys.stderr)
        raise SystemExit(1) from None

if __name__=='__main__': main()
