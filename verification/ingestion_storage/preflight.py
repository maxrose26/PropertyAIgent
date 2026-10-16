"""Single-use catalogue-only production preflight. Never installs or seeds."""
import argparse,hashlib,json,os,re,resource,subprocess,time
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from verification.discovery.route_validation import validate_route
WORKFLOW='.github/workflows/stage4-ingestion-storage-catalogue-once.yml'
AUTHORITY='AUTHORISE_INGESTION_STORAGE_CATALOGUE_ONCE_20261016'
PACKAGE='docs/design/ingestion-readiness-20261016/'
HASHES={'migration.sql':'f790550778172adbfe1db792d20b4c4fb58298e5829f4033f269c8670dc47033','three-items.json':'7883c1a8f99ce3e498fb73911713c3b531d4c73d20fd2524e3c9901e822e7b04'}
ROLES=['ingestion_storage_owner','ingestion_storage_operator','ingestion_worker','ingestion_authority_issuer','ingestion_barrier_releaser','ingestion_worker_login','ingestion_storage_login']
QUERIES={
 'identity':"SELECT current_user,session_user,current_database(),current_setting('server_version_num') AS server_version_num,pg_backend_pid() AS backend_pid,current_setting('transaction_read_only') AS read_only,current_setting('transaction_isolation') AS isolation,current_timestamp::text AS snapshot",
 'roles':"SELECT rolname,rolsuper,rolcreaterole,rolcreatedb,rolcanlogin,rolinherit,rolbypassrls,rolconnlimit FROM pg_roles WHERE rolname=current_user OR rolname IN ('ingestion_storage_owner','ingestion_storage_operator','ingestion_worker','ingestion_authority_issuer','ingestion_barrier_releaser','ingestion_worker_login','ingestion_storage_login') ORDER BY rolname LIMIT 9",
 'privileges':"SELECT has_schema_privilege(current_user,'public','CREATE') AS public_create,has_database_privilege(current_user,current_database(),'CREATE') AS database_create",
 'objects':"SELECT to_regclass('public.ingestion_work_items')::text AS items,to_regclass('public.ingestion_work_attempts')::text AS attempts,to_regprocedure('public.ingestion_seed_storage_test()')::text AS seed,to_regprocedure('public.ingestion_raise_stop(text)')::text AS stop",
 'memberships':"SELECT member.rolname AS member,role.rolname AS role,m.admin_option FROM pg_auth_members m JOIN pg_roles member ON member.oid=m.member JOIN pg_roles role ON role.oid=m.roleid WHERE member.rolname IN ('ingestion_worker_login','ingestion_storage_login') OR role.rolname IN ('ingestion_storage_owner','ingestion_storage_operator','ingestion_worker','ingestion_authority_issuer','ingestion_barrier_releaser') ORDER BY member.rolname,role.rolname LIMIT 41",
 'defaults':"SELECT pg_get_userbyid(d.defaclrole) AS owner,coalesce(n.nspname,'ALL_SCHEMAS') AS namespace,d.defaclobjtype,d.defaclacl::text FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE d.defaclrole=(SELECT oid FROM pg_roles WHERE rolname=current_user) AND (n.nspname='public' OR n.oid IS NULL) ORDER BY namespace,d.defaclobjtype LIMIT 10",
}
def admitted(sha,authority,env):
 return bool(re.fullmatch('[0-9a-f]{40}',sha)) and authority==AUTHORITY and all(env.get(k)==v for k,v in {'GITHUB_SHA':sha,'GITHUB_WORKFLOW_SHA':sha,'GITHUB_REF':'refs/heads/master','GITHUB_REPOSITORY':'maxrose26/PropertyAIgent','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_RUN_NUMBER':'1','GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKFLOW_REF':'maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master'}.items())
