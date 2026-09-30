"""Process-local authority for runner-owned PostgreSQL only. No production opt-in.

The runner/OS owner is trusted; this prevents accidental target/configuration
mistakes. It is not a sandbox against malicious Python or the machine's root.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
from weakref import WeakKeyDictionary
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import URL

DENIED = 'AH PostgreSQL runtime/schema verification pending; migration remains disabled outside the attested disposable local database'
_REGISTRY = WeakKeyDictionary()


@dataclass
class _Authority:
    manifest: dict
    signature: str | None = None


def _deny(message):
    raise ValueError('AH disposable PostgreSQL: ' + message)


def private_json(path):
    path = Path(path)
    if path.is_symlink():
        _deny('symlink proof')
    st = path.stat()
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600:
        _deny('proof ownership/mode')
    return json.loads(path.read_text())


def filesystem_proof(m):
    if os.getuid() == 0:
        _deny('root application process')
    if not re.fullmatch('[0-9a-f]{32}', m.get('run_id', '')):
        _deny('run identity')
    root = Path(m['root'])
    if root.is_symlink() or root.resolve() != root or stat.S_IMODE(root.stat().st_mode) != 0o700 or root.stat().st_uid != os.getuid():
        _deny('run directory')
    marker = private_json(root/'cluster.json')
    keys = ('run_id', 'root', 'system_identifier', 'port', 'host_netns', 'netns', 'server_start', 'server_pid')
    if any(m[k] != marker[k] for k in keys):
        _deny('cluster marker mismatch')
    ns = os.readlink('/proc/self/ns/net')
    if ns != m['netns'] or ns == m['host_netns'] or set(os.listdir('/sys/class/net')) != {'lo'}:
        _deny('network isolation mismatch')
    pid = (root/'pgdata/postmaster.pid').read_text().splitlines()
    if int(pid[0]) != m['server_pid'] or Path(pid[1]).resolve() != root/'pgdata' or int(pid[2]) != m['server_start'] or int(pid[3]) != m['port']:
        _deny('postmaster identity mismatch')
    proc = Path('/proc')/pid[0]
    if proc.stat().st_uid != os.getuid() or os.readlink(proc/'ns/net') != ns:
        _deny('postmaster owner/namespace')
    args = (proc/'cmdline').read_bytes().split(b'\0')
    if b'-D' not in args or args[args.index(b'-D')+1].decode() != str(root/'pgdata'):
        _deny('postmaster data directory')


def connection_proof(conn, m):
    filesystem_proof(m)
    row = conn.execute(text("""SELECT current_database() AS database,
        (SELECT oid FROM pg_database WHERE datname=current_database()) AS database_oid,
        current_user AS username, session_user AS session_user,
        inet_server_addr()::text AS host, inet_server_port() AS port,
        (SELECT system_identifier::text FROM pg_control_system()) AS system_identifier,
        floor(extract(epoch FROM pg_postmaster_start_time()))::bigint AS server_start,
        current_schema() AS schema, current_setting('search_path') AS search_path,
        r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolreplication, r.rolbypassrls,
        EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS memberships
        FROM pg_roles r WHERE rolname=current_user""")).mappings().one()
    expected = dict(database=m['database'],database_oid=m['database_oid'],username=m['role'],session_user=m['role'],
                    host='127.0.0.1/32',port=m['port'],system_identifier=m['system_identifier'],server_start=m['server_start'],
                    schema='public',search_path='public')
    if any(row[k] != v for k,v in expected.items()) or any(row[k] for k in ('rolsuper','rolcreatedb','rolcreaterole','rolreplication','rolbypassrls','memberships')):
        _deny('server/database/restricted-role mismatch')


def require_engine(engine):
    try:
        authority = _REGISTRY.get(engine)
    except TypeError:
        authority = None
    if authority is None:
        raise ValueError(DENIED)
    filesystem_proof(authority.manifest)
    return authority


def require_connection(conn):
    a = require_engine(conn.engine)
    connection_proof(conn, a.manifest)
    return a


def create_disposable_engine(manifest_path):
    m = private_json(manifest_path)
    filesystem_proof(m)
    if not re.fullmatch('ah_case_[0-9a-f]{32}', m['database']) or m['role'] != 'ah_writer_' + m['run_id'][:16]:
        _deny('case database/role name')
    engine = create_engine(URL.create('postgresql+psycopg',username=m['role'],host='127.0.0.1',port=m['port'],database=m['database']),
        connect_args={'connect_timeout':5,'options':'-csearch_path=public'},pool_size=4,max_overflow=0)
    try:
        with engine.connect() as conn:
            connection_proof(conn,m)  # Only SELECTs before admission; no schema write.
        _REGISTRY[engine] = _Authority(m)
        event.listen(engine,'engine_disposed',lambda e: _REGISTRY.pop(e,None))
        return engine
    except BaseException:
        engine.dispose()
        raise


def catalog_signature(conn):
    """Server-canonical definitions; excludes data/sequence current values."""
    queries = [
      """SELECT c.relname,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
        pg_get_expr(d.adbin,d.adrelid),a.attidentity,a.attgenerated
        FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE n.nspname='public' AND c.relname IN ('ah_source_claims','ah_claim_events') AND a.attnum>0 AND NOT a.attisdropped
        ORDER BY c.relname,a.attnum""",
      """SELECT c.relname,k.conname,k.contype,k.convalidated,k.condeferrable,k.condeferred,pg_get_constraintdef(k.oid,true)
        FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname IN ('ah_source_claims','ah_claim_events') ORDER BY c.relname,k.conname""",
      """SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public'
        AND tablename IN ('ah_source_claims','ah_claim_events') ORDER BY tablename,indexname""",
      """SELECT c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid,true)
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname IN ('ah_source_claims','ah_claim_events') AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""",
      """SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.proname='ah_deny_mutation' ORDER BY p.oid""",
      """SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,pg_get_userbyid(c.relowner)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
        AND c.relname IN ('ah_source_claims','ah_claim_events') ORDER BY c.relname""",
    ]
    return json.dumps([[list(row) for row in conn.execute(text(q))] for q in queries],default=str)


def verify_postgres(conn):
    a = require_connection(conn)
    if a.signature is None or catalog_signature(conn) != a.signature:
        _deny('missing or changed creation-attested schema')


def attest_created_schema(conn):
    """Called only after successful canonical table/trigger creation, before commit."""
    from app.db.ah_claim_schema import TABLES, Check, UniqueConstraint
    from sqlalchemy import inspect
    a = require_connection(conn)
    if a.signature is not None:
        _deny('schema already attested')
    ins = inspect(conn)
    for table in TABLES:
        cols=ins.get_columns(table.name)
        if [c['name'] for c in cols] != list(table.c.keys()):
            _deny('column inventory')
        for actual,expected in zip(cols,table.columns):
            if str(actual['type'].compile(dialect=conn.dialect)) != str(expected.type.compile(dialect=conn.dialect)) or actual['nullable'] != expected.nullable:
                _deny('column type/nullability')
        if ins.get_pk_constraint(table.name)['constrained_columns'] != ['id']:
            _deny('primary key')
        if {tuple(u['column_names']) for u in ins.get_unique_constraints(table.name)} != {tuple(c.name for c in u.columns) for u in table.constraints if isinstance(u,UniqueConstraint)}:
            _deny('unique constraints')
        if {c['name'] for c in ins.get_check_constraints(table.name)} != {c.name for c in table.constraints if isinstance(c,Check) and not str(c.name).startswith('ah_bool_')}:
            _deny('check inventory')
        fks={(tuple(f['constrained_columns']),f['referred_table'],tuple(f['referred_columns']),f.get('options',{}).get('ondelete')) for f in ins.get_foreign_keys(table.name)}
        expected_fks={(tuple(c.name for c in f.columns),f.elements[0].column.table.name,tuple(e.column.name for e in f.elements),'RESTRICT') for f in table.foreign_key_constraints}
        if fks != expected_fks:
            _deny('foreign keys')
        if {(i['name'],tuple(i['column_names']),bool(i['unique'])) for i in ins.get_indexes(table.name) if not i.get('duplicates_constraint')} != {(i.name,tuple(c.name for c in i.columns),i.unique) for i in table.indexes}:
            _deny('indexes')
    triggers=conn.execute(text("""SELECT c.relname,t.tgname,t.tgtype,t.tgenabled,p.proname,p.prosrc,p.prosecdef
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_proc p ON p.oid=t.tgfoid WHERE n.nspname='public'
        AND c.relname IN ('ah_source_claims','ah_claim_events') AND NOT t.tgisinternal""")).all()
    # BEFORE (2), DELETE (8), UPDATE (16), TRUNCATE (32), statement-level (no ROW bit).
    expected={(t.name,t.name+'_deny_mutation',58,'O','ah_deny_mutation',"BEGIN RAISE EXCEPTION 'AH history is append-only'; END;",False) for t in TABLES}
    if {tuple(list(r[:5])+[r[5].strip(),r[6]]) for r in triggers} != expected:
        _deny('append-only function/trigger semantics')
    a.signature=catalog_signature(conn)
