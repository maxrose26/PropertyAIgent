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
from .limit_reconciliation import grant_problems, reconcile_items, pending_grant_problems
from .operational_owner import item
from .scope_binding import check_contract, check_detail_target, scope_for,check_capture

AUTHORITY_PREFIX = 'INGESTION_CHAIN_'      # a disposable/design name; NO live policy recognises it (see the module docstring)
FACTUAL_OUTCOMES = ['SUPPORTED_FACTS_VERIFIED', 'ALREADY_KNOWN']


@dataclass
class Registration:
    kind: str                       # historical CAPTURE/CHAIN; opt-in SCREENING/ADMISSION
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


def chain_registration(owner, binding, contract, root, receipt, nominees, rule, detail_targets, *, revision, item_limits, allow_test_evidence=False, other_receipts=(), _pending_admission=False,capture_bound=False):
    """The batch, screening and factual items and the one grant covering them, for exactly the nominees the receipt yields.

    `detail_targets` maps reference -> the fresh-detail case target; each must name exactly the nominated record (`check_detail_target`). Refuses before preparing anything when the
    receipt is not the stored root's saved capture of exactly this scope (contract, interval, date basis), when `nominees` is not exactly what `derive_nominees` yields from it, when a limit does not fit, or when the authority would be
    expired or too short for the work it covers.
    """
    _capture_inputs(binding,contract,root,receipt,item_limits)
    from .idox_target import COUNCILS
    if binding.council in COUNCILS and detail_targets is not None and (not isinstance(detail_targets,dict) or set(detail_targets)!={n.reference for n in nominees}):raise Denied('CLOSED_IDOX_TARGET_SET')
    # `other_receipts` are further saved captures of the same council, supplied only so that a reference observed differently elsewhere is withheld; the nominees registered here are
    # exactly those the derivation binds to THIS capture.
    derived = derive_nominees([receipt, *other_receipts], rule, allow_test_evidence=allow_test_evidence,capture_bound=capture_bound)
    if tuple(nominees) != tuple(n for n in derived.nominees if n.capture_sha256 == digest(receipt)):
        raise Denied('CHAIN_NOMINEES_NOT_DERIVED')
    batches,screens = _screen_items(binding,root,receipt,rule,item_limits,capture_bound=capture_bound)
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
    problems = pending_grant_problems(lifetime,phase='ADMISSION',nominees=len(nominees)) if _pending_admission else grant_problems(binding, lifetime, batches=len(batches), nominees=len(nominees))
    if problems:
        raise Denied('LIMIT_INCOMPATIBLE:' + ','.join(problems))
    rows = [root, *batches, *screens.values(), *facts.values()]
    bindings, grant = owner.build_grant(rows, [], capture_key=root['key'], source_calls=len(nominees), capture_only=False, screening=rule, writes=2 * len(nominees),
                                        detail_source_keys=[f['key'] for f in facts.values()], extra_outcomes={'FACTUAL_REFRESH': FACTUAL_OUTCOMES})
    return Registration('CHAIN', authority_name(binding, 'CHAIN', revision), rows, [*batches, *facts.values()], grant, bindings, root['key'], contracts, batches, screens, facts)



