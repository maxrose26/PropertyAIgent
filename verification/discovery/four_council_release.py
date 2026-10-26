"""Fixed, inactive-by-default source-only release. No database or application effects.

Owner-local launch only. Live stop treatment requires a separately approved external
permit; this is NOT a synchronised reader of the database stop table.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from verification.ingestion_storage.operational_publication import GitHub, canonical, blob_bytes, Uncertain
from verification.ingestion_storage.operational_memory import OperationalMemory
from verification.ingestion_storage.memory_enforcement import MemoryUnavailable
from . import finite_acceptance as finite
from . import four_council_proof as proof
from .r0_recovery_proposal import resources, identities

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'FOUR_COUNCIL_SOURCE_RELEASE_V1'
SUCCESSOR_VERSION = 'THREE_COUNCIL_SOURCE_RELEASE_V1'
# Same rows/allowlist/stop policy as V1 under the BROWSER_SOURCE_V2 execution budget
# (docs/design/execution-budget-20261026/SPEC.md). V1 versions stay byte-identical.
SUCCESSOR_V2_VERSION = 'THREE_COUNCIL_SOURCE_RELEASE_V2'
SUCCESSORS = (SUCCESSOR_VERSION, SUCCESSOR_V2_VERSION)
BRANCH = 'stage4/narrow-continuation-evidence-20261016'
REPO = 'repos/maxrose26/PropertyAIgent'
PERMIT = 'OWNER_APPROVED_FIXED_FOUR_SOURCE_ONLY_STOP_TREATMENT'
SUCCESSOR_PERMIT = 'OWNER_APPROVED_FIXED_THREE_SOURCE_ONLY_STOP_TREATMENT'
SUCCESSOR_V2_PERMIT = 'OWNER_APPROVED_FIXED_THREE_SOURCE_ONLY_STOP_TREATMENT_V2'
PERMITS = {VERSION: PERMIT, SUCCESSOR_VERSION: SUCCESSOR_PERMIT, SUCCESSOR_V2_VERSION: SUCCESSOR_V2_PERMIT}
PRESERVED = ['CONSUMED_SALFORD_GLOBAL_STOP:38884069913', 'STORAGE_TEST_STOP']
ROWS = [dict(council=c, semantics=s, start=a, end=b) for c,s,a,b in [
    ('bury','RECEIVED','2026-10-08','2026-10-14'),
    ('rochdale','VALIDATED','2026-10-08','2026-10-14'),
    ('tameside','RECEIVED','2026-10-01','2026-10-07'),
    ('oldham','RECEIVED','2026-10-08','2026-10-14')]]
LIMITS = dict(observations=4, requests=110, mixed_source_bytes=29_971_520,
    worker_seconds=180, active_seconds=240, package_seconds=1920,
    exported_bytes=2*1024**2, github_requests=320, publication_requests=80,
    control_interval_seconds=2, control_call_timeout_seconds=5,
    control_visible_detection_seconds=7, source_close_seconds=5,
    per_job_seconds=480, setup_seconds=260, slot_active_seconds=60,
    closure_publication_seconds=160, per_slot_export_bytes=512*1024,
    source_memory_bytes=1024**3, aggregate_memory_bytes=1536*1024**2)
SUCCESSOR_LIMITS = dict(LIMITS, observations=3, requests=100,
    mixed_source_bytes=26_971_520, worker_seconds=135, active_seconds=180,
    package_seconds=1440)
# Ceilings, not reservations: 3 x 75s workers, 3 x 90s active; per-job/setup/package unchanged.
SUCCESSOR_V2_LIMITS = dict(SUCCESSOR_LIMITS, worker_seconds=225, active_seconds=270,
    slot_active_seconds=90, source_memory_bytes=1536*1024**2, aggregate_memory_bytes=2048*1024**2,
    execution_budget='BROWSER_SOURCE_V2')
VERSION_LIMITS = {VERSION: LIMITS, SUCCESSOR_VERSION: SUCCESSOR_LIMITS, SUCCESSOR_V2_VERSION: SUCCESSOR_V2_LIMITS}
LOCAL_OUTCOMES = ('ROCHDALE_RESULT_MARKER_TIMEOUT', 'IDOX_SEARCH_OR_SORT_TIMEOUT',
                  'OLDHAM_SORT_SELECTOR_ABSENT')
PACKAGES = ('requests','beautifulsoup4','lxml','playwright','psutil','cryptography')
DEPENDENCIES = ('docs/design/four-council-release-20261022/manifest.json','verification/discovery/four_council_release.py',
    'docs/design/four-council-release-20261022/owner-launch.sh',
    'verification/discovery/four_council_proof.py',
    'verification/discovery/finite_acceptance.py','verification/discovery/idox_window.py',
    'verification/discovery/arcus_ui_window.py','verification/discovery/arcus_ui_config.py',
    'verification/discovery/arcus_ui_audit.py','verification/discovery/r0_recovery_proposal.py',
    'verification/direct_reference/instrumented_probe.py',
    'verification/stage26b_l1/actions_runner.py','verification/stage26b_l1/request_boundary.py',
    'verification/ingestion_storage/operational_publication.py',
    'verification/ingestion_storage/operational_memory.py',
    'verification/ingestion_storage/memory_enforcement.py',
    'app/scrapers/discovery_idox.py','app/pipeline/discovery_contract.py',
    'app/pipeline/discovery_screening.py')
SUCCESSOR_DEPENDENCIES = ('docs/design/three-council-isolation-20261022/manifest.json',
    'verification/discovery/criteria_containment.py','verification/discovery/source_diagnostics.py')
SUCCESSOR_V2_DEPENDENCIES = ('docs/design/execution-budget-20261026/manifest.json',
    'docs/design/execution-budget-20261026/owner-launch.sh',
    'verification/discovery/criteria_containment.py','verification/discovery/source_diagnostics.py',
    'verification/discovery/execution_budget.py',
    'verification/ah_pg/requirements.lock','verification/discovery/runtime_dependencies.py')
VERSION_DEPENDENCIES = {VERSION: (), SUCCESSOR_VERSION: SUCCESSOR_DEPENDENCIES, SUCCESSOR_V2_VERSION: SUCCESSOR_V2_DEPENDENCIES}
# V2 also binds what the real worker path imports lazily (app.pipeline.site_linking: rapidfuzz, SQLAlchemy); exact pins are
# those of verification/ah_pg/requirements.lock (docs/design/real-worker-proof-20261026/SPEC.md). V1 bindings are unchanged.
V2_PACKAGES = PACKAGES + ('rapidfuzz','SQLAlchemy')
VERSION_PACKAGES = {VERSION: PACKAGES, SUCCESSOR_VERSION: PACKAGES, SUCCESSOR_V2_VERSION: V2_PACKAGES}

# Historical envelope, held here so V1 execution never imports or depends on execution_budget
# (absent from the V1 dependency bindings). Must equal execution_budget.HISTORICAL (tested).
HISTORICAL_BUDGET = dict(name=None, worker_seconds=45, source_outer_seconds=49, slot_active_seconds=60,
    source_memory_bytes=1024**3, aggregate_memory_bytes=1536*1024**2)


def select_budget(name):
    """None: the historical envelope with no import. A named budget loads the bound V2 module."""
    if name is None:return HISTORICAL_BUDGET
    from . import execution_budget as budgets
    return budgets.select(name)


def budget_of(version):
    """Execution budget selected by the release version (historical for V1 versions)."""
    return select_budget(VERSION_LIMITS[version].get('execution_budget'))


def memory_limits(version):
    """Keyword limits for OperationalMemory; V1 versions keep the unchanged default call."""
    limits=VERSION_LIMITS[version]
    if (limits['source_memory_bytes'],limits['aggregate_memory_bytes'])==(1024**3,1536*1024**2):return {}
    return dict(source_bytes=limits['source_memory_bytes'],aggregate_bytes=limits['aggregate_memory_bytes'])


class Stop(RuntimeError):
    """Only fixed codes from this module may be exported."""


def fixed_reason(error):
    code=str(error)
    # Fixed uppercase diagnostic codes only. No arbitrary driver/transport text.
    return code if re.fullmatch(r'[A-Z][A-Z0-9_]{1,64}',code) else 'UNCLASSIFIED_STOP'


MEMORY_CODES=frozenset({'CGROUP_V2_REQUIRED','DEDICATED_OPERATIONAL_SCOPE',
    'EXCLUSIVE_OPERATIONAL_SCOPE','MEMORY_DELEGATION_REQUIRED',
    'EXACT_AGGREGATE_MEMORY_LIMIT','MEMORY_ENFORCEMENT_LOST','MEMORY_LIMIT_HIT',
    'SOURCE_SURVIVORS','CONTROLLER_OWNED_SURVIVORS','FINALISATION_ONLY',
    'FINALISATION_BASELINE_UNAVAILABLE','MEMORY_EVENT_AFTER_LATCH','CGROUP_IDENTITY_CHANGED',
    'MEMORY_FIELD_UNAVAILABLE','CONTROLLER_OR_AGGREGATE_MEMORY_EVENT'})
PUBLICATION_CODES=frozenset({'PUBLICATION_BLOB_IDENTITY','GITHUB_RESPONSE_UNCERTAIN',
    'EVIDENCE_HEAD_MOVED_RECONCILE','BLOB_IDENTITY','PUBLICATION_HEAD_READBACK',
    'PUBLICATION_BYTES_READBACK','PRIOR_GITHUB_MUTATION_UNCERTAIN'})


def failure_detail(error,stage):
    """Never serialize an arbitrary exception message, URL or environment."""
    if isinstance(error,SourceFailure):return error.primary
    if isinstance(error,MemoryUnavailable):
        code=error.args[0] if len(error.args)==1 and isinstance(error.args[0],str) and error.args[0] in MEMORY_CODES else 'MEMORY_FAILURE_UNCLASSIFIED'
        kind='MEMORY'
    elif isinstance(error,Stop):code=fixed_reason(error);kind='STOP'
    elif isinstance(error,Uncertain):
        code=error.args[0] if len(error.args)==1 and isinstance(error.args[0],str) and error.args[0] in PUBLICATION_CODES else 'PUBLICATION_UNCERTAIN'
        kind='PUBLICATION'
    elif isinstance(error,(KeyboardInterrupt,SystemExit)):code='CANCELLED';kind='CANCELLATION'
    elif isinstance(error,subprocess.TimeoutExpired):code='LOCAL_PROCESS_TIMEOUT';kind='PROCESS'
    elif isinstance(error,PermissionError):code='LOCAL_PERMISSION_DENIED';kind='IO'
    elif isinstance(error,FileNotFoundError):code='LOCAL_PATH_UNAVAILABLE';kind='IO'
    elif isinstance(error,OSError):code='LOCAL_IO_FAILURE';kind='IO'
    elif isinstance(error,json.JSONDecodeError):code='SOURCE_JSON_MALFORMED';kind='FORMAT'
    else:code='UNCLASSIFIED_FAILURE';kind='UNKNOWN'
    return dict(stage=stage,code=code,kind=kind,message_exported=False)


# Fixed reasons a failed worker may print (the Stop codes raised on its path plus the guard's two generic ones).
# Child output is untrusted: only membership in this set is ever recorded (docs/design/real-worker-proof-20261026/SPEC.md).
# `reason_state=VALIDATED` means well-formed and allowlisted, not authentic: the worker asserts its own reason.
WORKER_EXIT_REASONS=frozenset({'CHILD_ENVIRONMENT','CHILD_GROUP','CHILD_EXECUTION_BUDGET','WORKER_EXPORT_BOUND',
    'SOURCE_CGROUP_V2','SOURCE_CGROUP_IDENTITY','SOURCE_MEMORY_ENFORCEMENT','SOURCE_OWNER_ENVIRONMENT',
    'UNCLASSIFIED_STOP','DEPENDENCY_UNAVAILABLE','PREPARATION_FAILURE'})
WORKER_OUTPUT_BOUND=4096


class BoundedPipe:
    """Non-blocking, size-bounded view of a child's stdout. Surplus is drained and discarded; EOF is never awaited."""
    def __init__(self):self.stream=None;self.fd=None;self.data=b'';self.discarded=0
    def attach(self,child):
        stream=getattr(child,'stdout',None)
        try:
            self.fd=stream.fileno();os.set_blocking(self.fd,False);self.stream=stream
        except (AttributeError,OSError,ValueError):self.fd=None
    def drain(self):
        for _ in range(16):
            if self.fd is None:return
            try:chunk=os.read(self.fd,65536)
            except BlockingIOError:return
            except OSError:self.fd=None;return
            if not chunk:self.fd=None;return
            room=max(0,WORKER_OUTPUT_BOUND-len(self.data));self.data+=chunk[:room];self.discarded+=len(chunk)-min(len(chunk),room)
    def close(self):
        try:
            if self.stream is not None:self.stream.close()
        except (OSError,ValueError):pass
        self.fd=None


