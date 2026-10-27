"""Three exact pre-existing logins. No role creation, privilege widening or secret discovery."""
from datetime import datetime,timezone
from pathlib import Path
import secrets,time
from psycopg import sql
from app.ingestion.ledger import Denied
from .operational_publication import Uncertain
from .oldham_authority import ROLES,SECRETS
from .storage_controller import split_sql
from . import oldham_policy

ACTIVATION=Path('docs/design/ingestion-operational-acceptance-20261016/activate.sql')


def verify_inventory(owner,c):
    """Recognise exactly the combined v3/partial worker plus this one substitution."""
    definitions={'ingestion_worker_step':oldham_policy.replacement().split('AS $fn$',1)[1].split('$fn$;',1)[0],
                 'ingestion_oldham_allowed':oldham_policy.FUNCTION.split('AS $oldham$',1)[1].split('$oldham$;',1)[0]}
    from .operational_owner import Owner
    definitions={**Owner.screening_v3_inventory(),**definitions}
    rows=owner.q(c,"SELECT p.proname,p.prosrc,pg_get_userbyid(p.proowner),p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname=ANY(%s)",(list(definitions),))
    if len(rows)!=len(definitions) or any(n not in definitions or body!=definitions[n] or who!='ingestion_storage_owner' or cfg!=['search_path=pg_catalog'] for n,body,who,cfg in rows):raise Denied('OLDHAM_POLICY_INVENTORY')
    privileges=owner.q(c,"SELECT has_function_privilege('ingestion_worker_login','public.ingestion_oldham_allowed(jsonb,text,text,jsonb)','EXECUTE'),has_function_privilege('ingestion_effect_login','public.ingestion_oldham_allowed(jsonb,text,text,jsonb)','EXECUTE'),has_function_privilege('ingestion_application_login','public.ingestion_oldham_allowed(jsonb,text,text,jsonb)','EXECUTE')")[0]
    if privileges!=(False,False,False):raise Denied('OLDHAM_POLICY_ACL')