def persisted_council_capture_inventory(connection, council, *, max_roots=128):
    """Owner-side READ-ONLY inventory of *stored* discovery roots in one SQL snapshot.

    This is an offline preparation/readback aid, NOT a new restricted-worker
    capability, source-completeness proof, permission to issue grants, or proof
    that historical R0 receipts were persisted. The caller owns and independently
    authenticates the existing connection; this helper neither obtains credentials
    nor changes the database. Every known unfinished root refuses nomination,
    rather than silently omitting a possibly conflicting observation.
    """
    from app.config import load_councils
    # Read-only inventory recognises all ten configured GM councils, including
    # Trafford; configuration is NOT source qualification or an execution grant.
    if council not in load_councils() or type(max_roots) is not int or not 1 <= max_roots <= 128:
        raise Denied('CAPTURE_INVENTORY_SCOPE')
    raw = connection.execute(
        "SELECT row_to_json(w) FROM public.ingestion_work_items AS w "
        "WHERE w.task='DISCOVERY' AND w.subject->>'council'=%s "
        "ORDER BY w.key LIMIT %s",
        (council, max_roots + 1),
    ).fetchall()
    if not raw or len(raw) > max_roots:
        raise Denied('CAPTURE_INVENTORY_EMPTY_OR_BOUND')
    roots = [r[0] for r in raw]
    # Reuse the existing 2 MiB readback ceiling; 128 small roots is not a
    # licence to materialise unbounded private captures in this process.
    from app.ingestion.ledger import bounded
    bounded(roots, 2 * 1024 ** 2)
    if len({r.get('key') for r in roots}) != len(roots):
        raise Denied('CAPTURE_INVENTORY_DUPLICATE')
    for root in roots:
        subject = root.get('subject')
        receipt = root.get('checkpoint')
        if (root.get('state') != 'COMPLETE' or not isinstance(subject, dict)
                or not isinstance(receipt, dict)):
            raise Denied('CAPTURE_INVENTORY_UNRESOLVED')
        archive = receipt.get('durable_archive')
        outcome = root.get('outcome')
        source_sha = receipt.get('source_sha256')
        # A COMPLETE status and a claimed archive readback are not sufficient:
        # tie the stored root's terminal outcome, retained receipt and archive
        # to the SAME source digest. This does not independently fetch bytes or
        # establish portal completeness, which remain separate review gates.
        from re import fullmatch
        digest_bound = (
            isinstance(source_sha, str)
            and fullmatch('[a-f0-9]{64}', source_sha) is not None
            and isinstance(archive, dict)
            and archive.get('sha256') == source_sha
            and isinstance(outcome, dict)
            and outcome.get('outcome') == 'ENUMERATED_METADATA_RETAINED'
            and outcome.get('source_sha256') == source_sha
        )
        if (not digest_bound
                or receipt.get('kind') != 'LISTING_RECEIPT_V1'
                or receipt.get('council') != council
                or receipt.get('contract') != root.get('contract')
                or receipt.get('interval') != [subject.get('start'), subject.get('end')]
                or receipt.get('date_semantics') != subject.get('semantics')
                or receipt.get('accounting_complete') is not True
                or receipt.get('cleanup') != 'CLOSED'
                or not isinstance(archive, dict)
                or archive.get('readback_verified') is not True):
            raise Denied('CAPTURE_INVENTORY_UNVERIFIED')
    # DB membership alone does not prove independent historical/source coverage:
    # use these receipts for overlap/conflict checks, never as a coverage gate.
    return tuple(roots)




