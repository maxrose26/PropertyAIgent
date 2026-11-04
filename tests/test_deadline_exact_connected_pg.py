"""Affected qualification only, existing disposable PG17 fixture; no portal path."""
import ast
import inspect
import json
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import psycopg
import pytest
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL
from tests.test_database_evidence_migration_pg import migration_world, installed, support
from verification.ingestion_storage import runtime_authentication as auth
from verification.ingestion_storage.database_evidence import migration_sql
from verification.ingestion_storage.intake_budget import IntakeRun
from verification.ingestion_storage.operational_controller import DatabaseBudget

@pytest.fixture(scope='module')
def world():
    # Only fixture database selection changes. Runtime clients are unmodified.
    original=support.FIXTURE_DATABASE
    support.FIXTURE_DATABASE='ingestion_provisioning_test'
    try:yield from support.world.__wrapped__()
    finally:support.FIXTURE_DATABASE=original

RECORDED=1793827036.7709913

def test_connected_deadline_both_roles_and_cleanup(migration_world,record_property):
    boot=migration_world['boot'];results=[];roles=auth.op.ROLES
    with support.actor() as owner:support.execute(owner,migration_sql())
    ledger_before=auth.op.ledger_sha(boot)
    passwords={r:'synthetic-deadline-'+r for r in roles}
    urls={r:URL.create('postgresql+psycopg',username=r,password=passwords[r],host='127.0.0.1',port=5432,database='ingestion_provisioning_test').render_as_string(hide_password=False) for r in roles}
    def set_deadline(r,d,offset=0):
        value=datetime.fromtimestamp(d,timezone.utc)+timedelta(microseconds=offset)
        boot.execute(sql.SQL('ALTER ROLE {} LOGIN VALID UNTIL {}').format(sql.Identifier(r),sql.Literal(value.isoformat())))
    def cleanup():
        for role,cap in roles.items():
            boot.execute(sql.SQL('ALTER ROLE {} NOLOGIN').format(sql.Identifier(role)))
            boot.execute(sql.SQL('REVOKE {} FROM {} GRANTED BY provisioning_bootstrap').format(sql.Identifier(cap),sql.Identifier(role)))
        sessions=boot.execute('SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)',(list(roles),)).fetchone()[0]
        members=boot.execute('SELECT count(*) FROM pg_auth_members WHERE member=ANY(SELECT oid FROM pg_roles WHERE rolname=ANY(%s))',(list(roles),)).fetchone()[0]
        assert sessions==members==0
        assert boot.execute('SELECT bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname=ANY(%s)',(list(roles),)).fetchone()==(True,)
        assert support.actor_flags()==(False,False,False)
        assert auth.op.ledger_sha(boot)==ledger_before
        return dict(sessions=0,memberships=0,logins_disabled=True,temporary_owner_absent=True,ledger_preserved=True)
    try:
        for role,cap in roles.items():
            boot.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role),sql.Literal(passwords[role])))
            boot.execute(sql.SQL('GRANT {} TO {} WITH ADMIN FALSE, INHERIT TRUE, SET FALSE').format(sql.Identifier(cap),sql.Identifier(role)))
            boot.execute(sql.SQL('ALTER ROLE {} SET extra_float_digits=0').format(sql.Identifier(role)))
        query=next(n.value for n in ast.walk(ast.parse(inspect.getsource(auth.qualify))) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('SELECT current_user,session_user'))
        # Establish genuine password-authenticated application connections while
        # valid, then query the historical epoch. PostgreSQL cannot authenticate
        # a password whose historical VALID UNTIL has already elapsed.
        for role,cap in roles.items():
            set_deadline(role,time.time()+2100)
            budget=DatabaseBudget(statements=20,connections=1,returned_bytes=8192,seconds=12)
            try:
                with budget.engine(urls[role]).connect() as conn:
                    for offset in (-1,0,1):
                        set_deadline(role,RECORDED,offset)
                        row=tuple(conn.execute(text(query),dict(cap=cap)).one())
                        comparison=auth.profile_comparison(row,role,RECORDED)
                        assert (comparison['status']=='MATCH')==(offset==0)
                        assert all(v for k,v in comparison['checks'].items() if k!='credential_deadline')
                        assert row[10]==Decimal('1793827036.770991')+Decimal(offset)/1000000
                        results.append(dict(case='recorded_query',role=role,offset_us=offset,numeric_epoch=str(row[10]),comparison=comparison))
            finally:
                closed=budget.close([])
                assert closed['connections_closed'] and closed['cleanup']=='CLOSED'
        # Unmodified qualification + unmodified DatabaseBudget/SQLAlchemy/psycopg.
        for failed_role,offset in [(None,0)]+[(r,o) for r in roles for o in (-1,1)]:
            deadline=float(str(int(time.time())+2100)+'.7709913')
            for r in roles:set_deadline(r,deadline,offset if r==failed_role else 0)
            runtime=SimpleNamespace(args=SimpleNamespace(period='disposable-exact-deadline'),binding=auth.op.APPLICATION_BINDING,run=IntakeRun(),urls=urls,options={},emit=lambda *_:None,deadline_diagnostic=True)
            receipt=auth.qualify(runtime,deadline)
            assert receipt['source_requests']==0
            if failed_role is None:
                assert receipt['status']=='VERIFIED_BOTH_RESTRICTED_ROLES',receipt
                assert {v['role'] for v in receipt['roles']}==set(roles)
            else:
                first=receipt['first_qualification_failure']
                assert first['role']==failed_role and first['comparison']['first_mismatch']=='credential_deadline',receipt
                assert receipt['status']=='REFUSED'
            assert all(a['connections_closed'] and a['cleanup']=='CLOSED' for a in receipt['attempts'])
            results.append(dict(case='full_qualification',failed_role=failed_role,offset_us=offset,receipt=receipt))
        expired=time.time()-1
        for r in roles:set_deadline(r,expired)
        runtime=SimpleNamespace(args=SimpleNamespace(period='disposable-expired'),binding={},run=IntakeRun(),urls=urls,options={},emit=lambda *_:None)
        receipt=auth.qualify(runtime,expired)
        assert receipt['status']=='REFUSED' and receipt['attempts']==[] and receipt['source_requests']==0
        results.append(dict(case='expired_before_connection',receipt=receipt))
        for r in roles:
            budget=DatabaseBudget(statements=20,connections=1,returned_bytes=8192,seconds=12)
            try:
                with budget.engine(urls[r]).connect():raise AssertionError('EXPIRED_PASSWORD_AUTHENTICATED')
            except Exception as exc:
                assert not isinstance(exc,AssertionError)
                assert budget.connection_diagnostics[-1]['reason_code']=='AUTHENTICATION_REJECTED',budget.connection_diagnostics
            finally:
                closed=budget.close([])
                assert closed['connections_closed'] and closed['cleanup']=='CLOSED'
            results.append(dict(case='server_expired_password',role=r,cleanup=closed))
    finally:
        closure=cleanup()
    report=dict(server_version=migration_world['server_version'],psycopg=psycopg.__version__,cases=results,case_count=len(results),cleanup=closure,source_requests=0)
    raw=json.dumps(report,sort_keys=True,indent=2)
    assert all(v not in raw for v in passwords.values()) and 'postgresql://' not in raw
    out=Path(os.environ['DEADLINE_PROOF_DIR']);out.mkdir(exist_ok=True)
    (out/'connected-results.json').write_text(raw+'\n')
    record_property('connected_cases',len(results));record_property('server_version',migration_world['server_version'])
