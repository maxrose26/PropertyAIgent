"""Owner-side preparation of the integrated chain's work items, grants and bindings from VALIDATED captures and nominees (dormant: it prepares, it never issues).

Everything a registration contains is derived here, by the production `Owner.build_grant`, from: a scope binding, the listing contract that captures exactly that scope, the saved
capture receipt and the nominee set RE-DERIVED from that receipt. A caller cannot name a key, a contract, a binding, a counter or an outcome. Insertion of the rows and the issuing of the
authority (`Owner.register`, which also registers the policy's named exception) is a separate, later, owner-only act that this module does not perform: the live exception function
accepts only the pinned Bolton scope today (`BOLTON_ONLY`, `EXACT_BOLTON_DAY`), so issuing for another council needs a reviewed policy step that does not exist yet.
"""
import hashlib
import time
from dataclasses import dataclass, field

from app.ingestion.batching import batch_plans
from app.ingestion.ledger import Denied, digest
from app.ingestion.listing_screening import V3_CONTRACT, assessment_identity
from app.ingestion.nomination import derive_nominees
from . import new_identity_contract
from .limit_reconciliation import grant_problems, reconcile_items
from .operational_owner import item
from .scope_binding import check_contract, check_detail_target, scope_for,check_capture

AUTHORITY_PREFIX = 'INGESTION_CHAIN_'      # a disposable/design name; NO live policy recognises it (see the module docstring)
FACTUAL_OUTCOMES = ['SUPPORTED_FACTS_VERIFIED', 'ALREADY_KNOWN']


@dataclass
class Registration:
    kind: str                       # 'CAPTURE' | 'CHAIN'
    authority: str
    rows: list                      # every row this registration's grant binds (including the already-registered root for CHAIN)
    insert: list                    # the rows still to be inserted by the owner
    grant: dict
    bindings: dict
    root_key: str
    factual_contracts: dict = field(default_factory=dict)      # reference -> accepted new-identity contract
    batches: list = field(default_factory=list)
    screens: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)


def authority_name(binding, kind, revision):
    return f'{AUTHORITY_PREFIX}{binding.council.upper()}_{kind}_{hashlib.sha256(revision.encode()).hexdigest()[:12].upper()}'


def capture_registration(owner, binding, contract, start, end, *, revision, item_limits):
    """The root DISCOVERY item and the retained-capture grant for exactly one scope. Source calls are 0: a retained capture spends none."""
    check_contract(binding, contract, start, end)
    reconcile_items(binding, item_limits)
    root = item(dict(subject=scope_for(binding, start, end), task='DISCOVERY', contract=contract.name, revision=revision), limits=dict(item_limits))
    bindings, grant = owner.build_grant([root], [], capture_key=root['key'], source_calls=0, capture_only=False)
    return Registration('CAPTURE', authority_name(binding, 'CAPTURE', revision), [root], [root], grant, bindings, root['key'])


def chain_registration(owner, binding, contract, root, receipt, nominees, rule, detail_targets, *, revision, item_limits, allow_test_evidence=False, other_receipts=()):
    """The batch, screening and factual items and the one grant covering them, for exactly the nominees the receipt yields.

    `detail_targets` maps reference -> the fresh-detail case target; each must name exactly the nominated record (`check_detail_target`). Refuses before preparing anything when the
    receipt is not the stored root's saved capture of exactly this scope (contract, interval, date basis), when `nominees` is not exactly what `derive_nominees` yields from it, when a limit does not fit, or when the authority would be
    expired or too short for the work it covers.
    """
    scope = contract.scope()
    if (root.get('subject') != scope or root.get('task') != 'DISCOVERY' or root.get('contract') != contract.name or receipt.get('council') != binding.council
            or receipt.get('contract') != contract.name or receipt.get('interval') != [scope['start'], scope['end']] or receipt.get('date_semantics', 'RECEIVED') != scope['semantics']
            or root.get('checkpoint') != receipt):      # the receipt must BE the stored root's saved capture, for exactly this scope
        raise Denied('CHAIN_FOREIGN_CAPTURE')
    reconcile_items(binding, item_limits)
    check_capture(binding,contract,receipt)
    from .idox_target import COUNCILS
    if binding.council in COUNCILS and detail_targets is not None and (not isinstance(detail_targets,dict) or set(detail_targets)!={n.reference for n in nominees}):raise Denied('CLOSED_IDOX_TARGET_SET')
    # `other_receipts` are further saved captures of the same council, supplied only so that a reference observed differently elsewhere is withheld; the nominees registered here are
    # exactly those the derivation binds to THIS capture.
    derived = derive_nominees([receipt, *other_receipts], rule, allow_test_evidence=allow_test_evidence)
    if tuple(nominees) != tuple(n for n in derived.nominees if n.capture_sha256 == digest(receipt)):
        raise Denied('CHAIN_NOMINEES_NOT_DERIVED')
    plans = batch_plans(root['key'], receipt, rule)
    batches = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint'], limits=dict(item_limits)) for p in plans]
    screens = {}
    for record in receipt['records']:
        subject = dict(kind='APPLICATION', council=binding.council, reference=record['reference'])
        screens[record['reference']] = item(dict(subject=subject, task='SCREENING', contract=V3_CONTRACT, revision=assessment_identity(record, rule)[3]), dependencies=[root['key']], limits=dict(item_limits))
    by_reference = {r['reference']: r for r in receipt['records']}
    from .idox_target import COUNCILS,derive
    factory = getattr(new_identity_contract, binding.detail_factory)
    contracts, facts = {}, {}
    for nominee in nominees:
        record = by_reference[nominee.reference]
        target = check_detail_target(binding, record, derive(binding.council,record) if binding.council in COUNCILS and detail_targets is None else (detail_targets or {}).get(nominee.reference))
        fc = factory(f'chain-fact-{binding.council}-{digest(record)[:16]}', target,**({'verification_scope':'COUPLED'} if binding.council in COUNCILS else {}))
        contracts[nominee.reference] = fc
        subject = dict(kind='APPLICATION', council=binding.council, reference=nominee.reference)
        facts[nominee.reference] = item(dict(subject=subject, task='FACTUAL_REFRESH', contract=fc.name, revision=revision), dependencies=[screens[nominee.reference]['key']], limits=dict(item_limits))
    lifetime = (owner.grant_expiry or owner.expiry).timestamp() - time.time()      # the clock is read here, never supplied by the caller
    problems = grant_problems(binding, lifetime, batches=len(batches), nominees=len(nominees))
    if problems:
        raise Denied('LIMIT_INCOMPATIBLE:' + ','.join(problems))
    rows = [root, *batches, *screens.values(), *facts.values()]
    bindings, grant = owner.build_grant(rows, [], capture_key=root['key'], source_calls=len(nominees), capture_only=False, screening=rule, writes=2 * len(nominees),
                                        detail_source_keys=[f['key'] for f in facts.values()], extra_outcomes={'FACTUAL_REFRESH': FACTUAL_OUTCOMES})
    return Registration('CHAIN', authority_name(binding, 'CHAIN', revision), rows, [*batches, *facts.values()], grant, bindings, root['key'], contracts, batches, screens, facts)
