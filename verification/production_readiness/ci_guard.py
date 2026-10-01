"""Authority limited to the PostgreSQL service created by the reviewed CI job."""
import json
import os
from pathlib import Path
import re
import subprocess

BRANCH='refs/heads/verification/ah-native-ci'
BOOTSTRAP='ah_ci_bootstrap'
PASSWORD='ah-ci-disposable-only'

def validate_environment(env, root):
    if env.get('GITHUB_ACTIONS')!='true' or env.get('GITHUB_REF')!=BRANCH or env.get('AH_REHEARSAL_NONPRODUCTION')!='YES_DISPOSABLE_ONLY':
        raise ValueError('Wrong CI branch or missing non-production marker')
    denied=[k for k in env if k.startswith(('PG','POSTGRES','DATABASE_','DB_','SUPABASE','OPENAI','ANTHROPIC','AZURE_OPENAI')) or k in ('DATABASE_URL','DATABASE_HOST','DB_HOST','DB_URL','DB_PASSWORD')]
    if denied: raise ValueError('Inherited database/model inputs rejected (values redacted)')
    if any(p.is_file() and p.name!='.env.example' for p in Path(root).rglob('.env*')):
        raise ValueError('Repository environment files rejected')
    if not re.fullmatch('[0-9a-f]{64}',env.get('AH_SERVICE_ID','')):
        raise ValueError('Missing runner-created container identity')

def inspect_service(container_id):
    if not re.fullmatch('[0-9a-f]{64}',container_id): raise ValueError('Invalid service identity')
    data=json.loads(subprocess.check_output(['docker','inspect',container_id],text=True,timeout=10))[0]
    if data['Id']!=container_id or not data['State']['Running'] or data['Config']['Image']!='postgres:16':
        raise ValueError('Wrong service container/image/state')
    env=dict(x.split('=',1) for x in data['Config']['Env'] if '=' in x)
    if any(env.get(k)!=v for k,v in {'POSTGRES_USER':BOOTSTRAP,'POSTGRES_DB':BOOTSTRAP,'POSTGRES_PASSWORD':PASSWORD}.items()):
        raise ValueError('Service bootstrap identity mismatch')
    if data.get('HostConfig',{}).get('Binds') or data.get('HostConfig',{}).get('Privileged'):
        raise ValueError('Persistent host bind or privileged service rejected')
    ports=data['NetworkSettings']['Ports'].get('5432/tcp') or []
    if not ports or any(p['HostIp'] not in ('127.0.0.1','::1') for p in ports):
        raise ValueError('Service must bind loopback only')
    port=int(ports[0]['HostPort'])
    return {'container_id':container_id,'image_id':data['Image'],'port':port,'started_at':data['State']['StartedAt']}

class ServiceAuthority:
    def __init__(self, env, root):
        validate_environment(env,root)
        self.service=inspect_service(env['AH_SERVICE_ID'])
        import psycopg
        self.driver=psycopg
        with self._connect(BOOTSTRAP,BOOTSTRAP) as conn:
            row=conn.execute("SELECT current_database(),session_user,(SELECT system_identifier::text FROM pg_control_system()),pg_postmaster_start_time()::text").fetchone()
            if row[:2]!=(BOOTSTRAP,BOOTSTRAP): raise ValueError('Bootstrap connection mismatch')
            self.identity=row[2:]
        self.databases={}
    def _connect(self,database,user):
        return self.driver.connect(host='127.0.0.1',port=self.service['port'],dbname=database,user=user,password=PASSWORD,
          connect_timeout=5,autocommit=True,options='-c statement_timeout=15000 -c lock_timeout=2000 -c search_path=public,pg_catalog')
    def admin(self):
        now=inspect_service(self.service['container_id'])
        if now!=self.service: raise ValueError('Service changed')
        c=self._connect(BOOTSTRAP,BOOTSTRAP)
        if c.execute("SELECT (SELECT system_identifier::text FROM pg_control_system()),pg_postmaster_start_time()::text").fetchone()!=self.identity:
            c.close();raise ValueError('Cluster identity changed')
        return c
    def register_database(self,name):
        if not re.fullmatch('ah_ci_[a-f0-9]{16}_(reference|target|partial|defaults)',name): raise ValueError('Non-disposable database name')
        with self.admin() as c:
            oid=c.execute('SELECT oid FROM pg_database WHERE datname=%s',(name,)).fetchone()
        if not oid: raise ValueError('Database not created')
        self.databases[name]=oid[0]
    def connect(self,name,user=BOOTSTRAP):
        if name not in self.databases or user not in (BOOTSTRAP,'ah_ci_owner','ah_ci_reader','ah_ci_importer','ah_ci_registrar','ah_ci_nobody','ah_ci_anon','ah_ci_authenticated','ah_ci_service_role'):
            raise ValueError('Unregistered database or role')
        with self.admin(): pass
        c=self._connect(name,user)
        row=c.execute('SELECT current_database(),session_user,(SELECT oid FROM pg_database WHERE datname=current_database()),pg_postmaster_start_time()::text').fetchone()
        if row!=(name,user,self.databases[name],self.identity[1]): c.close();raise ValueError('Database/role identity mismatch')
        return c
