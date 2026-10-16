"""Owned-process envelope for the manual ingestion controller/source workers.

Reuses existing Linux process identity/group signalling helpers. No scheduling,
secret discovery, workflow dispatch, source adapter or credential provisioning.
"""
import json,os,signal,subprocess,time
from pathlib import Path
import psutil
from app.security.document_process import proc_info,signal_owned_group


def supervise(command,*,environment,root,seconds=165,stop_file=None,source=False):
 if not 0<seconds<=(45 if source else 165):raise ValueError('FIXED_DEADLINE')
 root=Path(root);root.mkdir(exist_ok=False)
 if any(k in environment for k in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','GITHUB_TOKEN')):raise ValueError('UNNEEDED_CREDENTIAL')
 if source and any('DATABASE' in k or 'PASSWORD' in k or 'TOKEN' in k or 'SECRET' in k for k in environment):raise ValueError('SOURCE_CREDENTIAL_FREE')
 env=dict(PATH='/usr/bin:/bin',HOME=str(root),TMPDIR=str(root),LANG='C.UTF-8',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1')
 env.update(environment);started=time.monotonic();seen={};peak=0;reason=None;certain=True;survivors=[];child=None;identity=None
 maximum=512*1024 if source else 2*1024**2
 def size():
  paths=list(root.rglob('*'))
  if len(paths)>128 or any(p.is_symlink() for p in paths):raise ValueError('OUTPUT_PATH_BOUND')
  return sum(p.stat().st_size for p in paths if p.is_file())
 try:
  child=subprocess.Popen(command,env=env,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  identity=proc_info(child.pid);identity.update(group_host=child.pid,group_start=identity['start']);
  if identity['ppid']!=os.getpid():raise ValueError('PROCESS_NAMESPACE_MISMATCH')
  parent=psutil.Process(child.pid);seen[child.pid]=parent.create_time()
  while child.poll() is None:
   try:
    owned=[parent]+parent.children(recursive=True);rss=0
    for p in owned:
     try:
      seen[p.pid]=p.create_time();n=p.memory_info().rss;rss+=n
      if n>1024**3:reason='PROCESS_RSS'
     except psutil.NoSuchProcess:pass
    peak=max(peak,rss)
    if rss>1536*1024**2:reason='AGGREGATE_RSS'
    elif time.monotonic()-started>=seconds:reason='DEADLINE'
    elif stop_file and Path(stop_file).exists():reason='OWNER_STOP'
    elif size()>maximum-16384:reason='OUTPUT_BOUND'
   except Exception:certain=False;reason='ACCOUNTING_UNCERTAIN'
   if reason:break
   time.sleep(.025)
 except Exception:certain=False;reason='LAUNCH_OR_ACCOUNTING_UNCERTAIN'
 finally:
  if child is not None:
   # Scan/signal the verified group even if the leader has exited: an
   # unsampled ordinary orphan must not survive a successful root exit.
   try:
    if identity is not None:signal_owned_group(identity)
    elif child.poll() is None:child.kill()
   except Exception:certain=False
   killed=[]
   for pid,born in seen.items():
    if pid==child.pid:continue
    try:
     p=psutil.Process(pid)
     if p.create_time()==born and p.status()!=psutil.STATUS_ZOMBIE:p.kill();killed.append(p)
    except psutil.NoSuchProcess:pass
    except Exception:certain=False
   try:
    _,alive=psutil.wait_procs(killed,timeout=3)
    if alive:certain=False
    child.wait(timeout=5)
   except Exception:certain=False
   for pid,born in seen.items():
    if pid==child.pid and child.returncode is not None:continue
    try:
     p=psutil.Process(pid)
     if p.create_time()==born and p.status()!=psutil.STATUS_ZOMBIE:survivors.append(pid)
    except psutil.NoSuchProcess:pass
    except Exception:certain=False
 if child is not None and identity is not None:
  try:
   until=time.monotonic()+3
   while True:
    remaining=[]
    for entry in Path('/proc').iterdir():
     if not entry.name.isdecimal():continue
     try:info=proc_info(int(entry.name))
     except (FileNotFoundError,ProcessLookupError):continue
     if info['group']==identity['group_host'] and info['state']!='Z':remaining.append(info['host_pid'])
    if not remaining:break
    if time.monotonic()>=until:survivors.extend(remaining);break
    time.sleep(.025)
  except Exception:certain=False
 elapsed=time.monotonic()-started
 if elapsed>seconds+10:reason=reason or 'CLEANUP_DEADLINE';certain=False
 result=dict(exit_code=child.returncode if child else None,expired=reason=='DEADLINE',limit_hit=reason,
  live_owned_survivors=len(survivors),peak_owned_rss=peak,elapsed_seconds=elapsed,accounting_complete=certain,
  cleanup='CLOSED' if certain and not survivors else 'UNCERTAIN',processes_seen=len(seen),retry=False,
  persistence='RECONCILE_IF_EFFECT_INTENT' if reason or child is None or child.returncode!=0 else 'READBACK_REQUIRED')
 try:
  if size()>maximum-16384:result['limit_hit']='OUTPUT_BOUND'
 except Exception:result.update(cleanup='UNCERTAIN',accounting_complete=False,limit_hit='OUTPUT_ACCOUNTING')
 (root/'supervisor.json').write_text(json.dumps(result,sort_keys=True))
 return result
