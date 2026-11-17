import base64,copy,hashlib,importlib.util,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
from unittest.mock import patch
import pytest
import psycopg
from psycopg import ConnectionInfo
from psycopg.pq import TransactionStatus
BASE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('checkpoint',BASE/'checkpoint-read.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
RAW=b'SYNTHETIC_CIPHERTEXT_NOT_PRODUCTION'
SHA=hashlib.sha256(RAW).hexdigest()
def state():
 return dict(period=m.PERIOD,status='CLOSED',job={'id':'job-dbmq5qutlv9c73bn1rm0'},job_terminal={'status':'failed'},
  binding=dict(execution_binding=m.EXPECTED_BINDING,route='POOLER',hostaddr='192.0.2.1',owner_hostaddr='192.0.2.1',credential_policy='STABLE_RESTRICTED_V1'),
  closure_verification=m.CLOSURE,final_service=m.FINAL,password='MUST_NOT_ESCAPE',original_environment={'SECRET':'MUST_NOT_ESCAPE'},stable_credentials={'verifier_sha256':'SECRET_VERIFIER'})
def row():return dict(ordinal=55,sha256=SHA,ciphertext_bytes=len(RAW),body_base64=base64.b64encode(RAW).decode())
class C:
 def __init__(self,identity=None,result=None,ack=True,close_error=False,rollback_error=False):
  self.calls=[];self.closed=False;self.identity=identity or ['postgres','postgres','postgres','on','10s','3s'];self.result=row() if result is None else result
  self.info=ConnectionInfo(SimpleNamespace(transaction_status=int(TransactionStatus.IDLE if ack else TransactionStatus.UNKNOWN)))
  self.close_error=close_error;self.rollback_error=rollback_error
 def execute(self,sql):
  self.calls.append(sql)
  if sql=='ROLLBACK' and self.rollback_error:raise RuntimeError('MUST_NOT_ESCAPE')
  payload=self.identity if sql==m.IDENTITY else self.result
  return SimpleNamespace(statusmessage='ROLLBACK' if sql=='ROLLBACK' else 'OK',fetchall=lambda:[(json.dumps(payload),)])
 def close(self):
  if self.close_error:raise RuntimeError('MUST_NOT_ESCAPE')
  self.closed=True
class DB:
 def __init__(self,c):self.c=c;self.opens=0
 @contextmanager
 def connection(self):self.opens+=1;yield self.c

def invoke(c,decoder=None,age=0):
 d=DB(c);calls=[]
 def decode(db,raw):calls.append(raw);return state()
 with patch.object(m,'EXPECTED_SHA',SHA):r=m.run(lambda:d,time.monotonic()-age,decoder=decoder or decode)
 assert d.opens<=1 and len(c.calls)<=6
 assert 'MUST_NOT_ESCAPE' not in json.dumps(r)
 assert 'SECRET_VERIFIER' not in json.dumps(r)
 return r,calls

def test_fixed_identity_and_success():
 assert m.EXPECTED_SHA=='a5ba6be74c47eea89bd5068111bf3bc65198c8b4fd54c5036394a2c512f55c52'
 assert m.OWNER_RUN==hashlib.sha256((m.PERIOD+'_owner').encode()).hexdigest()[:32]
 c=C();r,decoded=invoke(c)
 assert r['status']=='READ_COMPLETED_REVIEW_REQUIRED' and decoded==[RAW]
 assert len(c.calls)==6 and c.calls[:3]==m.SETUP and c.calls[-1]=='ROLLBACK'
 assert r['result_bytes_with_metadata_reserve']==4096+r['returned_value_bytes']<=65536
 assert RAW.decode() not in json.dumps(r) and row()['body_base64'] not in json.dumps(r)
 assert r['rollback_acknowledged'] and r['connection_closed']

def test_identity_refusal_precedes_checkpoint():
 c=C(identity=['postgres','unexpected','postgres','on','10s','3s']);r,decoded=invoke(c)
 assert r['reason']=='ACTUAL_IDENTITY_OR_SETTINGS' and not decoded
 assert len(c.calls)==5 and not any('ingestion_intake_owner_state' in s for s in c.calls)

@pytest.mark.parametrize('result',[
 {'refusal':'CHECKPOINT_ROW_COUNT','rows_seen':2}, {'refusal':'CHECKPOINT_BODY_SIZE'},
 {'refusal':'CHECKPOINT_RESULT_CAP'}, {'refusal':'CHECKPOINT_HASH'},
 {**row(),'sha256':'0'*64},{**row(),'body_base64':base64.b64encode(b'wrong').decode()},
 {**row(),'ciphertext_bytes':32769},{**row(),'ordinal':54}])
def test_refusal_before_decoder(result):
 r,decoded=invoke(C(result=result));assert not decoded and r['status']=='STOP_INCOMPLETE_NO_RETRY'
 assert r['rollback_acknowledged'] and r['connection_closed']

@pytest.mark.parametrize('ack,close_error,rollback_error,expected',[(False,False,False,(False,True)),(True,True,False,(True,False)),(True,False,True,(False,True))])
def test_cleanup_is_separate(ack,close_error,rollback_error,expected):
 r,_=invoke(C(ack=ack,close_error=close_error,rollback_error=rollback_error))
 assert (r['rollback_acknowledged'],r['connection_closed'])==expected
 assert r['status']=='STOP_INCOMPLETE_NO_RETRY'

def test_deadline_no_connection():
 c=C();r,decoded=invoke(c,age=16)
 assert r['connections_attempted']==0 and not decoded and not c.calls

def test_projection_minimises_nested_fields():
 s=state();s['binding']['retained_deployment']={'id':'dep-abc','secret':'MUST_NOT_ESCAPE'}
 p=m.projection(s);assert 'MUST_NOT_ESCAPE' not in json.dumps(p)
 assert p['binding']['retained_deployment']=={'id':'dep-abc'}
 assert p['historical_only'] and p['stable_credential_verifier_present']

def test_actual_pinned_decoder_offline(tmp_path):
 pin=Path('/tmp/pa-tam001-owner-inspection')
 assert subprocess.check_output(['git','-C',str(pin),'rev-parse','HEAD'],text=True).strip()==m.PIN
 code='''import ast,base64,importlib.util,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from verification.ingestion_storage.intake_owner_io import Vault
s=importlib.util.spec_from_file_location('reader',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
parts=[]
for file,name,parent in [('intake_owner_io.py','Vault',None),('owner_pilot.py','hydrated_state',None),('owner_pilot.py','_vault','Journal'),('database_evidence.py','canonical',None)]:
 source=(Path('verification/ingestion_storage')/file).read_text();nodes=ast.parse(source).body
 if parent:nodes=next(n for n in nodes if isinstance(n,ast.ClassDef) and n.name==parent).body
 node=next(n for n in nodes if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==name)
 parts.append(ast.get_source_segment(source,node))
assert base64.b64decode(m.DECODER_SOURCE).decode()==(chr(10)*2).join(parts)+chr(10)
with tempfile.TemporaryDirectory() as folder:
 p=Path(folder)/'fixture';v=Vault(p,'disposable-only-fixture-key-12345',create=True);v.save({'period':m.PERIOD,'fixture':True})
 assert m.decode(SimpleNamespace(key='disposable-only-fixture-key-12345'),p.read_bytes())=={'period':m.PERIOD,'fixture':True}
from verification.ingestion_storage.owner_pilot import serialized_state
value={'period':m.PERIOD,'cleanup_reserve':{'version':'CLEANUP_RESERVE_V1'},'profile':{'fixture':'x'*5000}}
with tempfile.TemporaryDirectory() as folder:
 p=Path(folder)/'fixture';v=Vault(p,'disposable-only-fixture-key-12345',create=True);v.save(serialized_state(value))
 assert m.decode(SimpleNamespace(key='disposable-only-fixture-key-12345'),p.read_bytes())==value
print('PINNED_DECODER_OFFLINE_PASS')'''
 r=subprocess.run([sys.executable,'-c',code,str((BASE/'checkpoint-read.py').resolve())],cwd=pin,env={**os.environ,'PYTHONPATH':str(pin),'DATABASE_URL':'sqlite:///:memory:'},capture_output=True,text=True,timeout=10)
 assert r.returncode==0,r.stderr
 assert r.stdout.strip()=='PINNED_DECODER_OFFLINE_PASS'

@pytest.fixture
def pg():
 url=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
 if not url:pytest.skip('fixed disposable PostgreSQL required')
 from psycopg.conninfo import conninfo_to_dict
 info=conninfo_to_dict(url);assert (info['host'],info['port'],info['dbname'])==('127.0.0.1','5432','ingestion_provisioning_test')
 with psycopg.connect(url,autocommit=True) as c:
  c.execute('CREATE TEMP TABLE checkpoint_fixture(ordinal int,body bytea,sha256 text)')
  c.execute('CREATE FUNCTION pg_temp.checkpoint_fixture(text,text,text,bytea) RETURNS TABLE(ordinal int,body bytea,sha256 text) LANGUAGE SQL AS $$ SELECT * FROM pg_temp.checkpoint_fixture $$')
  yield c

def server(c,remaining=60000):
 sql=m.checkpoint_sql(remaining).replace('public.ingestion_intake_owner_state','pg_temp.checkpoint_fixture')
 value=c.execute(sql).fetchone()[0]
 assert len(value.encode())<=remaining
 return json.loads(value)

def test_pg_duplicate_never_returns_bodies(pg):
 for size in (1,1000000):
  pg.execute('TRUNCATE checkpoint_fixture')
  pg.execute("INSERT INTO checkpoint_fixture VALUES(55,%s,%s),(55,%s,%s)",(b'x'*size,'0'*64,b'y'*size,'0'*64))
  assert server(pg)=={'refusal':'CHECKPOINT_ROW_COUNT','rows_seen':2}

def test_pg_oversize_hash_and_metadata_cap(pg):
 pg.execute('INSERT INTO checkpoint_fixture VALUES(55,%s,%s)',(b'x'*32769,'0'*64))
 assert server(pg)=={'refusal':'CHECKPOINT_BODY_SIZE'}
 pg.execute('TRUNCATE checkpoint_fixture');pg.execute('INSERT INTO checkpoint_fixture VALUES(55,%s,%s)',(RAW,'0'*64))
 assert server(pg)=={'refusal':'CHECKPOINT_HASH'}
 pg.execute('UPDATE checkpoint_fixture SET sha256=%s',(SHA,))
 with patch.object(m,'EXPECTED_SHA',SHA):
  result=server(pg);assert result['body_base64']==row()['body_base64']
  assert server(pg,128)=={'refusal':'CHECKPOINT_RESULT_CAP'}
 # Maximum permitted ciphertext fits after base64 expansion and all JSON metadata.
 raw=b'x'*32768;sha=hashlib.sha256(raw).hexdigest()
 pg.execute('UPDATE checkpoint_fixture SET body=%s,sha256=%s',(raw,sha))
 with patch.object(m,'EXPECTED_SHA',sha):
  result=server(pg,65536-4096-1024)
  assert len(base64.b64decode(result['body_base64']))==32768

def test_work_deadline_still_attempts_cleanup():
 class Slow(C):
  def execute(self,sql):
   if sql==m.IDENTITY:time.sleep(30)
   return super().execute(sql)
 c=Slow();began=time.monotonic();r,decoded=invoke(c,age=14)
 assert time.monotonic()-began<2 and not decoded
 assert r['reason']=='OVERALL_DEADLINE' and r['rollback_acknowledged'] and r['connection_closed']

def test_decoder_failure_does_not_log_exception(capsys):
 def decoder(*_):raise RuntimeError('MUST_NOT_ESCAPE')
 r,_=invoke(C(),decoder=decoder)
 assert r['reason']=='CONFIGURATION_DATABASE_OR_DECODE_REFUSAL'
 assert capsys.readouterr()==('','')
