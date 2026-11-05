import copy,json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from app import owner_intake_control as ui
from app.security import access
from verification.ingestion_storage import period07_readonly as p

class Cursor:
 def __init__(self,rows):self.rows=rows
 def fetchall(self):return self.rows
 def fetchone(self):return self.rows[0]

class C:
 def __init__(self):self.calls=[];self.bad=None
 def execute(self,s,params=None):
  self.calls.append(s)
  if s.startswith(('BEGIN ','ROLLBACK')):return Cursor([])
  assert s.lstrip().startswith('SELECT ') and ';' not in s
  if 'grantor::regrole' in s:return Cursor([('bootstrap',True,False,False)] if self.bad!='permission' else [])
  if 'pg_has_role(current_user' in s:return Cursor([(False,False)])
  if 'has_function_privilege(current_user' in s:return Cursor([(True,True)])
  if 'has_function_privilege(' in s:return Cursor([(True,)])
  if "has_schema_privilege(current_user,'public','CREATE WITH GRANT OPTION')" in s:return Cursor([(True,)])
  if 'pg_stat_activity' in s:return Cursor([])
  if 'FROM pg_roles' in s:return Cursor([(0,)])
  if 'SELECT authority,revision' in s:return Cursor([(p.AUTHORITY,p.PERIOD+'-2026-11-02-tameside','CLAIMED','SOURCE_INTENT',2 if self.bad=='fence' else 1,1,None,True,'DISCOVERY','tameside-screening-metadata-five-v1',p.SCOPE)])
  if 'SELECT fence,phase,finished_at,checkpoint,authority' in s:return Cursor([(1,'SOURCE_INTENT',None,None,p.AUTHORITY)])
  if 'SELECT count(*) FROM public.ingestion_work_items' in s:return Cursor([(0,)])
  if 'SELECT encode(sha256(public.ingestion_intake_evidence_read' in s:return Cursor([(p.EVIDENCE[params[2]],)])
  if 'has_table_privilege' in s:return Cursor([(False,)])
  raise AssertionError(s)

@pytest.fixture
def world(monkeypatch):
 c=C()
 marker=dict(id=p.RUN,period=p.PERIOD,state='OPEN',day='2026-11-02',publication_path='docs/design/ingestion-operational-execution-daily-intake/'+p.PERIOD+'/'+p.RUN+'/final/result-before-publication.json')
 ctl=dict(p.STOP6,intake_run=marker,intake_periods={p.PERIOD:dict(execution_binding=p.BINDING,evidence_backend='POSTGRES_PILOT_V1',fixed_window={'start':'2026-10-27','end':'2026-11-02'},max_runs=1,councils={'tameside':{},'manchester':{}},days={'2026-11-02':{'tameside':p.KEY}})},grants={p.AUTHORITY:dict(intake_run=p.RUN,intake_period=p.PERIOD,capture_key=p.KEY,execution_binding=p.BINDING,expires_at=0)})
 old=dict(period=p.PERIOD,status='CLOSED',job={'id':p.JOB},binding={'period':p.PERIOD,'execution_binding':p.BINDING},access={'state':'DATABASE_CLOSURE_ACKNOWLEDGED','render':{'state':'RESTORATION_ACKNOWLEDGED'}},closure_verification={'status':'VERIFIED','authorities_closed':True,'sessions':0},final_service={'suspended':True,'configuration_equal':True,'environment_equal':True},stable_credentials={'version':'STABLE_RESTRICTED_V1','passwords':{r:'synthetic' for r in p.op.ROLES},'verifier_sha256':{r:'a'*64 for r in p.op.ROLES}})
 class DB:
  key='b'*64
  @contextmanager
  def connection(self):yield c
 class J:
  ordinal=1;ciphertext_bytes=100;previous='b'*64
  def __init__(self,db,period):assert period==p.PERIOD
  def load(self):return old
 monkeypatch.setattr(p.pilot,'Journal',J)
 for n in ['identity','inventory','owner_absent','admin_capabilities','retained_cleanup']:monkeypatch.setattr(p.op,n,lambda *a,**kw:None)
 monkeypatch.setattr(p,'verify_inventory',lambda *_:None);monkeypatch.setattr(p.op,'dormant',lambda *a,**kw:None);monkeypatch.setattr(p.op,'control',lambda *_:ctl)
 calls=[]
 class API:
  def call(self,method,path=''):
   assert method=='GET';calls.append(path)
   if not path:return {'id':p.pilot.SERVICE,'ownerId':p.pilot.WORKSPACE,'suspended':'suspended','autoDeploy':'no','serviceDetails':{'plan':'standard','envSpecificDetails':{'startCommand':'/bin/true'}}}
   if 'env-vars' in path:return [{'envVar':{'key':k,'value':'SYNTHETIC_SECRET'}} for k in ['DATABASE_URL','PLANNING_STATUS_VERIFICATION_ENABLED','PLAYWRIGHT_BROWSERS_PATH','PYTHONUNBUFFERED']]
   return []
  def close(self):pass
 monkeypatch.setattr(p.pilot,'service_guard',lambda *_:'guard')
 env={'PROPERTYAIGENT_INTAKE_SOURCE_RELEASE':json.dumps({'execution_binding':p.RELEASE,'tree':'95bfb2677cddfe539b8b69945d870f6c8b5eb62e','branch':'prep/b-timing-pg17-current-20261103'})}
 return c,ctl,old,DB,API,env,calls

