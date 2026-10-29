"""Owner half of the existing standing handshake; no runtime credential intake.

All SQL issuance/revocation remains in OldhamOwner. No provision, installation,
retirement or compensating rollback is invoked by a batch operation.
"""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import hashlib,io,json,time,zipfile,re
from pathlib import Path
from app.ingestion.ledger import Denied,digest,DEFAULT_LIMITS
from . import oldham_standing_plan as plan,oldham_owner_package as pkg
from .standing_access import GITHUB,POLL_ATTEMPTS,POLL_SECONDS,require_closure,StandingGitHub
from .oldham_owner_once import Operation,MAX_EXPORT
from .oldham_authority import derive,registration_value,stop_identity
from .oldham_reuse import InstalledReuse,AUTHORITY,expected_historical,SETTINGS,ROLE_SETTINGS
from .oldham_allocation import Allocation
from .oldham_lifecycle import activation_gate
from .storage_controller import split_sql
from .operational_publication import canonical,blob_bytes,REPO,BRANCH,Uncertain
from .tls_trust import owned_resources


def standing_gate():
    text=activation_gate(capture_screening_only=True)
    exact='WHERE rolname=login AND NOT rolcanlogin'
    if text.count(exact)!=1:raise Denied('OLDHAM_STANDING_GATE_DERIVATION')
    # The standing model explicitly REQUIRES LOGIN; no alternate principal/flag
    # or provider predicate is changed. Password/expiry are checked separately.
    return text.replace(exact,'WHERE rolname=login AND rolcanlogin')


def sealed_export(result,raw,events,persisted,chain_head):
    external=result.get('accounting',{}).get('attempted_publication_bytes')
    if type(external) is not int or not 0<=external<=MAX_EXPORT or not isinstance(result.get('local_audit_path'),str):raise Uncertain('OLDHAM_STANDING_EXPORT_ACCOUNTING')
    receipt=dict(result,audit=result['local_audit_path'],audit_sha256=hashlib.sha256(events).hexdigest(),audit_chain_head=chain_head,result_sha256=hashlib.sha256(raw).hexdigest(),persisted_evidence_bytes=persisted,terminal_json_bytes=0,exported_bytes=persisted+external)
    if external:receipt['attempted_publication_bytes']=external
    for _ in range(10):
        size=len(json.dumps(receipt,sort_keys=True).encode())+1
        if receipt['terminal_json_bytes']==size:break
        receipt['terminal_json_bytes']=size;receipt['exported_bytes']=persisted+size+external
    else:raise Uncertain('OLDHAM_STANDING_EXPORT_ACCOUNTING')
    if receipt['exported_bytes']>MAX_EXPORT-8192:raise Uncertain('OLDHAM_STANDING_EXPORT_BOUND')
    return receipt['exported_bytes']


