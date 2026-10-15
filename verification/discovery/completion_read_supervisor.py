"""Fixed read-only owned-tree supervisor; no source/admission imports."""
import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
LIMITS=dict(seconds=60,rss_bytes=1610612736,output_bytes=2000000)
COHORT_SHA='34d6fe5ee4941b258afe88c2c6ffa196fb3d0bc052b73cb0667bb4e49acb8d5d'
PRIMARY_SHA=None


def files(root):
    values=list(Path(root).rglob('*'))
    if len(values)>650 or any(p.is_symlink() for p in values):raise ValueError('AUDIT_PATH_BOUND')
    return sum(p.stat().st_size for p in values if p.is_file())


def phase_bound(root,now):return None


def supervise(root,*,credential,runner=subprocess.Popen,deadline=None,execution=None):
    """Enforce elapsed, RSS, output, phase deadlines; kill/reap owned tree.

    Any interruption in a writing child is uncertain. Never infer rollback from
    kill/exit status, and never launch another child or resume this cohort.
    """
    import psutil,tempfile
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():raise ValueError('PROCESS_NAMESPACE_MISMATCH')
    root=Path(root);root.mkdir(exist_ok=False)
    if execution is not None:
        with (root/'execution.json').open('xb') as f:f.write(json.dumps(execution,sort_keys=True).encode());f.flush();os.fsync(f.fileno())
    started=time.monotonic();seen={};peak=0;reason=None;certain=True;child=None
    with tempfile.TemporaryDirectory(prefix='selective5-admission-home-') as home:
        env=dict(PATH='/usr/bin:/bin',HOME=home,TMPDIR=home,LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',
            PYTHONNOUSERSITE='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',COMPARISON_PRIVATE_CHILD='1',COMPARISON_DATABASE_URL=credential)
        command=[sys.executable,'-m','verification.discovery.completion_read_supervisor','--worker',str(root)]
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
        transaction='READ_ONLY_STATE_UNCONFIRMED_NO_RETRY',retry=False,cohort_sha256=COHORT_SHA,primary_sha256=PRIMARY_SHA)
    path=root/'worker-result.json'
    if child is not None and child.returncode==0 and not reason and certain and not survivors and path.is_file() and path.stat().st_size<4_000_000:
        out['result']=json.loads(path.read_bytes());out['transaction']='READ_ONLY_RESULT_RECONCILED'
    if 'result' not in out:out['stop_reason']=out['stop_reason'] or 'WORKER_OR_RESULT_UNCERTAIN_NO_RETRY'
    raw=json.dumps(out,sort_keys=True).encode()
    if files(root)+len(raw)>LIMITS['output_bytes']:raise ValueError('FINAL_AUDIT_BOUND')
    (root/'supervisor.json').write_bytes(raw)
    return out


def worker(root):
    if os.environ.get('COMPARISON_PRIVATE_CHILD')!='1':raise ValueError('PRIVATE_CHILD_ONLY')
    import resource
    from .completion_comparison import run
    resource.setrlimit(resource.RLIMIT_FSIZE,(LIMITS['output_bytes'],LIMITS['output_bytes']))
    result=run(os.environ.pop('COMPARISON_DATABASE_URL',''))
    raw=json.dumps(result,sort_keys=True).encode()
    if len(raw)>1000000:raise ValueError('READ_AUDIT_BOUND')
    p=Path(root)/'worker-result.json'
    with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path,required=True);a=p.parse_args();worker(a.worker)
