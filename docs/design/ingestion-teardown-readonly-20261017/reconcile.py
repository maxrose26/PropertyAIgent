"""Single read-only owner-local observation; no provisioning or secret mutation."""
import hashlib, ipaddress, json, multiprocessing, os, resource, signal, subprocess, sys, time, zipfile
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,os.getcwd())

REVISION='7cf8d32547b63d485de872afc2f717c3dce55322'
TREE='68bf766cda023b1f15a19a63978903995391ec46'
REGISTRATION='43bb06a2ee93cc77428e056eb8a19b2efe8f98e880ed42d0a0e0b2b69e33d5f3'
PRIOR_SECONDS=6.463323766999565
ROLES=('ingestion_worker_login','ingestion_storage_login')
NAMES=('INGESTION_WORKER_DATABASE_URL','INGESTION_STORAGE_DATABASE_URL')
STATE=Path.home()/'.local/state/propertyaigent'
OLD_AUDITS=(('storage-acceptance-once-20261016',1573,'f509bd0d5a53282d099ca68b6d5ceb0e60047dd500991395779ba483621aafc0'),('storage-acceptance-memory-successor-20261017',7005,'5dda1e97c8dfc2a9a899c839e9c60d88f3c08bff05d5172579ad2efe1ade279e'),('storage-acceptance-identity-successor-20261017',104114,'788351d1bf68d282640a88f0c5627631a57b447bd4028db2ee781290ce73b560'))

QUERY="""SELECT jsonb_build_object(
 'current_user',current_user,'session_user',session_user,
 'migration_flags',(SELECT jsonb_build_object('superuser',rolsuper,'create_role',rolcreaterole,'create_db',rolcreatedb,'bypass_rls',rolbypassrls) FROM pg_roles WHERE rolname=current_user),
 'roles',coalesce((SELECT jsonb_agg(jsonb_build_object('name',rolname,'can_login',rolcanlogin,'superuser',rolsuper,'create_role',rolcreaterole,'create_db',rolcreatedb,'bypass_rls',rolbypassrls,'replication',rolreplication,'connection_limit',rolconnlimit,'valid_until',rolvaliduntil)) FROM pg_roles WHERE rolname=ANY(%s)), '[]'::jsonb),
 'memberships',coalesce((SELECT jsonb_agg(jsonb_build_object('member',member_name,'role',role_name,'admin',admin_option,'inherit',inherit_option,'set',set_option)) FROM (SELECT m.rolname member_name,r.rolname role_name,a.admin_option,a.inherit_option,a.set_option FROM pg_auth_members a JOIN pg_roles m ON m.oid=a.member JOIN pg_roles r ON r.oid=a.roleid WHERE m.rolname=ANY(%s) ORDER BY m.rolname,r.rolname LIMIT 17) x),'[]'::jsonb),
 'membership_count',(SELECT count(*) FROM pg_auth_members a JOIN pg_roles m ON m.oid=a.member WHERE m.rolname=ANY(%s)),
 'sessions',coalesce((SELECT jsonb_agg(jsonb_build_object('pid',pid,'user',usename,'database',datname,'backend_start',backend_start,'state',state,'backend_type',backend_type)) FROM (SELECT pid,usename,datname,backend_start,state,backend_type FROM pg_stat_activity WHERE usename=ANY(%s) ORDER BY pid LIMIT 17) x),'[]'::jsonb),
 'session_count',(SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)),
 'password_boolean_read_permitted',has_column_privilege(current_user,'pg_catalog.pg_authid','rolname','SELECT') AND has_column_privilege(current_user,'pg_catalog.pg_authid','rolpassword','SELECT'))"""
PASSWORD_QUERY="""SELECT rolname,rolpassword IS NULL FROM pg_catalog.pg_authid WHERE rolname=ANY(%s) ORDER BY rolname"""

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def check_chain(raw):
    previous='0'*64;rows=[]
    for i,line in enumerate(raw.splitlines()):
        row=json.loads(line);body={k:v for k,v in row.items() if k!='sha256'}
        if row['sequence']!=i or row['previous_sha256']!=previous or hashlib.sha256(canonical(body)).hexdigest()!=row['sha256']:raise ValueError('AUDIT_CHAIN')
        previous=row['sha256'];rows.append(row)
    return rows

