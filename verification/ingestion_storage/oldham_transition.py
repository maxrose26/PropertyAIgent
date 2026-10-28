"""Closed preparation phases of the existing Oldham command. No connection on import.

No compensating rollback is executed here. All calls use the existing Owner
accounting/uncertainty gate and the existing GitHub acknowledgement gate.
"""
import hashlib
from psycopg import sql
from app.ingestion.ledger import Denied,digest
from . import oldham_policy
from .operational_owner import Owner
from .operational_publication import Uncertain
from .screening_v3_worker_sql import READBACK_SQL
from .oldham_authority import stop_identity
from .oldham_lifecycle import verify_inventory
from .storage_controller import split_sql

OPERATION='CAPTURE_SCREENING_ONLY'
PREDECESSOR='GENERATION3_SCREENING_V3_APPLIED'
RISK='ACCEPT_POSSIBLE_PROVIDER_SCRAM_RETENTION_WORKER_EFFECT_ONCE'


def texts(predecessor):
    if predecessor!=PREDECESSOR:raise Denied('OLDHAM_TRANSITION_PREDECESSOR')
    return oldham_policy.installation_script(),oldham_policy.rollback_script(predecessor)


def validate_inspection(value,predecessor):
    texts(predecessor)
    if (value.get('status')!='OLDHAM_READONLY_INSPECTION_COMPLETE'
        or value.get('outcome',{}).get('closure')!='VERIFIED'
        or value.get('inspection',{}).get('functions',{}).get('state')!='RECOGNISED_PRE_OLDHAM'
        or value['inspection']['functions'].get('recognised')!=predecessor
        or value['inspection']['functions'].get('owner_and_search_path_as_reviewed') is not True):
        raise Denied('OLDHAM_COMPLETED_INSPECTION_REQUIRED')


