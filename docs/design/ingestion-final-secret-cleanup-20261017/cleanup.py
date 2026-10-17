"""Owner-authorised exact two-secret teardown. Zero database connections."""
import hashlib,importlib.util,json,multiprocessing,os,re,resource,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,os.getcwd())

REVISION='7cf8d32547b63d485de872afc2f717c3dce55322'
TREE='68bf766cda023b1f15a19a63978903995391ec46'
EXPIRY='2026-10-18T08:54:58.469465Z'
PRIOR_SECONDS=7.079792436999014
NAMES=('INGESTION_WORKER_DATABASE_URL','INGESTION_STORAGE_DATABASE_URL')
PREFIX='repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets'
STATE=Path.home()/'.local/state/propertyaigent'
ROOT=STATE/'storage-final-secret-cleanup-20261017'
READONLY_SHA='cbe64e7394dda45f3940f5a66f68935687cc505069743ec1dc779523b8f1b3a2'
RESULT_SHA='4f1da6a2e5a3078813a42015da38a92016ab1cf631947fe74a60c423701d1e9a'
AUDIT_SHA='f72d6b58c7787313f680df4f29f51acf46cf1b544531a67ae66401592afc0772'
ZIP_SHA='09edd0dd786799f62ec88b20ca5cc5be696b76ff3ae07e4e97979cecb602c529'

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def unexpired():
    if datetime.now(timezone.utc)>=datetime.fromisoformat(EXPIRY):raise ValueError('ORIGINAL_EXPIRY')

def calls(emit,started,runner=subprocess.run):
    """Only2exact DELETEs and1filteredGET; no retry on any response."""
    requests=0;acknowledged=[];uncertain=None;names_status='UNKNOWN';preserved_database_url='UNKNOWN'
    def run(command):
        nonlocal requests
        unexpired()
        if requests>=3 or time.monotonic()-started>=7.5:raise ValueError('API_OR_TIME_LIMIT')
        requests+=1
        emit('api_intent',dict(request=requests,method='DELETE' if '--include' in command else 'GET',names=list(NAMES) if '--include' not in command else [command[-1].split('/')[-1]]))
        env={**os.environ,'GH_HOST':'github.com','GH_DEBUG':'','GH_PROMPT_DISABLED':'1'}
        result=runner(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=min(2,7.5-(time.monotonic()-started)))
        if len(result.stdout)+len(result.stderr)>8192:raise ValueError('OUTPUT_BOUND')
        return result
    for name in NAMES:
        emit('deletion_intent',dict(name=name,endpoint=PREFIX+'/'+name))
        try:
            result=run(['gh','api','--method','DELETE','--include','--silent',PREFIX+'/'+name])
            statuses=re.findall(rb'^HTTP/\S+\s+(\d{3})(?:\s|$)',result.stdout,re.M)
            status=int(statuses[-1]) if len(statuses)==1 else None
            if result.returncode!=0 or status!=204:raise ValueError('DELETE_NOT_ACKNOWLEDGED')
            emit('deletion_ack',dict(name=name,http_status=204));acknowledged.append(name)
        except BaseException:
            uncertain=name;emit('deletion_uncertain',dict(name=name));break
    # An uncertainDELETE stops remaining mutations. The one allowedGET can
    # still record absence/presence without retrying an uncertain operation.
    try:
        expression='{total_count:.total_count,names:[.secrets[]|select(.name=="INGESTION_WORKER_DATABASE_URL" or .name=="INGESTION_STORAGE_DATABASE_URL")|.name],database_url_present:any(.secrets[];.name=="DATABASE_URL")}'
        result=run(['gh','api','--method','GET',PREFIX+'?per_page=100','--jq',expression])
        if result.returncode!=0:raise ValueError('METADATA_NOT_CONFIRMED')
        metadata=json.loads(result.stdout)
        if type(metadata.get('total_count')) is not int or not 0<=metadata['total_count']<=100 or not isinstance(metadata.get('names'),list) or any(n not in NAMES for n in metadata['names']) or type(metadata.get('database_url_present')) is not bool:raise ValueError('METADATA_CAP_OR_SHAPE')
        names_status={n:('PRESENT' if n in metadata['names'] else 'ABSENT') for n in NAMES}
        preserved_database_url=metadata['database_url_present']
        emit('absence_observation',dict(names=names_status,database_url_present=preserved_database_url))
    except BaseException:emit('absence_observation',dict(names='UNKNOWN',database_url_present='UNKNOWN'))
    # All safe observations are durable before evaluating this verdict.
    result=dict(api_requests=requests,delete_acknowledgements=acknowledged,uncertain_delete=uncertain,names=names_status,database_url_present=preserved_database_url,database_connections=0,database_commands=0)
    result['verified']=not uncertain and acknowledged==list(NAMES) and names_status==dict.fromkeys(NAMES,'ABSENT') and preserved_database_url is True
    emit('cleanup_observation',result)
    return result

