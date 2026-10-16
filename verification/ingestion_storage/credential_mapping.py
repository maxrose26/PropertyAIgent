"""Owner-local, future-approved credential handoff. No production execution in CI.

Never print raw exceptions, connection strings, passwords, SCRAM verifiers or
GitHub CLI output. The CLI handles encryption to the existing environment key.
Python cannot guarantee erasure of strings from process memory. No files/core
are produced by this helper. Provider-side redaction requires owner attestation.
"""
import argparse,getpass,json,os,secrets,socket,subprocess,sys
from datetime import datetime,timezone,timedelta
from urllib.parse import quote
from psycopg import sql
from .tls_trust import verified_trust
from verification.discovery.route_validation import validate_route
REPO='github.com/maxrose26/PropertyAIgent'
ENVIRONMENT='stage4-production-canary'
MAPPINGS={'ingestion_worker_login':'INGESTION_WORKER_DATABASE_URL','ingestion_storage_login':'INGESTION_STORAGE_DATABASE_URL'}
AUTHORITY='AUTHORISE_RESTRICTED_INGESTION_CREDENTIAL_MAPPING_ONCE_20261016'


def put_secret(name,value,runner=subprocess.run):
 # gh uses the environment public key/sealed-box API; plaintext goes only stdin.
 result=runner(['gh','secret','set',name,'--repo',REPO,'--env',ENVIRONMENT],input=value.encode(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False)
 if result.returncode:raise RuntimeError('PROTECTED_MAPPING_NOT_CONFIRMED')


def install_mapping(connection,*,attested,runner=subprocess.run,password_factory=lambda:secrets.token_urlsafe(48)):
 if not attested:raise ValueError('PROVIDER_PASSWORD_REDACTION_ATTESTATION_REQUIRED')
 receipts=[]
 for role,name in MAPPINGS.items():
  flags=connection.execute('SELECT rolcanlogin,rolsuper,rolcreaterole,rolbypassrls,rolcreatedb,rolreplication FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
  if flags!=(False,False,False,False,False,False):raise ValueError('UNEXPECTED_LOGIN_STATE')
 # All roles must be checked before any credential mutation.
 for role,name in MAPPINGS.items():
  password=password_factory()
  if len(password)<48:raise ValueError('PASSWORD_ENTROPY_BOUND')
  verifier=connection.pgconn.encrypt_password(password.encode(),role.encode(),algorithm=b'scram-sha-256').decode()
  expiry=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()
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
 p=argparse.ArgumentParser();p.add_argument('--authority',required=True);p.add_argument('--provider-password-redaction-attested',action='store_true');a=p.parse_args()
 if a.authority!=AUTHORITY or not a.provider_password_redaction_attested:raise SystemExit('OWNER_MAPPING_NOT_ADMITTED')
 # This preparation file grants no authority. Only run after concrete approval.
 try:
  import resource
  resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 except ImportError:
  # On Windows the owner must disable process crash dumps in the trusted session.
  pass
 try:
  raw=getpass.getpass('Existing migration credential URL (hidden; never paste into chat): ')
  u=validate_route(raw);root,_=verified_trust()
  addresses=socket.getaddrinfo(u.host,u.port,family=socket.AF_INET,type=socket.SOCK_STREAM)
  if not addresses or len(addresses)>32:raise ValueError('DNS_BOUND')
  import psycopg
  with psycopg.connect(host=u.host,hostaddr=sorted({x[4][0] for x in addresses})[0],port=u.port,dbname=u.database,user=u.username,password=u.password,sslmode='verify-full',sslrootcert=str(root),connect_timeout=3,prepare_threshold=None,autocommit=True) as c:
   receipts=install_mapping(c,attested=True)
  print(json.dumps({'status':'MAPPED_NOLOGIN','receipts':receipts}))
 except BaseException:
  # Suppress stderr/tracebacks even on interruption; outcome may be uncertain.
  print('CREDENTIAL_MAPPING_STOP_RECONCILE_BEFORE_ANY_FURTHER_MUTATION',file=sys.stderr)
  raise SystemExit(1) from None
if __name__=='__main__':main()