def worker_exit_evidence(returncode,data,discarded):
    """Return code or signal, plus a fixed, validated reason where available. Never stores or executes child text."""
    ok=type(returncode) is int and -128<=returncode<=255
    evidence=dict(returncode=returncode if ok and returncode>=0 else None,signal=-returncode if ok and returncode<0 else None,
        reason=None,reason_state='ABSENT')
    if not data and not discarded:return evidence
    evidence['reason_state']='MALFORMED'
    try:
        if discarded or len(data)>WORKER_OUTPUT_BOUND:return evidence
        text=data.decode('ascii').strip()
        if '\n' in text or '\r' in text:return evidence
        def pairs(items):
            keys=[k for k,_ in items]
            if len(set(keys))!=len(keys):raise ValueError('duplicate')
            return dict(items)
        value=json.loads(text,object_pairs_hook=pairs)
        if (not isinstance(value,dict) or set(value)!={'status','reason','cleanup'} or value['status']!='STOP_RECONCILE_NO_RETRY'
                or value['cleanup']!='UNCERTAIN' or not isinstance(value['reason'],str)):return evidence
        if value['reason'] in WORKER_EXIT_REASONS:evidence.update(reason=value['reason'],reason_state='VALIDATED')
        else:evidence['reason_state']='UNRECOGNISED'
    except (UnicodeDecodeError,ValueError,RecursionError):pass
    return evidence


def descendant_identity(children,memory,limit=8):
    """Bounded identity of descendants seen at closure: no command line, environment or path. Unreadable is explicit."""
    def group_of(pid):
        try:
            name=Path(f'/proc/{pid}/cgroup').read_text().strip().rsplit('/',1)[-1]
            return 'SOURCE' if name==memory.source.name else 'CONTROLLER' if name==memory.controller.name else 'OTHER'
        except (OSError,AttributeError,ValueError):return 'UNAVAILABLE'
    listed=[]
    for child in list(children)[:limit]:
        try:
            name=str(child.name())
            listed.append(dict(pid=int(child.pid),ppid=int(child.ppid()),
                name=name[:32] if re.fullmatch(r'[A-Za-z0-9_.+:-]{1,32}',name[:32]) else 'UNPRINTABLE',
                status=str(child.status())[:16],age_seconds=round(max(0.0,time.time()-child.create_time()),1),group=group_of(int(child.pid))))
        except BaseException:listed.append(dict(identity='UNAVAILABLE'))
    return dict(descendants=listed,descendants_omitted=max(0,len(list(children))-limit)) if listed else {}


class SourceFailure(Stop):
    def __init__(self,primary,closure):
        super().__init__(primary['code']);self.primary=primary;self.closure=closure


def memory_observation(memory):
    try:return memory.observe()
    except BaseException as error:
        return dict(status='UNAVAILABLE',failure=failure_detail(error,'CONTAINMENT_OBSERVATION'),execution_authority=False)


def sha(raw): return hashlib.sha256(raw).hexdigest()
def now(): return datetime.now(timezone.utc)
def stamp(value):
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() != timedelta(0): raise Stop('UTC_REQUIRED')
    return dt

def selected_version(successor=False, version=None):
    """Explicit version wins; the historical boolean selects only the V1 pair."""
    if version is None:return SUCCESSOR_VERSION if successor else VERSION
    if version not in VERSION_LIMITS or (successor and version==VERSION):raise Stop('REGISTRATION_VERSION')
    return version


