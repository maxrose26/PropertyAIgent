"""REQUIRES EXISTING ISOLATED DISPOSABLE PG17 HARNESS; never production.
Not executed in the cloud preparation session. No silent skip is accepted.
Fixture-only catalogue changes exercise each fixed predicate. The diagnostic
itself only SELECTs. The original DO is compared inside READ ONLY and contains
no activation statements. This is SQL validation, not provider/route proof.
"""
import json,os
from pathlib import Path
import pytest,psycopg
from tests.e2e_pg_world import disposable_world
from verification.ingestion_storage import oldham_policy
from verification.ingestion_storage.oldham_lifecycle import activation_gate
from verification.ingestion_storage.storage_controller import split_sql

if not os.environ.get('INGESTION_PROVISIONING_TEST_URL'):
    raise RuntimeError('FIXED_ISOLATED_DISPOSABLE_POSTGRES_REQUIRED_NO_SKIP')
ROOT=Path(__file__).parent
Q=json.loads((ROOT/'queries.json').read_bytes())
CODES=json.loads((ROOT/'gate-mapping.json').read_bytes())['codes']
DO=[s for s in split_sql(activation_gate(True)) if s.lstrip().startswith('DO ')][0]
assert 'ALTER ROLE' not in DO and 'GRANT ' not in DO and 'UPDATE ' not in DO.split('THEN RAISE')[0] # privilege-list strings are not statements

@pytest.fixture
def world():
    gen=disposable_world();w=next(gen)
    try:
        with w['connect']('provisioning_migrator') as c:c.execute(oldham_policy.installation_script())
        for role in ('ingestion_worker_login','ingestion_effect_login'):w['boot'].execute('ALTER ROLE '+role+' NOLOGIN PASSWORD NULL')
        yield w
    finally:
        try:next(gen)
        except StopIteration:pass

FAULTS=[
 ('LOGIN_FLAGS_OR_PARTIAL_ACTIVATION','ALTER ROLE ingestion_worker_login LOGIN','ALTER ROLE ingestion_worker_login NOLOGIN'),
 ('EXACT_RUNTIME_MEMBERSHIP','GRANT ingestion_storage_operator TO ingestion_worker_login WITH INHERIT FALSE, SET FALSE','REVOKE ingestion_storage_operator FROM ingestion_worker_login'),
 ('FORBIDDEN_RUNTIME_MEMBERSHIP','GRANT ingestion_storage_owner TO ingestion_worker WITH INHERIT FALSE, SET FALSE','REVOKE ingestion_storage_owner FROM ingestion_worker'),
 ('AMBIENT_SCHEMA_CREATE','GRANT CREATE ON SCHEMA public TO ingestion_worker_login','REVOKE CREATE ON SCHEMA public FROM ingestion_worker_login'),
 ('AMBIENT_UNRELATED_TABLE_ACCESS','CREATE TABLE public.diagnostic_fixture_only(x int);GRANT SELECT ON public.diagnostic_fixture_only TO ingestion_worker_login','DROP TABLE public.diagnostic_fixture_only'),
 ('AMBIENT_UNRELATED_SEQUENCE','CREATE SEQUENCE public.diagnostic_sequence_fixture_only;GRANT USAGE ON SEQUENCE public.diagnostic_sequence_fixture_only TO ingestion_worker_login','DROP SEQUENCE public.diagnostic_sequence_fixture_only'),
 ('AMBIENT_UNREVIEWED_DEFINER',"CREATE FUNCTION public.diagnostic_function_fixture_only() RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'",'DROP FUNCTION public.diagnostic_function_fixture_only()'),
 ('WORKER_DIRECT_LEDGER_MUTATION','GRANT UPDATE(key) ON public.ingestion_work_items TO ingestion_worker_login','REVOKE UPDATE(key) ON public.ingestion_work_items FROM ingestion_worker_login'),
 ('REQUIRED_RUNTIME_FUNCTION_MISSING',"REVOKE EXECUTE ON FUNCTION public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) FROM ingestion_worker",'GRANT EXECUTE ON FUNCTION public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb) TO ingestion_worker'),
 ('RECOVERY_MUST_REMAIN_DORMANT','ALTER ROLE ingestion_recovery_login LOGIN','ALTER ROLE ingestion_recovery_login NOLOGIN'),
]

def selected(boot):
    boot.execute(Q['begin'])
    try:
        rows=boot.execute(Q['gate_predicates']).fetchone()[0]
        off=boot.execute(Q['gate_offenders']).fetchone()[0]
        assert len(rows)==17 and len(off)==8
        assert all(r['inputs_present'] is True for r in rows)
        return rows
    finally:boot.execute(Q['rollback'])

def gate_code(boot):
    boot.execute(Q['begin'])
    try:
        try:boot.execute(DO)
        except psycopg.Error as e:
            code=e.diag.message_primary
            assert e.sqlstate=='P0001' and code in CODES
            return code
        return None
    finally:boot.execute(Q['rollback'])

def test_native_baseline_and_all_fixed_statements_parse(world):
    b=world['boot'];assert not any(r['failing'] for r in selected(b));assert gate_code(b) is None
    b.execute(Q['begin'])
    try:
        assert len(b.execute(Q['identity']).fetchone())==19
        assert b.execute(Q['roles'],[list(('ingestion_worker_login','ingestion_effect_login','ingestion_application_login','ingestion_storage_login'))]).fetchall()
        assert b.execute(Q['roles_without_password'],[['ingestion_worker_login','ingestion_effect_login']]).fetchall()
        b.execute(Q['memberships'],[['ingestion_worker_login','ingestion_effect_login']]).fetchall()
        b.execute(Q['sessions'],[['ingestion_worker_login','ingestion_effect_login']]).fetchall()
        b.execute(Q['functions'],[['ingestion_worker_step','ingestion_oldham_allowed','ingestion_acceptance_control']]).fetchall()
        b.execute(Q['control']).fetchall();b.execute(Q['ledger']).fetchall();b.execute(Q['barriers']).fetchall()
    finally:b.execute(Q['rollback'])
    assert b.info.transaction_status==psycopg.pq.TransactionStatus.IDLE

@pytest.mark.parametrize('code,setup,cleanup',FAULTS)
def test_native_predicate_matches_exact_failed_run_gate(world,code,setup,cleanup):
    b=world['boot']
    try:
        for s in split_sql(setup+';'):b.execute(s)
        rows=selected(b);assert any(r['code']==code and r['failing'] is True for r in rows)
        first=next(r['code'] for r in rows if r['failing'])
        assert gate_code(b)==first
    finally:
        for s in split_sql(cleanup+';'):b.execute(s)
    assert b.info.transaction_status==psycopg.pq.TransactionStatus.IDLE


def test_native_stored_expiry_is_not_revocation(world):
    b=world['boot'];ctl=b.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    authority='INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5'
    # Incomplete, expired, NON-EXECUTABLE disposable projection fixture; no issuance.
    ctl.setdefault('grants',{})[authority]={'expires_at':1,'source_calls':0,'writes':0,'keys':[]}
    ctl.setdefault('oldham_allowances',{})[authority]={'expires_at':1,'revoked':False}
    b.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
    b.execute(Q['begin'])
    try:
        v=b.execute(Q['ledger']).fetchone()[0]
        assert v['stored_grant_expiry']==1 and v['stored_allowance_expiry']==1
        assert v['grant_expired_at_snapshot'] is True and v['allowance_expired_at_snapshot'] is True and v['revoked'] is False
    finally:b.execute(Q['rollback'])
