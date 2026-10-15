"""Unregistered bounded admission supervisor. No dispatch API or retry path."""
import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
from .bolton53_admission import LIMITS,PHASES,COHORT_SHA,PRIMARY_SHA


def files(root):
    values=list(Path(root).rglob('*'))
    if len(values)>650 or any(p.is_symlink() for p in values):raise ValueError('AUDIT_PATH_BOUND')
    return sum(p.stat().st_size for p in values if p.is_file())


class Journal:
    def __init__(self,root):self.root=Path(root);self.ordinal=0
    def __call__(self,index,phase):
        if type(index)is not int or not 0<=index<53 or phase not in PHASES:raise ValueError('PHASE_REJECTED')
        raw=json.dumps(dict(index=index,phase=phase,monotonic=time.monotonic()),sort_keys=True).encode()
        p=self.root/f'phase-{self.ordinal:03}.json'
        if files(self.root)+len(raw)+65536>LIMITS['output_bytes']:raise ValueError('AUDIT_BOUND')
        with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        fd=os.open(self.root,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        if p.read_bytes()!=raw:raise ValueError('JOURNAL_HASH')
        self.ordinal+=1


def phase_bound(root,now):
    paths=sorted(Path(root).glob('phase-*.json'))
    if not paths:return None
    phases=[json.loads(p.read_bytes()) for p in paths]
    for p in phases:
        if p['phase'] not in PHASES or type(p['index'])is not int or not 0<=p['index']<53 or not 0<=now-p['monotonic']<=LIMITS['seconds']:
            return 'PHASE_ACCOUNTING'
    last=phases[-1];starts=[p for p in phases if p['index']==last['index'] and p['phase']=='RECORD_STARTED']
    if len(starts)!=1:return 'PHASE_ACCOUNTING'
    if now-starts[0]['monotonic']>180:return 'RECORD_DEADLINE'
    budget={'IDENTITY_TRANSACTION_STARTED':50,'SOURCE_STARTED':55,'B2_TRANSACTION_STARTED':60}.get(last['phase'],15)
    return 'PHASE_DEADLINE' if now-last['monotonic']>budget else None


def supervise(root,*,credential,runner=subprocess.Popen,deadline=None):
    """Enforce elapsed, RSS, output, phase deadlines; kill/reap owned tree.

    Any interruption in a writing child is uncertain. Never infer rollback from
    kill/exit status, and never launch another child or resume this cohort.
    """
    import psutil,tempfile
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():raise ValueError('PROCESS_NAMESPACE_MISMATCH')
    root=Path(root);root.mkdir(exist_ok=False)
    started=time.monotonic();seen={};peak=0;reason=None;certain=True;child=None
    with tempfile.TemporaryDirectory(prefix='bolton53-admission-home-') as home:
        env=dict(PATH='/usr/bin:/bin',HOME=home,TMPDIR=home,LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',
            PYTHONNOUSERSITE='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',BOLTON_ADMISSION_PRIVATE_CHILD='1',BOLTON_ADMISSION_DATABASE_URL=credential)
        command=[sys.executable,'-m','verification.discovery.bolton53_admission_supervisor','--worker',str(root)]
        try:
            child=runner(command,env=env,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            parent=psutil.Process(child.pid)
            while child.poll() is None:
                try:
                    owned=[parent]+parent.children(recursive=True);rss=0
                    for p in owned:
                        try:seen[p.pid]=p.create_time();rss+=p.memory_info().rss
                        except psutil.NoSuchProcess:pass
                    peak=max(peak,rss);now=time.monotonic()
                    if now-started>min(LIMITS['seconds'],deadline or LIMITS['seconds']):reason='AGGREGATE_DEADLINE'
                    elif rss>LIMITS['rss_bytes']:reason='RSS_BOUND'
                    elif files(root)>LIMITS['output_bytes']-65536:reason='OUTPUT_BOUND'
                    else:reason=phase_bound(root,now)
                except Exception:certain=False;reason='ACCOUNTING_UNCERTAIN'
                if reason:break
                time.sleep(.05)
        except Exception:certain=False;reason='LAUNCH_OR_ACCOUNTING_UNCERTAIN'
        finally:
            if child is not None:
                if child.poll() is None:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    except Exception:certain=False
            killed=[]
            for pid,born in seen.items():
                if child is not None and pid==child.pid:continue
                try:
                    p=psutil.Process(pid)
                    if p.create_time()==born and p.status()!=psutil.STATUS_ZOMBIE:p.kill();killed.append(p)
                except psutil.NoSuchProcess:pass
                except Exception:certain=False
            try:psutil.wait_procs(killed,timeout=3)
            except Exception:certain=False
            if child is not None:
                try:child.wait(timeout=5)
                except Exception:certain=False
            survivors=[]
            for pid,born in seen.items():
                if child is not None and pid==child.pid:continue
                try:
                    p=psutil.Process(pid)
                    if p.create_time()==born and p.status()!=psutil.STATUS_ZOMBIE:survivors.append(pid)
                except psutil.NoSuchProcess:pass
                except Exception:certain=False
    if time.monotonic()-started>min(LIMITS['seconds'],deadline or LIMITS['seconds']):reason=reason or 'AGGREGATE_DEADLINE'
    try:
        reason=reason or phase_bound(root,time.monotonic())
        if files(root)>LIMITS['output_bytes']-65536:reason=reason or 'OUTPUT_BOUND'
    except Exception:certain=False;reason=reason or 'FINAL_ACCOUNTING_UNCERTAIN'
    out=dict(stop_reason=reason,accounting_complete=certain,cleanup='CLOSED' if certain and not survivors else 'UNKNOWN',
        live_owned_survivors=len(survivors),peak_owned_rss=peak,elapsed_seconds=time.monotonic()-started,
        transaction='UNKNOWN_COMMIT_OR_READBACK_NO_RETRY',retry=False,cohort_sha256=COHORT_SHA,primary_sha256=PRIMARY_SHA)
    path=root/'worker-result.json'
    if child is not None and child.returncode==0 and not reason and certain and not survivors and path.is_file() and path.stat().st_size<4_000_000:
        out['result']=json.loads(path.read_bytes());out['transaction']='PER_RECORD_DISPOSITIONS'
    if 'result' not in out:out['stop_reason']=out['stop_reason'] or 'WORKER_OR_RESULT_UNCERTAIN_NO_RETRY'
    raw=json.dumps(out,sort_keys=True).encode()
    if files(root)+len(raw)>LIMITS['output_bytes']:raise ValueError('FINAL_AUDIT_BOUND')
    (root/'supervisor.json').write_bytes(raw)
    return out


def worker(root):
    from .bolton53_admission import run
    from .committee_exact import checked_engine
    from .r0_registered_scopes import AuditStore
    if os.environ.get('BOLTON_ADMISSION_PRIVATE_CHILD')!='1':raise ValueError('PRIVATE_CHILD_ONLY')
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE,(LIMITS['output_bytes'],LIMITS['output_bytes']))
    journal=Journal(root);store=AuditStore(root,LIMITS)
    # Only this database child receives the protected value. Existing source
    # supervisor builds an explicit credential-free environment for its worker.
    result=run(engine_factory=lambda:checked_engine(os.environ['BOLTON_ADMISSION_DATABASE_URL']),checkpoint=store.record,journal=journal)
    result.update(checkpoint_sha256=store.hashes,checkpoint_bytes=store.bytes)
    raw=json.dumps(result,sort_keys=True).encode()
    if files(root)+len(raw)+65536>LIMITS['output_bytes']:raise ValueError('FINAL_BOUND')
    with (Path(root)/'worker-result.json').open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path,required=True);a=p.parse_args();worker(a.worker)
