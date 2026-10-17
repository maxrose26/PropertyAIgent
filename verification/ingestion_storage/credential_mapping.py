"""Exact finite owner-local mapping; accepted verifier-retention risk, not redaction.

Never print raw exceptions, connection strings, passwords, SCRAM verifiers or
GitHub CLI output. The CLI handles encryption to the existing environment key.
Python cannot guarantee erasure of strings from process memory. No files/core
are produced by this helper. Preserve the previously blocked entrypoint in git
history; the old provider-attestation flag does not admit this method.
"""
import argparse,getpass,hashlib,json,os,secrets,socket,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import quote
from psycopg import sql
from .tls_trust import verified_trust,owned_resources
from verification.discovery.route_validation import validate_route
REPO='github.com/maxrose26/PropertyAIgent'
ENVIRONMENT='stage4-production-canary'
MAPPINGS={'ingestion_worker_login':'INGESTION_WORKER_DATABASE_URL','ingestion_storage_login':'INGESTION_STORAGE_DATABASE_URL'}
AUTHORITY='AUTHORISE_RESTRICTED_INGESTION_CREDENTIAL_MAPPING_ONCE_20261016'
CONTROLLER='verification.ingestion_storage.credential_mapping'
RISK='ACCEPT_POSSIBLE_PROVIDER_SCRAM_VERIFIER_RETENTION_TWO_LOGINS_ONCE'
LIMITS={'supervised_seconds':240,'connection_attempts':13,'worker_rss_bytes':256*1024**2,'exported_bytes':2*1024**2,'mapping_seconds':90,'expiry_seconds':86400,'secret_puts':2,'storage_items':3,'work_attempts':0,'executable_grants':0}


def validate_binding(binding,revision,now=None):
 """Controller input is an owner-reviewed registration, never worker authority."""
 now=now or datetime.now(timezone.utc)
 expected={'authority':AUTHORITY,'controller':CONTROLLER,'risk_acceptance':RISK,
  'roles':list(MAPPINGS),'method':'CLIENT_GENERATED_SCRAM_SHA_256_MEMORY_TO_PROTECTED_SECRET',
  'project':'zcikcfgpblzuzpanpdqd','endpoint':'aws-0-eu-west-2.pooler.supabase.com:5432/postgres',
  'environment':ENVIRONMENT,'revision':revision,'limits':LIMITS}
 if not isinstance(binding,dict) or set(binding)!=set(expected)|{'expires_at','hashes'} or any(binding.get(k)!=v for k,v in expected.items()):raise ValueError('EXACT_RISK_SCOPE_REQUIRED')
 if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):raise ValueError('EXACT_REVISION_REQUIRED')
 expiry=datetime.fromisoformat(binding['expires_at'])
 if expiry.tzinfo is None or not now<expiry<=now+timedelta(hours=24):raise ValueError('REGISTRATION_EXPIRY')
 paths=['verification/ingestion_storage/credential_mapping.py','verification/ingestion_storage/tls_trust.py',
  'docs/design/ingestion-provisioning-20261016/install.sql','docs/design/ingestion-provisioning-20261016/activate.sql',
  'docs/design/ingestion-provisioning-20261016/revoke.sql','docs/design/ingestion-provisioning-20261016/storage-readback.sql',
  'docs/design/ingestion-readiness-20261016/three-items.json']
 if set(binding['hashes'])!=set(paths) or any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=binding['hashes'][p] for p in paths):raise ValueError('REGISTERED_CONTENT_CHANGED')
 return binding


