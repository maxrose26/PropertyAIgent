"""Fixed owner-only pilot bridge over the existing issuer, runtime and closure.

No scheduler, token, role creation or source reader lives here. The existing
web process supplies protected configuration; the actual daily job receives
only the two finite restricted credentials. Recovery journals use the existing
Vault format, encrypted in the approved private evidence table.
"""
import copy
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import tempfile
import time
import zlib
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo

from . import intake_owner as op
from .intake_owner_io import Vault,env_values,service_guard,KEEP,handoff,submission_check,restore_handoff,reconcile_handoff
from .intake_owner_operations import COUNCILS,SCREENING,issue_period,validate_policy
from .database_evidence import BACKEND,canonical,migration_sql,verify_inventory
from .restricted_route import url,ROUTES
from .tls_trust import verified_trust

PREDECESSOR='b-dbpilot-20261027-1102-04'
PERIOD='b-dbpilot-20261027-1102-05'
OWNER_PERIOD=PERIOD+'_owner'
OWNER_RUN=hashlib.sha256(OWNER_PERIOD.encode()).hexdigest()[:32]
SERVICE='crn-d9sv93vavr4c73f98rb0'
WORKSPACE='tea-d9qbf8jm8hqs7385cu0g'
WINDOW={'start':'2026-10-27','end':'2026-11-02'}
RELEASE_PARENT=Path('/tmp')
TERMINAL={'succeeded','failed','canceled'}
DEPLOY_TERMINAL={'live','deactivated','build_failed','update_failed','canceled','pre_deploy_failed'}

# Serialized VALUE ceilings; keys/separators are included in the reserve below.
# These are owner-journal bounds, not new source, provider or database budgets.
CLEANUP_RECORD_LIMITS={'first_failure':512,'failure':512,'closure_failure':512,'restoration_failure':512,
    'closure_receipt':2048,'restoration_receipt':1024,'final_service':128,'closure_verification':1024}
CLEANUP_STATE_GROWTH=512  # access/render state flags, status, counters and base-size metadata
CLEANUP_MARGIN=1024      # additional plaintext margin, beyond supported record maxima
CLEANUP_SNAPSHOTS=16     # 8 cleanup + first failure + verification + 4 reconciliation + 2 margin