def test_success_zero_writes_and_unknowns(world):
 c,ctl,old,DB,API,env,calls=world;before=copy.deepcopy((ctl,old))
 r=p.run(db_factory=DB,render_factory=API,environ=env)
 assert r['status']=='READ_ONLY_CHECKS_PASSED_WITH_UNVERIFIED_CAPABILITIES'
 assert (ctl,old)==before and c.calls[0].endswith('READ ONLY') and c.calls[-1]=='ROLLBACK'
 assert r['capabilities']['exact_archive_inventory']=='UNVERIFIED'
 assert all(r[k]==0 for k in ('database_writes','journal_writes','provider_mutations','job_submissions'))
 assert len(calls)==5 and 'SYNTHETIC_SECRET' not in json.dumps(r)

@pytest.mark.parametrize('drift',['permission','fence','id','generation','stop','successor','release','journal'])
def test_refusal_and_rollback(world,drift):
 c,ctl,old,DB,API,env,calls=world
 if drift in ('permission','fence'):c.bad=drift
 elif drift=='id':ctl['intake_run']['id']='f'*32
 elif drift=='generation':ctl['hard_stop_generation']=7
 elif drift=='stop':ctl['global_stop']={'reason':'UNRELATED'}
 elif drift=='successor':ctl['intake_periods'][p.SUCCESSOR]={}
 elif drift=='release':env['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']='{}'
 else:old['status']='OPEN'
 r=p.run(db_factory=DB,render_factory=API,environ=env)
 assert r['status']=='REFUSED' and 'REFUSED' in r['checks'].values() and c.calls[-1]=='ROLLBACK'

@pytest.mark.parametrize('s',['UPDATE x SET a=1','GRANT x TO y','SELECT 1; COMMIT','COMMIT','SET ROLE x'])
def test_statement_boundary(s):
 with pytest.raises(p.op.Denied):p.ReadOnly(C()).execute(s)

@pytest.mark.parametrize('subject,machine',[('other',False),('owner',True)])
def test_nonowner_never_reads_config_or_starts(monkeypatch,subject,machine):
 monkeypatch.setattr(access,'require_operator',lambda *_:SimpleNamespace(issuer='i',subject=subject,machine=machine))
 monkeypatch.setattr(access,'load_policy',lambda:{'issuer':'i','owner_subject':'owner'})
 monkeypatch.setattr(ui.subprocess,'Popen',lambda *a,**k:pytest.fail('UNAUTHORISED'))
 with pytest.raises(access.AccessDenied):ui.period07_preflight()

def test_owner_fixed_child_and_process_exclusion(monkeypatch):
 monkeypatch.setattr(ui,'require_owner',lambda:None);monkeypatch.setattr(ui,'_process',None)
 monkeypatch.setenv('OPENAI_API_KEY','NEVER_EXPORT');monkeypatch.setenv('DATABASE_URL','SYNTHETIC_SECRET')
 seen=[]
 class Child:
  returncode=0
  def communicate(self,timeout):return (b'{"version":"PERIOD07_READONLY_PREFLIGHT_V1","status":"REFUSED"}',None)
  def poll(self):return 0
 def popen(cmd,**kw):seen.append((cmd,kw));return Child()
 monkeypatch.setattr(ui.subprocess,'Popen',popen)
 assert ui.period07_preflight()['status']=='REFUSED'
 cmd,kw=seen[0];assert cmd[-1]=='scripts.owner_period07_preflight' and 'NEVER_EXPORT' not in str(kw) and 'SYNTHETIC_SECRET' not in str(cmd)
 monkeypatch.setattr(ui,'_process',SimpleNamespace(poll=lambda:None))
 with pytest.raises(ValueError,match='ALREADY_RUNNING'):ui.period07_preflight()
 assert len(seen)==1