class Journal:
    def __init__(self,root):
        root.mkdir(mode=0o700,exist_ok=False);self.root=root;self.head='0'*64;self.count=0;self.size=0
        self.file=(root/'events.jsonl').open('xb',buffering=0)
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        fd=os.open(root.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    def append(self,event,payload):
        body=dict(sequence=self.count,previous_sha256=self.head,event=event,payload=payload)
        digest=hashlib.sha256(canonical(body)).hexdigest();line=canonical(dict(body,sha256=digest))+b'\n'
        if len(line)>32768 or self.size+len(line)>131072:raise ValueError('AUDIT_BOUND')
        self.file.write(line);os.fsync(self.file.fileno());self.count+=1;self.size+=len(line);self.head=digest

def observe(group,pipe,raw,route,started):
    from verification.ingestion_storage import credential_mapping as mapping
    from verification.ingestion_storage.tls_trust import verified_trust,owned_resources
    import psycopg
    os.setsid();group.enter();resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    for fd in (1,2):
        n=os.open(os.devnull,os.O_WRONLY);os.dup2(n,fd);os.close(n)
    baseline=owned_resources();conn=None;commands=0;attempts=0;returned=0;transaction=False;observed={};error=None
    def emit(event,value):
        pipe.send_bytes(canonical(dict(event=event,payload=value)))
        if pipe.recv_bytes(16)!=b'DURABLE':raise ValueError('ACK')
    def execute(sql,args=None):
        nonlocal commands
        if commands>=6 or time.monotonic()-started>=7.5:raise ValueError('READ_ONLY_BUDGET')
        commands+=1;emit('statement_intent',dict(index=commands))
        return conn.execute(sql,args)
    try:
        emit('observation_started',dict(connection_attempts=1,prior_connections=8,prior_commands=139,prior_seconds=PRIOR_SECONDS))
        u=mapping.validate_route(raw);ca,_=verified_trust();attempts=1
        conn=psycopg.connect(host=u.host,hostaddr=route['selected_address'],port=u.port,dbname=u.database,user=u.username,password=u.password,sslmode='verify-full',sslrootcert=str(ca),connect_timeout=2,prepare_threshold=None,autocommit=True)
        execute('BEGIN READ ONLY');transaction=True
        execute("SET LOCAL statement_timeout='2s'")
        execute("SET LOCAL idle_in_transaction_session_timeout='3s'")
        observation=execute(QUERY,(list(ROLES),)*5).fetchone()[0]
        encoded=canonical(observation);returned+=len(encoded)
        if len(encoded)>16384:raise ValueError('DATABASE_RESULT_BOUND')
        emit('role_session_observation',observation);observed.update(observation)
        if observation['current_user']!='postgres' or observation['session_user']!='postgres' or observation['migration_flags']!=dict(superuser=False,create_role=True,create_db=True,bypass_rls=True):raise ValueError('MIGRATION_IDENTITY')
        if observation['password_boolean_read_permitted']:
            passwords=execute(PASSWORD_QUERY,(list(ROLES),)).fetchall()
            returned+=len(canonical(passwords));emit('password_removal_booleans',dict(rows=passwords))
            observed['password_removal_booleans']=passwords
        else:
            emit('password_removal_booleans',dict(status='UNKNOWN_PERMISSION_UNAVAILABLE',rows=[]))
            observed['password_removal_booleans']=None
    except BaseException as exc:
        state=getattr(exc,'sqlstate',None);error=dict(reason='READ_ONLY_DATABASE_OBSERVATION_FAILED',sqlstate=state if isinstance(state,str) and len(state)==5 and state.isalnum() else None)
        emit('observation_error',error)
    finally:
        if conn is not None:
            try:
                if transaction:execute('ROLLBACK');transaction=False;emit('rollback',dict(acknowledged=True))
            except BaseException:error=dict(reason='ROLLBACK_UNCERTAIN');emit('observation_error',error)
            finally:
                conn.close();emit('connection_closed',dict(closed=conn.closed,commands=commands,connection_attempts=attempts,returned_data_value_bytes=returned))
    # Successful list metadata is required for absence; a404is not proof.
    # gh exports only these two allowlisted names and total_count. No values.
    secrets={name:'UNKNOWN' for name in NAMES}
    try:
        if time.monotonic()-started>=7.5:raise ValueError('DEADLINE')
        expression='{total_count:.total_count,names:[.secrets[] | select(.name=="INGESTION_WORKER_DATABASE_URL" or .name=="INGESTION_STORAGE_DATABASE_URL") | .name]}'
        command=['gh','api','repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets?per_page=100','--jq',expression]
        env={**os.environ,'GH_HOST':'github.com','GH_DEBUG':'','GH_PROMPT_DISABLED':'1'}
        result=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=min(2,7.5-(time.monotonic()-started)))
        if len(result.stdout)+len(result.stderr)>8192 or result.returncode:raise ValueError('METADATA_UNAVAILABLE')
        metadata=json.loads(result.stdout)
        if type(metadata['total_count']) is not int or not 0<=metadata['total_count']<=100 or not isinstance(metadata['names'],list) or any(n not in NAMES for n in metadata['names']):raise ValueError('METADATA_CAP_OR_SHAPE')
        secrets={name:('PRESENT' if name in metadata['names'] else 'ABSENT') for name in NAMES}
    except BaseException:pass
    for name in NAMES:emit('temporary_secret_name',dict(name=name,status=secrets[name]))
    observed['temporary_secret_names']=secrets
    emit('recorded_observation',dict(results=observed,error=error,commands=commands,connection_attempts=attempts,returned_data_value_bytes=returned))
    after=owned_resources()
    if after['socket_fds']-baseline['socket_fds'] or after['children']:raise ValueError('OWNED_CLEANUP_UNCERTAIN')
    emit('worker_closed',dict(cleanup='CLOSED' if conn is not None and conn.closed else 'UNCERTAIN',connection_closed=conn is not None and conn.closed,live_children=0,new_socket_fds=0))
    pipe.close()

