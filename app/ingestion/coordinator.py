"""Shared stage coordinator; injected qualified readers, no legacy whole-run call.

This delivery is admitted only on disposable engines by Ledger. There are no
live authority registrations or network clients, schedules or later agents.
"""
from dataclasses import dataclass
import hashlib,json,math
from sqlalchemy import select
from .ledger import Denied,bounded,digest
from .listing_screening import qualifier_output_of,screen_row,routing_of,identity_admission_eligible,ScreeningRule,assessment_identity,SCREENING_CONTRACT_RULES,V1_CONTRACT,RULE_V1
from .resource_accounting import combined_bytes


def validate_outer(outer,limits):
    if (type(outer.get('exit_code')) is not int or outer['exit_code']!=0
        or type(outer.get('peak_owned_rss')) is not int or not 0<=outer['peak_owned_rss']<=limits['aggregate_rss']
        or type(outer.get('elapsed_seconds')) not in (int,float) or not math.isfinite(outer['elapsed_seconds'])
        or not 0<=outer['elapsed_seconds']<limits['outer_seconds'] or outer.get('cleanup')!='CLOSED'
        or type(outer.get('live_owned_survivors')) is not int or outer['live_owned_survivors']!=0
        or outer.get('expired') is not False or outer.get('limit_hit') is not None):raise Denied('OUTER_SAFETY')


def validate_source_resources(source,outer,limits):
    validate_outer(outer,limits)
    for k in ('requests','decoded_bytes','encoded_bytes','outbound_payload_bytes','peak_owned_rss'):
        if type(source.get(k)) is not int or source[k]<0:raise Denied('SOURCE_ACCOUNTING')
    if (source['requests']>limits['requests'] or combined_bytes(source)>limits['bytes'] or source['peak_owned_rss']>limits['source_rss']
        or type(source.get('supervisor_seconds')) not in (int,float) or not math.isfinite(source['supervisor_seconds']) or not 0<=source['supervisor_seconds']<=limits['worker_seconds']
        or source.get('cleanup')!='CONTEXT_BROWSER_CLOSED' or source.get('process_cleanup')!='CLOSED'
        or type(source.get('live_owned_survivors')) is not int or source['live_owned_survivors']!=0 or source.get('supervisor_limit_hit') is not False
        or source.get('safety_failure') is not False or source.get('safety_events')!=[]):raise Denied('SOURCE_SAFETY')
    bounded(source,min(128*1024,limits['audit_bytes']))


@dataclass(frozen=True)
class ListingContract:
    name:str
    config:object
    case:str
    audit_validator:object
    row_qualifier:object

    def __post_init__(self):
        if not callable(self.audit_validator) or not callable(self.row_qualifier):raise Denied("QUALIFIED_ADAPTER_REQUIRED")

    # Receipt validation is the existing reader's exact source-specific audit.
    def validate(self,source):
        if source.get('case')!=self.case or source.get('requested_interval')!=[self.config.start,self.config.end]:raise Denied('SOURCE_BINDING')
        self.audit_validator(source,self.config)
        for key in ('requests','decoded_bytes','encoded_bytes','outbound_payload_bytes','peak_owned_rss'):
            if type(source.get(key)) is not int or source[key]<0:raise Denied('SOURCE_ACCOUNTING')
        if source['peak_owned_rss']>1024**3:raise Denied('SOURCE_RSS')
        if type(source.get('supervisor_seconds')) not in (int,float) or not math.isfinite(source['supervisor_seconds']) or not 0<=source['supervisor_seconds']<=45:raise Denied('SOURCE_CLOCK')
        for row in source['listing_records']:
            fields=[dict(label='Reference',value=row['reference'])]
            if self.config.row_date:fields.append(dict(label='Valid Date',value=row['validated_date']['literal']))
            card=dict(fields=fields,links=[dict(text=row['reference'],href=row['source_url'])],assessment_capture=row['assessment_capture'])
            if self.row_qualifier('Showing 1 to 1 of 1 results',[card],1,config=self.config)[3][0]!=row:raise Denied('ROW_PROVENANCE')
        bounded(source)
        for seg in source['listing_segments']:
            if source['listing_records'] and seg.get('evidence_sha256')!=hashlib.sha256(json.dumps(source['listing_records'][seg['first']-1:seg['last']],sort_keys=True).encode()).hexdigest():raise Denied('SEGMENT_HASH')


