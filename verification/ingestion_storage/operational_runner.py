"""One manual capture-once/retained-screening acceptance, not a consumer.

Production entrypoint requires an exact, separately owner-released registration.
The required path never imports or enables an Application writer.
"""
import argparse,hashlib,json,os,resource,signal,socket,subprocess,sys,time
from contextlib import contextmanager
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import quote
from app.ingestion.ledger import digest,DEFAULT_LIMITS,Denied
from app.ingestion.coordinator import Coordinator
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.batching import capture_once,batch_plans,process_batch
from verification.discovery.idox_window import WindowConfig
from .operational_controller import DatabaseBudget,ControllerLedger,batch_allocation
from .operational_publication import GitHub,Uncertain,canonical,BRANCH
from .operational_owner import Owner,item,SCOPE,ROLES,SECRETS
from .tls_trust import verified_trust,owned_resources,PEM_SHA256

AUTHORITY='AUTHORISE_BOLTON_CAPTURE_QUEUE_ONCE_20261018'
QUALIFICATION='1833eb7349dda9b1dceb0924abd7380b2f24e591e13ad34ec37dd8e4763df3f2'
CONTRACT='bolton-received-idox-coordinator-v1'

class Journal:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(mode=0o700,parents=False,exist_ok=False)
        self.file=self.root/'events.jsonl';self.sequence=0;self.head='0'*64
        self.file.touch(mode=0o600,exist_ok=False)
        self.sync_dir()
    def sync_dir(self):
        for p in (self.root,self.root.parent):
            fd=os.open(p,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    def emit(self,event,payload):
        record=dict(sequence=self.sequence,event=event,payload=payload,previous_sha256=self.head)
        head=hashlib.sha256(canonical(record)).hexdigest();raw=canonical(dict(record,sha256=head))+b'\n'
        if self.file.stat().st_size+len(raw)>1024**2:raise Uncertain('AUDIT_BOUND')
        with self.file.open('ab') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        self.sequence+=1;self.head=head
    def save(self,name,value):
        if name not in {'progress.json','final-result.json'}:raise ValueError('CHECKPOINT_PATH')
        raw=canonical(value)
        if len(raw)>256*1024:raise ValueError('CHECKPOINT_BOUND')
        temp=self.root/(name+'.next')
        with temp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        temp.replace(self.root/name);self.sync_dir()
        if (self.root/name).read_bytes()!=raw:raise Uncertain('CHECKPOINT_READBACK')

    def progress(self):
        state=json.loads((self.root/'progress.json').read_bytes());previous='0'*64;sealed=None
        for i,line in enumerate(self.file.read_bytes().splitlines()):
            event=json.loads(line);sha=event.pop('sha256')
            if event['sequence']!=i or event['previous_sha256']!=previous or hashlib.sha256(canonical(event)).hexdigest()!=sha:raise Uncertain('AUDIT_CHAIN_BINDING')
            previous=sha
            if event['event']=='progress_saved':sealed=event['payload']['sha256']
        if previous!=self.head or digest(state)!=sealed:raise Uncertain('DURABLE_PROGRESS_SEAL')
        return state

class Runner:
    """Injected IO enables the actual wrapper to be rehearsed without sources."""
    def __init__(self,registration,journal,connector,*,source_reader,github,
                 url_factory,identity='postgres',ssl=None,memory=None,hostaddr=None,started=None):
        self.r=registration;self.journal=journal;self.emit=journal.emit;self.source_reader=source_reader;self.github=github;self.url_factory=url_factory;self.ssl=ssl;self.memory=memory
        self.started=started if started is not None else time.monotonic();self.phase='admin';self.phase_started=self.started;self.admin_seconds=0;self.runtime_seconds=0;self.hostaddr=hostaddr
        self.expiry=datetime.fromisoformat(registration['expires_at'])
        self.bindings=dict(revision=registration['revision'],workflow_sha256=registration['controller_sha256'],manifest_sha256=registration['manifest_sha256'])
        self.owner=Owner(connector,self.emit,self.check,identity=identity,expiry=self.expiry,bindings=self.bindings)
        self.receipts={};self.plans=[];self.capture=None;self.capture_key=None;self.batch_bindings={};self.evidence_head=registration['evidence_head'];self.closed=True;self.diagnosing=False;self.baseline=owned_resources()

    def check(self):
        now=time.monotonic()
        if self.diagnosing:
            if now-self.started>=475 or self.admin_seconds+now-self.phase_started>=240:raise Denied('DIAGNOSTIC_RESERVE_EXHAUSTED')
            return
        if datetime.now(timezone.utc)>=self.expiry or now-self.started>=450:raise Denied('EXPIRY_OR_JOB_CLOSURE_RESERVE')
        if self.phase=='admin' and self.admin_seconds+now-self.phase_started>=210:raise Denied('ADMIN_TEARDOWN_RESERVE')
        if self.phase=='teardown' and self.admin_seconds+now-self.phase_started>=240:raise Denied('ADMIN_TOTAL_BOUND')
        if self.phase=='runtime' and self.runtime_seconds+now-self.phase_started>=300:raise Denied('RUNTIME_TOTAL_BOUND')
        if (self.journal.root/'STOP').exists():raise Denied('OWNER_STOP')
        if self.memory is not None:self.memory.snapshot()
        size=sum(p.stat().st_size for p in self.journal.root.rglob('*') if p.is_file())
        if size>2*1024**2-16384:raise Denied('COMBINED_OUTPUT_CLOSURE_RESERVE')

    @contextmanager
    def phase_as(self,name):
        old=self.phase;now=time.monotonic()
        if old=='runtime':self.runtime_seconds+=now-self.phase_started
        else:self.admin_seconds+=now-self.phase_started
        self.phase=name;self.phase_started=now
        try:self.check();yield
        finally:
            now=time.monotonic()
            if name=='runtime':self.runtime_seconds+=now-self.phase_started
            else:self.admin_seconds+=now-self.phase_started
            self.phase=old;self.phase_started=now

    def archive(self,raw):
        sha=hashlib.sha256(raw).hexdigest();directory=self.r['evidence_directory']+'/capture'
        self.evidence_head=self.github.publish({'source.json':raw},directory=directory,expected_head=self.evidence_head)
        return dict(commit=self.evidence_head,path=directory+'/source.json',sha256=sha,bytes=len(raw),readback_verified=True)

    @contextmanager
    def slot(self,key,bindings,authority):
        slots=[self.capture_key]+[p['key'] for p in self.plans]
        allocation=batch_allocation(slots,self.receipts,sealed_sha256=digest(self.receipts),slot_key=key)
        remaining=allocation['remaining']
        if remaining['driver_statements']<80 or remaining['connection_attempts']<2:raise Denied('INSUFFICIENT_NEXT_SLOT_RESERVATION')
        prior=self.receipts.get(key,{})
        budget=DatabaseBudget(slot_key=key,previous=prior.get('database'),connections=min(16,remaining['connection_attempts']),statements=min(120,remaining['driver_statements']),seconds=min(165,remaining['supervised_seconds']),returned_bytes=remaining['returned_data_value_bytes'],stop_file=self.journal.root/'STOP')
        engines=[];started=time.monotonic();success=False
        try:
            engines=[budget.engine(self.owner.urls[r],ssl=self.ssl,hostaddr=self.hostaddr) for r in ROLES]
            ledger=ControllerLedger(engines[0],budget=budget,owner='required_once',authority=authority,bindings=bindings,broker_engine=engines[1])
            yield Coordinator(ledger,{CONTRACT:IdoxListingContract(CONTRACT,WindowConfig('bolton','RECEIVED',date(2026,10,16),date(2026,10,16),0),QUALIFICATION)}),budget
            success=True
        finally:
            account=budget.close(engines);elapsed=time.monotonic()-started
            receipt=dict(database=account,supervised_seconds=prior.get('supervised_seconds',0)+elapsed,cleanup=account['cleanup'])
            self.receipts[key]=receipt;self.emit('slot_closed',dict(key=key,receipt=receipt,success=success))
            if account['cleanup']!='CLOSED':self.closed=False;raise Uncertain('RUNTIME_DATABASE_CLOSURE')
            batch_allocation(slots,self.receipts,sealed_sha256=digest(self.receipts),slot_key=key)

    def setup(self):
        account=self.github.call('GET','user')
        if account.get('login')!='maxrose26':raise ValueError('EXACT_OWNER_GITHUB_ACCESS')
        self.owner.preflight();self.owner.install();self.owner.map_and_activate(self.github,url_factory=self.url_factory)
        identity=dict(subject=SCOPE,task='DISCOVERY',contract=CONTRACT,revision=self.r['manifest_sha256'])
        root=item(identity,max_attempts=1,limits=dict(DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
        self.capture_key=root['key'];self.capture_bindings=self.owner.register([root],AUTHORITY+'_CAPTURE',capture_key=self.capture_key,source_calls=1)
        self.emit('required_setup_committed',dict(capture_key=self.capture_key))

    def capture_once(self):
        if self.capture is not None:raise Denied('CAPTURE_ALREADY_RETAINED_NO_SOURCE_REPLAY')
        with self.phase_as('runtime'):
            with self.slot(self.capture_key,self.capture_bindings,AUTHORITY+'_CAPTURE') as (co,budget):
                def read(row):self.check();return self.source_reader(row)
                self.capture=capture_once(co,self.capture_key,read,self.archive,self.check)
        if self.capture['kind']!='LISTING_RECEIPT_V1':
            self.emit('capture_processing_blocked',dict(checkpoint=self.capture));return
        self.plans=batch_plans(self.capture_key,self.capture)
        if self.plans:
            prepared=[]
            for record in self.capture['records']:
                prepared.append(item(dict(subject=dict(kind='APPLICATION',council='bolton',reference=record['reference']),task='SCREENING',contract='listing-screen-v1',revision=digest(record)),dependencies=[self.capture_key]))
            batches=[item({k:p[k] for k in ('subject','task','contract','revision')},dependencies=p['dependencies'],checkpoint=p['checkpoint']) for p in self.plans]
            # The completed capture is also bound for exact retained-parent
            # reads; it is not inserted or granted another source allowance.
            root_binding=item(dict(subject=SCOPE,task='DISCOVERY',contract=CONTRACT,revision=self.r['manifest_sha256']))
            self.batch_bindings=self.owner.register(batches,AUTHORITY+'_SCREEN',capture_key=self.capture_key,source_calls=0,prepared=[root_binding,*prepared])
        self.save_progress()

    def save_progress(self):
        state=dict(capture_key=self.capture_key,capture_sha256=digest(self.capture),plans=self.plans,receipts=self.receipts,receipts_sha256=digest(self.receipts),evidence_head=self.evidence_head)
        self.journal.save('progress.json',state);self.emit('progress_saved',dict(sha256=digest(state)))

    def screen(self,*,pause_after=None):
        # A planned pause is an offline rehearsal injection, not a production
        # CLI option. Resume verifies durable progress and uses no source client.
        saved=self.journal.progress()
        if saved['capture_sha256']!=digest(self.capture) or saved['receipts_sha256']!=digest(self.receipts) or saved['receipts']!=self.receipts:raise Uncertain('DURABLE_PROGRESS_BINDING')
        delivered=0
        for plan in self.plans:
            key=plan['key']
            if key in self.receipts:continue
            with self.phase_as('runtime'):
                with self.slot(key,self.batch_bindings,AUTHORITY+'_SCREEN') as (co,budget):
                    result=process_batch(co,key,check=lambda:(self.check(),budget.check()))
            if result['outcome'] not in {'BATCH_SCREENED','BATCH_ALREADY_COMPLETE'}:raise Uncertain('SCREENING_OUTCOME')
            self.emit('batch_outcome',dict(key=key,outcome=result['outcome'],children=result.get('children',[])))
            delivered+=1;self.save_progress()
            if pause_after is not None and delivered==pause_after:return 'PAUSED_CLOSED_NO_SOURCE_REPLAY'
        return 'SCREENING_COMPLETE'

    @classmethod
    def resume(cls,previous):
        """Fresh bounded queue execution with an existing secure RAM handoff.

        The finite owner supervisor remains alive. Losing that supervisor or
        its credentials is reconciliation-required, never remapping/replay.
        """
        import copy
        previous.check();state=previous.journal.progress()
        if not previous.closed or state['receipts']!=previous.receipts or not previous.owner.urls:raise Uncertain('RESUME_CLOSURE_ACCOUNTING_OR_CREDENTIAL_HANDOFF')
        current=object.__new__(cls);current.__dict__=previous.__dict__.copy()
        current.owner=copy.copy(previous.owner);current.owner.check=current.check;current.github.check=current.check
        current.receipts=json.loads(json.dumps(state['receipts']))
        def no_source(_):raise Denied('RETAINED_EXECUTION_CANNOT_REFETCH')
        current.source_reader=no_source
        with current.phase_as('runtime'):
            with current.slot(current.capture_key,current.capture_bindings,AUTHORITY+'_CAPTURE') as (co,budget):
                root=co.ledger.get(current.capture_key)
                if root['state']!='COMPLETE' or digest(root['checkpoint'])!=state['capture_sha256']:raise Uncertain('CAPTURE_CHECKPOINT_IDENTITY')
                current.capture=root['checkpoint']
        current.plans=batch_plans(current.capture_key,current.capture)
        if current.plans!=state['plans']:raise Uncertain('EXACT_RECOVERED_BATCH_MEMBERSHIP')
        current.emit('retained_execution_reconstructed',dict(capture_sha256=state['capture_sha256'],source_calls=0,counters_carried=True))
        current.save_progress();return current

    def finish(self):
        with self.phase_as('teardown'):self.owner.teardown(self.github)
        self.emit('required_access_disabled',dict(roles=list(ROLES),authorities=self.owner.authorities))
        self.check()
        outcome='CAPTURED_PROCESSING_BLOCKED' if self.capture['kind']!='LISTING_RECEIPT_V1' else 'REQUIRED_CAPTURE_SCREENING_ACCEPTED_ACCESS_DISABLED'
        result=dict(status='ACCESS_DISABLED_FINAL_CLOSURE_PENDING',rows=len(self.capture.get('records',[])),batches=len(self.plans),capture_sha256=digest(self.capture),slot_receipts=self.receipts,admin=dict(connections=self.owner.connections,commands=self.owner.commands,returned_data_value_bytes=self.owner.returned_bytes),unit_facts='UNKNOWN_OUTSIDE_SCOPE',application_writes=0,source_observations=1,cleanup='CLOSURE_PENDING',historical_uncertainty_preserved=True)
        self.emit('required_result',result)
        # The sealed execution chain is archived separately from the publisher's
        # acknowledgement suffix; final owner output supplies that suffix hash.
        self.journal.save('final-result.json',result)
        self.evidence_head=self.github.publish({'events.jsonl':self.journal.file.read_bytes(),'final-result.json':canonical(result)},directory=self.r['evidence_directory']+'/completed',expected_head=self.evidence_head)
        if self.memory is not None:result.update(self.memory.close())
        after=owned_resources()
        if after['children'] or after['socket_fds']-self.baseline['socket_fds']:raise Uncertain('OWNED_PROCESS_OR_SOCKET_CLOSURE')
        result.update(status=outcome,cleanup='CLOSED',native_memory_proof=self.memory is not None)
        from collections import Counter
        from app.ingestion.listing_screening import screen_row
        screens=[screen_row(row) for row in self.capture.get('records',[])]
        usable=sum(x['proposal_usable'] for x in screens)
        if self.capture['kind']=='LISTING_RECEIPT_V1':
            if not screens:outcome='DISCOVERY_EXPLICIT_ZERO_ACCESS_DISABLED_SCREENING_NOT_EXERCISED'
            elif usable<len(screens):outcome='PARTIAL_PROPOSAL_COVERAGE_ACCESS_DISABLED'
        result.update(status=outcome,usable_proposals=usable,screening_dispositions=dict(Counter(x['disposition'] for x in screens)),citation_leads=sum(len(x['citations']['occurrences']) for x in screens),source_resources=self.capture.get('resources'),supervised_seconds=time.monotonic()-self.started,runtime_supervised_seconds=self.runtime_seconds,github_cli_invocations=self.github.requests)
        self.emit('final_closure_verified',dict(status=outcome,cleanup='CLOSED',native_memory_proof=self.memory is not None,new_sockets=0,live_children=0))
        result.update(evidence_commit=self.evidence_head,audit_sha256=hashlib.sha256(self.journal.file.read_bytes()).hexdigest(),audit_chain_head=self.journal.head)
        self.journal.save('final-result.json',result)
        return result

def validate_registration(body,sha):
    if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('REGISTRATION_SHA256')
    r=json.loads(body)
    if r.get('authority')!=AUTHORITY or r.get('status')!='OWNER_APPROVED_REQUIRED_ONCE' or r.get('scope')!=SCOPE or r.get('roles')!=list(ROLES) or r.get('risk_acceptance')!='ACCEPT_POSSIBLE_PROVIDER_SCRAM_VERIFIER_RETENTION_WORKER_EFFECT_ONCE':raise ValueError('EXACT_OPERATIONAL_APPROVAL_REQUIRED')
    expiry=datetime.fromisoformat(r['expires_at']);now=datetime.now(timezone.utc)
    if expiry.tzinfo is None or not now<expiry<=now+timedelta(hours=24):raise ValueError('ORIGINAL_OPERATIONAL_EXPIRY')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if revision!=r['revision'] or subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip()!=r['tree'] or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('CLEAN_REVIEWED_CHECKOUT')
    for path,digest_ in r['hashes'].items():
        p=Path(path)
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest_:raise ValueError('REVIEWED_CONTENT_BINDING')
    controller=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if r['controller_sha256']!=controller or r['ca_sha256']!=PEM_SHA256 or not r['evidence_directory'].startswith('docs/design/ingestion-operational-execution-'):raise ValueError('CONTROLLER_CA_EVIDENCE_BINDING')
    return r

def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',type=Path,required=True);p.add_argument('--registration-sha256',required=True);a=p.parse_args()
    if sys.platform!='linux' or not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('OWNER_LINUX_SECURE_TTY_REQUIRED')
    if any(os.environ.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN','GH_DEBUG','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN')):raise SystemExit('EXISTING_KEYRING_AUTH_ONLY')
    if os.environ.get('GH_HOST','github.com')!='github.com' or any(os.environ.get(k) for k in ('GH_CONFIG_DIR','GH_HTTP_UNIX_SOCKET','SSL_CERT_FILE','SSL_CERT_DIR','HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy','ALL_PROXY','all_proxy')):raise SystemExit('UNREVIEWED_GITHUB_ROUTE_OR_TRUST_OVERRIDE')
    if any(k.startswith('PG') for k in os.environ):raise SystemExit('LIBPQ_ENVIRONMENT_OVERRIDE')
    if a.registration.is_symlink() or a.registration.stat().st_size>32768:raise SystemExit('REGISTRATION_BOUND')
    r=validate_registration(a.registration.read_bytes(),a.registration_sha256)
    from .operational_memory import OperationalMemory
    memory=OperationalMemory() # Positive kernel enforcement BEFORE credentials.
    state=Path.home()/'.local/state/propertyaigent';state.mkdir(mode=0o700,exist_ok=True,parents=True)
    journal=Journal(state/'operational-capture-queue-once-20261018')
    journal.emit('consumed',dict(authority=AUTHORITY,registration_sha256=a.registration_sha256))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    from .credential_mapping import secure_migration_input
    from verification.discovery.route_validation import validate_route
    raw=secure_migration_input();started=time.monotonic();runner=None
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(Uncertain('HARD_JOB_DEADLINE')));signal.alarm(475)
    try:
        if datetime.now(timezone.utc)>=datetime.fromisoformat(r['expires_at']):raise ValueError('ORIGINAL_OPERATIONAL_EXPIRY')
        u=validate_route(raw)
        if not isinstance(u.password,str) or not u.password:raise ValueError('EXPLICIT_MIGRATION_PASSWORD_REQUIRED')
        ca,_=verified_trust()
        # Hard DNS timeout in a credential-free exec, not an unbounded libc
        # lookup inside a thread that could survive its timeout.
        command=[sys.executable,'-c',"import socket,json;print(json.dumps(sorted({x[4][0] for x in socket.getaddrinfo('aws-0-eu-west-2.pooler.supabase.com',5432,family=socket.AF_INET,type=socket.SOCK_STREAM)})))"]
        dns=subprocess.run(command,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3)
        addresses=json.loads(dns.stdout)
        if dns.returncode or not isinstance(addresses,list) or not 1<=len(addresses)<=32:raise ValueError('BOUND_DNS_RESULT')
        import ipaddress
        if any(ipaddress.ip_address(x).version!=4 for x in addresses):raise ValueError('REVIEWED_IPV4_ONLY')
        selected=addresses[0]
        import psycopg
        def connect():return psycopg.connect(host=u.host,hostaddr=selected,port=u.port,dbname=u.database,user=u.username,password=u.password,sslmode='verify-full',sslrootcert=str(ca),connect_timeout=3,prepare_threshold=None,autocommit=True,options='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000')
        holder={};github=GitHub(journal.emit,lambda:holder['runner'].check())
        from .operational_source import read
        def reader(_):return read('listing',dict(council='bolton',semantics='RECEIVED',start='2026-10-16',end='2026-10-16'),root=journal.root/'source',stop_file=journal.root/'STOP',memory_group=memory.source)
        def url(role,password):return 'postgresql://'+quote(role+'.zcikcfgpblzuzpanpdqd',safe='')+':'+quote(password,safe='')+'@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'
        runner=Runner(r,journal,connect,source_reader=reader,github=github,url_factory=url,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},memory=memory,hostaddr=selected,started=started);holder['runner']=runner
        runner.setup();runner.capture_once()
        if runner.plans:runner.screen()
        result=runner.finish()
        print(json.dumps(result,sort_keys=True))
    except BaseException as exc:
        # No automatic credential reset, compensating cleanup or write retry.
        # Actual read-only diagnostics may be collected within reserves only.
        diagnostics={'status':'NOT_OBSERVED'}
        import re
        code=str(exc) if isinstance(exc,(Denied,Uncertain,ValueError)) and re.fullmatch('[A-Z0-9_]{1,100}',str(exc)) else 'REDACTED_EXECUTION_FAILURE'
        sqlstate=getattr(getattr(exc,'orig',exc),'sqlstate',None)
        sqlstate=sqlstate if isinstance(sqlstate,str) and re.fullmatch('[A-Z0-9]{5}',sqlstate) else None
        try:
            if runner is None:raise ValueError('NO_CONNECTION_ATTEMPTED')
            runner.diagnosing=True
            diagnostics=runner.owner.diagnostics()
            names=github.names();journal.emit('failure_secret_names_observed',dict(names={n:n in names for n in SECRETS.values()},database_url_present='DATABASE_URL' in names))
        except BaseException:journal.emit('failure_diagnostics_incomplete',dict(status='UNKNOWN_NO_MUTATION'))
        closure={'status':'UNKNOWN'}
        try:closure=memory.close()
        except BaseException:pass
        journal.emit('stopped',dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',reason=code,sqlstate=sqlstate,roles=list(ROLES),secret_names=list(SECRETS.values()),diagnostics=diagnostics,owned_cleanup=closure))
        print(json.dumps(dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',reason=code,sqlstate=sqlstate,audit=str(journal.file),audit_sha256=hashlib.sha256(journal.file.read_bytes()).hexdigest())))
        raise SystemExit(1) from None
    finally:signal.alarm(0)

if __name__=='__main__':main()
