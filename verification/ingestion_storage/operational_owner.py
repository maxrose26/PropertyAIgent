"""Exact finite administrative seam for the manual ingestion acceptance.

No source worker receives this connector. Runtime roles never issue grants or
release barriers. Storage installation/seeding is deliberately absent.
"""
import hashlib,json,secrets,time,re
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote
from psycopg import sql
from app.ingestion.ledger import digest,DEFAULT_LIMITS
from .operational_publication import Uncertain,canonical
from .storage_controller import split_sql
from .hard_deadline import hard_deadline,abandon,DeadlineExceeded

ADMIN_STATEMENT_HARD_SECONDS=12
ADMIN_CANCEL_ALLOWANCE=3          # aggregate ceiling on administrative cancel connections for the whole run (one Owner object and its resumed copies share one event list); beyond it a deadline only closes the client
TERMINATE_SQL="SELECT pg_terminate_backend(pid) FROM pg_catalog.pg_stat_activity WHERE pid=%s AND usename=%s AND backend_start=%s::timestamptz"
SESSIONS_SQL='SELECT pid,usename,state,backend_start FROM pg_catalog.pg_stat_activity WHERE usename=ANY(%s) ORDER BY pid'
# USAGE (privileges actually INHERITED), not MEMBER: a NOINHERIT or WITH INHERIT FALSE membership answers MEMBER=true yet does not confer the privilege (found by the hosted PG17 rehearsal).
PRIVILEGE_SQL="SELECT pg_catalog.pg_has_role(current_user,'pg_read_all_stats','USAGE'),pg_catalog.pg_has_role(current_user,'pg_signal_backend','USAGE')"
SESSION_POLICY=dict(wait_reads=3,wait_seconds=0.5,max_terminations=2,post_reads=3)
# The three reviewed timeout settings, applied at ROLE level to the two restricted logins only, so they hold whether or not a pooler honours startup options.
ROLE_SETTINGS=(('statement_timeout','10s'),('lock_timeout','3s'),('idle_in_transaction_session_timeout','20s'))
ROLE_SETTINGS_SQL='SELECT r.rolname,r.rolconfig,(SELECT count(*) FROM pg_catalog.pg_db_role_setting s WHERE s.setrole=r.oid AND s.setdatabase<>0) FROM pg_catalog.pg_roles r WHERE r.rolname=ANY(%s) ORDER BY r.rolname'
ROLE_SETTING_VALUE=re.compile(r'[0-9]{1,9}(?:ms|s|min|h|d)?')

PKG=Path('docs/design/ingestion-operational-required-20261018')
WORKER=Path('docs/design/ingestion-operational-20261016/worker.sql')
STOP={'reason':'CONSUMED_SALFORD_GLOBAL_STOP','run':'38884069913'}
STOP_SHA='a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e'
SCOPE=dict(kind='DISCOVERY_SCOPE',council='bolton',start='2026-10-16',end='2026-10-16',semantics='RECEIVED')
ROLES={'ingestion_worker_login':'ingestion_worker','ingestion_effect_login':'ingestion_effect_broker'}
SECRETS={'ingestion_worker_login':'INGESTION_WORKER_DATABASE_URL','ingestion_effect_login':'INGESTION_EFFECT_DATABASE_URL'}

PIPELINE_LOGINS=('ingestion_effect_login','ingestion_storage_login','ingestion_worker_login')
PIPELINE_ROLES_SQL="SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NOT NULL,r.rolvaliduntil,r.rolconnlimit,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY r.rolname"
PIPELINE_IDENTITY_SQL="SELECT current_user,session_user,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','SET'),pg_catalog.pg_has_role(current_user,'ingestion_barrier_releaser','USAGE'),pg_catalog.pg_has_role(current_user,'ingestion_barrier_releaser','SET'),pg_catalog.pg_has_role(current_user,'pg_read_all_stats','USAGE'),pg_catalog.pg_has_role(current_user,'pg_signal_backend','USAGE') FROM pg_catalog.pg_roles r WHERE r.rolname=current_user"
# Sessions: the two restricted logins by name PLUS any client backend whose role is not attributable to this identity (a non-monitoring identity sees NULL there). No query text is ever selected.
PIPELINE_SESSIONS_SQL="SELECT pid,usename,state,backend_start,backend_type FROM pg_catalog.pg_stat_activity WHERE usename=ANY(%s) OR (usename IS NULL AND backend_type='client backend' AND pid<>pg_catalog.pg_backend_pid()) ORDER BY pid"
PIPELINE_REVIEWED_FLAGS=(False,False,False,False,False)


def evaluate_pipeline_readback(obs,expected):
    """Pure evaluation of the fixed owner readback against the registration expectations. Returns (findings, notes). `findings` are FIXED reason codes (never values); ANY finding prevents
    grant issuance. `notes` are accurate, non-blocking observations: an idle pooled backend is reported as exactly that and is never classified as a leak.

    The same evaluation serves the final readback after invalidation: execution authority has ended (no unexpired grant) and the standing credentials are still exactly as provisioned."""
    findings=[];notes=[]
    ident=obs.get('identity')
    if not ident or tuple(ident[:6])!=(expected['identity'],expected['identity'],False,True,True,True):findings.append('MIGRATION_IDENTITY')
    elif tuple(ident[6:10])!=(False,False,False,False):findings.append('TEMPORARY_OWNER_OR_RELEASER_CAPABILITY_PRESENT')
    ctl=obs.get('control')
    if not isinstance(ctl,dict):findings.append('CONTROL_STATE_UNAVAILABLE')
    else:
        if ctl.get('global_stop')!=STOP:findings.append('GLOBAL_STOP_CHANGED')
        if ctl.get('manual_stop')!='STORAGE_TEST_STOP':findings.append('MANUAL_STOP_CHANGED')
        if ctl.get('hard_stop_generation')!=expected['hard_stop_generation']:findings.append('HARD_STOP_GENERATION_CHANGED')
        if ctl.get('unexpired_grants')!=0:findings.append('UNEXPIRED_GRANT_PRESENT')
    roles={r[0]:r for r in obs.get('roles') or []}
    if set(roles)!=set(PIPELINE_LOGINS):findings.append('RESTRICTED_OR_STORAGE_LOGIN_MISSING')
    else:
        storage=roles['ingestion_storage_login']
        if (storage[1],storage[2])!=(False,False):findings.append('ACCEPTED_STORAGE_ACCESS_CHANGED')
        for name in ('ingestion_effect_login','ingestion_worker_login'):
            r=roles[name]
            if r[1] is not True:findings.append('LOGIN_NOT_ENABLED')
            if r[2] is not True:findings.append('PASSWORD_NOT_PRESENT')
            if r[3] is None or r[3].isoformat()!=expected['valid_until']:findings.append('VALID_UNTIL_MISMATCH')
            if r[4]!=1:findings.append('CONNECTION_LIMIT_CHANGED')
            if tuple(r[5:10])!=PIPELINE_REVIEWED_FLAGS:findings.append('PRIVILEGE_FLAG_CHANGED')
    if sorted(tuple(m) for m in obs.get('memberships') or [])!=sorted((r,c) for r,c in ROLES.items()):findings.append('MEMBERSHIPS_CHANGED')
    reviewed={'%s=%s'%(k,v) for k,v in ROLE_SETTINGS}
    config=obs.get('role_settings') or {}
    if not all(reviewed<=set(config.get(n,[])) for n in ROLES):findings.append('ROLE_SETTINGS_CHANGED')
    if not obs.get('inventory_recognised'):findings.append('INSTALLED_FUNCTIONS_NOT_RECOGNISED')
    sessions=obs.get('sessions')
    if sessions is None:findings.append('SESSIONS_NOT_OBSERVED')
    else:
        if not (ident and ident[10] is True):findings.append('SESSION_VISIBILITY_NOT_PROVEN')
        states=set()
        for row in sessions:
            if len(row)!=5 or row[1] is None or row[1] not in ROLES or row[2] is None:findings.append('UNATTRIBUTABLE_CLIENT_BACKEND');continue
            states.add(row[2])
            if row[2]!='idle':findings.append('ROLE_SESSION_NOT_IDLE')
        if states:notes.append('IDLE_POOLED_BACKENDS_OBSERVED_NOT_CLASSIFIED_AS_A_LEAK' if states=={'idle'} else 'NON_IDLE_ROLE_SESSION_OBSERVED')
    return sorted(set(findings)),notes


