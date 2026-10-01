"""Private Actions-container authority only; never accepts a DSN."""
import json
import re
import subprocess
from pathlib import Path

BRANCH='refs/heads/verification/ah-final-artifact'
IMAGE='postgres:17.6'
BOOTSTRAP='ah_final_bootstrap'
PASSWORD='ah-final-disposable-only'

def validate_environment(env,root):
    if env.get('GITHUB_ACTIONS')!='true' or env.get('GITHUB_REF')!=BRANCH or env.get('AH_REHEARSAL_NONPRODUCTION')!='YES_DISPOSABLE_ONLY':
        raise ValueError('Wrong branch/nonproduction authority')
    if any(k.startswith(('PG','POSTGRES','DATABASE_','DB_','SUPABASE','OPENAI','ANTHROPIC','AZURE_OPENAI','RENDER')) for k in env):
        raise ValueError('Inherited database/model/production inputs rejected; values redacted')
    if any(p.is_file() and p.name!='.env.example' for p in Path(root).rglob('.env*')):
        raise ValueError('Repository environment file rejected')
    if not re.fullmatch('[0-9a-f]{64}',env.get('AH_SERVICE_ID','')):
        raise ValueError('Missing service container identity')

def inspect_service(cid):
    if not re.fullmatch('[0-9a-f]{64}',cid): raise ValueError('Invalid container ID')
    x=json.loads(subprocess.check_output(['docker','inspect',cid],text=True,timeout=10))[0]
    if x['Id']!=cid or x['Config']['Image']!=IMAGE or not x['State']['Running']:
        raise ValueError('Wrong container/image/state')
    e=dict(v.split('=',1) for v in x['Config']['Env'] if '=' in v)
    if any(e.get(k)!=v for k,v in {'POSTGRES_USER':BOOTSTRAP,'POSTGRES_DB':BOOTSTRAP,'POSTGRES_PASSWORD':PASSWORD}.items()):
        raise ValueError('Wrong disposable service bootstrap')
    if x['HostConfig'].get('Binds') or x['HostConfig'].get('Privileged'): raise ValueError('Host bind/privileged service rejected')
    ports=x['NetworkSettings']['Ports'].get('5432/tcp') or []
    if not ports or any(v['HostIp'] not in ('127.0.0.1','::1') for v in ports): raise ValueError('Nonloopback service')
    identity=subprocess.check_output(['docker','exec',cid,'psql','-U',BOOTSTRAP,'-d',BOOTSTRAP,'-Atc',"SELECT system_identifier::text FROM pg_control_system()"],text=True,timeout=10).strip()
    return {'container_id':cid,'image_id':x['Image'],'port':int(ports[0]['HostPort']),'system_identifier':identity,'started_at':x['State']['StartedAt']}

class Authority:
    def __init__(self,env,root):
        validate_environment(env,root)
        import psycopg
        self.driver=psycopg
        self.service=inspect_service(env['AH_SERVICE_ID'])
        self.allowed={BOOTSTRAP}
        with self.connect(BOOTSTRAP) as c:
            if c.execute("SELECT current_setting('server_version_num')::int").fetchone()[0]!=170006:
                raise ValueError('Exact PostgreSQL 17.6 required')
    def connect(self,db='postgres',user=BOOTSTRAP):
        if db not in self.allowed or user not in (BOOTSTRAP,'postgres'):
            raise ValueError('Unregistered disposable database/user')
        if inspect_service(self.service['container_id'])!=self.service: raise ValueError('Container identity changed')
        c=self.driver.connect(host='127.0.0.1',port=self.service['port'],dbname=db,user=user,password=PASSWORD,autocommit=True,connect_timeout=5,options='-c statement_timeout=15000 -c lock_timeout=2000 -c search_path=public,pg_catalog')
        # Both permitted administrative fixture roles may inspect pg_control_system.
        row=c.execute("SELECT current_database(),session_user,system_identifier::text FROM pg_control_system()").fetchone()
        if row!=(db,user,self.service['system_identifier']): c.close();raise ValueError('Cluster/database/session mismatch')
        return c
    def register(self,db):
        if db not in ('postgres','ah_final_reference'): raise ValueError('Wrong disposable database name')
        self.allowed.add(db)
