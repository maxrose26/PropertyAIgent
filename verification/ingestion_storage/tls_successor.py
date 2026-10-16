"""Prepared successor entry. No registered workflow or live authority here."""
import argparse,hashlib,json,os,resource,socket,subprocess
from pathlib import Path
from sqlalchemy import create_engine
from . import preflight
WORKFLOW='.github/workflows/stage4-ingestion-storage-catalogue-tls-once.yml'
AUTHORITY='AUTHORISE_STORAGE_TLS_CATALOGUE_ONCE_20261016'


def single_address_engine(url,**options):
    # Resolve the same approved host once; keep host for SNI/hostname checks.
    # A single hostaddr prevents psycopg's implicit per-DNS-address failover.
    addresses=socket.getaddrinfo(url.host,url.port,family=socket.AF_INET,type=socket.SOCK_STREAM)
    if not addresses or len(addresses)>32:raise ValueError('DNS_BOUND')
    address=sorted({x[4][0] for x in addresses})[0]
    args=dict(options['connect_args']);args['hostaddr']=address
    return create_engine(url,**{**options,'connect_args':args})


def admitted(sha,authority,env):
    adjusted=dict(env)
    if authority!=AUTHORITY or env.get('GITHUB_WORKFLOW_REF')!='maxrose26/PropertyAIgent/'+WORKFLOW+'@refs/heads/master':return False
    adjusted['GITHUB_WORKFLOW_REF']='maxrose26/PropertyAIgent/'+preflight.WORKFLOW+'@refs/heads/master'
    return preflight.admitted(sha,preflight.AUTHORITY,adjusted)


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--authority',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    if not admitted(a.sha,a.authority,os.environ):raise SystemExit('SUCCESSOR_NOT_ADMITTED')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise SystemExit('CHECKOUT_NOT_CLEAN_EXACT')
    for path,digest in preflight.HASHES.items():
        if hashlib.sha256(Path(preflight.PACKAGE+path).read_bytes()).hexdigest()!=digest:raise SystemExit('PACKAGE_CHANGED')
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**2,2*1024**2))
    raw=os.environ.pop('STORAGE_PREFLIGHT_DATABASE_URL','')
    context=dict(revision=a.sha,workflow=WORKFLOW,workflow_sha256=hashlib.sha256(Path(WORKFLOW).read_bytes()).hexdigest(),run_id=os.environ['GITHUB_RUN_ID'],attempt=1,run_number=1)
    result=preflight.run(raw,a.output,engine_factory=single_address_engine,execution=context)
    raise SystemExit(0 if result['status']=='READ_ONLY_CATALOGUE_COMPLETE_BLOCKED' and result['cleanup']=='CLOSED' else 1)
if __name__=='__main__':main()