def shutdown_gap_sql_readback(connection, as_of):
    """Read-only, bounded per-council/window SQL checkpoint for PA-D004 v1.2.

    This checks persisted capture and saved screening *only*. It does not
    authenticate official-source enumeration, mark dates covered, determine
    qualification, count new changes, or establish buyer-facing facts. The
    caller owns its SQL connection/transaction; this function grants nothing.
    Every required council/window remains visible when no trusted SQL rows
    exist, including unqualified Trafford and historical UNKNOWN Bolton.
    """
    from datetime import date
    from app.ingestion.listing_screening import RULE_V3, ScreeningRule
    from app.ingestion.ledger import bounded
    from verification.discovery.campaign_manifest import shutdown_gap_source_packages
    plan = shutdown_gap_source_packages(as_of)
    rule = ScreeningRule(RULE_V3, unit_threshold=10, link_related=False)
    entries = []
    for council in plan['required_councils']:
        raw = connection.execute(
            "SELECT row_to_json(w) FROM public.ingestion_work_items AS w "
            "WHERE w.task='DISCOVERY' AND w.subject->>'council'=%s "
            "ORDER BY w.key LIMIT 129", (council,),
        ).fetchall()
        if len(raw) > 128:
            raise Denied('SHUTDOWN_SQL_READBACK_ROOT_BOUND')
        roots = [row[0] for row in raw]
        bounded(roots, 2 * 1024 ** 2)
        verified = ()
        if roots:
            try:
                verified = persisted_council_capture_inventory(connection, council)
            except Denied:
                pass  # preserve unknown/failed roots; never silently omit them
        for window in plan['windows']:
            start, end = window['start'], window['end']
            exact, other_overlap = [], False
            for root in roots:
                subject = root.get('subject')
                if not isinstance(subject, dict):
                    other_overlap = True
                    continue
                a, b = subject.get('start'), subject.get('end')
                try:
                    if (type(a) is not str or type(b) is not str or
                            date.fromisoformat(a).isoformat() != a or
                            date.fromisoformat(b).isoformat() != b or a > b):
                        raise ValueError('bad interval')
                except (TypeError, ValueError):
                    other_overlap = True
                    continue
                if a <= end and b >= start:
                    if (a, b) == (start, end):
                        exact.append(root)
                    else:
                        other_overlap = True
            entry = dict(council=council, start=start, end=end,
                         source_coverage='UNKNOWN', source_qualified=False,
                         retained_sql_records=None, screened_sql_records=None,
                         factual_qualifications=None, newly_added=None,
                         saved_key_facts=None, buyer_backlog=None)
            if other_overlap or len(exact) > 1:
                entry['state'] = 'OVERLAP_OR_CONFLICT_REQUIRES_REVIEW'
            elif not exact:
                entry['state'] = 'NO_EXACT_PERSISTED_SQL_CAPTURE'
            elif not verified or exact[0] not in verified:
                entry['state'] = 'SQL_CAPTURE_UNVERIFIED'
            else:
                root = exact[0]
                receipt = root['checkpoint']
                if (root['subject'].get('kind') != 'DISCOVERY_SCOPE' or
                        not isinstance(receipt.get('records'), list)):
                    entry['state'] = 'SQL_CAPTURE_UNVERIFIED'
                else:
                    entry['state'] = 'SQL_CAPTURE_SCREENING_UNVERIFIED'
                    entry['retained_sql_records'] = len(receipt['records'])
                    try:
                        binding = binding_for(council)
                        batches, screens = _screen_items(
                            binding, root, receipt, rule, root['limits'],
                            capture_bound=True)
                        expected = [*batches, *screens.values()]
                        if len(expected) > 72:
                            raise Denied('SHUTDOWN_SQL_SCREENING_BOUND')
                        keys = [r['key'] for r in expected]
                        saved = ([r[0] for r in connection.execute(
                            "SELECT row_to_json(w) FROM public.ingestion_work_items AS w "
                            "WHERE w.key = ANY(%s)", (keys,),
                        ).fetchall()] if keys else [])
                        bounded(saved, 2 * 1024 ** 2)
                        registration = Registration(
                            'SCREENING', '', [], [], {}, {}, root['key'],
                            batches=batches, screens=screens)
                        completed_screening(registration, receipt, rule, saved)
                        entry['state'] = 'SQL_CAPTURE_AND_SCREENING_READBACK'
                        entry['screened_sql_records'] = len(screens)
                    except (Denied, KeyError, TypeError, ValueError, IndexError):
                        # Unqualified source contracts and inconsistent saved
                        # children must never be counted as screened evidence.
                        pass
            entries.append(entry)
    if len(entries) != plan['total_date_scopes']:
        raise Denied('SHUTDOWN_SQL_READBACK_LEDGER_BOUND')
    return dict(as_of_london=plan['as_of_london'],
                fallback_is_verified_shutdown=False,
                required_date_scopes=plan['total_date_scopes'],
                entries=entries,
                sql_readback_scopes=sum(x['state']=='SQL_CAPTURE_AND_SCREENING_READBACK' for x in entries),
                sql_readback_screened_records=sum(x['screened_sql_records'] or 0 for x in entries),
                all_source_coverage_proven=False,
                qualification_or_application_admission_proven=False)


