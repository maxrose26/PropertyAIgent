"""Exact retained-v3 nominee handoff; no CLI, registration or new capability.

The trusted caller supplies accounted restricted engines and an already issued
authority. This wrapper validates evidence before the existing controller owns
the source intent, fence, shared admission/B2 and committed readback.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib

from app.ingestion.ledger import Denied, digest
from app.ingestion.listing_screening import RULE_V3, V3_CONTRACT, assessment_identity, code_binding, routing_of
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.arcus_adapter import ArcusListingContract
from .new_identity_contract import ARCUS_PROJECTION_MODULES, accepted_arcus_new_identity, accepted_idox_new_identity
from .operational_controller import AcceptanceBinding, ControllerLedger, _execute


@dataclass(frozen=True)
class V3AdmissionBinding:
    nominee: AcceptanceBinding
    council: str
    capture_contract: str
    capture_revision: str
    screening_config_sha256: str
    screening_code_sha256: str
    factual_contract: str
    factual_revision: str
    factual_contract_sha256: str


def factual_binding(contract):
    """Bind the existing factory and its target, not an arbitrary callable.

    No new council qualification: only the two reviewed families (Idox and Arcus) are bound; unrecognised projectors are refused.
    Module bytes are part of the binding; the overall reviewed revision remains
    a separate controller/registration prerequisite.
    """
    from app.ingestion.new_identity import NewIdentityContract
    if not isinstance(contract, NewIdentityContract):
        raise Denied('V3_FACTUAL_CONTRACT_REQUIRED')
    components = ('projector', 'handoff', 'coupled_gate')
    for factory, extra in ((accepted_idox_new_identity, ()), (accepted_arcus_new_identity, ARCUS_PROJECTION_MODULES)):
        known = factory(contract.name, contract.row, verification_scope=contract.verification_scope)
        if all(getattr(contract, name) is getattr(known, name) for name in components):
            break
    else:
        raise Denied('V3_FACTUAL_COMPONENT_UNSUPPORTED')      # only the two reviewed factories; Arcus no longer refused, anything else still is
    import inspect
    modules = {getattr(known, name).__module__ for name in components} | set(extra)
    modules.add(__name__.rsplit('.', 1)[0] + '.new_identity_contract')
    import importlib
    hashes = {name: hashlib.sha256(Path(inspect.getsourcefile(importlib.import_module(name))).read_bytes()).hexdigest()
              for name in sorted(modules)}
    return digest(dict(name=contract.name, row=contract.row, verification_scope=contract.verification_scope, modules=hashes))


def execute_retained_v3(coordinator, binding, *, detail_reader, envelope, council, check=lambda: None, allow_test_evidence=False):
    """No listing callback exists here: a complete saved capture is mandatory.

    Ineligible records remain untouched investigation evidence. No row/grant is
    created by nomination. All effects still go through execute/new_identity.
    """
    ledger = coordinator.ledger
    if not isinstance(ledger, ControllerLedger) or not isinstance(binding, V3AdmissionBinding):
        raise Denied('V3_ACCOUNTED_RETAINED_HANDOFF_REQUIRED')
    check()
    b = binding.nominee
    rule = coordinator.screening_rule
    if rule.rule_version != RULE_V3 or coordinator.screening_contract != V3_CONTRACT:
        raise Denied('V3_EXPLICIT_RULE_REQUIRED')
    if (not b.retained_capture_sha256 or not b.screening_batch_key
            or digest(rule.config()) != binding.screening_config_sha256
            or digest(code_binding()) != binding.screening_code_sha256
            or rule.config()['code_binding'] != code_binding()):
        raise Denied('V3_CONFIGURATION_OR_CAPTURE_BINDING')
    root = ledger.get(b.discovery_key)
    receipt = root['checkpoint'] or {}
    contract = coordinator.contracts.get(root['contract'])
    if (root['state'] != 'COMPLETE' or root['task'] != 'DISCOVERY'
            or (root['contract'], root['revision']) != (binding.capture_contract, binding.capture_revision)
            or receipt.get('kind') != 'LISTING_RECEIPT_V1' or digest(receipt) != b.retained_capture_sha256
            or not isinstance(contract, (IdoxListingContract, ArcusListingContract))
            or binding.council != council.code or receipt.get('council') != binding.council
            or envelope.council != binding.council):
        raise Denied('V3_COMPLETE_IDOX_CAPTURE_REQUIRED')
    if receipt.get('evidence_label') and not allow_test_evidence:
        raise Denied('TEST_EVIDENCE_NOT_LIVE')      # a labelled test artefact is never live evidence unless a test explicitly opts in
    records = [r for r in receipt['records'] if r['reference'] == b.reference]
    if len(records) != 1 or digest(records[0]) != b.listing_revision:
        raise Denied('V3_NOMINATED_RECORD_BINDING')
    record = records[0]
    record_sha, config, config_sha, revision = assessment_identity(record, rule)
    batch = ledger.get(b.screening_batch_key)
    progress = batch['checkpoint'] or {}
    plan = progress.get('plan', {})
    if (batch['state'] != 'COMPLETE' or batch['task'] != 'LISTING_METADATA'
            or batch['contract'] != 'listing-batch-v1' or batch['subject'] != root['subject']
            or b.discovery_key not in batch['dependencies'] or batch['revision'] != digest(plan)
            or progress.get('kind') != 'BATCH_PROGRESS_V1'
            or plan.get('capture_key') != b.discovery_key or plan.get('capture_sha256') != digest(receipt)
            or plan.get('screening') != dict(contract=V3_CONTRACT, config_sha256=config_sha)
            or progress.get('next') != plan.get('last') or b.screening_key not in progress.get('children', [])
            or record not in receipt['records'][plan.get('first', 0):plan.get('last', 0)]):
        raise Denied('V3_COMPLETED_BATCH_BINDING')
    # The current daily intake commits capture-specific v3 screen revisions;
    # historical v3 children remain unbound. The saved plan, not a caller
    # flag or a proposed fact, selects which exact identity is admissible.
    mode = plan.get('capture_bound', False)
    capture_bound = mode is True
    if (type(mode) is not bool
            or capture_bound is not (coordinator.capture_bound_screening is True)):
        raise Denied('V3_CAPTURE_BOUND_MODE')
    if capture_bound:
        from app.ingestion.observation_screening import observation_revision
        revision = observation_revision(revision, digest(receipt))
    screen = ledger.get(b.screening_key)
    subject = dict(kind='APPLICATION', council=binding.council, reference=b.reference)
    if (screen['state'] != 'COMPLETE' or screen['task'] != 'SCREENING'
            or screen['contract'] != V3_CONTRACT or screen['revision'] != revision
            or screen['subject'] != subject or screen['dependencies'] != [b.discovery_key]):
        raise Denied('V3_COMPLETED_SCREENING_BINDING')
    stored = screen['checkpoint'] or {}
    expected = rule.screen(record)
    if ((stored.get('capture_bound') is True) is not capture_bound
            or any(stored.get(k) != v for k, v in expected.items())
            or stored.get('record_sha256') != record_sha or stored.get('config') != config
            or stored.get('config_sha256') != config_sha or stored.get('assessment_revision') != revision):
        raise Denied('V3_ASSESSMENT_BINDING')
    outcome = routing_of(expected)[1]
    if outcome not in {'ADMIT_SCHEME', 'ADMIT_FOR_ASSESSMENT'}:
        return dict(outcome='RETAINED_INVESTIGATION_OR_EXCLUSION', screening=outcome,
                    admission='NOT_ATTEMPTED', b2='NOT_ATTEMPTED', application_writes=0)
    factual = ledger.get(b.factual_key)
    factual_contract = coordinator.contracts.get(binding.factual_contract)
    if (factual['task'] != 'FACTUAL_REFRESH' or factual['subject'] != subject
            or factual['dependencies'] != [b.screening_key]
            or (factual['contract'], factual['revision']) != (binding.factual_contract, binding.factual_revision)
            or factual_binding(factual_contract) != binding.factual_contract_sha256
            or (factual_contract.row['council'], factual_contract.row['reference'], factual_contract.row['source_url'], factual_contract.row.get('source_identifier'))
                != (binding.council, b.reference, b.source_url, b.source_record_id)):
        raise Denied('V3_FACTUAL_TASK_BINDING')
    def no_listing(_):
        raise Denied('V3_SOURCE_REFETCH_FORBIDDEN')
    return _execute(coordinator, b, listing_reader=no_listing, detail_reader=detail_reader,
                   envelope=envelope, council=council, check=check)


def readback_committed_v3_facts(work_connection, application_engine, factual_key, *, council, reference):
    """Bounded Stage 4 read-only proof: saved v3 fact and independently saved B2 row.

    A returned match is a factual/status readback, NOT a source-completeness,
    development-unit, buyer-fit, or Stage 4 qualification certificate.
    The caller supplies existing authenticated connections. No grants, writes,
    external requests, issuance, or retry of uncertain effects occur here.
    """
    from app.ingestion.ledger import bounded
    from app.pipeline.discovery_admission import PROTECTED_FIELDS
    from app.db.models import Application
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    import re
    if (type(factual_key) is not str or not re.fullmatch(r'[a-f0-9]{64}', factual_key)
            or type(council) is not str or not re.fullmatch(r'[a-z]{2,25}', council)
            or type(reference) is not str or not 1 <= len(reference) <= 100
            or reference != reference.strip()):
        raise Denied('FACT_READBACK_BOUND')

    def one(key):
        rows = work_connection.execute(
            "SELECT row_to_json(w) FROM public.ingestion_work_items AS w WHERE w.key=%s LIMIT 2",
            (key,)).fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], dict):
            raise Denied('FACT_READBACK_ROW_MISSING')
        return rows[0][0]

    fact = one(factual_key)
    subject = dict(kind='APPLICATION', council=council, reference=reference)
    if (fact.get('key') != factual_key or fact.get('task') != 'FACTUAL_REFRESH'
            or fact.get('subject') != subject or fact.get('state') != 'COMPLETE'
            or fact.get('phase') != 'FINISHED'
            or not isinstance(fact.get('dependencies'), list)
            or len(fact['dependencies']) != 1):
        raise Denied('FACT_READBACK_TASK')
    screen = one(fact['dependencies'][0])
    screen_state = screen.get('checkpoint')
    screen_outcome = screen.get('outcome')
    if (screen.get('task') != 'SCREENING' or screen.get('state') != 'COMPLETE'
            or screen.get('subject') != subject
            or screen.get('contract') != 'listing-screen-v3'
            or not isinstance(screen_state, dict)
            or screen_state.get('capture_bound') is not True
            or not isinstance(screen_outcome, dict)
            or screen_outcome.get('outcome') not in ('ADMIT_SCHEME', 'ADMIT_FOR_ASSESSMENT')
            or screen_outcome.get('retained') is not True
            or not isinstance(screen.get('dependencies'), list)
            or len(screen['dependencies']) != 1):
        raise Denied('FACT_READBACK_SCREEN')
    capture = one(screen['dependencies'][0])
    receipt = capture.get('checkpoint')
    if (capture.get('task') != 'DISCOVERY' or capture.get('state') != 'COMPLETE'
            or not isinstance(receipt, dict) or receipt.get('kind') != 'LISTING_RECEIPT_V1'
            or capture.get('subject', {}).get('council') != council
            or receipt.get('council') != council
            or not isinstance(receipt.get('records'), list)
            or len(receipt['records']) > 60
            or screen_state.get('capture_key') != capture['key']
            or screen_state.get('capture_checkpoint_sha256') != digest(receipt)
            or screen_state.get('source_sha256') != receipt.get('source_sha256')
            or receipt.get('accounting_complete') is not True
            or receipt.get('cleanup') != 'CLOSED'
            or not isinstance(receipt.get('durable_archive'), dict)
            or receipt['durable_archive'].get('readback_verified') is not True
            or receipt['durable_archive'].get('sha256') != receipt.get('source_sha256')
            or sum(r.get('reference') == reference for r in receipt['records']
                   if isinstance(r, dict)) != 1):
        raise Denied('FACT_READBACK_CAPTURE')
    candidate = next(r for r in receipt['records'] if r['reference'] == reference)
    if (screen_state.get('record_sha256') != digest(candidate)
            or screen_state.get('source_url') != candidate.get('source_url')
            or screen_state.get('source_record_id') != candidate.get('source_record_id')):
        raise Denied('FACT_READBACK_SOURCE_BINDING')
    outcome, saved = fact.get('outcome'), fact.get('checkpoint')
    if (not isinstance(outcome, dict) or not isinstance(saved, dict)
            or outcome != saved
            or outcome.get('outcome') != 'SUPPORTED_FACTS_VERIFIED'
            or outcome.get('identity') != 'COMMITTED_PENDING_IDENTITY'
            or outcome.get('verification_scope') != 'COUPLED'
            or outcome.get('unit_facts') != 'NOT_WRITTEN'
            or outcome.get('cleanup') != 'CLOSED'
            or outcome.get('accounting_complete') is not True
            or type(outcome.get('application_id')) is not int
            or outcome['application_id'] <= 0):
        raise Denied('FACT_READBACK_OUTCOME')
    stored = saved.get('readback')
    if (not isinstance(stored, dict)
            or stored.get('application_id') != outcome['application_id']
            or not isinstance(stored.get('protected'), dict)
            or set(stored['protected']) != set(PROTECTED_FIELDS)):
        raise Denied('FACT_READBACK_SNAPSHOT')
    bounded([fact, screen, capture], 2 * 1024 ** 2)
    with Session(application_engine) as session:
        columns = [Application.id, *[getattr(Application, field) for field in PROTECTED_FIELDS]]
        rows = session.execute(select(*columns).where(
            Application.id == outcome['application_id'],
            Application.council_code == council,
            Application.reference == reference).limit(2)).mappings().all()
    if len(rows) != 1:
        raise Denied('FACT_READBACK_APPLICATION_MISSING')
    actual = {field: (rows[0][field].isoformat() if hasattr(rows[0][field], 'isoformat')
                      else rows[0][field]) for field in PROTECTED_FIELDS}
    if (actual != stored['protected']
            or not actual.get('status_verified_at')
            or not actual.get('status')):
        raise Denied('FACT_READBACK_APPLICATION_CHANGED')
    return dict(council=council, reference=reference,
                application_id=outcome['application_id'], factual_key=factual_key,
                state='COMMITTED_B2_FACTS_READ_BACK',
                saved_key_facts={key: actual[key] for key in
                                 ('status', 'decision', 'decision_issued_date')},
                verification_scope='COUPLED', unit_count_verified=False,
                source_completeness='UNKNOWN', buyer_opportunity_qualified=False)
