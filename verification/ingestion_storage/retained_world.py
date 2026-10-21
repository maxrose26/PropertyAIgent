"""The verified full retained Bolton capture (RECEIVED 2026-09-28 to 2026-10-04, 24 records) rebuilt OFFLINE from the pinned evidence files, and the owner-side check that the production ledger holds exactly that world before any
authority is issued (screening-v3 activation). Pure: no database, network or GitHub. The evidence files are byte-for-byte copies at their pinned hashes (tests/fixtures/retained_bolton_window, `-text` in .gitattributes).

Nothing in the evidence is reconstructed or edited: the capture checkpoint is regenerated from the archived source with the repository's own generating code and must reproduce the recorded digest exactly."""
import hashlib
import json
from datetime import date
from pathlib import Path

from app.ingestion.batching import batch_plans
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS, digest
from app.ingestion.listing_screening import RULE_V1, RULE_V3, ScreeningRule, assessment_identity, screening_plan_binding
from verification.discovery.idox_window import WindowConfig

EVIDENCE = Path(__file__).resolve().parents[2] / 'tests/fixtures/retained_bolton_window'
ARCHIVE_DIR = 'docs/design/ingestion-operational-execution-bolton-window-demonstration-20261023/'      # the path recorded INSIDE the archive receipt (an identifier)
PINS = {'capture/source.json': ('5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a', 20733),
        'capture-retained/retained.json': ('a47122d0bf386a83f423d0f41d0fb2984a4f3eb8d2cf7cf0aeff74016d7ec2ee', 574),
        'screening-authority/registered.json': ('458c50efd3c55e2ef10193f4449e85ddcb84e2b7eda397eb9bb872fdeedb7c5d', 630),
        'completed/final-result.json': ('d38db9b67dbc8715e9257d040d7dff19c2b759ca6b25393169388d310437ab9e', 15845),
        'completed/events.jsonl': ('26d6392b5f91ce49baa11f45f49dd36371a7e0cdefa837cfadb3aa5b23de2dd0', 44650)}
CAPTURE_CHECKPOINT = 'd5fa9e29bdd51afbf36772e9b08880af6811a8cec771a3335bad0095801445ee'
CAPTURE_KEY = 'd1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545'
BINDINGS = 'ad4e598267d2104a6d2e0d2321087d84ac6313270f58a2411b3100e66762445f'
CON = 'bolton-received-idox-coordinator-v1'
MANIFEST = '8fb79d78db499a4f5f622ae20debba6397451f242ae0028514246d3234358e0c'
SCOPE = dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-09-28', end='2026-10-04', semantics='RECEIVED')
ROOT_LIMITS = dict(DEFAULT_LIMITS, requests=10, bytes=3000000, rows=60, pages=6)


class WorldMismatch(ValueError):
    """A fixed reason code (never row content)."""


def item(identity, *, dependencies=(), checkpoint=None, limits=None, max_attempts=2):      # == verification.ingestion_storage.operational_owner.item
    return dict(identity, key=digest(identity), dependencies=list(dependencies), priority=50, eligible_at=0, state='QUEUED', reason=None, next_action='CLAIM_WHEN_AUTHORISED',
                limits=limits or DEFAULT_LIMITS, authority=None, attempt_count=0, max_attempts=max_attempts, fence=0, owner=None, lease_until=None, phase='IDLE', checkpoint=checkpoint, outcome=None)


def verify_evidence_files():
    """Every evidence file is byte-for-byte at its pinned hash and size, or the run does not start."""
    for name, (sha, size) in PINS.items():
        raw = (EVIDENCE / name).read_bytes()
        if (hashlib.sha256(raw).hexdigest(), len(raw)) != (sha, size):
            raise WorldMismatch('EVIDENCE_FILE_NOT_AT_PINNED_HASH')


def retained():
    """(source, receipt) rebuilt exactly as the production run built them; the receipt digest must equal the recorded capture checkpoint digest."""
    verify_evidence_files()
    raw = (EVIDENCE / 'capture/source.json').read_bytes()
    source = json.loads(raw)
    events = [json.loads(line) for line in (EVIDENCE / 'completed/events.jsonl').read_bytes().decode('utf-8').splitlines() if line.strip()]
    outer = next(e for e in events if e['event'] == 'source_supervisor_observed')['payload']['actual']
    contract = IdoxListingContract(CON, WindowConfig('bolton', 'RECEIVED', date(2026, 9, 28), date(2026, 10, 4), 0), '1833eb7349dda9b1dceb0924abd7380b2f24e591e13ad34ec37dd8e4763df3f2')
    receipt = contract.project(source, outer, ROOT_LIMITS, source_bytes_limit=512 * 1024)
    receipt.pop('window')
    receipt['durable_archive'] = dict(commit='3587e2778720f56a9510b33c7bbce7584f6be59d', path=ARCHIVE_DIR + 'capture/source.json', sha256=digest(source), bytes=len(raw), readback_verified=True)
    if digest(receipt) != CAPTURE_CHECKPOINT:
        raise WorldMismatch('CAPTURE_CHECKPOINT_NOT_REPRODUCED')
    return source, receipt


