"""Integrated end-to-end proof through restricted disposable PostgreSQL roles, for both families (Idox: Tameside; Arcus: Manchester).

non-empty local listing -> validated retained audit -> durable archive with verified readback -> batching and frozen v3 screening -> deterministic exact nominee
-> fresh local detail verification -> existing shared identity admission and B2 -> committed database readback.

Local fixtures, an isolated test publisher and a disposable database only: no council, no GitHub, no production database. Every archive and receipt here is labelled a test
artefact. Synthetic contract tests qualify no real council markup, and a source-only fixture success is never admission proof: each chain case below ends at a committed readback.
The processing path is the production one, reached through ControllerLedger on the three restricted logins; only the owner's registration (work items and grants) is a fixture.
"""
import json
import subprocess
import time
import sys
import os
from dataclasses import asdict, replace

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.models import Application
from app.ingestion.ledger import Denied, UncertainPersistence, digest
from app.ingestion.nomination import Nominee, derive_nominees
from tests.e2e_chain_caller import FAMILY_COUNCIL, ROLES, Chain, application, changed_tables, restricted_sessions, snapshot
from tests.e2e_connection_support import ASSESS, EXTENSION, LABEL, NO_COUNT, SCHEME, entry, outer
from tests.e2e_pg_world import disposable_world

FAMILIES = ['idox', 'arcus']
EXPECTED = {'E2E/1/26': 'ADMIT_SCHEME', 'E2E/2/26': 'ADMIT_FOR_ASSESSMENT', 'E2E/3/26': 'ROUTE_COUNT_UNCONFIRMED', 'E2E/4/26': 'RETAIN_NOT_RESIDENTIAL_SUPPLY',
            'E2E/5/26': 'RETAIN_BELOW_THRESHOLD', 'E2E/6/26': 'RETAIN_RELATED_TO_PARENT'}
# What the accepted shared B2 path is observed to write, per verification scope (derived by running it, then frozen here): the application row, and for the COUPLED scope its
# lifecycle event. Nothing else may change; the forbidden tables are named so a future change cannot widen the write set silently.
WRITES = {'idox': {'applications', 'application_lifecycle_events'}, 'arcus': {'applications'}}
FORBIDDEN = ['sites', 'documents', 'scheme_intelligence', 'companies', 'application_companies', 'contacts', 'visual_evidence', 'buyers', 'buyer_mandates', 'buyer_profiles',
             'opportunity_monitoring_states', 'current_buyer_opportunity_states', 'acquisition_subject_anchors', 'applicant_intelligences']
# The exact production binding that refuses each forgery (the capture-digest check keeps its historical Idox-era name).
REFUSED_BY = {'capture': 'V3_COMPLETE_IDOX_CAPTURE_REQUIRED', 'screening': 'V3_ASSESSMENT_BINDING', 'nominee': 'V3_NOMINATED_RECORD_BINDING', 'factual': 'V3_FACTUAL_TASK_BINDING'}
UNCERTAIN = ['after_admission', 'interrupt_after_commit', 'b2_readback_failure', 'committed_readback_failure', 'ledger_lost_ack']


@pytest.fixture(scope='module')
def world():
    yield from disposable_world()


def staged(world, tmp_path, family, tag, entries=None, **kw):
    """Owner stand-in registration, then the production capture, derivation and screening: everything short of admission."""
    chain = Chain(world, tmp_path, family, tag, entries, **kw).owner_reset().owner_registers_capture()
    chain.capture()
    chain.read_capture()
    nominees = chain.nominees()
    chain.owner_registers_chain(nominees.nominees)
    chain.screen()
    return chain, nominees


