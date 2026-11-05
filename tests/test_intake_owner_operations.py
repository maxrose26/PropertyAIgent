"""Focused MOCK validation only; never represents PostgreSQL execution."""
import copy,hashlib,json,subprocess,time
from pathlib import Path
import pytest
from verification.ingestion_storage import intake_owner as op,intake_owner_operations as extra,intake_owner_client as client
from verification.ingestion_storage.intake_owner_io import Vault
from verification.ingestion_storage.operational_publication import canonical
TOKEN='ghs_'+'PrivateSyntheticSentinel0123456789'*2
KEY='synthetic passphrase above24 chars'
def inputs(tmp_path):
 b=dict(version='FINITE_INTAKE_OWNER_V1',period='operations-fixture',route='POOLER',hostaddr='192.0.2.1',owner_hostaddr='192.0.2.2',execution_binding=copy.deepcopy(op.APPLICATION_BINDING),accepted_stop=copy.deepcopy(op.ACCEPTED_STOP),valid_until=time.time()+1800,publication_valid_until=time.time()+1700,publication_scope=dict(repository='maxrose26/PropertyAIgent',contents='write',metadata='read'),period_vault_path=str(tmp_path/'period.vault'),publication_vault_path=str(tmp_path/'token.vault'))
 profile=dict(mode='render-intake-v1',service_id='crn-d9sv93vavr4c73f98rb0',revision=op.APPLICATION_BINDING['revision'],browser_path='/fixture/browser',browser_sha256='a'*64,aggregate_bytes=2147483648,source_rss_bytes=1073741824,controller_rss_bytes=268435456,reserve_bytes=536870912,source_seconds=75)
 b['render_profile']=profile
 p=dict(expires_at=b['publication_valid_until'],max_runs=1,overlap_days=7,councils=copy.deepcopy(extra.COUNCILS),expected_stop=copy.deepcopy(op.ACCEPTED_STOP),execution_binding=copy.deepcopy(op.APPLICATION_BINDING),test_evidence=False,screening_config=extra.SCREENING,hostaddr=b['hostaddr'],route=b['route'],render_profile=profile)
 b['period_policy_sha256']=hashlib.sha256(canonical(p)).hexdigest();return b,p
class Cursor:
 pgresult=None
 def __init__(self,rows=()):self.rows=list(rows);self.description=bool(rows)
 def fetchall(self):return self.rows
 def fetchone(self):return self.rows[0]
class SQL:
 def __init__(self):
  self.closed=False;self.ctl=dict(copy.deepcopy(op.ACCEPTED_STOP),intake_periods={});self.members=[(extra.ISSUER,'postgres','fixture_bootstrap',True,False,False)];self.tx=None;self.statements=[];self.fault=None;self.commits=0;self.inventory=True
 def execute(self,s,params=None):
  self.statements.append(s)
  if s=='BEGIN':self.tx=copy.deepcopy((self.ctl,self.members))
  elif s=='COMMIT':
   self.tx=None;self.commits+=1
   if self.fault=='commit_lost':raise RuntimeError('synthetic lost reply')
   if self.fault=='post_commit':self.ctl['drift']=True
  elif s=='ROLLBACK':
   if self.tx:self.ctl,self.members=self.tx;self.tx=None
  elif s==op.MEMBERS:return Cursor(self.members)
  elif s==extra.ISSUER_MEMBERS:return Cursor([(m[2],*m[3:]) for m in self.members if m[0]==extra.ISSUER])
  elif s==extra.FLAGS:return Cursor([(any(m[4] for m in self.members if m[0]==extra.ISSUER),any(m[5] for m in self.members if m[0]==extra.ISSUER))])
  elif s.startswith('GRANT ingestion_barrier_releaser'):self.members.append((extra.ISSUER,'postgres','postgres',self.fault=='temporary',True,True))
  elif s.startswith('REVOKE ingestion_barrier_releaser'):
   self.members=[m for m in self.members if m[2]!='postgres']
   if self.fault=='privilege':self.members.append(('unrelated','postgres','postgres',False,False,True))
  elif s=='SELECT public.ingestion_register_bolton_exception(%s::jsonb)':
   if self.fault=='sql':raise RuntimeError('synthetic SQL failure')
   x=json.loads(params[0]);entry=dict(x['policy'],registered_at=time.time(),days={});self.ctl['intake_periods'][x['period']]=entry;return Cursor([(entry,)])
  elif 'extract(epoch FROM clock_timestamp())' in s:return Cursor([(time.time(),)])
  elif s.startswith('SET LOCAL'):pass
  else:raise AssertionError('Unexpected fixed query')
  return Cursor()
 def close(self):
  if self.tx:self.ctl,self.members=self.tx;self.tx=None
  self.closed=True
