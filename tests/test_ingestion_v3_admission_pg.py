"""Real wrapper, SQL ledger and three restricted logins; disposable PG17 only.

Bootstrap constructs/asserts fixtures, never performs the tested admission.
Synthetic listing/detail bodies use existing parsers. No council or GitHub.
"""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import secrets
import time

import psycopg
from psycopg import sql
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import DBAPIError

from app.config import get_council
from app.db.models import Application, Base, Council, Site
from app.ingestion.batching import batch_plans, process_batch
from app.ingestion.coordinator import Coordinator
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS, Denied, UncertainPersistence, digest
from app.ingestion.listing_screening import RULE_V3, V3_CONTRACT, ScreeningRule, assessment_identity, code_binding
from app.ingestion.schema import WorkItem as W
from tests.test_discovery_admission import envelope
from tests.test_discovery_ingestion_acceptance import listing_audit
from tests.test_discovery_ingestion_ledger import outer
from tests.test_discovery_ingestion_provisioning_pg import PACKAGE, ROLES
from tests.test_discovery_initial_application_contract import projected
from verification.direct_reference.fixtures import summary
from verification.discovery.idox_window import WindowConfig
from verification.ingestion_storage import screening_v3_worker_sql
from verification.ingestion_storage.new_identity_contract import accepted_idox_new_identity
from verification.ingestion_storage.operational_controller import AcceptanceBinding, ControllerLedger, DatabaseBudget, execute
from verification.ingestion_storage.retained_world import item
from verification.ingestion_storage.v3_admission import V3AdmissionBinding, execute_retained_v3, factual_binding


@pytest.fixture(scope='module')
def pg():
    raw = os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:
        pytest.skip('fixed disposable PG17 service required')
    info = psycopg.conninfo.conninfo_to_dict(raw)
    assert (info['host'], info['port'], info['dbname'], info['user']) == ('127.0.0.1', '5432', 'ingestion_provisioning_test', 'provisioning_bootstrap')
    names = ['provisioning_migrator', 'ingestion_worker_login', 'ingestion_storage_login', 'ingestion_effect_login', 'ingestion_recovery_login', 'ingestion_application_login']
    passwords = {name: secrets.token_urlsafe(48) for name in names}
    setup_started = time.monotonic()
    fixture_costs = dict(connection_attempts=1, cursor_calls=0)
    class FixtureCursor(psycopg.Cursor):
        def execute(self, *args, **kwargs):
            fixture_costs['cursor_calls'] += 1
            return super().execute(*args, **kwargs)
    with psycopg.connect(raw, autocommit=True, prepare_threshold=None, cursor_factory=FixtureCursor) as boot:
        assert boot.info.server_version >= 170000
        app = create_engine(URL.create('postgresql+psycopg', **dict(username=info['user'], password=info['password'], host='127.0.0.1', port=5432, database=info['dbname'])), poolclass=NullPool, connect_args=dict(cursor_factory=FixtureCursor))
        from sqlalchemy import event
        event.listen(app, 'do_connect', lambda *args: fixture_costs.__setitem__('connection_attempts', fixture_costs['connection_attempts'] + 1))
        def connect(role):
            fixture_costs['connection_attempts'] += 1
            return psycopg.connect(**{**info, 'user': role, 'password': passwords[role]}, autocommit=True, prepare_threshold=None, cursor_factory=FixtureCursor)
        try:
            boot.execute(sql.SQL('CREATE ROLE provisioning_migrator LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Literal(passwords['provisioning_migrator'])))
            boot.execute('GRANT USAGE,CREATE ON SCHEMA public TO provisioning_migrator WITH GRANT OPTION')
            boot.execute('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO provisioning_migrator WITH GRANT OPTION')
            with connect('provisioning_migrator') as c:
                c.execute((PACKAGE / 'install.sql').read_text())
                c.execute(Path('docs/design/ingestion-operational-20261016/worker.sql').read_text())
            Base.metadata.create_all(app)
            writer = Path('docs/design/ingestion-operational-acceptance-20261016/application-writer.sql').read_text()
            grants = '\n'.join(line for line in writer.splitlines() if not line.startswith('CREATE ROLE ')).replace(' TO ingestion_application_writer', ' TO provisioning_migrator WITH GRANT OPTION')
            boot.execute(grants)
            with connect('provisioning_migrator') as c:
                c.execute(writer)
                c.execute(Path('docs/design/ingestion-operational-acceptance-20261016/runtime-mappings.sql').read_text())
                # Existing reviewed v3 function, unchanged, installed as fixture only.
                c.execute(screening_v3_worker_sql.installation_script())
            for role in names[1:]:
                boot.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role), sql.Literal(passwords[role])))
            with connect('provisioning_migrator') as c:
                c.execute(Path('docs/design/ingestion-operational-acceptance-20261016/activate.sql').read_text())
            with Session(app) as s:
                s.add(Council(code='bolton', name='Bolton', base_url='https://paplanning.bolton.gov.uk', date_field_mode='received', doc_system='idox'))
                s.commit()
            control = boot.execute('SELECT outcome FROM ingestion_work_items WHERE key=repeat(\'0\',64)').fetchone()[0]
            initial_control = copy.deepcopy(control)
            # Disposable authority fixture only: production stops are not read or changed.
            control['global_stop'] = None
            control['manual_stop'] = None
            control['grants'] = {}
            urls = {role: URL.create('postgresql+psycopg', username=role, password=passwords[role], host='127.0.0.1', port=5432, database=info['dbname']).render_as_string(hide_password=False) for role in names[1:]}
            yield dict(boot=boot, app=app, control=control, urls=urls, connect=connect, setup_seconds=time.monotonic() - setup_started, setup_costs=dict(fixture_costs), fixture_costs=fixture_costs, initial_control=initial_control)
        finally:
            app.dispose()
            boot.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
            extra = ['ingestion_application_writer', 'ingestion_effect_broker', 'ingestion_recovery_operator', 'ingestion_effect_login', 'ingestion_recovery_login', 'ingestion_application_login']
            for name in ['provisioning_migrator', *ROLES, *extra]:
                boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(name)))
            for name in ['provisioning_migrator', *ROLES, *extra]:
                boot.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)))


