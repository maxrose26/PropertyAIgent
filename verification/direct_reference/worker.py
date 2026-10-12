"""Offline-only disposable supervisor rehearsal. No live mode exists.

Same accepted ordinary process-group supervisor as prior Actions canaries.
Future live registration requires separate REVIEW authority. No OS network
isolation claim for future live execution; offline CLI explicitly denies it.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import resource
import sys
import tempfile

MEMORY_BYTES = 512 * 1024 * 1024
WORKER_SECONDS = 45
MAX_AUDIT = 16384

def worker(application_id, output):
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES,MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (30,30))
    from verification.stage26b_l1.actions_canary import offline_network_denial
    with offline_network_denial():
        from .refresh import retrieve, Budget, admitted_row
        from .fixtures import Session, summary
        row=admitted_row(application_id);budget=Budget()
        session=Session(summary(row['reference']))
        result=retrieve(application_id,session_factory=lambda:session,budget=budget)
        artifact=dict(qualification='SYNTHETIC_OFFLINE_ONLY', council_network_requests=0,
            observation=asdict(result), requests=budget.requests, bytes=budget.bytes,
            session_closed=session.closed, responses_closed=all(r.closed for r in session.responses))
        body=json.dumps(artifact).encode()
        if len(body)>MAX_AUDIT:raise ValueError('Audit bound')
        output.write_bytes(body)

def run(application_id):
    from verification.stage26b_l1.actions_runner import supervise
    with tempfile.TemporaryDirectory(prefix='direct-reference-') as directory:
        path=Path(directory)/'audit.json'
        env=dict(PATH='/usr/bin:/bin',HOME=directory,TMPDIR=directory,
                 PYTHONDONTWRITEBYTECODE='1',LANG='C.UTF-8',PYTHONNOUSERSITE='1')
        status,expired=supervise([sys.executable,'-m',__name__.replace('__main__','verification.direct_reference.worker'),
            '--worker','--application-id',str(application_id),'--output',str(path)],env=env,deadline=WORKER_SECONDS)
        if expired or status or not path.is_file():
            raise ValueError('Worker interrupted/failed; accounting UNKNOWN, no success')
        if path.stat().st_size>MAX_AUDIT:raise ValueError('Audit bound')
        artifact=json.loads(path.read_bytes())
        if (artifact['qualification']!='SYNTHETIC_OFFLINE_ONLY' or artifact['council_network_requests']!=0
            or not artifact['session_closed'] or not artifact['responses_closed']
            or artifact['observation']['application_id']!=application_id):
            raise ValueError('Invalid audit')
        return artifact

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--application-id',type=int,default=42)
    p.add_argument('--worker',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.worker:worker(args.application_id,args.output)
    else:print(json.dumps(run(args.application_id)))