def test_no_startup_mutation_and_only_readonly_ui():
 from pathlib import Path
 assert 'startup_prepare()' not in Path('app/ui/server.py').read_text()
 page=Path('app/ui/pages/8_Bounded_Intake.py').read_text()
 assert page.count('disabled=True')==2 and 'period07_preflight()' in page

@pytest.mark.skipif(not __import__('os').environ.get('P07_DISPOSABLE_PG'),reason='CI disposable PostgreSQL only')
def test_postgres_enforces_read_only_transaction(monkeypatch):
 import os,psycopg
 from psycopg.errors import ReadOnlySqlTransaction
 url=os.environ['P07_DISPOSABLE_PG']
 assert url=='postgresql://fixture:fixture@127.0.0.1:5432/p07_readonly'
 with psycopg.connect(url,autocommit=True) as setup:
  setup.execute('CREATE TABLE p07_probe (id integer)')
  setup.execute("CREATE FUNCTION p07_write_probe() RETURNS integer LANGUAGE plpgsql AS $$BEGIN INSERT INTO p07_probe VALUES(1); RETURN 1; END$$")
 connections=[]
 class DB:
  key='synthetic'
  @contextmanager
  def connection(self):
   with psycopg.connect(url,autocommit=True) as c:connections.append(c);yield c
 def forbidden(c):c.execute('SELECT p07_write_probe()')
 monkeypatch.setattr(p.op,'identity',forbidden)
 r=p.run(db_factory=DB,render_factory=lambda:(_ for _ in ()).throw(ValueError()),environ={})
 assert r['transaction']=='ROLLED_BACK' and r['sqlstates']['identity_inventory']=='25006'
 assert connections[0].closed
 with psycopg.connect(url,autocommit=True) as c:assert c.execute('SELECT count(*) FROM p07_probe').fetchone()==(0,)

@pytest.mark.parametrize('failure',[None,'metadata','capability_acl','registrar_acl'])
def test_actual_inventory_through_unchanged_guard(failure):
 import hashlib
 class InventoryConnection:
  def __init__(self):self.calls=[]
  def execute(self,sql,params=None):
   self.calls.append(sql)
   if len(self.calls)==1:
    rows=[(n,hashlib.sha256(body.encode()).hexdigest(),'ingestion_storage_owner',['search_path=pg_catalog'],n!='ingestion_bolton_allowed') for n,body in sorted(p.op.Owner.daily_intake_inventory().items())]
    return Cursor([] if failure=='metadata' else rows)
   if len(self.calls)==2:return Cursor([(False,False,True,True) if failure=='capability_acl' else (True,False,True,True)])
   return Cursor([(True,) if failure=='registrar_acl' else (False,)])
 c=InventoryConnection()
 codes={'metadata':'INTAKE_OWNER_FUNCTION_INVENTORY','capability_acl':'INTAKE_OWNER_CAPABILITY_ACL','registrar_acl':'REGISTRAR_NARROW_ACL'}
 if failure:
  with pytest.raises(p.op.Denied,match=codes[failure]):p.op.inventory(p.ReadOnly(c))
  assert codes[failure] in p.SAFE_CODES
 else:
  p.op.inventory(p.ReadOnly(c));assert len(c.calls)==3
  assert c.calls[1].startswith('SELECT \n')

@pytest.mark.parametrize('field',['revision','workflow_sha256','manifest_sha256','tree','branch'])
@pytest.mark.parametrize('kind',['MISMATCH','MISSING','MALFORMED'])
def test_individual_release_fields(world,field,kind):
 c,ctl,old,DB,API,env,calls=world
 r=json.loads(env['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']);parent=r['execution_binding'] if field in p.RELEASE else r
 if kind=='MISSING':del parent[field]
 elif kind=='MALFORMED':parent[field]={'secret':'DO_NOT_EXPORT'}
 else:parent[field]='other-branch' if field=='branch' else 'a'*len(parent[field])
 env['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']=json.dumps(r)
 result=p.run(db_factory=DB,render_factory=API,environ=env)
 assert result['release_fields'][field]==kind
 assert all(v=='MATCH' for k,v in result['release_fields'].items() if k!=field)
 assert result['refusals']['release']=='P07_RELEASE_BINDING' and result['transaction']=='ROLLED_BACK'
 assert 'DO_NOT_EXPORT' not in json.dumps(result)