class Owner:
    # (normal, diagnostic) administrative connections; (normal, teardown, diagnostic) administrative commands. The restricted-connection matrix passes much tighter finite values.
    DEFAULT_LIMITS=dict(connections=(11,13),commands=(200,232,240))
    limits=DEFAULT_LIMITS      # class default for any Owner not built through __init__
    statement_hard_seconds=None      # None = the module constant ADMIN_STATEMENT_HARD_SECONDS at call time (every other mode keeps 12 s, and tests may patch it); the observation mode sets its own

    def __init__(self,connector,emit,check,*,identity='postgres',expiry,bindings,limits=None):
        self.limits=dict(limits or self.DEFAULT_LIMITS);self.timeline={}
        self.connector=connector;self.emit=emit;self.check=check;self.identity=identity;self.expiry=expiry;self.bindings=bindings
        self.connections=0;self.opened=0;self.closed=0;self.connection_active=0.0;self.effect_uncertain=False;self.invalidation='NOT_REQUIRED_NO_AUTHORITY';self.expected_generation=0;self.reuse_installed=False;self.apply_policy=True;self.baseline_control_sha256='0d829597f1422fef0af13920d5749c5751adf6d896588f379c400db7b3fa27cf';self.commands=0;self.returned_bytes=0;self.active=0;self.urls={};self.original_control=None;self.authorities=[];self.diagnostic_mode=False;self.tearing_down=False;self.grant_expiry=None;self.require_control_sha256=None;self.commit_uncertain=False
        self.failed_native_connections=[];self.cancel_events=[];self.sleep=time.sleep;self.session_disposition='NOT_EVALUATED';self.terminations=0
        self.preflight_report=dict(reason_code='NOT_REACHED',policy_state='NOT_EVALUATED',permitted_states=[]);self.permitted_policy_states=None;self.stable_state=False;self.valid_until=None;self.apply_role_settings=False;self.role_settings_prior=None;self.role_settings_state='NOT_REQUESTED';self.teardown_residuals=[]

    @contextmanager
    def connection(self):
        self.check()
        if self.connections>=(self.limits['connections'][1] if self.diagnostic_mode else self.limits['connections'][0]):raise ValueError('ADMIN_CONNECTION_BOUND')
        self.connections+=1;self.emit('admin_connection_intent',dict(ordinal=self.connections))
        c=None;began=time.monotonic()
        try:
            c=self.connector();self.connection_active+=time.monotonic()-began;self.opened+=1;self.emit('admin_connection_open',dict(ordinal=self.connections))
            yield c
        except BaseException as exc:
            if c is None:self.connection_active+=time.monotonic()-began
            from .connection_diagnostics import safe_failure
            observed=safe_failure(exc,'DRIVER_CONNECT' if c is None else 'EXECUTION')
            if c is None:self.failed_native_connections.append(observed['failed_native_connection_finished'])
            self.emit('admin_connection_failed',dict(ordinal=self.connections,**observed))
            if c is None:
                exc.__context__=None;exc.__cause__=None
                raise exc.with_traceback(None) from None
            raise
        finally:
            if c is not None:
                closing=time.monotonic();c.close();self.connection_active+=time.monotonic()-closing
                if not c.closed:raise Uncertain('ADMIN_CLOSE_UNCERTAIN')
                self.closed+=1;self.emit('admin_connection_closed',dict(ordinal=self.connections))

    def q(self,c,statement,params=None,*,effect=False):
        self.check()
        normal,teardown,diagnostic=self.limits['commands'];cap=diagnostic if self.diagnostic_mode else teardown if self.tearing_down else normal
        if self.commands>=cap:raise ValueError('ADMIN_COMMAND_BOUND')
        self.commands+=1
        if effect:self.emit('admin_effect_intent',dict(command=self.commands))
        started=time.monotonic()
        try:
            try:
                with hard_deadline(self.statement_hard_seconds or ADMIN_STATEMENT_HARD_SECONDS,'ADMIN_STATEMENT_HARD_DEADLINE'):
                    cur=c.execute(statement,params)
                    rows=cur.fetchall() if cur.description else []
            except DeadlineExceeded:
                if sum(e.get('cancel_attempts',0) for e in self.cancel_events)>=ADMIN_CANCEL_ALLOWANCE:
                    try:c.close()
                    except BaseException:pass
                    self.cancel_events.append(dict(cancel_requested=False,cancel_outcome='CANCEL_SKIPPED_ALLOWANCE_EXHAUSTED',cancel_attempts=0,cancel_seconds=0.0,client_closed=bool(c.closed),backend_closure='NOT_ESTABLISHED'))
                else:self.cancel_events.append(abandon(c))
                raise Uncertain('ADMIN_STATEMENT_HARD_DEADLINE') from None       # cancel acknowledged or not, the effect and the backend stay unproven
            if cur.pgresult is not None:
                self.returned_bytes+=sum(len(cur.pgresult.get_value(r,k) or b'') for r in range(cur.pgresult.ntuples) for k in range(cur.pgresult.nfields))
            if self.returned_bytes>1024**2:raise Uncertain('ADMIN_RETURNED_VALUE_BOUND')
            if effect:self.emit('admin_effect_ack',dict(command=self.commands))
            return rows
        except BaseException:
            if effect:self.effect_uncertain=True;raise Uncertain('ADMIN_EFFECT_UNCERTAIN') from None
            raise
        finally:self.active+=time.monotonic()-started

    def script(self,c,path):
        for statement in split_sql(Path(path).read_text()):self.q(c,statement,effect=True)

    def accounting(self):
        return dict(connections=self.connections,connections_opened=self.opened,connections_closed=self.closed,failed_native_connections=len(self.failed_native_connections),failed_native_finished=sum(self.failed_native_connections),commands=self.commands,returned_data_value_bytes=self.returned_bytes,database_active_seconds=self.active+self.connection_active,uncertain_effect=self.effect_uncertain,admin_hard_deadline_events=list(self.cancel_events),admin_cancel_allowance=ADMIN_CANCEL_ALLOWANCE,session_terminations=self.terminations,preflight=dict(self.preflight_report),first_connection_intervals={r:t.get('first_contact_intervals') for r,t in self.timeline.items()},session_disposition=self.session_disposition,role_settings=dict(state=self.role_settings_state,prior_captured=self.role_settings_prior is not None),teardown_residuals=list(self.teardown_residuals))

    def preflight(self):
        with self.connection() as c:
            flags=self.q(c,"SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_catalog.pg_roles WHERE rolname=current_user")[0]
            self.emit('migration_identity_observed',dict(current_user=flags[0],session_user=flags[1],superuser=flags[2],createrole=flags[3],createdb=flags[4],bypassrls=flags[5]))
            if tuple(flags)!=(self.identity,self.identity,False,True,True,True):raise ValueError('MIGRATION_IDENTITY')
            permissions=self.q(c,"SELECT has_schema_privilege(current_user,'public','USAGE WITH GRANT OPTION'),has_schema_privilege(current_user,'public','CREATE WITH GRANT OPTION'),has_database_privilege(current_user,current_database(),'CONNECT WITH GRANT OPTION'),EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid='ingestion_storage_owner'::regrole AND member=(SELECT oid FROM pg_roles WHERE rolname=current_user) AND admin_option),bool_and(relowner='ingestion_storage_owner'::regrole AND relrowsecurity AND relforcerowsecurity) FROM pg_class WHERE oid IN ('public.ingestion_work_items'::regclass,'public.ingestion_work_attempts'::regclass)")[0]
            self.emit('migration_capabilities_observed',dict(values=permissions))
            if permissions!=(True,True,True,True,True):raise ValueError('MIGRATION_OWNERSHIP_OR_GRANT_OPTIONS')
            # ADMIN does not imply table SELECT or role SET. Use the accepted
            # installer self-grant only inside an explicitly rolled-back
            # preflight transaction, never grant runtime owner membership.
            self.q(c,'BEGIN',effect=True)
            self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            rows=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)")
            ctl=rows[0][0];self.emit('control_observed',dict(global_stop=ctl.get('global_stop'),manual_stop=ctl.get('manual_stop'),hard_stop_generation=ctl.get('hard_stop_generation',0),grant_count=len(ctl['grants'])))
            self.q(c,'ROLLBACK',effect=True)
            if ctl.get('global_stop')!=STOP or ctl.get('manual_stop')!='STORAGE_TEST_STOP' or (not self.reuse_installed and (ctl.get('hard_stop_generation',0)!=0 or ctl['grants'] or ctl.get('bolton_exceptions'))) or (self.reuse_installed and digest(ctl)!=self.baseline_control_sha256):raise ValueError('EXACT_STORAGE_STOP_STATE')
            self.original_control=ctl
            password_access=self.q(c,"SELECT has_column_privilege(current_user,'pg_catalog.pg_authid','rolname','SELECT') AND has_column_privilege(current_user,'pg_catalog.pg_authid','rolpassword','SELECT')")[0][0]
            self.emit('password_boolean_read_permission',dict(permitted=password_access))
            if password_access is not True:raise ValueError('EXISTING_PASSWORD_BOOLEAN_READ_UNAVAILABLE')
            roles=self.q(c,"SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NULL FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY r.rolname",(['ingestion_worker_login','ingestion_storage_login'],))
            self.emit('existing_login_state',dict(roles=roles))
            if self.stable_state:      # revocation: the storage login must be as accepted; the worker login may be in ANY enabled/disabled state (a partial earlier disable must not block the revocation)
                if [r for r in roles if r[0]=='ingestion_storage_login']!=[('ingestion_storage_login',False,True)] or len(roles)!=2:raise ValueError('ACCEPTED_STORAGE_ACCESS_CHANGED')
                members=self.q(c,"SELECT member::regrole::text,roleid::regrole::text FROM pg_auth_members WHERE member='ingestion_storage_login'::regrole")
                if members:raise ValueError('STORAGE_MEMBERSHIP_CHANGED')
            elif roles!=[('ingestion_storage_login',False,True),('ingestion_worker_login',False,True)]:raise ValueError('ACCEPTED_STORAGE_ACCESS_CHANGED')
            elif self.q(c,"SELECT count(*) FROM pg_auth_members WHERE member=ANY(ARRAY['ingestion_worker_login'::regrole,'ingestion_storage_login'::regrole])")[0][0]!=0:raise ValueError('STORAGE_MEMBERSHIP_CHANGED')
            if not self.stable_state and self.q(c,"SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)",(['ingestion_worker_login','ingestion_storage_login','ingestion_effect_login'],))[0][0]:raise ValueError('PREEXISTING_RUNTIME_SESSIONS')      # a revocation must be able to meet and resolve sessions
            if self.reuse_installed:
                exact=self.q(c,"SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NULL,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication,r.rolconnlimit FROM pg_roles r JOIN pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY r.rolname",(list(ROLES),))
                self.emit('reused_runtime_flags_observed',dict(rows=exact))
                if self.stable_state:      # only the privilege-bearing flags and the connection limit are fixed; login/password/membership state may be partially disabled
                    if len(exact)!=2 or any(row[3:8]!=(False,False,False,False,False) or row[8]!=1 for row in exact):raise ValueError('REUSED_RUNTIME_FLAGS_CHANGED')
                    allowed={(r,cap) for r,cap in ROLES.items()}
                    if not {tuple(m) for m in self.q(c,'SELECT member::regrole::text,roleid::regrole::text FROM pg_auth_members WHERE member=ANY(%s::regrole[])',(list(ROLES),))}<=allowed:raise ValueError('REUSED_RUNTIME_MEMBERSHIPS_CHANGED')
                else:
                    if exact!=[(r,False,True,False,False,False,False,False,1) for r in sorted(ROLES)]:raise ValueError('REUSED_RUNTIME_FLAGS_CHANGED')
                    if self.q(c,'SELECT count(*) FROM pg_auth_members WHERE member=ANY(%s::regrole[])',(list(ROLES),))[0][0]!=0:raise ValueError('REUSED_RUNTIME_MEMBERSHIPS_CHANGED')
                self.verify_installed(c)
                return
            if self.q(c,"SELECT to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),EXISTS(SELECT 1 FROM pg_roles WHERE rolname='ingestion_effect_login')")[0]!=(None,False):raise ValueError('INSTALLATION_ALREADY_EXISTS_NO_REPLAY')

    FUNCTION_PATTERN=re.compile(r'CREATE (?:OR REPLACE )?FUNCTION public\.(\w+)\(.*?\).*?AS \$(\w*)\$(.*?)\$\2\$;',re.S)

    @classmethod
    def reviewed_inventories(cls,permit_successor_policy):
        """The coherent, explicitly identified installed states that may be accepted: the ORIGINAL reviewed inventory (worker.sql) and, only for a mode that itself applies the reviewed
        successor policy, the SUCCESSOR_POLICY_APPLIED inventory (the original with exactly the functions redefined by successor-policy.sql). Never a per-function mixture."""
        original={m[1]:m[3] for m in cls.FUNCTION_PATTERN.finditer(WORKER.read_text())}
        policy={m[1]:m[3] for m in cls.FUNCTION_PATTERN.finditer((PKG/'successor-policy.sql').read_text())}
        if len(original)<5 or not policy or not set(policy)<=set(original):raise ValueError('REVIEWED_FUNCTION_INVENTORY')
        states={'ORIGINAL':original}
        upgraded={**original,**policy}
        return states,upgraded,(dict(states,SUCCESSOR_POLICY_APPLIED=upgraded) if permit_successor_policy else states)

    def verify_installed(self,c):
        """Accept exactly one coherent reviewed inventory, bound to the execution mode, with the reviewed owner and search path on every function. Reports a fixed reason code and the
        recognised policy state (never exception text). Preflight fails closed before any change."""
        states,upgraded,permitted=self.reviewed_inventories(self.apply_policy)
        if self.permitted_policy_states is not None:      # a mode may name exactly the retained state it is bound to (it then neither applies the policy nor accepts any other state)
            permitted={k:v for k,v in {'ORIGINAL':states['ORIGINAL'],'SUCCESSOR_POLICY_APPLIED':upgraded}.items() if k in self.permitted_policy_states}
        names=list(upgraded)
        rows=self.q(c,"SELECT p.proname,p.prosrc,r.rolname,p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner WHERE n.nspname='public' AND p.proname=ANY(%s) ORDER BY p.proname",(names,))
        observed={n:body for n,body,_,_ in rows}
        recognised=next((s for s,b in {'ORIGINAL':states['ORIGINAL'],'SUCCESSOR_POLICY_APPLIED':upgraded}.items() if observed==b),None)
        self.emit('installed_function_inventory',dict(hashes={n:hashlib.sha256(body.encode()).hexdigest() for n,body in observed.items()},policy_state=recognised or 'UNRECOGNISED'))
        if set(observed)!=set(names) or len(rows)!=len(names):reason='INSTALLED_FUNCTION_CONTENT_CHANGED'      # missing, extra or duplicated (overloaded) functions
        elif any(owner!='ingestion_storage_owner' or config!=['search_path=pg_catalog'] for _,_,owner,config in rows):reason='INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED'
        elif recognised is None:
            mixed=all(observed[n] in (states['ORIGINAL'][n],upgraded[n]) for n in names)
            reason='INSTALLED_POLICY_STATE_MIXED' if mixed else 'INSTALLED_FUNCTION_CONTENT_CHANGED'
        elif recognised not in permitted:reason='INSTALLED_POLICY_STATE_NOT_PERMITTED_FOR_MODE'
        else:reason=None
        self.preflight_report=dict(reason_code=reason or 'POLICY_STATE_RECOGNISED',policy_state=recognised or 'UNRECOGNISED',permitted_states=sorted(permitted))
        if reason:raise ValueError(reason)
        self.expected_generation=1

    def install(self):
        if self.reuse_installed:
            # No base storage/operational reinstall or role creation. Regrant
            # only the same reviewed runtime memberships in this finite phase.
            with self.connection() as c:
                if self.apply_policy:self.script(c,PKG/'successor-policy.sql')
                self.q(c,'BEGIN',effect=True)
                self.q(c,'GRANT ingestion_worker TO ingestion_worker_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE',effect=True)
                self.q(c,'GRANT ingestion_effect_broker TO ingestion_effect_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE',effect=True)
                self.q(c,'COMMIT',effect=True)
                self.activation_precheck(c)
            return
        with self.connection() as c:
            self.script(c,WORKER)
            self.q(c,'BEGIN',effect=True)
            self.q(c,'CREATE ROLE ingestion_effect_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION CONNECTION LIMIT 1 PASSWORD NULL',effect=True)
            self.q(c,'GRANT ingestion_worker TO ingestion_worker_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE',effect=True)
            self.q(c,'GRANT ingestion_effect_broker TO ingestion_effect_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE',effect=True)
            self.q(c,sql.SQL('GRANT CONNECT ON DATABASE {} TO ingestion_effect_login').format(sql.Identifier(c.info.dbname)),effect=True)
            self.q(c,'COMMIT',effect=True)
            # Exercise the exact complete activation gate read-only before any
            # password/secret operation. No unsupported redaction assertion.
            self.activation_precheck(c)

    def activation_precheck(self,c):
        gate=(PKG/'activate.sql').read_text().split('ALTER ROLE ingestion_worker_login LOGIN;')[0].replace('BEGIN;','BEGIN READ ONLY;',1)+'ROLLBACK;'
        for statement in split_sql(gate):self.q(c,statement)

    def map_and_activate(self,github,*,url_factory):
        names=github.names()
        if 'DATABASE_URL' not in names or 'INGESTION_STORAGE_DATABASE_URL' in names or any(n in names for n in SECRETS.values()):raise ValueError('EXACT_EMPTY_OPERATIONAL_MAPPINGS_REQUIRED')
        with self.connection() as c:
            if self.apply_role_settings:self.install_role_settings(c)      # before any password exists and before LOGIN is possible
            for role,name in SECRETS.items():
                password=secrets.token_urlsafe(48)
                verifier=c.pgconn.encrypt_password(password.encode(),role.encode(),algorithm=b'scram-sha-256').decode()
                self.q(c,'BEGIN',effect=True)
                self.q(c,sql.SQL('ALTER ROLE {} PASSWORD {} VALID UNTIL {}').format(sql.Identifier(role),sql.Literal(verifier),sql.Literal((self.valid_until or self.expiry).isoformat())),effect=True)
                self.q(c,'COMMIT',effect=True);self.timeline.setdefault(role,{})['password_committed']=time.monotonic()
                url=url_factory(role,password);github.put_secret(name,url);self.urls[role]=url;self.timeline[role]['mapped']=time.monotonic()
                del password,verifier,url
            self.script(c,PKG/'activate.sql')
            stamp=time.monotonic()
            for role in ROLES:self.timeline.setdefault(role,{})['activated']=stamp

    @staticmethod
    def _split(entries):
        names={n for n,_ in ROLE_SETTINGS}
        return {e.split('=',1)[0]:e.split('=',1)[1] for e in entries if e.split('=',1)[0] in names},sorted(e for e in entries if e.split('=',1)[0] not in names)

    def install_role_settings(self,c):
        """Capture the existing role configuration of the two restricted logins, then set ONLY the three reviewed timeouts (one transaction), and read back.

        Existing values are kept for exact restoration; unrelated settings are never touched. Database-specific settings or an unsupported prior value of a reviewed parameter stop the run
        BEFORE any change. A failed or uncertain installation leaves state APPLYING so the teardown restores from the capture (idempotent)."""
        rows=self.q(c,ROLE_SETTINGS_SQL,(list(ROLES),))
        if [r[0] for r in rows]!=sorted(ROLES):raise ValueError('ROLE_SETTINGS_ROLES_MISSING')
        if any(r[2] for r in rows):raise ValueError('ROLE_DATABASE_SPECIFIC_SETTINGS_PRESENT')
        prior={}
        for name,config,_ in rows:
            reviewed,unrelated=self._split(list(config or []))
            if any(not ROLE_SETTING_VALUE.fullmatch(v) for v in reviewed.values()):raise ValueError('ROLE_SETTING_PRIOR_VALUE_UNSUPPORTED')
            prior[name]=list(config or [])
        self.role_settings_prior=prior
        self.emit('role_settings_captured',dict(roles={n:dict(reviewed=self._split(e)[0],unrelated_names=sorted(x.split('=',1)[0] for x in self._split(e)[1])) for n,e in prior.items()}))
        self.role_settings_state='APPLYING'
        self.q(c,'BEGIN',effect=True)
        for role in sorted(ROLES):
            for param,value in ROLE_SETTINGS:
                self.q(c,sql.SQL('ALTER ROLE {} SET {} TO {}').format(sql.Identifier(role),sql.Identifier(param),sql.Literal(value)),effect=True)
        self.q(c,'COMMIT',effect=True)
        after={r[0]:list(r[1] or []) for r in self.q(c,ROLE_SETTINGS_SQL,(list(ROLES),))}
        want={n:(dict(ROLE_SETTINGS),self._split(prior[n])[1]) for n in prior}
        if {n:(self._split(e)[0],self._split(e)[1]) for n,e in after.items()}!=want:raise Uncertain('ROLE_SETTINGS_NOT_VERIFIED')
        self.role_settings_state='APPLIED_VERIFIED';self.emit('role_settings_applied',dict(roles=sorted(ROLES),settings=dict(ROLE_SETTINGS)))

    def restore_role_settings(self):
        """Restore the captured configuration of each reviewed parameter (SET to the prior value, or RESET when there was none) on its own connection, then read back."""
        prior=self.role_settings_prior
        if prior is None:return
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
            for role in sorted(ROLES):
                was=self._split(prior[role])[0]
                for param,_ in ROLE_SETTINGS:
                    if param in was:self.q(c,sql.SQL('ALTER ROLE {} SET {} TO {}').format(sql.Identifier(role),sql.Identifier(param),sql.Literal(was[param])),effect=True)
                    else:self.q(c,sql.SQL('ALTER ROLE {} RESET {}').format(sql.Identifier(role),sql.Identifier(param)),effect=True)
            self.q(c,'COMMIT',effect=True)
            now={r[0]:sorted(r[1] or []) for r in self.q(c,ROLE_SETTINGS_SQL,(list(ROLES),))}
            if now!={n:sorted(e) for n,e in prior.items()}:raise Uncertain('ROLE_SETTINGS_NOT_RESTORED')
        self.role_settings_state='RESTORED_VERIFIED'

    def restore_role_settings_guarded(self):
        if self.role_settings_prior is None:return True
        try:self.restore_role_settings()
        except Exception:
            self.role_settings_state='RESTORATION_UNCERTAIN';self.teardown_residuals.append('ROLE_SETTINGS_UNRESTORED')
            self.emit('role_settings_restoration',dict(state=self.role_settings_state,prior=self.role_settings_prior));return False
        self.emit('role_settings_restoration',dict(state=self.role_settings_state));return True

    def stable_readback(self):
        """Owner-privileged readback of the STANDING state after provisioning: flags, password presence (boolean only), validity, memberships and role settings. Sessions are NOT read here:
        that needs monitoring privileges the migration identity has not been shown to hold, so absence of other sessions is an owner verification."""
        with self.connection() as c:
            roles=self.q(c,"SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NOT NULL,r.rolvaliduntil,r.rolconnlimit,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY r.rolname",(list(ROLES),))
            members=[tuple(m) for m in self.q(c,'SELECT member::regrole::text,roleid::regrole::text FROM pg_auth_members WHERE member=ANY(%s::regrole[]) ORDER BY 1,2',(list(ROLES),))]
            config={r[0]:sorted(r[1] or []) for r in self.q(c,ROLE_SETTINGS_SQL,(list(ROLES),))}
        reviewed={'%s=%s'%(k,v) for k,v in ROLE_SETTINGS}
        ok=(len(roles)==2 and all(r[1] is True and r[2] is True and r[3] is not None and r[4]==1 and not any(r[5:]) for r in roles)
            and members==[(r,cap) for r,cap in sorted(ROLES.items())] and all(reviewed<=set(config.get(n,[])) for n in ROLES))
        self.emit('stable_state_readback',dict(roles=[[r[0],r[1],r[2],r[3].isoformat() if r[3] else None,r[4]] for r in roles],memberships=members,role_settings_applied=ok))
        if not ok:raise Uncertain('STABLE_STATE_NOT_VERIFIED')
        return dict(valid_until=min(r[3] for r in roles).isoformat(),memberships=members)

    def register(self,items,authority,*,capture_key,source_calls,prepared=()):
        bindings={x['key']:{k:x[k] for k in ('subject','task','contract','revision')} for x in [*items,*prepared]}
        grant=dict(keys=sorted(bindings),contracts=sorted({x['contract'] for x in [*items,*prepared]}),expires_at=(self.grant_expiry or self.expiry).timestamp(),source_calls=source_calls,writes=0,login='ingestion_worker_login',effect_login='ingestion_effect_login',workers=['required_once'],bindings=bindings,detail_source_keys=[],capture_key=capture_key,capture_only=True,execution_binding=self.bindings,
                   completion_outcomes={'DISCOVERY':['ENUMERATED_METADATA_RETAINED'],'LISTING_METADATA':['BATCH_SCREENED'],'SCREENING':['SCREENED','ALREADY_KNOWN','INSUFFICIENT_EVIDENCE','SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH','DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE']})
        # Owner-only fixed insertion/issuance. No runtime principal receives the
        # owner, issuer, barrier or recovery memberships used here.
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
            self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            ctl=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
            if ctl['global_stop']!=STOP or ctl.get('manual_stop')!='STORAGE_TEST_STOP' or ctl.get('hard_stop_generation',0)!=self.expected_generation or authority in ctl['grants']:raise Uncertain('OWNER_REGISTRATION_STATE_CHANGED')
            if self.require_control_sha256 is not None and digest(ctl)!=self.require_control_sha256:raise Uncertain('OWNER_REGISTRATION_CONTROL_BINDING')      # first registration: the control row is exactly the accepted baseline
            self.authorities.append(authority);self.invalidation='REQUIRED'
            for item in items:
                self.q(c,'INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)',(json.dumps(item),),effect=True)
            ctl['grants'][authority]=grant
            self.q(c,"UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),),effect=True)
            self.q(c,'REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
            self.q(c,'GRANT ingestion_barrier_releaser TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            exception=dict(authority=authority,transport='REQUESTS_IDOX',grant_binding={k:v for k,v in grant.items() if k not in {'source_calls','writes'}},stop_checkpoint_sha256=STOP_SHA,hard_stop_generation=self.expected_generation,**self.bindings)
            self.q(c,'SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(exception),),effect=True)
            self.q(c,'REVOKE ingestion_barrier_releaser FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
            self.q(c,'COMMIT',effect=True)
            capability=self.q(c,"SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET'),pg_has_role(current_user,'ingestion_barrier_releaser','USAGE'),pg_has_role(current_user,'ingestion_barrier_releaser','SET'),has_schema_privilege('ingestion_storage_owner','public','CREATE')")[0]
            self.emit('temporary_owner_capability_readback',dict(flags=capability))
            if capability!=(False,False,False,False,False):raise Uncertain('TEMPORARY_OWNER_CAPABILITY_REMAINS')
        self.emit('owner_registration_committed',dict(authority=authority,keys=sorted(bindings),binding_sha256=digest(grant)))
        return bindings

    def teardown(self,github):
        """Disable access first, then resolve surviving sessions under a bounded, privilege-proven policy, then delete the temporary secrets independently once DISABLED status is verified.

        Disabling stops NEW logins and removes membership-granted privileges from any open session immediately (statement-time evaluation); it does not end a session. A surviving session
        is therefore resolved (bounded waits, then at most two precisely identified terminations, only with proven existing privileges) or left UNRESOLVED and reported - it can no
        longer suppress the secret deletion, and it can never be reported closed."""
        self.tearing_down=True
        try:self._teardown(github)
        except BaseException:
            if self.role_settings_prior is not None and self.role_settings_state in ('APPLYING','APPLIED_VERIFIED'):
                self.role_settings_state='RESTORATION_NOT_ATTEMPTED';self.teardown_residuals.append('ROLE_SETTINGS_RESTORATION_NOT_ATTEMPTED')
            raise

    def _teardown(self,github):
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
            if self.authorities:
                self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
                ctl=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
                for authority in self.authorities:
                    ctl['grants'][authority]['expires_at']=0
                    if authority in ctl.get('bolton_exceptions',{}):ctl['bolton_exceptions'][authority]['expires_at']=0
                self.q(c,"UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),),effect=True)
                self.q(c,'REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
            for role,capability in ROLES.items():
                self.q(c,sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL').format(sql.Identifier(role)),effect=True)
                self.q(c,sql.SQL('REVOKE {} FROM {}').format(sql.Identifier(capability),sql.Identifier(role)),effect=True)
            self.q(c,'COMMIT',effect=True)
            # Observe actual safe fields, never password material or query text.
            roles=self.q(c,"SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NULL FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY r.rolname",(list(ROLES),))
            memberships=self.q(c,'SELECT m.member::regrole::text,m.roleid::regrole::text,m.admin_option,m.inherit_option,m.set_option FROM pg_auth_members m WHERE m.member=ANY(%s::regrole[])',(list(ROLES),))
            disabled=roles==[(r,False,True) for r in sorted(ROLES)] and not memberships      # decided from the role/password/membership readbacks alone
            try:sessions=self.q(c,SESSIONS_SQL,(list(ROLES),))
            except Exception:                                                                # a failed FIRST session read can never suppress the secret deletion
                sessions=None;self.session_disposition='UNVERIFIED'
            self.emit('teardown_observed',dict(roles=roles,memberships=memberships,sessions=None if sessions is None else [[s[0],s[1],s[2]] for s in sessions]))
            if sessions is not None:self.session_disposition='NONE' if not sessions else 'NOT_EVALUATED'
            if disabled and sessions:
                try:self.resolve_sessions(c,sessions)
                except Exception:                                    # a failed session read or termination must never suppress the independent secret deletion
                    if self.session_disposition in ("NONE","NOT_EVALUATED","CLEARED_BY_WAIT"):self.session_disposition="UNRESOLVED_ERROR"
                    self.emit("session_disposition",dict(disposition=self.session_disposition))
        if not disabled:
            if self.role_settings_prior is not None:self.teardown_residuals.append('ROLE_SETTINGS_RESTORATION_NOT_ATTEMPTED');self.role_settings_state='RESTORATION_NOT_ATTEMPTED'
            raise Uncertain('TEARDOWN_RECONCILE')              # not verified disabled: the temporary secrets are NOT deleted
        if self.session_disposition not in ('NONE','CLEARED_BY_WAIT','TERMINATED_VERIFIED_ABSENT'):self.teardown_residuals.append('SESSIONS_'+self.session_disposition)      # recorded before anything can raise
        try:
            present=github.names() if self.stable_state else None      # a revocation deletes only the secrets that still exist (idempotent after a partial earlier removal)
            for name in SECRETS.values():
                if present is None or name in present:github.call('DELETE','repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets/'+name)
            names=github.names();self.emit('teardown_secret_names_observed',dict(names={n:n in names for n in SECRETS.values()},database_url_present='DATABASE_URL' in names))
            if any(n in names for n in SECRETS.values()) or 'DATABASE_URL' not in names:raise Uncertain('TEARDOWN_SECRET_RECONCILE')
            self.urls.clear()
        finally:
            settings_ok=self.restore_role_settings_guarded()      # independent of the secret outcome; the secrets always come first
        if self.session_disposition not in ('NONE','CLEARED_BY_WAIT','TERMINATED_VERIFIED_ABSENT'):
            raise Uncertain('TEARDOWN_SESSIONS_UNRESOLVED')
        if not settings_ok:raise Uncertain('TEARDOWN_ROLE_SETTINGS_UNRESTORED')

    def resolve_sessions(self,c,sessions):
        policy=SESSION_POLICY
        for _ in range(policy['wait_reads']):
            self.sleep(policy['wait_seconds']);sessions=self.q(c,SESSIONS_SQL,(list(ROLES),))
            if not sessions:self.session_disposition='CLEARED_BY_WAIT';self.emit('session_disposition',dict(disposition=self.session_disposition));return
        # still present: identify precisely or leave unresolved. No privilege is ever granted to make this possible.
        flags=self.q(c,PRIVILEGE_SQL)[0]
        if tuple(flags)!=(True,True):self.session_disposition='UNRESOLVED_PRIVILEGE_NOT_PROVEN'
        elif len(sessions)>policy['max_terminations'] or any(len(row)!=4 or None in row or row[1] not in ROLES for row in sessions):self.session_disposition='UNRESOLVED_EXTRA_OR_UNIDENTIFIABLE'
        else:
            for pid,usename,state,start in sessions:
                if self.terminations>=policy['max_terminations']:self.session_disposition='UNRESOLVED_TERMINATION_BOUND';break
                self.terminations+=1
                answer=self.q(c,TERMINATE_SQL,(pid,usename,start))
                self.emit('session_termination',dict(pid=pid,role=usename,state=state,acknowledged=answer==[(True,)]))
            else:
                self.session_disposition='TERMINATION_SIGNALLED_NOT_VERIFIED'
                for _ in range(policy['post_reads']):
                    self.sleep(policy['wait_seconds']);left=self.q(c,SESSIONS_SQL,(list(ROLES),))
                    if not left:self.session_disposition='TERMINATED_VERIFIED_ABSENT';break
        self.emit('session_disposition',dict(disposition=self.session_disposition))

    def invalidate_failure(self):
        """Owner-only safety action. No replay after uncertain administrative effects."""
        if not self.authorities:return self.invalidation
        self.invalidation='UNCERTAIN_RECONCILE'
        if self.effect_uncertain:
            self.emit('authority_invalidation_uncertain',dict(reason='PRIOR_ADMIN_EFFECT_UNCERTAIN'))
            return self.invalidation
        self.diagnostic_mode=True
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
            self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            ctl=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
            if ctl.get('global_stop')!=STOP:raise Uncertain('STOP_IDENTITY_CHANGED')
            updated=deepcopy(ctl)
            for authority in self.authorities:
                grant=updated.get('grants',{}).get(authority)
                if not grant or grant.get('execution_binding')!=self.bindings:raise Uncertain('INVALIDATION_BINDING_CHANGED')
                grant['expires_at']=0
                if authority in updated.get('bolton_exceptions',{}):updated['bolton_exceptions'][authority]['expires_at']=0
            updated['hard_stop_generation']=updated.get('hard_stop_generation',0)+1
            updated['last_hard_stop']='OPERATIONAL_SUCCESSOR_FAILED'
            self.q(c,"UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(updated),),effect=True)
            self.q(c,'REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
            self.q(c,'COMMIT',effect=True)
        with self.connection() as c:
            actual=self.q(c,'SELECT public.ingestion_acceptance_control()')[0][0]
            self.emit('authority_invalidation_readback',actual)
            if actual.get('unexpired_grants')!=0 or actual.get('hard_stop_generation')!=updated['hard_stop_generation'] or actual.get('global_stop')!=STOP:raise Uncertain('INVALIDATION_READBACK')
        self.invalidation='ACKNOWLEDGED_READBACK'
        return self.invalidation

    def diagnostics(self):
        """Read-only actual state, within remaining13/240 administrative caps."""
        self.diagnostic_mode=True
        statements=[('BEGIN READ ONLY',None),
          ("SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NULL,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY r.rolname",(list(ROLES),)),
          ('SELECT m.member::regrole::text,m.roleid::regrole::text,m.admin_option,m.inherit_option,m.set_option FROM pg_auth_members m WHERE m.member=ANY(%s::regrole[])',(list(ROLES),)),
          ('SELECT pid,usename,state FROM pg_stat_activity WHERE usename=ANY(%s)',(list(ROLES),)),
          ("SELECT public.ingestion_acceptance_control()",None),('ROLLBACK',None)]
        keys=['begin','roles','memberships','sessions','control','rollback']
        if self.role_settings_prior is not None:      # only when role configuration was captured: the actual configuration of the two logins, for reconciliation
            statements.insert(5,('SELECT rolname,rolconfig FROM pg_catalog.pg_roles WHERE rolname=ANY(%s) ORDER BY rolname',(list(ROLES),)));keys.insert(5,'role_config')
        result={}
        with self.connection() as c:
            for key,(statement,params) in zip(keys,statements):
                result[key]=self.q(c,statement,params)
                self.emit('failure_diagnostic_observed',dict(field=key,value=result[key]))
        return result

    PIPELINE_MAX_STATEMENTS=12      # bound named in the registration; the readback itself uses 9

    def pipeline_readback(self,expected,*,label):
        """The FIXED read-only owner phase. One connection, one READ ONLY transaction, no GRANT, no write, no query text, no password or verifier value (a boolean presence only). The
        observation is persisted to the audit journal BEFORE it is evaluated and before anything can proceed. Any finding, or any failed or uncertain read, raises and nothing is issued."""
        started=time.monotonic();before=self.commands
        obs={}
        with self.connection() as c:
            self.q(c,'BEGIN READ ONLY')
            obs['identity']=tuple(self.q(c,PIPELINE_IDENTITY_SQL)[0])
            raw=self.q(c,'SELECT public.ingestion_acceptance_control()')[0][0]
            obs['control']=raw if isinstance(raw,dict) else json.loads(raw)
            obs['roles']=[tuple(r) for r in self.q(c,PIPELINE_ROLES_SQL,(list(PIPELINE_LOGINS),))]
            obs['memberships']=[tuple(m) for m in self.q(c,'SELECT member::regrole::text,roleid::regrole::text FROM pg_auth_members WHERE member=ANY(%s::regrole[]) ORDER BY 1,2',(list(PIPELINE_LOGINS),))]
            obs['role_settings']={r[0]:sorted(r[1] or []) for r in self.q(c,ROLE_SETTINGS_SQL,(list(ROLES),))}
            obs['sessions']=[tuple(r) for r in self.q(c,PIPELINE_SESSIONS_SQL,(list(ROLES),))]
            try:self.verify_installed(c);obs['inventory_recognised']=True
            except ValueError:obs['inventory_recognised']=False
            self.q(c,'ROLLBACK')
        findings,notes=evaluate_pipeline_readback(obs,expected)
        record=dict(label=label,statements=self.commands-before,elapsed_seconds=round(time.monotonic()-started,3),
                    identity=list(obs['identity']),control=obs['control'],
                    roles=[[r[0],r[1],r[2],r[3].isoformat() if r[3] else None,r[4],*r[5:]] for r in obs['roles']],memberships=[list(m) for m in obs['memberships']],
                    role_settings=obs['role_settings'],sessions=[[r[0],r[1],r[2],r[3].isoformat() if r[3] else None,r[4]] for r in obs['sessions']],
                    inventory_recognised=obs['inventory_recognised'],findings=findings,notes=notes,query_text_read=False,password_values_read=False)
        self.emit('pipeline_readback',record)      # persisted (chained, synced) before the result can be acted on
        if findings:raise Uncertain('PIPELINE_READBACK_'+findings[0])
        if record['statements']>self.PIPELINE_MAX_STATEMENTS:raise Uncertain('PIPELINE_READBACK_STATEMENT_BOUND')
        return record

    OBSERVER_MAX_STATEMENTS=12      # bound named in the registration; the observation itself uses 6
    OBSERVER_MAX_DB_ACTIVE_SECONDS=20

    @staticmethod
    def project_control(ctl,now):
        """A bounded projection of the control record: the stop state, and the identity and expiry state of every grant and Bolton exception (names, expiry numbers and states only - never the bindings or
        any key list). `now` is the SERVER's clock. Two digests: of the whole record, and of the stop fields alone (the exact stop binding a policy could pin)."""
        if not isinstance(ctl,dict):raise ValueError('CONTROL_SHAPE')
        def state(expires):
            if not isinstance(expires,(int,float)) or isinstance(expires,bool) or not math.isfinite(expires):return 'UNREADABLE'
            return 'REVOKED_ZERO' if expires==0 else 'EXPIRED' if expires<=now else 'UNEXPIRED'
        import math
        def text(value,limit=100):
            return value[:limit] if isinstance(value,str) else None
        def small(value):
            try:return value if len(json.dumps(value,sort_keys=True))<=512 else 'OVERSIZE_NOT_EXPORTED'
            except (TypeError,ValueError):return 'UNREADABLE'
        def integer(value):
            return value if type(value) is int and -10**9<=value<=10**9 else None
        grants=ctl.get('grants',{});exceptions=ctl.get('bolton_exceptions',{})
        if not isinstance(grants,dict) or not isinstance(exceptions,dict):raise ValueError('CONTROL_SHAPE')
        stop=dict(global_stop=small(ctl.get('global_stop')),manual_stop=text(ctl.get('manual_stop'),512),last_hard_stop=text(ctl.get('last_hard_stop'),512),hard_stop_generation=integer(ctl.get('hard_stop_generation')))
        out=dict(**stop,council_deferred_until=small(ctl.get('council_deferred_until')),control_keys=sorted(str(k) for k in ctl),
                 grants=[dict(authority=text(a),expires_at=g.get('expires_at') if state(g.get('expires_at'))!='UNREADABLE' else None,state=state(g.get('expires_at')),source_calls=integer(g.get('source_calls')),writes=integer(g.get('writes')),login=text(g.get('login')),key_count=len(g.get('keys') or []) if isinstance(g.get('keys'),list) else None,
                              execution_binding_revision=(lambda r:r if isinstance(r,str) and re.fullmatch(r'[0-9a-f]{40}',r) else None)((g.get('execution_binding') or {}).get('revision') if isinstance(g.get('execution_binding'),dict) else None)) for a,g in sorted(grants.items()) if isinstance(g,dict)],
                 bolton_exceptions=[dict(authority=text(a),expires_at=e.get('expires_at') if state(e.get('expires_at'))!='UNREADABLE' else None,state=state(e.get('expires_at')),transport=text(e.get('transport')),hard_stop_generation=integer(e.get('hard_stop_generation')),
                                         grant_binding_matches=bool(isinstance(grants.get(a),dict) and e.get('grant_binding')=={k:v for k,v in grants[a].items() if k not in ('source_calls','writes')})) for a,e in sorted(exceptions.items()) if isinstance(e,dict)])
        out['counts']=dict(grants=len(out['grants']),grants_unexpired=sum(g['state']=='UNEXPIRED' for g in out['grants']),exceptions=len(out['bolton_exceptions']),exceptions_unexpired=sum(e['state']=='UNEXPIRED' for e in out['bolton_exceptions']))
        out['stop_state_sha256']=digest(stop);out['control_sha256']=digest(ctl)
        return out

    def control_observation(self):
        """The FIXED single-connection observation of the control record. NOTHING IS COMMITTED. The administrative identity has no table privilege, so (exactly as the accepted preflight and the accepted
        invalidation readback do) the temporary owner capability exists only inside a transaction that is ROLLED BACK, and its absence is read back. That GRANT is a statement that would write the role
        catalog if it were committed; it is the only way the record can be read, and it is reported as such. No other write, no termination, no secret, no source request. The projection is persisted to
        the audit journal before anything else can happen."""
        started=time.monotonic();before=self.commands;active_before=self.connection_active
        with self.connection() as c:
            flags=tuple(self.q(c,"SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_catalog.pg_roles WHERE rolname=current_user")[0])
            if flags!=(self.identity,self.identity,False,True,True,True):raise ValueError('MIGRATION_IDENTITY')
            self.q(c,'BEGIN',effect=True)
            self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            row=self.q(c,"SELECT outcome::jsonb,extract(epoch FROM statement_timestamp()) FROM public.ingestion_work_items WHERE key=repeat('0',64)")[0]
            self.q(c,'ROLLBACK',effect=True)
            capability=tuple(self.q(c,"SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET')")[0])
        if capability!=(False,False):raise Uncertain('TEMPORARY_OWNER_CAPABILITY_REMAINS')
        ctl=row[0] if isinstance(row[0],dict) else json.loads(row[0])
        record=dict(statements=self.commands-before,elapsed_seconds=round(time.monotonic()-started,3),database_active_seconds=round(self.connection_active-active_before,3),server_epoch=float(row[1]),
                    projection=self.project_control(ctl,float(row[1])),transient_owner_capability='ROLLED_BACK_AND_READ_BACK_ABSENT',committed_writes=0,query_text_read=False,password_values_read=False)
        self.emit('control_observation',record)      # persisted (chained, synced) before the result can be acted on
        if record['statements']>self.OBSERVER_MAX_STATEMENTS:raise Uncertain('OBSERVER_STATEMENT_BOUND')
        if record['database_active_seconds']>self.OBSERVER_MAX_DB_ACTIVE_SECONDS:raise Uncertain('OBSERVER_DB_ACTIVE_BOUND')
        return record

    def read_items(self,keys):
        """Bounded owner read of named ledger rows (state and checkpoint only). The administrative identity has no table privilege; this uses the accepted preflight technique: the temporary
        owner capability exists only inside a transaction that is ROLLED BACK, and its absence is read back."""
        keys=list(keys)
        if not 1<=len(keys)<=64:raise ValueError('READ_ITEMS_BOUND')
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
            self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            rows=self.q(c,'SELECT key,state,checkpoint FROM public.ingestion_work_items WHERE key=ANY(%s) ORDER BY key',(keys,))
            self.q(c,'ROLLBACK',effect=True)
            capability=self.q(c,"SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET')")[0]
            if tuple(capability)!=(False,False):raise Uncertain('TEMPORARY_OWNER_CAPABILITY_REMAINS')
        return {r[0]:(r[1],r[2]) for r in rows}

    AUTHORITY_NAME=re.compile(r'[A-Z0-9_]{1,100}')
    INVALIDATION_CONFIRMED=('ACKNOWLEDGED_READBACK','ALREADY_INVALIDATED_READBACK','NOT_REQUIRED_NO_AUTHORITY')

    def invalidate_authorities(self):
        """REVOCATION-ONLY end of execution authority. It is deliberately independent of every stop-state: permission to END an authority never depends on the global stop, the manual stop or
        the hard-stop generation, all of which a failed execution may legitimately have advanced (the accepted fail-safe stop replaces the manual stop and bumps the generation).

        Under the control-row lock it identifies ONLY the authorities THIS execution registered, verifies their exact execution binding and the corresponding exception binding, and sets ONLY
        the grant and exception expiry values to zero (jsonb_set on exact paths, create_missing=false). Every other control field - stops, generation, unrelated grants and exceptions - is
        left byte-for-byte as it is, which the transaction verifies from the UPDATE's own RETURNING row before COMMIT. A committed revocation is then confirmed by a readback; nothing is
        claimed confirmed before that. An uncertain COMMIT is never retried: it is reported UNCERTAIN_RECONCILE (with a read-only observation if one can be made) for reconciliation.

        Returns one of INVALIDATION_CONFIRMED, or UNCERTAIN_RECONCILE."""
        if not self.authorities:return 'NOT_REQUIRED_NO_AUTHORITY'
        names=list(dict.fromkeys(self.authorities))
        if any(not self.AUTHORITY_NAME.fullmatch(a) for a in names):raise Uncertain('INVALIDATION_AUTHORITY_NAME')
        self.invalidation='UNCERTAIN_RECONCILE'
        if self.commit_uncertain:      # an earlier attempt's persistence is unknown: never a second write, only one read-only observation, reported for reconciliation
            observation=self._observe_revoked(names)
            self.emit('authority_invalidation_uncertain',dict(authorities=names,stopped='PRIOR_COMMIT_UNCERTAIN_OBSERVE_ONLY',observation=observation))
            if observation=='REVOKED_OBSERVED':self.invalidation='ALREADY_INVALIDATED_READBACK'      # confirmed by a readback; the run itself stays uncertain through effect_uncertain
            return self.invalidation
        report=dict(authorities=names,absent=[],already=[],revoked=[],refused=[],prior_effect_uncertain=self.effect_uncertain)
        committed=False
        try:
            with self.connection() as c:
                self.q(c,'BEGIN',effect=True)
                self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
                ctl=self.q(c,"SELECT outcome::jsonb FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
                ctl=ctl if isinstance(ctl,dict) else json.loads(ctl)
                targets=[]
                for authority in names:
                    grant=(ctl.get('grants') or {}).get(authority);exception=(ctl.get('bolton_exceptions') or {}).get(authority)
                    if grant is None and exception is None:report['absent'].append(authority);continue      # nothing of ours exists under this name
                    if grant is None or grant.get('execution_binding')!=self.bindings:report['refused'].append(authority);continue      # not demonstrably ours: never touched
                    if exception is not None:
                        identity={k:v for k,v in grant.items() if k not in ('source_calls','writes')}
                        recorded=exception.get('grant_binding') or {}
                        if grant.get('expires_at')==0:      # once revoked the grant's expiry no longer equals the snapshot taken at registration; every other field must still correspond
                            identity={k:v for k,v in identity.items() if k!='expires_at'};recorded={k:v for k,v in recorded.items() if k!='expires_at'}
                        if recorded!=identity:report['refused'].append(authority);continue
                    if grant.get('expires_at')==0 and (exception is None or exception.get('expires_at')==0):report['already'].append(authority);continue
                    targets.append((authority,exception is not None))
                if targets:
                    expression="outcome::jsonb";params=[]
                    for authority,has_exception in targets:
                        expression="jsonb_set(%s,ARRAY['grants',%%s,'expires_at'],'0'::jsonb,false)"%expression;params.append(authority)
                        if has_exception:
                            expression="jsonb_set(%s,ARRAY['bolton_exceptions',%%s,'expires_at'],'0'::jsonb,false)"%expression;params.append(authority)
                    expected=deepcopy(ctl)
                    for authority,has_exception in targets:
                        expected['grants'][authority]['expires_at']=0
                        if has_exception:expected['bolton_exceptions'][authority]['expires_at']=0
                    posted=self.q(c,"UPDATE public.ingestion_work_items SET outcome=("+expression+")::json WHERE key=repeat('0',64) RETURNING outcome::jsonb",tuple(params),effect=True)[0][0]
                    posted=posted if isinstance(posted,dict) else json.loads(posted)
                    if posted!=expected:      # anything other than exactly the expiry paths changed: do not commit
                        self.q(c,'ROLLBACK',effect=True);raise Uncertain('INVALIDATION_UNEXPECTED_CHANGE')
                    report['revoked']=[a for a,_ in targets]
                self.q(c,'REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
                if targets:
                    self.q(c,'COMMIT',effect=True);committed=True
                else:self.q(c,'ROLLBACK',effect=True)
                capability=self.q(c,"SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET')")[0]
                if tuple(capability)!=(False,False):raise Uncertain('TEMPORARY_OWNER_CAPABILITY_REMAINS')
                if report['refused']:      # not ours / inconsistent: reported, never altered
                    self.emit('authority_invalidation_refused',report);return self.invalidation
                if committed or report['already'] or report['absent']:
                    confirmed=self._confirm_revoked(c,[a for a in names if a not in report['absent']])
                    report['readback']='CONFIRMED' if confirmed else 'NOT_CONFIRMED'
                    if not confirmed:self.emit('authority_invalidation_unconfirmed',report);return self.invalidation
        except Uncertain as exc:
            report['stopped']=str(exc)
            if str(exc)=='ADMIN_EFFECT_UNCERTAIN':self.commit_uncertain=True
            if committed or str(exc)=='ADMIN_EFFECT_UNCERTAIN':      # persistence unknown: ONE read-only observation, never a retry of the effect
                report['observation']=self._observe_revoked(names)
            self.emit('authority_invalidation_uncertain',report);return self.invalidation
        self.invalidation=('ACKNOWLEDGED_READBACK' if report['revoked'] else 'ALREADY_INVALIDATED_READBACK')
        self.emit('authorities_invalidated',report);return self.invalidation

    def _confirm_revoked(self,c,names):
        """Readback on the same connection AFTER the commit: the control row as committed, with the same transient owner capability as the accepted preflight, rolled back."""
        self.q(c,'BEGIN',effect=True)
        self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
        ctl=self.q(c,"SELECT outcome::jsonb FROM public.ingestion_work_items WHERE key=repeat('0',64)")[0][0]
        self.q(c,'ROLLBACK',effect=True)
        capability=self.q(c,"SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET')")[0]
        if tuple(capability)!=(False,False):raise Uncertain('TEMPORARY_OWNER_CAPABILITY_REMAINS')
        ctl=ctl if isinstance(ctl,dict) else json.loads(ctl)
        return all((ctl.get('grants') or {}).get(a,{}).get('expires_at',0)==0 and (ctl.get('bolton_exceptions') or {}).get(a,{}).get('expires_at',0)==0 for a in names)

    def _observe_revoked(self,names):
        try:
            with self.connection() as c:return 'REVOKED_OBSERVED' if self._confirm_revoked(c,names) else 'NOT_REVOKED_OBSERVED'
        except BaseException:return 'UNOBSERVABLE'

def item(identity,*,dependencies=(),checkpoint=None,limits=None,max_attempts=2):
    return dict(identity,key=digest(identity),dependencies=list(dependencies),priority=50,eligible_at=0,state='QUEUED',reason=None,next_action='CLAIM_WHEN_AUTHORISED',limits=limits or DEFAULT_LIMITS,authority=None,attempt_count=0,max_attempts=max_attempts,fence=0,owner=None,lease_until=None,phase='IDLE',checkpoint=checkpoint,outcome=None)
