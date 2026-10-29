"""Dormant Oldham adapter to existing standing mapping/provisioning mechanics.

Owner-only library: no CLI, credential lookup, policy installation or implicit
cleanup. Production entry remains held on provider comparison and exact approval.
"""
from datetime import datetime,timezone,timedelta
from app.ingestion.ledger import Denied,digest
from .oldham_authority import OldhamOwner,stop_identity
from .operational_owner import Owner,PKG
from .oldham_lifecycle import Lifecycle
from .oldham_reuse import InstalledReuse,expected_historical
from .standing_access import ROLES
from .operational_runner import STABLE_VALIDITY_DAYS
from .storage_controller import split_sql


class Provisioner(OldhamOwner):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.capture_screening_only=True;self.reuse_installed=True;self.apply_policy=False;self.apply_role_settings=False;self.pre_mint_gate=False

    def install(self):
        # install() is the legacy provisioning seam name; this adapter executes
        # memberships only, never installation.sql, functions, roles or privileges.
        if self.require_control_sha256 is None:raise Denied('OLDHAM_STANDING_CLEANUP_READBACK_REQUIRED')
        from psycopg import sql
        with self.connection() as c:
            from .oldham_lifecycle import verify_inventory
            verify_inventory(self,c,capture_screening_only=True)
            self.q(c,'BEGIN',effect=True)
            try:
                self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
                ctl=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
                stop_identity(ctl)
                if digest(ctl)!=self.require_control_sha256:raise Denied('OLDHAM_STANDING_CONTROL_CHANGED')
                historical=expected_historical(self,c)
                from .oldham_reuse import AUTHORITY
                g=ctl.get('grants',{}).get(AUTHORITY);a=ctl.get('oldham_allowances',{}).get(AUTHORITY)
                wanted_g,wanted_a=historical;wanted_g['expires_at']=0;wanted_a['revoked']=True
                if g!=wanted_g or a!=wanted_a:raise Denied('OLDHAM_STANDING_CLEANUP_READBACK_REQUIRED')
                barriers=self.q(c,"SELECT count(*) FILTER(WHERE state='PERSISTENCE_UNCERTAIN'),count(*) FILTER(WHERE phase='WRITE_INTENT') FROM public.ingestion_work_items")[0]
                if barriers!=(0,0) or any(v.get('expires_at',0)>__import__('time').time() for v in ctl.get('grants',{}).values()) or ctl.get('council_deferred_until',{}).get('oldham',0)>__import__('time').time():raise Denied('OLDHAM_STANDING_BARRIER')
                self.q(c,'REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
                life=Lifecycle(self,None,capture_screening_only=True)
                before=life.observed(c)
                if len(before['roles'])!=2 or before['memberships'] or before['sessions'] or any(r[1] or not r[2] or any(r[4:9]) or r[9]!=1 for r in before['roles']):raise Denied('OLDHAM_STANDING_PROVISION_ACCESS')
                for r,cap in life.roles.items():self.q(c,sql.SQL('GRANT {} TO {} WITH ADMIN FALSE, INHERIT TRUE, SET FALSE').format(sql.Identifier(cap),sql.Identifier(r)),effect=True)
                life.gate(c,inside_transaction=True) # provider/recovery checks BEFORE COMMIT and any password
                self.q(c,'COMMIT',effect=True);self.pre_mint_gate=True
            except BaseException:
                if not self.effect_uncertain:self.q(c,'ROLLBACK',effect=True)
                raise

    def activation_precheck(self,c):
        Lifecycle(self,None,capture_screening_only=True).gate(c)

    def script(self,c,path):
        if path!=PKG/'activate.sql':raise Denied('OLDHAM_STANDING_NO_INSTALLATION')
        from psycopg import sql
        self.activation_precheck(c)
        self.q(c,'BEGIN',effect=True)
        for role in ROLES:self.q(c,sql.SQL('ALTER ROLE {} LOGIN').format(sql.Identifier(role)),effect=True)
        self.q(c,'COMMIT',effect=True)

    def map_and_activate(self,github,*,url_factory):
        if not self.pre_mint_gate:raise Denied('OLDHAM_STANDING_PRE_MINT_GATE_REQUIRED')
        self.valid_until=datetime.now(timezone.utc).replace(microsecond=0)+timedelta(days=STABLE_VALIDITY_DAYS)
        try:return Owner.map_and_activate(self,github,url_factory=url_factory)
        finally:self.urls.clear() # owner never reuses restricted passwords for processing
