"""The restricted GitHub-hosted half of the screening-v3 RETAINED-WINDOW assessment (PR #175): ONE source-free assessment of the 24 retained Bolton applications with the standing restricted credentials ALONE. No
administrative credential, no Owner, no credential change, no capture operation, no source client, no council request, no application write and no authority issuance: the OWNER registers the one named allowance; this job only
spends it. It reuses the accepted hosted pipeline unchanged (admission, connection qualification, the checkout binding against the grant, the owner-marker wait, the accounted slot per batch, publication-then-closure).

Order: admission -> bounded connection qualification (read-only, before ANY ledger work) -> this job's actual checkout (revision, controller, manifest) -> READY marker (execution, checkout, configuration digest, retained capture,
expected item set; the owner verifies it BEFORE registering, so queueing and approval never consume the grant lifetime) -> wait (no database connection) for the owner's registration marker -> authority and checkout binding
read from the grant (a mismatch stops here: nothing is assessed) -> stage 1 (read the retained capture, verify its pinned digest, recompute the exact v3 batch plans, snapshot the preserved rows) -> stage 2 (each batch
through the accepted `process_batch`, one accounted slot each) -> stage 3 (recompute every assessment in trusted memory, prove the preserved rows unchanged) -> sealed result published. There is no retry and no replay."""
import json,time
from app.ingestion.batching import batch_plans
from app.ingestion.ledger import Denied,digest
from app.ingestion.listing_screening import RULE_V3,V3_CONTRACT,ScreeningRule
from . import stable_pipeline as sp
from . import stable_qualification as sq
from .operational_controller import assessment_plan,verify_assessed
from .operational_owner import WINDOW_SCOPE
from .operational_publication import Uncertain
from .operational_runner import SV3_AUTHORITY,SV3_EVIDENCE_DIRECTORY,SV3_HOSTED_AUTHORITY,SV3_MANIFEST_PATH
from .retained_world import CAPTURE_CHECKPOINT,CAPTURE_KEY,identities,retained,v3_items

SV3_RULE_THRESHOLD=10      # the council-configured platform threshold, frozen into the configuration digest (read once, never per record)


