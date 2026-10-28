"""One dormant owner command; composition of existing reviewed components, never a listing client."""
import argparse,hashlib,json,os,resource,signal,time
from datetime import datetime,timezone
from pathlib import Path
from app.ingestion.ledger import DEFAULT_LIMITS,Denied,digest
from app.ingestion.listing_screening import RULE_V3,ScreeningRule
from . import oldham_owner_package as pkg
from .chain_registration import authority_name
from .oldham_authority import OldhamOwner,derive,registration_value,stop_identity,ROLES
from .oldham_lifecycle import Lifecycle,verify_inventory
from .operational_journal import Journal
from .operational_publication import GitHub,Uncertain,canonical,blob_bytes,REPO,BRANCH
from .operational_outcome import session
from .tls_trust import owned_resources

MAX_EXPORT=2*1024**2
RESERVE=128*1024


def environment():
    forbidden=('GH_TOKEN','GITHUB_TOKEN','GH_DEBUG','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_CONFIG_DIR','GH_HTTP_UNIX_SOCKET','SSL_CERT_FILE','SSL_CERT_DIR','HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy','ALL_PROXY','all_proxy','PYTHONPATH')
    if any(os.environ.get(k) for k in forbidden) or any(k.startswith('PG') for k in os.environ):raise Denied('OLDHAM_ENVIRONMENT_OVERRIDE')
    if os.environ.get('GH_HOST','github.com')!='github.com':raise Denied('OLDHAM_GITHUB_HOST')


