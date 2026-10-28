"""Dormant, owner-only Oldham issuance. No CLI, credential lookup or automatic source work."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import date
import json
import time

from app.ingestion.ledger import Denied,digest,bounded
from .chain_registration import capture_registration,chain_registration,screening_registration,admission_registration,completed_screening,authority_name
from .operational_owner import Owner,STOP,GENERATION3_STOP
from .scope_binding import binding_for

STOP_STATE=dict(global_stop=STOP,manual_stop=GENERATION3_STOP['manual_stop'],last_hard_stop=GENERATION3_STOP['last_hard_stop'],hard_stop_generation=3)
ROLES={'ingestion_worker_login':'ingestion_worker','ingestion_effect_login':'ingestion_effect_broker','ingestion_application_login':'ingestion_application_writer'}
SECRETS={r:'INGESTION_'+part+'_DATABASE_URL' for r,part in zip(ROLES,('WORKER','EFFECT','APPLICATION'))}

def stop_identity(control):
    projected={k:control.get(k) for k in STOP_STATE}
    if projected!=STOP_STATE or not set(STOP_STATE)<=set(control):raise Denied('OLDHAM_UNKNOWN_STOP')
    return digest(projected)

def scope_check(binding,contract):
    s=contract.scope()
    if binding!=binding_for('oldham') or s.get('council')!='oldham' or s.get('semantics')!='RECEIVED':raise Denied('OLDHAM_SCOPE')
    if not 0<=(date.fromisoformat(s['end'])-date.fromisoformat(s['start'])).days<=6:raise Denied('OLDHAM_WINDOW')
    return s

def registration_value(reg):
    value={k:deepcopy(getattr(reg,k)) for k in ('kind','authority','rows','insert','grant','bindings','root_key')} | {'targets':{k:dict(v.row) for k,v in reg.factual_contracts.items()}}
    if reg.kind=='ADMISSION':value['screening_sha256']=reg.screening_sha256
    return value

def derive(owner,binding,contract,*,revision,item_limits,root=None,receipt=None,nominees=(),rule=None,detail_targets=None,allow_test_evidence=False,phase=None,screening_rows=None):
    scope_check(binding,contract)
    if root is not None:
        from app.ingestion.listing_screening import ScreeningRule,RULE_V3
        frozen=ScreeningRule(RULE_V3,unit_threshold=10,link_related=False)
        if type(rule) is not ScreeningRule or rule.config()!=frozen.config() or rule.link_related is not False:raise Denied('OLDHAM_FROZEN_SCREENING')
    if phase not in (None,'CAPTURE','SCREENING','ADMISSION'):raise Denied('OLDHAM_PHASE')
    if phase=='CAPTURE' and root is not None or phase in ('SCREENING','ADMISSION') and root is None:raise Denied('OLDHAM_PHASE_INPUT')
    if phase=='CAPTURE':
        reg=capture_registration(owner,binding,contract,contract.scope()['start'],contract.scope()['end'],revision=revision,item_limits=item_limits)
        reg.authority=authority_name(binding,'STAGED_CAPTURE',revision);return reg
    if phase=='SCREENING':
        if nominees or detail_targets is not None:raise Denied('OLDHAM_SCREENING_NO_FACTS')
        return screening_registration(owner,binding,contract,root,receipt,rule,revision=revision,item_limits=item_limits,allow_test_evidence=allow_test_evidence)
    if phase=='ADMISSION':
        return admission_registration(owner,binding,contract,root,receipt,nominees,rule,detail_targets,revision=revision,item_limits=item_limits,screening_rows=screening_rows,allow_test_evidence=allow_test_evidence)
    if root is None:return capture_registration(owner,binding,contract,contract.scope()['start'],contract.scope()['end'],revision=revision,item_limits=item_limits)
    return chain_registration(owner,binding,contract,root,receipt,nominees,rule,detail_targets,revision=revision,item_limits=item_limits,allow_test_evidence=allow_test_evidence)

class OldhamOwner(Owner):
    """Separate entrypoint: historical Owner.register is never called or modified."""
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.issuance_deadline=None;self.issuance_statement_cap=None
        self.original_expiry=self.expiry;self.staged_capture=None;self.staged_screening=None;self.issuance_mode=None;self.staged_prior={};self.staged_expiry=None;self.admission_held=False
        self.awaiting_verification=False;self.package_started=time.monotonic();self.admin_elapsed=0.;self.admin_depth=0;self.admin_live=None;original=self.check
        def check():
            original()
            if self.issuance_deadline is not None:
                remaining=self.issuance_deadline-time.monotonic()
                if remaining<=0:raise Denied('OLDHAM_ISSUANCE_WORK_RESERVE')
                from .operational_owner import ADMIN_STATEMENT_HARD_SECONDS
                self.statement_hard_seconds=min(self.issuance_statement_cap or ADMIN_STATEMENT_HARD_SECONDS,remaining)
            active=self.admin_elapsed+(time.monotonic()-self.admin_live if self.admin_live is not None else 0)
            if active >= (240 if self.tearing_down else 210):raise Denied('OLDHAM_ADMIN_DEADLINE')
            if time.monotonic()-self.package_started >= (475 if self.tearing_down else 450):raise Denied('OLDHAM_OUTER_DEADLINE')
        self.check=check

    def caller(self,*args,**kw):
        from .oldham_allocation import Allocation,FiniteCaller
        if not hasattr(self,'_allocation'):self._allocation=Allocation(package_started=self.package_started)
        return FiniteCaller(*args,allocation=self._allocation,**kw)

    @contextmanager
    def admin_phase(self):
        if self.admin_depth==0:self.admin_live=time.monotonic()
        self.admin_depth+=1
        try:yield
        finally:
            self.admin_depth-=1
            if self.admin_depth==0:
                self.admin_elapsed+=time.monotonic()-self.admin_live;self.admin_live=None

    @contextmanager
    def connection(self):
        with self.admin_phase():
            with super().connection() as c:yield c

    def issue(self,*args,**kw):
        original_cap=self.statement_hard_seconds
        try:
            result=self._issue(*args,**kw)
            if self.issuance_deadline is not None and time.monotonic()>=self.issuance_deadline:
                self.effect_uncertain=True;raise Denied('OLDHAM_ISSUANCE_ACK_RESERVE')
            return result
        except BaseException:
            if self.awaiting_verification:self.effect_uncertain=True
            raise
        finally:
            self.issuance_deadline=None;self.issuance_statement_cap=None;self.statement_hard_seconds=original_cap

    def _issue(self,prepared,binding,contract,*,revision,item_limits,evidence,root=None,receipt=None,nominees=(),rule=None,detail_targets=None,allow_test_evidence=False,source=None,outer=None,phase=None,screening_rows=None):
        if getattr(self,'capture_screening_only',False) and phase not in ('CAPTURE','SCREENING'):raise Denied('OLDHAM_CAPTURE_SCREENING_NO_ADMISSION')
        if self.effect_uncertain:raise Denied('OLDHAM_RECONCILE_REQUIRED')
        mode='LEGACY' if phase is None else 'STAGED'
        if self.issuance_mode not in (None,mode):raise Denied('OLDHAM_ISSUANCE_MODE')
        if self.admission_held:raise Denied('OLDHAM_ADMISSION_HELD')
        if phase=='CAPTURE' and self.staged_prior or phase=='SCREENING' and set(self.staged_prior)!={'CAPTURE'} or phase=='ADMISSION' and set(self.staged_prior)!={'CAPTURE','SCREENING'}:raise Denied('OLDHAM_PHASE_ORDER')
        if revision!=self.bindings.get('revision') or len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):raise Denied('OLDHAM_CODE_BINDING')
        if source is None or outer is None:raise Denied('OLDHAM_CAPTURE_INPUTS_REQUIRED')
        projected=contract.project(source,outer,item_limits,source_bytes_limit=512*1024)
        from .oldham_allocation import capacity
        capture_seal=digest(dict(source=digest(source),outer=digest(outer),qualification=contract.qualification_sha256,scope=contract.scope()))
        records=len(projected['records']);batches=(records+4)//5
        if phase is None:capacity(records,records if root is None else len(nominees))
        elif phase=='CAPTURE':capacity(records,0)
        elif phase not in ('SCREENING','ADMISSION'):raise Denied('OLDHAM_PHASE')
        if phase is not None and (self.expiry!=self.original_expiry or (self.grant_expiry or self.expiry)>self.original_expiry):raise Denied('OLDHAM_ORIGINAL_EXPIRY')
        from .limit_reconciliation import grant_problems
        lifetime=(self.grant_expiry or self.expiry).timestamp()-time.time()
        from .limit_reconciliation import pending_grant_problems
        problems=grant_problems(binding,lifetime,batches=batches,nominees=records if root is None else len(nominees)) if phase is None else pending_grant_problems(lifetime,phase=phase,batches=batches,nominees=len(nominees))
        if problems:raise Denied('OLDHAM_INSUFFICIENT_LIFETIME')
        if phase is not None and self.staged_expiry is not None and (self.grant_expiry or self.expiry).timestamp()!=self.staged_expiry:raise Denied('OLDHAM_ORIGINAL_EXPIRY')
        expected=derive(self,binding,contract,revision=revision,item_limits=item_limits,root=root,receipt=receipt,nominees=nominees,rule=rule,detail_targets=detail_targets,allow_test_evidence=allow_test_evidence,phase=phase,screening_rows=screening_rows)
        capacity_hold=False
        if phase in ('SCREENING','ADMISSION'):
            if not self.staged_capture or self.staged_capture!=capture_seal:raise Denied('OLDHAM_STAGED_CAPTURE_REQUIRED')
            if not hasattr(self,'_allocation'):raise Denied('OLDHAM_SHARED_ALLOCATION_REQUIRED')
            need=dict(commands=80*batches+8*records,connections=2*batches+records) if phase=='SCREENING' else dict(commands=120*len(nominees),connections=4*len(nominees),nominees=len(nominees))
            if phase=='ADMISSION' and self.staged_screening!=digest(dict(root=root['key'],receipt=digest(receipt),rule=rule.config())):raise Denied('OLDHAM_STAGED_SCREENING_REQUIRED')
            capacity_hold=not self._allocation.require_remaining(need)
        bounded(registration_value(expected))
        if registration_value(expected)!=registration_value(prepared):raise Denied('OLDHAM_ALTERED_REGISTRATION')
        if set(evidence)!={'source_sha256','qualification_sha256','outer_sha256','registration_sha256'} or any(not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in evidence.values()):raise Denied('OLDHAM_EVIDENCE_BINDING')
        if evidence['source_sha256']!=digest(source) or evidence['outer_sha256']!=digest(outer):raise Denied('OLDHAM_EVIDENCE_BINDING')
        if receipt is not None and any(receipt.get(k)!=projected.get(k) for k in ('records','source_sha256','qualification_sha256','outer_supervisor','interval','council','contract')):raise Denied('OLDHAM_PROJECTED_CAPTURE')
        if evidence['registration_sha256']!=digest(registration_value(expected)) or evidence['qualification_sha256']!=contract.qualification_sha256:raise Denied('OLDHAM_EVIDENCE_BINDING')
        if receipt is not None and (evidence['outer_sha256']!=digest(receipt['outer_supervisor']) or evidence['source_sha256']!=receipt['source_sha256']):raise Denied('OLDHAM_EVIDENCE_BINDING')
        if expected.grant['expires_at']<=time.time() or expected.grant['expires_at']>time.time()+86400:raise Denied('OLDHAM_EXPIRY')
        # No grants are inserted until the complete bounded package has passed rederivation.
        with self.connection() as c:
            from .oldham_lifecycle import verify_inventory
            verify_inventory(self,c)
            self.q(c,'BEGIN',effect=True)
            try:
                self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
                ctl=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
                sid=stop_identity(ctl)
                if expected.authority in ctl['grants'] or expected.authority in ctl.get('oldham_allowances',{}):raise Denied('OLDHAM_CONSUMED')
                if self.require_control_sha256 is None or digest(ctl)!=self.require_control_sha256:raise Denied('OLDHAM_CONTROL_CHANGED')
                if phase in ('SCREENING','ADMISSION'):
                    for prior in self.staged_prior.values():
                        authority=prior['authority'];entry=ctl.get('oldham_allowances',{}).get(authority,{})
                        if entry.get('package_sha256')!=prior['package_sha256']:raise Denied('OLDHAM_PRIOR_AUTHORITY_CHANGED')
                        allowed=self.q(c,"SELECT public.ingestion_oldham_allowed(outcome::jsonb,%s,%s,%s::jsonb) FROM public.ingestion_work_items WHERE key=repeat('0',64)",(authority,expected.root_key,json.dumps(contract.scope())))[0][0]
                        if allowed is not True:raise Denied('OLDHAM_PRIOR_AUTHORITY_INACTIVE')
                if root is not None:
                    saved=self.q(c,'SELECT row_to_json(w) FROM public.ingestion_work_items w WHERE key=%s',(root['key'],))[0][0]
                    if any(saved.get(k)!=root.get(k) for k in ('key','subject','contract','revision')) or saved.get('state')!='COMPLETE' or saved.get('checkpoint')!=receipt:raise Denied('OLDHAM_SAVED_CAPTURE_CHANGED')
                if phase=='ADMISSION':
                    keys=[r['key'] for r in [*expected.batches,*expected.screens.values()]]
                    actual_rows=self.q(c,'SELECT row_to_json(w) FROM public.ingestion_work_items w WHERE key=ANY(%s) ORDER BY key',(keys,))
                    actual_rows=[r[0] for r in actual_rows]
                    submitted=sorted(screening_rows,key=lambda r:r['key'])
                    if actual_rows!=submitted:raise Denied('OLDHAM_SAVED_SCREENING_CHANGED')
                    completed_screening(expected,receipt,rule,actual_rows)
                if phase in ('SCREENING','ADMISSION'):capacity_hold=not self._allocation.require_remaining(need)
                if capacity_hold:
                    self.q(c,'ROLLBACK',effect=True)
                    flags=self.q(c,"SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET')")[0]
                    if flags!=(False,False):self.effect_uncertain=True;raise Denied('OLDHAM_TEMPORARY_CAPABILITY')
                    self.admission_held=phase=='ADMISSION'
                    return dict(outcome='SCREENING_COMPLETED_ADMISSION_HELD_CAPACITY' if phase=='ADMISSION' else 'SCREENING_HELD_CAPACITY',admission='NOT_ISSUED',source_calls=0,writes=0)
                if phase in ('SCREENING','ADMISSION'):
                    self.issuance_statement_cap=self.statement_hard_seconds
                    self.issuance_deadline=self._allocation.deadline-45*len(nominees) if phase=='ADMISSION' else self._allocation.deadline
                # Effects cannot borrow administrative closure/reporting capacity.
                # Remaining insertion and two-connection acknowledgement envelope.
                if self.commands+len(expected.insert)+10>200 or self.connections+1>11:raise Denied('OLDHAM_ADMIN_ISSUANCE_CAPACITY')
                for row in expected.insert:self.q(c,'INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)',(json.dumps(row),),effect=True)
                grant=deepcopy(expected.grant)
                allowance=dict(grant_binding={k:v for k,v in grant.items() if k not in ('source_calls','writes')},source_cap=grant['source_calls'],write_cap=grant['writes'],revoked=False,expires_at=grant['expires_at'],stop_sha256=sid,scope=scope_check(binding,contract),evidence=evidence,targets={k:dict(v.row) for k,v in expected.factual_contracts.items()})
                package=dict(authority=expected.authority,registration=registration_value(expected),scope=allowance['scope'],stop=STOP_STATE,evidence=evidence,targets=allowance['targets'])
                bounded(package)
                package_sha=self.q(c,"SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(json.dumps(package),))[0][0]
                grant['oldham_package_sha256']=package_sha
                allowance.update(package=package,package_sha256=package_sha,grant_binding={k:v for k,v in grant.items() if k not in ('source_calls','writes')})
                ctl['grants'][expected.authority]=grant;ctl.setdefault('oldham_allowances',{})[expected.authority]=allowance
                # Track intent BEFORE commit; an uncertain acknowledgement cannot silently issue again.
                self.authorities.append(expected.authority);self.invalidation='REQUIRED'
                self.q(c,"UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),),effect=True)
                self.q(c,'REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
                self.q(c,'COMMIT',effect=True);self.awaiting_verification=True
            except BaseException:
                self.issuance_deadline=None;self.statement_hard_seconds=self.issuance_statement_cap;self.issuance_statement_cap=None
                if not self.effect_uncertain:self.q(c,'ROLLBACK',effect=True)
                raise
            flags=self.q(c,"SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET')")[0]
            if flags!=(False,False):
                self.effect_uncertain=True;raise Denied('OLDHAM_TEMPORARY_CAPABILITY')
        try:
            with self.connection() as c:
                self.q(c,'BEGIN',effect=True)
                self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
                actual=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)")[0][0]
                if actual['grants'].get(expected.authority)!=grant or actual.get('oldham_allowances',{}).get(expected.authority)!=allowance:raise Denied('OLDHAM_COMMITTED_READBACK')
                self.q(c,'ROLLBACK',effect=True)
        except BaseException:
            self.effect_uncertain=True;raise
        self.emit('oldham_authority_committed',dict(authority=expected.authority,registration_sha256=evidence['registration_sha256'],stop_sha256=sid))
        self.original_control=deepcopy(actual);self.require_control_sha256=digest(actual)
        self.issuance_mode=mode
        if phase is not None:self.staged_prior[phase]=dict(authority=expected.authority,package_sha256=package_sha)
        if phase=='CAPTURE':self.staged_capture=capture_seal;self.staged_expiry=expected.grant['expires_at']
        if phase=='SCREENING':self.staged_screening=digest(dict(root=root['key'],receipt=digest(receipt),rule=rule.config()))
        self.awaiting_verification=False
        return expected

    def revoke(self):
        try:return self._revoke()
        except BaseException:
            if self.awaiting_verification:self.effect_uncertain=True
            raise

    def _revoke(self):
        if self.effect_uncertain:raise Denied('OLDHAM_RECONCILE_REQUIRED')
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
            self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            ctl=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
            for a in self.authorities:
                if a not in ctl.get('oldham_allowances',{}) or a not in ctl['grants']:raise Denied('OLDHAM_RECONCILE_REQUIRED')
                ctl['grants'][a]['expires_at']=0;ctl['oldham_allowances'][a]['revoked']=True
            self.q(c,"UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),),effect=True)
            self.q(c,'REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
            self.q(c,'COMMIT',effect=True);self.awaiting_verification=True
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
            self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            ctl=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)")[0][0]
            ok=all(ctl['grants'][a]['expires_at']==0 and ctl['oldham_allowances'][a]['revoked'] is True for a in self.authorities)
            self.q(c,'ROLLBACK',effect=True)
            if not ok:
                self.effect_uncertain=True;raise Denied('OLDHAM_REVOCATION_UNCERTAIN')
        self.invalidation='VERIFIED';self.awaiting_verification=False