class StandingOperation(Operation):
    def __init__(self,data,value,*args,**kw):
        super().__init__(data,*args,**kw)
        self.selection=value;self.seal=digest(value);from app.ingestion.listing_screening import ScreeningRule,RULE_V3
        self.rule=ScreeningRule(RULE_V3,unit_threshold=10,link_related=False)
        self.github=StandingGitHub(self.journal.emit,self.check,runner=self.github.runner,bound=GITHUB['owner_work'])
        self.github.requests=value['standing']['credential_preparation_github_calls']
        self.hosted=None;self.standing_before=None;self.standing_verified=False;self.artifact_verified=False;self.runtime_packet_bytes=0;self.runtime_copied_bytes=0;self.export_reservation=None
        self.namespace='docs/design/ingestion-operational-execution-'+self.p['release_id'];self.sleep=time.sleep

    def prepare(self,raw,started):
        super().prepare(raw,started)
        self.owner.standing_capture_screening=True;self.owner.capture_screening_only=True
        self.owner.bindings=dict(revision=self.p['revision'],workflow_sha256=self.p['dependencies']['verification/ingestion_storage/oldham_standing_owner.py'],manifest_sha256=self.seal)
        self.owner._allocation=Allocation(package_started=started)
        return self

    def _preflight(self):
        super()._preflight()
        prefix='docs/design/ingestion-operational-execution-'+plan.PREVIOUS+'/completed/'
        values={}
        for name in ('result-before-publication.json','events-prefix.jsonl'):
            raw=blob_bytes(self.github.call('GET',REPO+'/contents/'+prefix+name+'?ref='+plan.PREVIOUS_COMMIT));values[name]=raw
        result=json.loads(values['result-before-publication.json'])
        if digest(result)!=plan.PREVIOUS_RESULT or hashlib.sha256(values['events-prefix.jsonl']).hexdigest()!=plan.PREVIOUS_AUDIT:raise Denied('OLDHAM_STANDING_PREVIOUS_ATTEMPT_CHANGED')
        if result.get('historical_cleanup',{}).get('status')!='NOT_ATTEMPTED' or result.get('failure',{}).get('reason_code')!='STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED':raise Denied('OLDHAM_STANDING_PREVIOUS_ATTEMPT_CHANGED')
        # One finite workflow-history read; refuse unexpected/active use. Never
        # revive the historical stable-pipeline-once workflow.
        runs=self.github.call('GET',REPO+'/actions/workflows/stage4-oldham-standing.yml/runs?per_page=1').get('workflow_runs',[])
        expected=self.selection['runtime_admission']['run_number']
        if any(r.get('status')!='completed' for r in runs) or expected!=(runs[0]['run_number']+1 if runs else 1):raise Denied('OLDHAM_STANDING_RUNTIME_HISTORY')

    def _observe_standing(self,c):
        from .oldham_authority import ROLES
        roles=list(ROLES)[:2];state=self.life.observed(c)
        until=datetime.fromisoformat(self.selection['standing']['valid_until'])
        if len(state['roles'])!=2 or state['sessions'] or any(not r[1] or r[2] or r[3]!=until or any(r[4:9]) or r[9]!=1 for r in state['roles']):raise Denied('OLDHAM_STANDING_ACCESS_STATE')
        if state['memberships']!=[(r,ROLES[r],False,True,False) for r in sorted(roles)]:raise Denied('OLDHAM_STANDING_MEMBERSHIPS')
        configs=self.owner.q(c,ROLE_SETTINGS,(roles,))
        if len(configs)!=2 or any(sorted(v or [])!=SETTINGS or n!=0 for _,v,n in configs):raise Denied('OLDHAM_STANDING_ROLE_SETTINGS')
        state['roles']=[list(r[:3])+[r[3].astimezone(timezone.utc).isoformat()]+list(r[4:]) for r in state['roles']]
        return dict(access=state,settings=configs)

    def preflight_standing(self):
        o=self.owner;self.stage='STANDING_PREFLIGHT'
        names=set(self.github.names())
        if not {'DATABASE_URL','INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'}<=names or any(n in names for n in ('INGESTION_STORAGE_DATABASE_URL','INGESTION_APPLICATION_DATABASE_URL')):raise Denied('OLDHAM_STANDING_SECRET_STATE')
        with o.connection() as c:
            identity=o.q(c,'SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user')[0]
            if identity!=(o.identity,o.identity,False,True,True,True):raise Denied('OLDHAM_OWNER_IDENTITY')
            reuse=InstalledReuse(self);reuse.capabilities_absent(c);reuse.inventory(c)
            observed=self._observe_standing(c)
            if digest(observed)!=self.selection['standing']['state_sha256']:raise Denied('OLDHAM_STANDING_QUALIFIED_STATE_CHANGED')
            for q in split_sql(standing_gate()):o.q(c,q)
            o.q(c,'BEGIN',effect=True);o.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            try:
                ctl=o.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)")[0][0]
                reuse.expected=expected_historical(o,c);reuse.historical(ctl,cleaned=True);reuse.historical_work(c);reuse.barriers(c)
                # Read-only gate checks must already have completed before work authority.
                o.original_control=ctl
            finally:o.q(c,'ROLLBACK',effect=True)
            reuse.capabilities_absent(c)
        self.standing_before=observed;self.result['historical_cleanup']='PREVIOUSLY_VERIFIED_CURRENT_STATE_CONFIRMED'

    def await_marker(self,part,*,also_failure=False):
        for attempt in range(POLL_ATTEMPTS):
            self.check();head=self.github.call('GET',REPO+'/git/ref/heads/'+BRANCH)['object']['sha']
            blob=self.github.probe(REPO+'/contents/'+self.namespace+'/'+part+'?ref='+head)
            if blob is not None:self.head=head;return json.loads(blob_bytes(blob))
            if also_failure:
                failed=self.github.probe(REPO+'/contents/'+self.namespace+'/completed/final-result.json?ref='+head)
                if failed is not None:
                    self.hosted=json.loads(blob_bytes(failed))
                    raise Uncertain('OLDHAM_STANDING_RUNTIME_ENDED_BEFORE_RETENTION')
            if attempt+1<POLL_ATTEMPTS:self.sleep(POLL_SECONDS)
        raise Denied('OLDHAM_STANDING_MARKER_WAIT_EXHAUSTED')

    def capture_checkpoint(self,marker,reg):
        if not isinstance(marker,dict) or set(marker)!={'execution','capture_sha256','phase_receipts','allocation','phase_closure'} or marker['execution']!=self.execution or marker['phase_closure']!=dict(children=0,new_sockets=0):raise Uncertain('OLDHAM_STANDING_CAPTURE_MARKER')
        require_closure(marker['phase_receipts'])
        totals=marker['allocation'];receipts=marker['phase_receipts']
        measured=dict(commands=sum(v['driver_statements'] for v in receipts),connections=sum(v['connection_attempts'] for v in receipts),returned_bytes=sum(v['returned_data_value_bytes'] for v in receipts))
        if any(type(totals.get(k)) is not int or totals[k]!=v for k,v in measured.items()) or not isinstance(totals.get('seconds'),(int,float)) or totals['seconds']<0:raise Uncertain('OLDHAM_STANDING_CAPTURE_ACCOUNTING')
        o=self.owner
        with o.connection() as c:
            o.q(c,'BEGIN',effect=True);o.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            try:root=o.q(c,'SELECT row_to_json(w) FROM public.ingestion_work_items w WHERE key=%s',(reg.root_key,))[0][0]
            finally:o.q(c,'ROLLBACK',effect=True)
        receipt=root.get('checkpoint')
        if root.get('state')!='COMPLETE' or marker['capture_sha256']!=digest(receipt):raise Uncertain('OLDHAM_STANDING_SAVED_CAPTURE')
        from .scope_binding import check_capture
        check_capture(self.data['binding'],self.data['contract'],receipt)
        # One immutable measured CAPTURE receipt is adopted once. Runtime retains
        # its actual single Allocation across both phases; owner never resets it.
        if o._allocation.budgets:raise Denied('OLDHAM_STANDING_ACCOUNTING_REPLAY')
        for v in receipts:o._allocation.budgets.append(SimpleNamespace(statements=v['driver_statements'],attempts=v['connection_attempts'],returned_bytes=v['returned_data_value_bytes'],previous={}))
        return root,receipt

    def runtime_artifact(self,published):
        rid=published.get('workflow_run_id')
        if type(rid) is not int or rid<1:raise Uncertain('OLDHAM_STANDING_RUN_ID')
        for attempt in range(POLL_ATTEMPTS):
            run=self.github.call('GET',REPO+'/actions/runs/'+str(rid))
            if run.get('head_sha')!=self.p['revision'] or run.get('run_number')!=self.selection['runtime_admission']['run_number'] or run.get('run_attempt')!=1 or run.get('path')!='.github/workflows/stage4-oldham-standing.yml':raise Uncertain('OLDHAM_STANDING_ARTIFACT_RUN')
            if run.get('status')=='completed':
                if run.get('conclusion')!='success':raise Uncertain('OLDHAM_STANDING_HOSTED_EXIT')
                break
            if attempt+1<POLL_ATTEMPTS:self.sleep(POLL_SECONDS)
        else:raise Uncertain('OLDHAM_STANDING_ARTIFACT_WAIT')
        items=self.github.call('GET',REPO+'/actions/runs/'+str(rid)+'/artifacts').get('artifacts',[])
        expected='oldham-standing-'+str(rid)+'-'+self.p['revision'];items=[a for a in items if a.get('name')==expected and not a.get('expired')]
        if len(items)!=1 or not re.fullmatch('sha256:[a-f0-9]{64}',items[0].get('digest','')):raise Uncertain('OLDHAM_STANDING_ARTIFACT_IDENTITY')
        a=items[0];declared=a.get('size_in_bytes')
        if type(declared) is not int or declared<1:raise Uncertain('OLDHAM_STANDING_ARTIFACT_SIZE')
        if declared>self.export_reservation['runtime_limit']+self.export_reservation['zip_overhead']:raise Denied('OLDHAM_STANDING_ARTIFACT_SIZE')
        self.artifact_capacity(declared)
        raw=self.github.call('GET',REPO+'/actions/artifacts/'+str(a['id'])+'/zip',binary=True)
        self.runtime_packet_bytes+=len(raw) # Attempted intake counts even on hash/shape failure.
        if len(raw)!=declared or len(raw)>MAX_EXPORT or 'sha256:'+hashlib.sha256(raw).hexdigest()!=a['digest']:raise Uncertain('OLDHAM_STANDING_ARTIFACT_HASH')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or not {'events.jsonl','final-result.json'}<=set(names) or not set(names)<={'events.jsonl','final-result.json','progress.json'} or sum(i.file_size for i in z.infolist())>MAX_EXPORT:raise Uncertain('OLDHAM_STANDING_ARTIFACT_BOUND')
            result_raw=z.read('final-result.json');events=z.read('events.jsonl');sealed=json.loads(result_raw)
        if sealed.get('records')!=5 or type(sealed.get('nominees')) is not int or not 0<=sealed['nominees']<=5 or any(sealed.get(k)!=0 for k in ('application_writes','source_observations_attempted','detail_requests','credential_changes')) or sealed.get('application_engine')!='NOT_CREATED':raise Uncertain('OLDHAM_STANDING_WRITE_CONFINEMENT')
        if sealed.get('execution')!=self.execution or sealed.get('published_status')!=published['status'] or sealed.get('cleanup')!='CLOSED' or sealed.get('publication')!='PUBLISHED' or type(sealed.get('accounting',{}).get('github_requests')) is not int or sealed['accounting']['github_requests']>GITHUB['runtime']:raise Uncertain('OLDHAM_STANDING_ARTIFACT_CLOSURE')
        # Existing finalise hashes the original persisted result, not terminal copy.
        previous='0'*64
        for line in events.splitlines():
            row=json.loads(line);observed=row.pop('sha256')
            if row.get('previous_sha256')!=previous or digest(row)!=observed:raise Uncertain('OLDHAM_STANDING_ARTIFACT_AUDIT_CHAIN')
            previous=observed
        persisted=sum(i.file_size for i in z.infolist())
        runtime_export=sealed_export(sealed,result_raw,events,persisted,previous)
        if sealed.get('accounting',{}).get('export_reservation')!=self.export_reservation or runtime_export>self.export_reservation['runtime_limit'] or len(result_raw)+len(events)>self.export_reservation['runtime_limit']:raise Uncertain('OLDHAM_STANDING_RUNTIME_EXPORT_RESERVATION')
        self.artifact_capacity(runtime_export+len(result_raw)+len(events))
        self.runtime_packet_bytes+=runtime_export
        self.runtime_copied_bytes+=len(result_raw)+len(events)
        self.journal.save('runtime-final-result.json',sealed);self.journal.save('runtime-events.jsonl',events)
        self.result['runtime_exported_bytes']=runtime_export
        self.artifact_verified=True;self.hosted=sealed;return sealed

    def artifact_capacity(self,additional):
        persisted=sum(p.stat().st_size for p in self.journal.root.rglob('*') if p.is_file())
        if self.runtime_packet_bytes+self.published+persisted+additional>MAX_EXPORT-8192:raise Denied('OLDHAM_STANDING_ARTIFACT_EXPORT_RESERVE')

    def publish(self,files,part):
        # Include runtime intake/export in the existing whole-publication check.
        size=sum(map(len,files.values()));self.artifact_capacity(size)
        if self.export_reservation is not None:
            persisted=sum(p.stat().st_size for p in self.journal.root.rglob('*') if p.is_file())
            if self.published+persisted-self.runtime_copied_bytes+size>self.export_reservation['owner_limit']:raise Denied('OLDHAM_STANDING_OWNER_EXPORT_RESERVE')
        return super().publish(files,part)

    def original_active_start(self):
        elapsed=time.monotonic()-self.started
        if not 0<=elapsed<450:raise Denied('OLDHAM_STANDING_ORIGINAL_CLOCK')
        return (datetime.now(timezone.utc)-timedelta(seconds=elapsed)).isoformat()

    def execute(self):
        try:
            self.preflight_standing()
            claim=plan.public_claim(self.selection,self.data,self.original_active_start())
            from .standing_access import export_reservation
            base=self.published+sum(f.stat().st_size for f in self.journal.root.rglob('*') if f.is_file())
            for _ in range(10):
                reserve=export_reservation(base+len(canonical(claim)))
                if claim.get('export')==reserve:break
                claim['export']=reserve
            else:raise Denied('OLDHAM_STANDING_EXPORT_RESERVATION')
            self.export_reservation=reserve
            self.execution=dict(revision=self.p['revision'],manifest_sha256=self.seal,capture_key=claim['capture_registration']['root_key'],initial_evidence_head=self.p['evidence_head'],authority=claim['capture_registration']['authority'])
            self.stage='DURABLE_CLAIM';self.publish({'claim.json':canonical(claim)},'claim');self.claimed=True
            self.stage='CAPTURE_ISSUANCE';capture=self.issue('CAPTURE')
            self.journal.emit('oldham_standing_runtime_launch_ready',dict(claim_commit=self.head,release_id=self.p['release_id'],manifest_sha256=self.seal,expected_run_number=self.selection['runtime_admission']['run_number']))
            self.stage='CAPTURE_RECEIPT';marker=self.await_marker('capture-retained/retained.json',also_failure=True);root,receipt=self.capture_checkpoint(marker,capture)
            self.stage='SCREENING_ISSUANCE';screen=self.issue('SCREENING',root=root,receipt=receipt)
            if isinstance(screen,dict):raise Denied('OLDHAM_STANDING_CAPACITY')
            self.publish({'registered.json':canonical(dict(execution=self.execution,capture_sha256=digest(receipt),prepared_sha256=plan.screening_authority_digest(screen),authority=screen.authority))},'screening-authority')
            self.stage='RUNTIME_RESULT';published=self.await_marker('completed/final-result.json')
            if published.get('execution')!=self.execution or published.get('capture_sha256')!=digest(receipt) or published.get('status')!='OLDHAM_STANDING_CAPTURE_SCREENING_COMPLETE':raise Uncertain('OLDHAM_STANDING_RUNTIME_OUTCOME')
            self.hosted=published;self.closing=True;self.github.bound=GITHUB['owner'];self.stage='AUTHORITY_INVALIDATION';self.owner.tearing_down=True;self.owner.revoke()
            self.stage='RUNTIME_ARTIFACT';sealed=self.runtime_artifact(published)
            with self.owner.connection() as c:
                self.owner.q(c,'BEGIN',effect=True);self.owner.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
                try:
                    keys=[r['key'] for r in [*screen.batches,*screen.screens.values()]]
                    actual=[r[0] for r in self.owner.q(c,'SELECT row_to_json(w) FROM public.ingestion_work_items w WHERE key=ANY(%s) ORDER BY key',(keys,))]
                    from .chain_registration import completed_screening
                    completed_screening(screen,receipt,self.rule,actual)
                    if digest(actual)!=sealed.get('screening_sha256'):raise Uncertain('OLDHAM_STANDING_SCREENING_READBACK')
                finally:self.owner.q(c,'ROLLBACK',effect=True)
                after=self._observe_standing(c)
                if after!=self.standing_before:raise Uncertain('OLDHAM_STANDING_ACCESS_CHANGED')
            names=set(self.github.names())
            if not {'DATABASE_URL','INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'}<=names:raise Uncertain('OLDHAM_STANDING_SECRETS_CHANGED')
            self.standing_verified=True;self.result.update(status='COMPLETED',records=sealed['records'],nominees=sealed['nominees'],outcome=sealed['outcome'],authority_invalidation=self.owner.invalidation,credential_changes=0,application_writes=0,detail_requests=0,source_requests=0,coverage_advance=False)
            return self.finish()
        except BaseException as exc:return self.failed(exc)

    def check(self):
        super().check()
        persisted=sum(f.stat().st_size for f in self.journal.root.rglob('*') if f.is_file())
        if self.export_reservation is not None and self.published+persisted-self.runtime_copied_bytes>self.export_reservation['owner_limit']:raise Denied('OLDHAM_STANDING_OWNER_EXPORT_RESERVE')
        if self.runtime_packet_bytes+self.published+persisted>MAX_EXPORT-8192:raise Denied('OLDHAM_STANDING_COMBINED_EXPORT')

    def accounting(self):
        value=super().accounting();runtime=(self.hosted or {}).get('accounting',{})
        value.update(hosted=runtime,github=dict(owner=self.github.requests,hosted=runtime.get('github_requests'),combined=None if runtime.get('github_requests') is None else self.github.requests+runtime['github_requests'],maximum=GITHUB['combined'],owner_current_measured=self.github.requests-self.selection['standing']['credential_preparation_github_calls'],preparation=dict(value=self.selection['standing']['credential_preparation_github_calls'],basis='RESERVED_MAXIMUM_NOT_MEASURED'),combined_basis='MEASURED_CURRENT_PLUS_RESERVED_PREPARATION'))
        return value

    def failed(self,exc):
        from .connection_diagnostics import safe_failure,fixed_stop_reason
        self.closing=True;self.github.bound=GITHUB['owner'];self.result.update(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',failure=dict(safe_failure(exc,'EXECUTION'),stage=self.stage,reason_code=fixed_stop_reason(exc) or 'UNKNOWN'),credentials='RETAINED_NO_AUTOMATIC_REVOCATION')
        self.result['authority_invalidation']=self.failure_invalidation()
        return self.finish()

    def failure_invalidation(self):
        o=self.owner
        if o is None or not o.authorities:return 'NOT_REQUIRED_NO_AUTHORITY'
        if o.invalidation=='VERIFIED':return 'VERIFIED'
        known_before_runtime=self.stage in ('STANDING_PREFLIGHT','DURABLE_CLAIM','CAPTURE_ISSUANCE')
        known_no_runtime_effects=(self.hosted or {}).get('database_connections_attempted')==0
        if o.effect_uncertain or o.awaiting_verification or self.github.mutation_uncertain or not (known_before_runtime or known_no_runtime_effects):return 'RECONCILIATION_REQUIRED_NO_AUTOMATIC_MUTATION'
        try:
            o.tearing_down=True;o.revoke()
            return o.invalidation
        except BaseException:return 'UNCERTAIN_RECONCILIATION_REQUIRED'

    def finish(self):
        if self.finished:return self.result
        self.finished=True;self.closing=True;self.github.bound=GITHUB['owner'];self.result['cleanup']='UNCERTAIN'
        self.result.update(accounting=self.accounting(),operation='CAPTURE_SCREENING_ONLY',access='STANDING_UNCHANGED_VERIFIED' if self.standing_verified else 'STANDING_STATE_UNVERIFIED',stage4='OPEN')
        try:
            if self.claimed and not self.github.mutation_uncertain and self.owner is not None and not self.owner.effect_uncertain:self.publish({'events-prefix.jsonl':self.journal.file.read_bytes(),'result-before-publication.json':canonical(self.result)},'owner-completed')
        except BaseException:self.result['publication']='UNCERTAIN'
        try:
            proof=self.memory.close() if self.memory is not None else dict(owned_groups_removed=None,owned_survivors=None,kernel_proof='NOT_EXERCISED_DISPOSABLE')
            after=owned_resources();closed=not after['children'] and not after['socket_fds']-self.baseline['socket_fds'] and (self.memory is None and self.backend is not None or proof.get('owned_groups_removed') is True and proof.get('owned_survivors')==0)
            self.result['process_closure']=dict(owned=proof,live_children=len(after['children']),new_sockets=len(after['socket_fds']-self.baseline['socket_fds']))
            if closed and self.artifact_verified and self.standing_verified and self.owner.invalidation=='VERIFIED' and not self.owner.effect_uncertain and not self.github.mutation_uncertain and self.result.get('publication')!='UNCERTAIN':self.result['cleanup']='CLOSED'
        except BaseException:pass
        if self.result['cleanup']!='CLOSED':self.result['status']='STOP_RECONCILE_NO_RETRY'
        self.result['outer_scope_removal']='SEPARATE_POST_EXIT_OBSERVATION_REQUIRED';self.result['accounting']=self.accounting();return self.result


def validate_owner(path,expected,*,inactive=False,disposable=False):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>128*1024:raise Denied('OLDHAM_STANDING_MANIFEST_BOUND')
    raw=path.read_bytes()
    if pkg.sha(raw)!=expected:raise Denied('OLDHAM_STANDING_MANIFEST_HASH')
    value=json.loads(raw);p=plan.validate_selection(value,inactive=inactive)
    companion=path.parent/'owner-package.json'
    if companion.is_symlink() or not companion.is_file() or companion.stat().st_size>128*1024 or companion.read_bytes()!=canonical(p):raise Denied('OLDHAM_STANDING_OWNER_PACKAGE')
    data=pkg.validate(companion,pkg.sha(canonical(p)),inactive=inactive,disposable=disposable)
    if not inactive:
        q=path.parent/'standing-qualification.json'
        if q.is_symlink() or not q.is_file() or q.stat().st_size>128*1024:raise Denied('OLDHAM_STANDING_QUALIFICATION_REQUIRED')
        qraw=q.read_bytes();qualified=json.loads(qraw)
        # The original qualification artifact is unchanged. Eleven preparation
        # calls are conservatively reserved in the live manifest, never labelled
        # measured; ordinary owner/runtime calls remain measured separately.
        if pkg.sha(qraw)!=value['standing']['qualification_sha256'] or qualified.get('status')!='STABLE_CREDENTIALS_QUALIFIED' or qualified.get('use_blocked') is not False or set(qualified.get('roles',{}))!={'ingestion_worker_login','ingestion_effect_login'} or any(r.get('qualified') is not True for r in qualified['roles'].values()) or qualified.get('accounting',{}).get('client_closure',{}).get('status')!='VERIFIED_FOR_EVERY_ATTEMPT':raise Denied('OLDHAM_STANDING_QUALIFICATION_REQUIRED')
    return data,value


def main(argv=None):
    import argparse,resource
    from .oldham_owner_once import environment
    from .operational_cleanup import HardDeadline
    from .operational_journal import Journal
    from .operational_outcome import session
    from .credential_mapping import secure_migration_input
    from .operational_memory import OperationalMemory
    a=argparse.ArgumentParser();a.add_argument('--manifest',type=Path,required=True);a.add_argument('--manifest-sha256',required=True);x=a.parse_args(argv)
    environment();data,value=validate_owner(x.manifest,x.manifest_sha256)
    if not __import__('sys').stdin.isatty() or not __import__('sys').stderr.isatty():raise SystemExit('OWNER_SECURE_TTY_REQUIRED')
    started=time.monotonic();deadline=HardDeadline(started+790);resource.setrlimit(resource.RLIMIT_CORE,(0,0));memory=OperationalMemory()
    state=Path.home()/'.local/state/propertyaigent'/data['package']['release_id']
    if state.exists():raise Denied('OLDHAM_LOCAL_RELEASE_USED')
    journal=Journal(state);op=StandingOperation(data,value,journal,memory,None,command_started=started)
    try:
        op.preflight()
        result=session(journal,data['package']['expires_at'],secure_migration_input,op.prepare,memory=memory,baseline=op.baseline,external_bytes=lambda:op.published+op.runtime_packet_bytes,initial_worker=op)
        return 0 if result.get('status')=='COMPLETED' and result.get('cleanup')=='CLOSED' else 1
    finally:deadline.close()

if __name__=='__main__':raise SystemExit(main())
