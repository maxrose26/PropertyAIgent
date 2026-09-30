"""Prepared native PostgreSQL suite, never a guard bypass or SQLite substitute.
The fixture calls the canonical migration using an attested restricted-role engine.
"""
import uuid
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from app.db.models import Base, Council, Document
from app.db.ah_claim_schema import migrate_local
from tests.test_ah_qualified_discovery import record
from tests import test_ah_source_claims as original

@pytest.fixture
def unmigrated():
    import os
    from verification.ah_pg.cluster import provision_case,destroy_case
    engine,m=provision_case(os.environ['AH_DISPOSABLE_ROOT'])
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        destroy_case(engine,m)

@pytest.fixture
def db(unmigrated):
    engine=unmigrated
    with Session(engine,expire_on_commit=False) as s:
        s.add(Council(code='testcouncil',name='Test',base_url='https://example.invalid',date_field_mode='received',doc_system='idox'))
        s.commit()
        site,app,_=record(s)
        app.scheme_intelligence.development_type='mixed_retirement_and_market_housing'
        doc=Document(application_id=app.id,document_name='Synthetic evidence',source_url='https://example.invalid/doc1',extracted_text='Approximately 72 affordable retirement apartments in the retirement component. Scheme total 82 homes.')
        s.add(doc); s.commit()
        before=set(inspect(engine).get_table_names())
        assert migrate_local(engine) is True
        assert set(inspect(engine).get_table_names())-before=={'ah_source_claims','ah_claim_events'}
        yield engine,s,site,app,doc

# Reuse substantive original assertions, not their SQLite fixtures or compile-only checks.
NAMES = '''test_narrow_migration_and_retained_rollback
test_append_only_db_protections
test_duplicate_keys_and_changed_content
test_invalid_import_rejected_without_rows
test_independent_documents_corroborate
test_concurrent_reviews_reject_stale_head
test_concurrent_duplicate_imports_one_row
test_review_replay_and_import_invalidates_preview
test_scope_correction_retains_unrelated_evidence
test_unclear_scope_requires_new_claim
test_stage_alone_and_date_do_not_resolve_conflicts
test_reversal_and_cycle
test_unknown_legacy_zero_and_source_zero
test_component_zero_and_unknown_do_not_prove_maximum
test_no_writes_on_read_and_specialist_exclusion
test_same_selection_across_consumers_and_csv
test_database_rejects_invalid_quantity_shape
test_changed_document_invalidates_review_and_selection
test_review_source_check_is_not_stage_or_availability
test_extractor_cannot_review
test_scope_correction_does_not_hide_other_component
test_dirty_session_not_flushed_by_claim_reader
test_audit_only_reaccept_does_not_change_projection
test_bound_forms_preserved
test_tenure_does_not_become_total_or_infer_opso
test_shared_consumer_outcomes_for_unknown_zero_conflict
test_actual_explore_report_row_and_csv
test_phase_claim_without_legacy_phase_position
test_concurrent_identical_review_replays
test_tenure_conflict_does_not_replace_independent_count
test_replacement_chain_can_resolve_rejected_intermediate'''.split()
for name in NAMES:
    globals()[name]=getattr(original,name)

@pytest.mark.parametrize('table',['ah_source_claims','ah_claim_events'])
def test_postgres_truncate_and_recovery(db,table):
    cid=original.add(db); original.review(db,cid)
    with db[0].connect() as c:
        pid=c.execute(text('SELECT pg_backend_pid()')).scalar_one(); c.commit()
        with pytest.raises(DBAPIError,match='append-only'):
            c.exec_driver_sql('TRUNCATE '+table+' CASCADE')
        c.rollback()
        assert c.execute(text('SELECT pg_backend_pid()')).scalar_one()==pid
        assert c.execute(text('SELECT count(*) FROM '+table)).scalar_one()==1


def test_ordinary_engine_denied_before_connection(unmigrated):
    from app.policy.ah_claim_store import preview
    ordinary=create_engine(unmigrated.url)
    try:
        for op in (lambda:migrate_local(ordinary),lambda:preview(ordinary,[1])):
            with pytest.raises(ValueError,match='migration remains disabled'):
                op()
    finally:
        ordinary.dispose()