def worker(group,pipe,started):
    from verification.ingestion_storage.tls_trust import owned_resources
    os.setsid();group.enter();resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    for fd in (1,2):
        n=os.open(os.devnull,os.O_WRONLY);os.dup2(n,fd);os.close(n)
    before=owned_resources()
    def emit(event,payload):
        pipe.send_bytes(canonical(dict(event=event,payload=payload)))
        if pipe.recv_bytes(16)!=b'DURABLE':raise ValueError('AUDIT_ACK')
    try:
        calls(emit,started)
        after=owned_resources()
        if after['socket_fds']-before['socket_fds'] or after['children']:raise ValueError('OWNED_CLOSURE')
        emit('worker_closed',dict(cleanup='CLOSED',live_children=0,new_socket_fds=0))
    except BaseException:emit('worker_failed',dict(reason='SECRET_CLEANUP_UNCERTAIN',cleanup='UNCERTAIN'))
    finally:pipe.close()

def supervise(journal):
    from verification.ingestion_storage.memory_enforcement import WorkerMemory
    started=time.monotonic();parent,child=multiprocessing.get_context('fork').Pipe();group=None;process=None;observation=None;closed=False;reason=None;memory={}
    try:
        group=WorkerMemory.create();process=multiprocessing.get_context('fork').Process(target=worker,args=(group,child,started));process.start();child.close()
        while process.is_alive() or parent.poll():
            if time.monotonic()-started>=8:raise ValueError('DEADLINE')
            memory=group.snapshot()
            if any(memory[k] for k in ('kernel_memory_max_events','kernel_memory_oom','kernel_memory_oom_kill','outer_memory_max_events','outer_memory_oom','outer_memory_oom_kill')):raise ValueError('MEMORY_LIMIT')
            if parent.poll(.01):
                try:message=json.loads(parent.recv_bytes(16384))
                except EOFError:break
                if set(message)!={'event','payload'}:raise ValueError('PROTOCOL')
                journal.append(message['event'],message['payload'])
                if message['event']=='cleanup_observation':observation=message['payload']
                if message['event']=='worker_closed':closed=message['payload'].get('cleanup')=='CLOSED'
                if message['event']=='worker_failed':reason='SECRET_CLEANUP_UNCERTAIN'
                parent.send_bytes(b'DURABLE')
        process.join(timeout=.1)
    except BaseException:reason='SECRET_CLEANUP_OR_SUPERVISION_UNCERTAIN'
    finally:
        if process is not None and process.is_alive():process.terminate();process.join(timeout=min(.2,max(0,10-(time.monotonic()-started))))
        try:
            if group is not None:memory=group.close(started+10)
        except BaseException:reason='MEMORY_CLEANUP_UNCERTAIN'
        if process is not None:process.join(timeout=min(.1,max(0,10-(time.monotonic()-started))))
        parent.close();child.close()
    elapsed=time.monotonic()-started
    closure=closed and process is not None and process.exitcode==0 and not reason and elapsed<=10 and memory.get('kernel_memory_populated')==0 and memory.get('kernel_memory_group_removed') and not memory.get('kernel_memory_forced_cleanup') and not memory.get('kernel_memory_accounting_uncertain') and not any(memory.get(k) for k in ('kernel_memory_max_events','kernel_memory_oom','kernel_memory_oom_kill','outer_memory_max_events','outer_memory_oom','outer_memory_oom_kill'))
    success=closure and observation is not None and observation['verified']
    result=dict(status='TEMPORARY_SECRETS_REMOVED_ACCESS_DISABLED' if success else 'STOP_RECONCILE_NO_RETRY',cleanup='CLOSED' if closure else 'UNCERTAIN',reason=reason,elapsed_seconds=elapsed,cumulative_supervised_seconds=PRIOR_SECONDS+elapsed,cumulative_database_connections=9,cumulative_database_commands=145,observation=observation,historical_cleanup_uncertainty_preserved=True,**memory)
    journal.append('supervisor_result',result)
    return result