@pytest.fixture
def mocked_sql(monkeypatch):
 c=SQL();monkeypatch.setattr(extra.Owner,'verify_installed',lambda self,c:op.require(c.inventory,'INTAKE_OWNER_FUNCTION_INVENTORY'))
 for n in ('identity','owner_absent','retained_cleanup','no_hazards'):monkeypatch.setattr(op,n,lambda *a,**kw:None)
 monkeypatch.setattr(op,'inventory',lambda c:op.require(c.inventory,'INTAKE_OWNER_FUNCTION_INVENTORY'))
 monkeypatch.setattr(op,'dormant',lambda c,**kw:list(c.members));monkeypatch.setattr(op,'control',lambda c:copy.deepcopy(c.ctl))
 monkeypatch.setattr(op,'ledger_sha',lambda c,replacement=None:hashlib.sha256(canonical(dict(control=c.ctl if replacement is None else replacement,other='unchanged'))).hexdigest());return c

def issue(c,b,p):
 saved=[];state=dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p)
 return state,saved,lambda:extra.issue_period(c,b,p,state,lambda x:saved.append(copy.deepcopy(x)))
def test_period_success_existing_primitive(mocked_sql,tmp_path):
 c=mocked_sql;b,p=inputs(tmp_path);prior=list(c.members);state,saved,call=issue(c,b,p);r=call()
 assert r['connections']==1 and c.commits==1 and c.closed and c.members==prior
 assert [x['state'] for x in saved]==['COMMIT_INTENT_NO_RETRY','COMMIT_ACKNOWLEDGED']
 assert c.statements.index('REVOKE ingestion_barrier_releaser FROM CURRENT_USER GRANTED BY CURRENT_USER')<c.statements.index('COMMIT')
@pytest.mark.parametrize('field,value',[('max_runs',2),('max_runs',True),('test_evidence',True),('screening_config','b'*64),('route','DIRECT'),('expires_at',0),('councils',{}),('expected_stop',op.STOP)])
def test_wrong_policy(tmp_path,field,value):
 b,p=inputs(tmp_path);p[field]=value;b['period_policy_sha256']=hashlib.sha256(canonical(p)).hexdigest()
 with pytest.raises(op.Denied):extra.validate_policy(b,p)
@pytest.mark.parametrize('fault',['stop','inventory','missing','privilege','sql','commit_lost','post_commit'])
def test_period_faults(mocked_sql,tmp_path,fault):
 c=mocked_sql;b,p=inputs(tmp_path)
 if fault=='stop':c.ctl.update(op.STOP)
 elif fault=='inventory':c.inventory=False
 elif fault=='missing':c.members=[]
 else:c.fault=fault
 prior=copy.deepcopy((c.ctl,c.members));state,saved,call=issue(c,b,p)
 with pytest.raises(Exception):call()
 assert c.closed
 if fault in ('commit_lost','post_commit'):assert c.commits==1 and b['period'] in c.ctl['intake_periods'] and state['state']=='COMMIT_INTENT_NO_RETRY'
 else:assert (c.ctl,c.members)==prior and c.commits==0
 if fault in ('stop','inventory','missing'):assert not any(s.startswith('GRANT ') for s in c.statements)
@pytest.mark.parametrize('fault',['admin','inherit','set','grantor'])
def test_issuer_options(mocked_sql,tmp_path,fault):
 c=mocked_sql;b,p=inputs(tmp_path);m=list(c.members[0]);m[{'admin':3,'inherit':4,'set':5,'grantor':2}[fault]]={'admin':False,'inherit':True,'set':True,'grantor':'postgres'}[fault];c.members=[tuple(m)];_,_,call=issue(c,b,p)
 with pytest.raises(op.Denied,match='PERIOD_EXISTING_ISSUER_ADMIN_ONLY'):call()
 assert not any(s.startswith('GRANT ') for s in c.statements)