class Lifecycle:
    def __init__(self,owner,github):self.owner=owner;self.github=github;self.urls={};self.state='UNUSED'
    def safe(self):
        if self.owner.effect_uncertain or self.state in ('UNCERTAIN','CLOSED'):raise Denied('OLDHAM_LIFECYCLE_RECONCILE')
    def observed(self,c):
        o=self.owner
        if o.q(c,"SELECT pg_has_role(current_user,'pg_read_all_stats','USAGE')")[0][0] is not True:raise Denied('OLDHAM_SESSION_VISIBILITY_REQUIRED')
        roles=o.q(c,"SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NULL,r.rolvaliduntil,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication,r.rolconnlimit FROM pg_roles r JOIN pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY 1",(list(ROLES),))
        members=o.q(c,"SELECT m.member::regrole::text,m.roleid::regrole::text,m.admin_option,m.inherit_option,m.set_option FROM pg_auth_members m WHERE m.member=ANY(%s::regrole[]) ORDER BY 1,2",(list(ROLES),))
        sessions=o.q(c,'SELECT pid,usename,state,backend_start FROM pg_stat_activity WHERE usename=ANY(%s) ORDER BY pid',(list(ROLES),))
        return dict(roles=roles,memberships=members,sessions=sessions)
    def activate(self,*,url_factory):
        self.safe();o=self.owner
        if self.state!='UNUSED':raise Denied('OLDHAM_LIFECYCLE_USED')
        expiry=o.valid_until or o.expiry;remaining=expiry.timestamp()-time.time()
        if not 0<remaining<=86400:raise Denied('OLDHAM_CREDENTIAL_EXPIRY')
        names=self.github.names()
        if 'DATABASE_URL' not in names or any(n in names for n in SECRETS.values()) or 'INGESTION_STORAGE_DATABASE_URL' in names:raise Denied('OLDHAM_SECRET_STATE')
        try:
            with o.connection() as c:
                verify_inventory(o,c)
                before=self.observed(c)
                if len(before['roles'])!=3 or before['sessions'] or any(r[1] or not r[2] or any(r[4:9]) or r[9]!=1 for r in before['roles']):raise Denied('OLDHAM_INITIAL_ACCESS')
                # Only already-reviewed capabilities may be restored; unexpected memberships refuse.
                if any(m[1]!=ROLES.get(m[0]) or tuple(m[2:])!=(False,True,False) for m in before['memberships']):raise Denied('OLDHAM_MEMBERSHIPS')
                o.q(c,'BEGIN',effect=True)
                for role,cap in ROLES.items():o.q(c,sql.SQL('GRANT {} TO {} WITH ADMIN FALSE, INHERIT TRUE, SET FALSE').format(sql.Identifier(cap),sql.Identifier(role)),effect=True)
                o.q(c,'COMMIT',effect=True)
                gate=ACTIVATION.read_text().split('ALTER ROLE ingestion_worker_login LOGIN;')[0]+'ROLLBACK;'
                for q in split_sql(gate):o.q(c,q)
                for role,name in SECRETS.items():
                    password=secrets.token_urlsafe(48)
                    verifier=c.pgconn.encrypt_password(password.encode(),role.encode(),algorithm=b'scram-sha-256').decode()
                    o.q(c,'BEGIN',effect=True)
                    o.q(c,sql.SQL('ALTER ROLE {} PASSWORD {} VALID UNTIL {}').format(sql.Identifier(role),sql.Literal(verifier),sql.Literal(expiry.isoformat())),effect=True)
                    o.q(c,'COMMIT',effect=True)
                    url=url_factory(role,password);self.github.put_secret(name,url);self.urls[role]=url
                    del password,verifier,url
                o.q(c,'BEGIN',effect=True)
                for role in ROLES:o.q(c,sql.SQL('ALTER ROLE {} LOGIN').format(sql.Identifier(role)),effect=True)
                o.q(c,'COMMIT',effect=True)
                after=self.observed(c)
                expected_members=[(r,cap,False,True,False) for r,cap in sorted(ROLES.items())]
                if len(after['roles'])!=3 or after['memberships']!=expected_members or after['sessions'] or any(not r[1] or r[2] or r[3]!=expiry or any(r[4:9]) or r[9]!=1 for r in after['roles']):raise Uncertain('OLDHAM_ACTIVATION_READBACK')
                o.emit('oldham_three_login_activation',dict(logins=sorted(ROLES),expiry=expiry.isoformat()))
            self.state='ACTIVE';return self.urls
        except BaseException:
            self.state='UNCERTAIN';raise
    def teardown(self):
        # No automatic compensation after uncertain mutations. Caller must reconcile first.
        self.safe();o=self.owner;o.tearing_down=True
        try:
            o.revoke()
            with o.connection() as c:
                o.q(c,'BEGIN',effect=True)
                for role,cap in ROLES.items():
                    o.q(c,sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL').format(sql.Identifier(role)),effect=True)
                    o.q(c,sql.SQL('REVOKE {} FROM {}').format(sql.Identifier(cap),sql.Identifier(role)),effect=True)
                o.q(c,'COMMIT',effect=True)
                observed=self.observed(c)
                disabled=len(observed['roles'])==3 and all(not r[1] and r[2] for r in observed['roles']) and not observed['memberships']
                o.emit('oldham_three_login_disabled',dict(disabled=disabled,sessions=[[r[0],r[1],r[2]] for r in observed['sessions']]))
                if not disabled:raise Uncertain('OLDHAM_DISABLE_READBACK')
                # Do not terminate unexpected sessions or obtain monitoring privileges.
                sessions=observed['sessions']
                for _ in range(3):
                    if not sessions:break
                    o.sleep(0.5);sessions=o.q(c,'SELECT pid,usename,state,backend_start FROM pg_stat_activity WHERE usename=ANY(%s) ORDER BY pid',(list(ROLES),))
            for name in SECRETS.values():self.github.call('DELETE','repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets/'+name)
            names=self.github.names()
            if any(n in names for n in SECRETS.values()) or 'DATABASE_URL' not in names:raise Uncertain('OLDHAM_SECRET_READBACK')
            self.urls.clear()
            if sessions:raise Uncertain('OLDHAM_SESSIONS_REMAIN')
            self.state='CLOSED';o.emit('oldham_three_login_teardown',dict(access='DISABLED',sessions='ABSENT',temporary_secrets='ABSENT',cleanup='CLOSED'))
        except BaseException:
            self.state='UNCERTAIN';raise
