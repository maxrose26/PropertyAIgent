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
from .new_identity_contract import accepted_idox_new_identity
from .operational_controller import AcceptanceBinding, ControllerLedger, execute


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

    No new council qualification: Arcus and unrecognised projectors are refused.
    Module bytes are part of the binding; the overall reviewed revision remains
    a separate controller/registration prerequisite.
    """
    from app.ingestion.new_identity import NewIdentityContract
    if not isinstance(contract, NewIdentityContract):
        raise Denied('V3_FACTUAL_CONTRACT_REQUIRED')
    known = accepted_idox_new_identity(contract.name, contract.row, verification_scope=contract.verification_scope)
    components = ('projector', 'handoff', 'coupled_gate')
    if any(getattr(contract, name) is not getattr(known, name) for name in components):
        raise Denied('V3_FACTUAL_COMPONENT_UNSUPPORTED')
    import inspect
    modules = {getattr(known, name).__module__ for name in components}
    modules.add(__name__.rsplit('.', 1)[0] + '.new_identity_contract')
    import importlib
    hashes = {name: hashlib.sha256(Path(inspect.getsourcefile(importlib.import_module(name))).read_bytes()).hexdigest()
              for name in sorted(modules)}
    return digest(dict(name=contract.name, row=contract.row, verification_scope=contract.verification_scope, modules=hashes))


def execute_retained_v3(coordinator, binding, *, detail_reader, envelope, council, check=lambda: None):
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
            or not isinstance(contract, IdoxListingContract)
            or binding.council != council.code or receipt.get('council') != binding.council
            or envelope.council != binding.council):
        raise Denied('V3_COMPLETE_IDOX_CAPTURE_REQUIRED')
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
    screen = ledger.get(b.screening_key)
    subject = dict(kind='APPLICATION', council=binding.council, reference=b.reference)
    if (screen['state'] != 'COMPLETE' or screen['task'] != 'SCREENING'
            or screen['contract'] != V3_CONTRACT or screen['revision'] != revision
            or screen['subject'] != subject or screen['dependencies'] != [b.discovery_key]):
        raise Denied('V3_COMPLETED_SCREENING_BINDING')
    stored = screen['checkpoint'] or {}
    expected = rule.screen(record)
    if (any(stored.get(k) != v for k, v in expected.items())
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
            or (factual_contract.row['council'], factual_contract.row['reference'], factual_contract.row['source_url'])
                != (binding.council, b.reference, b.source_url)):
        raise Denied('V3_FACTUAL_TASK_BINDING')
    def no_listing(_):
        raise Denied('V3_SOURCE_REFETCH_FORBIDDEN')
    return execute(coordinator, b, listing_reader=no_listing, detail_reader=detail_reader,
                   envelope=envelope, council=council, check=check)
