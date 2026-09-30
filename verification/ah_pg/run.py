"""Fail-closed WSL runner. Only fresh, namespace-isolated PostgreSQL is allowed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import traceback

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--candidate',required=True); p.add_argument('--output-parent',type=Path,required=True)
p.add_argument('--pg-bin',type=Path,default=Path('/usr/lib/postgresql/16/bin'))
a=p.parse_args(); repo=Path(__file__).resolve().parents[2]
a.output_parent.mkdir(parents=True,exist_ok=True)
out=Path(tempfile.mkdtemp(prefix='ah-pg-run-',dir=a.output_parent.resolve())); os.chmod(out,0o700)
root=out/'disposable'; root.mkdir(mode=0o700); home=out/'empty-home'; home.mkdir(mode=0o700)
archive=out/'ah-postgres-results.tar.gz'
env={'PATH':str(Path(sys.executable).parent)+':/usr/sbin:/usr/bin:/sbin:/bin','HOME':str(home),'LC_ALL':'C','DATABASE_URL':'sqlite:///:memory:','PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
def git(*args): return subprocess.check_output(['git',*args],cwd=repo,env={**env,'GIT_CONFIG_NOSYSTEM':'1'})
def logcall(args,name,timeout=1200):
    with (out/name).open('w') as f:
        return subprocess.run(list(map(str,args)),cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout).returncode
status={'state':'BLOCKED','candidate':a.candidate,'ordinary_postgres':'disabled','archive_inspection_required':True}
try:
    if os.getuid()==0: raise ValueError('Run as an ordinary WSL user, not root')
    # Reject rather than silently reuse potentially live inputs. Never print their values.
    denied=[k for k in os.environ if re.match(r'^(PG|DATABASE|DB_|SUPABASE|OPENAI|ANTHROPIC|AZURE|AWS_|GOOGLE_APPLICATION_CREDENTIALS|MODEL|LLM|PROPERTYAIGENT|AH_)',k)]
    if denied: raise ValueError('Inherited database/model inputs rejected (names only): '+','.join(sorted(denied)))
    if not re.fullmatch('[0-9a-f]{40}',a.candidate) or git('rev-parse','HEAD').decode().strip()!=a.candidate: raise ValueError('Exact candidate mismatch')
    before=git('status','--porcelain','--untracked-files=all'); (out/'working-tree-before.txt').write_bytes(before)
    if before: raise ValueError('Candidate tree is not clean')
    forbidden=[x for x in repo.rglob('*') if x.is_file() and (x.name=='.env' or (x.name.startswith('.env.') and x.name not in ('.env.example','.env.template')) or x.name=='secrets.toml')]
    for parent in repo.parents:
        forbidden += [x for x in parent.glob('.env*') if x.name not in ('.env.example','.env.template')]
    if forbidden: raise ValueError('Repository/ancestor environment files rejected: '+','.join(map(str,forbidden)))
    (out/'candidate.txt').write_text(a.candidate+'\n')
    (out/'runner.sha256').write_text(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()+'  verification/ah_pg/run.py\n')
    if logcall([sys.executable,'verification/ah_pg/preflight.py',out/'dependencies.json'],'preflight-before-namespace.log'): raise ValueError('Dependency preflight failed; cluster not created')
    for binary in ('postgres','initdb','pg_ctl','pg_controldata'):
        if not (a.pg_bin/binary).is_file(): raise ValueError('Missing existing PostgreSQL binary: '+str(a.pg_bin/binary))
        if logcall([a.pg_bin/binary,'--version'],binary+'-version.txt'): raise ValueError('PostgreSQL binary preflight failed')
    for binary in ('sudo','unshare','runuser','mount','ip','timeout'):
        if not shutil.which(binary,path=env['PATH']): raise ValueError('Missing OS prerequisite: '+binary)
    for binary in ('unshare','git'):
        logcall([binary,'--version'],binary+'-version.txt')
    host_ns=os.readlink('/proc/self/ns/net')
    # sudo only creates OS isolation. PostgreSQL and application tests remain unprivileged.
    subprocess.run(['sudo','-v'],check=True,env={'PATH':env['PATH'],'TERM':os.environ.get('TERM','dumb')})
    shell='set -eu; mount --make-rprivate /; mount -t sysfs sysfs /sys; ip link set lo up; exec runuser -u "$1" -- env -i PATH="$2" HOME="$3" LC_ALL=C DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$4" "$5" "$6" "$7" "$8" "$9"'
    rc=logcall(['sudo','-n','env','-i','PATH=/usr/sbin:/usr/bin:/sbin:/bin','unshare','--net','--pid','--fork','--mount','--mount-proc','--kill-child=SIGKILL','timeout','--signal=TERM','--kill-after=10s','1200s','/bin/bash','-c',shell,'ah-isolated',pwd.getpwuid(os.getuid()).pw_name,env['PATH'],home,sys.executable,repo/'verification/ah_pg/inside.py',root,host_ns,a.pg_bin.resolve(),out],'namespace.log',timeout=1500)
    status.update(state='EXECUTED_AWAITING_INSPECTION' if rc==0 else 'FAILED_OR_BLOCKED',runner_exit=rc)
    after=git('status','--porcelain','--untracked-files=all'); (out/'working-tree-after.txt').write_bytes(after)
    if after: raise ValueError('Candidate tree changed')
except BaseException as e:
    status['error']=str(e); (out/'exception.txt').write_text(traceback.format_exc())
finally:
    (out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    # Database files and environment values are not exported. Keep test proofs/logs.
    files=sorted(x for x in out.iterdir() if x.is_file() and x!=archive)
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.name+'\n' for x in files))
    with tarfile.open(archive,'w:gz') as tar:
        for x in [*files,out/'SHA256SUMS']: tar.add(x,arcname='ah-postgres-results/'+x.name)
    print('Return this single archive: '+str(archive),flush=True)
    print('SHA256: '+hashlib.sha256(archive.read_bytes()).hexdigest(),flush=True)
    print('PostgreSQL acceptance requires archive inspection. State: '+status['state'],flush=True)
raise SystemExit(0 if status['state']=='EXECUTED_AWAITING_INSPECTION' else 1)