def assert_closed(world, chain):
    """Positive connection closure: every stage's accounting reports CLOSED and no restricted session survives."""
    stages = [chain.accounting['capture'], *chain.accounting.get('screening', []), *chain.accounting.get('admission', [])]
    assert all(s['cleanup'] == 'CLOSED' and s['connections_closed'] is True and s['failed_native_connections_closed'] is True and s['socket_closure'] == 'NO_NEW_OWNED_SOCKETS'
               and s['connections_opened'] == s['connections_closed_count'] and s['driver_statements'] <= 120 and s['connection_attempts'] <= 16 for s in stages), stages
    deadline = time.monotonic() + 5      # the client has closed; the server reaps the backend asynchronously, so confirm it positively within a short bound
    while restricted_sessions(world['boot']) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert restricted_sessions(world['boot']) == 0


def assert_confined(world, family, before, admitted, preexisting=()):
    after = snapshot(world['boot'])
    changed = set(changed_tables(before, after))
    assert changed <= WRITES[family], changed
    assert not changed & set(FORBIDDEN)
    for name in FORBIDDEN:
        assert before[name] == after[name], name
    boot = world['boot']
    assert boot.execute('SELECT count(*) FROM sites').fetchone()[0] == 0
    assert boot.execute("SELECT count(*) FROM applications WHERE NOT (reference = ANY(%s)) AND (site_id IS NOT NULL OR estimated_unit_count IS NOT NULL "
                        "OR opportunity_classification IS NOT NULL OR proposal IS NOT NULL OR address IS NOT NULL OR application_type IS NOT NULL "
                        "OR unit_confirmation_status IS DISTINCT FROM 'discovery_pending')", (list(preexisting),)).fetchone()[0] == 0
    if admitted:
        assert changed == {'applications'} | ({'application_lifecycle_events'} if family == 'idox' else set())
    else:
        assert changed == set() or changed <= WRITES[family]


def unexpected(exc):
    assert not isinstance(exc, (AssertionError, TypeError, KeyError, AttributeError)), type(exc).__name__


