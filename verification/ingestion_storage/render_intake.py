"""Explicit Render intake profile, read-only memory observation, owned orphan cleanup.

No settings mutation, cgroup creation, credentials, or production permission.
RSS samples are NOT aggregate kernel accounting or guaranteed peak observations.
"""
import ctypes
import hashlib
import os
import time
from pathlib import Path

import psutil
from app.ingestion.ledger import Denied

MODE='render-intake-v1'
SERVICE='crn-d9sv93vavr4c73f98rb0'
MiB=1024**2
SOURCE_ENV={'PATH','HOME','TMPDIR','LANG','LC_CTYPE','PYTHONNOUSERSITE',
            'PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS','INGESTION_SOURCE_PRIVATE',
            'PLAYWRIGHT_BROWSERS_PATH','INGESTION_RENDER_PROFILE'}


def memory_group():
    lines=Path('/proc/self/cgroup').read_text().splitlines()
    if len(lines)!=1 or not lines[0].startswith('0::/'):raise Denied('RENDER_CGROUP_V2_REQUIRED')
    relative=lines[0][3:]
    if '..' in Path(relative).parts:raise Denied('RENDER_CGROUP_PATH')
    mounted=Path('/sys/fs/cgroup')
    candidate=mounted/relative.lstrip('/')
    if not (candidate/'memory.max').is_file():candidate=mounted
    # Read only the process's namespace-visible hierarchy, never guess plan bytes.
    paths=[candidate]
    while paths[-1]!=mounted and mounted in paths[-1].parents:paths.append(paths[-1].parent)
    limits=[]
    for p in paths:
        value=(p/'memory.max').read_text().strip()
        if value!='max':limits.append((int(value),p))
    if not limits:raise Denied('RENDER_FINITE_AGGREGATE_REQUIRED')
    return min(limits,key=lambda x:x[0])[1]


def memory_sample(group):
    group=Path(group)
    result={}
    for field in ('memory.max','memory.current','memory.swap.max','memory.peak'):
        try:
            raw=(group/field).read_text().strip()
            result[field]=raw if raw=='max' else int(raw)
        except (OSError,ValueError):result[field]=None
    try:result['memory.events']={k:int(v) for k,v in (line.split() for line in (group/'memory.events').read_text().splitlines())}
    except (OSError,ValueError):result['memory.events']=None
    return result


def validate_profile(profile,*,revision=None,environ=None):
    env=os.environ if environ is None else environ
    required={'mode','service_id','revision','browser_path','browser_sha256','aggregate_bytes','source_rss_bytes','controller_rss_bytes','reserve_bytes','source_seconds'}
    if not isinstance(profile,dict) or set(profile)!=required:raise Denied('RENDER_PROFILE_FIELDS')
    if profile['mode']!=MODE or profile['service_id']!=SERVICE or revision and profile['revision']!=revision:
        raise Denied('RENDER_PROFILE_IDENTITY')
    import re
    if not re.fullmatch('[a-f0-9]{40}',profile['revision']) or not re.fullmatch('[a-f0-9]{64}',profile['browser_sha256']):raise Denied('RENDER_PROFILE_HASH')
    if any(type(profile[k]) is not int for k in ('aggregate_bytes','source_rss_bytes','controller_rss_bytes','reserve_bytes','source_seconds')):raise Denied('RENDER_PROFILE_LIMITS')
    if not (0<profile['aggregate_bytes']<=2048*MiB and 0<profile['source_rss_bytes']<=1536*MiB
            and 0<profile['controller_rss_bytes']<=256*MiB and profile['reserve_bytes']>=256*MiB
            and profile['source_rss_bytes']+profile['controller_rss_bytes']+profile['reserve_bytes']<=profile['aggregate_bytes']
            and 0<profile['source_seconds']<=75):raise Denied('RENDER_PROFILE_LIMITS')
    path=Path(profile['browser_path'])
    if not path.is_absolute() or '..' in path.parts or not path.is_dir():raise Denied('RENDER_BROWSER_PATH')
    from verification.direct_reference.prepared_font_cache import headless_shell_executable
    executable=Path(headless_shell_executable(str(path)))
    with executable.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=profile['browser_sha256']:raise Denied('RENDER_BROWSER_HASH')
    return profile


