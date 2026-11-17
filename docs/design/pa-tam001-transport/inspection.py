import ast, hashlib, io, json, os, signal, sys, time, uuid
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path

# REVIEW ONLY: first approval consumed; fresh explicit owner authorisation required.
# Before any newly authorised execution, reconcile #214/#227 and active operators.
# No installer, download, journal, dispatcher, grant, source request or retry.
SERVICE = 'srv-d9qbl7qjnfac73d8nieg'
DEPLOY = '2fa0f07cfdfb56a27243ebff18110d441f9da04d'
PIN = 'f027ba28af69ae70208eab5ed047e4a8a81c6337'
CLASS_SHA = '4959d79558bd5c4a5aabb8ec6c5dd6f05c02720c23bcefa9bf6985507673b36f'
started = time.monotonic()
c = None
out = dict(scope='PA-TAM001 v1.0', prior_approval='CONSUMED',
    execution_authorisation='SEPARATE_EXPLICIT_OWNER_AUTHORISATION_REQUIRED',
    execution_id=str(uuid.uuid4()),
    started_at=datetime.now(timezone.utc).isoformat(), service=SERVICE,
    expected_deployed_revision=DEPLOY, adapter_reference=PIN, adapter_class_sha256=CLASS_SHA,
    status='NOT_EXECUTED', phase='LOCAL_PREFLIGHT', connections_attempted=0,
    connections_opened=0, statements_attempted=0, statements_completed=0,
    returned_value_bytes=0, observations={}, unknowns={}, database_writes=0,
    controller_validated=False, identity_validated=False,
    transaction='NOT_STARTED', rollback_attempted=False, rollback_acknowledged=False,
    connection_closed=None,
    containment='NOT_ESTABLISHED', operational_authority=False)

class Refusal(Exception): pass
def require(ok, code):
    if not ok: raise Refusal(code)
ESSENTIAL = ('identity','roles','memberships','owner_effective_membership',
    'schema','tables','functions','restricted_execute','sessions',
    'controller','current_grants','unresolved_work')
FUNCTIONS = ('ingestion_intake_evidence_write','ingestion_intake_evidence_read',
    'ingestion_intake_owner_state','ingestion_register_campaign_once')

def validate_controller(rows):
    require(len(rows)==1, 'CONTROLLER_RECORD_COUNT_INVALID')
    row = rows[0]
    require(isinstance(row,dict) and row.get('structure_valid') is True,
            'CONTROLLER_STRUCTURE_INVALID')
    require(type(row.get('generation')) is int and row['generation']>=0,
            'CONTROLLER_GENERATION_INVALID')
    require(all(type(row.get(k)) is bool for k in
        ('global_stop_set','manual_stop_set','has_stop_history','has_intake_run')),
        'CONTROLLER_STOP_EVIDENCE_INVALID')
    digest = row.get('controller_sha256')
    require(isinstance(digest,str) and len(digest)==64 and
            all(ch in '0123456789abcdef' for ch in digest), 'CONTROLLER_FINGERPRINT_INVALID')