def identities(receipt):
    """(root, v1 children, v1 plans, v1 batches, bindings) of the registered v1 screening, exactly as the owner registered them."""
    root = item(dict(subject=SCOPE, task='DISCOVERY', contract=CON, revision=MANIFEST), max_attempts=1, limits=ROOT_LIMITS)
    children = [item(dict(subject=dict(kind='APPLICATION', council='bolton', reference=r['reference']), task='SCREENING', contract='listing-screen-v1', revision=digest(r)), dependencies=[root['key']]) for r in receipt['records']]
    plans = batch_plans(root['key'], receipt)
    batches = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint']) for p in plans]
    bindings = {x['key']: {k: x[k] for k in ('subject', 'task', 'contract', 'revision')} for x in [*batches, item(dict(subject=SCOPE, task='DISCOVERY', contract=CON, revision=MANIFEST)), *children]}
    if root['key'] != CAPTURE_KEY or digest(bindings) != BINDINGS or len(bindings) != 30:
        raise WorldMismatch('REGISTERED_IDENTITIES_NOT_REPRODUCED')
    return root, children, plans, batches, bindings


def v3_items(receipt, rule):
    """The 29 new items the screening-only allowance would create or register: five v3 batch items and 24 v3 children."""
    plans = batch_plans(CAPTURE_KEY, receipt, rule)
    batches = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint']) for p in plans]
    children = [item(dict(subject=dict(kind='APPLICATION', council='bolton', reference=r['reference']), task='SCREENING', contract='listing-screen-v3', revision=assessment_identity(r, rule)[3]), dependencies=[CAPTURE_KEY]) for r in receipt['records']]
    return plans, batches, children


def verify_world(rows, receipt=None):
    """`rows` is {key: (state, checkpoint)} as the owner reads them (absent keys map to (None, None)). Requires: the capture COMPLETE with exactly the pinned checkpoint; the 24 earlier assessments COMPLETE and equal to
    the v1 screening of the pinned records; the 5 earlier batches COMPLETE with the registered plans; and NO v3 row of any kind. Raises WorldMismatch with a fixed reason; returns the 30 retained keys."""
    receipt = receipt or retained()[1]
    root, children, plans, batches, _ = identities(receipt)
    state, checkpoint = rows.get(CAPTURE_KEY, (None, None))
    if state is None or checkpoint is None:
        raise WorldMismatch('RETAINED_ROW_MISSING')
    if state != 'COMPLETE' or digest(checkpoint) != CAPTURE_CHECKPOINT:
        raise WorldMismatch('RETAINED_CAPTURE_ALTERED')
    v1 = ScreeningRule(RULE_V1)
    for child, record in zip(children, receipt['records']):
        state, checkpoint = rows.get(child['key'], (None, None))
        if state is None or checkpoint is None:
            raise WorldMismatch('RETAINED_ROW_MISSING')
        expected = v1.screen(record)
        if state != 'COMPLETE' or not isinstance(checkpoint, dict) or any(checkpoint.get(k) != v for k, v in expected.items()):
            raise WorldMismatch('RETAINED_ASSESSMENT_ALTERED')
    for batch in batches:
        state, checkpoint = rows.get(batch['key'], (None, None))
        if state is None or checkpoint is None:
            raise WorldMismatch('RETAINED_ROW_MISSING')
        if state != 'COMPLETE' or not isinstance(checkpoint, dict) or checkpoint.get('plan') != batch['checkpoint']['plan']:
            raise WorldMismatch('RETAINED_BATCH_ALTERED')
    return [CAPTURE_KEY, *[c['key'] for c in children], *[b['key'] for b in batches]]


def verify_no_v3_rows(rows, receipt, rule):
    """The 29 new keys must not exist yet (a run is made once; a partial earlier attempt is reconciled by a human, never silently resumed)."""
    _, batches, children = v3_items(receipt, rule)
    present = [x['key'] for x in (*batches, *children) if rows.get(x['key'], (None, None))[0] is not None]
    if present:
        raise WorldMismatch('V3_ROWS_ALREADY_PRESENT')
    return [x['key'] for x in (*batches, *children)]
