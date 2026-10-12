"""Dedicated disposable-runner launcher. Registration and live authority are HOLD."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from .recon import AUTHORITY, MAX_AUDIT, VERSION, WORKFLOW, encode, envelope, run, validate


def admit(sha,mode,authority):
    if not re.fullmatch('[0-9a-f]{40}',sha) or mode not in ('offline','live'): raise ValueError('admission')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip():
        raise ValueError('clean pinned code required')
    if mode=='offline':
        if authority!='OFFLINE_ONLY': raise ValueError('offline admission')
    elif authority!=AUTHORITY or any(os.environ.get(k)!=v for k,v in {
        'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_EVENT_NAME':'workflow_dispatch',
        'GITHUB_REPOSITORY':'maxrose26/PropertyAIgent','GITHUB_RUN_ATTEMPT':'1','BOLTON_RECON_SHA':sha}.items()):
        raise ValueError('live admission')


def worker(sha,mode,path):
    if mode=='offline':
        from .fixtures import offline_responses
        with offline_responses(): result=run(sha,mode)
    else: result=run(sha,mode)
    try: data=encode(result)
    except Exception:
        result.update(outcome='BUDGET_EXCEEDED',failure_reason='ARTIFACT_LIMIT',result=None,
                      form={'selected':False,'action_path':None,'method':None,'controls':[]},budget_state='EXHAUSTED')
        data=encode(result)
    with path.open('xb') as f: f.write(data)
    return 0 if result['outcome'].startswith('RECOGNISED_') else 1


def supervise(command,env,deadline):
    """Independent timeout, no stdout/stderr pipes. Owned HTTP worker spawns no children."""
    if not 0<deadline<=30: raise ValueError('deadline')
    child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    expired=False
    try:
        try: child.wait(timeout=deadline)
        except subprocess.TimeoutExpired:
            expired=True; child.terminate()
            try: child.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=2)
    finally:
        if child.poll() is None:
            child.kill(); child.wait(timeout=2)
    return child.returncode,expired


def execute(sha,mode,authority,output,job_start=None):
    admit(sha,mode,authority)
    if output.exists(): raise ValueError('existing output')
    deadline=30
    if mode=='live':
        if job_start is None or not 0<=time.time()-job_start<105: raise ValueError('outer deadline')
        deadline=min(deadline,105-(time.time()-job_start))
    with tempfile.TemporaryDirectory(prefix='bolton-discovery-') as directory:
        path=Path(directory)/'audit.json'
        env={'PATH':'/usr/bin:/bin','HOME':directory,'TMPDIR':directory,'LANG':'C.UTF-8','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
        if mode=='live': env.update(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_EVENT_NAME='workflow_dispatch',
            GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_RUN_ATTEMPT='1',BOLTON_RECON_SHA=sha)
        command=[sys.executable,'-m','verification.bolton_recon.runner','--sha',sha,'--mode',mode,'--authority',authority,'--output',str(path),'--worker']
        started=time.monotonic()
        status,expired=supervise(command,env,deadline)
        if expired:
            result=envelope(sha,mode)
            result.update(outcome='TIMEOUT',failure_reason='WORKER_INTERRUPTED',requests=None,redirects=None,received_bytes=None,
                accounting_complete=False,cleanup_verified=True,budget_state='UNKNOWN_INTERRUPTED',elapsed_seconds=round(time.monotonic()-started,6))
        else:
            if status not in (0,1) or not path.is_file() or path.stat().st_size>MAX_AUDIT: raise ValueError('worker artifact')
            result=json.loads(path.read_bytes()); validate(result)
            if result['code_sha']!=sha or result['mode']!=mode or (status==0)!=result['outcome'].startswith('RECOGNISED_'):
                raise ValueError('artifact provenance')
        with output.open('xb') as f: f.write(encode(result))
    print('Bounded reconnaissance artifact validated; '+('zero council requests' if mode=='offline' else 'audit only'))
    return 0 if result['outcome'].startswith('RECOGNISED_') else 1


def main():
    p=argparse.ArgumentParser(); p.add_argument('--sha',required=True); p.add_argument('--mode',choices=('offline','live'),default='offline')
    p.add_argument('--authority',default='OFFLINE_ONLY'); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--job-start',type=float); p.add_argument('--worker',action='store_true'); a=p.parse_args()
    try:
        admit(a.sha,a.mode,a.authority)
        return worker(a.sha,a.mode,a.output) if a.worker else execute(a.sha,a.mode,a.authority,a.output,a.job_start)
    except Exception:
        print('Reconnaissance admission/output failed; no accepted artifact',file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