def finish_receipt(receipt):
    observations = receipt['observations']
    unknowns = receipt['unknowns']
    for name in ESSENTIAL:
        if name not in observations:
            unknowns.setdefault(name,'NOT_OBSERVED')
    required_roles = ('postgres','ingestion_storage_owner','ingestion_worker',
        'ingestion_worker_login','ingestion_effect_login',
        'ingestion_recovery_operator','ingestion_barrier_releaser')
    for name in required_roles:
        if sum(r.get('rolname')==name for r in observations.get('roles',[]))!=1:
            unknowns.setdefault('roles','REQUIRED_ROLE_PERMISSION_EVIDENCE_INCOMPLETE')
    for name in ('ingestion_storage_owner','ingestion_recovery_operator','ingestion_barrier_releaser'):
        rows = [r for r in observations.get('owner_effective_membership',[]) if r.get('rolname')==name]
        if len(rows)!=1 or any(type(rows[0].get(k)) is not bool for k in ('inherited','can_set')):
            unknowns.setdefault('owner_effective_membership','EFFECTIVE_MEMBERSHIP_UNKNOWN')
    for name in FUNCTIONS:
        if sum(f.get('name')==name for f in observations.get('functions',[]))!=1:
            unknowns.setdefault('functions','REQUIRED_FUNCTION_ABSENT_OR_AMBIGUOUS')
    schema = observations.get('schema',[])
    if len(schema)!=1 or schema[0].get('usage') is not True:
        unknowns.setdefault('schema','PUBLIC_SCHEMA_USAGE_NOT_ESTABLISHED')
    for name in ('ingestion_work_items','ingestion_work_attempts','ingestion_run_evidence'):
        rows = [r for r in observations.get('tables',[]) if r.get('relname')==name]
        if len(rows)!=1 or any(type(rows[0].get(k)) is not bool for k in ('can_select','can_update')):
            unknowns.setdefault('tables','REQUIRED_TABLE_PERMISSION_EVIDENCE_INCOMPLETE')
    grants = observations.get('current_grants',[])
    if len(grants)!=1 or grants[0].get('unknown_expiry')!=0:
        unknowns.setdefault('current_grants','GRANT_EXPIRY_EVIDENCE_UNKNOWN')
    for role in ('ingestion_worker','ingestion_worker_login','ingestion_effect_login'):
        for name in (FUNCTIONS[0],FUNCTIONS[1],FUNCTIONS[3]):
            rows = [r for r in observations.get('restricted_execute',[])
                if r.get('rolname')==role and r.get('name')==name]
            if len(rows)!=1 or type(rows[0].get('can_execute')) is not bool:
                unknowns.setdefault('restricted_execute','REQUIRED_EXECUTE_PERMISSION_UNKNOWN')
    if not receipt['identity_validated']:
        unknowns.setdefault('identity','NOT_VALIDATED')
    if not receipt['controller_validated']:
        unknowns.setdefault('controller','NOT_VALIDATED_STOP_STATE_UNKNOWN')
    if receipt['connection_closed'] is not True:
        unknowns.setdefault('connection_close','NOT_VERIFIED')
    if receipt['transaction']!='ROLLED_BACK' or not receipt['rollback_acknowledged']:
        unknowns.setdefault('transaction_end','ROLLBACK_NOT_ACKNOWLEDGED')
    complete = not unknowns and 'reason' not in receipt
    receipt['inspection'] = ('COMPLETED' if complete else
        'PARTIAL' if observations else 'REFUSED')
    receipt['status'] = ('COMPLETED_READ_ONLY_INSPECTION_REVIEW_REQUIRED' if complete else
        'STOP_INCOMPLETE_NO_RETRY' if observations else 'STOP_REFUSED_NO_RETRY')
    receipt['missing_observations'] = [name for name in ESSENTIAL if name in unknowns]

def deadline(*_): raise Refusal('TIME_LIMIT_STOP_RECONCILE_NO_RETRY')
signal.signal(signal.SIGALRM, deadline)
signal.signal(signal.SIGTERM, deadline)
signal.setitimer(signal.ITIMER_REAL, 45)

def execute(sql, *, cleanup=False):
    require(not cleanup or sql=='ROLLBACK', 'CLEANUP_ROLLBACK_ONLY')
    require(out['statements_attempted'] < (20 if cleanup else 19), 'STATEMENT_LIMIT')
    require(time.monotonic()-started < (52 if cleanup else 45), 'TIME_LIMIT')
    out['statements_attempted'] += 1
    cursor = c.execute(sql)
    out['statements_completed'] += 1
    return cursor

