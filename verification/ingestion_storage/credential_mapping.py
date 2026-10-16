"""BLOCKED production CLI; retain low-level mapping only for disposable tests.

Never print raw exceptions, connection strings, passwords, SCRAM verifiers or
GitHub CLI output. The CLI handles encryption to the existing environment key.
Python cannot guarantee erasure of strings from process memory. No files/core
are produced by this helper. Provider-side redaction requires owner attestation.
"""
import argparse,getpass,json,os,secrets,socket,subprocess,sys
from datetime import datetime,timezone,timedelta
from urllib.parse import quote
from psycopg import sql
from .tls_trust import verified_trust,owned_resources
from verification.discovery.route_validation import validate_route
REPO='github.com/maxrose26/PropertyAIgent'
ENVIRONMENT='stage4-production-canary'
MAPPINGS={'ingestion_worker_login':'INGESTION_WORKER_DATABASE_URL','ingestion_storage_login':'INGESTION_STORAGE_DATABASE_URL'}
AUTHORITY='AUTHORISE_RESTRICTED_INGESTION_CREDENTIAL_MAPPING_ONCE_20261016'


def put_secret(name,value,runner=subprocess.run):
 # gh uses the environment public key/sealed-box API; plaintext goes only stdin.
 result=runner(['gh','secret','set',name,'--repo',REPO,'--env',ENVIRONMENT],input=value.encode(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False,env={**os.environ,'GH_HOST':'github.com','GH_DEBUG':'','GH_PROMPT_DISABLED':'1'})
 if result.returncode:raise RuntimeError('PROTECTED_MAPPING_NOT_CONFIRMED')


def install_mapping(connection,*,attested,runner=subprocess.run,password_factory=lambda:secrets.token_urlsafe(48)):
 if not attested:raise ValueError('PROVIDER_PASSWORD_REDACTION_ATTESTATION_REQUIRED')
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
 if sys.platform!='linux':raise SystemExit('REVIEWED_OWNER_LINUX_OR_WSL_REQUIRED')
 if not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('OWNER_SECURE_TTY_REQUIRED')
 # Explicit stop: reviewed owner authority does not establish log protection.
 raise SystemExit('SCRAM_SQL_PROVISIONING_BLOCKED_PENDING_METHOD_ACCEPTANCE')
if __name__=='__main__':main()