@dataclass(frozen=True)
class FactualContract:
    name:str
    row:dict
    handoff:object
    verification_scope:str='COUPLED'


RELATED_ASSESSMENTS_CAP=50


class Coordinator:
    def __init__(self,ledger,contracts,*,isolated_contracts=(),screening_rules=None):
        self.ledger=ledger;self.contracts=dict(contracts);self.isolated_contracts=frozenset(isolated_contracts)
        # Explicit rule selection: v1 unless a rule is registered under its own contract name. ONE screening contract per run; a v3 threshold is read once, at ScreeningRule construction, and frozen here.
        rules=dict(screening_rules) if screening_rules else {V1_CONTRACT:ScreeningRule(RULE_V1)}
        if len(rules)!=1:raise ValueError('ONE_SCREENING_CONTRACT_PER_RUN')
        (name,rule),=rules.items()
        if not isinstance(rule,ScreeningRule) or SCREENING_CONTRACT_RULES.get(name)!=rule.rule_version:raise ValueError('SCREENING_CONTRACT_RULE_MISMATCH')
        self.screening_rules=rules;self.screening_contract=name;self.screening_rule=rule

    def _preflight_listing(self,claim):
        row=self.ledger.get(claim.key);subject=row['subject'];contract=self.contracts.get(row['contract'])
        if not isinstance(contract,ListingContract):raise Denied('UNSUPPORTED_CONTRACT')
        config=contract.config
        if (row['task'] not in {'DISCOVERY','LISTING_METADATA'} or subject.get('kind')!='DISCOVERY_SCOPE'
            or [subject.get(k) for k in ('council','start','end','semantics')]!=[config.council,config.start,config.end,'VALIDATED']):raise Denied('TASK_CONTRACT_SCOPE')
        return row,contract,config

    def _listing(self,claim,source,outer=None):
        row,contract,config=self._preflight_listing(claim)
        contract.validate(source)
        records=source['listing_records'];limits=row['limits']
        if (source['requests']>limits['requests'] or combined_bytes(source)>limits['bytes'] or source['supervisor_seconds']>limits['worker_seconds']
            or source['peak_owned_rss']>limits['source_rss'] or len(records)>limits['rows'] or len(source['listing_segments'])>limits['pages']):raise Denied('TASK_RESOURCE_LIMIT')
        bounded(source,min(128*1024,limits['audit_bytes']))
        receipt=dict(kind='LISTING_RECEIPT_V1',source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
            contract=contract.name,council=config.council,interval=[config.start,config.end],records=records,
            segments=source['listing_segments'],applied_interval=source['applied_interval'],cleanup='CLOSED',accounting_complete=True,
            outer_supervisor=outer,resources={k:source[k] for k in ('requests','decoded_bytes','encoded_bytes','outbound_payload_bytes','supervisor_seconds','peak_owned_rss')})
        # Both task checkpoint and attempt copy are bounded; no expiring URL needed.
        if row["phase"]=="SOURCE_INTENT" and hasattr(self.ledger,"resolve_source"):self.ledger.resolve_source(claim,receipt)
        else:self.ledger.checkpoint(claim,receipt)
        return receipt

    def listing(self,claim,source):
        """Retained-source path, no new source operation or authority consumption."""
        if self.ledger.get(claim.key)['phase'] not in {'CLAIMED','CHECKPOINTED'}:raise Denied('RETAINED_PATH_NO_EFFECT_INTENT')
        receipt=self._listing(claim,source)
        return self._materialize(claim,receipt)

    def _materialize(self,claim,receipt):
        row=self.ledger.get(claim.key);children=[]
        for record in receipt['records']:
            subject=dict(kind='APPLICATION',council=receipt['council'],reference=record['reference'])
            # Stable key/version makes crash between insert and acknowledgement safe.
            revision=digest(record) if self.screening_rule.rule_version==RULE_V1 else assessment_identity(record,self.screening_rule)[3]
            key=self.ledger.enqueue(subject,'SCREENING',contract=self.screening_contract,revision=revision,dependencies=[claim.key],priority=row['priority'],max_attempts=2,parent_claim=claim)
            children.append(key)
        self.ledger.finish(claim,dict(outcome='ENUMERATED_METADATA_RETAINED',children=children,source_sha256=receipt['source_sha256']))
        return children

    def resume_listing(self,claim):
        row=self.ledger.get(claim.key);receipt=row['checkpoint']
        if not receipt or receipt.get('kind')!='LISTING_RECEIPT_V1' or receipt.get('cleanup')!='CLOSED':raise Denied('NO_DURABLE_CHECKPOINT')
        # Reclaim rotates the fence and returns CLAIMED. Re-seal the unchanged
        # retained receipt under that fence before broker child materialisation.
        self.ledger.checkpoint(claim,receipt)
        return self._materialize(claim,receipt)

    def idox_listing(self,claim,source,outer):
        from .idox_adapter import IdoxListingContract
        row=self.ledger.get(claim.key);contract=self.contracts.get(row['contract'])
        if not isinstance(contract,IdoxListingContract):raise Denied('UNSUPPORTED_IDOX_CONTRACT')
        c=contract.config
        if row['task'] not in {'DISCOVERY','LISTING_METADATA'} or row['subject']!={'kind':'DISCOVERY_SCOPE','council':c.council,'start':c.start.isoformat(),'end':c.end.isoformat(),'semantics':c.semantics}:raise Denied('IDOX_TASK_SCOPE')
        if row['phase'] not in {'CLAIMED','CHECKPOINTED'}:raise Denied('IDOX_RETAINED_ONLY')
        receipt=contract.project(source,outer,row['limits'])
        # Store only JSON-safe data; dates in WindowEvidence stay string literals.
        receipt.pop('window')
        self.ledger.checkpoint(claim,receipt)
        return self._materialize(claim,receipt)

    def idox_source(self,claim,supervised_reader,*,materialize=True,archive=None):
        from .idox_adapter import IdoxListingContract
        row=self.ledger.get(claim.key);contract=self.contracts.get(row['contract'])
        if not isinstance(contract,IdoxListingContract):raise Denied('UNSUPPORTED_IDOX_CONTRACT')
        c=contract.config
        if row['subject']!={'kind':'DISCOVERY_SCOPE','council':c.council,'start':c.start.isoformat(),'end':c.end.isoformat(),'semantics':c.semantics}:raise Denied('IDOX_TASK_SCOPE')
        if row['checkpoint'] is not None:raise Denied('RESUME_CHECKPOINT_NO_SOURCE_REPLAY')
        self.ledger.intent(claim,'source_calls')
        try:
            source,outer=supervised_reader(row)
            if not materialize and archive is None:raise Denied('DURABLE_ARCHIVE_REQUIRED')
            saved=None
            if archive is not None:
                from .batching import archive_capture
                saved=archive_capture(source,archive)
            receipt=contract.project(source,outer,row['limits'],source_bytes_limit=512*1024) if not materialize else contract.project(source,outer,row['limits'])
            receipt.pop('window')
            if saved is not None:receipt['durable_archive']=saved
            try:bounded(receipt)
            except Denied:
                if materialize:raise
                blocked=dict(kind='CAPTURE_BLOCKED_V1',durable_archive=saved,reason='INLINE_PAYLOAD_BOUND',qualified_rows=len(receipt['records']),cleanup='CLOSED',accounting_complete=True)
                if hasattr(self.ledger,'resolve_source'):self.ledger.resolve_source(claim,blocked)
                else:self.ledger.checkpoint(claim,blocked)
                self.ledger.finish(claim,{'outcome':'CAPTURED_PROCESSING_BLOCKED'},state='UNSUPPORTED_CONTRACT',reason='INLINE_PAYLOAD_BOUND_NO_REFETCH')
                return []
            if hasattr(self.ledger,'resolve_source'):self.ledger.resolve_source(claim,receipt)
            else:self.ledger.checkpoint(claim,receipt)
            if materialize:return self._materialize(claim,receipt)
            self.ledger.finish(claim,dict(outcome='ENUMERATED_METADATA_RETAINED',children=[],source_sha256=receipt['source_sha256']))
            return []
        except Exception:
            self.ledger.stop('IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE',claim=claim)
            raise

    def idox_form_probe(self,claim,supervised_reader):
        """The form-probe analogue of idox_source: one DB-gated source intent, one form-only read, the observation recorded, the item finished UNSUPPORTED_CONTRACT (never reusable as a capture). A council
        answer of any kind is an observation. Only an unsafe or unaccountable outcome raises the accepted fail-safe stop."""
        from .idox_adapter import IdoxListingContract
        from .form_probe import project
        row=self.ledger.get(claim.key);contract=self.contracts.get(row['contract'])
        if not isinstance(contract,IdoxListingContract):raise Denied('UNSUPPORTED_IDOX_CONTRACT')
        c=contract.config
        if row['subject']!={'kind':'DISCOVERY_SCOPE','council':c.council,'start':c.start.isoformat(),'end':c.end.isoformat(),'semantics':c.semantics} or row['task']!='DISCOVERY':raise Denied('IDOX_TASK_SCOPE')
        if row['checkpoint'] is not None:raise Denied('RESUME_CHECKPOINT_NO_SOURCE_REPLAY')
        self.ledger.intent(claim,'source_calls')
        try:
            source,outer=supervised_reader(row)
            receipt=project(source,outer,row['limits'])
            bounded(receipt)
            self.ledger.resolve_source(claim,receipt)
            self.ledger.finish(claim,{'outcome':'FORM_PROBE_OBSERVED'},state='UNSUPPORTED_CONTRACT',reason='DIAGNOSTIC_FORM_PROBE_NO_CAPTURE')
        except Exception:
            self.ledger.stop('IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE',claim=claim)
            raise
        return receipt

    def metadata_from_scope(self,claim):
        row=self.ledger.get(claim.key)
        if row['task']!='LISTING_METADATA' or row['subject']['kind']!='APPLICATION' or len(row['dependencies'])!=1:raise Denied('METADATA_TASK')
        parent=self.ledger.get(row['dependencies'][0]);receipt=parent['checkpoint']
        if not receipt or receipt.get('kind')!='LISTING_RECEIPT_V1' or receipt['council']!=row['subject']['council']:raise Denied('NO_QUALIFIED_SCOPE_RECEIPT')
        records=[r for r in receipt['records'] if r['reference']==row['subject']['reference']]
        if len(records)!=1:
            self.ledger.checkpoint(claim,dict(outcome='NOT_RETURNED_IN_OBSERVATION',source_sha256=receipt['source_sha256']))
            self.ledger.finish(claim,dict(outcome='METADATA_WITHHELD'),state='UNSUPPORTED_CONTRACT',reason='REVIEW_CROSS_OBSERVATION_DIFFERENCE');return []
        receipt=dict(receipt,records=records)
        self.ledger.checkpoint(claim,receipt)
        return self._materialize(claim,receipt)

    def screening(self,claim):
        row=self.ledger.get(claim.key)
        if row['task']!='SCREENING' or row['contract'] not in SCREENING_CONTRACT_RULES or len(row['dependencies'])!=1:raise Denied('SCREENING_TASK')
        if row['contract']!=self.screening_contract:raise Denied('SCREENING_CONTRACT_NOT_REGISTERED')
        rule=self.screening_rule
        parent=self.ledger.get(row['dependencies'][0]);receipt=parent['checkpoint']
        records=[r for r in receipt['records'] if r['reference']==row['subject']['reference']]
        if len(records)!=1 or receipt['council']!=row['subject']['council']:raise Denied('SCREENING_IDENTITY')
        record=records[0]
        if rule.rule_version==RULE_V1:
            if digest(record)!=row['revision']:raise Denied('SCREENING_IDENTITY')
            binding={}
        else:
            # The stored identity must be exactly the one this run's frozen configuration derives from the record; a mismatch means the item was made under another record or configuration.
            record_sha,config,config_sha,revision=assessment_identity(record,rule)
            if revision!=row['revision']:raise Denied('SCREENING_CONFIG_BINDING')
            binding=dict(record_sha256=record_sha,config=config,config_sha256=config_sha,assessment_revision=revision)
        result=rule.screen(record)
        result.update(source_url=record['source_url'],source_record_id=record['source_record_id'],source_sha256=receipt['source_sha256'],proposal=record['fields']['proposal'],application_type=record['fields']['application_type'])
        if binding:
            from .screening_projection import screening_items,assessment_history      # imported lazily: a production registration never reaches here
            result.update(binding,assessment_sha256=digest(result['count_assessment']),qualifier_output_sha256=digest(qualifier_output_of(result)),capture_key=row['dependencies'][0],capture_sha256=receipt['source_sha256'],
                          capture_checkpoint_sha256=digest(receipt))
            # Informational links to other stored assessments of the same record; never `supersedes`, never "current", and no earlier item is touched.
            # Snapshot at screening time, capped so a checkpoint stays far inside the payload bound; assessment_history() over the ledger is the only authoritative, order-independent view.
            if rule.link_related:
                related=[e for e in assessment_history(screening_items(self.ledger),row['subject'],record_sha) if e['item_key']!=claim.key]
                result['related_assessments']=related[:RELATED_ASSESSMENTS_CAP];result['related_assessments_total']=len(related)
        self.ledger.checkpoint(claim,result);self.ledger.finish(claim,dict(outcome=routing_of(result)[1],retained=True))
        # No automatic factual task, parent retrieval or Application admission.
        return result

    def source(self,claim,supervised_reader):
        """Disposable qualification seam; existing supervisor receipt required.

        The caller cannot pass a production engine or historical authority. A
        reader must return the existing source audit plus its outer envelope.
        """
        self._preflight_listing(claim)
        prior=self.ledger.get(claim.key)['checkpoint']
        if prior is not None and prior.get('failure') not in {'RATE_LIMIT','SOURCE_UNAVAILABLE'}:raise Denied('RESUME_CHECKPOINT_NO_SOURCE_REPLAY')
        self.ledger.intent(claim,'source_calls')
        try:
            audit,outer=supervised_reader(self.ledger.get(claim.key))
            validate_source_resources(audit,outer,self.ledger.get(claim.key)['limits'])
            receipt=self._listing(claim,audit,outer)
            return self._materialize(claim,receipt)
        except Exception:
            self.ledger.stop('SOURCE_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE',claim=claim)
            raise

    def fail(self,claim,category,*,cleanup_closed,accounting_complete,council_isolated=False,source_audit=None,outer=None):
        """Reviewed finite policy; unknown failures and TargetClosed stop globally."""
        if not cleanup_closed or not accounting_complete or category not in {'RATE_LIMIT','SOURCE_UNAVAILABLE','UNSUPPORTED_CONTRACT','NO_SUPPORTED_FACTS'}:
            self.ledger.stop(category,claim=claim);return
        row=self.ledger.get(claim.key)
        if category in {'RATE_LIMIT','SOURCE_UNAVAILABLE'} and (not council_isolated or row['contract'] not in self.isolated_contracts):
            self.ledger.stop('ISOLATION_NOT_ESTABLISHED',claim=claim);return
        if row['phase']=='WRITE_INTENT':self.ledger.stop('UNCERTAIN_WRITE',claim=claim,persistence_uncertain=True);return
        if row['phase']=='SOURCE_INTENT':
            try:validate_source_resources(source_audit or {},outer or {},row['limits'])
            except Exception:
                self.ledger.stop('FAILURE_ACCOUNTING_OR_CLEANUP_UNKNOWN',claim=claim);raise
        receipt=dict(cleanup='CLOSED',accounting_complete=True,outer_supervisor=outer,failure=category,previous=row['checkpoint'])
        state='UNSUPPORTED_CONTRACT' if category in {'UNSUPPORTED_CONTRACT','NO_SUPPORTED_FACTS'} else 'DEFERRED'
        self.ledger.finish(claim,dict(outcome=category),state=state,reason=category,delay=3600 if state=='DEFERRED' else 0,resolved_receipt=receipt,council_defer_seconds=3600 if state=='DEFERRED' else 0)

    def factual_refresh(self,claim,*,council,observation,accepted_row):
        """Already captured qualified evidence -> shared B2 -> independent readback.

        Existing identities only. Unsupported evidence never creates a pending
        Application. New identity admission remains an explicit separate gate.
        """
        if self.ledger.engine.dialect.name!='postgresql':raise Denied('B2_REQUIRES_DISPOSABLE_POSTGRES')
        from sqlalchemy.orm import Session
        from app.db.models import Application
        row=self.ledger.get(claim.key)
        if row['task']!='FACTUAL_REFRESH' or row['subject']['kind']!='APPLICATION':raise Denied('FACTUAL_TASK')
        if (row['subject']['council']!=council.code or accepted_row['council']!=council.code or row['subject']['reference']!=accepted_row['reference']
            or observation.reference!=accepted_row['reference'] or observation.source_url!=accepted_row['source_url']):raise Denied('FACTUAL_IDENTITY')
        contract=self.contracts.get(row['contract'])
        if not isinstance(contract,FactualContract) or not callable(contract.handoff) or accepted_row!=contract.row or observation.verification_scope!=contract.verification_scope or contract.verification_scope!='COUPLED':raise Denied('UNSUPPORTED_FACTUAL_CONTRACT')
        if not observation.b2_eligible:
            self.ledger.checkpoint(claim,dict(outcome='FACTS_WITHHELD',reason='UNSUPPORTED_EVIDENCE',cleanup='CLOSED',accounting_complete=True))
            self.ledger.finish(claim,dict(outcome='FACTS_WITHHELD'),state='UNSUPPORTED_CONTRACT',reason='SUPPORTED_FACTS_REQUIRED');return
        with Session(self.ledger.engine) as s:
            app=s.execute(select(Application).where(Application.council_code==council.code,Application.reference==accepted_row['reference'])).scalar_one_or_none()
            if app is None:raise Denied('IDENTITY_ADMISSION_NOT_AUTHORISED')
            app_id=app.id
        if observation.application_id!=app_id or accepted_row['application_id']!=app_id:raise Denied('APPLICATION_ID')
        prior=row['checkpoint']
        if prior and prior.get('outcome')=='SUPPORTED_FACTS_VERIFIED':
            with Session(self.ledger.engine) as s:
                app=s.get(Application,app_id)
                actual={k:(v.isoformat() if hasattr(v,'isoformat') else v) for k in prior['readback'] for v in [getattr(app,k)]}
            if actual!=prior['readback']:
                self.ledger.stop('COMMITTED_READBACK_CHANGED');raise Denied('RECONCILIATION_REQUIRED')
            self.ledger.finish(claim,prior);return prior
        def writer(_):
            with Session(self.ledger.engine) as s:
                app=s.get(Application,app_id);result=contract.handoff(s,app,council,accepted_row,retrieve_evidence=lambda:observation)
                if not result['accepted']:raise RuntimeError('B2_NOT_ACCEPTED')
                names=('id','council_code','reference','status','decision','decision_issued_date','status_verified_at','planning_field_verification')
                before={k:getattr(app,k) for k in names}
            with Session(self.ledger.engine) as s:
                after={k:getattr(s.get(Application,app_id),k) for k in names}
            if before!=after:raise RuntimeError('COMMITTED_READBACK_UNRESOLVED')
            return dict(outcome='SUPPORTED_FACTS_VERIFIED',identity='EXISTING_IDENTITY_PRESERVED',application_id=app_id,readback={k:(v.isoformat() if hasattr(v,'isoformat') else v) for k,v in after.items()})
        self.ledger.intent(claim,'writes');result=self.ledger.fenced_effect(claim,writer)
        self.ledger.finish(claim,result);return result

    def new_identity(self,claim,*,envelope,council,source):
        from .new_identity import execute
        return execute(self,claim,envelope=envelope,council=council,source=source)

    def new_identity_source(self,claim,*,envelope,council,supervised_reader):
        from .new_identity import NewIdentityContract
        row=self.ledger.get(claim.key);contract=self.contracts.get(row['contract'])
        if not isinstance(contract,NewIdentityContract) or row['subject']!={'kind':'APPLICATION','council':envelope.council,'reference':envelope.reference}:raise Denied('EXACT_DETAIL_BINDING')
        from app.pipeline.discovery_contract import Completeness
        if row['task']!='FACTUAL_REFRESH' or (contract.row['council'],contract.row['reference'],contract.row['source_url'])!=(envelope.council,envelope.reference,envelope.source_url) or council.code!=envelope.council or envelope.window.outcome!=Completeness.COMPLETE:raise Denied('EXACT_DETAIL_CONTRACT_BEFORE_SOURCE')
        if len(row['dependencies'])!=1:raise Denied('SELECTIVE_SCREENING_REQUIRED')
        parent=self.ledger.get(row['dependencies'][0]);screen=parent['checkpoint'] or {}
        if parent['state']!='COMPLETE' or parent['task']!='SCREENING' or parent['subject']!=row['subject'] or not identity_admission_eligible(screen,parent) or screen.get('source_url')!=envelope.source_url or screen.get('source_record_id')!=envelope.source_record_id:raise Denied('SELECTIVE_SCREENING_REQUIRED')
        prior=row['checkpoint']
        if prior is not None:
            if prior.get('kind')=='DETAIL_RECEIPT_V1':return self.new_identity(claim,envelope=envelope,council=council,source=prior['source'])
            if prior.get('outcome')=='SUPPORTED_FACTS_VERIFIED':return self.new_identity(claim,envelope=envelope,council=council,source={})
            raise Denied('DETAIL_NO_REPLAY')
        self.ledger.intent(claim,'source_calls')
        try:
            source,outer=supervised_reader(row)
            validate_outer(outer,row['limits'])
            packet=contract.projector(contract.row,source)
            # Retain failed/unsupported observations truthfully; execute withholds
            # admission, preserving the consumed source call and original evidence.
            receipt=dict(kind='DETAIL_RECEIPT_V1',source=source,source_sha256=digest(source),cleanup='CLOSED',accounting_complete=True,outer_supervisor=outer)
            if packet['audit'].get('cleanup_state')!='CLOSED' or packet['audit'].get('budget_state')!='WITHIN_LIMITS' or packet['failure'] in {'CLEANUP_FAILURE','SCOPE_ESCAPE','ACCOUNTING_FAILURE','INVALID_ARTIFACT','UNSUPPORTED_ROUTE'}:raise Denied('DETAIL_RESOURCE_OR_CONTRACT')
            if hasattr(self.ledger,'resolve_source'):self.ledger.resolve_source(claim,receipt)
            else:self.ledger.checkpoint(claim,receipt)
            return self.new_identity(claim,envelope=envelope,council=council,source=source)
        except Exception:
            self.ledger.stop('DETAIL_OR_WRITE_RECONCILIATION_REQUIRED')
            raise