def rollback_and_close():
    try:
        if out['transaction']!='NOT_STARTED' and not c.closed:
            out['rollback_attempted'] = True
            cursor = execute('ROLLBACK', cleanup=True)
            require(cursor.statusmessage=='ROLLBACK' and
                    c.info.transaction_status.name=='IDLE', 'ROLLBACK_ACK_UNVERIFIED')
            out['rollback_acknowledged'] = True
            out['transaction'] = 'ROLLED_BACK'
    except BaseException:
        out['unknowns']['transaction_end'] = 'ROLLBACK_NOT_ACKNOWLEDGED_NO_RETRY'
    finally:
        try:
            c.close()
            out['connection_closed'] = bool(c.closed)
        except BaseException:
            out['connection_closed'] = False
        if out['connection_closed'] is not True:
            out['unknowns']['connection_close'] = 'NOT_VERIFIED'

def observe(name, sql):
    # Each SELECT returns one text cell <=3 KiB, enforced BEFORE network return.
    # At most 40 rows are disclosed; a 41st row causes a fail-closed refusal.
    require(sql.split(None,1)[0]=='SELECT' and ';' not in sql, 'SELECT_ONLY')
    wrapped = """SELECT CASE WHEN n > 40 OR octet_length(payload) > 3072
      THEN '{"bounded_refusal":true}' ELSE payload END
      FROM (SELECT count(*) AS n,coalesce(jsonb_agg(to_jsonb(q)),'[]'::jsonb)::text AS payload
      FROM (""" + sql + " LIMIT 41) q) bounded"
    out['phase'] = name
    raw = execute(wrapped).fetchone()[0]
    size = len(raw.encode('utf-8'))
    out['returned_value_bytes'] += size
    require(size <= 3072 and out['returned_value_bytes'] <= 65536, 'RESULT_LIMIT')
    value = json.loads(raw)
    require(isinstance(value, list), 'RESULT_BOUND_STOP_RECONCILE')
    out['observations'][name] = value
    return value