class Operation:
    """Thin orchestration only; policy, grants, writes, transport and supervision remain delegated."""
    def __init__(self,data,journal,memory,backend,*,started=None,command_started=None):
        self.data=data;self.p=data['package'];self.journal=journal;self.memory=memory;self.backend=backend
        self.capture_screening_only=self.p['version']==pkg.VERSION_CAPTURE_SCREENING
        self.created=time.monotonic() if command_started is None else command_started;self.preflight_seconds=0;self.started=started;self.stage='PREFLIGHT';self.closing=False;self.published=0;self.publication='NOT_ATTEMPTED';self.claimed=False
        self.head=self.p['evidence_head'];self.directory='docs/design/ingestion-operational-execution-'+self.p['release_id']
        self.source_receipts=[];self.source_accounting='NOT_STARTED'
        self.owner=None;self.life=None;self.caller=None;self.result=dict(detail_attempts=0) if self.capture_screening_only else {};self.baseline=owned_resources();self.closure=None;self.finished=False;self.runtime_uncertain=False;self.preparation_progress=None
        self.github=GitHub(journal.emit,self.check,bound=26,**({'runner':backend.github} if backend else {}))

    def check(self):
        if self.started is not None:
            remaining=self.started+(475 if self.closing else 450)-time.monotonic()
            # Longest existing bounded wait is an administrative statement12s + bounded cancel/close3s
            # (GitHub5s, secret mapping8s, connector/DNS3s). Never spend reporting.
            if remaining<=15:raise Denied('OLDHAM_PACKAGE_DEADLINE')
            if self.owner is not None:self.owner.statement_hard_seconds=min(12,remaining-3)

        if not self.closing:
            if datetime.now(timezone.utc).timestamp()+12>=self.data['expiry'].timestamp():raise Denied('OLDHAM_PACKAGE_EXPIRED')
            if (self.journal.root/'STOP').exists():raise Denied('OLDHAM_OWNER_CANCELLED')
        if self.memory is not None:self.memory.snapshot()
        if self.published+sum(f.stat().st_size for f in self.journal.root.rglob('*') if f.is_file())>MAX_EXPORT-(8192 if self.closing else RESERVE):raise Denied('OLDHAM_COMBINED_EXPORT_RESERVE')

    def publish(self,files,part):
        size=sum(len(raw) for raw in files.values());self.check()
        if self.published+size+sum(f.stat().st_size for f in self.journal.root.rglob('*') if f.is_file())>MAX_EXPORT-(max(65536,4*len(canonical(self.result))+8192) if self.closing else RESERVE):raise Denied('OLDHAM_COMBINED_EXPORT_RESERVE')
        self.published+=size # Count attempted bytes even when acknowledgement is lost.
        self.head=self.github.publish(files,directory=self.directory+'/'+part,expected_head=self.head)
        return self.head

    def preflight(self):
        began=time.monotonic()
        try:return self._preflight()
        finally:self.preflight_seconds=time.monotonic()-began

    def _preflight(self):
        self.stage='PUBLICATION_PREFLIGHT'
        if self.github.call('GET',REPO+'/git/ref/heads/'+BRANCH)['object']['sha']!=self.head:raise Denied('OLDHAM_EVIDENCE_HEAD_CHANGED')
        if self.github.probe(REPO+'/contents/'+self.directory+'/claim/claim.json?ref='+self.head) is not None:raise Denied('OLDHAM_RELEASE_USED')
        blob=self.github.call('GET',REPO+'/contents/'+str(pkg.QUALIFICATION)+'?ref='+self.head)
        if canonical(json.loads(blob_bytes(blob)))!=self.data['qraw']:raise Denied('OLDHAM_QUALIFICATION_COMMITTED_BINDING')
        origin=self.p['origin']
        compared=self.github.call('GET',REPO+'/compare/'+origin['commit']+'...'+self.head)
        if compared.get('status') not in ('identical','ahead') or compared.get('base_commit',{}).get('sha')!=origin['commit']:raise Denied('OLDHAM_ORIGIN_NOT_RETAINED')
        for name,key in [('source_path','source_raw'),('slot_path','slot_raw')]:
            observed=blob_bytes(self.github.call('GET',REPO+'/contents/'+origin[name]+'?ref='+origin['commit']))
            if observed!=self.data[key]:raise Denied('OLDHAM_ORIGIN_BYTES_CHANGED')
        self.journal.emit('preflight_verified',dict(package_sha256=self.data['sha256'],source_sha256=digest(self.data['source']),qualification_sha256=pkg.sha(self.data['qraw']),test_mode=self.backend is not None))

    def prepare(self,raw,started):
        self.started=started;self.stage='CONNECTION_PREPARATION'
        if pkg.git('rev-parse','HEAD')!=self.p['revision'] or pkg.git('status','--porcelain'):raise Denied('OLDHAM_CHECKOUT_CHANGED')
        if datetime.now(timezone.utc).timestamp()+480>=self.data['expiry'].timestamp():raise Denied('OLDHAM_EXPIRY_CAPACITY')
        if self.backend:
            config=self.backend.prepare(raw,self)
            self.baseline=owned_resources() # Fixture bootstrap sockets are not runtime sockets.
        else:
            from .operational_preparation import Progress,prepare_connection
            from .restricted_route import url
            self.preparation_progress=Progress()
            prepared=prepare_connection(self.p,raw,progress=self.preparation_progress)
            config=dict(connect=prepared.connect,identity='postgres',ssl={'sslmode':'verify-full','sslrootcert':str(prepared.ca)},route='POOLER',hostaddr=prepared.hostaddr,url_factory=lambda role,password:url('POOLER',role,password))
        self.config=config
        bindings=dict(revision=self.p['revision'],workflow_sha256=self.p['dependencies']['verification/ingestion_storage/oldham_owner_once.py'],manifest_sha256=self.data['sha256'])
        self.owner=OldhamOwner(config['connect'],self.journal.emit,self.check,identity=config['identity'],expiry=self.data['expiry'],bindings=bindings)
        self.owner.package_started=started
        self.owner.capture_screening_only=self.capture_screening_only
        self.owner.require_control_sha256=self.p.get('control_sha256')
        self.life=Lifecycle(self.owner,self.github,capture_screening_only=self.capture_screening_only)
        return self

    def owner_preflight(self):
        """Reuse Oldham stop/inventory checks, not the historical Bolton-only Owner.preflight."""
        o=self.owner
        with o.connection() as c:
            flags=o.q(c,'SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user')[0]
            self.journal.emit('owner_identity',dict(identity=flags[0],session_user=flags[1],superuser=flags[2],createrole=flags[3],createdb=flags[4],bypassrls=flags[5]))
            if flags!=(o.identity,o.identity,False,True,True,True):raise Denied('OLDHAM_OWNER_IDENTITY')
            verify_inventory(o,c)
            o.q(c,'BEGIN',effect=True)
            try:
                o.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
                ctl=o.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)")[0][0]
                stop_identity(ctl)
                if digest(ctl)!=(self.owner.require_control_sha256 if self.capture_screening_only else self.p['control_sha256']):raise Denied('OLDHAM_CONTROL_CHANGED')
                o.original_control=ctl
            finally:o.q(c,'ROLLBACK',effect=True)

    def issue(self,phase,*,root=None,receipt=None,nominees=(),rows=None):
        args=dict(revision=self.p['revision'],item_limits=DEFAULT_LIMITS,phase=phase)
        if phase!='CAPTURE':args.update(root=root,receipt=receipt,nominees=nominees,rule=self.rule,screening_rows=rows,allow_test_evidence=self.backend is not None)
        reg=derive(self.owner,self.data['binding'],self.data['contract'],**args)
        evidence=dict(source_sha256=digest(self.data['source']),qualification_sha256=self.data['contract'].qualification_sha256,outer_sha256=digest(self.data['outer']),registration_sha256=digest(registration_value(reg)))
        return self.owner.issue(reg,self.data['binding'],self.data['contract'],source=self.data['source'],outer=self.data['outer'],evidence=evidence,**args)

    def archive(self,raw):
        if raw!=self.data['source_raw']:raise Denied('OLDHAM_ARCHIVE_SOURCE_BINDING')
        if self.capture_screening_only:
            # Reuse the immutable archive already verified by preflight, with a
            # fresh exact committed-path readback at capture. A duplicate commit
            # would spend publication capacity needed for retirement/closure.
            origin=self.p['origin'];commit=origin['commit'];path=origin['source_path']
            observed=blob_bytes(self.github.call('GET',REPO+'/contents/'+path+'?ref='+commit))
            if observed!=raw:raise Denied('OLDHAM_ARCHIVE_READBACK_CHANGED')
        else:
            commit=self.publish({'source.json':raw},'capture');path=self.directory+'/capture/source.json'
        result=dict(commit=commit,path=path,sha256=pkg.sha(raw),bytes=len(raw),readback_verified=True)
        if self.backend:result['label']='TEST_ARCHIVE_NOT_LIVE_EVIDENCE'
        return result

    def execute(self):
        try:
            self.stage='DURABLE_CLAIM'
            claim=canonical(dict(package=self.p,package_sha256=self.data['sha256'],consumed=True))
            self.publish({'claim.json':claim},'claim');self.claimed=True
            if self.capture_screening_only:
                self.stage='RETIREMENT_AND_INSTALLATION'
                from .oldham_transition import Transition
                Transition(self).run()
            self.stage='OWNER_PREFLIGHT';self.owner_preflight()
            self.rule=ScreeningRule(RULE_V3,unit_threshold=10,link_related=False)
            self.stage='CAPTURE_ISSUANCE';capture=self.issue('CAPTURE')
            self.stage='ACCESS_ACTIVATION'
            urls=self.life.activate(url_factory=self.config['url_factory'],ssl=self.config.get('ssl'),route=self.config.get('route'))
            options={k:self.config[k] for k in ('ssl','route','hostaddr') if self.config.get(k) is not None}
            self.caller=self.owner.caller(self.data['binding'],self.data['contract'],self.rule,urls,revision=self.p['revision'],bindings=dict(capture.bindings),capture_authority=capture.authority,chain_authority='',stop_file=self.journal.root/'STOP',allow_test_evidence=self.backend is not None,engine_options=options,capture_screening_only=self.capture_screening_only)
            self.stage='RETAINED_CAPTURE';self.caller.preflight(capture.root_key)
            receipt=self.caller.capture(self.data['source'],self.data['outer'],expected_source_sha256=digest(self.data['source']),evidence_label='TEST_ARCHIVE_NOT_LIVE_EVIDENCE' if self.backend else None,archive=self.archive)
            receipt=self.caller.read_capture();root=dict(capture.rows[0],state='COMPLETE',checkpoint=receipt)
            self.stage='SCREENING_ISSUANCE';screen=self.issue('SCREENING',root=root,receipt=receipt)
            if isinstance(screen,dict):raise Denied('OLDHAM_SCREENING_CAPACITY')
            self.caller.bindings.update(screen.bindings);self.caller.use(screen)
            self.stage='SCREENING';self.caller.screen();rows=self.caller.read_screening();ns=self.caller.nominees()
            if self.capture_screening_only:
                from .chain_registration import completed_screening
                completed_screening(screen,receipt,self.rule,rows)
            self.result.update(outcome='SCREENING_COMPLETE_ADMISSION_NOT_STARTED' if ns.nominees else 'SCREENING_COMPLETE_NO_ADMISSION_REQUIRED',records=len(receipt['records']),nominees=len(ns.nominees),nominee_results=[],capture_sha256=digest(receipt),screening_sha256=digest(rows),detail_attempts=0)
            if self.capture_screening_only:
                self.result.update(operation='CAPTURE_SCREENING_ONLY',coverage_advance=False,admission='NOT_AUTHORISED',application_engine='NOT_CREATED',
                    completeness_basis=receipt.get('completeness_basis','SOURCE_TERMINAL'),owner_acceptance=receipt.get('owner_acceptance'),
                    screening_results=[dict(reference=r['subject']['reference'],outcome=r['outcome'],screening_key=r['key'],checkpoint_sha256=digest(r['checkpoint']),
                        record_sha256=r['checkpoint']['record_sha256'],assessment_revision=r['checkpoint']['assessment_revision'],config_sha256=r['checkpoint']['config_sha256'])
                        for r in sorted((r for r in rows if r['task']=='SCREENING'),key=lambda r:r['subject']['reference'])])
            self.checkpoint('SCREENING_COMPLETE',capture_sha256=digest(receipt),screening_sha256=digest(rows),root_key=root['key'],nominees=len(ns.nominees))
            if self.backend:self.backend.after_screening(self)
            if self.capture_screening_only and ns.nominees:self.result['outcome']='SCREENING_COMPLETE_ADMISSION_HELD_OPERATION_SCOPE'
            if ns.nominees and not self.capture_screening_only:
                self.stage='ADMISSION_ISSUANCE';admission=self.issue('ADMISSION',root=root,receipt=receipt,nominees=ns.nominees,rows=rows)
                if isinstance(admission,dict):self.result['outcome']=admission['outcome']
                else:
                    self.caller.bindings.update(admission.bindings);self.caller.use(admission)
                    self.result['outcome']='ADMISSION_PROCESSING_IN_PROGRESS'
                    for i,n in enumerate(ns.nominees):
                        self.check();self.stage='FRESH_DETAIL_ADMISSION';adm=self.caller.prepare(n)
                        reader=self.caller.closed_idox_detail(adm,root=self.journal.root/('detail-'+str(i)),memory_group=None if self.memory is None else self.memory.source,observe=self.observe)
                        if self.backend:reader=self.backend.detail(reader,adm,self)
                        original=reader
                        def counted(row):
                            self.result['detail_attempts']+=1;self.source_accounting='ATTEMPTED_UNVERIFIED'
                            target=self.caller.registration.factual_contracts[n.reference].row
                            accounted=dict(reference=n.reference,factual_key=row['key'],target_sha256=digest(target),status='ATTEMPTED_UNVERIFIED')
                            self.source_receipts.append(accounted)
                            audit,outer=original(row)
                            from verification.discovery.material_qualification import project_idox
                            projection=project_idox(target,audit);projected=projection['audit']
                            known=projected.get('budget_state')=='WITHIN_LIMITS' and projected.get('cleanup_state')=='CLOSED'
                            accounted.update(status='RETURNED_ACCOUNTING_VALIDATED' if known else 'RETURNED_UNVERIFIED',target_sha256=digest(target),source_outcome=projection['failure'] or 'PROJECTED_OBSERVATION',worker=projected,supervisor=outer)
                            self.source_accounting='COMPLETE' if all(x['status']=='RETURNED_ACCOUNTING_VALIDATED' for x in self.source_receipts) else 'PARTIAL'
                            self.journal.emit('detail_accounting_returned',accounted)
                            return audit,outer
                        value=self.caller.admit(adm,counted)
                        self.result['nominee_results'].append(dict(reference=n.reference,outcome=value.get('outcome'),application_id=value.get('application_id') if value.get('application_id') is not None else (value.get('factual') or {}).get('application_id'),identity=value.get('admission'),factual=value.get('factual')))
                        self.checkpoint('NOMINEE_READBACK',reference=n.reference,outcome=value.get('outcome'),completed=i+1)
                    self.result['outcome']='ADMISSION_PROCESSING_COMPLETE'
            self.stage='TEARDOWN';self.closing=True;self.github.bound=40;self.life.teardown()
            self.result.update(status='COMPLETED',access='DISABLED_VERIFIED',cleanup='PENDING_PROCESS_READBACK')
            return self.finish()
        except BaseException as exc:return self.failed(exc)

    def checkpoint(self,stage,**facts):
        state=dict(stage=stage,facts=facts,authorities=list(self.owner.authorities),result=self.result)
        self.journal.save('progress.json',state);self.journal.emit('progress_saved',dict(sha256=digest(state)))

    def observe(self,event,value):
        # Source diagnostics are fixed structured observations; never exception text.
        if event in ('source_supervisor_observed','source_worker_resource_observed'):self.journal.emit(event,value)

    def source_totals(self):
        names=dict(requests='requests',received_body_bytes='received_body_bytes',worker_seconds='elapsed_seconds',supervisor_seconds='supervisor_seconds')
        known=[x['worker'] for x in self.source_receipts if x['status']=='RETURNED_ACCOUNTING_VALIDATED']
        subtotal={k:sum(x[v] for x in known) for k,v in names.items()}
        complete=len(known)==len(self.source_receipts)
        return dict(status=self.source_accounting,attempts=len(self.source_receipts),totals=subtotal if complete else None,known_subtotal=subtotal,receipts=self.source_receipts)

    def accounting(self):
        return dict(source=self.source_totals(),preflight_seconds=self.preflight_seconds,total_command_seconds=time.monotonic()-self.created,preparation=None if self.preparation_progress is None else dict(report=self.preparation_progress.report(),work=self.preparation_progress.work()),fixture_setup=None if not self.backend or not self.backend.world else self.backend.world['setup_costs'],administration=None if self.owner is None else self.owner.accounting(),runtime=None if self.caller is None else self.caller.allocation.totals(),runtime_receipts={} if self.caller is None else self.caller.accounting,github_requests=self.github.requests,attempted_publication_bytes=self.published,elapsed_active_seconds=None if self.started is None else time.monotonic()-self.started)

    def failed(self,exc):
        from .connection_diagnostics import safe_failure
        self.closing=True;self.github.bound=40
        from app.ingestion.ledger import UncertainPersistence
        if isinstance(exc,UncertainPersistence) or self.stage=='FRESH_DETAIL_ADMISSION' or self.caller is not None and self.caller.allocation.failed:self.runtime_uncertain=True
        failure=safe_failure(exc,'EXECUTION');failure.setdefault('stage',self.stage)
        self.result.update(status='STOP_RECONCILE_NO_RETRY',failure=failure,cleanup='UNCERTAIN')
        certain=not self.runtime_uncertain and self.owner is not None and not self.owner.effect_uncertain and not self.github.mutation_uncertain and (self.life is None or self.life.state not in ('UNCERTAIN','CLOSED'))
        if certain:
            try:
                if self.life.state=='ACTIVE':self.life.teardown()
                elif self.owner.authorities:self.owner.tearing_down=True;self.owner.revoke()
            except BaseException:self.result['cleanup_failure']='RECONCILIATION_REQUIRED'
        return self.finish()

    def finish(self):
        if self.finished:return self.result
        self.finished=True;self.closing=True;self.github.bound=40;self.result['cleanup']='UNCERTAIN'
        self.result.update(accounting=self.accounting(),claimed=self.claimed,stage4='OPEN',test_mode=self.backend is not None,source_listing_requests=0)
        if not self.runtime_uncertain and not self.github.mutation_uncertain and not (self.owner and self.owner.effect_uncertain) and self.claimed:
            try:
                self.stage='FINAL_PUBLICATION';prefix=self.journal.file.read_bytes()
                self.result['audit_prefix_sha256']=pkg.sha(prefix)
                raw=canonical(self.result)
                self.publish({'events-prefix.jsonl':prefix,'result-before-publication.json':raw},'completed')
                self.publication='VERIFIED'
            except BaseException:self.publication='UNCERTAIN_OR_HELD'
        self.result.update(publication=self.publication,evidence_commit=self.head if self.publication=='VERIFIED' else None)
        try:
            proof=self.memory.close() if self.memory is not None else dict(owned_groups_removed=None,owned_survivors=None,kernel_proof='NOT_EXERCISED_DISPOSABLE')
            after=owned_resources();process=not after['children'] and not (after['socket_fds']-self.baseline['socket_fds'])
            self.result['process_closure']=dict(live_children=len(after['children']),new_sockets=len(after['socket_fds']-self.baseline['socket_fds']),owned=proof)
            positive=process and (self.memory is None and self.backend is not None or proof.get('owned_groups_removed') is True and proof.get('owned_survivors')==0)
            access=self.life is not None and self.life.state=='CLOSED'
            no_access=self.owner is None or not self.owner.authorities and self.life.state=='UNUSED'
            self.result['access']='DISABLED_VERIFIED' if access else 'NO_ACCESS_CREATED' if no_access else 'UNCERTAIN'
            if positive and (access or no_access) and (self.publication=='VERIFIED' or not self.claimed) and not (self.owner and self.owner.effect_uncertain) and not self.github.mutation_uncertain and not self.runtime_uncertain:self.result['cleanup']='CLOSED'
            self.result['outer_scope_removal']='NOT_VERIFIABLE_BEFORE_EXIT'
        except BaseException:self.result['cleanup']='UNCERTAIN'
        if self.result.get('cleanup')!='CLOSED':self.result['status']='STOP_RECONCILE_NO_RETRY'
        self.result['accounting']=self.accounting();self.result['runtime_effect_uncertain']=self.runtime_uncertain
        # finalise() also accounts its own local result and terminal copy. Add
        # attempted remote bytes to its bound by retaining a small accounting value;
        # the session-level final publisher below verifies the complete envelope.
        self.journal.emit('owner_operation_result',self.result)
        return self.result


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--package',type=Path,required=True);parser.add_argument('--package-sha256',required=True);parser.add_argument('--disposable-test',action='store_true')
    a=parser.parse_args(argv);memory=None;backend=None;op=None
    from .operational_cleanup import HardDeadline
    entered=time.monotonic();outer=HardDeadline(entered+790)
    try:
        if a.disposable_test:
            from tests.oldham_wrapper_fixture import Backend
            backend=Backend(a.package)
        else:
            environment();from .operational_memory import OperationalMemory
            memory=OperationalMemory()
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        data=pkg.validate(a.package,a.package_sha256,disposable=a.disposable_test)
        state=Path.home()/'.local/state/propertyaigent';state.mkdir(mode=0o700,parents=True,exist_ok=True)
        root=state/data['package']['release_id']
        if root.exists():raise Denied('OLDHAM_LOCAL_RELEASE_USED')
        journal=Journal(root);op=Operation(data,journal,memory,backend,command_started=entered);op.preflight()
        if backend and backend.native:
            from .operational_memory import OperationalMemory
            memory=OperationalMemory();op.memory=memory;op.baseline=owned_resources()
        from .credential_mapping import secure_migration_input
        result=session(journal,data['package']['expires_at'],backend.input if backend else secure_migration_input,op.prepare,memory=memory,baseline=op.baseline,external_bytes=lambda:op.published,initial_worker=op)
        if backend:backend.close()
        outer.close()
        return 0 if result.get('cleanup')=='CLOSED' and result.get('status')=='COMPLETED' else 1
    except BaseException as exc:
        if op is not None:
            try:
                from .operational_outcome import finalise
                result=op.failed(exc);finalise(op.journal,result,input_seconds=0,active_started=op.started,external_bytes=op.published)
            except BaseException:print('{"status":"STOP_RECONCILE_NO_RETRY","cleanup":"UNCERTAIN","failure":"FINALISATION_FAILED"}',flush=True)
        else:
            proof=None
            try:
                if memory is not None:proof=memory.close()
            except BaseException:pass
            print(json.dumps(dict(status='PREFLIGHT_REFUSED',credential_requested=False,database_connections=0,cleanup='NO_EFFECTS' if memory is None or proof is not None and proof.get('owned_groups_removed') is True and proof.get('owned_survivors')==0 else 'UNCERTAIN',failure='SEALED_INPUT_OR_ENVIRONMENT',memory=proof)),flush=True)
        if backend:backend.close()
        outer.close()
        return 1

if __name__=='__main__':raise SystemExit(main())
