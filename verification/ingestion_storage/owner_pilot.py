"""Fixed owner-only pilot bridge over the existing issuer, runtime and closure.

No scheduler, token, role creation or source reader lives here. The existing
web process supplies protected configuration; the actual daily job receives
only the two finite restricted credentials. Recovery journals use the existing
Vault format, encrypted in the approved private evidence table.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo

from . import intake_owner as op
from .intake_owner_io import Vault,env_values,service_guard,KEEP,handoff,submission_check,restore_handoff,reconcile_handoff
from .intake_owner_operations import COUNCILS,SCREENING,issue_period
from .database_evidence import BACKEND,canonical,migration_sql,verify_inventory
from .restricted_route import url,ROUTES
from .tls_trust import verified_trust

PREDECESSOR='b-dbpilot-20261027-1102-02'
PERIOD='b-dbpilot-20261027-1102-03'
OWNER_PERIOD=PERIOD+'_owner'
OWNER_RUN=hashlib.sha256(OWNER_PERIOD.encode()).hexdigest()[:32]
SERVICE='crn-d9sv93vavr4c73f98rb0'
WORKSPACE='tea-d9qbf8jm8hqs7385cu0g'
WINDOW={'start':'2026-10-27','end':'2026-11-02'}
RELEASE_PARENT=Path('/tmp')
TERMINAL={'succeeded','failed','canceled'}
DEPLOY_TERMINAL={'live','deactivated','build_failed','update_failed','canceled','pre_deploy_failed'}

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
        self.db=db;self.period=period;self.owner_period=period+'_owner';self.owner_run=hashlib.sha256(self.owner_period.encode()).hexdigest()[:32];self.previous='';self.state=None
    def _vault(self,raw=None,value=None):
        # Only encrypted bytes touch the temporary filesystem. No new credential
        # is persisted; recovery derives its key from existing protected config.
        with tempfile.TemporaryDirectory(prefix='propertyaigent-owner-') as folder:
            p=Path(folder)/'state.vault'
            if raw is None:
                v=Vault(p,self.db.key,create=True);v.save(value);return p.read_bytes()
            fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as f:f.write(raw)
            return Vault(p,self.db.key).load()
    def load(self):
        with self.db.connection() as c:
            row=c.execute('SELECT * FROM public.ingestion_intake_owner_state(%s,%s,%s,NULL::bytea)',(self.owner_period,self.owner_run,'')).fetchone()
        if row is None:return None
        raw=bytes(row[1]);op.require(hashlib.sha256(raw).hexdigest()==row[2],'OWNER_JOURNAL_HASH')
        self.previous=row[2];self.state=self._vault(raw=raw)
        op.require(self.state.get('period')==self.period,'OWNER_JOURNAL_PERIOD')
        return self.state
    def save(self,state,connection=None):
        raw=self._vault(value=state);h=hashlib.sha256(raw).hexdigest()
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
        self.previous=h;self.state=copy.deepcopy(state)

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
        qualification=method=='GET' and re.fullmatch(r'qualification:job-[a-z0-9]{20}',suffix)
        artifact=method=='GET' and re.fullmatch(r'artifact:[0-9TZ:.+-]{20,40}',suffix)
        allowed=(method=='GET' and suffix in ('','/env-vars?limit=100','/jobs?limit=100','/deploys?limit=100','/secret-files?limit=100') or
                 method=='GET' and re.fullmatch(r'/(jobs/job-|deploys/dep-)[a-z0-9]{20}',suffix) or
                 method=='PUT' and suffix=='/env-vars' or method=='PATCH' and suffix=='' or
                 method=='POST' and suffix in ('/resume','/suspend','/jobs') or artifact or qualification)
        op.require(allowed,'OWNER_RENDER_FIXED_OPERATION')
        before=[]
        if self.calls>=8:before.append('REQUEST_LIMIT')
        if self.clock()-self.started>=40:before.append('CLIENT_TIME_LIMIT')
        if before:self.limit_refusal(before)
        self.calls+=1;limit=524288 if suffix=='/deploys?limit=100' else 32768
        target='https://api.render.com/v1/services/'+SERVICE+suffix
        if artifact:
            from urllib.parse import urlencode
            target='https://api.render.com/v1/logs?'+urlencode(dict(ownerId=WORKSPACE,resource=SERVICE,text='DATABASE_PILOT_BUILD_RECEIPT',startTime=suffix.split(':',1)[1],limit=5,direction='backward'))
        if qualification:
            from urllib.parse import urlencode
            target='https://api.render.com/v1/logs?'+urlencode(dict(ownerId=WORKSPACE,resource=suffix.split(':',1)[1],text='DATABASE_PILOT_RUNTIME_QUALIFICATION',limit=5,direction='backward'))
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
    known={'ACCESS_DISABLED_BUT_MEMBERSHIP_RECONCILIATION_REQUIRED',
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
     'VAULT_32K_BOUND',
     'VAULT_INCOMPLETE',
     'VAULT_PASSPHRASE_LENGTH'}
    from itertools import combinations
    for n in range(1,4):
        known.update('OWNER_RENDER_'+'_AND_'.join(parts) for parts in combinations(('RESPONSE_BYTE_LIMIT','AGGREGATE_BYTE_LIMIT','CLIENT_TIME_LIMIT'),n))
    known.update({'OWNER_RENDER_REQUEST_LIMIT','OWNER_RENDER_REQUEST_LIMIT_AND_CLIENT_TIME_LIMIT'})
    known.update({'OWNER_CONTINUATION_PREDECESSOR','OWNER_CONTINUATION_DUPLICATE','OWNER_CONTINUATION_MIGRATION','OWNER_CONTINUATION_PRESERVATION','OWNER_CONTINUATION_QUALIFICATION', 'OWNER_RESULT_RUN_BINDING','OWNER_RESULT_EVIDENCE_BINDING','OWNER_JOURNAL_REQUIRES_AUTOCOMMIT_BOUNDARY'})
    known.update('ARTIFACT_RECONCILIATION_'+x for x in ('CONFIGURATION','HASH','CODE','BROWSER','STATE','CONFLICT','PREDECESSOR','REFUSAL','CURRENT_STATE','DURABLE_READBACK'))
    known.update({'DRIVER_STATEMENT_BOUND','SERVER_TIMEOUT_OR_RESTRICTED_IDENTITY_PROFILE','REVIEWED_TLS_ENDPOINT_REQUIRED','RESTRICTED_ROUTE_MISMATCH','LIBPQ_ENVIRONMENT_OVERRIDE','RUNTIME_TRANSACTION_MODE','PINNED_REVIEWED_ADDRESS_REQUIRED','CONNECTION_BOUND','MANUAL_STOP_OR_CONTROLLER_DEADLINE'})
    known.update({'STABLE_CREDENTIALS_REQUIRED','STABLE_VERIFIER_BINDING','STABLE_CONFIGURATION_PRECONDITION','STABLE_CONFIGURATION_PRESERVATION','RUNTIME_AUTHENTICATION_REFUSED','RUNTIME_QUALIFICATION_EVIDENCE'})
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
    def prepare_continuation(self):
        from .owner_pilot_continuation import migrate_owner_namespace,predecessor
        old=Journal(self.db,PREDECESSOR).load();link=predecessor(old)
        with envelope(),self.db.connection() as c:migrate_owner_namespace(c)
        op.require(self.journal.load() is None,'OWNER_CONTINUATION_DUPLICATE')
        self.state={'period':PERIOD,'version':'OWNER_PLATFORM_PILOT_V1','intents':{},'status':'PREPARING','github_publication':'NOT_REQUESTED','predecessor':link}
        self.save()
        try:
            from .stable_runtime_credentials import prepare,configure
            with envelope(),self.db.connection() as c:
                self.state['stable_credentials']=prepare(c);op.require('STABLE_CREDENTIAL_CONFIGURATION' not in self.state['intents'],'OWNER_PRIOR_INTENT_RECONCILE');self.state['intents']['STABLE_CREDENTIAL_CONFIGURATION']={'at':time.time(),'state':'INTENT_NO_RETRY'};self.journal.save(self.state,connection=c)
                self.state['stable_configuration']=configure(c,self.state['stable_credentials']);self.state['intents']['STABLE_CREDENTIAL_CONFIGURATION']['state']='ACKNOWLEDGED';self.journal.save(self.state,connection=c)
            self.build();self.state['status']='ARTIFACT_READY';self.save()
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
    def run(self,owner_checked_at):
        op.require(type(owner_checked_at) in (int,float) and 0<=time.time()-owner_checked_at<=300,'OWNER_INHERITED_BOUNDARY_REQUIRED')
        self.state=self.journal.load()
        op.require(self.state is not None and self.state['status']=='ARTIFACT_READY' and 'RELEASE' not in self.state['intents'],'OWNER_PRIOR_ATTEMPT_RECONCILE')
        self.preflight()
        release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
        release['deployment']=self.state['deployment']
        folder=RELEASE_PARENT/('propertyaigent-owner-'+PERIOD)
        b,p=fixed_binding(release,self.state['profile'],self.db.address,self.state['original_guard'])
        b.update(release_root=str(folder),submission_intent_path=str(folder/'submission.intent.json'),credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=self.state['stable_credentials']['verifier_sha256'])
        if 'preparation_failure' in self.state:self.state.pop('failure',None)
        self.state.update(binding=b,policy=p,status='RELEASE_BOUND');self.intent('RELEASE')
        try:
            folder.mkdir(mode=0o700)
            self.intent('PERIOD')
            journal={'version':'FINITE_INTAKE_PERIOD_V1','state':'ARMED_NO_RETRY','binding':b,'policy':p}
            self.state['period_journal']=journal;self.save()
            with envelope(),self.db.connection() as c:
                def period_saved(value):
                    self.state['period_journal']=copy.deepcopy(value)
                    if value.get('state')=='COMMIT_ACKNOWLEDGED':self.journal.save(self.state,connection=c)
                period=issue_period(c,b,p,journal,period_saved)
            self.state['period_receipt']=period;self.ack('PERIOD')
            self.intent('ACTIVATE')
            with envelope(),self.db.connection() as c:
                prepared=op.prepare_activation(c,b,stable_credentials=self.state['stable_credentials']['passwords'])
                self.state['access']=copy.deepcopy(prepared);self.journal.save(self.state,connection=c)
                def access_saved(value):
                    self.state['access']=copy.deepcopy(value)
                    if value.get('state')=='ACTIVATION_ACKNOWLEDGED':self.journal.save(self.state,connection=c)
                self.state['activation_receipt']=op.activate(c,b,access_saved,prepared=prepared)
            self.ack('ACTIVATE')
            self.state['qualification']={'status':'REQUIRED_IN_ACTUAL_RUNTIME_BEFORE_SOURCE'};self.save()
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
            self.state['failure']=safe_result(exc);self.state['failure']['phase']=max(self.state['intents'],key=lambda x:self.state['intents'][x]['at'],default='RUN');self.state['pipeline_status']='NOT_VERIFIED';self.save()
            self.state['private_failure_detail']=private_failure(exc,self.state['failure']['phase']);self.save()
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
        # Independent database containment never depends on GitHub or Render.
        access=self.state.get('access')
        if access and access.get('state')!='DATABASE_CLOSURE_ACKNOWLEDGED':
            try:
                with envelope(),self.db.connection() as c:
                    def closed_saved(value):
                        self.state['access']=copy.deepcopy(value);self.journal.save(self.state,connection=c)
                    self.state['closure_receipt']=op.close(c,access,closed_saved)
                self.save()
            except BaseException as exc:self.state['closure_failure']=safe_result(exc);self.save()
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
            if r.get('state')=='PUT_ACKNOWLEDGED' or r.get('reconciliation')=='EXPECTED':
                try:
                    with self.api() as api:self.state['restoration_receipt']=restore_handoff(api,access,self.access_save,self.state.get('job',{}).get('id'))
                    self.save()
                except BaseException as exc:self.state['restoration_failure']=safe_result(exc);self.save()
        with self.api() as api:
            service=api.call('GET');environment=env_values(api.call('GET','/env-vars?limit=100'))
        self.state['final_service']={'suspended':service.get('suspended')=='suspended','configuration_equal':service_guard(service)==self.state['original_guard'],
            'environment_equal':environment==self.state['original_environment']}
        handoff_closed=not access or not access.get('render') or access['render'].get('state') in ('RESTORATION_ACKNOWLEDGED','RESTORATION_VERIFIED_BY_READBACK') or access['render'].get('reconciliation')=='ORIGINAL'
        self.state['status']='CLOSED' if (not access or access.get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED') and handoff_closed and all(self.state['final_service'].values()) else 'CONTAINMENT_REQUIRES_REVIEW'
        self.save()
    def recover(self):
        self.state=self.journal.load();op.require(self.state is not None,'OWNER_NO_RECOVERY_STATE')
        if 'binding' not in self.state:self.recover_build()
        else:self.cleanup()
        return self.summary()
    def inspect(self):
        """Read-only reconciliation; never calls prepare, recovery or save."""
        self.state=self.journal.load()
        if self.state is None:return {'status':'NOT_PREPARED','period':PERIOD,'read_only':True}
        value=self.summary();value['workflow_status']=value['status'];value['status']='READ_ONLY_EVIDENCE_SAVED';value['read_only']=True
        value['preparation_progress']={name:entry['state'] for name,entry in self.state.get('intents',{}).items()}
        value['artifact_verified']='artifact' in self.state
        value['release_intent_present']='RELEASE' in self.state.get('intents',{})
        value['job_intent_present']='ONE_JOB' in self.state.get('intents',{})
        value['job_recorded']=bool(self.state.get('job'))
        value['access_state']=self.state.get('access',{}).get('state')
        with envelope(),self.db.connection() as c:
            c.execute('BEGIN READ ONLY')
            try:
                roles=c.execute(op.ROLE_QUERY,(list(op.ROLES),)).fetchall()
                value['runtime_roles']=[{'role':r[0],'login':r[1],'password_null':r[2]} for r in roles]
                value['period_present']=PERIOD in op.control(c).get('intake_periods',{})
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
                'failure':s.get('failure'),'closure_failure':s.get('closure_failure'),'restoration_failure':s.get('restoration_failure'),
                'independent_result':s.get('independent_result'),'source_result':s.get('source_result'),'closure_receipt':s.get('closure_receipt'),
                'artifact_reconciliation':s.get('artifact_reconciliation'),'preparation_failure':s.get('preparation_failure'),
                'stable_configuration':s.get('stable_configuration'),'credential_policy':(s.get('binding') or {}).get('credential_policy'),'runtime_qualification':s.get('runtime_qualification'),'predecessor':s.get('predecessor'),'qualification':s.get('qualification'),'qualification_attempts':s.get('qualification_attempts')}