try:
    require(os.environ.get('RENDER_SERVICE_ID') == SERVICE, 'SERVICE_MISMATCH')
    require(os.environ.get('RENDER_GIT_COMMIT') == DEPLOY, 'DEPLOYMENT_DRIFT')
    require(bool(os.environ.get('DATABASE_URL')), 'DATABASE_CONFIGURATION_ABSENT')
    pins = {
      'verification/ingestion_storage/owner_pilot.py':'c5412249c9c42979425f518ad6e2827222e936c5',
      'verification/ingestion_storage/intake_owner.py':'cc41273779102e3fd57359e98e2717db5211e3a5',
      'verification/ingestion_storage/tls_trust.py':'f08d8647a2b740facaa7614d8cf7466fc379cc8a',
      'verification/ingestion_storage/trust/supabase-prod-ca-2021.crt':'3d693669b23c340c57a3457bdc8b6fefe1806cc5'}
    for name, expected in pins.items():
        p = Path(name)
        require(p.is_file() and not p.is_symlink(), 'SOURCE_OR_CA_ABSENT')
        raw = p.read_bytes()
        require(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==expected,
                'SOURCE_OR_CA_DRIFT')
    source = Path('verification/ingestion_storage/owner_pilot.py').read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Database')
    require(hashlib.sha256(ast.get_source_segment(source,node).encode()).hexdigest()==CLASS_SHA,
            'FROZEN_DATABASE_CLASS_DRIFT')
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        from verification.ingestion_storage.owner_pilot import Database
    require(Path(sys.modules[Database.__module__].__file__).resolve()==
            Path('verification/ingestion_storage/owner_pilot.py').resolve(), 'IMPORT_PATH_DRIFT')
    out['deployed_revision_verified'] = DEPLOY
    out['phase'] = 'CONFIGURATION_DNS_TLS_CONNECT'
    db = Database()
    out['connections_attempted'] = 1
    with db.connection() as c:
        out['connections_opened'] = 1
        # Prevent unnoticed protocol notices (which can contain server detail).
        c.add_notice_handler(lambda diagnostic: None)
        try:
            out['transaction'] = 'BEGIN_PENDING'
            execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            out['transaction'] = 'READ_ONLY'
            out['phase'] = 'TRANSACTION_LOCAL_TIMEOUTS'
            execute("SET LOCAL statement_timeout = '10s'")
            execute("SET LOCAL lock_timeout = '3s'")
            execute('SET LOCAL search_path = pg_catalog')
            identity_rows = observe('identity', """SELECT current_database() AS database,
              session_user::text,current_user::text,pg_backend_pid() AS backend_pid,
              clock_timestamp() AS observed_at,current_setting('server_version_num') AS server_version,
              current_setting('transaction_read_only') AS read_only,
              current_setting('statement_timeout') AS statement_timeout,
              current_setting('lock_timeout') AS lock_timeout,
              r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,
              pg_has_role(current_user,'pg_read_all_stats','USAGE') AS read_all_stats
              FROM pg_catalog.pg_roles r WHERE r.rolname=current_user""")
            require(len(identity_rows)==1, 'OWNER_IDENTITY_RECORD_COUNT_INVALID')
            identity = identity_rows[0]
            require(identity['read_only']=='on' and identity['statement_timeout']=='10s'
                    and identity['lock_timeout']=='3s', 'TIMEOUT_OR_READ_ONLY_DRIFT')
            require(identity['database']=='postgres' and identity['session_user']=='postgres'
              and identity['current_user']=='postgres' and not identity['rolsuper']
              and all(identity[k] for k in ('rolcreaterole','rolcreatedb','rolbypassrls')),
              'OWNER_IDENTITY_MISMATCH')
            require(int(identity['server_version'])>=160000, 'MEMBERSHIP_CATALOG_VERSION')
            out['identity_validated'] = True
            if identity.get('read_all_stats') is not True:
                out['unknowns']['sessions'] = 'INSUFFICIENT_SESSION_VISIBILITY_PERMISSION'
            observe('roles', """SELECT rolname,rolcanlogin,rolsuper,rolcreaterole,
              rolcreatedb,rolbypassrls,rolinherit,rolreplication,rolconnlimit
              FROM pg_catalog.pg_roles WHERE rolname='postgres' OR rolname LIKE 'ingestion_%'
              ORDER BY rolname""")
            observe('memberships', """SELECT roleid::regrole::text AS role,
              member::regrole::text AS member,grantor::regrole::text AS grantor,
              admin_option,inherit_option,set_option FROM pg_catalog.pg_auth_members
              WHERE roleid IN (SELECT oid FROM pg_catalog.pg_roles WHERE rolname LIKE 'ingestion_%')
              OR member=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)
              ORDER BY roleid,member,grantor""")
            observe('owner_effective_membership', """SELECT rolname,
              pg_has_role(current_user,oid,'USAGE') AS inherited,
              pg_has_role(current_user,oid,'SET') AS can_set
              FROM pg_catalog.pg_roles WHERE rolname IN
              ('ingestion_storage_owner','ingestion_recovery_operator','ingestion_barrier_releaser')
              ORDER BY rolname""")
            schema = observe('schema', """SELECT nspname,nspowner::regrole::text AS owner,nspacl::text AS acl,
              has_schema_privilege(current_user,oid,'USAGE') AS usage,
              has_schema_privilege(current_user,oid,'USAGE WITH GRANT OPTION') AS usage_grant_option,
              has_schema_privilege(current_user,oid,'CREATE WITH GRANT OPTION') AS create_grant_option
              FROM pg_catalog.pg_namespace WHERE nspname='public'""")
            if len(schema)!=1 or schema[0].get('usage') is not True:
                out['unknowns']['schema'] = 'PUBLIC_SCHEMA_USAGE_NOT_ESTABLISHED'
            tables = observe('tables', """SELECT relname,relowner::regrole::text AS owner,
              relacl::text AS acl,relrowsecurity,relforcerowsecurity,
              has_table_privilege(current_user,c.oid,'SELECT') AS can_select,
              has_table_privilege(current_user,c.oid,'UPDATE') AS can_update
              FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              WHERE n.nspname='public' AND c.relname IN
              ('ingestion_work_items','ingestion_work_attempts','ingestion_run_evidence') ORDER BY relname""")
            functions = observe('functions', """SELECT p.proname AS name,p.oid::regprocedure::text AS identity,
              p.proowner::regrole::text AS owner,p.prosecdef,p.proacl::text AS acl,
              p.proconfig=ARRAY['search_path=pg_catalog']::text[] AS exact_search_path,
              encode(sha256(convert_to(p.prosrc,'UTF8')),'hex') AS body_sha256,
              has_function_privilege(current_user,p.oid,'EXECUTE') AS owner_execute
              FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='public' AND p.proname IN
              ('ingestion_intake_evidence_write','ingestion_intake_evidence_read',
               'ingestion_intake_owner_state','ingestion_register_campaign_once')
              ORDER BY p.oid""")
            if (any(sum(f.get('name')==name for f in functions)!=1 for name in FUNCTIONS)
                or any(not f.get('identity') or not f.get('owner') or
                    not f.get('body_sha256') or type(f.get('prosecdef')) is not bool
                    for f in functions)):
                out['unknowns']['functions'] = 'REQUIRED_FUNCTION_ABSENT_AMBIGUOUS_OR_METADATA_INCOMPLETE'
            observe('restricted_execute', """SELECT r.rolname,p.proname AS name,p.oid::regprocedure::text AS function,
              has_function_privilege(r.oid,p.oid,'EXECUTE') AS can_execute
              FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
              WHERE r.rolname IN ('ingestion_worker','ingestion_worker_login','ingestion_effect_login')
              AND n.nspname='public' AND p.proname IN
              ('ingestion_intake_evidence_write','ingestion_intake_evidence_read','ingestion_register_campaign_once')
              ORDER BY r.rolname,p.oid""")
            sessions = observe('sessions', """SELECT pid,usename,state,backend_start,xact_start,
              wait_event_type,wait_event FROM pg_catalog.pg_stat_activity
              WHERE datname=current_database() AND pid<>pg_backend_pid()
              AND (usename LIKE 'ingestion_%' OR application_name='propertyaigent_owner_pilot')
              ORDER BY pid""")
            if any(s.get('state') is None or s.get('backend_start') is None for s in sessions):
                out['unknowns']['sessions'] = 'RELEVANT_SESSION_DETAILS_NOT_VISIBLE'
            for name in ('ingestion_work_items','ingestion_work_attempts','ingestion_run_evidence'):
                if sum(t.get('relname')==name for t in tables)!=1:
                    out['unknowns']['tables'] = 'REQUIRED_TABLE_PERMISSION_EVIDENCE_INCOMPLETE'
            can_read = (len(schema)==1 and schema[0].get('usage') is True and
                sum(t.get('relname')=='ingestion_work_items' and t.get('can_select') is True
                    for t in tables)==1)
            if can_read:
                controller = observe('controller', """SELECT
                  encode(sha256(convert_to(outcome::jsonb::text,'UTF8')),'hex') AS controller_sha256,
                  coalesce(jsonb_typeof(outcome::jsonb)='object'
                    AND outcome::jsonb ?& ARRAY['hard_stop_generation','global_stop','manual_stop','last_hard_stop','grants']
                    AND jsonb_typeof(outcome::jsonb->'hard_stop_generation')='number'
                    AND jsonb_typeof(outcome::jsonb->'global_stop') IN ('object','null')
                    AND (outcome::jsonb->'global_stop'='null'::jsonb OR
                      (jsonb_typeof(outcome::jsonb->'global_stop'->'reason')='string'
                       AND length(outcome::jsonb->'global_stop'->>'reason')>0))
                    AND jsonb_typeof(outcome::jsonb->'manual_stop') IN ('string','null')
                    AND jsonb_typeof(outcome::jsonb->'last_hard_stop') IN ('string','null')
                    AND jsonb_typeof(outcome::jsonb->'grants')='object',false) AS structure_valid,
                  outcome::jsonb->'hard_stop_generation' AS generation,
                  outcome::jsonb->'global_stop'<>'null'::jsonb AS global_stop_set,
                  outcome::jsonb->'manual_stop'<>'null'::jsonb AS manual_stop_set,
                  outcome::jsonb->'last_hard_stop'<>'null'::jsonb AS has_stop_history,
                  outcome::jsonb ? 'intake_run' AS has_intake_run
                  FROM public.ingestion_work_items WHERE key=repeat('0',64)""")
                validate_controller(controller)
                out['controller_validated'] = True
                observe('current_grants', """SELECT count(*) AS total,
                  count(*) FILTER (WHERE value->'expires_at'='0'::jsonb) AS explicitly_closed,
                  count(*) FILTER (WHERE jsonb_typeof(value->'expires_at') IS DISTINCT FROM 'number') AS unknown_expiry,
                  count(*) FILTER (WHERE CASE WHEN jsonb_typeof(value->'expires_at')='number'
                    THEN (value->>'expires_at')::numeric>extract(epoch FROM clock_timestamp()) ELSE false END) AS unexpired,
                  encode(sha256(convert_to(coalesce(jsonb_object_agg(key,value),'{}'::jsonb)::text,'UTF8')),'hex') AS grants_sha256
                  FROM jsonb_each((SELECT outcome::jsonb->'grants'
                    FROM public.ingestion_work_items WHERE key=repeat('0',64)))""")
                observe('unresolved_work', """SELECT state,phase,count(*) AS count
                  FROM public.ingestion_work_items WHERE key<>repeat('0',64)
                  AND (phase IN ('SOURCE_INTENT','WRITE_INTENT') OR state='PERSISTENCE_UNCERTAIN'
                    OR owner IS NOT NULL OR lease_until IS NOT NULL)
                  GROUP BY state,phase ORDER BY state,phase""")
            else:
                out['observations']['controller_access'] = 'NOT_OBSERVED_EXISTING_SELECT_ABSENT_NO_GRANT'
                out['unknowns']['controller'] = 'EXISTING_SCHEMA_USAGE_OR_CONTROLLER_SELECT_ABSENT_STOP_STATE_UNKNOWN'
        finally:
            # One explicit rollback, including refusals; preserve the failing phase.
            # Then close before the adapter context can perform implicit cleanup.
            rollback_and_close()
    require(out['connection_closed'], 'CLOSE_UNVERIFIED')