@pytest.mark.parametrize('raw,status',[(None,'MISSING'),('bad json','MALFORMED'),('[]','MALFORMED')])
def test_release_document_shape(world,raw,status):
 c,ctl,old,DB,API,env,calls=world
 if raw is None:env.pop('PROPERTYAIGENT_INTAKE_SOURCE_RELEASE')
 else:env['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']=raw
 r=p.run(db_factory=DB,render_factory=API,environ=env)
 assert r['release_document']==status and set(r['release_fields'].values())=={status}

@pytest.mark.parametrize('code',['OWNER_IDENTITY','OWNER_SESSION_VISIBILITY','INTAKE_OWNER_FUNCTION_INVENTORY','INTAKE_OWNER_CAPABILITY_ACL','REGISTRAR_NARROW_ACL','DATABASE_EVIDENCE_FUNCTION_OR_ACL_BINDING','DATABASE_EVIDENCE_TABLE_PRIVILEGES','P07_SELECT_ONLY'])
def test_fixed_inventory_refusal_output(world,monkeypatch,code):
 c,ctl,old,DB,API,env,calls=world
 def refuse(*args):raise p.op.Denied(code)
 monkeypatch.setattr(p.op,'inventory',refuse)
 r=p.run(db_factory=DB,render_factory=API,environ=env)
 assert r['refusals']['identity_inventory']==code and r['transaction']=='ROLLED_BACK'

def test_exact_native_owner_authentication(monkeypatch):
 monkeypatch.setattr(access,'require_operator',lambda *_:SimpleNamespace(issuer='i',subject='owner',machine=False))
 monkeypatch.setattr(access,'load_policy',lambda:{'issuer':'i','owner_subject':'owner'})
 ui.require_owner()

@pytest.mark.parametrize('effective',[True,False,None])
def test_schema_gate_requires_effective_grant_option(effective):
 class SchemaConnection(C):
  def execute(self,sql,params=None):
   if 'has_schema_privilege' in sql:
    self.calls.append(sql)
    assert sql=="SELECT has_schema_privilege(current_user,'public','CREATE WITH GRANT OPTION')"
    return Cursor([(effective,)])
   return super().execute(sql,params)
 c=SchemaConnection()
 # Real permission validator; only unrelated existing role predicates isolated.
 from unittest.mock import patch
 with patch.object(p.op,'owner_absent'),patch.object(p.op,'admin_capabilities'):
  if effective is True:p.permissions(p.ReadOnly(c))
  else:
   with pytest.raises(p.op.Denied,match='P07_SCHEMA_GRANTABILITY'):p.permissions(p.ReadOnly(c))
 assert any('has_schema_privilege' in sql for sql in c.calls)
 assert not any('aclexplode(n.nspacl)' in sql for sql in c.calls)

@pytest.mark.skipif(not __import__('os').environ.get('P07_DISPOSABLE_PG'),reason='CI disposable PostgreSQL only')
def test_postgres_schema_authority_ownership_inheritance_and_set_only():
 import os,psycopg
 url=os.environ['P07_DISPOSABLE_PG']
 assert url=='postgresql://fixture:fixture@127.0.0.1:5432/p07_readonly'
 with psycopg.connect(url,autocommit=True) as c:
  c.execute('BEGIN')
  try:
   for role in ('p07_schema_owner','p07_schema_member','p07_schema_set_only','p07_schema_direct','p07_schema_basic'):
    c.execute('CREATE ROLE '+role+' NOLOGIN')
   c.execute('ALTER SCHEMA public OWNER TO p07_schema_owner')
   c.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
   c.execute('GRANT p07_schema_owner TO p07_schema_member WITH INHERIT TRUE, SET TRUE')
   c.execute('GRANT p07_schema_owner TO p07_schema_set_only WITH INHERIT FALSE, SET TRUE')
   c.execute('GRANT CREATE ON SCHEMA public TO p07_schema_direct WITH GRANT OPTION')
   c.execute('GRANT CREATE ON SCHEMA public TO p07_schema_basic')
   for role,want in [('p07_schema_owner',True),('p07_schema_member',True),('p07_schema_direct',True),('p07_schema_basic',False),('p07_schema_set_only',False)]:
    c.execute('SET LOCAL ROLE '+role)
    got=p.ReadOnly(c).execute("SELECT has_schema_privilege(current_user,'public','CREATE WITH GRANT OPTION')").fetchone()
    assert got==(want,)
    if role in ('p07_schema_owner','p07_schema_member'):
     assert c.execute("SELECT count(*) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a WHERE n.nspname='public' AND a.grantee=current_user::regrole AND a.privilege_type='CREATE' AND a.is_grantable").fetchone()==(0,)
    c.execute('RESET ROLE')
  finally:c.execute('ROLLBACK')