def verdict(sessions):
 first=sessions[0];roles={r['rolname']:r for r in first['roles']};blocks=[]
 for name in ('ingestion_worker_login','ingestion_storage_login'):
  r=roles.get(name)
  if not r or not r['rolcanlogin']:blocks.append('EXISTING_RESTRICTED_LOGIN_NOT_AVAILABLE:'+name)
  elif r['rolsuper'] or r['rolbypassrls'] or r['rolcreaterole'] or r['rolcreatedb']:blocks.append('RESTRICTED_LOGIN_HAS_ADMIN_CAPABILITY:'+name)
 if any(first['objects'][0].values()):blocks.append('NAMED_OBJECTS_ALREADY_EXIST_RECONCILE_BEFORE_FIRST_INSTALL')
 if any(r['rolname'] in ROLES[:5] for r in first['roles']):blocks.append('NAMED_CAPABILITY_ROLES_ALREADY_EXIST_RECONCILE_BEFORE_FIRST_INSTALL')
 current=roles.get(first['identity'][0]['current_user'],{})
 if not (current.get('rolsuper') or current.get('rolcreaterole')):blocks.append('MIGRATION_ROLE_CREATION_PRIVILEGE_ABSENT')
 if not first['privileges'][0]['public_create']:blocks.append('MIGRATION_PUBLIC_CREATE_ABSENT')
 # Catalogue cannot prove new-owner transfer or a least-privilege authentication mapping.
 blocks.extend(['DEDICATED_RESTRICTED_LOGIN_SECRET_MAPPING_NOT_ESTABLISHED','NEW_OWNER_TRANSFER_AND_RESTRICTED_MEMBERSHIP_REQUIRE_REVIEW'])
 return {'compatibility':'BLOCKED','blockers':blocks,'pooler_mode':'REGISTERED_SESSION_ROUTE_5432; NOT_INFERRED_FROM_BACKEND_PID','migration_executed':False}