@pytest.mark.parametrize('stage',[None,'ACTIVATION_FAILED','PUT_INTENT_NO_RETRY','RESTORE_INTENT_NO_RETRY'])
def test_independent_revocation(tmp_path,stage):
 b,_=inputs(tmp_path);saved=[];extra.token_arm(b,TOKEN,lambda x:saved.append(copy.deepcopy(x)));state=saved[-1];state['legacy_state']=stage;calls=[]
 def runner(command,**kw):
  assert saved[-1]['state']=='REVOKE_INTENT_NO_RETRY';calls.append(command)
  assert TOKEN not in repr(command) and command==['gh','api','--method','DELETE','installation/token','--include','--silent']
  return subprocess.CompletedProcess(command,0,b'HTTP/2.0 204 No Content\r\n',b'')
 r=extra.token_revoke(b,state,lambda x:saved.append(copy.deepcopy(x)),runner=runner)
 assert r['restoration_required'] is False and len(calls)==1 and saved[-1]['token']==''
 with pytest.raises(op.Denied):extra.token_revoke(b,state,lambda _:None,runner=runner)
 assert len(calls)==1
@pytest.mark.parametrize('reply',[b'HTTP/2.0 200 OK\n',b'',b'HTTP/2.0 204 OK\nHTTP/2.0 204 OK\n',None])
def test_uncertain_revoke_never_repeats(tmp_path,reply):
 b,_=inputs(tmp_path);saved=[];extra.token_arm(b,TOKEN,lambda x:saved.append(copy.deepcopy(x)));state=saved[-1];calls=[]
 def runner(command,**kw):
  calls.append(command)
  if reply is None:raise RuntimeError(TOKEN)
  return subprocess.CompletedProcess(command,0,reply,b'')
 with pytest.raises(op.Denied,match='TOKEN_REVOKE_ACK_UNCERTAIN'):extra.token_revoke(b,state,lambda x:saved.append(copy.deepcopy(x)),runner=runner)
 with pytest.raises(op.Denied):extra.token_revoke(b,saved[-1],lambda _:None,runner=runner)
 assert len(calls)==1
@pytest.mark.parametrize('token',['ghp_'+'x'*40,'github_pat_'+'x'*40,'jwt.synthetic.admin','ghs_short',TOKEN+'\n'])
def test_admin_tokens_refused(tmp_path,token):
 b,_=inputs(tmp_path)
 with pytest.raises(op.Denied):extra.token_arm(b,token,lambda _:pytest.fail('must not save'))
def test_intent_save_failure_no_delete(tmp_path):
 b,_=inputs(tmp_path);saved=[];extra.token_arm(b,TOKEN,lambda x:saved.append(copy.deepcopy(x)))
 def fail(_):raise RuntimeError('synthetic disk failure')
 with pytest.raises(RuntimeError):extra.token_revoke(b,saved[-1],fail,runner=lambda *a,**k:pytest.fail('no DELETE'))
def test_worker_vault_binding_no_database(monkeypatch,tmp_path):
 import psycopg
 b,_=inputs(tmp_path);monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:pytest.fail('no database'))
 r=client.worker('publication-arm',b,dict(vault_key=KEY,publication_token=TOKEN),b['publication_vault_path'],{});f=Path(b['publication_vault_path'])
 assert TOKEN.encode() not in f.read_bytes() and f.stat().st_mode&0o777==0o600 and r['provider_calls']==0
 with pytest.raises(FileExistsError):client.worker('publication-arm',b,dict(vault_key=KEY,publication_token=TOKEN),str(f),{})
 state=Vault(f,KEY).load();assert extra.token_load(b,state)==TOKEN
 other=copy.deepcopy(b);other['period']='different'
 with pytest.raises(op.Denied):extra.token_load(other,state)
def test_diagnostics_bounded_known_unknown():
 for phase in ('period','publication-arm','publication-revoke'):
  known=client.failure_output(phase,op.Denied('TOKEN_REVOKE_ACK_UNCERTAIN'));unknown=client.failure_output(phase,RuntimeError(TOKEN*10000))
  assert 'TOKEN_REVOKE_ACK_UNCERTAIN' in known and 'UNKNOWN_FAILURE' in unknown and TOKEN not in known+unknown and len(unknown.encode())<client.DIAGNOSTIC_BYTES

