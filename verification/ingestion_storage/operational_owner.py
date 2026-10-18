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

PKG=Path('docs/design/ingestion-operational-required-20261018')
WORKER=Path('docs/design/ingestion-operational-20261016/worker.sql')
STOP={'reason':'CONSUMED_SALFORD_GLOBAL_STOP','run':'38884069913'}
STOP_SHA='a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e'
SCOPE=dict(kind='DISCOVERY_SCOPE',council='bolton',start='2026-10-16',end='2026-10-16',semantics='RECEIVED')
ROLES={'ingestion_worker_login':'ingestion_worker','ingestion_effect_login':'ingestion_effect_broker'}
SECRETS={'ingestion_worker_login':'INGESTION_WORKER_DATABASE_URL','ingestion_effect_login':'INGESTION_EFFECT_DATABASE_URL'}

class Owner:
    def __init__(self,connector,emit,check,*,identity='postgres',expiry,bindings):
        self.connector=connector;self.emit=emit;self.check=check;self.identity=identity;self.expiry=expiry;self.bindings=bindings
        self.connections=0;self.opened=0;self.closed=0;self.connection_active=0.0;self.effect_uncertain=False;self.invalidation='NOT_REQUIRED_NO_AUTHORITY';self.expected_generation=0;self.reuse_installed=False;self.apply_policy=True;self.baseline_control_sha256='0d829597f1422fef0af13920d5749c5751adf6d896588f379c400db7b3fa27cf';self.commands=0;self.returned_bytes=0;self.active=0;self.urls={};self.original_control=None;self.authorities=[];self.diagnostic_mode=False;self.tearing_down=False

    @contextmanager
    def connection(self):
        self.check()
        if self.connections>=(13 if self.diagnostic_mode else 11):raise ValueError('ADMIN_CONNECTION_BOUND')
        self.connections+=1;self.emit('admin_connection_intent',dict(ordinal=self.connections))
        c=None;began=time.monotonic()
        try:
            c=self.connector();self.connection_active+=time.monotonic()-began;self.opened+=1;self.emit('admin_connection_open',dict(ordinal=self.connections))
            yield c
        except BaseException:
            if c is None:self.connection_active+=time.monotonic()-began
            raise
        finally:
            if c is not None:
                closing=time.monotonic();c.close();self.connection_active+=time.monotonic()-closing
                if not c.closed:raise Uncertain('ADMIN_CLOSE_UNCERTAIN')
                self.closed+=1;self.emit('admin_connection_closed',dict(ordinal=self.connections))

    def q(self,c,statement,params=None,*,effect=False):
        self.check()
        cap=240 if self.diagnostic_mode else 232 if self.tearing_down else 200
        if self.commands>=cap:raise ValueError('ADMIN_COMMAND_BOUND')
        self.commands+=1
        if effect:self.emit('admin_effect_intent',dict(command=self.commands))
        started=time.monotonic()
        try:
            cur=c.execute(statement,params)
            rows=cur.fetchall() if cur.description else []
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
        return dict(connections=self.connections,connections_opened=self.opened,connections_closed=self.closed,commands=self.commands,returned_data_value_bytes=self.returned_bytes,database_active_seconds=self.active+self.connection_active,uncertain_effect=self.effect_uncertain)

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
            if roles!=[('ingestion_storage_login',False,True),('ingestion_worker_login',False,True)]:raise ValueError('ACCEPTED_STORAGE_ACCESS_CHANGED')
            if self.q(c,"SELECT count(*) FROM pg_auth_members WHERE member=ANY(ARRAY['ingestion_worker_login'::regrole,'ingestion_storage_login'::regrole])")[0][0]!=0:raise ValueError('STORAGE_MEMBERSHIP_CHANGED')
            if self.q(c,"SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)",(['ingestion_worker_login','ingestion_storage_login','ingestion_effect_login'],))[0][0]:raise ValueError('PREEXISTING_RUNTIME_SESSIONS')
            if self.reuse_installed:
                self.verify_installed(c)
                return
            if self.q(c,"SELECT to_regprocedure('public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'),EXISTS(SELECT 1 FROM pg_roles WHERE rolname='ingestion_effect_login')")[0]!=(None,False):raise ValueError('INSTALLATION_ALREADY_EXISTS_NO_REPLAY')

    def verify_installed(self,c):
        # Compare the retained reviewed function bodies, owner and search path;
        # activation separately reuses the exact effective ACL boundary.
        expected={}
        for match in re.finditer(r'CREATE (?:OR REPLACE )?FUNCTION public\.(\w+)\(.*?\).*?AS \$(\w*)\$(.*?)\$\2\$;',WORKER.read_text(),re.S):
            expected[match[1]]=match[3]
        if len(expected)<5:raise ValueError('REVIEWED_FUNCTION_INVENTORY')
        rows=self.q(c,"SELECT p.proname,p.prosrc,r.rolname,p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner WHERE n.nspname='public' AND p.proname=ANY(%s) ORDER BY p.proname",(list(expected),))
        self.emit('installed_function_inventory',dict(hashes={n:hashlib.sha256(body.encode()).hexdigest() for n,body,_,_ in rows}))
        if len(rows)!=len(expected) or any(body!=expected.get(n) or owner!='ingestion_storage_owner' or config!=['search_path=pg_catalog'] for n,body,owner,config in rows):raise ValueError('INSTALLED_FUNCTION_CONTENT_CHANGED')
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
            gate=(PKG/'activate.sql').read_text().split('ALTER ROLE ingestion_worker_login LOGIN;')[0].replace('BEGIN;','BEGIN READ ONLY;',1)+'ROLLBACK;'
            for statement in split_sql(gate):self.q(c,statement)

    def map_and_activate(self,github,*,url_factory):
        names=github.names()
        if 'DATABASE_URL' not in names or 'INGESTION_STORAGE_DATABASE_URL' in names or any(n in names for n in SECRETS.values()):raise ValueError('EXACT_EMPTY_OPERATIONAL_MAPPINGS_REQUIRED')
        with self.connection() as c:
            for role,name in SECRETS.items():
                password=secrets.token_urlsafe(48)
                verifier=c.pgconn.encrypt_password(password.encode(),role.encode(),algorithm=b'scram-sha-256').decode()
                self.q(c,'BEGIN',effect=True)
                self.q(c,sql.SQL('ALTER ROLE {} PASSWORD {} VALID UNTIL {}').format(sql.Identifier(role),sql.Literal(verifier),sql.Literal(self.expiry.isoformat())),effect=True)
                self.q(c,'COMMIT',effect=True)
                url=url_factory(role,password);github.put_secret(name,url);self.urls[role]=url
                del password,verifier,url
            self.script(c,PKG/'activate.sql')

    def register(self,items,authority,*,capture_key,source_calls,prepared=()):
        bindings={x['key']:{k:x[k] for k in ('subject','task','contract','revision')} for x in [*items,*prepared]}
        grant=dict(keys=sorted(bindings),contracts=sorted({x['contract'] for x in [*items,*prepared]}),expires_at=self.expiry.timestamp(),source_calls=source_calls,writes=0,login='ingestion_worker_login',effect_login='ingestion_effect_login',workers=['required_once'],bindings=bindings,detail_source_keys=[],capture_key=capture_key,capture_only=True,execution_binding=self.bindings,
                   completion_outcomes={'DISCOVERY':['ENUMERATED_METADATA_RETAINED'],'LISTING_METADATA':['BATCH_SCREENED'],'SCREENING':['SCREENED','ALREADY_KNOWN','INSUFFICIENT_EVIDENCE','SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH','DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE']})
        # Owner-only fixed insertion/issuance. No runtime principal receives the
        # owner, issuer, barrier or recovery memberships used here.
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
            self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            ctl=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
            if ctl['global_stop']!=STOP or ctl.get('manual_stop')!='STORAGE_TEST_STOP' or ctl.get('hard_stop_generation',0)!=self.expected_generation or authority in ctl['grants']:raise Uncertain('OWNER_REGISTRATION_STATE_CHANGED')
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
        self.tearing_down=True
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
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
            sessions=self.q(c,'SELECT pid,usename,state FROM pg_stat_activity WHERE usename=ANY(%s)',(list(ROLES),))
            self.emit('teardown_observed',dict(roles=roles,memberships=memberships,sessions=sessions))
            if roles!=[(r,False,True) for r in sorted(ROLES)] or memberships or sessions:raise Uncertain('TEARDOWN_RECONCILE')
        for name in SECRETS.values():github.call('DELETE','repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets/'+name)
        names=github.names();self.emit('teardown_secret_names_observed',dict(names={n:n in names for n in SECRETS.values()},database_url_present='DATABASE_URL' in names))
        if any(n in names for n in SECRETS.values()) or 'DATABASE_URL' not in names:raise Uncertain('TEARDOWN_SECRET_RECONCILE')
        self.urls.clear()

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
        result={}
        with self.connection() as c:
            for key,(statement,params) in zip(('begin','roles','memberships','sessions','control','rollback'),statements):
                result[key]=self.q(c,statement,params)
                self.emit('failure_diagnostic_observed',dict(field=key,value=result[key]))
        return result

def item(identity,*,dependencies=(),checkpoint=None,limits=None,max_attempts=2):
    return dict(identity,key=digest(identity),dependencies=list(dependencies),priority=50,eligible_at=0,state='QUEUED',reason=None,next_action='CLAIM_WHEN_AUTHORISED',limits=limits or DEFAULT_LIMITS,authority=None,attempt_count=0,max_attempts=max_attempts,fence=0,owner=None,lease_until=None,phase='IDLE',checkpoint=checkpoint,outcome=None)