def supervise(raw,route,journal,started):
    from verification.ingestion_storage.memory_enforcement import WorkerMemory
    from verification.ingestion_storage.storage_controller import safe_failure
    parent,child=multiprocessing.get_context('fork').Pipe();group=None;process=None;recorded=None;closed=False;reason=None;memory={}
    try:
        group=WorkerMemory.create()
        process=multiprocessing.get_context('fork').Process(target=observe,args=(group,child,raw,route,started));process.start();child.close()
        while process.is_alive() or parent.poll():
            if time.monotonic()-started>=8:raise ValueError('SUPERVISED_DEADLINE')
            memory=group.snapshot()
            if any(memory[k] for k in ('kernel_memory_max_events','kernel_memory_oom','kernel_memory_oom_kill','outer_memory_max_events','outer_memory_oom','outer_memory_oom_kill')):raise ValueError('MEMORY_LIMIT')
            if parent.poll(.01):
                try:message=json.loads(parent.recv_bytes(32768))
                except EOFError:break
                if set(message)!={'event','payload'}:raise ValueError('PROTOCOL')
                journal.append(message['event'],message['payload'])
                if message['event']=='recorded_observation':recorded=message['payload']
                if message['event']=='worker_closed':closed=message['payload'].get('cleanup')=='CLOSED'
                parent.send_bytes(b'DURABLE')
        process.join(timeout=.1)
    except BaseException:reason='READ_ONLY_OBSERVATION_OR_SUPERVISION_STOP'
    finally:
        if process is not None and process.is_alive():process.terminate();process.join(timeout=min(.2,max(0,10-(time.monotonic()-started))))
        try:
            if group is not None:memory=group.close(started+10)
        except BaseException:reason='MEMORY_CLEANUP_UNCERTAIN'
        if process is not None:process.join(timeout=min(.1,max(0,10-(time.monotonic()-started))))
        parent.close();child.close()
    elapsed=time.monotonic()-started
    normal=closed and recorded is not None and recorded['error'] is None and process is not None and process.exitcode==0 and not reason and elapsed<=10 and memory.get('kernel_memory_populated')==0 and memory.get('kernel_memory_group_removed') and not memory.get('kernel_memory_forced_cleanup') and not memory.get('kernel_memory_accounting_uncertain') and not any(memory.get(k) for k in ('kernel_memory_max_events','kernel_memory_oom','kernel_memory_oom_kill','outer_memory_max_events','outer_memory_oom','outer_memory_oom_kill'))
    result=dict(status='READ_ONLY_OBSERVATION_COMPLETE' if normal else 'STOP_RECONCILE_NO_RETRY',cleanup='CLOSED' if normal else 'UNCERTAIN',reason=reason,elapsed_seconds=elapsed,cumulative_supervised_seconds=PRIOR_SECONDS+elapsed,cumulative_connections=8+(recorded['connection_attempts'] if recorded else 1),cumulative_commands=139+(recorded['commands'] if recorded else 6),observation=recorded,**memory)
    # Results were recorded durably before this verdict. Missing/limited data
    # remains unknown and never grants mutation or relabels historical cleanup.
    result['access_verdict']=access_verdict(recorded['results']) if normal else 'UNKNOWN'
    result.update(reconciliation_commands=recorded['commands'] if recorded else 6,reconciliation_connection_attempts=recorded['connection_attempts'] if recorded else 1,original_expiry='2026-10-18T08:54:58.469465Z',historical_cleanup_uncertainty_preserved=True,original_teardown_commands_remaining=0)
    journal.append('observation_supervisor_result',dict(snapshot_type='INTERMEDIATE_OBSERVATION_CLOSURE',**result))
    return result