def main():
    if sys.platform!='linux' or not sys.stdin.isatty() or not sys.stderr.isatty():raise ValueError('OWNER_TTY')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=REVISION or subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip()!=TREE or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('EXACT_CHECKOUT')
    unexpired()
    if any(os.environ.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_DEBUG')):raise ValueError('KEYRING_REQUIRED')
    from verification.ingestion_storage.memory_enforcement import owner_scope
    owner_scope()
    reg=Path.home()/'stage4-owner/storage-identity-registration.json';body=reg.read_bytes()
    if reg.is_symlink() or hashlib.sha256(body).hexdigest()!='43bb06a2ee93cc77428e056eb8a19b2efe8f98e880ed42d0a0e0b2b69e33d5f3':raise ValueError('BINDING')
    for p,digest in json.loads(body)['hashes'].items():
        if Path(p).is_symlink() or hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('CONTENT')
    helper=Path.home()/'stage4-owner/storage-teardown-readonly.py'
    if helper.is_symlink() or hashlib.sha256(helper.read_bytes()).hexdigest()!=READONLY_SHA:raise ValueError('READONLY_HELPER_BINDING')
    spec=importlib.util.spec_from_file_location('accepted_readonly',helper);readonly=importlib.util.module_from_spec(spec);spec.loader.exec_module(readonly)
    prior=STATE/'storage-teardown-readonly-reconciliation-20261017'
    for name,digest in (('final-result.json',RESULT_SHA),('events.jsonl',AUDIT_SHA),('credential-free-audits.zip',ZIP_SHA)):
        p=prior/name
        if p.is_symlink() or p.stat().st_size>300000 or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('RECONCILIATION_BINDING')
    readonly.check_chain((prior/'events.jsonl').read_bytes())
    evidence=json.loads((prior/'final-result.json').read_bytes())
    if evidence['status']!='READ_ONLY_OBSERVATION_COMPLETE' or evidence['cleanup']!='CLOSED' or evidence['access_verdict']!='DATABASE_ACCESS_DISABLED_SECRET_CLEANUP_PENDING' or evidence['cumulative_supervised_seconds']!=PRIOR_SECONDS:raise ValueError('RECONCILIATION_STATE')
    journal=readonly.Journal(ROOT)
    try:
        journal.append('consumed',dict(authority='OWNER_APPROVED_TWO_TEMPORARY_SECRET_DELETIONS_20261017',names=list(NAMES),limits=dict(deletes=2,gets=1,supervised_seconds=10,memory_bytes=268435456,database_connections=0),prior_result_sha256=RESULT_SHA,archive_sha256=ZIP_SHA,original_expiry=EXPIRY))
        unexpired();result=supervise(journal)
    finally:journal.file.close()
    result.update(audit_bytes=(ROOT/'events.jsonl').stat().st_size,audit_sha256=hashlib.sha256((ROOT/'events.jsonl').read_bytes()).hexdigest(),audit_chain_head=journal.head)
    p=ROOT/'final-result.json'
    with p.open('xb',buffering=0) as f:f.write(canonical(result)+b'\n');os.fsync(f.fileno())
    fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps(result,sort_keys=True));print('Credential-free audit:',ROOT/'events.jsonl');print('Final result:',p)
    if result['status']!='TEMPORARY_SECRETS_REMOVED_ACCESS_DISABLED':raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except BaseException:
        print('FINAL_SECRET_CLEANUP_STOP_NO_RETRY',file=sys.stderr)
        raise SystemExit(1) from None