class ScreeningV3HostedRunner(sp.HostedRunner):
    EVIDENCE=SV3_EVIDENCE_DIRECTORY
    AUTHORITY=SV3_AUTHORITY
    MODE_NAME='BOLTON_SCREENING_V3_RETAINED_HOSTED'
    MANIFEST=SV3_MANIFEST_PATH
    GRANT_SUFFIX='_SCREEN'      # the only ledger authority this job reads and spends; there is no capture name
    scope=WINDOW_SCOPE

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.capture_key=CAPTURE_KEY      # the RETAINED capture root, not a root derived from this mode's manifest
        self.execution=dict(self.execution,capture_key=CAPTURE_KEY)      # identical to the owner's pipeline_execution()
        self.rule=ScreeningRule(RULE_V3,unit_threshold=SV3_RULE_THRESHOLD,link_related=False)
        self.screening_rules={V3_CONTRACT:self.rule}      # read by Runner.slot: every coordinator this job builds is the explicit v3 one

    def stage(self,name):
        self.operation_phase=name
        self.check()

    def ready_marker(self,checkout,new_keys):
        return dict(execution=self.execution,checkout_binding=checkout,capture_sha256=CAPTURE_CHECKPOINT,config_sha256=digest(self.rule.config()),new_items_sha256=digest(sorted(new_keys)),qualification='STABLE_CREDENTIALS_QUALIFIED')

    def publish_ready(self,marker):
        self.evidence_head=self.github.publish({'ready.json':json.dumps(marker,sort_keys=True,separators=(',',':')).encode()},directory=self.EVIDENCE+'/hosted-ready',expected_head=self.evidence_head)
        self.emit('hosted_ready_marker_published',dict(head=self.evidence_head))

    def run(self):
        qualification=None;assessments=[]
        try:
            self.stage('CONNECTION_QUALIFICATION')
            q=sq.Qualification(self.owner.urls,emit=self.emit,ssl=self.ssl,hostaddr=self.hostaddr,stop_file=self.journal.root/'STOP')
            qualification=q.run()
            self.emit('connection_qualification_result',dict(status=qualification['status'],stop_reason=qualification.get('stop_reason'),attempts_total=qualification['attempts_total'],accounting=qualification['accounting']))
            if qualification['status']!='STABLE_CREDENTIALS_QUALIFIED':raise Denied('CONNECTION_QUALIFICATION_'+str(qualification.get('stop_reason')))
            qualification={k:qualification[k] for k in ('status','attempts_total','accounting','elapsed_seconds')}
            self.stage('SV3_RECOMPUTE_EXPECTED')
            _,receipt=retained()      # the pinned evidence, regenerated; no database access
            root,children,_,batches1,_=identities(receipt)
            plans,batches3,children3=v3_items(receipt,self.rule)
            new_keys=[x['key'] for x in (*batches3,*children3)]
            self.capture=receipt;self.plans=plans
            self.batch_bindings=sp.bindings_for([*batches3,root,*children,*batches1,*children3])      # 59 keys, exactly what the owner registers
            preserved=[*[c['key'] for c in children],*[b['key'] for b in batches1]]
            self.stage('SV3_CHECKOUT')
            checkout=self.checkout_probe()
            if checkout.get('tracked_files_modified') is not False or checkout.get('revision')!=self.execution['revision'] or checkout.get('manifest_sha256')!=self.execution['manifest_sha256']:raise Denied('CHECKOUT_BINDING_MISMATCH')
            self.stage('SV3_PUBLISH_READY')
            self.publish_ready(self.ready_marker({k:checkout[k] for k in ('revision','tree','controller_sha256','manifest_sha256','tracked_files_modified')},new_keys))
            self.stage('SV3_AWAIT_OWNER_REGISTRATION')
            self.await_marker(self.batch_bindings)      # no database connection while waiting; a marker that disagrees with the locally recomputed bindings is UNCERTAIN; timeout is a stop
            self.stage('SV3_AUTHORITY_CHECK')
            self.authority_check=self.authority_present()      # an unexpired grant must exist AND this checkout must be exactly the one the owner registered: a mismatch is a stop before anything is assessed
            self.stage('SV3_PLAN')
            with self.phase_as('runtime'):
                with self.slot(self.capture_key,self.batch_bindings,self.authority+'_SCREEN') as (co,budget):
                    budget.capture_checkpoint_sha256=CAPTURE_CHECKPOINT
                    live,live_plans,snapshot=assessment_plan(co,CAPTURE_KEY,capture_sha256=CAPTURE_CHECKPOINT,batch_keys=[p['key'] for p in plans],preserved_keys=preserved,check=lambda:(self.check(),budget.check()))
            if live!=receipt or [p['key'] for p in live_plans]!=[p['key'] for p in plans]:raise Uncertain('RETAINED_CAPTURE_DIFFERS_FROM_PINNED_EVIDENCE')      # the database holds exactly the pinned capture
            self.save_progress()
            self.stage('SV3_ASSESSMENT')
            self.screen()      # the accepted source-free queued screening: one accounted slot per batch, through the existing process_batch
            self.stage('SV3_VERIFICATION')
            with self.phase_as('runtime'):
                with self.slot(self.capture_key,self.batch_bindings,self.authority+'_SCREEN') as (co,budget):
                    assessments=verify_assessed(co,CAPTURE_KEY,receipt,capture_sha256=CAPTURE_CHECKPOINT,preserved_keys=preserved,snapshot=snapshot,check=lambda:(self.check(),budget.check()))
            result=self.hosted_result(qualification,assessments)
        except BaseException as exc:
            result=self.hosted_failure(exc,qualification)
        return result

    def hosted_result(self,qualification,assessments):
        from collections import Counter
        components=self.closure('RESTRICTED_RUNTIME_NO_ACCESS_CHANGE',memory_close=False)      # the memory scope keeps enforcing until the final result is published (finalise)
        return dict(status='SCREENING_V3_RETAINED_ASSESSED_RESTRICTED_RUNTIME_ONLY' if components['overall'] in ('CLOSED','PENDING_MEMORY_SCOPE_CLOSURE') else 'STOP_RECONCILE_NO_RETRY',closure_stage='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE',
                    execution=self.execution,checkout_binding=self.checkout_binding,cleanup=components['overall'],closure_components=components,qualification=qualification,rows=len(self.capture['records']),batches=len(self.plans),
                    assessments=len(assessments),eligible=[a['reference'] for a in assessments if a['eligible']],admissions=dict(Counter(a['admission'] for a in assessments)),capture_sha256=digest(self.capture),slot_receipts=self.receipts,
                    accounting=self.accounting(),authority_check_receipt=self.authority_check,config_sha256=digest(self.rule.config()),source_observations_attempted=0,application_writes=0,identities_created=0,credential_changes=0,grants_issued=0,
                    client_closure_vs_server_session='CLIENT_SIDE_RECEIPTS_ONLY_SERVER_SESSIONS_ARE_AN_OWNER_READBACK',pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True,
                    memory_enforcement=dict(kind='CGROUP_V2_ACTUAL_MEMORY' if self.memory is not None else 'NOT_ESTABLISHED',aggregate_bytes=1536*1024**2 if self.memory is not None else None))


def main(argv=None):
    return sp.main(argv,authority=SV3_HOSTED_AUTHORITY,runner_class=ScreeningV3HostedRunner,manifest_path=SV3_MANIFEST_PATH,scope=WINDOW_SCOPE)


if __name__=='__main__':main()