def prepare_admission_from_persisted_captures(connection, owner, binding, contract, root_key,
                                               rule, detail_targets, *, revision, item_limits,
                                               allow_test_evidence=False):
    """Owner-side read-only admission preparation from persisted SQL history.

    The caller may choose a stored root, but CANNOT hand-pick the history or
    omit conflicting captures. Fetch all complete, verified persisted roots of
    that council and the exact saved screening children before deriving
    nominees. No issuer/worker capability or factual write is provided.
    SQL membership does not authenticate source enumeration or archive bytes.
    """
    roots = persisted_council_capture_inventory(connection, binding.council)
    selected = [r for r in roots if r['key'] == root_key]
    if len(selected) != 1:
        raise Denied('PERSISTED_ADMISSION_ROOT_NOT_FOUND')
    root = selected[0]
    receipt = root['checkpoint']
    receipts = tuple(r['checkpoint'] for r in roots)
    nomination = derive_nominees(receipts, rule, allow_test_evidence=allow_test_evidence,
                                  capture_bound=True)
    nominees = tuple(n for n in nomination.nominees if n.capture_sha256 == digest(receipt))
    screening = screening_registration(owner, binding, contract, root, receipt, rule,
                                       revision=revision, item_limits=item_limits,
                                       _completed=True, allow_test_evidence=allow_test_evidence,
                                       capture_bound=True)
    required = [r['key'] for r in [*screening.batches, *screening.screens.values()]]
    if len(required) > 72:
        raise Denied('PERSISTED_ADMISSION_SCREENING_BOUND')
    # Protect a candidate from a mutable saved screening row between its
    # initial read and return. This is only an owner-side optimistic fence:
    # a future issuer must still revalidate under its own execution lock.
    from app.ingestion.ledger import bounded
    def read_screening_children():
        rows = ([row[0] for row in connection.execute(
            "SELECT row_to_json(w) FROM public.ingestion_work_items AS w WHERE w.key = ANY(%s)",
            (required,),
        ).fetchall()] if required else [])
        bounded(rows, 2 * 1024 ** 2)
        return sorted(rows, key=lambda row: row['key'])
    saved = read_screening_children()
    registration = admission_registration(
        owner, binding, contract, root, receipt, nominees, rule, detail_targets,
        revision=revision, item_limits=item_limits, screening_rows=saved,
        allow_test_evidence=allow_test_evidence, capture_bound=True,
        other_receipts=tuple(r['checkpoint'] for r in roots if r['key'] != root_key),
    )
    # Do not claim a single snapshot from a caller-owned connection which may
    # be autocommit/READ COMMITTED. An optimistic second independent read must
    # agree before a preparation candidate is returned; the eventual issuer
    # must still revalidate current durable state at its own execution fence.
    if persisted_council_capture_inventory(connection, binding.council) != roots:
        raise Denied('PERSISTED_ADMISSION_INVENTORY_CHANGED')
    if read_screening_children() != saved:
        raise Denied('PERSISTED_ADMISSION_SCREENING_CHANGED')
    return registration, nomination


def _capture_inputs(binding,contract,root,receipt,item_limits):
    scope = contract.scope()
    if (root.get('subject') != scope or root.get('task') != 'DISCOVERY' or root.get('contract') != contract.name or receipt.get('council') != binding.council
            or receipt.get('contract') != contract.name or receipt.get('interval') != [scope['start'], scope['end']] or receipt.get('date_semantics', 'RECEIVED') != scope['semantics']
            or root.get('checkpoint') != receipt):      # the receipt must BE the stored root's saved capture, for exactly this scope
        raise Denied('CHAIN_FOREIGN_CAPTURE')
    reconcile_items(binding, item_limits)
    check_capture(binding,contract,receipt)


def _screen_items(binding,root,receipt,rule,item_limits,*,capture_bound=False):
    plans = batch_plans(root['key'], receipt, rule,capture_bound=capture_bound)
    batches = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint'], limits=dict(item_limits)) for p in plans]
    screens = {}
    for record in receipt['records']:
        subject = dict(kind='APPLICATION', council=binding.council, reference=record['reference'])
        screen_revision=assessment_identity(record, rule)[3]
        if capture_bound:
            from app.ingestion.observation_screening import observation_revision
            screen_revision=observation_revision(screen_revision,digest(receipt))
        screens[record['reference']] = item(dict(subject=subject, task='SCREENING', contract=V3_CONTRACT, revision=screen_revision), dependencies=[root['key']], limits=dict(item_limits))
    return batches,screens


def screening_registration(owner,binding,contract,root,receipt,rule,*,revision,item_limits,_completed=False,allow_test_evidence=False,capture_bound=False):
    """Complete listing screening only: no factual rows, source calls or application writes."""
    _capture_inputs(binding,contract,root,receipt,item_limits)
    if receipt.get('evidence_label') and not allow_test_evidence:raise Denied('TEST_EVIDENCE_NOT_LIVE')
    batches,screens=_screen_items(binding,root,receipt,rule,item_limits,capture_bound=capture_bound)
    if not _completed and pending_grant_problems((owner.grant_expiry or owner.expiry).timestamp()-time.time(),phase='SCREENING',batches=len(batches),cumulative_screening=capture_bound):
        raise Denied('SCREENING_INSUFFICIENT_LIFETIME')
    rows=[root,*batches,*screens.values()]
    bindings,grant=owner.build_grant(rows,[],capture_key=root['key'],source_calls=0,capture_only=False,screening=rule)
    return Registration('SCREENING',authority_name(binding,'SCREENING',revision),rows,batches,grant,bindings,root['key'],batches=batches,screens=screens)


