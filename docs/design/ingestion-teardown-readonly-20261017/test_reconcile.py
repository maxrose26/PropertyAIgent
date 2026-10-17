import importlib.util,json,multiprocessing,sys
from pathlib import Path
import pytest
from pglast import parse_sql,ast

spec=importlib.util.spec_from_file_location('read_only_reconcile',Path(__file__).with_name('reconcile.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def base():
    return dict(roles=[dict(name=n,can_login=False,superuser=False,create_role=False,create_db=False,bypass_rls=False,replication=False) for n in r.ROLES],password_removal_booleans=[(n,True) for n in r.ROLES],membership_count=0,session_count=0,temporary_secret_names={n:'ABSENT' for n in r.NAMES})

def test_queries_parse_as_single_select_without_material_projection():
    import re
    for sql in (r.QUERY,r.PASSWORD_QUERY):
        i=iter(range(1,8));nodes=parse_sql(re.sub('%s',lambda _: '$'+str(next(i)),sql))
        assert len(nodes)==1 and isinstance(nodes[0].stmt,ast.SelectStmt)
    assert 'rolpassword IS NULL' in r.PASSWORD_QUERY
    assert r.QUERY.count('%s')==5 and 'rolpassword' not in r.QUERY.replace("'rolpassword'",'')

@pytest.mark.parametrize('change,expected',[
    ({},'OBSERVED_DISABLED_AND_SECRETS_ABSENT'),
    ({'password_removal_booleans':None},'UNKNOWN'),
    ({'roles':[]},'UNKNOWN'),
    ({'session_count':1},'DATABASE_CLEANUP_INCOMPLETE'),
    ({'membership_count':1},'DATABASE_CLEANUP_INCOMPLETE'),
    ({'password_removal_booleans':[(r.ROLES[0],False),(r.ROLES[1],True)]},'DATABASE_CLEANUP_INCOMPLETE'),
    ({'temporary_secret_names':dict.fromkeys(r.NAMES,'PRESENT')},'DATABASE_ACCESS_DISABLED_SECRET_CLEANUP_PENDING'),
    ({'temporary_secret_names':dict.fromkeys(r.NAMES,'UNKNOWN')},'DATABASE_ACCESS_DISABLED_SECRET_STATE_UNKNOWN')])
def test_truthful_verdict(change,expected):assert r.access_verdict({**base(),**change})==expected

def test_latch_exclusive_and_chain(tmp_path):
    p=tmp_path/'once';j=r.Journal(p);j.append('consumed',{'phase':'READ_ONLY'});j.file.close()
    assert len(r.check_chain((p/'events.jsonl').read_bytes()))==1
    with pytest.raises(FileExistsError):r.Journal(p)
    raw=(p/'events.jsonl').read_bytes().replace(b'READ_ONLY',b'ALTERED')
    with pytest.raises(ValueError):r.check_chain(raw)

def run_observe(pipe,allowed,metadata):
    import os,time
    import psycopg
    from verification.ingestion_storage import credential_mapping as mapping
    class Group:
        def enter(self):pass
    class Cursor:
        def __init__(self,value):self.value=value
        def fetchone(self):return (self.value,)
        def fetchall(self):return self.value
    class Connection:
        closed=False
        def execute(self,sql,args=None):
            if sql==r.QUERY:
                x=base();x.pop('password_removal_booleans');x.pop('temporary_secret_names')
                x.update(current_user='postgres',session_user='postgres',migration_flags=dict(superuser=False,create_role=True,create_db=True,bypass_rls=True),password_boolean_read_permitted=allowed,memberships=[],sessions=[])
                return Cursor(x)
            if sql==r.PASSWORD_QUERY:
                assert allowed
                return Cursor([(n,True) for n in r.ROLES])
            assert sql in ('BEGIN READ ONLY',"SET LOCAL statement_timeout='2s'","SET LOCAL idle_in_transaction_session_timeout='3s'",'ROLLBACK')
            return Cursor(None)
        def close(self):self.closed=True
    def connect(**kw):
        assert kw['sslmode']=='verify-full' and kw['hostaddr']=='127.0.0.1'
        return Connection()
    psycopg.connect=connect
    # Actual Linux gh process/API parsing; only auth/host/TLS transport fixture.
    r.subprocess=__import__('types').SimpleNamespace(PIPE=-1,DEVNULL=-3,run=lambda command,**kwargs:__import__('types').SimpleNamespace(returncode=0,stdout=metadata(command),stderr=b''))
    r.observe(Group(),pipe,'postgresql://postgres.zcikcfgpblzuzpanpdqd:DISPOSABLE_ONLY@aws-0-eu-west-2.pooler.supabase.com:5432/postgres',{'selected_address':'127.0.0.1'},time.monotonic())

@pytest.mark.parametrize('allowed,commands',[(True,6),(False,5)])
def test_actual_gh_observation_with_synthetic_driver(allowed,commands,real_gh_store):
    metadata,secret,ciphertexts,requests=real_gh_store
    ctx=multiprocessing.get_context('fork');parent,child=ctx.Pipe()
    p=ctx.Process(target=run_observe,args=(child,allowed,metadata));p.start();child.close();events=[]
    try:
        while p.is_alive() or parent.poll():
            if parent.poll(.1):
                try:e=json.loads(parent.recv_bytes(32768))
                except EOFError:break
                events.append(e);parent.send_bytes(b'DURABLE')
        p.join(timeout=2)
        assert p.exitcode==0
        result=next(e['payload'] for e in events if e['event']=='recorded_observation')
        assert result['commands']==commands and result['connection_attempts']==1 and result['error'] is None
        assert result['results']['temporary_secret_names']==dict.fromkeys(r.NAMES,'ABSENT')
        assert (result['results']['password_removal_booleans'] is not None)==allowed
        assert events[-1]['event']=='worker_closed'
        assert all(method=='GET' for method,path in requests) and not ciphertexts
    finally:
        if p.is_alive():p.kill();p.join()
        parent.close()

sys.path.insert(0,str(Path('/workspace/scratch/bfed03f1aa09/storage-finite-controller/tests')))
from storage_gh_fixture import real_gh_store