# ----------------------------------------------------------------------------------------------------------------------- the chain
@pytest.mark.parametrize('family', FAMILIES)
def test_chain_eligible_scheme_and_assessment_reach_committed_readback(world, tmp_path, family, record_property):
    boot = world['boot']
    chain, nominees = staged(world, tmp_path, family, 'chain-' + family)
    receipt = chain.capture_receipt
    # collection -> retained audit -> durable archive with verified readback; no listing request; test artefacts labelled
    assert receipt['kind'] == 'LISTING_RECEIPT_V1' and receipt['evidence_label'] == LABEL and receipt['durable_archive']['label'] == LABEL
    assert receipt['durable_archive']['readback_verified'] is True and receipt['durable_archive']['sha256'] == receipt['source_sha256'] == digest(chain.audit)
    assert chain.listing_requests == [] and len(chain.publisher.calls) == 1
    root = boot.execute('SELECT state, phase, outcome FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()
    assert root[0] == 'COMPLETE' and root[2]['outcome'] == 'ENUMERATED_METADATA_RETAINED'
    # frozen v3 screening stored by the restricted worker: exactly the frozen outcome table
    assert {ref: chain.screening_outcome(ref) for ref in EXPECTED} == EXPECTED
    assert [(n.reference, n.outcome) for n in nominees.nominees] == [('E2E/1/26', 'ADMIT_SCHEME'), ('E2E/2/26', 'ADMIT_FOR_ASSESSMENT')]
    before = snapshot(boot)
    results = {}
    for nominee in nominees.nominees:
        adm = chain.prepare(nominee)
        results[nominee.reference] = chain.admit(adm)
        assert len(adm.detail_calls) == 1      # one fresh local detail verification per nominee, none for anyone else
    council = FAMILY_COUNCIL[family]
    for reference in ('E2E/1/26', 'E2E/2/26'):
        row = application(boot, council, reference)
        r = results[reference]
        assert r['outcome'] == 'SUPPORTED_FACTS_VERIFIED' and r['admission'] == 'COMMITTED_PENDING_IDENTITY' and r['factual']['unit_facts'] == 'NOT_WRITTEN'
        assert r['factual']['readback']['application_id'] == row['id'] and r['factual']['cleanup'] == 'CLOSED' and r['factual']['accounting_complete'] is True
        assert row['unit_confirmation_status'] == 'discovery_pending' and row['status'] is not None
        if family == 'idox':
            assert r['b2'] == 'COUPLED' and row['decision'] == 'Approve' and row['status_verified_at'] is not None
        else:
            assert r['b2'] == 'INITIAL_STATUS_ONLY' and row['status'] == 'Under Consideration' and row['decision'] is None and row['status_verified_at'] is None
            assert json.loads(row['planning_field_verification'])['status']['literal'] == 'Under Consideration'
    for reference in ('E2E/3/26', 'E2E/4/26', 'E2E/5/26', 'E2E/6/26'):
        assert application(boot, council, reference) is None      # retained evidence only: no identity, no detail call
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 2
    assert_confined(world, family, before, admitted=True)
    assert chain.listing_requests == []
    assert_closed(world, chain)
    record_property('server_version', world['server_version'])


@pytest.mark.parametrize('family', FAMILIES)
def test_assessment_with_unknown_address_and_type_is_still_admitted(world, tmp_path, family):
    """ADMIT_FOR_ASSESSMENT is a frozen identity-eligible outcome; unknown address and type do not gate routing, and the fresh detail verification still decides the effect."""
    chain, nominees = staged(world, tmp_path, family, 'assess-' + family, [entry('E2E/1/26', ASSESS, address=None if family == 'arcus' else '')])
    assert [(n.reference, n.outcome) for n in nominees.nominees] == [('E2E/1/26', 'ADMIT_FOR_ASSESSMENT')]
    r = chain.admit(chain.prepare(nominees.nominees[0]))
    assert r['outcome'] == 'SUPPORTED_FACTS_VERIFIED' and application(world['boot'], FAMILY_COUNCIL[family], 'E2E/1/26')['proposal'] is None      # proposal text is never written
    assert_closed(world, chain)


# ------------------------------------------------------------------------------------------------------- unusable metadata
UNUSABLE = {
    'idox': [entry('E2E/1/26', ''), entry('E2E/2/26', NO_COUNT), entry('E2E/3/26', EXTENSION, address='')],
    'arcus': [entry('E2E/1/26', None), dict(entry('E2E/2/26', SCHEME), both_labels=True), entry('E2E/3/26', 'x' * 9000), entry('E2E/4/26', NO_COUNT)],
}
UNUSABLE_OUTCOMES = {
    'idox': {'E2E/1/26': 'RETAIN_UNUSABLE_PROPOSAL', 'E2E/2/26': 'ROUTE_COUNT_UNCONFIRMED', 'E2E/3/26': 'RETAIN_NOT_RESIDENTIAL_SUPPLY'},
    'arcus': {'E2E/1/26': 'RETAIN_UNUSABLE_PROPOSAL', 'E2E/2/26': 'RETAIN_UNUSABLE_PROPOSAL', 'E2E/3/26': 'RETAIN_UNUSABLE_PROPOSAL', 'E2E/4/26': 'ROUTE_COUNT_UNCONFIRMED'},
}


@pytest.mark.parametrize('family', FAMILIES)
def test_unusable_metadata_follows_the_frozen_table_and_writes_nothing(world, tmp_path, family):
    boot = world['boot']
    chain = Chain(world, tmp_path, family, 'unusable-' + family, UNUSABLE[family]).owner_reset().owner_registers_capture()
    chain.capture(), chain.read_capture()
    nominees = chain.nominees()
    assert nominees.nominees == ()
    # A forged nomination of an unusable record is refused by the owner's own preparation, before any row or authority exists.
    record = chain.capture_receipt['records'][0]
    forged = Nominee(chain.council, record['reference'], record['source_url'], record['source_record_id'], digest(record), '0' * 64, digest(chain.capture_receipt), 'ADMIT_SCHEME')
    with pytest.raises(Denied, match='CHAIN_NOMINEES_NOT_DERIVED'):
        chain.owner_registers_chain([forged])
    chain.owner_registers_chain([])
    chain.screen()
    before = snapshot(boot)
    assert {ref: chain.screening_outcome(ref) for ref in UNUSABLE_OUTCOMES[family]} == UNUSABLE_OUTCOMES[family]
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    assert_confined(world, family, before, admitted=False)
    assert_closed(world, chain)


# --------------------------------------------------------------------------------------------------------------- known identity
@pytest.mark.parametrize('family', FAMILIES)
def test_known_identity_is_preserved_and_never_refetched(world, tmp_path, family):
    boot = world['boot']
    chain, nominees = staged(world, tmp_path, family, 'known-' + family)
    council = FAMILY_COUNCIL[family]
    with Session(world['app']) as s:
        s.add(Application(council_code=council, reference='E2E/1/26', status='PRESERVED'))
        s.commit()
    before = snapshot(boot)
    known, fresh = [chain.prepare(n) for n in nominees.nominees]
    r = chain.admit(known)
    assert r['outcome'] == 'DISCOVERY_SCREENING_ONLY_ALREADY_KNOWN' and known.detail_calls == []
    assert application(boot, council, 'E2E/1/26')['status'] == 'PRESERVED'
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 1
    assert chain.admit(fresh)['outcome'] == 'SUPPORTED_FACTS_VERIFIED' and boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 2
    assert application(boot, council, 'E2E/1/26')['status'] == 'PRESERVED'      # the known identity was never touched
    assert_confined(world, family, before, admitted=True, preexisting=('E2E/1/26',))
    assert_closed(world, chain)


# ----------------------------------------------------------------------------------------------------------- competing delivery
@pytest.mark.parametrize('family', FAMILIES)
def test_competing_delivery_wins_and_is_preserved(world, tmp_path, family, monkeypatch):
    """A second delivery (a separate supervised process using the real restricted writer) wins between the wrapper's precheck and shared admission."""
    boot = world['boot']
    chain, nominees = staged(world, tmp_path, family, 'race-' + family)
    adm = chain.prepare(nominees.nominees[0])
    import app.pipeline.discovery_admission as admission
    real = admission.admit_identity
    winners = []
    def race(engine, envelope, **kwargs):
        engine.dispose()      # the reviewed login limit is one connection
        child = subprocess.run([sys.executable, '-m', 'tests.v3_admission_supervised', 'race'], input=json.dumps(asdict(envelope), default=str), text=True, capture_output=True, timeout=20,
                               env=dict(PATH='/usr/bin:/bin', HOME=os.environ['HOME'], DATABASE_URL='sqlite:///:memory:', V3_DISPOSABLE_WRITER_URL=world['urls']['ingestion_application_login']))
        assert child.returncode == 0, child.stderr[-400:]
        winners.append(json.loads(child.stdout))
        return real(engine, envelope, **kwargs)
    monkeypatch.setattr(admission, 'admit_identity', race)
    r = chain.admit(adm)
    assert winners and winners[0]['outcome'] == 'CREATED_PENDING' and winners[0]['costs']['cleanup'] == 'CLOSED'
    assert r['admission'] == 'EXISTING_IDENTITY_PRESERVED' and boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 1
    assert application(boot, FAMILY_COUNCIL[family], 'E2E/1/26')['status'] is None      # the winner's bare identity: our delivery wrote no facts over it
    assert_closed(world, chain)


# ----------------------------------------------------------------------------------------------------- conflicting observations
@pytest.mark.parametrize('family', FAMILIES)
def test_conflicting_observations_are_withheld_and_never_admitted(world, tmp_path, family):
    boot = world['boot']
    a = Chain(world, tmp_path, family, 'conflict-a-' + family, [entry('E2E/1/26', SCHEME), entry('E2E/2/26', ASSESS)]).owner_reset().owner_registers_capture()
    a.capture(), a.read_capture()
    b = Chain(world, tmp_path, family, 'conflict-b-' + family, [entry('E2E/1/26', ASSESS), entry('E2E/2/26', ASSESS)]).owner_registers_capture()      # same reference, different content
    b.capture(), b.read_capture()
    both = derive_nominees([a.capture_receipt, b.capture_receipt], a.rule, allow_test_evidence=True)
    assert [c['reference'] for c in both.conflicts] == ['E2E/1/26'] and len(both.conflicts[0]['observations']) == 2
    assert [n.reference for n in both.nominees] == ['E2E/2/26']      # the identical observation still nominates, bound to one capture
    owner = a if both.nominees[0].capture_sha256 == digest(a.capture_receipt) else b
    other = b if owner is a else a
    owner.owner_registers_chain(both.nominees, others=[other.capture_receipt])
    owner.screen()
    before = snapshot(boot)
    r = owner.admit(owner.prepare(both.nominees[0]))
    assert r['outcome'] == 'SUPPORTED_FACTS_VERIFIED'
    assert application(boot, FAMILY_COUNCIL[family], 'E2E/1/26') is None      # the conflicting reference is withheld from both captures
    assert application(boot, FAMILY_COUNCIL[family], 'E2E/2/26') is not None
    assert_confined(world, family, before, admitted=True)


# ------------------------------------------------------------------------------------------------------- tampered provenance
@pytest.mark.parametrize('family', FAMILIES)
def test_tampered_audit_hash_is_refused_before_any_checkpoint(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'tamper-in-' + family).owner_reset().owner_registers_capture()
    with pytest.raises(Denied, match='RETAINED_AUDIT_BINDING'):
        chain.capture(expected='0' * 64)
    row = world['boot'].execute('SELECT state, checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()
    assert row[1] is None and row[0] != 'COMPLETE' and chain.publisher.calls == []
    assert_closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('forgery', ['capture', 'screening', 'nominee', 'factual'])
def test_tampering_after_capture_is_refused_by_the_production_bindings(world, tmp_path, family, forgery):
    boot = world['boot']
    chain, nominees = staged(world, tmp_path, family, f'tamper-{forgery}-{family}')
    nominee = nominees.nominees[0]
    before = snapshot(boot)
    if forgery == 'capture':      # the stored capture no longer matches the digest the nomination was sealed against
        chain.tamper(chain.root['key'], ['records', '0', 'fields', 'proposal', 'value'], 'Erection of 99 residential dwellings')
    adm = chain.prepare(nominee)
    if forgery == 'screening':      # a forged routing outcome in the stored screening result
        chain.tamper(chain.screens[nominee.reference]['key'], ['count_assessment', 'admission'], 'RETAIN_BELOW_THRESHOLD')
    if forgery == 'nominee':
        adm.binding = replace(adm.binding, nominee=replace(adm.binding.nominee, listing_revision='0' * 64))
    if forgery == 'factual':
        adm.binding = replace(adm.binding, factual_contract_sha256='0' * 64)
    with pytest.raises((Denied, DBAPIError)) as exc:
        chain.admit(adm)
    assert isinstance(exc.value, Denied) and str(exc.value) == REFUSED_BY[forgery], (forgery, repr(exc.value))      # the specific production binding, not just any refusal
    unexpected(exc.value)
    assert adm.detail_calls == [] and boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    assert_confined(world, family, before, admitted=False)
    assert_closed(world, chain)


# ------------------------------------------------------------------------------------------------ archive and readback failure
@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('mode', ['corrupt_write', 'wrong_sha', 'wrong_bytes', 'raises'])
def test_archive_or_readback_failure_leaves_no_checkpoint_and_no_children(world, tmp_path, family, mode):
    chain = Chain(world, tmp_path, family, f'archive-{mode}-{family}', publisher_mode=mode).owner_reset().owner_registers_capture()
    with pytest.raises((Denied, OSError)) as exc:
        chain.capture()
    unexpected(exc.value)
    row = world['boot'].execute('SELECT state, phase, checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()
    assert row[2] is None and row[0] != 'COMPLETE'
    assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE key<>repeat('0',64)").fetchone()[0] == 1
    assert_closed(world, chain)


# ---------------------------------------------------------------------------------------------------------------- uncertain commits
@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('case', UNCERTAIN)
def test_uncertain_commits_stop_every_following_write(world, tmp_path, family, case, monkeypatch):
    boot = world['boot']
    chain, nominees = staged(world, tmp_path, family, f'uncertain-{case}-{family}')
    first, second = [chain.prepare(n) for n in nominees.nominees]
    co = first.co
    if case in {'after_admission', 'interrupt_after_commit'}:
        import app.pipeline.discovery_admission as admission
        real = admission.admit_identity
        def after(*args, **kwargs):
            real(*args, **kwargs)
            raise KeyboardInterrupt('disposable committed identity') if case == 'interrupt_after_commit' else RuntimeError('disposable committed identity')
        monkeypatch.setattr(admission, 'admit_identity', after)
    if case == 'b2_readback_failure':
        def reject_after_b2(connection, cursor, statement, parameters, context, many):
            if statement.lstrip().startswith('UPDATE applications'):
                raise RuntimeError('disposable B2 failure')
        event.listen(co.ledger.engine, 'after_cursor_execute', reject_after_b2)
    if case == 'committed_readback_failure':
        committed = []
        real_commit, real_scalar = Session.commit, Session.scalar
        def commit(session):
            result = real_commit(session)
            if session.bind is co.ledger.engine and session.execute(text('SELECT 1 FROM applications WHERE status IS NOT NULL')).first():      # the B2 facts are now committed
                committed.append(True)
            return result
        def scalar(session, *args, **kwargs):
            if session.bind is co.ledger.engine and committed:
                raise RuntimeError('disposable readback after acknowledged B2 commit')
            return real_scalar(session, *args, **kwargs)
        monkeypatch.setattr(Session, 'commit', commit)
        monkeypatch.setattr(Session, 'scalar', scalar)
    if case == 'ledger_lost_ack':
        real_step = co.ledger._step
        def lost(op, *args, **kwargs):
            result = real_step(op, *args, **kwargs)
            if op == 'resolve_effect' and co.ledger.get(first.fact['key'])['phase'] == 'WRITE_INTENT':
                raise RuntimeError('disposable ledger acknowledgement loss')
            return result
        monkeypatch.setattr(co.ledger, '_step', lost)
    expected = KeyboardInterrupt if case == 'interrupt_after_commit' else UncertainPersistence
    with pytest.raises(expected) as exc:
        chain.admit(first)
    unexpected(exc.value)
    monkeypatch.undo()
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 1      # the identity is committed; its state is uncertain, so nothing may follow
    assert boot.execute('SELECT phase FROM ingestion_work_items WHERE key=%s', (first.fact['key'],)).fetchone()[0] == 'WRITE_INTENT'
    with pytest.raises(Exception):
        chain.probe_claim(first.fact['key'])      # the uncertain item itself can never be claimed again
    with pytest.raises(Exception) as following:      # the second, separately authorised nominee is stopped by the barrier
        chain.admit(second)
    unexpected(following.value)
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 1
    assert boot.execute('SELECT count(*) FROM sites').fetchone()[0] == 0
    assert_closed(world, chain)


# --------------------------------------------------------------------------------------------------------------------- authority
@pytest.mark.parametrize('family', FAMILIES)
def test_expired_capture_grant_stops_before_anything_is_stored(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'expired-capture-' + family).owner_reset().owner_registers_capture(ttl=-5)
    with pytest.raises(DBAPIError):
        chain.capture()
    assert world['boot'].execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()[0] is None and chain.publisher.calls == []
    assert_closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_expired_chain_grant_stops_screening_and_admission(world, tmp_path, family):
    boot = world['boot']
    chain, nominees = staged(world, tmp_path, family, 'expired-chain-' + family)
    adm = chain.prepare(nominees.nominees[0])
    chain.owner_expires(chain.auth_chain)
    with pytest.raises(DBAPIError):
        chain.admit(adm)
    assert adm.detail_calls == [] and boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    assert_closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('limit', ['writes', 'source_calls'])
def test_insufficient_authority_for_the_effect_is_refused(world, tmp_path, family, limit):
    """Authority is counted per effect: one identity transaction plus one B2 transaction needs writes=2, and the fresh detail read needs a source call."""
    boot = world['boot']
    chain = Chain(world, tmp_path, family, f'insufficient-{limit}-{family}').owner_reset().owner_registers_capture()
    chain.capture(), chain.read_capture()
    nominees = chain.nominees()
    chain.owner_registers_chain(nominees.nominees, **({'writes': 1} if limit == 'writes' else {'source_calls': 0}))
    chain.screen()
    adm = chain.prepare(nominees.nominees[0])
    with pytest.raises((DBAPIError, Denied, UncertainPersistence)) as exc:
        chain.admit(adm)
    unexpected(exc.value)
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    assert (adm.detail_calls == []) if limit == 'source_calls' else len(adm.detail_calls) == 1
    assert_closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('misuse', ['capture_only', 'no_completion_outcome'])
def test_a_grant_not_shaped_for_retained_capture_cannot_complete_it(world, tmp_path, family, misuse):
    chain = Chain(world, tmp_path, family, f'grant-{misuse}-{family}').owner_reset()
    chain.owner_registers_capture(**({'capture_only': True} if misuse == 'capture_only' else {'outcomes': ()}))
    with pytest.raises(DBAPIError):
        chain.capture()
    state, phase, checkpoint = world['boot'].execute('SELECT state, phase, checkpoint IS NOT NULL FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()
    assert state != 'COMPLETE'      # never completed, so nothing downstream can batch it
    assert_closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_a_set_global_stop_is_never_bypassed_at_capture(world, tmp_path, family):
    chain = Chain(world, tmp_path, family, 'stop-capture-' + family).owner_reset().owner_registers_capture(stop={'reason': 'DISPOSABLE_TEST_STOP'})
    with pytest.raises(DBAPIError, match='GLOBAL_STOP'):
        chain.capture()
    assert world['boot'].execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (chain.root['key'],)).fetchone()[0] is None and chain.publisher.calls == []
    assert world['boot'].execute("SELECT outcome->'global_stop' FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0] == {'reason': 'DISPOSABLE_TEST_STOP'}      # still set: nothing here clears one
    assert_closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_a_stop_set_after_capture_blocks_screening(world, tmp_path, family):
    boot = world['boot']
    chain = Chain(world, tmp_path, family, 'stop-screen-' + family).owner_reset().owner_registers_capture()
    chain.capture(), chain.read_capture()
    nominees = chain.nominees()
    chain.owner_registers_chain(nominees.nominees)
    chain.owner_sets_stop()
    with pytest.raises(DBAPIError, match='GLOBAL_STOP'):
        chain.screen()
    with pytest.raises((Denied, DBAPIError)):      # screening never completed, so admission cannot even be prepared
        chain.admit(chain.prepare(nominees.nominees[0]))
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    assert_closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_a_stop_set_after_screening_blocks_admission_before_the_detail_call(world, tmp_path, family):
    boot = world['boot']
    chain, nominees = staged(world, tmp_path, family, 'stop-admit-' + family)
    adm = chain.prepare(nominees.nominees[0])
    chain.owner_sets_stop()
    with pytest.raises(DBAPIError, match='GLOBAL_STOP'):
        chain.admit(adm)
    assert adm.detail_calls == [] and boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    assert_closed(world, chain)


# --------------------------------------------------------------------------------------------------- cancellation and closure
@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('how', ['stop_file', 'interrupt'])
def test_cancellation_before_effects_writes_nothing_and_closes_cleanly(world, tmp_path, family, how):
    boot = world['boot']
    stop = tmp_path / 'manual-stop'
    chain, nominees = staged(world, tmp_path, family, f'cancel-{how}-{family}', stop_file=stop if how == 'stop_file' else None)
    adm = chain.prepare(nominees.nominees[0])
    real = adm.detail
    def cancelling(row):
        if how == 'interrupt':
            raise KeyboardInterrupt('disposable cancellation before effects')
        stop.write_text('stop')      # the operator's manual stop appears while the detail read is in flight
        return real(row)
    adm.detail = cancelling
    with pytest.raises((KeyboardInterrupt, Denied, UncertainPersistence)) as exc:
        chain.admit(adm)
    unexpected(exc.value)
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    assert boot.execute('SELECT state FROM ingestion_work_items WHERE key=%s', (adm.fact['key'],)).fetchone()[0] != 'COMPLETE'
    assert_closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_accounting_is_complete_and_bounded_for_the_whole_chain(world, tmp_path, family):
    chain, nominees = staged(world, tmp_path, family, 'accounting-' + family)
    for n in nominees.nominees:
        chain.admit(chain.prepare(n))
    stages = [chain.accounting['capture'], *chain.accounting['screening'], *chain.accounting['admission']]
    assert len(stages) == 1 + len(chain.batches) + len(nominees.nominees)
    for s in stages:
        assert s['cleanup'] == 'CLOSED' and s['errors'] == [] and s['connection_attempts'] >= 1 and s['elapsed_seconds'] < 165
    assert chain.accounting['capture']['capture_checkpoint_sha256'] is None or len(chain.accounting['capture']['capture_checkpoint_sha256']) == 64
    assert_closed(world, chain)


# ------------------------------------------------------------------------------------------------------------ date basis in SQL
def test_stockport_validated_scope_batches_through_the_sql_ledger(world, tmp_path, monkeypatch):
    """Before the correction a VALIDATED council's batch identity named RECEIVED, so the SQL batch binding (batch subject == root subject) refused it. The restricted worker now batches and screens it."""
    from verification.ingestion_storage import scope_binding
    monkeypatch.setitem(scope_binding.CHAIN_BINDINGS, 'stockport', scope_binding.ScopeBinding('stockport', 'idox', 'VALIDATED', 'IDOX_REQUESTS', None, 'accepted_idox_new_identity'))
    boot = world['boot']
    chain = Chain(world, tmp_path, 'idox', 'stockport', council='stockport').owner_reset().owner_registers_capture()
    chain.capture(), chain.read_capture()
    assert chain.capture_receipt['date_semantics'] == 'VALIDATED' and chain.contract.scope()['semantics'] == 'VALIDATED'
    nominees = chain.nominees()
    chain.owner_registers_chain(nominees.nominees)
    chain.screen()
    assert {ref: chain.screening_outcome(ref) for ref in EXPECTED} == EXPECTED
    # the pre-correction identity (a receipt that names no basis defaults to RECEIVED) is exactly what the SQL refuses
    from app.ingestion.batching import batch_plans
    stale = {k: v for k, v in chain.capture_receipt.items() if k != 'date_semantics'}
    assert batch_plans(chain.root['key'], stale, chain.rule)[0]['subject']['semantics'] == 'RECEIVED' != chain.contract.scope()['semantics']
    assert_closed(world, chain)


@pytest.mark.parametrize('family', FAMILIES)
def test_a_labelled_test_archive_is_never_accepted_as_live_evidence(world, tmp_path, family):
    """The label is enforced, not just carried: nomination and admission refuse a TEST_ARCHIVE receipt unless the caller explicitly opts in."""
    boot = world['boot']
    chain, nominees = staged(world, tmp_path, family, 'label-' + family)
    with pytest.raises(Denied, match='TEST_EVIDENCE_NOT_LIVE'):
        derive_nominees([chain.capture_receipt], chain.rule)
    adm = chain.prepare(nominees.nominees[0])
    with pytest.raises(Denied, match='TEST_EVIDENCE_NOT_LIVE'):
        chain.admit(adm, allow_test_evidence=False)
    assert adm.detail_calls == [] and boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
    assert_closed(world, chain)