@pytest.mark.parametrize('change', ['system_identifier','database_oid','role','host_netns','server_start','database'])
def test_incorrect_proof_denied(unmigrated,tmp_path,change):
    import json
    from verification.ah_pg.cluster import write_proof
    from app.db.ah_disposable_postgres import create_disposable_engine
    m=json.loads(unmigrated._ah_test_manifest.read_text())
    m[change]=m['netns'] if change=='host_netns' else (m[change]+1 if isinstance(m[change],int) else 'incorrect')
    proof=tmp_path/'bad.json'; write_proof(proof,m)
    with pytest.raises((ValueError,DBAPIError)):
        create_disposable_engine(proof)


@pytest.mark.parametrize('sql_text',[
    'ALTER TABLE ah_source_claims DROP CONSTRAINT ah_quantity_shape',
    'ALTER TABLE ah_source_claims DISABLE TRIGGER ah_source_claims_deny_mutation',
    "CREATE OR REPLACE FUNCTION ah_deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END; $$",
    "ALTER TABLE ah_source_claims ALTER COLUMN schema_version SET DEFAULT 2",
    'DROP INDEX ix_ah_document',
    'ALTER TABLE ah_claim_events ENABLE ROW LEVEL SECURITY',
])
def test_catalog_tampering_rejected(db,sql_text):
    from app.db.ah_claim_schema import verify_schema
    with db[0].begin() as c:
        c.exec_driver_sql(sql_text)
    with pytest.raises(ValueError,match='changed creation-attested schema'):
        with db[0].connect() as c:
            verify_schema(c)


def test_partial_schema_not_adopted(unmigrated):
    from app.db.ah_claim_schema import claims
    # Deliberately incomplete canonical table is a rejection fixture, not a replacement migration.
    with unmigrated.begin() as c:
        claims.create(c)
    with pytest.raises(ValueError,match='creation-attested schema'):
        migrate_local(unmigrated)
    assert not inspect(unmigrated).has_table('ah_claim_events')


def test_ddl_failure_rolls_back_tables_and_connection_recovers(unmigrated):
    # Occupy the function name to force a real PostgreSQL CREATE FUNCTION failure.
    with unmigrated.begin() as c:
        c.exec_driver_sql("CREATE FUNCTION ah_deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END; $$")
    with pytest.raises(DBAPIError):
        migrate_local(unmigrated)
    assert not inspect(unmigrated).has_table('ah_source_claims')
    assert not inspect(unmigrated).has_table('ah_claim_events')
    with unmigrated.begin() as c:
        c.exec_driver_sql('DROP FUNCTION ah_deny_mutation()')
        assert c.exec_driver_sql('SELECT 42').scalar_one()==42
    assert migrate_local(unmigrated) is True
    assert migrate_local(unmigrated) is False


def test_new_engine_cannot_bless_existing_schema(db):
    from app.db.ah_disposable_postgres import create_disposable_engine
    e=create_disposable_engine(db[0]._ah_test_manifest)
    try:
        with pytest.raises(ValueError,match='creation-attested schema'):
            migrate_local(e)
    finally:
        e.dispose()


def test_restricted_role_cannot_create_database_or_role(db):
    for statement in ['CREATE DATABASE ah_forbidden','CREATE ROLE ah_forbidden']:
        with db[0].connect().execution_options(isolation_level='AUTOCOMMIT') as c:
            with pytest.raises(DBAPIError) as error:
                c.exec_driver_sql(statement)
            assert error.value.orig.sqlstate=='42501'


def test_foreign_key_error_and_pool_recovery(db):
    from app.db.ah_claim_schema import claims
    from app.policy.ah_claim_store import prepare
    from datetime import datetime,timezone
    values=prepare(original.manifest(db,document_id=2147483647))
    with db[0].connect() as c:
        pid=c.exec_driver_sql('SELECT pg_backend_pid()').scalar_one(); c.commit()
        with pytest.raises(DBAPIError) as error:
            c.execute(claims.insert().values(**values,recorded_at=datetime.now(timezone.utc)))
        assert error.value.orig.sqlstate=='23503'
        c.rollback()
        assert c.exec_driver_sql('SELECT pg_backend_pid()').scalar_one()==pid
    assert original.add(db)>0


def test_server_address_text_identity(unmigrated):
    # inet::text includes the /32 mask. Keep exact comparison, never strip it.
    with unmigrated.connect() as c:
        assert c.exec_driver_sql("SELECT inet_server_addr()::text").scalar_one() == '127.0.0.1/32'