def test_concurrent_stale_vault_cannot_issue_second_delete(tmp_path):
 b,_=inputs(tmp_path);saved=[];extra.token_arm(b,TOKEN,lambda x:saved.append(copy.deepcopy(x)))
 first=copy.deepcopy(saved[-1]);stale=copy.deepcopy(first);calls=[]
 def runner(command,**kw):calls.append(command);return subprocess.CompletedProcess(command,0,b'HTTP/2.0 204 OK\n',b'')
 extra.token_revoke(b,first,lambda _:None,runner=runner)
 with pytest.raises(FileExistsError):extra.token_revoke(b,stale,lambda _:None,runner=runner)
 assert len(calls)==1 and Path(b['publication_vault_path']+'.revoke-consumed').stat().st_mode&0o777==0o600

def test_worker_period_wrong_policy_never_connects(monkeypatch,tmp_path):
 import psycopg
 b,p=inputs(tmp_path);p['max_runs']=2
 monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:pytest.fail('no database on wrong policy'))
 with pytest.raises(op.Denied):client.worker('period',b,dict(vault_key=KEY),b['period_vault_path'],p)

def test_wrong_operation_vault_path_refuses(tmp_path):
 b,_=inputs(tmp_path)
 with pytest.raises(op.Denied,match='OPERATION_VAULT_BINDING'):extra.private_path(b,'publication_vault_path',str(tmp_path/'other'))

def test_legacy_close_cannot_duplicate_independent_revocation(tmp_path):
 b,_=inputs(tmp_path)
 with pytest.raises(op.Denied,match='INDEPENDENT_PUBLICATION_REVOKE_REQUIRED'):client.worker('publication-close',b,{},'/unused',{})

def test_worker_revoke_uses_hidden_exact_token_no_db_or_render(monkeypatch,tmp_path):
 import psycopg
 from verification.ingestion_storage import intake_owner_io
 b,_=inputs(tmp_path);client.worker('publication-arm',b,dict(vault_key=KEY,publication_token=TOKEN),b['publication_vault_path'],{})
 monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:pytest.fail('no database'))
 monkeypatch.setattr(intake_owner_io,'Render',lambda *a,**kw:pytest.fail('no Render'))
 calls=[]
 def run(command,**kw):
  calls.append(command);assert kw['env']['GH_TOKEN']==TOKEN and TOKEN not in repr(command)
  return subprocess.CompletedProcess(command,0,b'HTTP/2.0 204 No Content\n',b'')
 monkeypatch.setattr(extra.subprocess,'run',run)
 r=client.worker('publication-revoke',b,dict(vault_key=KEY),b['publication_vault_path'],{})
 assert len(calls)==1 and r['database_required'] is False
 assert Vault(b['publication_vault_path'],KEY).load()['state']=='REVOKED_ACKNOWLEDGED'

def test_period_worker_one_connection_pinned_tls_and_armed_vault(monkeypatch,tmp_path):
 import psycopg
 from verification.ingestion_storage import tls_trust
 b,p=inputs(tmp_path);calls=[]
 class Connection:
  def __enter__(self):return self
  def __exit__(self,*args):pass
 def connect(**kw):calls.append(kw);return Connection()
 monkeypatch.setattr(psycopg,'connect',connect);monkeypatch.setattr(tls_trust,'verified_trust',lambda:('/fixture/pinned-ca',{}))
 def issued(c,binding,policy,state,save):
  assert state['state']=='ARMED_NO_RETRY' and Vault(b['period_vault_path'],KEY).load()['policy']==p
  return dict(test='NO_REAL_DATABASE')
 monkeypatch.setattr(extra,'issue_period',issued)
 client.worker('period',b,dict(vault_key=KEY,owner_password='SYNTHETIC_PRIVATE'),b['period_vault_path'],p)
 assert len(calls)==1 and calls[0]['sslmode']=='verify-full' and calls[0]['sslrootcert']=='/fixture/pinned-ca' and calls[0]['hostaddr']==b['owner_hostaddr'] and calls[0]['connect_timeout']==5
 with pytest.raises(FileExistsError):client.worker('period',b,dict(vault_key=KEY,owner_password='SYNTHETIC_PRIVATE'),b['period_vault_path'],p)
 assert len(calls)==1


def test_period_unexpected_temporary_admin_refuses_before_registration(mocked_sql,tmp_path):
 c=mocked_sql;b,p=inputs(tmp_path);before=copy.deepcopy((c.ctl,c.members));c.fault='temporary';_,_,call=issue(c,b,p)
 with pytest.raises(op.Denied,match='PERIOD_EXACT_TEMPORARY_ISSUER'):call()
 assert (c.ctl,c.members)==before and not any('ingestion_register_bolton_exception' in x for x in c.statements)