def put_secret(name,value,runner=subprocess.run):
 # gh uses the environment public key/sealed-box API; plaintext goes only stdin.
 result=runner(['gh','secret','set',name,'--repo',REPO,'--env',ENVIRONMENT],input=value.encode(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False,env={**os.environ,'GH_HOST':'github.com','GH_DEBUG':'','GH_PROMPT_DISABLED':'1'})
 if result.returncode:raise RuntimeError('PROTECTED_MAPPING_NOT_CONFIRMED')


def install_mapping(connection,*,attested=False,risk_binding=None,revision=None,runner=subprocess.run,password_factory=None):
 if not attested and risk_binding is None:raise ValueError('EXPLICIT_RISK_ACCEPTANCE_REQUIRED')
 # The low-level primitive is retained solely for the existing disposable PG
 # rehearsal. No owner flag or direct import admits a production connection.
 info=connection.info
 disposable=(info.host,info.port,info.dbname,info.user)==('127.0.0.1',5432,'ingestion_provisioning_test','provisioning_migrator')
 if not disposable:
  if risk_binding is None:raise ValueError('DISPOSABLE_CREDENTIAL_MAPPING_ONLY')
  validate_binding(risk_binding,revision)
  if (info.host,info.port,info.dbname,info.user)!=('aws-0-eu-west-2.pooler.supabase.com',5432,'postgres','postgres.zcikcfgpblzuzpanpdqd') or not connection.pgconn.ssl_in_use:raise ValueError('EXACT_MIGRATION_ROUTE_REQUIRED')
  if password_factory is not None:raise ValueError('PRODUCTION_ENTROPY_FACTORY_FORBIDDEN')
  if connection.execute("SELECT current_user,session_user,(SELECT rolsuper FROM pg_roles WHERE rolname=current_user)").fetchone()!=('postgres','postgres',False):raise ValueError('EXACT_MIGRATION_PRINCIPAL_REQUIRED')
 password_factory=password_factory or (lambda:secrets.token_urlsafe(48))
 connection.execute("SET statement_timeout='10s'")
 connection.execute("SET lock_timeout='3s'")
 receipts=[]
 for role,name in MAPPINGS.items():
  flags=connection.execute('SELECT rolcanlogin,rolsuper,rolcreaterole,rolbypassrls,rolcreatedb,rolreplication FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
  if flags!=(False,False,False,False,False,False):raise ValueError('UNEXPECTED_LOGIN_STATE')
 # All roles must be checked before any credential mutation.
 for role,name in MAPPINGS.items():
  password=password_factory()
  if len(password)<48:raise ValueError('PASSWORD_ENTROPY_BOUND')
  verifier=connection.pgconn.encrypt_password(password.encode(),role.encode(),algorithm=b'scram-sha-256').decode()
  expiry=min(datetime.now(timezone.utc)+timedelta(hours=24),datetime.fromisoformat(risk_binding['expires_at']) if risk_binding else datetime.max.replace(tzinfo=timezone.utc)).isoformat()
  # If commit acknowledgement is lost, propagate a sanitised STOP. Do not retry,
  # upload, reset credentials, activate or compensate automatically.
  with connection.transaction():
   connection.execute(sql.SQL('ALTER ROLE {} PASSWORD {} VALID UNTIL {}').format(sql.Identifier(role),sql.Literal(verifier),sql.Literal(expiry)))
  uri='postgresql://'+quote(role+'.zcikcfgpblzuzpanpdqd',safe='')+':'+quote(password,safe='')+'@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'
  put_secret(name,uri,runner)
  receipts.append({'role':role,'secret_name':name,'mapped':True,'login_enabled':False,'expires_at':expiry})
  del password,verifier,uri
 return receipts


def main():
 p=argparse.ArgumentParser();p.add_argument('--authority',required=True);p.add_argument('--accept-verifier-retention',action='store_true');p.add_argument('--revision',required=True);p.add_argument('--binding',type=Path,required=True);p.add_argument('--binding-sha256',required=True);p.add_argument('--consumption-record',type=Path,required=True);a=p.parse_args()
 if a.authority!=AUTHORITY or not a.accept_verifier_retention:raise SystemExit('OWNER_MAPPING_NOT_ADMITTED')
 # This preparation file grants no authority. Only run after concrete approval.
 if sys.platform!='linux':raise SystemExit('REVIEWED_OWNER_LINUX_OR_WSL_REQUIRED')
 if not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('OWNER_SECURE_TTY_REQUIRED')
 # All registration/checkout gates precede prompts, DNS, DB and secret operations.
 if a.binding.is_symlink() or a.binding.stat().st_size>16384:raise SystemExit('REGISTRATION_BOUND')
 body=a.binding.read_bytes()
 if hashlib.sha256(body).hexdigest()!=a.binding_sha256:raise SystemExit('REGISTRATION_HASH')
 binding=validate_binding(json.loads(body),a.revision)
 if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.revision or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise SystemExit('CLEAN_EXACT_CHECKOUT_REQUIRED')
 # Owner-controlled, credential-free single-use record. A new path is NOT new
 # authority. Loss/removal of this record requires reconciliation, never replay.
 with a.consumption_record.open('x') as f:
  json.dump({'authority':AUTHORITY,'binding_sha256':a.binding_sha256,'state':'CONSUMED_BEFORE_CREDENTIAL_INPUT'},f);f.flush();os.fsync(f.fileno())
 import resource,signal
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 def deadline(signum,frame):raise TimeoutError('OWNER_MAPPING_DEADLINE')
 baseline=None
 try:
  raw=getpass.getpass('Existing migration credential URL (hidden; never paste into chat): ')
  resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
  baseline=owned_resources()
  if baseline['children']:raise ValueError('UNEXPECTED_OWNED_CHILD')
  signal.signal(signal.SIGALRM,deadline);signal.alarm(90)
  u=validate_route(raw);root,_=verified_trust()
  addresses=socket.getaddrinfo(u.host,u.port,family=socket.AF_INET,type=socket.SOCK_STREAM)
  if not addresses or len(addresses)>32:raise ValueError('DNS_BOUND')
  import psycopg
  with psycopg.connect(host=u.host,hostaddr=sorted({x[4][0] for x in addresses})[0],port=u.port,dbname=u.database,user=u.username,password=u.password,sslmode='verify-full',sslrootcert=str(root),connect_timeout=3,prepare_threshold=None,autocommit=True) as c:
   # Rehearse the exact activation gates read-only before any password material.
   gate=Path('docs/design/ingestion-provisioning-20261016/activate.sql').read_text()
   gate=gate[:gate.index('ALTER ROLE ingestion_worker_login LOGIN;')].replace('BEGIN;','BEGIN READ ONLY;',1)+'ROLLBACK;'
   c.execute(gate)
   receipts=install_mapping(c,risk_binding=binding,revision=a.revision)
  after=owned_resources()
  if after['socket_fds']-baseline['socket_fds'] or after['children']:raise ValueError('OWNED_CLEANUP_UNCERTAIN')
  print(json.dumps({'status':'MAPPED_NOLOGIN','provider_redaction_confirmed':False,'accepted_risk':RISK,'cleanup':'CLOSED','receipts':receipts}))
 except BaseException:
  print('CREDENTIAL_MAPPING_STOP_RECONCILE_BEFORE_ANY_FURTHER_MUTATION',file=sys.stderr)
  raise SystemExit(1) from None
 finally:signal.alarm(0)
if __name__=='__main__':main()