def source_context(profile):
    validate_profile(profile)
    if set(os.environ)-SOURCE_ENV or os.environ.get('INGESTION_SOURCE_PRIVATE')!='ONCE' or os.environ.get('PLAYWRIGHT_BROWSERS_PATH')!=profile['browser_path']:
        raise Denied('RENDER_SOURCE_ENVIRONMENT')
    sample=memory_sample(memory_group())
    if sample['memory.max']!=profile['aggregate_bytes']:raise Denied('RENDER_AGGREGATE_MISMATCH')
    return True


class MemoryMonitor:
    def __init__(self,profile):
        self.profile=profile;self.group=memory_group();self.initial=memory_sample(self.group)
        self.sampled_aggregate_peak=0;self.sampled_controller_peak=0;self.last=None
        self.check()

    def check(self):
        s=memory_sample(self.group);self.last=s
        if s['memory.max']!=self.profile['aggregate_bytes'] or type(s['memory.current']) is not int or s['memory.events'] is None:
            raise Denied('RENDER_MEMORY_ACCOUNTING_UNAVAILABLE')
        if s['memory.swap.max']!=self.initial['memory.swap.max']:raise Denied('RENDER_SWAP_POLICY_CHANGED')
        controller=psutil.Process().memory_info().rss
        self.sampled_controller_peak=max(self.sampled_controller_peak,controller)
        self.sampled_aggregate_peak=max(self.sampled_aggregate_peak,s['memory.current'])
        events=s['memory.events'];initial=self.initial['memory.events'] or {}
        if any(events.get(k,0)>initial.get(k,0) for k in ('max','oom','oom_kill','oom_group_kill')):raise Denied('RENDER_MEMORY_EVENT')
        if controller>self.profile['controller_rss_bytes'] or s['memory.current']>self.profile['aggregate_bytes']-self.profile['reserve_bytes']:
            raise Denied('RENDER_MEMORY_HEADROOM')

    def evidence(self):
        return dict(initial=self.initial,last=self.last,sampled_aggregate_peak=self.sampled_aggregate_peak,
                    sampled_controller_peak=self.sampled_controller_peak,guaranteed_peak=False)


class OwnedSubreaper:
    """Only for a sole-source supervisor with no pre-existing child processes.

    Kernel reparenting retains session-changing orphans, including those never
    sampled before their parent exits. No protection is claimed if this controller
    itself is killed; that requires whole-job teardown and durable reconciliation.
    """
    def __init__(self):
        self.parent=psutil.Process();self.libc=ctypes.CDLL(None,use_errno=True)
        if self.parent.children(recursive=True):raise Denied('SOURCE_EXCLUSIVE_CHILD_SCOPE_REQUIRED')
        value=ctypes.c_int()
        if self.libc.prctl(37,ctypes.byref(value),0,0,0)!=0:raise Denied('SOURCE_SUBREAPER_UNAVAILABLE')
        self.previous=value.value
        if self.libc.prctl(36,1,0,0,0)!=0:raise Denied('SOURCE_SUBREAPER_UNAVAILABLE')

    def close(self):
        deadline=time.monotonic()+3
        while True:
            # Repeated enumeration is safe here because living descendants cannot
            # escape kernel adoption by changing session or exiting their parent.
            children=self.parent.children(recursive=True)
            for child in children:
                try:
                    born=child.create_time()
                    if psutil.Process(child.pid).create_time()==born and child.status()!=psutil.STATUS_ZOMBIE:child.kill()
                except psutil.NoSuchProcess:pass
            # Reap adopted children only after the Popen leader has been waited.
            while True:
                try:
                    if os.waitpid(-1,os.WNOHANG)[0]==0:break
                except ChildProcessError:break
            if not self.parent.children(recursive=True):
                if self.libc.prctl(36,self.previous,0,0,0)!=0:raise Denied('SOURCE_SUBREAPER_RESTORE')
                return
            if time.monotonic()>=deadline:raise Denied('SOURCE_ADOPTED_SURVIVORS')
            time.sleep(.025)