def manifest(*, successor=False, version=None):
    from app.pipeline.discovery_contract import SOURCE_ROOTS
    version=selected_version(successor,version);successor=version in SUCCESSORS
    rows=ROWS[1:] if successor else ROWS
    routes={row['council']:('https://'+SOURCE_ROOTS[row['council']][0]+SOURCE_ROOTS[row['council']][1].rstrip('/')+'/search.do?action=advanced&searchType=Application') for row in rows if row['council']!='rochdale'}
    routes['rochdale']=finite.dated_config(finite.UI_CASES['discovery_rochdale_ui_window'],'2026-10-08','2026-10-14').destination
    value=dict(version=version, rows=rows, source_routes=routes,
        limits=VERSION_LIMITS[version], retain_proof=True,
        no_transport_retry=True, persistence=False, coverage_advance=False,
        stop_policy='EXACT_SOURCE_LOCAL_ALLOWLIST' if successor else 'STOP_ALL_NON_COMPLETE', evidence_branch=BRANCH)
    if successor:value['continuation_allowlist']=list(LOCAL_OUTCOMES)
    return value


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True,timeout=5).strip()


def dependencies(*, successor=False, version=None):
    version=selected_version(successor,version)
    return {p:sha((ROOT/p).read_bytes()) for p in DEPENDENCIES+VERSION_DEPENDENCIES[version]}
def packages(version=None): return {p:importlib.metadata.version(p) for p in VERSION_PACKAGES[VERSION if version is None else version]}


def runtime_check(version, **kwargs):
    """Council-free dependency verdict for the interpreter running this call (see runtime_dependencies)."""
    from . import runtime_dependencies
    paths=[p for p in DEPENDENCIES+VERSION_DEPENDENCIES[version] if p.endswith('.py')]
    return runtime_dependencies.check(paths,VERSION_PACKAGES[version],**kwargs)


def render(release_id, revision, tree, evidence_head, issued, expires, *, released=False, successor=False, version=None):
    if not re.fullmatch(r'[a-z0-9-]{8,64}',release_id): raise Stop('RELEASE_ID')
    for v in (revision,tree,evidence_head):
        if not re.fullmatch('[0-9a-f]{40}',v): raise Stop('GIT_BINDING')
    if not 0 < (stamp(expires)-stamp(issued)).total_seconds() <= 86400: raise Stop('EXPIRY_INTERVAL')
    version=selected_version(successor,version)
    value=manifest(version=version)
    return dict(version=value['version'], release_id=release_id, revision=revision, tree=tree,
        manifest=json.loads(canonical(value)), manifest_sha256=sha(canonical(value)),
        dependencies=dependencies(version=version), packages=packages(version), evidence_head=evidence_head,
        directory='docs/design/ingestion-operational-execution-'+release_id,
        issued_at=issued, expires_at=expires, released=released,
        stop_treatment=PERMITS[version] if released else 'INACTIVE', preserved_stops=PRESERVED,
        stop_evidence=dict(path='specifications/032-stage4-stable-credential-pipeline.md',
            baseline='608aa07d496ff00ccd405dc77de31eb6bbfc6edd', sha256=sha((ROOT/'specifications/032-stage4-stable-credential-pipeline.md').read_bytes()), database_synchronised=False))


def control(registration, *, enabled=False):
    return dict(version=registration['version'], release_id=registration['release_id'],
        revision=registration['revision'], manifest_sha256=registration['manifest_sha256'],
        expires_at=registration['expires_at'], preserved_stops=PRESERVED,
        stop_evidence=registration['stop_evidence'],
        registration_binding_sha256=sha(canonical({k:v for k,v in registration.items() if k!='evidence_head'})),
        stop_treatment=PERMITS[registration['version']] if enabled else 'INACTIVE', cancelled=False)


def validate(r, *, clock=now, checkout=True):
    required={'version','release_id','revision','tree','manifest','manifest_sha256',
        'dependencies','packages','evidence_head','directory','issued_at','expires_at',
        'released','stop_treatment','preserved_stops','stop_evidence'}
    if set(r)!=required: raise Stop('REGISTRATION_SCHEMA')
    if r['version'] not in VERSION_LIMITS:raise Stop('REGISTRATION_VERSION')
    expected=render(r['release_id'],r['revision'],r['tree'],r['evidence_head'],r['issued_at'],r['expires_at'],released=r['released'],version=r['version'])
    if r != expected or r['released'] is not True: raise Stop('REGISTRATION_INACTIVE_OR_CHANGED')
    if not stamp(r['issued_at'])<=clock()<stamp(r['expires_at']): raise Stop('REGISTRATION_EXPIRED_OR_FUTURE')
    if checkout and (git('rev-parse','HEAD')!=r['revision'] or git('rev-parse','HEAD^{tree}')!=r['tree'] or git('status','--porcelain')):
        raise Stop('CHECKOUT_BINDING')
    return r