def completed_screening(registration,receipt,rule,rows):
    """Validate EVERY saved batch and assessment against the immutable capture and frozen rule."""
    from app.ingestion.listing_screening import assessment_identity
    expected=[*registration.batches,*registration.screens.values()]
    if not isinstance(rows,list) or len(rows)!=len(expected) or {r.get('key') for r in rows}!={r['key'] for r in expected}:
        raise Denied('STAGED_SCREENING_SET')
    by_key={r['key']:r for r in rows}
    for template in expected:
        row=by_key[template['key']]
        if row.get('state')!='COMPLETE' or any(row.get(k)!=template[k] for k in ('subject','task','contract','revision','dependencies')):
            raise Denied('STAGED_SCREENING_IDENTITY')
    for batch in registration.batches:
        plan=batch['checkpoint']['plan'];saved=by_key[batch['key']]['checkpoint'] or {}
        children=[registration.screens[r['reference']]['key'] for r in receipt['records'][plan['first']:plan['last']]]
        if by_key[batch['key']].get('outcome')!=dict(outcome='BATCH_SCREENED',children=children):raise Denied('STAGED_BATCH_OUTCOME')
        if (saved.get('kind')!='BATCH_PROGRESS_V1' or saved.get('plan')!=plan or saved.get('next')!=plan['last']
                or saved.get('children')!=children):raise Denied('STAGED_BATCH_CHECKPOINT')
    for record in receipt['records']:
        saved=by_key[registration.screens[record['reference']]['key']]['checkpoint'] or {}
        sha,config,config_sha,revision=assessment_identity(record,rule)
        if registration.batches and registration.batches[0]['checkpoint']['plan'].get('capture_bound') is True:
            from app.ingestion.observation_screening import observation_revision
            revision=observation_revision(revision,digest(receipt))
            if saved.get('capture_bound') is not True:raise Denied('STAGED_CAPTURE_BOUND_RECEIPT')
        from app.ingestion.listing_screening import routing_of
        if by_key[registration.screens[record['reference']]['key']].get('outcome')!=dict(outcome=routing_of(rule.screen(record))[1],retained=True):raise Denied('STAGED_ASSESSMENT_OUTCOME')
        if (any(saved.get(k)!=v for k,v in rule.screen(record).items()) or saved.get('record_sha256')!=sha
                or saved.get('config')!=config or saved.get('config_sha256')!=config_sha or saved.get('assessment_revision')!=revision
                or saved.get('capture_key')!=registration.root_key or saved.get('capture_checkpoint_sha256')!=digest(receipt)
                or saved.get('capture_sha256')!=receipt['source_sha256'] or saved.get('source_sha256')!=receipt['source_sha256']
                or saved.get('source_url')!=record['source_url'] or saved.get('source_record_id')!=record['source_record_id']):
            raise Denied('STAGED_ASSESSMENT_CHECKPOINT')
    return digest(sorted(rows,key=lambda r:r['key']))


def admission_registration(owner,binding,contract,root,receipt,nominees,rule,detail_targets,*,revision,item_limits,screening_rows,allow_test_evidence=False,capture_bound=False,other_receipts=()):
    screen=screening_registration(owner,binding,contract,root,receipt,rule,revision=revision,item_limits=item_limits,_completed=True,allow_test_evidence=allow_test_evidence,capture_bound=capture_bound)
    seal=completed_screening(screen,receipt,rule,screening_rows)
    reg=chain_registration(owner,binding,contract,root,receipt,nominees,rule,detail_targets,revision=revision,item_limits=item_limits,allow_test_evidence=allow_test_evidence,_pending_admission=True,capture_bound=capture_bound,other_receipts=other_receipts)
    reg.kind='ADMISSION';reg.authority=authority_name(binding,'ADMISSION',revision)
    reg.insert=list(reg.facts.values());reg.screening_sha256=seal
    return reg