def run(raw,out,engine_factory=create_engine,clock=time.monotonic):
 started=clock();out=Path(out);out.mkdir(exist_ok=False);engine=None;connections=0;attempts=0;statements=0;driver_statements=0;sessions=[];closed=True;disposed=False;phase='ROUTE'
 result={'revision':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),'workflow':WORKFLOW,'workflow_sha256':hashlib.sha256(Path(WORKFLOW).read_bytes()).hexdigest(),'package_hashes':HASHES,'registered_route':{'host':'aws-0-eu-west-2.pooler.supabase.com','port':5432,'database':'postgres','login':'postgres.zcikcfgpblzuzpanpdqd'},'sslmode':'verify-full','prepare_threshold':None,'status':'INTENT_BEFORE_CONNECTION','sessions':sessions,'production_writes':0,'source_calls':0,'application_reads':0,'application_writes':0,'migration_executed':False,'seeding_executed':False}
 def save():
  data=json.dumps(result,sort_keys=True,allow_nan=False).encode();assert len(data)<=32768
  target=out/'result.json.tmp'
  with target.open('wb') as f:f.write(data+b'\n');f.flush();os.fsync(f.fileno())
  os.replace(target,out/'result.json')
 save()
 try:
  url=validate_route(raw)
  ca=Path('/etc/ssl/certs/ca-certificates.crt')
  if not ca.is_file():raise ValueError('SYSTEM_CA_UNAVAILABLE')
  import psycopg
  class AccountedCursor(psycopg.Cursor):
   def execute(self,query,params=None,*,prepare=None,binary=None):
    nonlocal driver_statements
    if driver_statements>=40 or clock()-started>27:raise TimeoutError('DRIVER_STATEMENT_OR_TIME_BOUND')
    driver_statements+=1
    return super().execute(query,params,prepare=prepare,binary=binary)
   def executemany(self,*args,**kwargs):raise ValueError('BULK_EXECUTION_FORBIDDEN')
  phase='ENGINE_WITH_VERIFY_FULL';engine=engine_factory(url,poolclass=NullPool,isolation_level='AUTOCOMMIT',connect_args={'autocommit':True,'connect_timeout':3,'prepare_threshold':None,'sslmode':'verify-full','sslrootcert':str(ca),'cursor_factory':AccountedCursor})
  for index in range(2):
   if clock()-started>20:raise TimeoutError('ACTIVE_DEADLINE')
   attempts+=1;phase='CONNECT_VERIFY_FULL';closed=False
   result.update(status='CONNECTION_INTENT',phase=phase,connection_attempts=attempts,connections=connections,statements=statements,cleanup='UNKNOWN');save()
   with engine.connect() as c:
    connections+=1;closed=False;rolled=False;phase='READ_ONLY_TRANSACTION'
    try:
     def execute(sql):
      nonlocal statements
      if statements>=40 or clock()-started>27:raise TimeoutError('ACTIVE_DEADLINE')
      statements+=1;return c.exec_driver_sql(sql)
     execute('BEGIN READ ONLY')
     for sql in ["SET LOCAL statement_timeout='10s'","SET LOCAL lock_timeout='3s'","SET LOCAL idle_in_transaction_session_timeout='10s'","SET LOCAL timezone='UTC'"]:execute(sql)
     session={};identity=execute(QUERIES['identity']).mappings().all();session['identity']=[dict(x) for x in identity]
     if identity[0]['read_only']!='on' or identity[0]['isolation']!='read committed':raise ValueError('TRANSACTION_CONTRACT')
     session['client_tls']=bool(c.connection.driver_connection.pgconn.ssl_in_use)
     if not session['client_tls']:raise ValueError('CLIENT_TLS_NOT_NEGOTIATED')
     if index==0:
      for name,sql in QUERIES.items():
       if name!='identity':session[name]=[dict(x) for x in execute(sql).mappings().all()]
     sessions.append(session)
    finally:
     statements+=1;c.exec_driver_sql('ROLLBACK');rolled=True
   closed=rolled
   result.update(status='CATALOGUE_CHECKPOINT',connections=connections,statements=statements,cleanup='CLOSED' if closed else 'UNKNOWN');save()
  result.update(verdict(sessions));result['status']='READ_ONLY_CATALOGUE_COMPLETE_BLOCKED'
 except Exception as exc:
  reason='TLS_CERTIFICATE_VERIFICATION_FAILED' if 'certificate verify failed' in str(exc).lower() else 'AUTHENTICATION_FAILED' if 'password authentication failed' in str(exc).lower() else 'CONNECTION_TIMEOUT' if 'timeout' in str(exc).lower() else 'REDACTED_FAILURE'
  result.update(status='PREFLIGHT_FAILED_STOP',phase=phase,reason_code=reason,error_class=type(exc).__name__,sqlstate=getattr(getattr(exc,'orig',exc),'sqlstate',None))
 finally:
  try:
   if engine is not None:engine.dispose();disposed=True
  except Exception:closed=False
  result.update(connection_attempts=attempts,connections=connections,explicit_statements=statements,driver_statements=driver_statements,elapsed_seconds=round(clock()-started,3),peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,cleanup='CLOSED' if closed else 'UNCERTAIN',pool_disposed=disposed)
  if result['peak_rss_bytes']>256*1024**2 or clock()-started>30:result['status']='RESOURCE_STOP'
  save()
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--authority',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 if not admitted(a.sha,a.authority,os.environ):raise SystemExit('PREFLIGHT_NOT_ADMITTED')
 if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise SystemExit('CHECKOUT_NOT_CLEAN_EXACT')
 for path,digest in HASHES.items():
  if hashlib.sha256(Path(PACKAGE+path).read_bytes()).hexdigest()!=digest:raise SystemExit('PACKAGE_CHANGED')
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
 resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**2,2*1024**2))
 raw=os.environ.pop('STORAGE_PREFLIGHT_DATABASE_URL','');r=run(raw,a.output)
 r.update(revision=a.sha,workflow=WORKFLOW,workflow_sha256=hashlib.sha256(Path(WORKFLOW).read_bytes()).hexdigest(),package_hashes=HASHES,run_id=os.environ['GITHUB_RUN_ID'],attempt=1,run_number=1)
 Path(a.output,'result.json').write_text(json.dumps(r,sort_keys=True)+'\n')
 raise SystemExit(0 if r['status']=='READ_ONLY_CATALOGUE_COMPLETE_BLOCKED' and r['cleanup']=='CLOSED' else 1)
if __name__=='__main__':main()
