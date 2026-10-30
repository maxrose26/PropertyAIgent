"""Targeted B supplement: only fixed disposable PostgreSQL, never production."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

import pytest

ROOT = Path('docs/design/daily-intake-20261029')
SQL = (ROOT / 'b-targeted-readonly.sql').read_text()
spec = importlib.util.spec_from_file_location('targeted_b_client', ROOT / 'b-targeted-readonly-client.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)
KEYS = ('3f0dba235de9b9efcd52ef3b281ba8c967491f57824404c695ed2b32fae4c045',
        'e92a8e220bbbbcefb2425d6f97a60920bc447bc1fe097d600ea28e3e9d87588e')
AUTHORITY = 'INGESTION_CHAIN_OLDHAM_FIXTURE'


def statements(text=SQL):
    return [q.strip() for q in re.sub(r'--[^\n]*', '', text).split(';') if q.strip()]


def test_original_preserved_and_client_is_exact_substitution():
    original = (ROOT / 'b-readonly-client.py').read_text()
    assert hashlib.sha256((ROOT / 'b-readonly.sql').read_bytes()).hexdigest() == '131e519e8d69f2b48b951b2dcc45e43dd2967cba66ec3e894b028752506e4997'
    expected = original.replace('b-readonly.sql', 'b-targeted-readonly.sql').replace(
        '131e519e8d69f2b48b951b2dcc45e43dd2967cba66ec3e894b028752506e4997', client.SQL_SHA).replace(
        "'propertyaigent-b-readonly'", "'propertyaigent-b-targeted-readonly'")
    assert expected == (ROOT / 'b-targeted-readonly-client.py').read_text()
    assert hashlib.sha256(SQL.encode()).hexdigest() == client.SQL_SHA
    queries = statements()
    assert len(queries) == 14 and queries[0].endswith('READ ONLY') and queries[-1] == 'ROLLBACK'
    assert not re.search(r'\b(GRANT|SET ROLE|CREATE|INSERT|UPDATE|DELETE)\b',
                         re.sub(r"'[^']*'", '', '\n'.join(queries)), re.I)


@pytest.mark.parametrize('mode', ['normal', 'error', 'deadline', 'overflow'])
def test_inherited_capture_limits_and_remote_uncertainty(mode):
    source = {'normal': 'print("ROLLBACK")', 'error': 'raise SystemExit(2)',
              'deadline': 'import time;time.sleep(10)',
              'overflow': 'import sys;sys.stderr.write("X"*100000)'}[mode]
    started = time.monotonic()
    data, status = client.capture([sys.executable, '-I', '-S', '-c', source], {}, seconds=2.5, ceiling=1024)
    assert time.monotonic() - started < 3 and len(data) <= 1024 and status['client_closed']
    if mode == 'normal': assert status['classification'] == 'OBSERVATIONS_REQUIRE_REVIEW'
    else:
        assert status['classification'] == 'INCOMPLETE'
        assert status['remote_closure'] == 'NOT_ACKNOWLEDGED'


@pytest.fixture(scope='module')
def world():
    from tests.e2e_pg_world import disposable_world
    for w in disposable_world():
        # This installation is fixture provisioning only; no inspection statement mutates.
        with w['connect']('provisioning_migrator') as c:
            c.execute(Path('docs/design/oldham-finite-authority-20261027/installation.sql').read_text())
        w['boot'].execute('CREATE ROLE postgres NOLOGIN NOSUPERUSER NOBYPASSRLS')
        try: yield w
        finally:
            w['boot'].execute('DROP ROLE postgres')


@pytest.fixture
def seeded(world):
    c = world['boot']
    c.execute('DELETE FROM ingestion_work_attempts')
    c.execute("DELETE FROM ingestion_work_items WHERE key<>repeat('0',64)")
    ctl = copy.deepcopy(world['control'])
    ctl.update(global_stop=None, manual_stop=None, last_hard_stop=None, hard_stop_generation=3)
    grant = {'expires_at': time.time()+600, 'keys': [KEYS[0]], 'source_calls': 1, 'writes': 0}
    ctl['grants'] = {AUTHORITY: grant}
    ctl['oldham_allowances'] = {AUTHORITY: {'expires_at': time.time()+300, 'revoked': False,
        'grant_binding': {k:v for k,v in grant.items() if k not in ('source_calls','writes')}}}
    c.execute("UPDATE ingestion_work_items SET outcome=%s WHERE key=repeat('0',64)", (json.dumps(ctl),))
    for key in KEYS:
        patch = dict(key=key, task='DISCOVERY', state='CLAIMED', phase='SOURCE_INTENT',
            fence=7, owner='fixture_owner', authority='fixture_bolton', lease_until=time.time()-100,
            attempt_count=1, checkpoint=None)
        c.execute("""INSERT INTO ingestion_work_items SELECT
          (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(t)||%s::jsonb)).*
          FROM ingestion_work_items t WHERE key=repeat('0',64)""", (json.dumps(patch),))
        c.execute("""INSERT INTO ingestion_work_attempts(work_key,fence,owner,started_at,authority,phase)
          VALUES(%s,7,'fixture_owner',%s,'fixture_bolton','SOURCE_INTENT')""", (key,time.time()-200))
    return world, ctl


def observe(c):
    result = {}
    try:
        for q in statements():
            cursor = c.execute(q)
            if cursor.description:
                names = [v.name for v in cursor.description]
                rows = [dict(zip(names, row)) for row in cursor.fetchall()]
                # All SELECTs have at least one labelled summary or fixed wanted row.
                result[rows[0]['section'] if rows else 'stops'] = rows
    finally:
        if c.info.transaction_status: c.execute('ROLLBACK')
    return result


def test_exact_schema_counts_fences_attempts_and_no_effects(seeded):
    w, ctl = seeded; c = w['boot']
    before = c.execute("SELECT key,to_jsonb(w) FROM ingestion_work_items w ORDER BY key").fetchall()
    r = observe(c)
    assert {k:len(v) for k,v in r.items()} == dict(context=1,items=2,sessions=1,recovery_access=3,functions=2,stops=1,oldham_authorities=1,end=1)
    assert r['context'][0]['read_only'] == 'on' and r['context'][0]['full_stats_visibility']
    assert [v['key'] for v in r['items']] == list(KEYS)
    assert all(v['found'] and v['fence']==7 and v['lease_expired'] and v['matching_attempt_found'] and v['attempt_identity_matches'] for v in r['items'])
    assert all(v['finished_at'] is None and not v['checkpoint_present'] for v in r['items'])
    for v in r['functions']:
        assert v['overload_count']==1
        d=v['definitions'][0]
        assert d['owner']=='ingestion_storage_owner' and d['config']==['search_path=pg_catalog'] and d['definer']
        expected = {'ingestion_oldham_allowed':'091ec5ee578083b0b64431542ec02ff8a39263d345dee6a360dde68d3622900a',
                    'ingestion_recover_abandoned':'9e7f98210c737d6f8f7fae2d98e328261ab9faf31481f041b6f63befa6686f58'}
        assert d['sha256']==expected[v['name']]
    binding=r['stops'][0]['exact_intake_stop_binding']
    assert binding=={k:ctl[k] for k in ('global_stop','manual_stop','last_hard_stop','hard_stop_generation')}
    actual=c.execute("SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(json.dumps(binding),)).fetchone()[0]
    assert actual==r['stops'][0]['stop_binding_pg_jsonb_sha256']
    assert r['oldham_authorities'][0]['records'][0]['binding_matches']
    assert before==c.execute("SELECT key,to_jsonb(w) FROM ingestion_work_items w ORDER BY key").fetchall()
    assert c.info.transaction_status==0


@pytest.mark.parametrize('case',['missing_item','missing_attempt','null_lease','null_owner','identity_mismatch','active_lease'])
def test_missing_and_incomplete_item_observations(seeded,case):
    w,_=seeded;c=w['boot']
    if case=='missing_item':
        c.execute('DELETE FROM ingestion_work_attempts WHERE work_key=%s',(KEYS[0],))
        c.execute('DELETE FROM ingestion_work_items WHERE key=%s',(KEYS[0],))
    elif case=='missing_attempt': c.execute('DELETE FROM ingestion_work_attempts WHERE work_key=%s',(KEYS[0],))
    elif case=='null_lease': c.execute('UPDATE ingestion_work_items SET lease_until=NULL WHERE key=%s',(KEYS[0],))
    elif case=='null_owner': c.execute('UPDATE ingestion_work_items SET owner=NULL WHERE key=%s',(KEYS[0],))
    elif case=='identity_mismatch': c.execute("UPDATE ingestion_work_attempts SET authority='other_fixture' WHERE work_key=%s",(KEYS[0],))
    else:c.execute('UPDATE ingestion_work_items SET lease_until=%s WHERE key=%s',(time.time()+600,KEYS[0]))
    row=observe(c)['items'][0]
    if case=='missing_item': assert not row['found'] and row['fence'] is None
    elif case=='missing_attempt': assert not row['matching_attempt_found'] and row['attempt_identity_matches'] is None
    elif case=='null_lease': assert row['lease_expired'] is None
    elif case=='null_owner': assert row['owner'] is None and row['attempt_identity_matches'] is None
    elif case=='identity_mismatch': assert row['attempt_identity_matches'] is False
    else:assert row['lease_expired'] is False


@pytest.mark.parametrize('case',['missing_role','missing_function','changed_fingerprint','overload'])
def test_catalogue_absence_and_changed_bindings(seeded,case):
    w,_=seeded;c=w['boot']
    oid,body=c.execute("SELECT oid,prosrc FROM pg_proc WHERE proname='ingestion_oldham_allowed'").fetchone()
    try:
        if case=='missing_role':c.execute('ALTER ROLE ingestion_recovery_login RENAME TO fixture_hidden_recovery')
        elif case=='missing_function':c.execute("UPDATE pg_proc SET proname='fixture_hidden_oldham' WHERE oid=%s",(oid,))
        elif case=='changed_fingerprint':c.execute("UPDATE pg_proc SET prosrc=prosrc||E'\\n' WHERE oid=%s",(oid,))
        else:c.execute('CREATE FUNCTION public.ingestion_oldham_allowed(integer) RETURNS boolean LANGUAGE sql AS $$SELECT false$$')
        r=observe(c)
        if case=='missing_role': assert next(v for v in r['recovery_access'] if v['name']=='ingestion_recovery_login')['role_found'] is False
        elif case=='missing_function': assert next(v for v in r['functions'] if v['name']=='ingestion_oldham_allowed')['overload_count']==0
        elif case=='changed_fingerprint':assert next(v for v in r['functions'] if v['name']=='ingestion_oldham_allowed')['definitions'][0]['sha256']!='091ec5ee578083b0b64431542ec02ff8a39263d345dee6a360dde68d3622900a'
        else:assert next(v for v in r['functions'] if v['name']=='ingestion_oldham_allowed')['overload_count']==2
    finally:
        c.execute("UPDATE pg_proc SET proname='ingestion_oldham_allowed',prosrc=%s WHERE oid=%s",(body,oid))
        if case=='missing_role':c.execute('ALTER ROLE fixture_hidden_recovery RENAME TO ingestion_recovery_login')
        if case=='overload':c.execute('DROP FUNCTION public.ingestion_oldham_allowed(integer)')


@pytest.mark.parametrize('case',['missing_global','missing_manual','missing_generation','null_control','oversized','empty_manual'])
def test_stop_semantics_and_complete_exact_binding(seeded,case):
    w,ctl=seeded;c=w['boot']
    if case.startswith('missing_'):ctl.pop({'missing_global':'global_stop','missing_manual':'manual_stop','missing_generation':'hard_stop_generation'}[case])
    elif case=='null_control':ctl=None
    elif case=='oversized':ctl['global_stop']={'reason':'X'*5000}
    else:ctl['manual_stop']=''
    c.execute("UPDATE ingestion_work_items SET outcome=%s WHERE key=repeat('0',64)",(json.dumps(ctl),))
    row=observe(c)['stops'][0]
    if case=='missing_global':assert row['global_field_present'] is False and row['intake_global_block'] is True
    elif case=='missing_manual':assert row['manual_field_present'] is False
    elif case=='missing_generation':assert row['generation_present'] is False and row['exact_intake_stop_binding']['hard_stop_generation']==0
    elif case=='null_control':assert row['control_type']=='null'
    elif case=='oversized':assert row['binding_complete'] is False and row['exact_intake_stop_binding'] is None
    else:assert row['intake_manual_block'] is True


@pytest.mark.parametrize('case',['expired','missing_grant','bad_expiry','string_expiry','bad_binding','overflow'])
def test_oldham_authority_expiry_and_malformed_data(seeded,case):
    w,ctl=seeded;c=w['boot']
    if case=='expired':ctl['oldham_allowances'][AUTHORITY]['expires_at']=0
    elif case=='missing_grant':ctl['grants']={}
    elif case=='bad_expiry':ctl['grants'][AUTHORITY]['expires_at']={'malformed':True}
    elif case=='string_expiry':ctl['oldham_allowances'][AUTHORITY]['expires_at']=str(int(time.time()+600))
    elif case=='bad_binding':ctl['oldham_allowances'][AUTHORITY]['grant_binding']={}
    else:
        ctl['oldham_allowances']={AUTHORITY+str(i):copy.deepcopy(ctl['oldham_allowances'][AUTHORITY]) for i in range(33)}
        ctl['grants']={k:copy.deepcopy(ctl['grants'][AUTHORITY]) for k in ctl['oldham_allowances']}
    c.execute("UPDATE ingestion_work_items SET outcome=%s WHERE key=repeat('0',64)",(json.dumps(ctl),))
    r=observe(c)['oldham_authorities'][0]
    if case=='overflow':assert r['total_count']==33 and r['reported_count']==32 and not r['complete']
    else:
        v=r['records'][0]
        if case=='expired':assert v['allowance_expiry']<r['observed_epoch']
        elif case=='missing_grant':assert not v['grant_present'] and v['binding_matches'] is None
        elif case=='bad_expiry':assert v['grant_expiry'] is None
        elif case=='string_expiry':assert v['allowance_expiry_type']=='string' and v['allowance_expiry'] is None
        else:assert v['binding_matches'] is False


def test_restricted_session_visibility_and_rls_are_explicit(seeded):
    w,_=seeded;c=w['boot']
    c.execute('CREATE ROLE fixture_inspector NOSUPERUSER NOBYPASSRLS')
    c.execute('GRANT USAGE ON SCHEMA public TO fixture_inspector')
    c.execute('GRANT SELECT ON ingestion_work_items,ingestion_work_attempts TO fixture_inspector')
    other=w['connect']('ingestion_effect_login')
    try:
        complete=observe(c)
        assert complete['context'][0]['full_stats_visibility']
        assert any(v['pid']==other.info.backend_pid and v['state']=='idle' for v in complete['sessions'][0]['records'])
        c.execute('SET SESSION AUTHORIZATION fixture_inspector')
        partial=observe(c)
        assert not partial['context'][0]['full_stats_visibility'] and partial['context'][0]['items_rls_active']
        assert all(not v['found'] for v in partial['items']) and partial['stops']==[]
        assert any(v['pid']==other.info.backend_pid and v['state'] is None for v in partial['sessions'][0]['records'])
    finally:
        c.execute('RESET SESSION AUTHORIZATION');other.close()
        c.execute('DROP OWNED BY fixture_inspector');c.execute('DROP ROLE fixture_inspector')


def test_session_inventory_overflow_is_explicit(seeded):
    w,_=seeded;c=w['boot'];connections=[]
    limit=c.execute("SELECT rolconnlimit FROM pg_roles WHERE rolname='ingestion_effect_login'").fetchone()[0]
    c.execute('ALTER ROLE ingestion_effect_login CONNECTION LIMIT 40')
    try:
        connections=[w['connect']('ingestion_effect_login') for _ in range(33)]
        r=observe(c)['sessions'][0]
        assert r['total_count']==33 and r['reported_count']==32 and not r['complete']
    finally:
        for connection in connections:connection.close()
        c.execute('ALTER ROLE ingestion_effect_login CONNECTION LIMIT '+str(limit))


def test_real_psql_readonly_rollback_failure_limits_and_server_closure(seeded,tmp_path):
    from psycopg.conninfo import conninfo_to_dict
    w,_=seeded
    info=conninfo_to_dict(os.environ['INGESTION_PROVISIONING_TEST_URL'])
    env={'PGHOST':'127.0.0.1','PGPORT':'5432','PGDATABASE':info['dbname'],'PGUSER':info['user'],
         'PGPASSWORD':info['password'],'PGAPPNAME':'fixed-b-targeted-fixture',
         'PGOPTIONS':'-c statement_timeout=1500 -c idle_in_transaction_session_timeout=1000'}
    for label,text in [('normal',SQL),('error','BEGIN READ ONLY;SELECT 1/0;ROLLBACK;'),
                       ('deadline','BEGIN READ ONLY;SELECT pg_sleep(10);ROLLBACK;'),
                       ('overflow',"BEGIN READ ONLY;SELECT repeat('X',100000);ROLLBACK;")]:
        path=tmp_path/'fixture.sql';path.write_text(text)
        data,status=client.capture([shutil.which('psql'),'-X','-w','--csv','-v','ON_ERROR_STOP=1','-f',str(path)],env,seconds=2.5)
        if label=='normal':assert status['exit_code']==0 and b'ROLLBACK' in data
        else:
            assert status['classification']=='INCOMPLETE' and status['remote_closure']=='NOT_ACKNOWLEDGED'
            if label=='overflow':assert status['reason']=='OUTPUT_OVERFLOW' and len(data)<=65536
        until=time.monotonic()+2
        while time.monotonic()<until:
            n=w['boot'].execute("SELECT count(*) FROM pg_stat_activity WHERE application_name='fixed-b-targeted-fixture'").fetchone()[0]
            if not n:break
            time.sleep(.025)
        assert n==0  # Disposable server observation, never inferred from local exit.
