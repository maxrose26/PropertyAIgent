"""Dormant, owner-only Oldham issuance. No CLI, credential lookup or automatic source work."""
from copy import deepcopy
from datetime import date
import json
import time

from app.ingestion.ledger import Denied,digest
from .chain_registration import capture_registration,chain_registration
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
    return {k:deepcopy(getattr(reg,k)) for k in ('kind','authority','rows','insert','grant','bindings','root_key')} | {'targets':{k:dict(v.row) for k,v in reg.factual_contracts.items()}}

def derive(owner,binding,contract,*,revision,item_limits,root=None,receipt=None,nominees=(),rule=None,detail_targets=None,allow_test_evidence=False):
    scope_check(binding,contract)
    if root is None:return capture_registration(owner,binding,contract,contract.scope()['start'],contract.scope()['end'],revision=revision,item_limits=item_limits)
    return chain_registration(owner,binding,contract,root,receipt,nominees,rule,detail_targets,revision=revision,item_limits=item_limits,allow_test_evidence=allow_test_evidence)

class OldhamOwner(Owner):
    """Separate entrypoint: historical Owner.register is never called or modified."""
    def issue(self,prepared,binding,contract,*,revision,item_limits,evidence,root=None,receipt=None,nominees=(),rule=None,detail_targets=None,allow_test_evidence=False,source=None,outer=None):
        if self.effect_uncertain:raise Denied('OLDHAM_RECONCILE_REQUIRED')
        if revision!=self.bindings.get('revision') or len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):raise Denied('OLDHAM_CODE_BINDING')
        if source is None or outer is None:raise Denied('OLDHAM_CAPTURE_INPUTS_REQUIRED')
        projected=contract.project(source,outer,item_limits,source_bytes_limit=512*1024)
        from .oldham_allocation import capacity
        capacity(len(projected['records']),len(projected['records']) if root is None else len(nominees))
        expected=derive(self,binding,contract,revision=revision,item_limits=item_limits,root=root,receipt=receipt,nominees=nominees,rule=rule,detail_targets=detail_targets,allow_test_evidence=allow_test_evidence)
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
                if root is not None:
                    saved=self.q(c,'SELECT row_to_json(w) FROM public.ingestion_work_items w WHERE key=%s',(root['key'],))[0][0]
                    if any(saved.get(k)!=root.get(k) for k in ('key','subject','contract','revision')) or saved.get('state')!='COMPLETE' or saved.get('checkpoint')!=receipt:raise Denied('OLDHAM_SAVED_CAPTURE_CHANGED')
                for row in expected.insert:self.q(c,'INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)',(json.dumps(row),),effect=True)
                grant=deepcopy(expected.grant)
                allowance=dict(grant_binding={k:v for k,v in grant.items() if k not in ('source_calls','writes')},source_cap=grant['source_calls'],write_cap=grant['writes'],revoked=False,expires_at=grant['expires_at'],stop_sha256=sid,scope=scope_check(binding,contract),evidence=evidence,targets={k:dict(v.row) for k,v in expected.factual_contracts.items()})
                package=dict(authority=expected.authority,registration=registration_value(expected),scope=allowance['scope'],stop=STOP_STATE,evidence=evidence,targets=allowance['targets'])
                package_sha=self.q(c,"SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(json.dumps(package),))[0][0]
                grant['oldham_package_sha256']=package_sha
                allowance.update(package=package,package_sha256=package_sha,grant_binding={k:v for k,v in grant.items() if k not in ('source_calls','writes')})
                ctl['grants'][expected.authority]=grant;ctl.setdefault('oldham_allowances',{})[expected.authority]=allowance
                # Track intent BEFORE commit; an uncertain acknowledgement cannot silently issue again.
                self.authorities.append(expected.authority);self.invalidation='REQUIRED'
                self.q(c,"UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),),effect=True)
                self.q(c,'REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
                self.q(c,'COMMIT',effect=True)
            except BaseException:
                if not self.effect_uncertain:self.q(c,'ROLLBACK',effect=True)
                raise
            flags=self.q(c,"SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET')")[0]
            if flags!=(False,False):
                self.effect_uncertain=True;raise Denied('OLDHAM_TEMPORARY_CAPABILITY')
        self.emit('oldham_authority_committed',dict(authority=expected.authority,registration_sha256=evidence['registration_sha256'],stop_sha256=sid))
        return expected

    def revoke(self):
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
            self.q(c,'COMMIT',effect=True)
        with self.connection() as c:
            self.q(c,'BEGIN',effect=True)
            self.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            ctl=self.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)")[0][0]
            ok=all(ctl['grants'][a]['expires_at']==0 and ctl['oldham_allowances'][a]['revoked'] is True for a in self.authorities)
            self.q(c,'ROLLBACK',effect=True)
            if not ok:
                self.effect_uncertain=True;raise Denied('OLDHAM_REVOCATION_UNCERTAIN')
        self.invalidation='VERIFIED'
