"""Transfer wrapper: verify, prepare fresh local dependencies, execute guarded runner."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import traceback
pkg=Path(__file__).resolve().parent
for line in (pkg/'SHA256SUMS').read_text().splitlines():
    digest,name=line.split('  ',1); path=pkg/name
    if path.resolve().parent!=pkg or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise SystemExit('Handoff checksum mismatch: '+name)
print('All handoff checksums verified.',flush=True)
parent=Path.home()/'p0a-work';parent.mkdir(exist_ok=True)
work=Path(tempfile.mkdtemp(prefix='mixed-guarded-',dir=parent));os.chmod(work,0o700)
out=work/'evidence';out.mkdir(); home=work/'empty-home';home.mkdir(mode=0o700)
repo=work/'candidate';venv=work/'venv';sha=(pkg/'CANDIDATE').read_text().strip()
env={'HOME':str(home),'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','GIT_CONFIG_NOSYSTEM':'1','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}
state={'state':'BLOCKED','candidate':sha,'archive_inspection_required':True}
def logged(args,name,cwd=None):
    with (out/name).open('w') as f:
        subprocess.run(list(map(str,args)),cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
try:
    if os.getuid()==0: raise ValueError('Use ordinary WSL user, not root')
    denied=[k for k in os.environ if re.match(r'^(PG|DATABASE|DB_|SUPABASE|OPENAI|ANTHROPIC|AZURE|AWS_|GOOGLE_APPLICATION_CREDENTIALS|MODEL|LLM|PROPERTYAIGENT|AH_)',k)]
    if denied: raise ValueError('Inherited inputs rejected (names only): '+','.join(sorted(denied)))
    for ancestor in work.parents:
        if any(x.name not in ('.env.example','.env.template') for x in ancestor.glob('.env*')):
            raise ValueError('Ancestor environment file rejected: '+str(ancestor))
    logged(['git','-c','core.hooksPath=/dev/null','clone','--no-checkout',pkg/'candidate.bundle',repo],'clone.log')
    logged(['git','bundle','verify',pkg/'candidate.bundle'],'bundle-verify.log',repo)
    logged(['git','-c','core.hooksPath=/dev/null','checkout','--detach',sha],'checkout.log',repo)
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,env=env).decode().strip()
    clean=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=repo,env=env)
    if actual!=sha or clean: raise ValueError('Exact candidate/clean tree check failed')
    if any(x.is_file() and (x.name=='.env' or (x.name.startswith('.env.') and x.name not in ('.env.example','.env.template')) or x.name=='secrets.toml') for x in repo.rglob('*')):
        raise ValueError('Repository environment file rejected')
    print('Installing pinned dependencies into a fresh dedicated venv. Log: '+str(out/'setup.log'),flush=True)
    logged(['/bin/bash',repo/'verification/ah_pg/setup.sh',venv],'setup.log',repo)
    print('Dependency preflight complete. Preparing private local OS namespaces.',flush=True)
    subprocess.run(['sudo','-v'],env={'PATH':env['PATH'],'TERM':os.environ.get('TERM','dumb')},check=True)
    # Use original environment so the runner independently rejects inherited inputs.
    with (out/'runner.log').open('w') as f:
        result=subprocess.run([str(venv/'bin/python'),str(repo/'verification/mixed_pg/run.py'),'--candidate',sha,'--output-parent',str(work/'runs')],cwd=repo,stdout=f,stderr=subprocess.STDOUT)
    state.update(state='EXECUTED_AWAITING_INSPECTION' if result.returncode==0 else 'FAILED_OR_BLOCKED',exit=result.returncode)
except BaseException as e:
    state['error']=str(e);(out/'bootstrap-exception.txt').write_text(traceback.format_exc())
finally:
    (out/'bootstrap-status.json').write_text(json.dumps(state,indent=2)+'\n')
    (out/'CANDIDATE').write_text(sha+'\n')
    (out/'bootstrap.sha256').write_text(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()+'  bootstrap.py\n')
    members={str(p.relative_to(out)):p for p in out.rglob('*') if p.is_file()}
    for folder in (work/'runs').glob('mixed-pg-run-*') if (work/'runs').exists() else []:
        for path in folder.iterdir():
            if path.is_file() and path.suffix!='.gz': members['native/'+path.name]=path
    sums=out/'SHA256SUMS'
    sums.write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+name+'\n' for name,path in sorted(members.items())))
    members['SHA256SUMS']=sums
    archive=work/'mixed-postgres-results.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for name,path in sorted(members.items()):tar.add(path,arcname='mixed-postgres-results/'+name)
    print('RETURN ONLY THIS ARCHIVE: '+str(archive),flush=True)
    print('SHA256: '+hashlib.sha256(archive.read_bytes()).hexdigest(),flush=True)
    print('State: '+state['state']+'. No PostgreSQL acceptance until archive inspection.',flush=True)
raise SystemExit(0 if state['state']=='EXECUTED_AWAITING_INSPECTION' else 1)
