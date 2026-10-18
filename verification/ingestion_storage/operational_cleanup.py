"""Single-use, owner-local revoke-only safety cleanup. No ingestion entrypoint.

Production runs this reviewed file externally against the unchanged checkout.
Disposable tests inject only the connector and loopback real-gh transport.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import time
import threading

REVISION = 'ad8d5211afcc635c5bc50f4963adde4f31b4ef62'
TREE = '8482c3d62c79bcbdb6ce91b1b8075751bcaf9893'
AUTHORITY = 'AUTHORISE_OPERATIONAL_SAFETY_CLEANUP_TIMING_ONCE_20261018'
CAPTURE_AUTHORITY = 'AUTHORISE_BOLTON_CAPTURE_QUEUE_ONCE_20261018_CAPTURE'
CAPTURE_KEY = '48e304a92fbe01bac655be36b1c4d6f8fa29ab11857501911b68929bec790699'
GRANT_SHA256 = 'd456f1849accfbde3d7c7dfeb576cad8211693c141cc542b6fb2e6363cb95f0c'
ORIGINAL_AUDIT_SHA256 = 'dd7c5814b686c8dd4c23451238d88fa76e095040ac30871e4139936b9d02677f'
ORIGINAL_CHAIN = 'cb86102ae32d0e91c8b1acd36b95f60cf7e4a35c28fecabe8cd359a4e678f679'
ORIGINAL_REGISTRATION = '5dd3cc1f5252b80d55d31ec3e98303d5a5fb609f212776d29d65c799819746dc'
STOP = {'reason': 'CONSUMED_SALFORD_GLOBAL_STOP', 'run': '38884069913'}
SCOPE = 'propertyaigent-operational-cleanup-timing-20261018.scope'
TIMING = dict(setup_seconds=10, credential_input_seconds=300, active_seconds=45,
              work_seconds=40, outer_seconds=355)
PREDECESSOR_REGISTRATION = '3c10291a1b2e7f3d81f463a619fca177a224259f1ed708f01d8d0a5e935cc377'
PREDECESSOR_RESULT = 'b47bdf072fa87e51157f29fda689dad72b44f49de34f712c5cb680cf751f110d'
PREDECESSOR_AUDIT = '6bdd6f3616230aad804908319627fc69f5254c11eca8836b119b1052651fbf4e'
ROLES = ['ingestion_effect_login', 'ingestion_worker_login']
MEMBERSHIPS = [('ingestion_effect_login', 'ingestion_effect_broker'), ('ingestion_worker_login', 'ingestion_worker')]
SECRETS = ['INGESTION_WORKER_DATABASE_URL', 'INGESTION_EFFECT_DATABASE_URL']
SECRET_PATH = 'repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets'
LIMITS = dict(connections=2, commands=32, supervised_seconds=45, returned_data_value_bytes=1048576,
              actual_memory_bytes=268435456, exported_bytes=524288, deletes=2, names_reads=2)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

class Stop(RuntimeError):
    pass

class Journal:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, exist_ok=False)
        self.file = self.root / 'events.jsonl'
        self.file.touch(mode=0o600, exist_ok=False)
        self.sequence = 0
        self.head = '0' * 64
        self.started = time.monotonic()
        self.sync_directory()

    def sync_directory(self):
        for p in (self.root, self.root.parent):
            fd = os.open(p, os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)

    def emit(self, event, payload):
        row = dict(sequence=self.sequence, event=event, payload=payload,
                   elapsed_seconds=time.monotonic()-self.started, previous_sha256=self.head)
        sha = digest(row)
        raw = canonical(dict(row, sha256=sha)) + b'\n'
        if self.file.stat().st_size + len(raw) > 256*1024:
            raise Stop('AUDIT_CLOSURE_RESERVE')
        with self.file.open('ab') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        self.sequence += 1; self.head = sha

    def save(self, result):
        raw = canonical(result)
        if len(raw) > 128*1024: raise Stop('RESULT_BOUND')
        p = self.root / 'final-result.json'
        with p.open('xb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        self.sync_directory()
        if p.read_bytes() != raw: raise Stop('RESULT_READBACK')
        return dict(audit_sha256=hashlib.sha256(self.file.read_bytes()).hexdigest(),
                    audit_chain_head=self.head, result_sha256=hashlib.sha256(raw).hexdigest(),
                    exported_bytes=len(raw)+self.file.stat().st_size)

class Memory:
    def __init__(self):
        lines = Path('/proc/self/cgroup').read_text().splitlines()
        if len(lines) != 1 or not lines[0].startswith('0::/'):
            raise Stop('CGROUP_V2_REQUIRED')
        relative = Path(lines[0][3:])
        if relative.name != SCOPE or '..' in relative.parts:
            raise Stop('DEDICATED_CLEANUP_SCOPE_REQUIRED')
        self.root = Path('/sys/fs/cgroup') / str(relative).lstrip('/')
        if self.root.is_symlink() or self.root.joinpath('cgroup.procs').read_text().split() != [str(os.getpid())]:
            raise Stop('EXCLUSIVE_CLEANUP_SCOPE_REQUIRED')
        self.snapshot()

    def snapshot(self):
        from verification.ingestion_storage.memory_enforcement import values
        if any(self.root.joinpath(n).read_text().strip() != v for n, v in
               [('memory.max', '268435456'), ('memory.swap.max', '0'), ('memory.oom.group', '1')]):
            raise Stop('KERNEL_MEMORY_ENFORCEMENT_LOST')
        events = values(self.root/'memory.events')
        result = dict(peak_bytes=int(self.root.joinpath('memory.peak').read_text()), events=events)
        if any(events.get(k) for k in ('max', 'oom', 'oom_kill')):
            raise Stop('KERNEL_MEMORY_LIMIT_HIT')
        return result

    def close(self):
        result = self.snapshot()
        if self.root.joinpath('cgroup.procs').read_text().split() != [str(os.getpid())]:
            raise Stop('OWNED_PROCESSES_REMAIN')
        return dict(**result, controller_only_in_scope=True,
                    scope_removal='SYSTEMD_ON_CONTROLLER_EXIT_NOT_CLAIMED_BEFORE_EXIT')

STATE_SQL = """SELECT jsonb_build_object(
 'roles',(SELECT jsonb_agg(jsonb_build_array(r.rolname,r.rolcanlogin,a.rolpassword IS NULL,
 r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication) ORDER BY r.rolname)
 FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s)),
 'memberships',(SELECT coalesce(jsonb_agg(jsonb_build_array(m.member::regrole::text,
 m.roleid::regrole::text,m.admin_option,m.inherit_option,m.set_option,m.grantor::regrole::text)
 ORDER BY m.member::regrole::text,m.roleid::regrole::text),'[]'::jsonb)
 FROM pg_catalog.pg_auth_members m WHERE m.member=ANY(%s::regrole[])),
 'sessions',(SELECT coalesce(jsonb_agg(jsonb_build_object('pid',pid,'usename',usename,'state',state)
 ORDER BY pid),'[]'::jsonb) FROM pg_catalog.pg_stat_activity WHERE usename=ANY(%s)))"""
RECORDS_SQL = """SELECT coalesce(jsonb_agg(to_jsonb(w) ORDER BY w.key),'[]'::jsonb),
 (SELECT count(*) FROM public.ingestion_work_attempts) FROM
 (SELECT * FROM public.ingestion_work_items WHERE key<>repeat('0',64) ORDER BY key LIMIT 5) w"""

class Cleanup:
    def __init__(self, connector, journal, *, github_runner=subprocess.run,
                 identity='postgres', memory=None, started=None, expiry=None):
        self.connector=connector; self.journal=journal; self.github_runner=github_runner
        self.identity=identity; self.memory=memory
        self.expiry=expiry
        self.started=time.monotonic() if started is None else started
        self.connections=0; self.commands=0; self.returned=0; self.database_active=0.0
        self.opened=0; self.closed=0; self.deletes=0; self.reads=0
        self.phase='INITIAL'; self.db_commit='NOT_ATTEMPTED'; self.readbacks={}
        self.secret_deletions=[]; self.baseline_records=None; self.before_control=None

    def accounting(self):
        return dict(connections=self.connections, commands=self.commands,
                    returned_data_value_bytes=self.returned, database_active_seconds=self.database_active,
                    supervised_seconds=time.monotonic()-self.started, connections_opened=self.opened,
                    connections_closed=self.closed, deletes=self.deletes, names_reads=self.reads)

    def emit(self, event, payload):
        self.journal.emit(event, dict(payload, accounting=self.accounting()))

    def check(self):
        if self.expiry is not None and datetime.now(timezone.utc)>=self.expiry:
            raise Stop('CLEANUP_EXPIRED')
        if time.monotonic()-self.started >= TIMING['work_seconds']: raise Stop('CLOSURE_RESERVE')
        if self.memory is not None: self.memory.snapshot()
        if sum(p.stat().st_size for p in self.journal.root.iterdir() if p.is_file()) > 384*1024:
            raise Stop('EXPORTED_OUTPUT_RESERVE')

    @contextmanager
    def connection(self):
        self.check()
        if self.connections >= 2: raise Stop('CONNECTION_BOUND')
        self.phase='DATABASE_CONNECT_'+str(self.connections+1)
        self.connections += 1; self.emit('connection_intent', {'ordinal':self.connections})
        c=None; began=time.monotonic()
        try:
            c=self.connector(); self.opened+=1
            self.database_active+=time.monotonic()-began
            self.emit('connection_open', {'ordinal':self.connections})
            yield c
        except BaseException:
            if c is None: self.database_active+=time.monotonic()-began
            raise
        finally:
            if c is not None:
                closing=time.monotonic()
                c.close()
                self.database_active+=time.monotonic()-closing
                if not c.closed: raise Stop('DATABASE_CLOSE_UNCERTAIN')
                self.closed+=1; self.emit('connection_closed', {'ordinal':self.connections})

    def q(self, c, operation, statement, params=None, *, effect=False):
        self.check()
        if self.commands >= 32: raise Stop('COMMAND_BOUND')
        self.commands+=1; self.phase=operation
        self.emit('database_intent', {'operation':operation,'effect':effect})
        began=time.monotonic()
        try:
            cursor=c.execute(statement,params)
            if cursor.pgresult is not None:
                self.returned+=sum(len(cursor.pgresult.get_value(r,k) or b'')
                                   for r in range(cursor.pgresult.ntuples)
                                   for k in range(cursor.pgresult.nfields))
            if self.returned > 1048576: raise Stop('RETURNED_DATA_VALUE_BOUND')
            rows=cursor.fetchall() if cursor.description else []
        except BaseException:
            self.database_active+=time.monotonic()-began
            if effect:
                self.emit('database_effect_uncertain', {'operation':operation})
                raise Stop('DATABASE_EFFECT_UNCERTAIN') from None
            raise
        self.database_active+=time.monotonic()-began
        self.emit('database_ack', {'operation':operation,'effect':effect})
        self.check()
        return rows

    def names(self):
        if self.reads>=2: raise Stop('NAMES_READ_BOUND')
        self.reads+=1
        value=self.api('GET',SECRET_PATH+'?per_page=100')
        if (not isinstance(value,dict) or type(value.get('total_count')) is not int
            or not 0<=value['total_count']<=100 or not isinstance(value.get('secrets'),list)):
            raise Stop('INCOMPLETE_SECRET_METADATA')
        names=[r.get('name') for r in value['secrets']]
        if (len(names)!=value['total_count'] or any(not isinstance(n,str) or
            not re.fullmatch('[A-Za-z0-9_]{1,100}',n) for n in names) or len(set(names))!=len(names)):
            raise Stop('INCOMPLETE_SECRET_NAMES')
        self.emit('secret_names_observed', {'names':sorted(names)})
        return set(names)

    def api(self, method, path):
        self.check(); self.phase='GITHUB_'+method
        if method=='DELETE':
            if path not in [SECRET_PATH+'/'+n for n in SECRETS] or self.deletes>=2:
                raise Stop('EXACT_DELETE_BOUND')
            self.deletes+=1
        elif method!='GET' or path!=SECRET_PATH+'?per_page=100':
            raise Stop('EXACT_GITHUB_ROUTE')
        self.emit('github_intent', {'method':method,'path':path})
        command=['gh','api','--method',method,path]
        if method=='DELETE': command+=['--include','--silent']
        try:
            result=self.github_runner(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,timeout=min(3,max(.01,TIMING['work_seconds']-(time.monotonic()-self.started))))
            if result.returncode or len(result.stdout)+len(result.stderr)>65536:
                raise Stop('GITHUB_ACK_UNCERTAIN')
            if method=='DELETE':
                if re.findall(rb'^HTTP/\S+\s+(\d{3})(?:\s|$)',result.stdout,re.M)!=[b'204']:
                    raise Stop('DELETE_ACK_UNCERTAIN')
                value=None; self.secret_deletions.append(path.rsplit('/',1)[1])
            else: value=json.loads(result.stdout)
        except BaseException:
            raise Stop('GITHUB_ACK_UNCERTAIN') from None
        self.emit('github_ack', {'method':method,'path':path})
        self.check(); return value

    def state(self,c,label,disabled):
        value=self.q(c,label,STATE_SQL,(ROLES,ROLES,ROLES))[0][0]
        self.readbacks[label]=value; self.emit('access_readback', {'label':label,'actual':value})
        expected=[[r,not disabled,disabled,False,False,False,False,False] for r in ROLES]
        memberships=[] if disabled else [[r,cap,False,True,False,self.identity] for r,cap in MEMBERSHIPS]
        if value!={'roles':expected,'memberships':memberships,'sessions':[]}:
            raise Stop('UNEXPECTED_ACCESS_OR_SESSIONS')

    def control(self,c,label):
        ctl=self.q(c,label,"SELECT outcome::jsonb FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
        self.emit('control_readback', {'label':label,'sha256':digest(ctl),
                  'global_stop':ctl.get('global_stop'),'manual_stop':ctl.get('manual_stop'),
                  'generation':ctl.get('hard_stop_generation',0),
                  'grant_expiry':ctl.get('grants',{}).get(CAPTURE_AUTHORITY,{}).get('expires_at'),
                  'exception_expiry':ctl.get('bolton_exceptions',{}).get(CAPTURE_AUTHORITY,{}).get('expires_at')})
        return ctl

    def records(self,c,label):
        records,attempts=self.q(c,label,RECORDS_SQL)[0]
        self.emit('ledger_readback', {'label':label,'rows_excluding_control':len(records),
                  'sha256':digest(records),'attempts':attempts})
        roots=[r for r in records if r['key']==CAPTURE_KEY]
        if len(records)!=4 or attempts!=0 or len(roots)!=1:
            raise Stop('UNEXPECTED_LEDGER_RECORDS')
        root=roots[0]
        if (root['state']!='QUEUED' or root['attempt_count']!=0 or root['checkpoint'] is not None
            or root['outcome'] is not None or root['task']!='DISCOVERY'):
            raise Stop('CAPTURE_WORK_CHANGED')
        if self.baseline_records is not None and records!=self.baseline_records:
            raise Stop('LEDGER_PRESERVATION_READBACK')
        self.baseline_records=records

    def execute(self):
        names=self.names()
        if not set(SECRETS)<=names or 'DATABASE_URL' not in names:
            raise Stop('UNEXPECTED_INITIAL_SECRET_NAMES')
        with self.connection() as c:
            flags=self.q(c,'migration_identity',"SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,has_column_privilege(current_user,'pg_catalog.pg_authid','rolname','SELECT') AND has_column_privilege(current_user,'pg_catalog.pg_authid','rolpassword','SELECT') FROM pg_catalog.pg_roles WHERE rolname=current_user")[0]
            self.emit('migration_identity_observed', {'flags':list(flags)})
            if flags!=(self.identity,self.identity,False,True,True,True,True): raise Stop('MIGRATION_CONTRACT')
            self.q(c,'begin_cleanup','BEGIN',effect=True)
            self.q(c,'temporary_owner','GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            ctl=self.control(c,'original_control'); self.before_control=deepcopy(ctl)
            grant=ctl.get('grants',{}).get(CAPTURE_AUTHORITY)
            exception=ctl.get('bolton_exceptions',{}).get(CAPTURE_AUTHORITY)
            if (ctl.get('global_stop')!=STOP or ctl.get('manual_stop')!='STORAGE_TEST_STOP'
                or ctl.get('hard_stop_generation',0)!=0 or set(ctl.get('grants',{}))!={CAPTURE_AUTHORITY}
                or set(ctl.get('bolton_exceptions',{}))!={CAPTURE_AUTHORITY} or digest(grant)!=GRANT_SHA256
                or not isinstance(exception,dict) or exception.get('grant_binding')!={k:v for k,v in grant.items() if k not in {'source_calls','writes'}}
                or exception.get('revision')!=REVISION or exception.get('expires_at')!=grant['expires_at']):
                raise Stop('CONSUMED_GRANT_OR_STOP_BINDING')
            self.state(c,'before_access',False); self.records(c,'before_records')
            updated=deepcopy(ctl)
            updated['grants'][CAPTURE_AUTHORITY]['expires_at']=0
            updated['bolton_exceptions'][CAPTURE_AUTHORITY]['expires_at']=0
            updated['hard_stop_generation']=1
            updated['last_hard_stop']='OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018'
            changed=self.q(c,'invalidate_only_consumed_authority',"UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64) AND outcome::jsonb=%s::jsonb RETURNING key",(json.dumps(updated),json.dumps(ctl)),effect=True)
            if changed!=[('0'*64,)]: raise Stop('EXACT_CONTROL_UPDATE_READBACK')
            for role in ROLES:
                self.q(c,'disable_'+role,'ALTER ROLE '+role+' NOLOGIN PASSWORD NULL',effect=True)
            for role,cap in MEMBERSHIPS:
                self.q(c,'revoke_'+role,'REVOKE '+cap+' FROM '+role+' GRANTED BY CURRENT_USER',effect=True)
            self.q(c,'remove_temporary_owner','REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
            self.db_commit='INTENT_UNCERTAIN'
            self.q(c,'commit_cleanup','COMMIT',effect=True); self.db_commit='ACKNOWLEDGED'
        with self.connection() as c:
            self.state(c,'reconnected_access',True)
            self.q(c,'begin_readback','BEGIN',effect=True)
            self.q(c,'temporary_readback_owner','GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
            actual=self.control(c,'reconnected_control'); self.records(c,'reconnected_records')
            if actual!=updated: raise Stop('COMMITTED_CONTROL_READBACK')
            self.q(c,'rollback_readback','ROLLBACK',effect=True)
            caps=self.q(c,'temporary_capability_readback',"SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET')")[0]
            self.emit('temporary_capability_observed', {'flags':list(caps)})
            if caps!=(False,False): raise Stop('TEMPORARY_CAPABILITY_REMAINS')
        for name in SECRETS: self.api('DELETE',SECRET_PATH+'/'+name)
        after=self.names()
        if after!=names-set(SECRETS): raise Stop('SECRET_ABSENCE_OR_PRESERVATION')
        self.emit('access_disabled_verified', {'grant_executable':False,'exception_executable':False,
                  'original_stops_preserved':True,'hard_stop_generation':1,'temporary_secrets_absent':True,
                  'database_url_preserved':True,'ledger_preserved':True})
        return dict(status='SAFETY_CLEANUP_ACCESS_DISABLED',accounting=self.accounting(),readbacks=self.readbacks,
                    database_commit=self.db_commit,deleted_secrets=self.secret_deletions,
                    original_cleanup='UNCERTAIN_PRESERVED',pipeline_retry='HELD',stage4='OPEN')

def verify_original(path):
    if path.is_symlink() or path.stat().st_size!=44272: raise Stop('ORIGINAL_AUDIT_BOUND')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ORIGINAL_AUDIT_SHA256: raise Stop('ORIGINAL_AUDIT_HASH')
    previous='0'*64; events=[]
    for i,line in enumerate(raw.splitlines()):
        row=json.loads(line); sha=row.pop('sha256')
        if row['sequence']!=i or row['previous_sha256']!=previous or digest(row)!=sha:
            raise Stop('ORIGINAL_AUDIT_CHAIN')
        previous=sha; events.append(row)
    if len(events)!=175 or previous!=ORIGINAL_CHAIN or events[0]['payload']['registration_sha256']!=ORIGINAL_REGISTRATION:
        raise Stop('ORIGINAL_ATTEMPT_BINDING')

def arm_deadline(seconds, reason):
    def expired(*_): raise Stop(reason)
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(.001, seconds))


def zero_accounting():
    return dict(connections=0, commands=0, returned_data_value_bytes=0,
                database_active_seconds=0.0, supervised_seconds=0.0,
                connections_opened=0, connections_closed=0, deletes=0, names_reads=0)


class HardDeadline:
    """A blocked final output cannot turn a caught signal into extra runtime.

    Uses no subprocess, credential or network capability. The systemd scope
    remains the independent outer containment if this interpreter cannot run.
    """
    def __init__(self, end):
        self.cancelled=threading.Event()
        def watch():
            if not self.cancelled.wait(max(0,end-time.monotonic())): os._exit(124)
        self.thread=threading.Thread(target=watch,name='cleanup-hard-deadline',daemon=True)
        self.thread.start()

    def close(self):
        self.cancelled.set(); self.thread.join(timeout=.1)
        if self.thread.is_alive(): os._exit(124)


def finalise(journal, result, *, outer_started, active_started, input_seconds, output=print):
    """One bounded result attempt; deadline/output failure never raises a second traceback.

    The caller keeps the finalisation deadline armed. Existing persisted evidence
    is never overwritten if a late failure makes its receipt uncertain.
    """
    result['phase_timing'] = dict(credential_input_seconds=input_seconds,
        active_seconds_before_finalisation=0.0 if active_started is None else time.monotonic()-active_started,
        total_seconds_before_finalisation=time.monotonic()-outer_started)
    try:
        receipt=journal.save(result)
        now=time.monotonic()
        output(json.dumps(dict(result, **receipt, audit=str(journal.file),
            active_seconds_after_audit_flush=0.0 if active_started is None else now-active_started,
            total_seconds_after_audit_flush=now-outer_started), sort_keys=True), flush=True)
        return result
    except BaseException:
        fallback=dict(status='STOP_RECONCILE_NO_RETRY', cleanup='UNCERTAIN',
            reason='FINAL_EVIDENCE_OR_OUTPUT_UNCERTAIN',
            prior_status=result.get('status'), audit=str(journal.file),
            accounting=result.get('accounting',zero_accounting()),
            phase_timing=result['phase_timing'])
        # One small output attempt only; no evidence replay or compensating effect.
        try: output(json.dumps(fallback,sort_keys=True),flush=True)
        except BaseException: pass
        return fallback


def run_session(journal, memory, expiry, reader, prepare, *, outer_started=None,
                timing=TIMING, resources=None, output=print):
    """Shared production/rehearsal phase controller; no CLI timing/route override.

    reader only obtains hidden local input. prepare is not called until input
    ends and validity is checked again; source/SQL/secret effects live in Cleanup.
    """
    from verification.ingestion_storage.tls_trust import owned_resources
    resources=resources or owned_resources
    outer_started=time.monotonic() if outer_started is None else outer_started
    baseline=resources(); worker=None; active_started=None; input_started=time.monotonic()
    input_seconds=0.0; phase='SECURE_CREDENTIAL_INPUT'; credential=None; hard=None
    try:
        remaining=timing['outer_seconds']-(time.monotonic()-outer_started)-timing['active_seconds']
        if remaining<=0: raise Stop('OUTER_CLOSURE_RESERVE')
        arm_deadline(min(timing['credential_input_seconds'],remaining),'SECURE_INPUT_DEADLINE')
        journal.emit('credential_input_started',{'maximum_seconds':timing['credential_input_seconds'],
                     'database_and_secret_operations_permitted':False})
        credential=reader()
        input_seconds=time.monotonic()-input_started
        # Check once more before route resolution, connector creation or any API.
        if datetime.now(timezone.utc)>=expiry: raise Stop('CLEANUP_EXPIRED')
        journal.emit('credential_input_completed',{'elapsed_seconds':input_seconds})
        active_started=time.monotonic(); phase='ACTIVE_PREPARATION'
        hard=HardDeadline(min(active_started+timing['active_seconds'],outer_started+timing['outer_seconds']))
        arm_deadline(min(timing['work_seconds'],timing['outer_seconds']-(active_started-outer_started)),
                     'ACTIVE_WORK_DEADLINE')
        journal.emit('active_cleanup_started',{'maximum_seconds':timing['active_seconds'],
                     'work_seconds':timing['work_seconds'],'finalisation_reserve_seconds':timing['active_seconds']-timing['work_seconds']})
        worker=prepare(credential,active_started)
        credential=None
        result=worker.execute()
        proof=memory.close() if memory is not None else {'status':'DISPOSABLE_NO_MEMORY_PROOF'}
        current=resources()
        if (current['children'] or current['socket_fds']-baseline['socket_fds']
            or worker.opened!=worker.closed): raise Stop('OWNED_RESOURCE_CLOSURE')
        result.update(cleanup='CLOSED',memory=proof,new_sockets=0,live_children=0,accounting=worker.accounting())
        journal.emit('closure_verified',result)
    except BaseException as exc:
        if active_started is None: input_seconds=time.monotonic()-input_started
        reason=str(exc) if isinstance(exc,Stop) and re.fullmatch('[A-Z0-9_]{1,100}',str(exc)) else 'SAFE_CLEANUP_FAILURE'
        native=getattr(exc,'orig',exc); code=getattr(native,'sqlstate',None)
        code=code if isinstance(code,str) and re.fullmatch('[A-Z0-9]{5}',code) else None
        proof={'status':'UNKNOWN'}
        try:
            if memory is not None: proof=memory.close()
        except BaseException: pass
        result=dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',reason=reason,sqlstate=code,
            exception_class=type(native).__name__ if re.fullmatch('[A-Za-z0-9_]{1,80}',type(native).__name__) else 'UNKNOWN',
            phase=worker.phase if worker else phase,memory=proof,
            accounting=worker.accounting() if worker else zero_accounting(),
            database_commit=worker.db_commit if worker else 'NOT_ATTEMPTED',
            actual_readbacks=worker.readbacks if worker else {},
            acknowledged_secret_deletions=worker.secret_deletions if worker else [])
        try: journal.emit('stopped',result)
        except BaseException: result['audit_stop_record']='UNCERTAIN'
    finally:
        credential=None
    # Input failure also gets a finite five-second finalisation reserve, taken
    # from the unused active allowance; no database/GitHub work becomes eligible.
    end=(active_started+timing['active_seconds']) if active_started is not None else time.monotonic()+(timing['active_seconds']-timing['work_seconds'])
    end=min(end,outer_started+timing['outer_seconds'])
    if hard is None: hard=HardDeadline(end)
    arm_deadline(end-time.monotonic(),'FINALISATION_DEADLINE')
    try:
        return finalise(journal,result,outer_started=outer_started,active_started=active_started,
                        input_seconds=input_seconds,output=output)
    finally:
        hard.close()
        signal.setitimer(signal.ITIMER_REAL,0)


def main():
    began=time.monotonic()
    p=argparse.ArgumentParser(); p.add_argument('--registration',type=Path,required=True)
    p.add_argument('--registration-sha256',required=True); args=p.parse_args()
    arm_deadline(TIMING['setup_seconds'],'SETUP_DEADLINE')
    if sys.platform!='linux' or not sys.stdin.isatty() or not sys.stderr.isatty(): raise SystemExit('SECURE_LINUX_TTY_REQUIRED')
    forbidden=('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_DEBUG','GH_CONFIG_DIR',
               'GH_HTTP_UNIX_SOCKET','SSL_CERT_FILE','SSL_CERT_DIR','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')
    if any(os.environ.get(n) for n in forbidden) or any(k.startswith('PG') for k in os.environ) or os.environ.get('GH_HOST','github.com')!='github.com':
        raise SystemExit('UNREVIEWED_CREDENTIAL_ROUTE_OR_ENVIRONMENT')
    if args.registration.is_symlink() or args.registration.stat().st_size>32768: raise SystemExit('REGISTRATION_BOUND')
    raw=args.registration.read_bytes(); reg=json.loads(raw)
    if (hashlib.sha256(raw).hexdigest()!=args.registration_sha256 or reg.get('authority')!=AUTHORITY
        or reg.get('status')!='OWNER_APPROVED_CLEANUP_ONCE' or reg.get('limits')!=LIMITS
        or reg.get('timing')!=TIMING or reg.get('consumed_predecessor_registration_sha256')!=PREDECESSOR_REGISTRATION
        or reg.get('helper_sha256')!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        or reg.get('original_audit_sha256')!=ORIGINAL_AUDIT_SHA256): raise SystemExit('EXACT_CLEANUP_BINDING')
    expiry=datetime.fromisoformat(reg['expires_at'])
    from datetime import timedelta
    now=datetime.now(timezone.utc)
    if expiry.tzinfo is None or not now<expiry<=now+timedelta(hours=24): raise SystemExit('CLEANUP_EXPIRED')
    if (not re.fullmatch('[0-9a-f]{40}',reg.get('revision','')) or not re.fullmatch('[0-9a-f]{40}',reg.get('tree',''))
        or subprocess.check_output(['git','rev-parse','HEAD'],text=True,timeout=2).strip()!=reg['revision']
        or subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True,timeout=2).strip()!=reg['tree']
        or subprocess.check_output(['git','status','--porcelain'],text=True,timeout=2).strip()): raise SystemExit('CLEAN_APPROVED_CHECKOUT')
    for name,sha in reg['hashes'].items():
        path=Path(name)
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha: raise SystemExit('DEPENDENCY_HASH')
    state=Path.home()/'.local/state/propertyaigent'
    verify_original(state/'operational-capture-queue-once-20261018/events.jsonl')
    predecessor=state/'operational-safety-cleanup-once-20261018'
    for name,sha in [('events.jsonl',PREDECESSOR_AUDIT),('final-result.json',PREDECESSOR_RESULT)]:
        path=predecessor/name
        if path.is_symlink() or path.stat().st_size>2048 or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise SystemExit('CONSUMED_PREDECESSOR_EVIDENCE_CHANGED')
    memory=Memory()
    journal=Journal(state/'operational-safety-cleanup-timing-successor-20261018')
    journal.emit('consumed',dict(authority=AUTHORITY,registration_sha256=args.registration_sha256,
                 original_audit_sha256=ORIGINAL_AUDIT_SHA256,limits=LIMITS,timing=TIMING,
                 consumed_predecessor_registration_sha256=PREDECESSOR_REGISTRATION))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    from verification.ingestion_storage.credential_mapping import secure_migration_input
    def prepare(raw,active_started):
        from verification.ingestion_storage.tls_trust import verified_trust
        from verification.discovery.route_validation import validate_route
        url=validate_route(raw)
        if not url.password: raise Stop('EXPLICIT_EXISTING_MIGRATION_PASSWORD_REQUIRED')
        ca,_=verified_trust()
        dns=subprocess.run([sys.executable,'-I','-B','-c',"import socket,json;print(json.dumps(sorted({r[4][0] for r in socket.getaddrinfo('aws-0-eu-west-2.pooler.supabase.com',5432,family=socket.AF_INET,type=socket.SOCK_STREAM)})))"],
             env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3)
        addresses=json.loads(dns.stdout)
        import ipaddress
        if dns.returncode or not isinstance(addresses,list) or not 1<=len(addresses)<=32 or any(ipaddress.ip_address(x).version!=4 for x in addresses): raise Stop('BOUNDED_APPROVED_DNS')
        import psycopg
        def connector():
            return psycopg.connect(host=url.host,hostaddr=addresses[0],port=url.port,dbname=url.database,
                user=url.username,password=url.password,sslmode='verify-full',sslrootcert=str(ca),
                autocommit=True,prepare_threshold=None,connect_timeout=3,
                options='-c statement_timeout=2000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=5000 -c search_path=pg_catalog,public')
        return Cleanup(connector,journal,memory=memory,started=active_started,expiry=expiry)
    result=run_session(journal,memory,expiry,secure_migration_input,prepare,outer_started=began)
    raise SystemExit(0 if result['status']=='SAFETY_CLEANUP_ACCESS_DISABLED' and result['cleanup']=='CLOSED' else 1)

if __name__=='__main__':
    try: main()
    except SystemExit: raise
    except BaseException:
        # Before run_session no DB/secret path is callable. Never print a raw
        # exception or cause a second exception while reporting setup failure.
        try: print(json.dumps(dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',
                       phase='SETUP',reason='SETUP_NOT_COMPLETED')),flush=True)
        except BaseException: pass
        raise SystemExit(1)
