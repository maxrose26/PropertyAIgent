"""One fixed, sequential read-only compatibility window per remaining Idox council."""
from dataclasses import asdict
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from .idox_window import WindowConfig, live
from verification.stage26b_l1.actions_runner import supervise

# Selected before source observations. This is historical source qualification,
# not the unseen/prospective acceptance calendar or database identity freeze.
CASES=tuple(WindowConfig(c,'VALIDATED' if c=='stockport' else 'RECEIVED',date(2026,9,28),date(2026,10,4))
            for c in ('bury','oldham','stockport','tameside','wigan'))
WORKFLOW='.github/workflows/stage4-discovery-idox-family-once.yml'


def manifest():
    return [{'council':c.council,'base':c.base,'semantics':c.semantics,
             'start':c.start.isoformat(),'end':c.end.isoformat()} for c in CASES]


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker-index',type=int,choices=range(len(CASES)))
    a=p.parse_args()
    if any(k in os.environ for k in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY')):raise ValueError('credential-free only')
    sha=os.environ.get('DISCOVERY_CANDIDATE_SHA','');run_id=os.environ.get('DISCOVERY_RUN_ID','')
    if not re.fullmatch('[0-9a-f]{40}',sha) or not re.fullmatch('[0-9]{1,20}',run_id):raise ValueError('run identity')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise ValueError('candidate mismatch')
    if a.output.exists():raise ValueError('existing output')
    digest=hashlib.sha256(json.dumps(manifest(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if a.worker_index is not None:
        result=live(CASES[a.worker_index])
        result.update(code_sha=sha,run_id=run_id,attempt=1,manifest_sha256=digest,execution_workflow=WORKFLOW)
        raw=json.dumps(result,sort_keys=True).encode()
        if len(raw)>512000:raise ValueError('audit bound')
        a.output.write_bytes(raw)
        return 0
    a.output.mkdir()
    outcomes=[]
    for index,config in enumerate(CASES):
        with tempfile.TemporaryDirectory(prefix='discovery-idox-family-') as td:
            child=Path(td)/'audit.json'
            env={'HOME':td,'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','DISCOVERY_CANDIDATE_SHA':sha,'DISCOVERY_RUN_ID':run_id}
            code,expired=supervise([sys.executable,'-m','verification.discovery.idox_family','--worker-index',str(index),'--output',str(child)],env=env,deadline=50)
            if expired or code!=0 or not child.exists() or child.stat().st_size>512000:
                result={'council':config.council,'completeness':'FAILED','failure':'WORKER_FAILURE','cleanup':'SUPERVISOR_RETURNED','persistence':False,'code_sha':sha,'run_id':run_id,'manifest_sha256':digest}
            else:result=json.loads(child.read_bytes())
            result['supervisor']={'worker_exit':code,'expired':expired,'returned':True,'worker_restarted':False}
            (a.output/(config.council+'.json')).write_text(json.dumps(result,sort_keys=True))
            outcomes.append(result.get('failure') is None and result.get('enumeration_evidence')=='COUNT_RECONCILED' and result.get('applied_interval')==result.get('requested_interval'))
    (a.output/'manifest.json').write_text(json.dumps({'cases':manifest(),'manifest_sha256':digest,'code_sha':sha,'run_id':run_id,'persistence':False},sort_keys=True))
    return 0 if all(outcomes) else 1


if __name__=='__main__':raise SystemExit(main())