except BaseException as exc:
    out['status'] = 'STOP_RECONCILE_NO_RETRY'
    out['reason'] = str(exc) if isinstance(exc,Refusal) else 'CONFIGURATION_DEPENDENCY_OR_DATABASE_REFUSAL'
    state = getattr(exc,'sqlstate',None)
    out['unknowns'].setdefault(out['phase'], 'OBSERVATION_OR_VALIDATION_FAILED')
    if state=='42501':
        out['unknowns'][out['phase']] = 'PERMISSION_DENIED_EVIDENCE_UNKNOWN'
    if state in ('42501','28P01','28000','57014','25006','42P01','42883'):
        out['sqlstate'] = state
finally:
    signal.setitimer(signal.ITIMER_REAL,0)
    out['elapsed_ms'] = int((time.monotonic()-started)*1000)
    out['finished_at'] = datetime.now(timezone.utc).isoformat()
    finish_receipt(out)
    out['not_established'] = ['historical_process_or_source_closure',
        'current_non_database_process_containment','row_lock_acquisition',
        'installed_function_acceptance','operational_release','database_population']
    result = json.dumps(out,sort_keys=True,separators=(',',':'))
    if len(result.encode()) > 65535:
        result = json.dumps(dict(status='STOP_INCOMPLETE_OUTPUT_BOUND_NO_RETRY',inspection='PARTIAL',
            execution_id=out['execution_id'],connection_closed=out['connection_closed']))
    print(result,flush=True)
