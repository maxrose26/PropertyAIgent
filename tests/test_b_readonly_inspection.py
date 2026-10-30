"""Fixed B inspection; all database setup/mutations below are disposable only."""
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import sys
import time
import pytest

ROOT=Path('docs/design/daily-intake-20261029')
SQL=(ROOT/'b-readonly.sql').read_text()
spec=importlib.util.spec_from_file_location('fixed_b_client',ROOT/'b-readonly-client.py')
client=importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def statements():
    return [s.strip() for s in re.sub(r'--[^\n]*','',SQL).split(';') if s.strip()]


def test_fixed_query_hash_and_no_effects():
    assert hashlib.sha256(SQL.encode()).hexdigest()==client.SQL_SHA
    assert len(statements())==16
    assert statements()[0].endswith('READ ONLY') and statements()[-1]=='ROLLBACK'
    assert not re.search(r'\b(GRANT|SET ROLE|CREATE|INSERT|UPDATE|DELETE)\b',
                         re.sub(r"'[^']*'",'', '\n'.join(statements())),re.I)


@pytest.mark.parametrize('mode',['normal','error','deadline','overflow'])
def test_client_bounds_and_uncertain_remote_closure(mode):
    code={'normal':'print("ROLLBACK")','error':'raise SystemExit(2)',
          'deadline':'import time; time.sleep(10)',
          'overflow':'import sys; sys.stderr.write("X"*100000)'}[mode]
    start=time.monotonic()
    data,status=client.capture([sys.executable,'-I','-S','-c',code],{},seconds=2.5,ceiling=1024)
    assert time.monotonic()-start<3
    assert len(data)<=1024 and status['client_closed']
    assert (status['classification']=='OBSERVATIONS_REQUIRE_REVIEW')==(mode=='normal')
    if mode!='normal': assert status['remote_closure']=='NOT_ACKNOWLEDGED'


def test_client_has_fixed_secure_connection_contract():
    source=(ROOT/'b-readonly-client.py').read_text()
    for value in ('getpass.getpass','passfile.chmod(0o600)',"'PGSSLMODE':'verify-full'",
                  "'PGCONNECT_TIMEOUT':'5'","'-X','-w','--csv'","'ON_ERROR_STOP=1'"):
        assert value in source
    assert 'os.environ.copy' not in source and 'PGPASSWORD' not in source


def test_password_is_private_and_removed(tmp_path,monkeypatch,capsys):
    ca=tmp_path/'ca.pem';ca.write_text('synthetic CA')
    output=tmp_path/'evidence'
    answers=iter(['192.0.2.10',str(ca),'postgres',str(output)])
    monkeypatch.setattr('builtins.input',lambda _:next(answers))
    monkeypatch.setattr(client.getpass,'getpass',lambda _:'SYNTHETIC:secret\\value')
    monkeypatch.setattr(client.shutil,'which',lambda _:'/usr/bin/psql')
    seen=[]
    def run(command,environment,**bounds):
        p=Path(environment['PGPASSFILE']);seen.append(p)
        assert p.stat().st_mode & 0o777==0o600
        assert 'secret' not in repr(command) and 'PGPASSWORD' not in environment
        assert environment['PGSSLMODE']=='verify-full'
        return b'ROLLBACK\n',dict(classification='OBSERVATIONS_REQUIRE_REVIEW')
    monkeypatch.setattr(client,'capture',run)
    assert client.main()==0 and not seen[0].exists()
    exported=''.join(p.read_text() for p in output.iterdir())+capsys.readouterr().out
    assert 'secret' not in exported


@pytest.fixture(scope='module')
def world():
    from tests.e2e_pg_world import disposable_world
    from verification.ingestion_storage.intake_policy import installation_script
    for w in disposable_world():
        # Owner provisioning belongs ONLY to this synthetic disposable fixture.
        with w['connect']('provisioning_migrator') as c: c.execute(installation_script())
        yield w


def observe(connection):
    results=[]
    try:
        for query in statements():
            cur=connection.execute(query)
            if cur.description: results.append(cur.fetchall())
    finally:
        if connection.info.transaction_status:
            connection.execute('ROLLBACK')
    return results


def test_exact_candidate_inventory(world):
    from verification.ingestion_storage.operational_owner import Owner
    expected={n:hashlib.sha256(body.encode()).hexdigest() for n,body in Owner.daily_intake_inventory().items()}
    for name,sha in expected.items(): assert "('%s','%s')"%(name,sha) in SQL
    rows=observe(world['boot'])
    assert len(rows)==10 and len(rows[0])==1 and len(rows[1])==2
    assert len(rows[5])==6 and all(r[3:7]==(True,True,True,True) and r[7]==1 for r in rows[5])
    assert len(rows[6])==12 and len(rows[7])==4 and len(rows[8])==1
    assert rows[0][0][3]=='on'