def ciphertext_size(n):
    # Existing Vault: 16-byte salt + base64(Fernet 57-byte overhead + PKCS7 AES).
    return 16+4*((57+16*(n//16+1)+2)//3)

# Fixed normal metadata only. Cleanup records/counters and durable intents stay
# outside this lossless container, so their reserved growth remains unchanged.
JOURNAL_METADATA_FIELDS=frozenset(('binding','access','artifact','profile','policy','startup_preflight','observations','job','job_terminal','runtime_qualification','source_result','independent_result','original_environment','stable_credentials','stable_configuration'))

def serialized_state(value):
    stored=copy.deepcopy(value)
    if isinstance(stored,dict) and stored.get('cleanup_reserve',{}).get('version') in ('CLEANUP_RESERVE_V1','CLEANUP_RESERVE_DIAGNOSTIC02_36K_V1'):
        if isinstance(stored.get('binding'),dict) and canonical(stored.get('access',{}).get('binding'))==canonical(stored['binding']):
            stored['access']['binding']=dict(version='ROOT_BINDING_REFERENCE_V1',sha256=hashlib.sha256(canonical(stored['binding'])).hexdigest())
        metadata={k:stored[k] for k in JOURNAL_METADATA_FIELDS if k in stored}
        raw=canonical(metadata)
        if len(raw)<=65536:
            packed=dict(version='JOURNAL_METADATA_DEFLATE_V1',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(zlib.compress(raw,9)).decode('ascii'))
            if len(canonical(packed))+128<len(raw):
                op.require('journal_metadata' not in stored,'OWNER_CODE_BINDING')
                for key in metadata:del stored[key]
                stored['journal_metadata']=packed
    return stored

def state_size(value):return len(canonical(serialized_state(value)))

def hydrated_state(stored):
    if isinstance(stored,dict):
        packed=stored.get('journal_metadata')
        if packed is not None:
            try:
                op.require(stored.get('cleanup_reserve',{}).get('version') in ('CLEANUP_RESERVE_V1','CLEANUP_RESERVE_DIAGNOSTIC02_36K_V1') and isinstance(packed,dict) and set(packed)=={'version','bytes','sha256','data'} and packed['version']=='JOURNAL_METADATA_DEFLATE_V1' and type(packed['bytes']) is int and 0<=packed['bytes']<=65536,'OWNER_CODE_BINDING')
                compressed=base64.b64decode(packed['data'],validate=True)
                op.require(len(compressed)<=32768,'OWNER_CODE_BINDING')
                decoder=zlib.decompressobj();raw=decoder.decompress(compressed,packed['bytes']+1)
                op.require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and len(raw)==packed['bytes'] and hashlib.sha256(raw).hexdigest()==packed['sha256'],'OWNER_CODE_BINDING')
                decoded=json.loads(raw)
                op.require(isinstance(decoded,dict) and set(decoded)<=JOURNAL_METADATA_FIELDS and not set(decoded).intersection(stored) and canonical(decoded)==raw,'OWNER_CODE_BINDING')
                del stored['journal_metadata'];stored.update(decoded)
            except (ValueError,TypeError,KeyError,zlib.error):raise op.Denied('OWNER_CODE_BINDING') from None
        binding=stored.get('access',{}).get('binding',{})
        if isinstance(binding,dict) and binding.get('version')=='ROOT_BINDING_REFERENCE_V1':
            op.require(set(binding)=={'version','sha256'} and stored.get('cleanup_reserve',{}).get('version') in ('CLEANUP_RESERVE_V1','CLEANUP_RESERVE_DIAGNOSTIC02_36K_V1') and
                binding['sha256']==hashlib.sha256(canonical(stored.get('binding'))).hexdigest(),'OWNER_CODE_BINDING')
            stored['access']['binding']=copy.deepcopy(stored['binding'])
    return stored

def cleanup_reserve_policy(period=None,version=None):
    expanded=period=='b-qualification-20261104-02' and version!='CLEANUP_RESERVE_V1'
    limit=36864 if expanded else 32768
    growth=sum(len(canonical(k))+1+n+1 for k,n in CLEANUP_RECORD_LIMITS.items())+CLEANUP_STATE_GROWTH
    maximum=max(n for n in range(limit+1) if ciphertext_size(n+growth+CLEANUP_MARGIN)<=limit)
    return dict(version='CLEANUP_RESERVE_DIAGNOSTIC02_36K_V1' if expanded else 'CLEANUP_RESERVE_V1',record_limits=dict(CLEANUP_RECORD_LIMITS),
        growth_bytes=growth,margin_bytes=CLEANUP_MARGIN,normal_plaintext_ceiling=maximum,
        reserved_snapshots=CLEANUP_SNAPSHOTS)

def bounded_failure(exc,phase):
    result=safe_result(exc)
    value={k:result[k] for k in ('reason','exception_class','sqlstate')}
    value['phase']=phase if phase in {'RUN','RELEASE','PERIOD','ACTIVATE','HANDOFF','ONE_JOB','CLEANUP'} else 'RUN'
    if type(result.get('http_status')) is int:value['http_status']=result['http_status']
    op.require(len(canonical(value))<=512,'OWNER_CLEANUP_RECORD_BOUND')
    return value

def period_checkpoint(value):
    """Root binding/policy are already durable; retain exact references, not copies."""
    return dict(version='ROOT_REFERENCED_PERIOD_CHECKPOINT_V1',state=value['state'],
        binding_ref='binding',policy_ref='policy',binding_sha256=hashlib.sha256(canonical(value['binding'])).hexdigest(),
        policy_sha256=hashlib.sha256(canonical(value['policy'])).hexdigest())

@contextmanager
def envelope(seconds=60):
    """Same60-second active envelope; never nested with another phase envelope."""
    previous=signal.getsignal(signal.SIGALRM)
    op.require(seconds in (40,60),'OWNER_PHASE_ENVELOPE')
    def refuse(*_):raise op.Denied('OWNER_PHASE_60_SECONDS' if seconds==60 else 'OWNER_RENDER_CLIENT_TIME_LIMIT')
    signal.signal(signal.SIGALRM,refuse);signal.setitimer(signal.ITIMER_REAL,seconds)
    try:yield
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

class Database:
    def __init__(self,environ=None):
        from sqlalchemy.engine import make_url
        env=os.environ if environ is None else environ
        u=make_url(env.get('DATABASE_URL','sqlite://'))
        op.require(u.get_backend_name() in ('postgres','postgresql') and (u.host,u.port,u.database,u.username)==('aws-0-eu-west-2.pooler.supabase.com',5432,'postgres','postgres.zcikcfgpblzuzpanpdqd') and bool(u.password),'CONFIGURED_OWNER_SESSION_ROUTE_REQUIRED')
        self.u=u
        self.key=hashlib.sha256(('propertyaigent-owner-pilot-v1\0'+u.password).encode()).hexdigest()
        # Fresh IPv4 DNS observation; no fallback endpoint or address guessing.
        self.address=socket.getaddrinfo(u.host,u.port,socket.AF_INET,socket.SOCK_STREAM)[0][4][0]
    @contextmanager
    def connection(self):
        import psycopg
        ca,_=verified_trust()
        with psycopg.connect(host=self.u.host,hostaddr=self.address,port=5432,dbname='postgres',user=self.u.username,password=self.u.password,
                sslmode='verify-full',sslrootcert=str(ca),connect_timeout=5,gssencmode='disable',prepare_threshold=None,autocommit=True,
                application_name='propertyaigent_owner_pilot',options='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000') as c:
            yield c
        op.require(c.closed,'OWNER_CONNECTION_CLOSURE')

class Journal:
    def __init__(self,db,period=PERIOD):
        op.require(period in (PERIOD,PREDECESSOR),'OWNER_JOURNAL_PERIOD')
        self.db=db;self.period=period;self.owner_period=period+'_owner';self.owner_run=hashlib.sha256(self.owner_period.encode()).hexdigest()[:32];self.previous='';self.state=None;self.ordinal=-1
    def _vault(self,raw=None,value=None):
        # Only encrypted bytes touch the temporary filesystem. No new credential
        # is persisted; recovery derives its key from existing protected config.
        with tempfile.TemporaryDirectory(prefix='propertyaigent-owner-') as folder:
            p=Path(folder)/'state.vault'
            if raw is None:
                limit=36864 if self.period=='b-qualification-20261104-02' and value.get('cleanup_reserve',{}).get('version')=='CLEANUP_RESERVE_DIAGNOSTIC02_36K_V1' else 32768
                v=Vault(p,self.db.key,create=True,limit=limit);v.save(serialized_state(value));return p.read_bytes()
            fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as f:f.write(raw)
            return hydrated_state(Vault(p,self.db.key,limit=36864 if self.period=='b-qualification-20261104-02' else 32768).load())
    def load(self):
        with self.db.connection() as c:
            row=c.execute('SELECT * FROM public.ingestion_intake_owner_state(%s,%s,%s,NULL::bytea)',(self.owner_period,self.owner_run,'')).fetchone()
        if row is None:return None
        raw=bytes(row[1]);op.require(hashlib.sha256(raw).hexdigest()==row[2],'OWNER_JOURNAL_HASH')
        self.previous=row[2];self.ordinal=row[0];self.ciphertext_bytes=len(raw);self.state=self._vault(raw=raw)
        op.require(self.state.get('period')==self.period,'OWNER_JOURNAL_PERIOD')
        return copy.deepcopy(self.state)
    def save(self,state,connection=None,*,validate_only=False):
        reserve=state.get('cleanup_reserve')
        if self.state and self.state.get('cleanup_reserve'):
            op.require(reserve is not None and all(reserve.get(k)==self.state['cleanup_reserve'].get(k) for k in cleanup_reserve_policy(self.period,self.state['cleanup_reserve'].get('version'))),'OWNER_CLEANUP_RESERVE_IMMUTABLE')
            if 'first_failure' in self.state:op.require(state.get('first_failure')==self.state['first_failure'],'OWNER_FIRST_FAILURE_IMMUTABLE')
        if reserve is not None:
            policy=cleanup_reserve_policy(self.period,reserve.get('version'))
            op.require(all(reserve.get(k)==v for k,v in policy.items()),'OWNER_CLEANUP_RESERVE_IMMUTABLE')
            prior=(self.state or {}).get('cleanup_reserve',{})
            used=prior.get('cleanup_writes',0)
            op.require(type(used) is int and 0<=used<=CLEANUP_SNAPSHOTS,'OWNER_CLEANUP_ROW_BOUND')
            for k,limit in CLEANUP_RECORD_LIMITS.items():
                op.require(k not in state or len(canonical(state[k]))<=limit,'OWNER_CLEANUP_RECORD_BOUND')
            reserve=copy.deepcopy(reserve);state['cleanup_reserve']=reserve
            if getattr(self,'cleanup_mode',False):
                op.require(used<CLEANUP_SNAPSHOTS and self.ordinal<63,'OWNER_CLEANUP_ROW_BOUND')
                if 'cleanup_base_bytes' not in prior:
                    reserve['cleanup_base_bytes']=state_size(self.state)
                    reserve['cleanup_base_access_bytes']=len(canonical((self.state or {}).get('access',{})))
                else:
                    for k in ('cleanup_base_bytes','cleanup_base_access_bytes'):reserve[k]=prior[k]
                reserve['cleanup_writes']=used+1
                op.require(len(canonical(state.get('access',{})))<=reserve['cleanup_base_access_bytes']+CLEANUP_STATE_GROWTH,'OWNER_CLEANUP_RECORD_BOUND')
                op.require(state_size(state)<=reserve['cleanup_base_bytes']+policy['growth_bytes']+CLEANUP_MARGIN,'OWNER_CLEANUP_RESERVE_BYTE_BOUND')
            else:
                op.require(used==0,'OWNER_NO_NORMAL_AFTER_CLEANUP')
                reserve['cleanup_writes']=0
                op.require(self.ordinal+1<=63-CLEANUP_SNAPSHOTS,'OWNER_CLEANUP_ROW_BOUND')
                op.require(state_size(state)<=policy['normal_plaintext_ceiling'],'OWNER_CLEANUP_RESERVE_BYTE_BOUND')
        raw=self._vault(value=state);h=hashlib.sha256(raw).hexdigest()
        if validate_only:return len(raw)  # same checks/encryption, no SQL or state advance
        def write(c):
            if connection is not None:
                from psycopg.pq import TransactionStatus
                op.require(c.pgconn.transaction_status==TransactionStatus.IDLE,'OWNER_JOURNAL_REQUIRES_AUTOCOMMIT_BOUNDARY')
            return c.execute('SELECT * FROM public.ingestion_intake_owner_state(%s,%s,%s,%s)',(self.owner_period,self.owner_run,self.previous,raw)).fetchone()
        if connection is not None:row=write(connection)
        else:
            with self.db.connection() as c:row=write(c)
        # No repetition after uncertain acknowledgement. Independent load is
        # available even if this exact write committed but its reply was lost.
        op.require(row is not None and bytes(row[1])==raw and row[2]==h,'OWNER_JOURNAL_ACK_RECONCILE')
        self.previous=h;self.ordinal=row[0];self.ciphertext_bytes=len(raw);self.state=copy.deepcopy(state)

class Render:
    """Fixed-service transport, reviewed control-plane limits, no automatic retry."""
    def __init__(self,token,*,session=None,clock=time.monotonic):
        import requests
        self.session=session or requests.Session();self.session.trust_env=False
        self.token=token;self.clock=clock;self.started=clock();self.calls=0;self.total=0
    def limit_refusal(self,hits,*,seen=0,limit=32768):
        exc=op.Denied('OWNER_RENDER_'+'_AND_'.join(hits))
        exc.limits={'requests_started':self.calls,'request_limit':8,'response_bytes_seen':min(seen,limit+4096),
            'response_byte_limit':limit,'aggregate_bytes_seen':min(self.total,786432+4096),'aggregate_byte_limit':786432,
            'elapsed_ms':min(60000,max(0,int((self.clock()-self.started)*1000))),'client_time_limit_ms':40000,'limit_hits':hits}
        raise exc
    def call(self,method,suffix='',body=None):
        startup=method=='GET' and re.fullmatch(r'startup:job-[a-z0-9]{20}',suffix)
        qualification=method=='GET' and re.fullmatch(r'qualification:job-[a-z0-9]{20}',suffix)
        artifact=method=='GET' and re.fullmatch(r'artifact:[0-9TZ:.+-]{20,40}',suffix)
        allowed=(method=='GET' and suffix in ('','/env-vars?limit=100','/jobs?limit=100','/deploys?limit=100','/secret-files?limit=100') or
                 method=='GET' and re.fullmatch(r'/(jobs/job-|deploys/dep-)[a-z0-9]{20}',suffix) or
                 method=='PUT' and suffix=='/env-vars' or method=='PATCH' and suffix=='' or
                 method=='POST' and suffix in ('/resume','/suspend','/jobs') or artifact or qualification or startup)
        op.require(allowed,'OWNER_RENDER_FIXED_OPERATION')
        before=[]
        if self.calls>=8:before.append('REQUEST_LIMIT')
        if self.clock()-self.started>=40:before.append('CLIENT_TIME_LIMIT')
        if before:self.limit_refusal(before)
        self.calls+=1;limit=524288 if suffix=='/deploys?limit=100' else 65536 if method=='GET' and suffix=='/jobs?limit=100' else 32768
        target='https://api.render.com/v1/services/'+SERVICE+suffix
        if artifact:
            from urllib.parse import urlencode
            target='https://api.render.com/v1/logs?'+urlencode(dict(ownerId=WORKSPACE,resource=SERVICE,text='DATABASE_PILOT_BUILD_RECEIPT',startTime=suffix.split(':',1)[1],limit=5,direction='backward'))
        if qualification:
            from urllib.parse import urlencode
            target='https://api.render.com/v1/logs?'+urlencode(dict(ownerId=WORKSPACE,resource=suffix.split(':',1)[1],text='DATABASE_PILOT_RUNTIME_QUALIFICATION',limit=5,direction='backward'))
        if startup:
            from urllib.parse import urlencode
            target='https://api.render.com/v1/logs?'+urlencode(dict(ownerId=WORKSPACE,resource=suffix.split(':',1)[1],text='DATABASE_PILOT_STARTUP_GUARD',limit=5,direction='backward'))
        with self.session.request(method,target,
                headers={'Authorization':'Bearer '+self.token,'Accept':'application/json'},json=body,
                timeout=(3,5),allow_redirects=False,stream=True) as r:
            expected=202 if suffix in ('/resume','/suspend') else 201 if method=='POST' and suffix=='/jobs' else 200
            if r.status_code!=expected:
                refusal=op.Denied('OWNER_RENDER_HTTP_REFUSED_OR_UNCERTAIN')
                refusal.http_status=r.status_code;refusal.requests=self.calls
                raise refusal
            raw=bytearray()
            for chunk in r.iter_content(4096):
                raw.extend(chunk);self.total+=len(chunk)
                hits=[]
                if len(raw)>limit:hits.append('RESPONSE_BYTE_LIMIT')
                if self.total>786432:hits.append('AGGREGATE_BYTE_LIMIT')
                if self.clock()-self.started>=40:hits.append('CLIENT_TIME_LIMIT')
                if hits:self.limit_refusal(hits,seen=len(raw),limit=limit)
            if self.clock()-self.started>=40:self.limit_refusal(['CLIENT_TIME_LIMIT'],seen=len(raw),limit=limit)
            return json.loads(raw) if raw else None
    def close(self):self.session.close()

def complete_inventory(value,kind):
    op.require(type(value) is list and len(value)<100,'OWNER_COMPLETE_INVENTORY_REQUIRED')
    result=[];seen=set()
    for entry in value:
        row=entry.get(kind,entry)
        op.require(type(row) is dict and row.get('id') not in seen and isinstance(row.get('createdAt'),str),'OWNER_INVENTORY_SHAPE')
        created=datetime.fromisoformat(row['createdAt'].replace('Z','+00:00')).timestamp()
        op.require(created>0 and row.get('status') in (TERMINAL if kind=='job' else DEPLOY_TERMINAL),'OWNER_CURRENT_WORK_OR_UNKNOWN_STATUS')
        op.require(row.get('finishedAt') or kind=='deploy' and row.get('status')=='deactivated','OWNER_INVENTORY_FINISH_REQUIRED')
        seen.add(row['id']);result.append(row)
    return result

def source_profile(artifact,revision):
    op.require(artifact.get('execution_binding',{}).get('revision')==revision and artifact.get('browser_canary')=='LAUNCHED_AND_CLOSED','OWNER_BUILD_RECEIPT_BINDING')
    return dict(mode='render-intake-v1',service_id=SERVICE,revision=revision,browser_path=artifact['browser_path'],browser_sha256=artifact['browser_sha256'],
                aggregate_bytes=2147483648,source_rss_bytes=1073741824,controller_rss_bytes=268435456,reserve_bytes=536870912,source_seconds=75)

def start_availability(now=None):
    """Display availability without consuming authority or sliding a deadline."""
    now=time.time() if now is None else now
    day=datetime.fromtimestamp(now,ZoneInfo('Europe/London'))
    midnight=datetime.combine(day.date()+timedelta(days=1),datetime.min.time(),ZoneInfo('Europe/London')).timestamp()
    return dict(available=now+2100<=midnight,next_available_at=now if now+2100<=midnight else midnight,
                latest_start_today=midnight-2100,access_seconds=2100,window=WINDOW)

def fixed_binding(release,profile,address,guard,now=None):
    now=time.time() if now is None else now
    day=datetime.fromtimestamp(now,ZoneInfo('Europe/London'))
    midnight=datetime.combine(day.date()+timedelta(days=1),datetime.min.time(),ZoneInfo('Europe/London')).timestamp()
    op.require(now+2100<=midnight,'OWNER_FULL_DAY_AND_CLOSURE_MARGIN')
    b=dict(version='FINITE_INTAKE_OWNER_V1',period=PERIOD,route='POOLER',hostaddr=address,owner_hostaddr=address,
           execution_binding=release['execution_binding'],accepted_stop=op.ACCEPTED_STOP,evidence_backend=BACKEND,fixed_window=WINDOW,
           render_profile=profile,render_config_sha256=guard,retained_deployment=release['deployment'],valid_until=now+2100,runtime_deadline=now+1915,
           timing_policy=dict(version='SEPARATE_EXPIRY_V2_RESERVE',bound_at=now,execution_day=day.date().isoformat()))
    policy=dict(expires_at=b['runtime_deadline'],max_runs=1,overlap_days=7,councils=COUNCILS,expected_stop=op.ACCEPTED_STOP,
        execution_binding=b['execution_binding'],test_evidence=False,screening_config=SCREENING,hostaddr=address,route='POOLER',render_profile=profile,
        evidence_backend=BACKEND,fixed_window=WINDOW,access_deadline=b['valid_until'])
    b['period_policy_sha256']=hashlib.sha256(canonical(policy)).hexdigest()
    op.validate_binding(b,opening=True,now=now)
    return b,policy

def safe_result(exc):
    # A closed allowlist, never arbitrary exception messages or environment.
    code=getattr(exc,'sqlstate',None)
    known={'OWNER_STARTUP_PREFLIGHT_DRIFT','OWNER_STARTUP_PREFLIGHT_JOB','OWNER_STARTUP_PREFLIGHT_EVIDENCE','OWNER_CONTINUATION_PREDECESSOR','ACCESS_DISABLED_BUT_MEMBERSHIP_RECONCILIATION_REQUIRED',
     'ACCESS_DISABLE_READBACK',
     'ACTIVATION_COMMITTED_READBACK',
     'ACTIVATION_GATE_DERIVATION',
     'ACTIVATION_LEDGER_CHANGED',
     'ACTIVATION_MEMBERSHIP_POSTCONDITION',
     'ACTIVATION_SETTINGS_POSTCONDITION',
     'ACTIVATION_STOP_CHANGED',
     'BOTH_EXPLICIT_STOP_DECISIONS_REQUIRED',
     'CONTROLLER_CEILING',
     'CLOSURE_AUTHORITY_BINDING',
     'CLOSURE_AUTHORITY_BOUND',
     'CLOSURE_AUTHORITY_READBACK',
     'CLOSURE_CONTROL_POSTCONDITION',
     'CLOSURE_RUN_BINDING',
     'CLOSURE_SETTINGS_DRIFT',
     'CLOSURE_SETTINGS_POSTCONDITION',
     'CLOSURE_STATE',
     'CLOSURE_UNRELATED_MEMBERSHIP_DRIFT',
     'COMPLETE_JOB_INVENTORY_REQUIRED',
     'CONFIGURED_OWNER_SESSION_ROUTE_REQUIRED',
     'CONFIGURED_RENDER_KEY_REQUIRED',
     'CONFIGURED_SOURCE_RELEASE_REQUIRED',
     'DATABASE_CLOSURE_FIRST',
     'EXACT_GENERATION5_STOP_REQUIRED',
     'EXACT_RENDER_PROFILE_FIELDS_AND_LIMITS',
     'EXACT_REVIEWED_APPLICATION_REQUIRED',
     'EXISTING_PIPELINE_SESSION',
     'EXISTING_RUNTIME_ADMIN_CAPABILITIES_REQUIRED',
     'FINITE_EXECUTION_RESERVE_BINDING',
     'FINITE_FIXED_DEADLINE',
     'FINITE_OWNER_VALIDITY',
     'FINITE_SELF_REVOCABLE_PUBLICATION_TOKEN',
     'FINITE_TIMING_POLICY',
     'HANDOFF_CREDENTIAL_WINDOW',
     'HANDOFF_RECONCILIATION_REQUIRED',
     'HANDOFF_SINGLE_USE',
     'INDEPENDENT_ARCHIVE_OR_ZERO',
     'INDEPENDENT_AUTHORITY_CLOSURE',
     'INDEPENDENT_BOTH_CAPTURE_AUTHORITIES',
     'INDEPENDENT_CAPTURE',
     'INDEPENDENT_COUNCILS',
     'INDEPENDENT_DATABASE_BYTES',
     'INDEPENDENT_DATABASE_EVENTS',
     'INDEPENDENT_DATABASE_REPORT',
     'INDEPENDENT_DATABASE_SOURCE_BYTES',
     'INDEPENDENT_FINALISATION_BINDING',
     'INDEPENDENT_PUBLICATION_BINDING',
     'INDEPENDENT_SCREENING_BATCHES',
     'INDIRECT_RUNTIME_CAPABILITY',
     'INSTALLATION_TOKEN_ONLY',
     'INTAKE_OWNER_CAPABILITY_ACL',
     'INTAKE_OWNER_FUNCTION_INVENTORY',
     'JOB_EXISTS_REQUIRES_NAMED_TERMINAL_READBACK',
     'MINT_B_AND_CLOSURE_WINDOW',
     'MINT_RECEIPT_BINDING',
     'OLDHAM_HISTORICAL_BINDING_CHANGED',
     'OLDHAM_HISTORICAL_ROOT_CHANGED',
     'OLDHAM_RETAINED_BINDINGS_HASH',
     'OLDHAM_REVOKED_STATE_CHANGED',
     'OPERATION_OBSERVATION_BINDING',
     'OPERATION_OBSERVATION_DRIFT',
     'OPERATION_OBSERVATION_STALE',
     'OPERATION_VAULT_BINDING',
     'OWNER_ADMIN_IPV4',
     'OWNER_ADMIN_ONLY_BASELINE',
     'OWNER_BINDING',
     'OWNER_BUILD_CONFIGURATION_READBACK',
     'OWNER_BUILD_ENV_RESTORE_DRIFT',
     'OWNER_BUILD_ENV_RESTORE_READBACK',
     'OWNER_BUILD_FILE_BINDING',
     'OWNER_BUILD_RECEIPT_BINDING',
     'OWNER_BUILD_RECEIPT_REQUIRED',
     'OWNER_BUILD_REQUIRED',
     'OWNER_BUILD_RESTORE_DRIFT',
     'OWNER_BUILD_RESTORE_READBACK',
     'OWNER_BUILD_REVISION_DRIFT',
     'OWNER_CODE_BINDING',
     'OWNER_COMPLETE_INVENTORY_REQUIRED',
     'OWNER_CONFIGURATION_DRIFT',
     'OWNER_CONNECTION_CLOSURE',
     'OWNER_CURRENT_WORK_OR_UNKNOWN_STATUS',
     'OWNER_DATABASE_PILOT_SCOPE',
     'OWNER_ENVIRONMENT_DRIFT',
     'OWNER_FULL_DAY_AND_CLOSURE_MARGIN',
     'OWNER_IDENTITY',
     'OWNER_INHERITED_BOUNDARY_REQUIRED',
     'OWNER_INVENTORY_FINISH_REQUIRED',
     'OWNER_INVENTORY_SHAPE',
     'OWNER_IPV4',
     'OWNER_JOB_ACK_UNCERTAIN',
     'OWNER_JOURNAL_ACK_RECONCILE',
     'OWNER_JOURNAL_HASH',
     'OWNER_JOURNAL_PERIOD',
     'OWNER_JOURNAL_REQUIRES_AUTOCOMMIT_BOUNDARY',
     'OWNER_MORE_THAN_ONE_BUILD',
     'OWNER_NO_RECOVERY_STATE',
     'OWNER_OBSERVATION_ALREADY_USED',
     'OWNER_OPEN_OR_UNVERIFIED',
     'OWNER_PERIOD',
     'OWNER_PERIOD_ALREADY_USED',
     'OWNER_PREBUILD_DRIFT',
     'OWNER_PREBUILD_ENVIRONMENT_READBACK',
     'OWNER_PRIOR_ATTEMPT_RECONCILE',
     'OWNER_PRIOR_INTENT_RECONCILE',
     'OWNER_RENDER_CLIENT_TIME_LIMIT',
     'OWNER_RENDER_FIXED_OPERATION',
     'OWNER_RENDER_HTTP_REFUSED_OR_UNCERTAIN',
     'OWNER_RENDER_REQUEST_OR_TIME_LIMIT',
     'OWNER_RENDER_TRANSPORT_UNCERTAIN',
     'OWNER_RESTORE_UNCERTAIN_NO_RETRY',
     'OWNER_RESTRICTED_AUTHENTICATION_REFUSED',
     'OWNER_RESTRICTED_CONNECTION_NOT_CLOSED',
     'OWNER_RESUSPEND_READBACK',
     'OWNER_RETAINED_ARTIFACT_DRIFT',
     'OWNER_ROUTE',
     'OWNER_SECRET_FILES_DRIFT',
     'OWNER_SERVICE_OR_PLAN_CHANGED',
     'OWNER_SESSION_VISIBILITY',
     'OWNER_SOURCE_BRANCH_BINDING',
     'OWNER_STOP_BINDING',
     'OWNER_STOP_CHANGED',
     'OWNER_UNEXPECTED_BUILD',
     'OWNER_UNEXPECTED_RESUMPTION',
     'PASSWORD_ENTROPY_BOUND',
     'PERIOD_ALREADY_EXISTS_NO_RETRY',
     'PERIOD_COMMITTED_READBACK',
     'PERIOD_DATABASE_FIXED_DEADLINES',
     'PERIOD_EXACT_POLICY',
     'PERIOD_EXACT_TEMPORARY_ISSUER',
     'PERIOD_EXISTING_ISSUER_ADMIN_ONLY',
     'PERIOD_FIXED_DEADLINE',
     'PERIOD_JOURNAL_BINDING',
     'PERIOD_LEDGER_POSTCONDITION',
     'PERIOD_POLICY_HASH',
     'PERIOD_PRIVILEGE_RESTORATION',
     'PERIOD_PROFILE',
     'PERIOD_REGISTRATION_READBACK',
     'PERIOD_REVIEWED_BINDINGS',
     'PERIOD_ROUTE_EXPIRY',
     'PERIOD_SERVER_EXPIRY',
     'PERIOD_SINGLE_RUN',
     'PERIOD_STOP_CHANGED',
     'PRIVATE_VAULT_REQUIRED',
     'READBACK_EXPORT_BOUND',
     'READBACK_RUN_ID',
     'RECOVERED_ATTEMPT_CHANGED',
     'RECOVERED_ATTEMPT_MISSING',
     'RECOVERED_ROOT_CHANGED',
     'REGISTRAR_NARROW_ACL',
     'RENDER_BOUND_INTEGER_PROFILE',
     'RENDER_COMMAND_SCHEDULE',
     'RENDER_COMPLETE_ENV_PAGE_REQUIRED',
     'RENDER_ENV_SHAPE',
     'RENDER_FINITE_BOUND',
     'RENDER_FIXED_OPERATION',
     'RENDER_HANDOFF_READBACK',
     'RENDER_JOB_NOT_TERMINAL',
     'RENDER_PROFILE_MAPPING_REQUIRED',
     'RENDER_RESPONSE_BOUND',
     'RENDER_RESPONSE_UNCERTAIN',
     'RENDER_RESTORE_DRIFT',
     'RENDER_RESTORE_READBACK',
     'RENDER_REVIEWED_CONFIGURATION',
     'RENDER_SAFETY_CONTROLS',
     'RESTORATION_PRIOR_INTENT_RECONCILE_NO_RETRY',
     'REVIEWED_INHERITED_BOUNDARY_REQUIRED',
     'ROLE_SETTINGS_SCOPE',
     'ROLE_SETTINGS_VALUE',
     'RUNTIME_MEMBERSHIP_PRESENT',
     'RUNTIME_NOT_DORMANT',
     'SELF_REVOCABLE_INSTALLATION_TOKEN_REQUIRED',
     'SERVER_FINITE_VALIDITY',
     'SESSIONS_UNRESOLVED',
     'SETUP_TEN_MINUTE_BOUND',
     'STOP_COMMITTED_READBACK',
     'STOP_POSTCONDITION',
     'STOP_PRIVILEGE_CLEANUP',
     'SUBMISSION_CURRENT_STATE_DRIFT',
     'SUBMISSION_HANDOFF_REQUIRED',
     'SUBMISSION_INTENT_PATH',
     'SUBMISSION_PRIOR_INTENT_NO_RETRY',
     'TEMPORARY_OWNER_CAPABILITY_REMAINS',
     'TERMINAL_JOB_ID_REQUIRED',
     'TOKEN_PRIOR_INTENT_RECONCILE_NO_RETRY',
     'TOKEN_PRIVATE_BINDING',
     'TOKEN_REVIEWED_SCOPE_REQUIRED',
     'UNEXPIRED_OR_UNREADABLE_AUTHORITY',
     'UNFINISHED_INTAKE_RUN',
     'UNRESOLVED_EFFECT_INTENT',
     'VAULT_32K_BOUND','VAULT_36K_BOUND',
     'VAULT_INCOMPLETE',
     'VAULT_PASSPHRASE_LENGTH'}
    from itertools import combinations
    for n in range(1,4):
        known.update('OWNER_RENDER_'+'_AND_'.join(parts) for parts in combinations(('RESPONSE_BYTE_LIMIT','AGGREGATE_BYTE_LIMIT','CLIENT_TIME_LIMIT'),n))
    known.update({'OWNER_RENDER_REQUEST_LIMIT','OWNER_RENDER_REQUEST_LIMIT_AND_CLIENT_TIME_LIMIT'})
    known.update({'OWNER_CONTINUATION_PREDECESSOR','OWNER_CONTINUATION_DUPLICATE','OWNER_CONTINUATION_MIGRATION','OWNER_CONTINUATION_PRESERVATION','OWNER_CONTINUATION_QUALIFICATION', 'OWNER_RESULT_RUN_BINDING','OWNER_RESULT_EVIDENCE_BINDING','OWNER_JOURNAL_REQUIRES_AUTOCOMMIT_BOUNDARY'})
    known.update('ARTIFACT_RECONCILIATION_'+x for x in ('CONFIGURATION','HASH','CODE','BROWSER','STATE','CONFLICT','PREDECESSOR','REFUSAL','CURRENT_STATE','DURABLE_READBACK'))
    known.update({'DRIVER_STATEMENT_BOUND','SERVER_TIMEOUT_OR_RESTRICTED_IDENTITY_PROFILE','REVIEWED_TLS_ENDPOINT_REQUIRED','RESTRICTED_ROUTE_MISMATCH','LIBPQ_ENVIRONMENT_OVERRIDE','RUNTIME_TRANSACTION_MODE','PINNED_REVIEWED_ADDRESS_REQUIRED','CONNECTION_BOUND','MANUAL_STOP_OR_CONTROLLER_DEADLINE'})
    known.update({'OWNER_CLOSURE_ARCHIVE_BINDING','STABLE_CREDENTIALS_REQUIRED','STABLE_VERIFIER_BINDING','STABLE_CONFIGURATION_PRECONDITION','STABLE_CONFIGURATION_PRESERVATION','RUNTIME_AUTHENTICATION_REFUSED','RUNTIME_QUALIFICATION_EVIDENCE'})
    known.update({'OWNER_CLEANUP_RESERVE_BYTE_BOUND','OWNER_CLEANUP_ROW_BOUND','OWNER_CLEANUP_RECORD_BOUND','OWNER_CLEANUP_RESERVE_IMMUTABLE','OWNER_FIRST_FAILURE_IMMUTABLE','OWNER_NO_NORMAL_AFTER_CLEANUP'})
    reason=str(exc) if isinstance(exc,op.Denied) and str(exc) in known else 'UNKNOWN_FAILURE'
    sql_reason=getattr(getattr(exc,'diag',None),'message_primary',None)
    if sql_reason in ('DATABASE_EVIDENCE_MIGRATION_PRECONDITION','DATABASE_EVIDENCE_UNRESOLVED_STATE','DATABASE_EVIDENCE_EXACT_CLEANUP_OR_PRESERVATION','DATABASE_EVIDENCE_FUNCTION_OR_ACL_BINDING','OWNER_STATE_BUSY','OWNER_STATE_HISTORY_BOUND','OWNER_STATE_CONCURRENT_OR_UNCERTAIN','OWNER_STATE_VAULT_BOUND'):reason=sql_reason
    result=dict(status='RECONCILIATION_REQUIRED',reason=reason,sqlstate=code if type(code) is str and re.fullmatch('[0-9A-Z]{5}',code) else None)
    classes={'Denied','ValueError','KeyError','TypeError','AttributeError','IndexError','JSONDecodeError','OperationalError','ProgrammingError','DataError','InterfaceError','RuntimeError','ConnectionError','Timeout','ConnectTimeout','ReadTimeout','SSLError','HTTPError'}
    result['exception_class']=type(exc).__name__ if type(exc).__name__ in classes else 'UNKNOWN_CLASS'
    status=getattr(exc,'http_status',None)
    if type(status) is int and 100<=status<=599:result['http_status']=status;result['requests']=getattr(exc,'requests',None)
    if reason.startswith('OWNER_RENDER_') and hasattr(exc,'limits'):result['limits']=exc.limits
    return result

def private_failure(exc,phase):
    """Diagnostic frames only: no exception message, source lines or locals."""
    import traceback
    names={'owner_pilot.py','intake_owner.py','intake_owner_io.py','intake_owner_operations.py','owner_managed_pilot.py'}
    frames=[]
    for frame in traceback.extract_tb(exc.__traceback__)[-12:]:
        name=Path(frame.filename).name
        if name in names and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,80}',frame.name):
            frames.append({'file':name,'function':frame.name,'line':min(10000,max(0,frame.lineno))})
    return dict(safe_result(exc),phase=phase,frames=frames,messages='OMITTED',locals='OMITTED')

BUILD_COMMAND='export PLAYWRIGHT_BROWSERS_PATH=0; pip install -r requirements.txt && playwright install chromium && python -m scripts.verify_browser_runtime && python -m scripts.owner_pilot_artifact'

class Pilot:
    """One fixed accepted pilot. Each consequential phase has a durable intent.

    This connects existing operations; it cannot select councils/windows, reset
    a failed attempt or automatically replace an uncertain write/job/build.
    """
    def __init__(self,db=None,*,token=None,render_factory=None,sleep=time.sleep):
        self.db=db or Database();self.journal=Journal(self.db)
        self.token=token or os.environ.get('PROPERTYAIGENT_INTAKE_RENDER_API_KEY')
        op.require(type(self.token) is str and bool(self.token),'CONFIGURED_RENDER_KEY_REQUIRED')
        self.render_factory=render_factory or (lambda:Render(self.token));self.sleep=sleep
        self.state=None
    @contextmanager
    def api(self):
        api=self.render_factory()
        try:
            with envelope(40):yield api
        finally:api.close()
    def save(self):self.journal.save(self.state)
    def intent(self,name):
        op.require(name not in self.state['intents'],'OWNER_PRIOR_INTENT_RECONCILE')
        self.state['intents'][name]={'at':time.time(),'state':'INTENT_NO_RETRY'};self.save()
    def ack(self,name):self.state['intents'][name]['state']='ACKNOWLEDGED';self.save()
    def access_save(self,value):self.state['access']=copy.deepcopy(value);self.save()
    def period_save(self,value):self.state['period_journal']=copy.deepcopy(value);self.save()
    @contextmanager
    def cleanup_writes(self):
        journal=getattr(self,'journal',None)
        before=getattr(journal,'cleanup_mode',False)
        if journal is not None:journal.cleanup_mode=True
        try:yield
        finally:
            if journal is not None:journal.cleanup_mode=before
    def arm_cleanup_reserve(self):
        op.require(self.state.get('status')=='ARTIFACT_READY' and 'RELEASE' not in self.state['intents'],'OWNER_PRIOR_ATTEMPT_RECONCILE')
        if 'cleanup_reserve' in self.state:
            reserve=self.state['cleanup_reserve'];policy=cleanup_reserve_policy(self.state.get('period'),reserve.get('version'))
            op.require(all(reserve.get(k)==v for k,v in policy.items()) and reserve.get('cleanup_writes')==0 and
                not any(k in self.state for k in ('binding','access','first_failure')),'OWNER_PRIOR_ATTEMPT_RECONCILE')
            return  # confirmed pre-intent reservation; no new write or deadline
        candidate=self.reserved_candidate()
        self.journal.save(candidate);self.state=candidate
    def reserved_candidate(self):
        candidate=copy.deepcopy(self.state)
        fields=('original_service','original_deploy_ids','build_guard','build_environment','build_receipt_created_at','startup_job','startup_job_terminal','startup_command','source_revision')
        present=[n for n in fields if n in candidate]
        artifact_keys={'execution_binding','browser_canary','browser_path','browser_sha256'}
        if isinstance(candidate.get('artifact'),dict) and set(candidate['artifact'])-artifact_keys:present.append('artifact')
        if present:
            op.require('closed_build_archive' not in candidate and all(candidate['intents'].get(n,{}).get('state')=='ACKNOWLEDGED' for n in ('RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT')),'OWNER_CLOSURE_ARCHIVE_BINDING')
            candidate['closed_build_archive']=dict(prior_ciphertext_sha256=self.journal.previous,prior_ordinal=self.journal.ordinal,
                fields={n:hashlib.sha256(canonical(candidate[n])).hexdigest() for n in present})
            artifact={k:v for k,v in candidate.get('artifact',{}).items() if k in artifact_keys}
            for n in present:del candidate[n]
            if 'artifact' in present:candidate['artifact']=artifact
        candidate['cleanup_reserve']=dict(cleanup_reserve_policy(candidate.get('period')),cleanup_writes=0)
        return candidate
    def record_first_failure(self,exc):
        # A rejected oversized working copy must not prevent its failure record.
        # Reload only the last acknowledged baseline; durable effect intents stay.
        names=list(self.state.get('intents',{}))
        phase=max(enumerate(names),key=lambda item:(self.state['intents'][item[1]].get('at',0),item[0]),default=(0,'RUN'))[1]
        diagnostic=bounded_failure(exc,phase)
        print('PROPERTYAIGENT_OWNER_PILOT_FAILURE_OBSERVED '+json.dumps(diagnostic,sort_keys=True,separators=(',',':')),flush=True)
        self.state=self.journal.load()
        if self.state.get('first_failure') is not None:return
        print('PROPERTYAIGENT_OWNER_PILOT_FIRST_FAILURE '+json.dumps(diagnostic,sort_keys=True,separators=(',',':')),flush=True)
        self.state['first_failure']=diagnostic
        self.state['failure']=copy.deepcopy(diagnostic);self.state['pipeline_status']='NOT_VERIFIED'
        with self.cleanup_writes():self.save()
    def record_cleanup_failure(self,exc,key):
        op.require(key in ('closure_failure','restoration_failure'),'OWNER_CLEANUP_RECORD_BOUND')
        diagnostic=bounded_failure(exc,'CLEANUP')
        if self.state.get('cleanup_reserve') and not self.state.get('first_failure'):
            self.state['first_failure']=copy.deepcopy(diagnostic)
            self.state['failure']=copy.deepcopy(diagnostic)
            print('PROPERTYAIGENT_OWNER_PILOT_FIRST_FAILURE '+json.dumps(diagnostic,sort_keys=True,separators=(',',':')),flush=True)
        self.state[key]=diagnostic
        with self.cleanup_writes():self.save()
    def migrate(self):
        # This explicit owner action is never performed by normal page loads.
        # Unknown acknowledgement cannot fall through to activation.
        with envelope(),self.db.connection() as c:
            exists=c.execute("SELECT to_regclass('public.ingestion_run_evidence') IS NOT NULL").fetchone()[0]
            if not exists:
                c.execute(migration_sql())
                while c.pgconn.get_result() is not None:pass
            op.inventory(c);verify_inventory(c);op.owner_absent(c)
    def preflight(self):
        with envelope(),self.db.connection() as c:
            op.identity(c);op.inventory(c);verify_inventory(c);op.dormant(c,stable_verifiers=(self.state or {}).get('stable_credentials',{}).get('verifier_sha256'));op.owner_absent(c)
            ctl=op.control(c);op.require(op.stop_snapshot(ctl)==op.ACCEPTED_STOP,'OWNER_STOP_CHANGED')
            op.retained_cleanup(c,ctl);op.no_hazards(c,ctl)
            op.require(PERIOD not in ctl.get('intake_periods',{}),'OWNER_PERIOD_ALREADY_USED')
        with self.api() as api:
            service=api.call('GET');guard=service_guard(service)
            op.require(service.get('ownerId')==WORKSPACE and service['serviceDetails']['plan']=='standard','OWNER_SERVICE_OR_PLAN_CHANGED')
            jobs=complete_inventory(api.call('GET','/jobs?limit=100'),'job')
            deploys=complete_inventory(api.call('GET','/deploys?limit=100'),'deploy')
            original=env_values(api.call('GET','/env-vars?limit=100'))
        op.require(set(original)=={'DATABASE_URL','PLANNING_STATUS_VERIFICATION_ENABLED','PLAYWRIGHT_BROWSERS_PATH','PYTHONUNBUFFERED'},'OWNER_ENVIRONMENT_DRIFT')
        # The configured harmless settings and inherited boundary are retained
        # from the accepted owner inspection. Fresh direct-map equality is
        # rechecked before handoff/submission; no secret value is exported.
        return service,guard,jobs,deploys,original
    def build(self):
        service,guard,jobs,deploys,original=self.preflight()
        release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
        op.require(type(release.get('branch')) is str and release['branch']=='prep/b-timing-pg17-current-20261103','OWNER_SOURCE_BRANCH_BINDING')
        self.state.update(original_service=service,original_environment=original,original_guard=guard,
            original_deploy_ids=[x['id'] for x in deploys],source_revision=release['execution_binding']['revision'])
        self.save()
        harmless={k:v for k,v in original.items() if k in ('PLAYWRIGHT_BROWSERS_PATH','PYTHONUNBUFFERED')}
        self.state['build_environment']=harmless
        self.intent('BUILD_ENVIRONMENT')
        with self.api() as api:
            op.require(service_guard(api.call('GET'))==guard and env_values(api.call('GET','/env-vars?limit=100'))==original,'OWNER_PREBUILD_DRIFT')
            api.call('PUT','/env-vars',[{'key':k,'value':v} for k,v in sorted(harmless.items())])
            op.require(env_values(api.call('GET','/env-vars?limit=100'))==harmless,'OWNER_PREBUILD_ENVIRONMENT_READBACK')
        self.ack('BUILD_ENVIRONMENT')
        self.intent('BUILD_CONFIGURATION')
        patch={'branch':release['branch'],'serviceDetails':{'envSpecificDetails':{'buildCommand':BUILD_COMMAND,'startCommand':'/bin/true'}}}
        expected=copy.deepcopy(service);expected['branch']=release['branch'];expected['serviceDetails']['envSpecificDetails'].update(patch['serviceDetails']['envSpecificDetails'])
        self.state['build_guard']=service_guard(expected);self.save()
        with self.api() as api:
            op.require(service_guard(api.call('GET'))==guard and env_values(api.call('GET','/env-vars?limit=100'))==harmless,'OWNER_PREBUILD_DRIFT')
            complete_inventory(api.call('GET','/jobs?limit=100'),'job');complete_inventory(api.call('GET','/deploys?limit=100'),'deploy')
            api.call('PATCH','',patch);configured=api.call('GET')
            op.require(service_guard(configured)==self.state['build_guard'],'OWNER_BUILD_CONFIGURATION_READBACK')
        self.ack('BUILD_CONFIGURATION')
        # Resume is the ONE build allowance. Never also POST /deploys.
        self.intent('ONE_RESUME_BUILD')
        with self.api() as api:
            op.require(service_guard(api.call('GET'))==self.state['build_guard'] and env_values(api.call('GET','/env-vars?limit=100'))==harmless,'OWNER_PREBUILD_DRIFT')
            complete_inventory(api.call('GET','/jobs?limit=100'),'job')
            prior=complete_inventory(api.call('GET','/deploys?limit=100'),'deploy')
            op.require({x['id'] for x in prior}==set(self.state['original_deploy_ids']),'OWNER_UNEXPECTED_BUILD')
            api.call('POST','/resume')
        self.ack('ONE_RESUME_BUILD')
        new=None
        for _ in range(20):
            self.sleep(15)
            with self.api() as api:rows=api.call('GET','/deploys?limit=100')
            op.require(type(rows) is list and len(rows)<100,'OWNER_COMPLETE_INVENTORY_REQUIRED')
            added=[x.get('deploy',x) for x in rows if x.get('deploy',x).get('id') not in self.state['original_deploy_ids']]
            op.require(len(added)<=1,'OWNER_MORE_THAN_ONE_BUILD')
            if added:
                new=added[0]
                op.require(new.get('commit',{}).get('id')==self.state['source_revision'],'OWNER_BUILD_REVISION_DRIFT')
                if new.get('status') in DEPLOY_TERMINAL:break
        op.require(new is not None and new.get('status')=='live','OWNER_BUILD_REQUIRED')
        self.state['deployment']=new['id'];self.state['build_receipt_created_at']=new['createdAt'];self.save()
        self.intent('RESUSPEND')
        with self.api() as api:api.call('POST','/suspend');op.require(api.call('GET').get('suspended')=='suspended','OWNER_RESUSPEND_READBACK')
        self.ack('RESUSPEND')
        with self.api() as api:
            logs=api.call('GET','artifact:'+new['createdAt'])
        op.require(logs.get('hasMore') is False and len(logs.get('logs',[]))==1,'OWNER_BUILD_RECEIPT_REQUIRED')
        line=logs['logs'][0]['message'];prefix='DATABASE_PILOT_BUILD_RECEIPT '
        op.require(line.startswith(prefix),'OWNER_BUILD_RECEIPT_REQUIRED')
        artifact=json.loads(line[len(prefix):]);profile=source_profile(artifact,self.state['source_revision'])
        op.require(artifact['execution_binding']==release['execution_binding'],'OWNER_BUILD_FILE_BINDING')
        self.state['artifact']=artifact;self.state['profile']=profile;self.save()
        self.restore_build()
    def restore_build(self):
        service=self.state['original_service'];details=service['serviceDetails']['envSpecificDetails']
        with self.api() as api:
            current=api.call('GET');observed=service_guard(current)
            if observed!=self.state['original_guard']:
                op.require(observed==self.state['build_guard'],'OWNER_BUILD_RESTORE_DRIFT')
                complete_inventory(api.call('GET','/jobs?limit=100'),'job');complete_inventory(api.call('GET','/deploys?limit=100'),'deploy')
                self.intent('RESTORE_BUILD_CONFIGURATION')
                api.call('PATCH','',{'branch':service['branch'],'serviceDetails':{'envSpecificDetails':{'buildCommand':details['buildCommand'],'startCommand':'/bin/true'}}})
                op.require(service_guard(api.call('GET'))==self.state['original_guard'],'OWNER_BUILD_RESTORE_READBACK')
                self.ack('RESTORE_BUILD_CONFIGURATION')
        with self.api() as api:
            environment=env_values(api.call('GET','/env-vars?limit=100'))
            if environment!=self.state['original_environment']:
                op.require(environment==self.state['build_environment'] and service_guard(api.call('GET'))==self.state['original_guard'],'OWNER_BUILD_ENV_RESTORE_DRIFT')
                complete_inventory(api.call('GET','/jobs?limit=100'),'job');complete_inventory(api.call('GET','/deploys?limit=100'),'deploy')
                self.intent('RESTORE_BUILD_ENVIRONMENT')
                api.call('PUT','/env-vars',[{'key':k,'value':v} for k,v in sorted(self.state['original_environment'].items())])
                op.require(env_values(api.call('GET','/env-vars?limit=100'))==self.state['original_environment'] and service_guard(api.call('GET'))==self.state['original_guard'],'OWNER_BUILD_ENV_RESTORE_READBACK')
                self.ack('RESTORE_BUILD_ENVIRONMENT')
    def startup_preflight(self):
        """One packaged-runtime guard check, before any finite-access opening."""
        release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
        command='/usr/bin/timeout --signal=TERM --kill-after=2s 30s python -B -u -m scripts.owner_pilot_job --period '+PERIOD+' --hostaddr 127.0.0.1 --startup-check-only'
        self.state['startup_command']=command
        self.intent('STARTUP_PREFLIGHT_JOB')
        with self.api() as api:
            op.require(service_guard(api.call('GET'))==self.state['original_guard'] and env_values(api.call('GET','/env-vars?limit=100'))==self.state['original_environment'],'OWNER_STARTUP_PREFLIGHT_DRIFT')
            complete_inventory(api.call('GET','/jobs?limit=100'),'job')
            deployments=complete_inventory(api.call('GET','/deploys?limit=100'),'deploy')
            latest=max(deployments,key=lambda x:x['createdAt'])
            op.require(latest['id']==self.state['deployment'] and latest['commit']['id']==release['execution_binding']['revision'],'OWNER_STARTUP_PREFLIGHT_DRIFT')
            job=api.call('POST','/jobs',{'startCommand':command})
        op.require(type(job) is dict and re.fullmatch('job-[a-z0-9]{20}',job.get('id','')) and job.get('serviceId')==SERVICE and job.get('startCommand')==command,'OWNER_JOB_ACK_UNCERTAIN')
        self.state['startup_job']=job;self.ack('STARTUP_PREFLIGHT_JOB')
        for _ in range(30):
            self.sleep(2)
            with self.api() as api:observed=api.call('GET','/jobs/'+job['id'])
            op.require(observed.get('id')==job['id'] and observed.get('status') in TERMINAL|{'pending','running'},'OWNER_STARTUP_PREFLIGHT_JOB')
            if observed['status'] in TERMINAL:break
        self.state['startup_job_terminal']=observed;self.save()
        op.require(observed.get('status')=='succeeded' and observed.get('finishedAt'),'OWNER_STARTUP_PREFLIGHT_JOB')
        with self.api() as api:logs=api.call('GET','startup:'+job['id'])
        op.require(logs.get('hasMore') is False and len(logs.get('logs',[]))==1,'OWNER_STARTUP_PREFLIGHT_EVIDENCE')
        line=logs['logs'][0]['message'];prefix='DATABASE_PILOT_STARTUP_GUARD '
        op.require(line.startswith(prefix),'OWNER_STARTUP_PREFLIGHT_EVIDENCE')
        receipt=json.loads(line[len(prefix):])
        op.require(receipt.get('status')=='CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION' and receipt.get('period')==PERIOD and
            receipt.get('execution_binding')==release['execution_binding'] and receipt.get('tree')==release['tree'] and
            receipt.get('cwd')=='/opt/render/project/src' and receipt.get('git')==dict(exit_status=0,tracked_changes=False) and
            receipt.get('authentication_attempts')==0 and receipt.get('source_requests')==0,'OWNER_STARTUP_PREFLIGHT_EVIDENCE')
        with self.api() as api:
            op.require(service_guard(api.call('GET'))==self.state['original_guard'] and env_values(api.call('GET','/env-vars?limit=100'))==self.state['original_environment'],'OWNER_STARTUP_PREFLIGHT_DRIFT')
        with envelope(),self.db.connection() as c:
            op.dormant(c,stable_verifiers=self.state['stable_credentials']['verifier_sha256']);op.owner_absent(c)
            op.no_hazards(c,op.control(c))
        self.state['startup_preflight']={'job_id':job['id'],'receipt':receipt,'sha256':hashlib.sha256(canonical(receipt)).hexdigest(),
            'readback':dict(runtime_access='DISABLED',configuration_equal=True,environment_equal=True,suspended=True)}
        self.save()

    def prepare_continuation(self):
        from .owner_pilot_continuation import migrate_owner_namespace,predecessor
        prior=Journal(self.db,PREDECESSOR);old=prior.load();link=predecessor(old,snapshot={'ordinal':prior.ordinal,'bytes':prior.ciphertext_bytes,'sha256':prior.previous})
        with envelope(),self.db.connection() as c:migrate_owner_namespace(c,stable_verifiers=old['stable_credentials']['verifier_sha256'])
        preserved=prior.load()
        op.require(prior.previous==link['snapshot']['sha256'] and prior.ordinal==46 and prior.ciphertext_bytes==29084 and hashlib.sha256(canonical(preserved)).hexdigest()==link['state_sha256'],'OWNER_CONTINUATION_PRESERVATION')
        existing=self.journal.load()
        if existing is not None:
            op.require(existing.get('period')==PERIOD and existing.get('status')=='PREPARATION_REFUSED' and
                existing.get('failure',{}).get('reason')=='OWNER_CLEANUP_RESERVE_BYTE_BOUND' and
                not any(k in existing for k in ('binding','access','job','period_journal')) and
                'RELEASE' not in existing.get('intents',{}) and 'ONE_JOB' not in existing.get('intents',{}),'OWNER_CONTINUATION_DUPLICATE')
            self.state=existing;check=self.inspect();current=check['current_readback']
            op.require(not check['period_present'] and check['runtime_membership_count']==0 and check['pipeline_session_count']==0 and check['temporary_owner_absent'] and check['stable_verifier_binding']=='MATCH' and
                all(not r['login'] for r in check['runtime_roles']) and all(current[k] for k in ('suspended','configuration_equal','environment_equal')),'OWNER_CONTINUATION_PRESERVATION')
            self.state['preparation_failure']=copy.deepcopy(self.state['failure'])
            self.state['preparation_refusal_reference']=dict(prior_ciphertext_sha256=self.journal.previous,prior_ordinal=self.journal.ordinal,
                diagnostic_sha256=hashlib.sha256(canonical(self.state.get('private_failure_detail'))).hexdigest())
            self.state.pop('private_failure_detail',None)
            self.state['status']='ARTIFACT_READY'
            release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']);release['deployment']=self.state['deployment']
            b,policy=self.construct_release_binding(release)
            self.preview_release_capacity(b,policy)  # refuse without spending another snapshot
            self.save()
            try:result=self.verify_release_binding()
            except BaseException:
                self.state['status']='PREPARATION_REFUSED';self.save();raise
            print('PROPERTYAIGENT_OWNER_PILOT_RELEASE_CHECK '+json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
            return
        op.require(self.journal.load() is None,'OWNER_CONTINUATION_DUPLICATE')
        self.state={'period':PERIOD,'version':'OWNER_PLATFORM_PILOT_V1','intents':{},'status':'PREPARING','github_publication':'NOT_REQUESTED','predecessor':link}
        self.save()
        try:
            self.state['stable_credentials']=copy.deepcopy(old['stable_credentials'])
            self.state['stable_configuration']=copy.deepcopy(old['stable_configuration'])
            self.state['credential_reuse']={'predecessor':PREDECESSOR,'verifiers':'UNCHANGED_NO_CONFIGURATION_WRITE'}
            self.save()
            print('PROPERTYAIGENT_OWNER_PILOT_INITIAL_JOURNAL '+json.dumps(dict(period=PERIOD,ciphertext_bytes=self.journal.ciphertext_bytes,ordinal=self.journal.ordinal,predecessor_snapshot=link['snapshot']),sort_keys=True),flush=True)
            self.build();self.startup_preflight();self.state['status']='ARTIFACT_READY';self.save()
            result=self.verify_release_binding();print('PROPERTYAIGENT_OWNER_PILOT_RELEASE_CHECK '+json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
        except BaseException as exc:
            self.state['failure']=safe_result(exc);self.state['failure']['phase']=max(self.state['intents'],key=lambda x:self.state['intents'][x]['at'],default='PREPARE');self.state['private_failure_detail']=private_failure(exc,self.state['failure']['phase']);self.state['status']='PREPARATION_REFUSED';self.save()
            self.recover_build();raise
    def prepare(self):
        self.migrate()
        op.require(self.journal.load() is None,'OWNER_PRIOR_ATTEMPT_RECONCILE')
        self.state={'period':PERIOD,'version':'OWNER_PLATFORM_PILOT_V1','intents':{},'status':'PREPARING','github_publication':'NOT_REQUESTED'}
        self.save()
        try:
            self.build();self.state['status']='ARTIFACT_READY';self.save()
        except BaseException as exc:
            self.state['failure']=safe_result(exc);self.state['failure']['phase']=max(self.state['intents'],key=lambda x:self.state['intents'][x]['at'],default='PREPARE');self.state['status']='PREPARATION_REFUSED';self.save()
            self.state['private_failure_detail']=private_failure(exc,self.state['failure']['phase']);self.save()
            self.recover_build();raise
    def recover_build(self):
        if 'original_service' not in self.state:return
        with self.api() as api:current=api.call('GET')
        if current.get('suspended')!='suspended':
            op.require('ONE_RESUME_BUILD' in self.state['intents'],'OWNER_UNEXPECTED_RESUMPTION')
            self.intent('RESUSPEND')
            with self.api() as api:api.call('POST','/suspend');op.require(api.call('GET').get('suspended')=='suspended','OWNER_RESUSPEND_READBACK')
            self.ack('RESUSPEND')
        self.restore_build()
    def observation(self,operation,owner_checked_at):
        # Owner's single button confirms the Dashboard-only inherited-group
        # fact; actual service/work/file reads are taken at their consuming
        # operations, never copied from a historical receipt.
        op.require(type(owner_checked_at) in (int,float) and 0<=time.time()-owner_checked_at<=300,'OWNER_INHERITED_BOUNDARY_REQUIRED')
        b=self.state['binding']
        with self.api() as api:
            op.require(service_guard(api.call('GET'))==b['render_config_sha256'],'OWNER_CONFIGURATION_DRIFT')
            complete_inventory(api.call('GET','/jobs?limit=100'),'job')
            deploys=complete_inventory(api.call('GET','/deploys?limit=100'),'deploy')
            op.require(api.call('GET','/secret-files?limit=100')==[],'OWNER_SECRET_FILES_DRIFT')
        ordered=sorted(deploys,key=lambda x:x['createdAt'],reverse=True)
        op.require(ordered and ordered[0]['id']==b['retained_deployment'] and ordered[0]['commit']['id']==b['execution_binding']['revision'] and ordered[0]['status']=='live','OWNER_RETAINED_ARTIFACT_DRIFT')
        now=time.time()
        value=dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=operation,binding_sha256=hashlib.sha256(canonical(b)).hexdigest(),
            service_id=SERVICE,observed_at=now,env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,
            other_activity_stopped=True,deployment_id=b['retained_deployment'],revision=b['execution_binding']['revision'],suspended=True)
        op.require(operation not in self.state.setdefault('observations',{}),'OWNER_OBSERVATION_ALREADY_USED')
        self.state['observations'][operation]={'provider_observation':value,'owner_boundary_confirmed_at':owner_checked_at};self.save()
        return value
    def qualify(self):
        from .operational_controller import DatabaseBudget
        from .tls_trust import verified_trust
        from sqlalchemy import text
        b=self.state['binding'];ca,_=verified_trust()
        out=[]
        for role,cap in op.ROLES.items():
            # Includes driver initialisation and the existing eight-statement
            # cleanup reserve; four is below DatabaseBudget's admitted minimum.
            budget=DatabaseBudget(statements=20,connections=1,returned_bytes=8192,seconds=12)
            try:
                engine=budget.engine(url('POOLER',role,self.state['access']['passwords'][role]),ssl={'sslmode':'verify-full','sslrootcert':str(ca)},hostaddr=b['hostaddr'],route='POOLER')
                with engine.connect() as c:
                    row=c.execute(text("SELECT current_user,session_user,pg_has_role(current_user,:cap,'USAGE'),current_setting('statement_timeout'),current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout')"),{'cap':cap}).one()
                    op.require(tuple(row)==(role,role,True,'10s','3s','20s'),'OWNER_RESTRICTED_AUTHENTICATION_REFUSED')
            finally:
                closed=budget.close([])
                self.state.setdefault('qualification_attempts',[]).append(dict(role=role,**{k:closed[k] for k in ('driver_statements','connection_attempts','returned_data_value_bytes','elapsed_seconds','connections_closed','cleanup','connection_diagnostics')}))
            op.require(closed['connections_closed'] and closed['cleanup']=='CLOSED' and all(c.closed for c in budget.opened) and budget.failed_native_closed,'OWNER_RESTRICTED_CONNECTION_NOT_CLOSED')
            out.append({'role':role,'attempts':budget.attempts,'closed':True})
        return out
    def release_preflight(self):
        """Shared Run boundary; reads and validation only, before release intent."""
        self.state=self.journal.load()
        op.require(self.state is not None and self.state.get('period')==PERIOD and self.state['status']=='ARTIFACT_READY' and 'RELEASE' not in self.state['intents'],'OWNER_PRIOR_ATTEMPT_RECONCILE')
        service,guard,jobs,deploys,environment=self.preflight()
        op.require(guard==self.state['original_guard'] and environment==self.state['original_environment'],'OWNER_PREBUILD_DRIFT')
        release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
        latest=max(deploys,key=lambda row:row['createdAt'])
        op.require(latest['id']==self.state['deployment'] and latest['commit']['id']==release['execution_binding']['revision'] and
            self.state['artifact']['execution_binding']==release['execution_binding'] and
            self.state['profile']==source_profile(self.state['artifact'],release['execution_binding']['revision']),'OWNER_BUILD_RECEIPT_BINDING')
        startup=self.state['startup_preflight']
        op.require(startup['sha256']==hashlib.sha256(canonical(startup['receipt'])).hexdigest() and
            startup['receipt']['period']==PERIOD and startup['receipt']['execution_binding']==release['execution_binding'] and
            startup['receipt']['tree']==release['tree'] and startup['receipt']['status']=='CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION',
            'OWNER_STARTUP_PREFLIGHT_EVIDENCE')
        release['deployment']=self.state['deployment']
        b,p=self.construct_release_binding(release)
        self._release_capacity=self.preview_release_capacity(b,p)
        self._release_readback=dict(configuration_equal=True,environment_equal=True,suspended=True,
            runtime_roles_dormant=True,stable_verifiers='MATCH',pipeline_sessions='ABSENT',runtime_memberships='ABSENT',
            temporary_owner='ABSENT',complete_terminal_jobs=len(jobs),complete_terminal_deployments=len(deploys),
            latest_deployment=latest['id'],latest_revision=latest['commit']['id'],checked_at=time.time())
        return b,p
    def construct_release_binding(self,release):
        folder=RELEASE_PARENT/('propertyaigent-owner-'+PERIOD)
        b,p=fixed_binding(release,self.state['profile'],self.db.address,self.state['original_guard'])
        b.update(release_root=str(folder),submission_intent_path=str(folder/'submission.intent.json'),credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=self.state['stable_credentials']['verifier_sha256'])
        validate_policy(b,p)
        return b,p
    def preview_release_capacity(self,b,policy):
        """Exact retained values; projected phase records, no intent/effect/freeze."""
        starting=dict(ciphertext_bytes=self.journal.ciphertext_bytes,ordinal=self.journal.ordinal)
        op.require(self.journal.ordinal+23<=63-CLEANUP_SNAPSHOTS,'OWNER_CLEANUP_ROW_BOUND')
        projected=self.reserved_candidate();sizes={};plaintext_sizes={}
        def measure(name):
            plaintext_sizes[name]=state_size(projected)
            try:sizes[name]=self.journal.save(copy.deepcopy(projected),validate_only=True)
            except BaseException:
                print('PROPERTYAIGENT_OWNER_PILOT_CAPACITY_REFUSAL '+json.dumps(dict(stage=name,plaintext_bytes=state_size(projected),ciphertext_bytes=ciphertext_size(state_size(projected)),normal_ceiling=22152),sort_keys=True),flush=True)
                raise
        measure('reserved')
        projected.update(binding=copy.deepcopy(b),policy=copy.deepcopy(policy),status='RELEASE_BOUND')
        for n in ('RELEASE','PERIOD'):projected['intents'][n]=dict(at=9999999999.999998,state='ACKNOWLEDGED')
        projected['period_journal']=period_checkpoint(dict(state='COMMIT_ACKNOWLEDGED',binding=b,policy=policy))
        projected['period_receipt']=dict(outcome='COMMIT_ACKNOWLEDGED',period=PERIOD,policy_sha256=b['period_policy_sha256'],temporary_issuer='REMOVED',original_memberships='PRESERVED',readback='EXACT_ON_SAME_CONNECTION',connections=1,retry=False)
        measure('period')
        with envelope(),self.db.connection() as c:
            prepared=op.prepare_activation(c,b,stable_credentials=self.state['stable_credentials']['passwords'])
        projected['access']=prepared;projected['access']['state']='ACTIVATION_ACKNOWLEDGED'
        projected['intents']['ACTIVATE']=dict(at=9999999999.999998,state='ACKNOWLEDGED')
        projected['activation_receipt']=dict(outcome='COMMIT_ACKNOWLEDGED',runtime_roles=sorted(op.ROLES),credentials='ENCRYPTED_LOCAL_ONLY',valid_until=b['valid_until'])
        projected['qualification']={'status':'REQUIRED_IN_ACTUAL_RUNTIME_BEFORE_SOURCE'};measure('opening')
        original=self.state['original_environment'];expected={k:v for k,v in original.items() if k in KEEP}
        expected['INGESTION_RENDER_PROFILE']=canonical(b['render_profile']).decode()
        for role,name in (('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')):expected[name]=url(b['route'],role,prepared['passwords'][role])
        projected['access']['render']=dict(original=copy.deepcopy(original),expected=expected,guard=b['render_config_sha256'],state='PUT_ACKNOWLEDGED',publication_token=None,publication_state='NOT_REQUESTED',mapped_at=9999999999.999998,handoff_observation_sha256='f'*64)
        for operation in ('HANDOFF','SUBMISSION'):
            observation=dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=operation,binding_sha256='f'*64,service_id=SERVICE,observed_at=9999999999.999998,env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,other_activity_stopped=True,deployment_id=b['retained_deployment'],revision=b['execution_binding']['revision'],suspended=True)
            projected.setdefault('observations',{})[operation]=dict(provider_observation=observation,owner_boundary_confirmed_at=9999999999.999998)
        projected['intents']['HANDOFF']=dict(at=9999999999.999998,state='ACKNOWLEDGED')
        projected['handoff_receipt']=dict(status='RENDER_HANDOFF_ACKNOWLEDGED',service_id=SERVICE,names=sorted(expected),calls=5,observation_sha256='f'*64)
        measure('handoff_and_submission_observation')
        projected['access']['render']['submission_state']='SUBMISSION_INTENT_NO_RETRY'
        command='/usr/bin/timeout --signal=INT --kill-after=5s 960s python -u -m scripts.owner_pilot_job --period '+PERIOD+' --hostaddr '+b['hostaddr']+' --deadline '+str(b['valid_until'])
        projected['job_command']=command
        projected['intents']['ONE_JOB']=dict(at=9999999999.999998,state='ACKNOWLEDGED')
        # Retained provider schema, not an assertion that a new job exists.
        job=copy.deepcopy(self.state.get('startup_job_terminal') or self.state.get('startup_job') or {})
        job.update(id='job-'+'z'*20,serviceId=SERVICE,startCommand=command,status='succeeded',createdAt='2026-11-04T23:59:59.999999Z',startedAt='2026-11-04T23:59:59.999999Z',finishedAt='2026-11-04T23:59:59.999999Z')
        projected['job']=copy.deepcopy(job);projected['job']['status']='pending';projected['job']['finishedAt']=None
        measure('job_acknowledged')
        projected['job_terminal']=job;measure('job_terminal')
        qualification=dict(version='RUNTIME_AUTHENTICATION_V1',period=PERIOD,execution_binding=b['execution_binding'],deadline=b['valid_until'],status='VERIFIED_BOTH_RESTRICTED_ROLES',roles=[],attempts=[],source_requests=0,max_attempts_per_role=2)
        for role in sorted(op.ROLES):
            qualification['roles'].append(dict(role=role,identity='VERIFIED',interface='VERIFIED',connection_closed=True))
            for attempt in (1,2):
                qualification['attempts'].append(dict(role=role,attempt=attempt,connection_attempts=1,driver_statements=20,returned_data_value_bytes=8192,elapsed_seconds=12.999999999,connections_closed=True,cleanup='CLOSED',connection_diagnostics=[dict(reason_code='AUTHENTICATION_REJECTED',failed_native_connection_finished=True,sqlstate='28P01',exception_class='OperationalError')]))
        projected['runtime_qualification']=qualification;measure('runtime_qualification')
        scopes=[dict(council=c,status='RETAINED_AND_SCREENED',records=n,failure=None) for c,n in (('tameside',30),('manchester',60))]
        usage={k:999999999 for k in ('driver_statements','connection_attempts','cancel_requests','returned_bytes','source_requests','source_bytes','source_seconds','source_supervised_seconds','publication_bytes','publication_calls')}
        usage.update(elapsed_seconds=999.999999999,all_connections_closed=True)
        projected['source_result']=dict(period=PERIOD,run_id='a'*32,run_state='VERIFIED',pipeline_status='RETAINED_AND_SCREENED',scopes=scopes,cleanup='CLOSED',authority_closure='INVALIDATED',evidence_readback=dict(name='final/result-before-publication.json',sha256=hashlib.sha256(b'projected-result').hexdigest(),bytes=2097152),github_publication='NOT_REQUESTED',usage=usage,source_failure=None,runtime_qualification=qualification)
        measure('source_result')
        captures=[]
        for index,scope in enumerate(scopes,1):
            digest=lambda tag:hashlib.sha256((scope['council']+tag).encode()).hexdigest()
            archive=dict(backend=BACKEND,period=PERIOD,run_id='a'*32,name='capture-'+str(index)+'/source.json',path='docs/design/ingestion-operational-execution-daily-intake/'+PERIOD+'/'+'a'*32+'/capture-'+str(index)+'/source.json',sha256=digest('archive'),bytes=524288,readback_verified=True)
            captures.append(dict(council=scope['council'],capture_key=digest('capture'),record_count=scope['records'],screening_complete=scope['records'],batches_complete=(scope['records']+4)//5,archive=archive,source_sha256=digest('source'),capture_sha256=digest('receipt')))
        projected['independent_result']=dict(status='INDEPENDENT_DATABASE_VERIFIED_SUCCESS',period=PERIOD,run_id='a'*32,publication=dict(captures[0]['archive'],name='final/result-before-publication.json'),authorities={hashlib.sha256(str(i).encode()).hexdigest():0 for i in range(4)},captures=captures,stop=op.ACCEPTED_STOP,independent_external_publication_check='NOT_REQUESTED',independent_render_terminal_check='REQUIRED')
        projected['pipeline_status']='VERIFIED_RETAINED_AND_SCREENED';measure('independent_result')
        return dict(starting=starting,projected_ciphertext_bytes=sizes,normal_ciphertext_ceiling=22152,normal_last_ordinal=47,
            normal_snapshots_remaining=47-self.journal.ordinal,reserved_cleanup_snapshots=16,cleanup_growth_plaintext=6937,margin_plaintext=1024,worst_cleanup_ciphertext=32756,
            remaining_normal_bytes=22152-max(sizes.values()),remaining_normal_writes=23,projected_last_normal_ordinal=self.journal.ordinal+23,
            projected_plaintext_bytes=plaintext_sizes,projected_worst_cleanup_ciphertext=ciphertext_size(max(plaintext_sizes.values())+6937+1024),
            modeled_record_shapes='RETAINED_PROVIDER_SCHEMA_TWO_COUNCILS_FOUR_AUTH_ATTEMPTS',projection_only=True,provider_mutations=0)
    def verify_release_binding(self):
        """Deployed read-only proof of the same boundary consumed by Run."""
        b,p=self.release_preflight()
        before=(self.journal.previous,self.journal.ordinal)
        self.journal.load()
        op.require((self.journal.previous,self.journal.ordinal)==before,'OWNER_PRIOR_ATTEMPT_RECONCILE')
        return dict(status='RELEASE_BINDING_VERIFIED_READ_ONLY',period=PERIOD,window=WINDOW,
            date_fields={'tameside':'RECEIVED','manchester':'VALIDATED'},deployment=b['retained_deployment'],
            execution_binding=b['execution_binding'],binding_sha256=hashlib.sha256(canonical(b)).hexdigest(),
            policy_sha256=b['period_policy_sha256'],max_runs=p['max_runs'],render_profile=b['render_profile'],
            readback=self._release_readback,capacity=self._release_capacity,
            journal_sha256=before[0],journal_ordinal=before[1],journal_unchanged=True,
            release_intent_present=False,access_opened=False,job_created=False,provider_mutations=0,
            deadline_frozen=False,validation_only=True)
    def run(self,owner_checked_at):
        op.require(type(owner_checked_at) in (int,float) and 0<=time.time()-owner_checked_at<=300,'OWNER_INHERITED_BOUNDARY_REQUIRED')
        b,p=self.release_preflight()
        folder=Path(b['release_root'])
        self.arm_cleanup_reserve()
        if 'preparation_failure' in self.state:self.state.pop('failure',None)
        self.state.update(binding=b,policy=p,status='RELEASE_BOUND');self.intent('RELEASE')
        try:
            folder.mkdir(mode=0o700)
            self.intent('PERIOD')
            journal={'version':'FINITE_INTAKE_PERIOD_V1','state':'ARMED_NO_RETRY','binding':b,'policy':p}
            self.state['period_journal']=period_checkpoint(journal);self.save()
            with envelope(),self.db.connection() as c:
                def period_saved(value):
                    self.state['period_journal']=period_checkpoint(value)
                    if value.get('state')=='COMMIT_ACKNOWLEDGED':self.journal.save(self.state,connection=c)
                period=issue_period(c,b,p,journal,period_saved)
            self.state['period_receipt']=period;self.ack('PERIOD')
            self.intent('ACTIVATE')
            with envelope(),self.db.connection() as c:
                prepared=op.prepare_activation(c,b,stable_credentials=self.state['stable_credentials']['passwords'])
                self.state['access']=copy.deepcopy(prepared);self.journal.save(self.state,connection=c)
                opening=copy.deepcopy(self.state)
                opening['access']['state']='ACTIVATION_ACKNOWLEDGED'
                opening['activation_receipt']=dict(outcome='COMMIT_ACKNOWLEDGED',runtime_roles=sorted(op.ROLES),credentials='ENCRYPTED_LOCAL_ONLY',valid_until=b['valid_until'])
                opening['intents']['ACTIVATE']['state']='ACKNOWLEDGED'
                opening['qualification']={'status':'REQUIRED_IN_ACTUAL_RUNTIME_BEFORE_SOURCE'}
                op.require(self.journal.ordinal+3<=63-CLEANUP_SNAPSHOTS,'OWNER_CLEANUP_ROW_BOUND')
                self.journal.save(opening,validate_only=True)
                def access_saved(value):
                    self.state['access']=copy.deepcopy(value)
                    if value.get('state')=='ACTIVATION_ACKNOWLEDGED':self.journal.save(self.state,connection=c)
                self.state['activation_receipt']=op.activate(c,b,access_saved,prepared=prepared)
            self.state['qualification']={'status':'REQUIRED_IN_ACTUAL_RUNTIME_BEFORE_SOURCE'}
            self.ack('ACTIVATE')
            observation=self.observation('HANDOFF',owner_checked_at)
            self.intent('HANDOFF')
            with self.api() as api:self.state['handoff_receipt']=handoff(api,self.state['access'],self.access_save,None,observation=observation)
            self.ack('HANDOFF')
            observation=self.observation('SUBMISSION',owner_checked_at)
            with self.api() as api:submission_check(api,self.state['access'],self.access_save,observation)
            command='/usr/bin/timeout --signal=INT --kill-after=5s 960s python -u -m scripts.owner_pilot_job --period '+PERIOD+' --hostaddr '+b['hostaddr']+' --deadline '+str(b['valid_until'])
            self.state['job_command']=command;self.intent('ONE_JOB')
            with self.api() as api:
                op.validate_binding(b,opening=True)
                job=api.call('POST','/jobs',{'startCommand':command})
            op.require(isinstance(job,dict) and re.fullmatch('job-[a-z0-9]{20}',job.get('id','')) and job.get('serviceId')==SERVICE and job.get('startCommand')==command,'OWNER_JOB_ACK_UNCERTAIN')
            self.state['job']=job;self.ack('ONE_JOB')
            for _ in range(32):
                self.sleep(30)
                with self.api() as api:job=api.call('GET','/jobs/'+job['id'])
                if job.get('status') in TERMINAL and job.get('finishedAt'):break
            self.state['job_terminal']=job;self.save()
            self.read_runtime_qualification()
            self.read_result()
            op.require(job.get('status')=='succeeded' and job.get('finishedAt'),'OWNER_OPEN_OR_UNVERIFIED')
            with envelope(),self.db.connection() as c:
                ctl=op.control(c);run=ctl.get('intake_run') or {}
                self.state['independent_result']=op.finalisation(c,b,{'run_id':run.get('id'),'publication':run.get('publication')})
            self.state['pipeline_status']='VERIFIED_RETAINED_AND_SCREENED';self.save()
        except BaseException as exc:
            self.record_first_failure(exc)
        finally:
            self.cleanup()
        return self.summary()
    def read_runtime_qualification(self):
        with self.api() as api:value=api.call('GET','qualification:'+self.state['job']['id'])
        op.require(value.get('hasMore') is False and len(value.get('logs',[]))==1,'RUNTIME_QUALIFICATION_EVIDENCE')
        line=value['logs'][0]['message'];prefix='DATABASE_PILOT_RUNTIME_QUALIFICATION '
        op.require(line.startswith(prefix),'RUNTIME_QUALIFICATION_EVIDENCE')
        receipt=json.loads(line[len(prefix):])
        op.require(receipt.get('period')==PERIOD and receipt.get('execution_binding')==self.state['binding']['execution_binding'] and receipt.get('deadline')==self.state['binding']['valid_until'] and receipt.get('source_requests')==0,'RUNTIME_QUALIFICATION_EVIDENCE')
        self.state['runtime_qualification']=receipt;self.save()
        op.require(receipt.get('status')=='VERIFIED_BOTH_RESTRICTED_ROLES','RUNTIME_AUTHENTICATION_REFUSED')
    def read_result(self):
        """Independent private byte/hash retrieval, including unsuccessful runs."""
        with envelope(),self.db.connection() as c:
            c.execute('BEGIN READ ONLY')
            try:
                run=op.control(c).get('intake_run') or {}
                op.require(run.get('period')==PERIOD and re.fullmatch('[a-f0-9]{32}',run.get('id','')),'OWNER_RESULT_RUN_BINDING')
                raw=bytes(c.execute('SELECT public.ingestion_intake_evidence_read(%s,%s,%s)',(PERIOD,run['id'],'final/result-before-publication.json')).fetchone()[0])
                report=json.loads(raw)
                op.require(report.get('period')==PERIOD and report.get('run_id')==run['id'] and report.get('execution_binding')==self.state['binding']['execution_binding'],'OWNER_RESULT_EVIDENCE_BINDING')
                self.state['source_result']={'period':PERIOD,'run_id':run['id'],'run_state':run.get('state'),'pipeline_status':report.get('status'),
                    'scopes':report.get('scopes'),'cleanup':report.get('cleanup'),'authority_closure':report.get('authority_closure'),
                    'evidence_readback':{'name':'final/result-before-publication.json','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)},
                    'github_publication':report.get('github_publication'),'usage':report.get('usage'),'source_failure':report.get('reason') or report.get('failure'),'runtime_qualification':report.get('runtime_qualification')}
            finally:c.execute('ROLLBACK')
        self.save()
    def cleanup(self):
        if self.state.get('cleanup_reserve'):self.state=self.journal.load()
        with self.cleanup_writes():
            self._cleanup()
            if self.state.get('cleanup_reserve') and self.state.get('status')=='CLOSED' and not self.state.get('closure_verification'):
                try:check=self.inspect()
                except BaseException as exc:
                    self.state=self.journal.load()
                    self.record_cleanup_failure(exc,'closure_failure')
                    self.state['status']='CONTAINMENT_REQUIRES_REVIEW';self.save()
                    return
                good=(check['stable_verifier_binding']=='MATCH' and check['runtime_membership_count']==0 and check['pipeline_session_count']==0 and check['temporary_owner_absent'] and
                    all(not r['login'] for r in check['runtime_roles']) and all(check['current_readback'][k] for k in ('suspended','configuration_equal','environment_equal')) and check['attempt_authorities']['all_expiry_zero'])
                self.state['closure_verification']=dict(status='VERIFIED' if good else 'REFUSED',runtime_memberships=check['runtime_membership_count'],sessions=check['pipeline_session_count'],
                    temporary_owner_absent=check['temporary_owner_absent'],stable_verifiers=check['stable_verifier_binding'],suspended=check['current_readback']['suspended'],
                    configuration_equal=check['current_readback']['configuration_equal'],environment_equal=check['current_readback']['environment_equal'],authorities_closed=check['attempt_authorities']['all_expiry_zero'])
                if not good:self.state['status']='CONTAINMENT_REQUIRES_REVIEW'
                self.save()
    def _cleanup(self):
        # Independent database containment never depends on GitHub or Render.
        access=self.state.get('access')
        if access and access.get('state')!='DATABASE_CLOSURE_ACKNOWLEDGED':
            try:
                with envelope(),self.db.connection() as c:
                    def closed_saved(value):
                        self.state['access']=copy.deepcopy(value);self.journal.save(self.state,connection=c)
                    self.state['closure_receipt']=op.close(c,access,closed_saved)
                self.save()
            except BaseException as exc:self.record_cleanup_failure(exc,'closure_failure')
        if access and access.get('render') and access.get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED':
            r=access['render']
            if r.get('state')=='RESTORE_INTENT_NO_RETRY':
                with self.api() as api:
                    actual=env_values(api.call('GET','/env-vars?limit=100'));guard=service_guard(api.call('GET'))
                op.require(actual==r['original'] and guard==r['guard'],'OWNER_RESTORE_UNCERTAIN_NO_RETRY')
                r['state']='RESTORATION_VERIFIED_BY_READBACK';self.access_save(access)
                self.state['restoration_receipt']={'status':'EXACT_RESTORATION_VERIFIED_BY_READBACK','original_acknowledgement':'UNKNOWN','provider_mutations':0};self.save()
            if r.get('state')=='PUT_INTENT_NO_RETRY':
                with self.api() as api:reconcile_handoff(api,access,self.access_save)
            if r.get('state')=='PUT_ACKNOWLEDGED' or r.get('state')=='PUT_INTENT_NO_RETRY' and r.get('reconciliation')=='EXPECTED':
                try:
                    with self.api() as api:self.state['restoration_receipt']=restore_handoff(api,access,self.access_save,self.state.get('job',{}).get('id'))
                    self.save()
                except BaseException as exc:self.record_cleanup_failure(exc,'restoration_failure')
        with self.api() as api:
            service=api.call('GET');environment=env_values(api.call('GET','/env-vars?limit=100'))
        self.state['final_service']={'suspended':service.get('suspended')=='suspended','configuration_equal':service_guard(service)==self.state['original_guard'],
            'environment_equal':environment==self.state['original_environment']}
        handoff_closed=not access or not access.get('render') or access['render'].get('state') in ('RESTORATION_ACKNOWLEDGED','RESTORATION_VERIFIED_BY_READBACK') or access['render'].get('reconciliation')=='ORIGINAL'
        self.state['status']='CLOSED' if (not access or access.get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED') and handoff_closed and all(self.state['final_service'].values()) else 'CONTAINMENT_REQUIRES_REVIEW'
        self.save()
    def recover(self):
        self.state=self.journal.load();op.require(self.state is not None,'OWNER_NO_RECOVERY_STATE')
        if self.state.get('status')=='CLOSED':
            if self.state.get('cleanup_reserve') and not self.state.get('closure_verification'):
                with self.cleanup_writes():self.cleanup()
            return self.summary()
        self.reserve_closure_space()
        if 'binding' not in self.state:self.recover_build()
        else:self.cleanup()
        return self.summary()
    def reserve_closure_space(self):
        """Keep concluded build detail in immutable prior rows, not every copy.

        No release, restoration intent, original environment, credential, job,
        policy or actual-result field is removed. No ciphertext/row limit grows.
        """
        access=self.state.get('access',{})
        if not access:return
        fields=('original_service','original_deploy_ids','build_guard','build_environment','build_receipt_created_at')
        present=[name for name in fields if name in self.state]
        if not present:return
        early=access.get('state')!='DATABASE_CLOSURE_ACKNOWLEDGED'
        if early:
            # Exact acknowledged pre-submission Attempt04 only. Recovery never
            # consumes or clears its existing release/handoff intent.
            op.require(self.state.get('period')==PERIOD=='b-dbpilot-20261027-1102-04' and
                self.state.get('status')=='RELEASE_BOUND' and access.get('state')=='ACTIVATION_ACKNOWLEDGED' and
                access.get('render',{}).get('state')=='PUT_ACKNOWLEDGED' and
                all(self.state.get('intents',{}).get(n,{}).get('state')=='ACKNOWLEDGED' for n in ('PERIOD','ACTIVATE','HANDOFF')) and
                'ONE_JOB' not in self.state.get('intents',{}) and not self.state.get('job'),'OWNER_CLOSURE_ARCHIVE_BINDING')
        required=('RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT')
        op.require(all(self.state.get('intents',{}).get(name,{}).get('state')=='ACKNOWLEDGED' for name in required)
            and self.state.get('original_guard')==self.state['binding'].get('render_config_sha256')
            and self.state['access'].get('render',{}).get('guard')==self.state['original_guard']
            and self.state['access']['render'].get('original')==self.state.get('original_environment'),'OWNER_CLOSURE_ARCHIVE_BINDING')
        op.require(type(self.journal.ordinal) is int and 0<=self.journal.ordinal<=59,'OWNER_STATE_HISTORY_BOUND')
        op.require(re.fullmatch('[a-f0-9]{64}',self.journal.previous or ''),'OWNER_JOURNAL_HASH')
        reference=dict(prior_ciphertext_sha256=self.journal.previous,prior_ordinal=self.journal.ordinal,
            fields={name:hashlib.sha256(canonical(self.state[name])).hexdigest() for name in present})
        compact=copy.deepcopy(self.state)
        for name in present:del compact[name]
        compact['closed_build_archive']=reference
        if early:
            compact['recovery_capacity']=self.check_cleanup_capacity(compact)
        self.state=compact
        self.save()
    def check_cleanup_capacity(self,compact):
        """Encrypt projections of the retained state; no SQL/provider effects.

        Nine remaining snapshots: archive, four DB-close/receipt saves,
        three restoration saves, final outcome. Existing 32KiB/64-row bounds.
        Synthetic receipt shapes are measured only, never saved as outcomes.
        """
        stages=('archived','access_disabled','memberships_removed','database_closed','closure_receipt','restore_intent','restore_ack','restoration_receipt','final')
        op.require(self.journal.ordinal+len(stages)<=63,'OWNER_STATE_HISTORY_BOUND')
        projected=copy.deepcopy(compact)
        def metadata(sizes):return dict(version='RETAINED_CLOSURE_CAPACITY_V1',ciphertext_limit=32768,remaining_snapshots=len(stages),projected_ciphertext_bytes=sizes)
        projected['recovery_capacity']=metadata({n:32768 for n in stages})
        sizes={}
        def measure(name):sizes[name]=len(self.journal._vault(value=projected))
        measure('archived')
        projected['access']['state']='ACCESS_DISABLED_ACKNOWLEDGED';measure('access_disabled')
        projected['access']['membership_closure']='RECONCILIATION_REQUIRED';measure('memberships_removed')
        projected['access'].update(state='DATABASE_CLOSURE_ACKNOWLEDGED',passwords={});measure('database_closed')
        projected['closure_receipt']=dict(outcome='COMMIT_ACKNOWLEDGED',runtime_access='DISABLED',password_verifiers='RETAINED',authorities=['f'*64]*4,authority_expiry=0,temporary_owner='REMOVED',sessions='ABSENT',stop_preserved=projected['binding']['accepted_stop'],intake_run_state='PERSISTENCE_UNCERTAIN',open_run_requires_reconciliation=False)
        measure('closure_receipt')
        projected['access']['render'].update(state='RESTORE_INTENT_NO_RETRY',submission_ack_timing='NO_JOB_VERIFIED');measure('restore_intent')
        projected['access']['render'].update(state='RESTORATION_ACKNOWLEDGED',expected={});measure('restore_ack')
        projected['restoration_receipt']=dict(status='RESTORATION_VERIFIED',service_id=SERVICE,job_id=None,calls=8,publication_token='WITHDRAWN_FROM_SERVICE_SNAPSHOT_NOT_PROVIDER_REVOKED',submission_ack_timing='NO_JOB_VERIFIED');measure('restoration_receipt')
        projected.update(status='CLOSED',final_service=dict(suspended=True,configuration_equal=True,environment_equal=True));measure('final')
        return metadata(sizes)
    def inspect(self):
        """Read-only reconciliation; never calls prepare, recovery or save."""
        self.state=self.journal.load()
        if self.state is None:return {'status':'NOT_PREPARED','period':PERIOD,'read_only':True}
        value=self.summary();value['workflow_status']=value['status'];value['status']='READ_ONLY_EVIDENCE_SAVED';value['read_only']=True
        value['preparation_progress']={name:entry['state'] for name,entry in self.state.get('intents',{}).items()}
        value['artifact_verified']='artifact' in self.state
        value['journal_snapshot_ordinal']=self.journal.ordinal
        value['journal_ciphertext_bytes']=getattr(self.journal,'ciphertext_bytes',None)
        value['journal_sha256']=getattr(self.journal,'previous',None)
        value['remaining_snapshot_slots']=63-self.journal.ordinal
        value['release_intent_present']='RELEASE' in self.state.get('intents',{})
        value['job_intent_present']='ONE_JOB' in self.state.get('intents',{})
        value['job_recorded']=bool(self.state.get('job'))
        value['access_state']=self.state.get('access',{}).get('state')
        value['handoff_state']=self.state.get('access',{}).get('render',{}).get('state')
        with envelope(),self.db.connection() as c:
            c.execute('BEGIN READ ONLY')
            try:
                roles=c.execute(op.ROLE_QUERY,(list(op.ROLES),)).fetchall()
                value['runtime_roles']=[{'role':r[0],'login':r[1],'password_null':r[2]} for r in roles]
                control=op.control(c);policy=control.get('intake_periods',{}).get(PERIOD)
                value['period_present']=policy is not None
                grants={k:v for k,v in control.get('grants',{}).items() if v.get('intake_period')==PERIOD}
                value['attempt_authorities']={'count':len(grants),'all_expiry_zero':all(g.get('expires_at')==0 for g in grants.values()),'ids':sorted(grants)}
                value['period_policy_readback']=None if policy is None else {'max_runs':policy.get('max_runs'),'expires_at':policy.get('expires_at'),'execution_binding':policy.get('execution_binding'),'retained_history':True}
                run=control.get('intake_run') or {}
                value['attempt_run_state']=run.get('state') if run.get('period')==PERIOD else None
                value['pipeline_session_count']=c.execute('SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)',(list(op.ROLES),)).fetchone()[0]
                value['runtime_membership_count']=c.execute('SELECT count(*) FROM pg_auth_members WHERE member=ANY(%s::regrole[])',(list(op.ROLES),)).fetchone()[0]
                if self.state.get('stable_credentials'):
                    observed=dict(c.execute("SELECT rolname,encode(sha256(convert_to(rolpassword,'UTF8')),'hex') FROM pg_authid WHERE rolname=ANY(%s)",(list(op.ROLES),)).fetchall())
                    value['stable_verifier_binding']='MATCH' if observed==self.state['stable_credentials']['verifier_sha256'] else 'DRIFT'
                value['temporary_owner_absent']=c.execute("SELECT NOT pg_has_role(current_user,'ingestion_storage_owner','SET') AND NOT pg_has_role(current_user,'ingestion_storage_owner','USAGE') AND NOT has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()[0]
            finally:c.execute('ROLLBACK')
        with self.api() as api:
            service=api.call('GET');environment=env_values(api.call('GET','/env-vars?limit=100'))
            jobs=complete_inventory(api.call('GET','/jobs?limit=100'),'job')
            deploys=complete_inventory(api.call('GET','/deploys?limit=100'),'deploy')
        value['current_readback']={'suspended':service.get('suspended')=='suspended','configuration_equal':service_guard(service)==self.state.get('original_guard'),
             'environment_equal':environment==self.state.get('original_environment'),'complete_terminal_jobs':len(jobs),'complete_terminal_deployments':len(deploys),
             'latest_deployment':sorted(deploys,key=lambda x:x['createdAt'],reverse=True)[0]['id'] if deploys else None,
             'latest_revision':sorted(deploys,key=lambda x:x['createdAt'],reverse=True)[0].get('commit',{}).get('id') if deploys else None,
             'jobs_since_preparation':sum(datetime.fromisoformat(j['createdAt'].replace('Z','+00:00')).timestamp()>=self.state['intents'].get('BUILD_ENVIRONMENT',{}).get('at',0) for j in jobs),'provider_mutations':0}
        return value
    def reconcile_artifact(self,configuration=None):
        """Bind the independently retrieved existing receipt; never rebuild.

        Protected nonsecret configuration is supplied by the authenticated
        Render connector. Historical refusal, intents and restoration evidence
        remain unchanged. An identical entry is a read, a conflict refuses.
        """
        cfg=configuration or json.loads(os.environ['PROPERTYAIGENT_INTAKE_BUILD_RECEIPT'])
        op.require(type(cfg) is dict and set(cfg)=={'version','deployment','receipt_sha256','receipt','preparation_failure_sha256'} and cfg['version']=='AUTHORITATIVE_RENDER_RECEIPT_V1','ARTIFACT_RECONCILIATION_CONFIGURATION')
        receipt=cfg['receipt'];sha=hashlib.sha256(canonical(receipt)).hexdigest()
        op.require(sha==cfg['receipt_sha256'],'ARTIFACT_RECONCILIATION_HASH')
        release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
        op.require(receipt.get('kind')=='DATABASE_PILOT_BUILD_NOT_EXECUTION' and receipt.get('execution_binding')==release['execution_binding'],'ARTIFACT_RECONCILIATION_CODE')
        profile=source_profile(receipt,release['execution_binding']['revision'])
        executable=Path(receipt.get('browser_executable',''))
        op.require(re.fullmatch('[a-f0-9]{64}',profile['browser_sha256']) and Path(profile['browser_path']).is_absolute() and '..' not in Path(profile['browser_path']).parts and executable.is_absolute() and '..' not in executable.parts and executable.is_relative_to(profile['browser_path']),'ARTIFACT_RECONCILIATION_BROWSER')
        entry={'version':'EXISTING_BUILD_RECONCILIATION_V1','deployment':cfg['deployment'],'receipt_sha256':sha,
               'execution_binding':release['execution_binding'],'historical_failure_sha256':cfg['preparation_failure_sha256']}
        self.state=self.journal.load();op.require(self.state is not None,'ARTIFACT_RECONCILIATION_STATE')
        prior=self.state.get('artifact_reconciliation')
        if prior is not None:
            op.require(prior==entry,'ARTIFACT_RECONCILIATION_CONFLICT')
            return self.summary()
        required={'BUILD_ENVIRONMENT','BUILD_CONFIGURATION','ONE_RESUME_BUILD','RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT'}
        op.require(self.state.get('status')=='PREPARATION_REFUSED' and self.state.get('failure',{}).get('phase')=='RESUSPEND' and self.state.get('deployment')==cfg['deployment'] and not any(k in self.state for k in ('binding','access','job','period_journal')) and all(self.state.get('intents',{}).get(k,{}).get('state')=='ACKNOWLEDGED' for k in required),'ARTIFACT_RECONCILIATION_PREDECESSOR')
        op.require(hashlib.sha256(canonical(self.state['failure'])).hexdigest()==cfg['preparation_failure_sha256'],'ARTIFACT_RECONCILIATION_REFUSAL')
        observed=self.inspect();current=observed['current_readback']
        op.require(observed['workflow_status']=='PREPARATION_REFUSED' and current['suspended'] and current['configuration_equal'] and current['environment_equal'] and current['latest_deployment']==cfg['deployment'] and current['latest_revision']==release['execution_binding']['revision'] and current['jobs_since_preparation']==0 and observed['period_present'] is False and observed['temporary_owner_absent'] is True and all(r['login'] is False and r['password_null'] is (not bool(self.state.get('stable_credentials'))) for r in observed['runtime_roles']),'ARTIFACT_RECONCILIATION_CURRENT_STATE')
        with envelope(),self.db.connection() as c:
            c.execute('BEGIN READ ONLY')
            try:op.dormant(c,stable_verifiers=self.state.get('stable_credentials',{}).get('verifier_sha256'));op.inventory(c);verify_inventory(c);op.no_hazards(c,op.control(c))
            finally:c.execute('ROLLBACK')
        self.state['preparation_failure']=copy.deepcopy(self.state['failure'])
        self.state.update(artifact=receipt,profile=profile,artifact_reconciliation=entry,status='ARTIFACT_READY')
        self.state['artifact_reconciliation_readback']=current
        self.save()
        saved=self.journal.load()
        op.require(saved.get('artifact_reconciliation')==entry and saved.get('artifact')==receipt and saved.get('profile')==profile and saved.get('status')=='ARTIFACT_READY','ARTIFACT_RECONCILIATION_DURABLE_READBACK')
        self.state=saved
        return self.summary()
    def summary(self):
        s=self.state
        return {'period':PERIOD,'window':WINDOW,'date_fields':{'tameside':'RECEIVED','manchester':'VALIDATED'},'status':s['status'],
                'pipeline_status':s.get('pipeline_status','NOT_RUN'),'github_publication':'NOT_REQUESTED','deployment':s.get('deployment'),
                'job_id':s.get('job',{}).get('id'),'job_status':s.get('job_terminal',{}).get('status'),'final_service':s.get('final_service'),
                'failure':s.get('failure'),'first_failure':s.get('first_failure'),'cleanup_reserve':s.get('cleanup_reserve'),'closure_verification':s.get('closure_verification'),'closure_failure':s.get('closure_failure'),'restoration_failure':s.get('restoration_failure'),
                'independent_result':s.get('independent_result'),'source_result':s.get('source_result'),'closure_receipt':s.get('closure_receipt'),
                'artifact_reconciliation':s.get('artifact_reconciliation'),'preparation_failure':s.get('preparation_failure'),
                'startup_preflight':s.get('startup_preflight'),'startup_job_id':s.get('startup_job',{}).get('id') or s.get('startup_preflight',{}).get('job_id'),'credential_reuse':s.get('credential_reuse'),'closed_build_archive':s.get('closed_build_archive'),'recovery_capacity':s.get('recovery_capacity'),'stable_configuration':s.get('stable_configuration'),'credential_policy':(s.get('binding') or {}).get('credential_policy'),'runtime_qualification':s.get('runtime_qualification'),'predecessor':s.get('predecessor'),'qualification':s.get('qualification'),'qualification_attempts':s.get('qualification_attempts')}