def scenario(pg, tag, proposal='Erection of 20 residential dwellings'):
    """Install synthetic saved capture; generate its assessment via real batch SQL."""
    boot = pg['boot']
    target, detail, _ = projected(summary('01780/26', status='Decided', decision='Approve', date='Mon 28 Sep 2026'))
    cfg = WindowConfig(max_transport_retries=0)
    contract = IdoxListingContract('controller-idox', cfg, 'a' * 64)
    source = listing_audit(target)
    if proposal != 'Erection of 20 residential dwellings':
        from tests.test_discovery_idox_window import FORM, Response, page
        from verification.discovery.idox_window import run
        echo = FORM.replace(b'name="date(applicationReceivedStart)" value=""', b'name="date(applicationReceivedStart)" value="28/09/2026"').replace(b'name="date(applicationReceivedEnd)" value=""', b'name="date(applicationReceivedEnd)" value="04/10/2026"')
        body = page(first=1, last=1, total=1, refs=(target['reference'],)).replace(b'keyVal=K0', ('keyVal='+target['source_identifier']).encode()).replace(b'Outline residential development, scale unknown', proposal.encode())
        bodies = iter([FORM, body, body, echo])
        source = run(lambda *args, **kwargs: Response(next(bodies)), cfg)
    capture = contract.project(source, outer(), DEFAULT_LIMITS)
    capture.pop('window')
    capture['durable_archive'] = dict(commit='a' * 40, path='docs/design/disposable.json', sha256=digest(source), bytes=len(json.dumps(source).encode()), readback_verified=True)
    rule = ScreeningRule(RULE_V3, unit_threshold=10, link_related=False)
    record = capture['records'][0]
    root = item(dict(subject=dict(kind='DISCOVERY_SCOPE', council='bolton', start=cfg.start.isoformat(), end=cfg.end.isoformat(), semantics='RECEIVED'), task='DISCOVERY', contract=contract.name, revision=tag))
    root.update(state='COMPLETE', phase='FINISHED', checkpoint=capture, outcome=dict(children=[]))
    plans = batch_plans(root['key'], capture, rule)
    batch = item({k: plans[0][k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=plans[0]['dependencies'], checkpoint=plans[0]['checkpoint'])
    subject = dict(kind='APPLICATION', council='bolton', reference=record['reference'])
    screen = item(dict(subject=subject, task='SCREENING', contract=V3_CONTRACT, revision=assessment_identity(record, rule)[3]), dependencies=[root['key']])
    factual_contract = accepted_idox_new_identity('controller-fact', target)
    fact = item(dict(subject=subject, task='FACTUAL_REFRESH', contract=factual_contract.name, revision=tag), dependencies=[screen['key']])
    # Each scenario is an independent disposable world, not a recovery/retry.
    boot.execute('DELETE FROM ingestion_work_attempts')
    boot.execute("DELETE FROM ingestion_work_items WHERE key<>repeat('0',64)")
    boot.execute('TRUNCATE applications CASCADE')
    control = copy.deepcopy(pg['control'])
    authority = 'INGESTION_TEST_v3_handoff'
    bindings = {r['key']: {k: r[k] for k in ('subject', 'task', 'contract', 'revision')} for r in [root, batch, screen, fact]}
    grant = dict(keys=list(bindings), contracts=[contract.name, 'listing-batch-v1', V3_CONTRACT, factual_contract.name], bindings=bindings, expires_at=time.time()+600, source_calls=1, writes=2, login='ingestion_worker_login', effect_login='ingestion_effect_login', workers=['one'], detail_source_keys=[fact['key']], screening_configs=[digest(rule.config())], completion_outcomes={'SCREENING': ['ADMIT_SCHEME', 'ADMIT_FOR_ASSESSMENT', 'ROUTE_COUNT_UNCONFIRMED', 'RETAIN_RELATED_TO_PARENT', 'RETAIN_NOT_RESIDENTIAL_SUPPLY', 'RETAIN_BELOW_THRESHOLD'], 'FACTUAL_REFRESH': ['SUPPORTED_FACTS_VERIFIED', 'ALREADY_KNOWN']})
    grant['completion_outcomes']['LISTING_METADATA'] = ['BATCH_SCREENED']
    control['grants'][authority] = grant
    boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)", (json.dumps(control),))
    for row in [root, batch, fact]:
        boot.execute('INSERT INTO ingestion_work_items SELECT * FROM json_populate_record(NULL::ingestion_work_items,%s::json)', (json.dumps(row),))
    budgets = []
    def coordinator(budget):
        budgets.append(budget)
        worker, broker, app = [budget.engine(pg['urls'][r]) for r in ['ingestion_worker_login', 'ingestion_effect_login', 'ingestion_application_login']]
        ledger = ControllerLedger(worker, budget=budget, owner='one', authority=authority, bindings=bindings, broker_engine=broker, application_engine=app)
        return Coordinator(ledger, {contract.name: contract, factual_contract.name: factual_contract}, screening_rules={V3_CONTRACT: rule})
    b0 = DatabaseBudget(slot_key=batch['key'])
    co = coordinator(b0)
    try:
        process_batch(co, batch['key'], check=b0.check)
    finally:
        screening_cost = b0.close([])
    # Actual bounded retained-checkpoint read, carried into the writer budget.
    b1 = DatabaseBudget()
    co = coordinator(b1)
    try:
        saved = co.ledger.get(root['key'])['checkpoint']
        b1.capture_checkpoint_sha256 = digest(saved)
    finally:
        prior = b1.close([])
    budget = DatabaseBudget(previous=prior)
    co = coordinator(budget)
    nominee = AcceptanceBinding(root['key'], screen['key'], fact['key'], record['reference'], record['source_url'], record['source_record_id'], digest(record), digest(capture), digest(prior), batch['key'])
    binding = V3AdmissionBinding(nominee, 'bolton', contract.name, tag, digest(rule.config()), digest(code_binding()), factual_contract.name, tag, factual_binding(factual_contract))
    env = replace(envelope(), reference=record['reference'], displayed_references=(record['reference'],), source_url=record['source_url'], source_record_id=record['source_record_id'])
    return dict(co=co, binding=binding, envelope=env, detail=detail, budget=budget, screening_cost=screening_cost, fact=fact, root=root, screen=screen, batch=batch, budgets=budgets, target=target)


def test_runtime_permission_denials(pg):
    for role in ['ingestion_worker_login', 'ingestion_effect_login', 'ingestion_application_login']:
        with pg['connect'](role) as c:
            assert c.execute('SELECT rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone() == (False, False, False, False)
            for capability in ['ingestion_storage_owner', 'ingestion_authority_issuer', 'ingestion_barrier_releaser']:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    c.execute('SET ROLE ' + capability)
            for statement in ["UPDATE ingestion_work_items SET state='QUEUED'", 'DELETE FROM applications', 'UPDATE applications SET estimated_unit_count=20', 'UPDATE applications SET site_id=1', "UPDATE applications SET proposal='forged'", 'INSERT INTO sites DEFAULT VALUES']:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    c.execute(statement)


@pytest.mark.parametrize('case', ['exact', 'qualified', 'unknown', 'parent', 'forged_v1', 'known', 'race', 'unsupported', 'wrong_council', 'wrong_record', 'wrong_capture', 'wrong_config', 'wrong_code', 'wrong_fact', 'wrong_source_id', 'missing_batch', 'expired', 'before_effect', 'after_admission', 'b2_readback_failure', 'committed_readback_failure', 'ledger_lost_ack', 'interrupt_after_commit'])
def test_restricted_v3_handoff(pg, case, monkeypatch, record_property):
    fixture_before = dict(pg['fixture_costs'])
    proposal = {'qualified': 'Erection of up to 20 residential dwellings', 'unknown': 'Residential development, number of dwellings unknown', 'forged_v1': 'Residential development, number of dwellings unknown', 'parent': 'Discharge of condition 3 attached to planning permission 01234/26'}.get(case, 'Erection of 20 residential dwellings')
    sc = scenario(pg, case, proposal)
    co, b, budget = sc['co'], sc['binding'], sc['budget']
    boot, app = pg['boot'], pg['app']
    # A separate already-authorised task must also be stopped by uncertainty.
    other = dict(sc['fact'], key=digest(dict(other=case)), revision='other-' + case)
    boot.execute('INSERT INTO ingestion_work_items SELECT * FROM json_populate_record(NULL::ingestion_work_items,%s::json)', (json.dumps(other),))
    co.ledger.bindings[other['key']] = {k: other[k] for k in ('subject', 'task', 'contract', 'revision')}
    ctl = boot.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    grant = ctl['grants'][co.ledger.authority]
    grant['keys'].append(other['key'])
    grant['bindings'][other['key']] = co.ledger.bindings[other['key']]
    boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)", (json.dumps(ctl),))
    called = []
    def detail(_):
        called.append(1)
        return sc['detail'], outer()
    if case == 'known':
        with Session(app) as s:
            s.add(Application(council_code='bolton', reference='01780/26', status='PRESERVED'))
            s.commit()
    if case == 'unsupported':
        _, sc['detail'], _ = projected(summary('01780/26', status='Awaiting decision', omit=('Decision', 'Decision Issued Date')))
    if case == 'forged_v1':
        row = boot.execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (sc['screen']['key'],)).fetchone()[0]
        row['disposition'] = 'SUPPORTED_PROCESSING_PRIORITY'
        boot.execute('UPDATE ingestion_work_items SET checkpoint=%s::json WHERE key=%s', (json.dumps(row), sc['screen']['key']))
    if case == 'wrong_source_id':
        contract = co.contracts[b.factual_contract]
        co.contracts[b.factual_contract] = replace(contract, row=dict(contract.row, source_identifier='OTHER'))
        b = replace(b, factual_contract_sha256=factual_binding(co.contracts[b.factual_contract]))
    mutations = {'wrong_council': {'council': 'manchester'}, 'wrong_config': {'screening_config_sha256': '0'*64}, 'wrong_code': {'screening_code_sha256': '0'*64}, 'wrong_fact': {'factual_revision': 'other'}}
    if case in mutations:
        b = replace(b, **mutations[case])
    if case in {'wrong_record', 'wrong_capture', 'missing_batch'}:
        b = replace(b, nominee=replace(b.nominee, **{'wrong_record': {'listing_revision': '0'*64}, 'wrong_capture': {'retained_capture_sha256': '0'*64}, 'missing_batch': {'screening_batch_key': None}}[case]))
    if case == 'expired':
        ctl = boot.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
        ctl['grants'][co.ledger.authority]['expires_at'] = 0
        boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)", (json.dumps(ctl),))
    if case == 'before_effect':
        def detail(_):
            raise KeyboardInterrupt('disposable before effects')
    if case in {'after_admission', 'interrupt_after_commit'}:
        import app.pipeline.discovery_admission as admission
        real = admission.admit_identity
        def after(*args, **kwargs):
            result = real(*args, **kwargs)
            if case == 'interrupt_after_commit':
                raise KeyboardInterrupt('disposable committed identity')
            raise RuntimeError('disposable committed identity')
        monkeypatch.setattr(admission, 'admit_identity', after)
    if case == 'race':
        # A second delivery wins between wrapper precheck and shared admission.
        # Both deliveries use the real restricted application engine and writer;
        # the one-connection contract deliberately serialises their DB effects.
        import app.pipeline.discovery_admission as admission
        import subprocess, sys
        from dataclasses import asdict
        real = admission.admit_identity
        race_costs = []
        def race(engine, envelope):
            engine.dispose()  # close idle connection: reviewed login limit is one
            child = subprocess.run([sys.executable, '-m', 'tests.v3_admission_supervised', 'race'],
                input=json.dumps(asdict(envelope), default=str), text=True, capture_output=True, timeout=10,
                env=dict(PATH='/usr/bin:/bin', HOME=os.environ['HOME'], DATABASE_URL='sqlite:///:memory:', V3_DISPOSABLE_WRITER_URL=pg['urls']['ingestion_application_login']))
            assert child.returncode == 0, 'disposable competing writer failed'
            winner = json.loads(child.stdout)
            race_costs.append(winner['costs'])
            assert winner['outcome'] == 'CREATED_PENDING'
            return real(engine, envelope)
        monkeypatch.setattr(admission, 'admit_identity', race)
    if case == 'b2_readback_failure':
        from sqlalchemy import event
        def reject_after_b2(connection, cursor, statement, parameters, context, many):
            if statement.lstrip().startswith('UPDATE applications'):
                raise RuntimeError('disposable B2 failure')
        event.listen(co.ledger.engine, 'after_cursor_execute', reject_after_b2)
    if case == 'committed_readback_failure':
        committed = []
        real_commit, real_scalar = Session.commit, Session.scalar
        def commit(session):
            b2 = session.bind is co.ledger.engine and any(isinstance(x, Application) and x.status is not None for x in session.dirty)
            result = real_commit(session)
            if b2:
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
            if op == 'resolve_effect' and co.ledger.get(sc['fact']['key'])['phase'] == 'WRITE_INTENT':
                raise RuntimeError('disposable ledger acknowledgement loss')
            return result
        monkeypatch.setattr(co.ledger, '_step', lost)
    before = boot.execute('SELECT count(*) FROM applications').fetchone()[0]
    result = None
    try:
        if case.startswith('wrong_') or case in {'missing_batch', 'expired', 'before_effect', 'after_admission', 'b2_readback_failure', 'committed_readback_failure', 'ledger_lost_ack', 'interrupt_after_commit'}:
            expected_error = KeyboardInterrupt if case in {'before_effect', 'interrupt_after_commit'} else DBAPIError if case == 'expired' else UncertainPersistence if case in {'after_admission', 'b2_readback_failure', 'committed_readback_failure', 'ledger_lost_ack'} else Denied
            with pytest.raises(expected_error) as exc:
                execute(co, b, listing_reader=lambda _: pytest.fail('no listing refetch'), detail_reader=detail, envelope=sc['envelope'], council=get_council('bolton'), check=budget.check)
            assert not isinstance(exc.value, (AssertionError, TypeError, KeyError, AttributeError)), type(exc.value).__name__
        else:
            result = execute(co, b, listing_reader=lambda _: pytest.fail('no listing refetch'), detail_reader=detail, envelope=sc['envelope'], council=get_council('bolton'), check=budget.check)
        after = boot.execute('SELECT count(*) FROM applications').fetchone()[0]
        if case in {'exact', 'qualified'}:
            assert result['outcome'] == 'SUPPORTED_FACTS_VERIFIED' and after == 1 and called == [1]
            assert result['factual']['unit_facts'] == 'NOT_WRITTEN'
            saved = boot.execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (sc['screen']['key'],)).fetchone()[0]
            assert saved['count_assessment']['admission'] == ('ADMIT_SCHEME' if case == 'exact' else 'ADMIT_FOR_ASSESSMENT')
        elif case == 'known':
            assert after == before == 1 and called == []
            assert boot.execute('SELECT status FROM applications').fetchone()[0] == 'PRESERVED'
        elif case == 'race':
            assert result['admission'] == 'EXISTING_IDENTITY_PRESERVED' and after == 1
            assert boot.execute('SELECT status FROM applications').fetchone()[0] is None
        elif case in {'unknown', 'parent', 'forged_v1'}:
            assert result['admission'] == 'NOT_ATTEMPTED' and after == 0 and not called
            if case == 'forged_v1':
                assert boot.execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s', (sc['screen']['key'],)).fetchone()[0]['disposition'] == 'SUPPORTED_PROCESSING_PRIORITY'
        elif case == 'unsupported':
            assert result['factual']['identity'] == 'NOT_CREATED' and after == 0
        elif case in {'after_admission', 'b2_readback_failure', 'committed_readback_failure', 'ledger_lost_ack', 'interrupt_after_commit'}:
            assert after == 1
            phase = boot.execute('SELECT phase FROM ingestion_work_items WHERE key=%s', (sc['fact']['key'],)).fetchone()[0]
            assert phase == 'WRITE_INTENT'
            with pytest.raises(Exception):
                co.ledger.claim(sc['fact']['key'])
            with pytest.raises(Exception):
                co.ledger.claim(other['key'])
            if case in {'committed_readback_failure', 'ledger_lost_ack'}:
                assert boot.execute('SELECT status FROM applications').fetchone()[0] == 'Decided'
            assert boot.execute('SELECT count(*) FROM applications').fetchone()[0] == 1
        else:
            assert after == 0
        assert boot.execute('SELECT count(*) FROM sites').fetchone()[0] == 0
        assert boot.execute('SELECT count(*) FROM applications WHERE site_id IS NOT NULL OR estimated_unit_count IS NOT NULL OR opportunity_classification IS NOT NULL').fetchone()[0] == 0
        actual = boot.execute('SELECT reference,status,decision,site_id,estimated_unit_count FROM applications ORDER BY id').fetchall()
        record_property('effects', json.dumps(dict(case=case, identity_delta=after-before, rows=actual,
            factual_delivery='ACKNOWLEDGED' if result and result.get('outcome') == 'SUPPORTED_FACTS_VERIFIED' else 'NOT_ACKNOWLEDGED',
            identity_count=after, sites=0, unit_writes=0), sort_keys=True))
    finally:
        costs = budget.close([])
        assert costs['cleanup'] == 'CLOSED' and costs['connections_opened'] == costs['connections_closed_count']
        assert costs['driver_statements'] <= 120 and costs['connection_attempts'] <= 16
        if case == 'race':
            assert sum(x['driver_statements'] for x in race_costs) + costs['driver_statements'] <= 120
            assert sum(x['connection_attempts'] for x in race_costs) + costs['connection_attempts'] <= 16
            assert all(x['cleanup'] == 'CLOSED' for x in race_costs)
        child_costs = race_costs if case == 'race' else []
        totals = {name: costs[name] + sum(x[name] for x in child_costs) for name in ('driver_statements', 'connection_attempts', 'returned_data_value_bytes', 'connection_active_seconds')}
        # Parent elapsed includes the child wait; never add it a second time.
        totals['supervised_seconds'] = costs['elapsed_seconds']
        measured = dict(case=case, admission=result and result.get('admission'), runtime=costs, competing_delivery=child_costs, runtime_totals=totals,
                        screening=sc['screening_cost'], fixture_setup_seconds=pg['setup_seconds'], fixture_setup=pg['setup_costs'],
                        fixture_and_assertions={k: pg['fixture_costs'][k] - fixture_before[k] for k in fixture_before})
        record_property('measured', json.dumps(measured, sort_keys=True))
        print('V3_HANDOFF_MEASURED ' + json.dumps(measured, sort_keys=True))