@pytest.mark.parametrize('case',['missing_function','fingerprint','missing_role','null_control','overflow'])
def test_observations_do_not_hide_incomplete_states(world,case):
    boot=world['boot']
    # Reversible fixture mutation; inspection sees a committed disposable state.
    oid,body=boot.execute("SELECT oid,prosrc FROM pg_proc WHERE proname='ingestion_worker_step'").fetchone()
    old=boot.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    try:
        if case=='missing_function': boot.execute('UPDATE pg_proc SET proname=\'fixture_hidden_worker\' WHERE oid=%s',(oid,))
        if case=='fingerprint': boot.execute('UPDATE pg_proc SET prosrc=prosrc||%s WHERE oid=%s',('\n',oid))
        if case=='missing_role': boot.execute('ALTER ROLE ingestion_effect_login RENAME TO fixture_hidden_effect')
        if case=='null_control': boot.execute("UPDATE ingestion_work_items SET outcome=NULL WHERE key=repeat('0',64)")
        if case=='overflow':
            boot.execute("""INSERT INTO ingestion_work_items
              SELECT (jsonb_populate_record(NULL::ingestion_work_items,
                to_jsonb(t)||jsonb_build_object('key',md5(i::text)||md5(i::text),
                  'state','QUEUED','phase','IDLE'))).*
              FROM ingestion_work_items t CROSS JOIN generate_series(1,202) i
              WHERE t.key=repeat('0',64)""")
        rows=observe(boot)
        if case=='missing_function': assert any(r[0]=='ingestion_worker_step' and r[7]==0 for r in rows[5])
        if case=='fingerprint': assert any(r[0]=='ingestion_worker_step' and r[3] is False for r in rows[5])
        if case=='missing_role': assert len(rows[1])==1 and len(rows[6])==6
        if case=='null_control': assert rows[8][0][0] is None
        if case=='overflow': assert len(rows[9])==201
    finally:
        boot.execute('UPDATE pg_proc SET proname=\'ingestion_worker_step\',prosrc=%s WHERE oid=%s',(body,oid))
        if case=='missing_role': boot.execute('ALTER ROLE fixture_hidden_effect RENAME TO ingestion_effect_login')
        import json
        boot.execute("UPDATE ingestion_work_items SET outcome=%s WHERE key=repeat('0',64)",(json.dumps(old),))
        if case=='overflow': boot.execute("DELETE FROM ingestion_work_items WHERE key<>repeat('0',64)")


def test_permission_denial(world):
    import psycopg
    with world['connect']('ingestion_effect_login') as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege): observe(c)


def test_rls_filtered_empty_is_not_absence(world):
    c=world['boot']
    c.execute('CREATE ROLE fixture_inspection NOSUPERUSER NOBYPASSRLS')
    c.execute('GRANT SELECT ON ingestion_work_items,ingestion_work_attempts TO fixture_inspection')
    try:
        c.execute('SET SESSION AUTHORIZATION fixture_inspection')
        rows=observe(c)
        assert all(r[4] for r in rows[7]) # Observer's RLS applies.
        assert rows[8]==[] # Cannot claim there is no control row.
    finally:
        c.execute('RESET SESSION AUTHORIZATION')
        c.execute('DROP OWNED BY fixture_inspection')
        c.execute('DROP ROLE fixture_inspection')


def test_real_psql_rollback_and_error_session_closure(world,tmp_path):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    executable=shutil.which('psql')
    assert executable, 'hosted PostgreSQL client required'
    info=conninfo_to_dict(os.environ['INGESTION_PROVISIONING_TEST_URL'])
    env={'PGHOST':'127.0.0.1','PGPORT':'5432','PGDATABASE':info['dbname'],
         'PGUSER':info['user'],'PGPASSWORD':info['password'],'PGAPPNAME':'fixed-b-fixture'}
    for text in (SQL,'BEGIN READ ONLY; SELECT 1/0; ROLLBACK;',
                 'BEGIN READ ONLY; SELECT pg_sleep(10); ROLLBACK;'):
        f=tmp_path/'query.sql';f.write_text(text)
        data,status=client.capture([executable,'-X','-w','-v','ON_ERROR_STOP=1','-f',str(f)],env,seconds=2.5)
        if text==SQL: assert status['exit_code']==0 and b'ROLLBACK' in data
        else: assert status['classification']=='INCOMPLETE'
        until=time.monotonic()+2
        while time.monotonic()<until:
            n=world['boot'].execute("SELECT count(*) FROM pg_stat_activity WHERE application_name='fixed-b-fixture'").fetchone()[0]
            if n==0: break
            time.sleep(.025)
        assert n==0 # Actual disposable server observation, not inferred from exit.