class Transition:
    def __init__(self,operation):
        self.op=operation;self.o=operation.owner;self.life=operation.life
        self.sealed=operation.p['transition'];self.retired=False;self.installed=False

    def predecessor(self,c):
        expected=Owner.screening_v3_inventory()
        rows=self.o.q(c,"SELECT p.proname,p.prosrc,pg_get_userbyid(p.proowner),p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname=ANY(%s)",(list(expected)+['ingestion_oldham_allowed'],))
        observed={name:hashlib.sha256(body.encode()).hexdigest() for name,body,_,_ in rows}
        wanted={name:hashlib.sha256(body.encode()).hexdigest() for name,body in expected.items()}
        self.o.emit('oldham_install_predecessor',dict(observed=observed,expected=wanted))
        if (len(rows)!=len(expected) or observed!=wanted
            or any(who!='ingestion_storage_owner' or cfg!=['search_path=pg_catalog'] for _,_,who,cfg in rows)):
            raise Denied('OLDHAM_INSTALL_PREDECESSOR_CHANGED')

    def barriers(self,c):
        ctl=self.o.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
        sid=stop_identity(ctl)
        if sid!=self.op.p['control_stop_sha256']:raise Denied('OLDHAM_INSTALL_STOP_CHANGED')
        if self.o.require_control_sha256 is not None and digest(ctl)!=self.o.require_control_sha256:raise Denied('OLDHAM_INSTALL_CONTROL_CHANGED')
        counts=self.o.q(c,"SELECT count(*) FILTER (WHERE state='PERSISTENCE_UNCERTAIN'),count(*) FILTER (WHERE phase='WRITE_INTENT') FROM public.ingestion_work_items")[0]
        active=any(g.get('expires_at',0)>__import__('time').time() for g in ctl.get('grants',{}).values())
        deferred=ctl.get('council_deferred_until',{}).get('oldham',0)>__import__('time').time()
        self.o.emit('oldham_install_barriers',dict(persistence_uncertain=counts[0],write_intents=counts[1],active_grants=active,oldham_deferred=deferred,control_sha256=digest(ctl)))
        if counts!=(0,0) or active or deferred:raise Denied('OLDHAM_INSTALL_BARRIER')
        # The capability-free inspection cannot expose the full control digest.
        # Bind its first actual observation here, then require it unchanged at
        # installation and every existing issuance/preflight boundary.
        self.o.require_control_sha256=digest(ctl)

    def capabilities_absent(self,c):
        flags=self.o.q(c,READBACK_SQL['capability_absent'])[0]
        self.o.emit('oldham_install_capabilities',dict(flags=flags))
        if flags!=(False,False,False,False,False):raise Uncertain('OLDHAM_INSTALL_CAPABILITY_READBACK')

    def check_before_retirement(self,c):
        identity=self.o.q(c,"SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user")[0]
        self.o.emit('oldham_transition_owner_identity',dict(identity=identity[0],session_user=identity[1],superuser=identity[2],createrole=identity[3],createdb=identity[4],bypassrls=identity[5]))
        if tuple(identity)!=(self.o.identity,self.o.identity,False,True,True,True):raise Denied('OLDHAM_TRANSITION_OWNER_IDENTITY')
        self.capabilities_absent(c)
        self.o.q(c,'BEGIN',effect=True)
        try:
            self.o.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            self.predecessor(c);self.barriers(c)
        finally:
            if not self.o.effect_uncertain:self.o.q(c,'ROLLBACK',effect=True)
        self.capabilities_absent(c)

    def retire(self):
        if self.sealed['external_consumers_confirmed'] is not True or self.sealed['retire_standing'] is not True:
            raise Denied('OLDHAM_RETIREMENT_CONFIRMATION_REQUIRED')
        names=self.op.github.names()
        if 'DATABASE_URL' not in names or any(n in names for n in ('INGESTION_APPLICATION_DATABASE_URL','INGESTION_STORAGE_DATABASE_URL')):
            raise Denied('OLDHAM_RETIREMENT_SECRET_STATE')
        try:
            with self.o.connection() as c:
                self.check_before_retirement(c)
                before=self.life.observed(c)
                self.o.emit('oldham_retirement_before_access',self.public_access(before))
                if (len(before['roles'])!=2 or before['sessions']
                    or any(any(row[4:9]) or row[9]!=1 for row in before['roles'])
                    or any(m[1]!=self.life.roles.get(m[0]) or tuple(m[2:])!=(False,True,False) for m in before['memberships'])):
                    raise Denied('OLDHAM_RETIREMENT_ACCESS_STATE')
                self.o.q(c,'BEGIN',effect=True)
                for role,cap in self.life.roles.items():
                    self.o.q(c,sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL').format(sql.Identifier(role)),effect=True)
                    self.o.q(c,sql.SQL('REVOKE {} FROM {}').format(sql.Identifier(cap),sql.Identifier(role)),effect=True)
                self.o.q(c,'COMMIT',effect=True)
                actual=self.life.observed(c)
                self.o.emit('oldham_standing_disabled',self.public_access(actual))
                if len(actual['roles'])!=2 or any(r[1] or not r[2] for r in actual['roles']) or actual['memberships'] or actual['sessions']:
                    raise Uncertain('OLDHAM_RETIREMENT_READBACK')
            for name in self.life.secrets.values():
                if name in names:self.op.github.call('DELETE','repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets/'+name)
            after=self.op.github.names()
            if 'DATABASE_URL' not in after or any(name in after for name in self.life.secrets.values()):raise Uncertain('OLDHAM_RETIREMENT_SECRET_READBACK')
            self.retired=True;self.o.emit('oldham_retirement_closed',dict(logins=list(self.life.roles),sessions='ABSENT',secrets='ABSENT',standing_copies='INVALIDATED'))
        except BaseException:
            self.life.state='UNCERTAIN';raise

    @staticmethod
    def public_access(value):
        return dict(roles=[dict(login=r[0],canlogin=r[1],password_removed=r[2],valid_until=r[3].isoformat() if r[3] else None,restricted_flags=list(r[4:9]),connection_limit=r[9]) for r in value['roles']],
            memberships=value['memberships'],sessions=[[r[0],r[1],r[2],r[3].isoformat()] for r in value['sessions']])

    def install(self):
        if not self.retired:raise Denied('OLDHAM_RETIREMENT_REQUIRED')
        install,_=texts(self.sealed['predecessor'])
        # The existing ceremony itself removes owner/schema capabilities before
        # COMMIT. Checks run after its self-grant and before schema/function DDL.
        statements=split_sql(install)
        try:
            with self.o.connection() as c:
                for statement in statements:
                    if statement.strip().startswith('GRANT CREATE ON SCHEMA'):
                        self.predecessor(c);self.barriers(c)
                    self.o.q(c,statement,effect=True)
                verify_inventory(self.o,c,capture_screening_only=True)
                helper=self.o.q(c,"SELECT prosecdef,provolatile,pg_get_function_identity_arguments(oid) FROM pg_proc WHERE oid='public.ingestion_oldham_allowed(jsonb,text,text,jsonb)'::regprocedure")[0]
                self.o.emit('oldham_install_helper_readback',dict(security_definer=helper[0],volatility=helper[1],arguments=helper[2]))
                if helper!=(True,'s','ctl jsonb, authority text, work_key text, subject jsonb'):raise Uncertain('OLDHAM_INSTALL_HELPER_READBACK')
                self.capabilities_absent(c)
                self.installed=True
                self.o.emit('oldham_install_committed',dict(installation_sha256=hashlib.sha256(install.encode()).hexdigest(),rollback_executed=False))
        except BaseException:
            # A known pre-COMMIT refusal is aborted by connection disposal.
            # Uncertain effects latch Owner; no compensating script is invoked.
            self.life.state='UNCERTAIN';raise

    def run(self):
        with self.o.admin_phase():self.retire();self.install()
        self.op.result['transition']=dict(retirement='VERIFIED',installation='VERIFIED',predecessor=self.sealed['predecessor'],rollback='NOT_EXECUTED')