def write_new(path, raw):
    with Path(path).open('xb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    if Path(path).read_bytes()!=raw: raise Stop('LOCAL_EVIDENCE_READBACK')


def sockets():
    return {os.readlink(p) for p in Path('/proc/self/fd').iterdir()
            if p.exists() and os.readlink(p).startswith('socket:')}


class Journal:
    def __init__(self,path):
        self.path=path; self.head='0'*64; self.count=0
        self.handle=path.open('xb')
    def emit(self,event,payload):
        entry=dict(sequence=self.count,event=event,payload=payload,previous_sha256=self.head)
        entry['sha256']=sha(canonical(entry));raw=canonical(entry)+b'\n'
        if self.handle.tell()+len(raw)>192*1024: raise Stop('JOURNAL_BOUND')
        self.handle.write(raw);self.handle.flush();os.fsync(self.handle.fileno())
        self.head=entry['sha256'];self.count+=1
    def close(self): self.handle.close()


def verify_chain(raw):
    if len(raw)>192*1024:raise Stop('JOURNAL_BOUND')
    previous='0'*64
    for number,line in enumerate(raw.splitlines()):
        value=json.loads(line);digest=value.pop('sha256')
        if value['sequence']!=number or value['previous_sha256']!=previous or sha(canonical(value))!=digest:raise Stop('JOURNAL_CHAIN')
        previous=digest
    return previous


class Source:
    """Whole-source-cgroup cancellation; nested readers may start new sessions."""
    def __init__(self,memory,registration,root,*,clock=time.monotonic,sleep=time.sleep):
        self.memory=memory;self.r=registration;self.root=root;self.clock=clock;self.sleep=sleep
    def command(self,index,out):
        budget=VERSION_LIMITS[self.r['version']].get('execution_budget')
        return [sys.executable,'-m','verification.discovery.four_council_release','worker',str(index),str(out),str(self.memory.source)]+(['--three-council-successor'] if self.r['version'] in SUCCESSORS else [])+(['--execution-budget',budget] if budget else [])
    def run(self,index,check):
        out=self.root/f'source-{index}.json';started=self.clock();poll_at=started
        outer=budget_of(self.r['version'])['source_outer_seconds']
        child=None;primary=None;stage='SOURCE_CONTAINMENT_CHECK';pipe=BoundedPipe()
        closure=dict(source_group_closed=False,child_reaped=False,failures=[])
        try:
            if getattr(self.memory,'finalisation_only',False):raise Stop('FINALISATION_ONLY')
            if not (self.memory.source/'cgroup.kill').is_file():raise Stop('SOURCE_KILL_UNAVAILABLE')
            def attach_before_exec():
                fd=os.open(self.memory.source/'cgroup.procs',os.O_WRONLY)
                try:os.write(fd,str(os.getpid()).encode())
                finally:os.close(fd)
            stage='SOURCE_PROCESS_START'
            child=subprocess.Popen(self.command(index,out),cwd=ROOT,preexec_fn=attach_before_exec,
                env=dict(PATH='/usr/bin:/bin',HOME=str(self.root),TMPDIR=str(self.root),PYTHONDONTWRITEBYTECODE='1',
                    PLAYWRIGHT_BROWSERS_PATH=str(Path.home()/'.cache/ms-playwright')),
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            pipe.attach(child)
            while child.poll() is None:
                pipe.drain()
                stage='SOURCE_MEMORY_CHECK';self.memory.snapshot()
                if self.clock()-started>=outer:raise Stop('SOURCE_OUTER_DEADLINE')
                if self.clock()>=poll_at:
                    stage='SOURCE_CONTROL_CHECK';check();poll_at=self.clock()+LIMITS['control_interval_seconds']
                stage='SOURCE_OUTPUT_BOUND'
                if out.exists() and out.stat().st_size>512000:raise Stop('SOURCE_OUTPUT_BOUND')
                self.sleep(.05)
            stage='SOURCE_PROCESS_EXIT';pipe.drain()
            if child.returncode:
                closure['worker_exit']=worker_exit_evidence(child.returncode,pipe.data,pipe.discarded)
                raise Stop('SOURCE_CHILD_FAILURE')
        except BaseException as error:primary=failure_detail(error,stage)
        finally:
          try:
            # Always attempt owned termination/readback; never replace the first
            # source failure with an exception raised by cleanup.
            try:
                stage='SOURCE_GROUP_TERMINATION'
                self.memory.source.joinpath('cgroup.kill').write_text('1')
                deadline=self.clock()+LIMITS['source_close_seconds']
                stage='SOURCE_GROUP_READBACK'
                while 'populated 1' in self.memory.source.joinpath('cgroup.events').read_text() and self.clock()<deadline:self.sleep(.05)
                closure['source_group_closed']='populated 1' not in self.memory.source.joinpath('cgroup.events').read_text()
            except BaseException as error:closure['failures'].append(failure_detail(error,stage))
            try:
                if child is not None:child.wait(timeout=1)
                closure['child_reaped']=True
            except BaseException as error:closure['failures'].append(failure_detail(error,'SOURCE_CHILD_REAP'))
          finally:pipe.close()
        if not closure['source_group_closed'] or not closure['child_reaped'] or closure['failures']:
            if primary is None:primary=failure_detail(Stop('SOURCE_CLEANUP_UNCERTAIN'),'SOURCE_CLOSURE')
        if primary is not None:raise SourceFailure(primary,closure)
        try:
            stage='SOURCE_OUTPUT_READ';bound=65535 if index==1 else 512000
            if not out.is_file() or out.is_symlink() or out.stat().st_size>bound:raise Stop('SOURCE_OUTPUT_BOUND')
            raw=out.read_bytes();stage='SOURCE_OUTPUT_DECODE';audit=json.loads(raw)
        except BaseException as error:raise SourceFailure(failure_detail(error,stage),closure) from None
        return audit,dict(closure,supervised_seconds=self.clock()-started)


class Launcher:
    def __init__(self,r,root,*,github,memory,source,clock=time.monotonic,wall=now,emit=None):
        self.r=r;self.root=Path(root);self.github=github;self.memory=memory;self.source=source
        self.successor=r['version'] in SUCCESSORS
        self.rows=ROWS[1:] if self.successor else ROWS
        self.indices=(1,2,3) if self.successor else (0,1,2,3)
        self.limits=VERSION_LIMITS[r['version']];self.budget=budget_of(r['version'])
        self.clock=clock;self.wall=wall;self.emit=emit or (lambda *_:None)
        self.start=clock();self.expected=r['evidence_head'];self.next_control=0
        self.publication_calls=0;self.exported=0;self.requests=0;self.source_bytes=0
        self.source_seconds=0;self.active_seconds=0;self.results=[];self.reserved=[];self.returned_evidence=[];self.source_cleanup_uncertain=False
        self.consumed=False;self.cancelled=False;self.accounting_complete=True
        self.failure=None;self.reporting_failures=[];self.containment_uncertain=False;self.reporting_cleanup_uncertain=False
        self.source_closure=None;self.stage='INITIAL_CONTROL'
        self.continued=[]
        self.baseline=sockets();self.control_checks=0;self.memory_closed=False;self.slot_deadline=None
        # Set only after a memory failure is latched (source group empty); never re-enables execution.
        self.memory_latch=None;self.finalising=False
    def deadline(self):
        if self.clock()-self.start>=self.limits['package_seconds']-10:raise Stop('PACKAGE_DEADLINE')
        if not stamp(self.r['issued_at'])<=self.wall()<stamp(self.r['expires_at']):raise Stop('REGISTRATION_EXPIRED_OR_FUTURE')
        # Finalisation may only publish/close; execution paths keep snapshot(), which refuses once latched.
        if self.finalising:self.memory.finalisation_check()
        else:self.memory.snapshot()
        if self.slot_deadline is not None and self.clock()>=self.slot_deadline:raise Stop('SLOT_JOB_DEADLINE')
    def poll(self,*,active=False):
        self.deadline()
        if self.cancelled:raise Stop('OPERATOR_CANCELLED')
        ref=self.github.call('GET',REPO+'/git/ref/heads/'+BRANCH)
        if ref['object']['sha']!=self.expected:raise Stop('CONTROL_OR_EVIDENCE_HEAD_MOVED')
        if active:
            self.control_checks+=1
            self.emit('control_verified',dict(head=self.expected,ordinal=self.control_checks,immutable_permit=True))
            return
        path=self.r['directory']+'/control.json'
        blob=self.github.call('GET',REPO+'/contents/'+path+'?ref='+self.expected)
        value=json.loads(blob_bytes(blob));self.control_checks+=1
        if value != control(self.r,enabled=True):raise Stop('CONTROL_CANCELLED_OR_UNAVAILABLE')
        self.emit('control_verified',dict(head=self.expected,ordinal=self.control_checks))
    def publish(self,files,part):
        raw_bytes=sum(map(len,files.values()))
        anticipated=6+2*len(files)
        if (self.publication_calls+anticipated>self.limits['publication_requests'] or
            self.exported+raw_bytes>self.limits['exported_bytes']):raise Stop('PUBLICATION_OR_EXPORT_BOUND')
        before=self.github.requests
        try:
            self.expected=self.github.publish(files,directory=self.r['directory']+'/'+part,expected_head=self.expected)
        finally:
            self.publication_calls+=self.github.requests-before
            # All attempted exported payloads count, even lost acknowledgements.
            self.exported+=raw_bytes
    def accept(self,index,a):
        row=ROWS[index];proof.validate_audit(a,tuple(row[k] for k in ('council','semantics','start','end')))
        if (a.get('requested_interval')!=[row['start'],row['end']] or a.get('date_semantics')!=row['semantics'] or
            a.get('persistence') is not False or not identities(row,a)):raise Stop('SOURCE_IDENTITY_OR_EFFECT')
        source_rows=a.get('listing_records' if index==1 else 'records',[])
        source_pages=a.get('listing_segments' if index==1 else 'pages',[])
        if len(source_rows)>60 or len(source_pages)>6:raise Stop('SOURCE_ROW_OR_PAGE_BOUND')
        if a.get('safety_failure') or a.get('safety_events'):raise Stop('SOURCE_SECURITY')
        if self.successor:
            if a.get('applied_interval') not in (None,[row['start'],row['end']]):raise Stop('SOURCE_CRITERIA')
            if a.get('proof_retention_failure'):raise Stop('SOURCE_PROOF_FAILURE')
            if index==1 and a.get('supervisor_limit_hit') is not False:raise Stop('SOURCE_ACCOUNTING')
            if index!=1 and a.get('resource',{}).get('budget_exhaustion') is not False:
                raise Stop('SOURCE_ACCOUNTING')
        if index==1:
            expected=finite.dated_config(finite.UI_CASES['discovery_rochdale_ui_window'],row['start'],row['end']).destination
            if a.get('destination')!=expected or a.get('case')!='discovery_rochdale_ui_window':raise Stop('SOURCE_DESTINATION')
            closed=a.get('cleanup')=='CONTEXT_BROWSER_CLOSED' and a.get('process_cleanup')=='CLOSED' and a.get('live_owned_survivors')==0
            worker=a.get('supervisor_seconds')
        else:
            if a.get('council')!=row['council']:raise Stop('SOURCE_COUNCIL')
            closed=a.get('cleanup')=='SESSION_BOUNDARY_CLOSED'
            worker=a.get('resource',{}).get('elapsed_seconds')
        cost=resources(row,a)
        if cost is None or a.get('accounting_complete') is False:raise Stop('SOURCE_ACCOUNTING')
        # Browser (Rochdale) worker bound follows the selected budget; Idox readers keep 45s.
        bound=self.budget['worker_seconds'] if index==1 else 45
        if type(worker) not in (int,float) or not math.isfinite(worker) or not 0<=worker<=bound:raise Stop('SOURCE_TIME_ACCOUNTING')
        self.requests+=cost[0];self.source_bytes+=cost[1];self.source_seconds+=worker
        if self.requests>self.limits['requests'] or self.source_bytes>self.limits['mixed_source_bytes'] or self.source_seconds>self.limits['worker_seconds']:raise Stop('CUMULATIVE_SOURCE_BOUND')
        if not closed:raise Stop('SOURCE_CLEANUP_UNCERTAIN')
        state=finite.classify(row,a,**({'execution_budget':self.budget['name']} if index==1 and self.budget['name'] else {}))
        if self.successor and state=='COMPLETE' and a.get('completeness')=='FAILED':
            raise Stop('SOURCE_OUTCOME_CONFLICT')
        return state

    def local_outcome(self,index,a,state):
        """Fixed successor-only allowlist; labels or arbitrary exceptions grant nothing.

        Called only after the existing proof/identity/accounting/cleanup gates.
        Missing applied evidence may remain unknown; contradictory evidence stops.
        No parser, timeout, source qualification or result is changed here.
        """
        if not self.successor or state not in {'FAILED','UNKNOWN'}:return None
        if a.get('completeness')!='FAILED' or a.get('proof_retention_failure') or a.get('capped'):
            return None
        if a.get('applied_interval') is not None:return None
        p=a['retained_proof']['events']
        if index==1:
            from .criteria_containment import eligible
            if (not eligible(ROWS[index],a,**({'execution_budget':self.budget['name']} if self.budget['name'] else {})) or a.get('listing_failure')!='TimeoutError'
                or a.get('criteria_control_timeout',{}).get('operation')!='RESULT_MARKER_VISIBLE'
                or a.get('listing_records')!=[] or a.get('listing_segments')!=[]
                or a.get('enumeration_evidence') is not None):return None
            if len(p)!=1 or p[0]['operation']!='CRITERIA':return None
            evidence=p[0]['sanitised_evidence']
            if (evidence.get('view')!='PLAYWRIGHT_RENDERED_LOCATORS' or evidence.get('availability')!='PRESENT'
                or any(v in {'MISMATCH','AMBIGUOUS'} for v in evidence['criteria'].values())):return None
            return LOCAL_OUTCOMES[0]
        if state!='FAILED':return None
        resource=a.get('resource',{})
        row=ROWS[index]
        if (resource.get('council')!=row['council'] or resource.get('adapter')!='idox'
            or resource.get('reference')!=row['semantics']+':'+row['start']+':'+row['end']
            or resource.get('outcome')!='FAILED' or type(resource.get('redirects')) is not int or resource['redirects']!=0
            or resource.get('budget_exhaustion') is not False or type(resource.get('retries')) is not int or resource['retries']!=0
            or resource.get('retry_policy')!='NO_INTERNAL_RETRY'
            or a.get('records')!=[] or a.get('pages')!=[]):return None
        for event in p:
            if event['operation']=='SEARCH':
                criteria=event['sanitised_evidence'].get('criteria',{})
                if any(v['controls']>1 or (v['controls']==1 and v['matches_requested'] is False)
                       for v in criteria.values()):return None
        operation=a.get('proof_failure_operation');diagnostic=a.get('failure_diagnostic',{})
        from .source_diagnostics import validate as validate_diagnostic
        try:validate_diagnostic(diagnostic)
        except ValueError:return None
        if (a.get('failure')=='BoundaryFailure:SOURCE_CONTRACT_REJECTED'
            and resource.get('requests_attempted')==len(p)
            and operation in {'SEARCH_REQUEST','SORT_REQUEST'} and diagnostic.get('stage')==operation
            and diagnostic.get('code')=='SOURCE_CONTRACT_REJECTED'
            and diagnostic['shape_available'] is False and diagnostic['body_bytes']==0
            and diagnostic['body_sha256']==sha(b'')
            and p[-1]['operation']==operation and p[-1]['original_response_availability']=='UNAVAILABLE'
            and p[-1]['original_response_sha256'] is None and p[-1]['body_bytes'] is None
            and p[-1]['sanitised_evidence']=={'availability':'UNAVAILABLE'}
            and p[-1]['transport']==diagnostic.get('transport')
            and diagnostic.get('transport')=={'http_status':None,'media_type':None,'redirect':None,
                'rejection_outcome':'TIMEOUT','rejection_reason':'transport failed'}):
            if [e['operation'] for e in p] == (['FORM','SEARCH_REQUEST'] if operation=='SEARCH_REQUEST' else ['FORM','SEARCH','SORT_REQUEST']):
                return LOCAL_OUTCOMES[1]
        if (index==3 and a.get('failure')=='ListingError:sort selector' and operation=='SORT_FORM_PARSE'
            and resource.get('requests_attempted')==2
            and diagnostic.get('stage')=='SORT_FORM_PARSE' and diagnostic.get('code')=='SORT_SELECTOR_COUNT'
            and diagnostic.get('shape_available') is True
            and len(p)==3 and [e['operation'] for e in p]==['FORM','SEARCH','SORT_FORM_PARSE']
            and p[1]['original_response_availability']=='PRESENT'
            and p[1]['original_response_sha256']==diagnostic.get('body_sha256')
            and p[1]['body_bytes']==diagnostic.get('body_bytes')
            and p[1]['transport']==diagnostic.get('transport')
            and p[1]['transport']=={'http_status':200,'media_type':'text/html','redirect':'NONE',
                'rejection_outcome':None,'rejection_reason':None}):
            evidence=p[1]['sanitised_evidence']
            if (evidence.get('availability')=='PRESENT' and evidence.get('document_closed') is True
                and evidence.get('order_by_selects')==0 and evidence.get('zero_literal_matches')==0
                and diagnostic['counts']['order_by_selects']==evidence['order_by_selects']
                and diagnostic['counts']['forms']==evidence['forms']
                and len(a.get('response_provenance',[]))==2
                and a['response_provenance'][-1].get('body_sha256')==p[1]['original_response_sha256']):
                return LOCAL_OUTCOMES[2]
        return None

    def slot_closure(self,owned):
        import psutil
        if owned.get('source_group_closed') is not True:
            self.source_cleanup_uncertain=True
            raise Stop('SOURCE_CLEANUP_UNCERTAIN')
        if psutil.Process().children(recursive=True) or sockets()-self.baseline:
            raise Stop('PROCESS_OR_SOCKET_CLOSURE')
        self.memory.snapshot()

    def next_budget(self,next_index):
        """Reserve the next fixed slot; never borrow another slot's allowance."""
        if (stamp(self.r['expires_at'])-self.wall()).total_seconds()<480:
            raise Stop('NEXT_AUTHORITY_ALLOCATION')
        if self.active_seconds+self.limits['slot_active_seconds']>self.limits['active_seconds']:
            raise Stop('NEXT_ACTIVE_ALLOCATION')
        if (sum(x['requests'] for x in self.reserved)+(80 if next_index==1 else 10)>self.limits['requests']
            or sum(x['bytes'] for x in self.reserved)+(20*1024**2 if next_index==1 else 3_000_000)>self.limits['mixed_source_bytes']):
            raise Stop('NEXT_SOURCE_RESERVATION')
        if self.clock()-self.start+480>self.limits['package_seconds']-10:
            raise Stop('NEXT_JOB_ALLOCATION')
        if (self.exported+self.limits['per_slot_export_bytes']>self.limits['exported_bytes']
            or self.publication_calls+24>self.limits['publication_requests']
            or self.github.requests+26>self.limits['github_requests']):raise Stop('NEXT_PUBLICATION_ALLOCATION')
    def execute(self):
        reason=None;process='UNCERTAIN';closure={};publication='NOT_ATTEMPTED';active_slot=None;active_started=None
        try:
            self.slot_deadline=self.start+self.limits['per_job_seconds']-10
            self.stage='INITIAL_CONTROL';self.poll()
            self.stage='CONSUMED_HISTORY'
            history=self.github.probe(REPO+'/contents/'+self.r['directory']+'/claim/consumed.json?ref='+self.expected)
            if history is not None:raise Stop('REGISTRATION_ALREADY_CONSUMED')
            # First durable CAS wins. Existing directory/old head cannot be replayed.
            self.stage='CLAIM_PUBLICATION'
            self.publish({'consumed.json':canonical(dict(registration_sha256=sha(canonical(self.r)),release_id=self.r['release_id'])),
                          'manifest.json':canonical(self.r['manifest'])},'claim')
            self.consumed=True
            for i,row in enumerate(self.rows):
                reader_index=self.indices[i]
                slot_started=self.start if i==0 else self.clock()
                self.slot_deadline=slot_started+self.limits['per_job_seconds']-10
                self.poll();active_slot=i
                if self.clock()-slot_started>self.limits['setup_seconds']:raise Stop('SETUP_DEADLINE')
                self.reserved.append(dict(index=i,requests=80 if reader_index==1 else 10,bytes=20*1024**2 if reader_index==1 else 3_000_000))
                self.emit('source_intent',dict(index=i,scope=row,reserved=self.reserved[-1]))
                print(f'[{i+1}/{len(self.rows)}] {row["council"].upper()}: one observation; '+('exact isolation policy applies.' if self.successor else 'stop-all applies.'),flush=True)
                active_started=self.clock()
                self.stage='SOURCE_RUN'
                a,owned=self.source.run(reader_index,lambda:self.poll(active=True))
                self.source_closure=owned
                used=self.clock()-active_started;self.active_seconds+=used;active_started=None
                if used>self.budget['slot_active_seconds'] or self.active_seconds>self.limits['active_seconds']:raise Stop('ACTIVE_ALLOCATION')
                raw=canonical(a)
                if len(raw)>(65535 if reader_index==1 else 512000):raise Stop('RETURNED_AUDIT_BOUND')
                local=self.root/f'returned-{i}.json';write_new(local,raw)
                retained=dict(index=i,sha256=sha(raw),bytes=len(raw),local_file=local.name,export='HELD_UNVALIDATED')
                self.returned_evidence.append(retained)
                # Reuse #180's scope/hash/projection gate; malformed or transplanted
                # proof stays local with its hash. Never export an unvalidated body.
                self.stage='SOURCE_PROOF_VALIDATION'
                proof.validate_audit(a,tuple(row[k] for k in ('council','semantics','start','end')))
                rejection=None
                self.stage='SOURCE_ACCEPTANCE'
                try:state=self.accept(reader_index,a)
                except Stop as exc:
                    state='FAILED';rejection=fixed_reason(exc)
                    if 'ACCOUNTING' in rejection or 'BOUND' in rejection:self.accounting_complete=False
                    if rejection=='SOURCE_CLEANUP_UNCERTAIN':self.source_cleanup_uncertain=True
                if self.successor:self.slot_closure(owned)
                local_code=self.local_outcome(reader_index,a,state) if rejection is None else None
                receipt=dict(index=i,scope=row,outcome=state,rejection=rejection,source_sha256=sha(raw),owned_cleanup=owned)
                self.results.append(receipt)
                if self.successor:
                    receipt.update(source_outcome=a.get('completeness'),continuation_code=local_code,
                        continuation_eligible=local_code is not None)
                receipt_raw=canonical(receipt)
                if len(raw)+len(receipt_raw)+8192>self.limits['per_slot_export_bytes']:raise Stop('SLOT_EXPORT_BOUND')
                self.stage='SLOT_PUBLICATION'
                self.publish({'source.json':raw,'receipt.json':receipt_raw,
                    'HASHES.json':canonical({'source.json':sha(raw),'receipt.json':sha(receipt_raw)})},f'slot-{i}')
                retained['export']='COMMITTED_READBACK_VERIFIED'
                if rejection:raise Stop(rejection)
                if self.clock()-slot_started>480:raise Stop('SLOT_JOB_DEADLINE')
                publication='VERIFIED';self.slot_deadline=None
                print(f'[{i+1}/{len(self.rows)}] {state}; evidence read back.',flush=True)
                if state!='COMPLETE' and not local_code:
                    reason='STOP_ALL_NON_COMPLETE';break
                if self.successor and i+1<len(self.rows):
                    self.poll();self.slot_closure(owned);self.next_budget(self.indices[i+1])
                    if local_code:
                        self.continued.append(dict(index=i,code=local_code))
                        self.emit('source_local_continuation',dict(index=i,code=local_code,
                            original_outcome=state,publication_head=self.expected))
                        print('Source result remains unresolved; exact reviewed continuation admitted.',flush=True)
                active_slot=None
        except BaseException as e:
            self.failure=failure_detail(e,self.stage);reason=self.failure['code']
            if isinstance(e,SourceFailure):
                self.source_closure=e.closure
                if not e.closure['source_group_closed'] or not e.closure['child_reaped'] or e.closure['failures']:self.source_cleanup_uncertain=True
            if self.failure['kind']=='MEMORY' or self.failure['stage'] in {'SOURCE_MEMORY_CHECK','SOURCE_CONTAINMENT_CHECK'}:self.containment_uncertain=True
            # Only while the failing slot's outcome is still UNVERIFIED: a slot whose receipt
            # was already accepted is never exported under finalisation (stays held).
            # Only a recorded limit event; lost enforcement or unclassified memory failures stay held.
            if (self.failure['code']=='MEMORY_LIMIT_HIT' and not self.source_cleanup_uncertain and hasattr(self.memory,'latch')
                and active_slot is not None and len(self.results)<=active_slot):
                # Latch after source closure: remaining slots stay stopped; only bounded
                # finalisation (publication/removal) may follow, under finalisation_check.
                try:self.memory_latch=self.memory.latch()
                except BaseException as error:self.reporting_failures.append(failure_detail(error,'MEMORY_FAILURE_LATCH'))
            if active_slot is not None and len(self.results)<=active_slot:
                self.accounting_complete=False
                if active_started is not None:self.active_seconds+=max(0,self.clock()-active_started)
            if getattr(self.github,'mutation_uncertain',False):publication='UNCERTAIN'
        finally:
            process='UNCERTAIN';children_known=False;memory_known=False
            try:
                import psutil
                children=psutil.Process().children(recursive=True)
                new=sockets()-self.baseline
                closure.update(live_child_count=len(children),new_socket_count=len(new),owned_groups_removed=False,**descendant_identity(children,self.memory))
                children_known=not children and not new
                if not children_known:raise Stop('PROCESS_OR_SOCKET_CLOSURE')
            except BaseException as error:self.reporting_failures.append(failure_detail(error,'FINAL_CHILD_SOCKET_READBACK'))
            try:
                closure['memory']=self.memory.finalisation_check() if self.memory_latch is not None else self.memory.snapshot();memory_known=True
            except BaseException as error:
                self.containment_uncertain=True
                self.reporting_failures.append(failure_detail(error,'FINAL_CONTAINMENT_CHECK'))
                closure['observation']=memory_observation(self.memory)
            # A latched failure never reports pending/clean cleanup in the exported packet.
            if children_known and memory_known and self.memory_latch is None:process='PENDING_MEMORY_SCOPE_CLOSURE'
        all_complete=reason is None and len(self.results)==len(self.rows) and all(x['outcome']=='COMPLETE' for x in self.results)
        result=dict(version=self.r['version'],release_id=self.r['release_id'],
            status=('THREE_COMPLETE' if self.successor else 'FOUR_COMPLETE') if all_complete else
                ('OBSERVATIONS_FINISHED_WITH_GAPS' if self.successor and reason is None and len(self.results)==3 else 'STOP_RECONCILE_NO_RETRY'),
            reason=reason,results=self.results,returned_evidence=self.returned_evidence,not_attempted=self.rows[len(self.reserved):],
            consumed=self.consumed,accounting_complete=self.accounting_complete,
            failure=self.failure,reporting_failures=list(self.reporting_failures),
            source_closure=self.source_closure,
            source_outcome='UNVERIFIED' if active_slot is not None and len(self.results)<=active_slot else 'SEE_SLOT_RECEIPTS' if self.results else 'NOT_STARTED',
            accounting_status='VERIFIED' if self.accounting_complete else 'PARTIAL_SOURCE_USAGE_UNKNOWN',
            source_usage=dict(requests=self.requests if self.accounting_complete else None,
                mixed_bytes=self.source_bytes if self.accounting_complete else None,
                worker_seconds=self.source_seconds if self.accounting_complete else None),
            containment_observation=memory_observation(self.memory),
            containment_status='UNCERTAIN' if self.containment_uncertain else 'CHECKS_PASSED',
            owned_group_closure='NOT_VERIFIED',outer_scope_observation='NOT_OBSERVED_FROM_INSIDE_SCOPE',
            finalisation=dict(state='FINALISATION_ONLY',latched_failure=self.failure,latched_counters=self.memory_latch['events'])
                if self.memory_latch is not None else dict(state='NOT_LATCHED'),
            accounting=dict(observed_requests=self.requests,observed_mixed_source_bytes=self.source_bytes,
                observed_worker_seconds=self.source_seconds,active_seconds=self.active_seconds,
                reservations=self.reserved,github_requests=self.github.requests,publication_requests=self.publication_calls,
                attempted_exported_bytes=self.exported,supervised_seconds=self.clock()-self.start),
            process_cleanup=process,owned_cleanup=closure,publication=publication,
            source_contract_cleanup='UNVERIFIED' if not self.accounting_complete else 'UNCERTAIN' if self.source_cleanup_uncertain else 'NO_UNRESOLVED_CLOSURE',
            cleanup='PENDING_MEMORY_SCOPE_CLOSURE' if process=='PENDING_MEMORY_SCOPE_CLOSURE' and publication!='UNCERTAIN' and not self.source_cleanup_uncertain else 'UNCERTAIN',
            database_connections=0,application_writes=0,coverage_advance=False,preserved_stops=PRESERVED)
        if process!='PENDING_MEMORY_SCOPE_CLOSURE':result['status']='STOP_RECONCILE_NO_RETRY'
        if self.successor:result['continued_after_source_local']=self.continued
        return result


def owner_source_context(execution_budget=None):
    """Exact memory-contained proof context; no hosted-environment impersonation.

    The source/aggregate limits must equal the selected budget exactly (historical: 1GiB/1.5GiB)."""
    try:budget=select_budget(execution_budget)
    except ValueError:raise Stop('SOURCE_MEMORY_ENFORCEMENT') from None
    lines=Path('/proc/self/cgroup').read_text().splitlines()
    if len(lines)!=1 or not lines[0].startswith('0::/'):raise Stop('SOURCE_CGROUP_V2')
    relative=Path(lines[0][3:])
    if relative.name!='source' or relative.parent.name!='propertyaigent-operational-once.scope':raise Stop('SOURCE_CGROUP_IDENTITY')
    group=Path('/sys/fs/cgroup')/str(relative).lstrip('/')
    for path,limit in ((group,budget['source_memory_bytes']),(group.parent,budget['aggregate_memory_bytes'])):
        if path.joinpath('memory.max').read_text().strip()!=str(limit) or path.joinpath('memory.swap.max').read_text().strip()!='0' or path.joinpath('memory.oom.group').read_text().strip()!='1':raise Stop('SOURCE_MEMORY_ENFORCEMENT')
    allowed={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE','LC_CTYPE','PLAYWRIGHT_BROWSERS_PATH'}
    if set(os.environ)-allowed:raise Stop('SOURCE_OWNER_ENVIRONMENT')
    return True


def worker(index,out,group,*,successor=False,execution_budget=None):
    # Private child, deliberately no owner credentials/control API capability.
    if not (1<=index<4 if successor else 0<=index<4) or any(k not in {'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE','LC_CTYPE','PLAYWRIGHT_BROWSERS_PATH'} for k in os.environ):raise Stop('CHILD_ENVIRONMENT')
    if execution_budget is not None and (not successor or execution_budget!=SUCCESSOR_V2_LIMITS['execution_budget']):raise Stop('CHILD_EXECUTION_BUDGET')
    group=Path(group)
    if group.name!='source' or not group.is_dir():raise Stop('CHILD_GROUP')
    group.joinpath('cgroup.procs').write_text(str(os.getpid()))
    value=finite.read(ROWS[index],retain_proof=True,no_transport_retry=True,fixed_four_rows=True,
        execution_mode='four-council-owner-local' if index==1 else None,
        **({'execution_budget':execution_budget} if execution_budget is not None and index==1 else {}))
    raw=canonical(value)
    if len(raw)>(65535 if index==1 else 512000):raise Stop('WORKER_EXPORT_BOUND')
    write_new(out,raw)


def main():
    entry_started=time.monotonic()
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='mode',required=True)
    w=sub.add_parser('worker');w.add_argument('index',type=int);w.add_argument('out',type=Path);w.add_argument('group',type=Path);w.add_argument('--three-council-successor',action='store_true');w.add_argument('--execution-budget')
    r=sub.add_parser('render');r.add_argument('--release-id',required=True);r.add_argument('--revision',required=True);r.add_argument('--tree',required=True);r.add_argument('--evidence-head',required=True);r.add_argument('--issued-at',required=True);r.add_argument('--expires-at',required=True);r.add_argument('--output',required=True,type=Path);r.add_argument('--propose-reviewed-stop-treatment',action='store_true');r.add_argument('--three-council-successor',action='store_true');r.add_argument('--version',choices=tuple(VERSION_LIMITS))
    # Rendering creates local proposals only, never authority or a remote control.
    c=sub.add_parser('runtime-check');c.add_argument('--version',required=True,choices=tuple(VERSION_LIMITS))
    a=sub.add_parser('run');a.add_argument('--registration',required=True,type=Path);a.add_argument('--registration-sha256',required=True);a.add_argument('--enable-reviewed-source-only-stop-treatment',action='store_true')
    args=p.parse_args()
    if args.mode=='runtime-check':
        report=runtime_check(args.version);print(json.dumps(report,sort_keys=True),flush=True);return 0 if report['ok'] else 1
    if args.mode=='worker':return worker(args.index,args.out,args.group,successor=args.three_council_successor,execution_budget=args.execution_budget)
    if args.mode=='render':
        value=render(args.release_id,args.revision,args.tree,args.evidence_head,args.issued_at,args.expires_at,released=args.propose_reviewed_stop_treatment,successor=args.three_council_successor,version=args.version)
        write_new(args.output,canonical(value))
        write_new(args.output.with_suffix('.control.json'),canonical(control(value,enabled=args.propose_reviewed_stop_treatment)))
        print('PROPOSED_FILES_ONLY_NO_AUTHORITY' if args.propose_reviewed_stop_treatment else 'INACTIVE_REGISTRATION_RENDERED');return
    raw=args.registration.read_bytes()
    if len(raw)>65536 or sha(raw)!=args.registration_sha256:raise Stop('REGISTRATION_HASH')
    r=json.loads(raw);validate(r)
    if os.environ.get('GH_HOST','github.com')!='github.com':raise Stop('GITHUB_DESTINATION')
    if not args.enable_reviewed_source_only_stop_treatment:raise Stop('STOP_TREATMENT_NOT_ENABLED')
    if any(any(s in k.upper() for s in ('DATABASE','SUPABASE','OPENAI','ANTHROPIC')) for k in os.environ):raise Stop('OWNER_CREDENTIAL_CONTEXT')
    if r['version']==SUCCESSOR_V2_VERSION:
        # Before any claim, in the interpreter that will run the worker: names and exception classes only are reported.
        report=runtime_check(r['version'])
        if not report['ok']:
            print(json.dumps(dict(status='STOP_RECONCILE_NO_RETRY',reason='RUNTIME_DEPENDENCY_CHECK',cleanup='NOT_STARTED',report=report),sort_keys=True),flush=True)
            raise Stop('RUNTIME_DEPENDENCY_CHECK')
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():raise Stop('PROCESS_NAMESPACE_MISMATCH')
    root=Path.home()/'.local/state/propertyaigent'/r['release_id'];root.mkdir(parents=True,exist_ok=False)
    journal=Journal(root/'events.jsonl')
    try:memory=OperationalMemory(**memory_limits(r['version']))
    except BaseException:
        early=dict(status='STOP_RECONCILE_NO_RETRY',reason='MEMORY_ENFORCEMENT_UNAVAILABLE',cleanup='UNCERTAIN',database_connections=0,source_slots_started=0)
        journal.emit('initialisation_failed',early);journal.close()
        write_new(root/'final-result.json',canonical(early));print(json.dumps(early),flush=True);return 1
    holder={} 
    github=GitHub(journal.emit,lambda:holder['launcher'].deadline(),bound=LIMITS['github_requests'])
    source=Source(memory,r,root)
    launch=Launcher(r,root,github=github,memory=memory,source=source,emit=journal.emit);holder['launcher']=launch
    launch.start=entry_started
    if time.monotonic()-entry_started>LIMITS['setup_seconds']:raise Stop('SETUP_DEADLINE')
    def cancelled(*_):launch.cancelled=True;raise Stop('OPERATOR_CANCELLED')
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    result=launch.execute()
    return finish(launch,journal,result,root)


def finish(launch,journal,result,root):
    """Preserve controller evidence first; all publication gates stay enforced."""
    github=launch.github;publication_journal=None;audit_raw=b'';files=None
    errors=result.setdefault('reporting_failures',[])
    def failed(error,stage):
        detail=failure_detail(error,stage);errors.append(detail)
        if detail['kind']=='MEMORY':launch.containment_uncertain=True
        result['status']='STOP_RECONCILE_NO_RETRY'
        if result.get('reason') is None:result['reason']=detail['code']
    result['controller_audit_status']='VERIFIED'
    try:journal.emit('result_before_final_publication',result)
    except BaseException as error:
        result['controller_audit_status']='PARTIAL';failed(error,'FINAL_AUDIT_EVENT')
    try:journal.close()
    except BaseException as error:
        launch.reporting_cleanup_uncertain=True
        result['controller_audit_status']='PARTIAL';failed(error,'FINAL_AUDIT_CLOSE')
    try:
        if journal.path.stat().st_size>launch.limits['exported_bytes']:raise Stop('FINAL_ENVELOPE_BOUND')
        audit_raw=journal.path.read_bytes()
        if not audit_raw:raise Stop('EMPTY_AUDIT_PREFIX')
        verify_chain(audit_raw);result['audit_chain_validated']=True
        result['evidence_scope']='CONTROLLER_PARTIAL_SOURCE_UNVERIFIED' if not result['accounting_complete'] else 'CONTROLLER_PARTIAL_VALIDATED_SLOT_RECEIPTS' if result['controller_audit_status']=='PARTIAL' else 'CONTROLLER_AND_VALIDATED_SLOT_RECEIPTS'
        result['containment_observation']=memory_observation(launch.memory)
        if result['containment_observation']['status'] in {'UNAVAILABLE','PARTIAL'}:
            launch.containment_uncertain=True
            failed(Stop('CONTAINMENT_OBSERVATION_UNAVAILABLE'),'CONTAINMENT_OBSERVATION')
        files={'events.jsonl':audit_raw,'result-before-publication.json':canonical(result)}
        files['HASHES.json']=canonical({k:sha(v) for k,v in files.items()})
        if sum(map(len,files.values()))+launch.exported>launch.limits['exported_bytes']:raise Stop('FINAL_ENVELOPE_BOUND')
        # The full original audit is already on disk. Save the exact bounded
        # packet/readback hashes locally even when the publication gate refuses.
        for name in ('result-before-publication.json','HASHES.json'):write_new(root/name,files[name])
        result['local_evidence_packet']=dict(status='PRESERVED',files={k:dict(bytes=len(v),sha256=sha(v)) for k,v in files.items()})
    except BaseException as error:
        files=None;failed(error,'LOCAL_EVIDENCE_PACKET')
        result['controller_audit_status']='UNVERIFIED' if not result.get('audit_chain_validated') else result['controller_audit_status']
        result['local_evidence_packet']=dict(status='UNVERIFIED_OR_UNWRITABLE_OR_OVER_BOUND')
    try:
        publication_journal=Journal(root/'publication-events.jsonl');github.emit=publication_journal.emit
        if files is None or not launch.consumed or github.mutation_uncertain:raise Stop('FINAL_PUBLICATION_HELD')
        if launch.memory_latch is not None:
            # Finalisation-only export: required child/socket closure first, then the
            # finalisation gate (exact limits, identity, unchanged counters) on every call.
            if __import__('psutil').Process().children(recursive=True) or sockets()-launch.baseline:raise Stop('PROCESS_OR_SOCKET_CLOSURE')
            launch.finalising=True
        # No fallback check: the original expiry, deadline and memory.snapshot
        # guard is used for every API call, including after a containment error.
        # Persistent enforcement failure therefore keeps the packet local.
        launch.deadline()
        remaining=min(launch.limits['publication_requests']-launch.publication_calls,launch.limits['github_requests']-github.requests)
        seconds=min(launch.limits['closure_publication_seconds'],launch.limits['package_seconds']-10-(launch.clock()-launch.start))
        with github.reserve_scope(remaining,seconds):launch.publish(files,'completed')
        result.update(final_publication='VERIFIED',evidence_commit=launch.expected)
    except BaseException as error:
        failed(error,'FINAL_PUBLICATION');result['final_publication']='UNCERTAIN_OR_HELD'
    finally:
        if publication_journal is not None:
            try:publication_journal.close()
            except BaseException as error:
                launch.reporting_cleanup_uncertain=True;failed(error,'FINAL_PUBLICATION_JOURNAL_CLOSE')
        final_clean=False
        try:
            children=__import__('psutil').Process().children(recursive=True)
            new=sockets()-launch.baseline
            result['final_process_readback']=dict(live_child_count=len(children),new_socket_count=len(new),**descendant_identity(children,launch.memory))
            final_clean=not children and not new
            result['child_socket_closure']='CLOSED' if final_clean else 'UNCERTAIN'
        except BaseException as error:
            result['child_socket_closure']='UNCERTAIN';failed(error,'FINAL_CHILD_SOCKET_READBACK')
        result['containment_observation']=memory_observation(launch.memory)
        if result['containment_observation']['status'] in {'UNAVAILABLE','PARTIAL'}:launch.containment_uncertain=True
        try:
            result['owned_cleanup']=launch.memory.close();launch.memory_closed=True
            result['owned_group_closure']='CLOSED'
            if not final_clean:raise Stop('FINAL_PROCESS_CLOSURE')
            result.update(final_process_cleanup='CLOSED',process_cleanup='CLOSED',
                cleanup='UNCERTAIN' if launch.source_cleanup_uncertain or launch.containment_uncertain or launch.reporting_cleanup_uncertain else 'CLOSED')
        except BaseException as error:
            failed(error,'OWNED_GROUP_CLOSURE')
            result.update(process_cleanup='UNCERTAIN',final_process_cleanup='UNCERTAIN',cleanup='UNCERTAIN')
        result['reporting_resource_closure']='UNCERTAIN' if launch.reporting_cleanup_uncertain else 'CLOSED'
        result['containment_status']='UNCERTAIN' if launch.containment_uncertain else 'CHECKS_PASSED'
        result['outer_scope_observation']='NOT_OBSERVED_FROM_INSIDE_SCOPE'
        if github.mutation_uncertain:result['cleanup']='UNCERTAIN'
    result['accounting'].update(github_requests=github.requests,publication_requests=launch.publication_calls,
        attempted_exported_bytes=launch.exported,supervised_seconds=launch.clock()-launch.start)
    final_raw=canonical(result)
    receipt_bytes=publication_journal.path.stat().st_size if publication_journal is not None else 0
    if len(final_raw)+launch.exported+receipt_bytes>launch.limits['exported_bytes']:
        result.update(status='STOP_RECONCILE_NO_RETRY',reason='FINAL_ENVELOPE_BOUND',cleanup='UNCERTAIN')
        final_raw=canonical(result)
    try:write_new(root/'final-result.json',final_raw)
    except BaseException:result.update(status='STOP_RECONCILE_NO_RETRY',reason='FINAL_RESULT_UNWRITABLE')
    summary=dict(status=result['status'],reason=result['reason'],cleanup=result['cleanup'],
        failure=result.get('failure'),reporting_failures=result.get('reporting_failures',[]),
        child_socket_closure=result.get('child_socket_closure'),owned_group_closure=result.get('owned_group_closure'),
        accounting_status=result['accounting_status'],local_evidence_packet=result.get('local_evidence_packet'),
        audit=str(journal.path),audit_sha256=sha(audit_raw) if audit_raw else None,
        final_result=str(root/'final-result.json'),evidence_commit=result.get('evidence_commit'),
        accounting=result['accounting'],outcomes=[dict(council=x['scope']['council'],outcome=x['outcome']) for x in result['results']])
    try:print(json.dumps(summary,sort_keys=True),flush=True)
    except BaseException:return 1
    return 0 if result['status'] in {'FOUR_COMPLETE','THREE_COMPLETE'} and result['cleanup']=='CLOSED' else 1

if __name__=='__main__':
    try:sys.exit(main())
    except BaseException as e:
        if isinstance(e,SystemExit):raise
        print(json.dumps(dict(status='STOP_RECONCILE_NO_RETRY',reason=fixed_reason(e) if isinstance(e,Stop) else 'DEPENDENCY_UNAVAILABLE' if isinstance(e,ImportError) else 'PREPARATION_FAILURE',cleanup='UNCERTAIN')),flush=True)
        sys.exit(1)