def access_verdict(results):
    roles=results.get('roles',[]);passwords=results.get('password_removal_booleans')
    if len(roles)!=2 or {x.get('name') for x in roles}!=set(ROLES) or passwords is None or {x[0] for x in passwords}!=set(ROLES):return 'UNKNOWN'
    if any(x.get('can_login') is not False or any(x.get(k) is not False for k in ('superuser','create_role','create_db','bypass_rls','replication')) for x in roles) or any(x[1] is not True for x in passwords) or results.get('membership_count')!=0 or results.get('session_count')!=0:return 'DATABASE_CLEANUP_INCOMPLETE'
    if any(results.get('temporary_secret_names',{}).get(n) not in ('ABSENT','PRESENT') for n in NAMES):return 'DATABASE_ACCESS_DISABLED_SECRET_STATE_UNKNOWN'
    if any(results.get('temporary_secret_names',{}).get(n)=='PRESENT' for n in NAMES):return 'DATABASE_ACCESS_DISABLED_SECRET_CLEANUP_PENDING'
    return 'OBSERVED_DISABLED_AND_SECRETS_ABSENT'

def main():
    if sys.platform!='linux' or not sys.stdin.isatty() or not sys.stderr.isatty():raise ValueError('SECURE_TTY')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=REVISION or subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip()!=TREE or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('EXACT_CHECKOUT')
    from verification.ingestion_storage import storage_controller as c
    from verification.ingestion_storage.memory_enforcement import owner_scope
    from verification.ingestion_storage.tls_trust import verified_trust
    reg=Path.home()/'stage4-owner/storage-identity-registration.json';body=reg.read_bytes()
    if reg.is_symlink() or hashlib.sha256(body).hexdigest()!=REGISTRATION:raise ValueError('REGISTRATION')
    c.validate_registration(body,REVISION);verified_trust();owner_scope()
    if any(os.environ.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_DEBUG','PGPASSWORD','PGPASSFILE','PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGSSLCERT','PGSSLKEY')):raise ValueError('ENVIRONMENT_OVERRIDE')
    audits={};latest=None
    for directory,size,digest in OLD_AUDITS:
        p=STATE/directory/'events.jsonl'
        if p.is_symlink() or p.stat().st_size!=size:raise ValueError('PRIOR_AUDIT')
        data=p.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('PRIOR_AUDIT_HASH')
        latest=check_chain(data);audits[directory+'/events.jsonl']=data
    routes=[r['payload'] for r in latest if r['event']=='route']
    if len(routes)!=1:raise ValueError('EXACT_PRIOR_ROUTE')
    route=routes[0];ipaddress.IPv4Address(route['selected_address'])
    if (route['host'],route['port'],route['database'],route['tls'])!=('aws-0-eu-west-2.pooler.supabase.com',5432,'postgres','verify-full'):raise ValueError('EXACT_PRIOR_ROUTE')
    root=STATE/'storage-teardown-readonly-reconciliation-20261017';journal=Journal(root)
    result=None;started=None
    try:
        journal.append('consumed',dict(authority='OWNER_APPROVED_READ_ONLY_TEARDOWN_RECONCILIATION_20261017',revision=REVISION,limits=dict(connections=1,commands=6,supervised_seconds=10,memory_bytes=268435456),source_audit_sha256=OLD_AUDITS[-1][2]))
        raw=c.mapping.secure_migration_input();started=time.monotonic();c.validate_registration(body,REVISION);c.mapping.validate_route(raw)
        result=supervise(raw,route,journal,started);del raw
    finally:
        journal.file.close()
        audits['read-only-reconciliation/events.jsonl']=(root/'events.jsonl').read_bytes()
        sums={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in audits.items()}
        if sum(x['bytes'] for x in sums.values())>300000:raise ValueError('ARCHIVE_BOUND')
        archive=root/'credential-free-audits.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for name,data in audits.items():z.writestr(name,data)
            z.writestr('HASHES.json',canonical(sums)+b'\n')
        if archive.stat().st_size>300000:raise ValueError('ARCHIVE_BOUND')
        if result is not None:
            # Include final local archival in the reported aggregate, not just
            # source observation. No new source operation follows supervision.
            result['observation_supervised_seconds']=result['elapsed_seconds']
            result['elapsed_seconds']=time.monotonic()-started
            result['cumulative_supervised_seconds']=PRIOR_SECONDS+result['elapsed_seconds']
            if result['elapsed_seconds']>10:result.update(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',reason='TOTAL_DEADLINE')
            result['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
            result['authoritative_final_result']=True
            final=root/'final-result.json'
            with final.open('xb',buffering=0) as stream:stream.write(canonical(result)+b'\n');os.fsync(stream.fileno())
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
            print(json.dumps(result,sort_keys=True))
            print('Final result file:',final)
            print('Final result SHA256:',hashlib.sha256(final.read_bytes()).hexdigest())
        print('Credential-free archive:',archive)
        print('Archive SHA256:',hashlib.sha256(archive.read_bytes()).hexdigest())
    if result is None or result['status']!='READ_ONLY_OBSERVATION_COMPLETE':raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except BaseException:
        print('READ_ONLY_RECONCILIATION_STOP_NO_RETRY',file=sys.stderr)
        raise SystemExit(1) from None
