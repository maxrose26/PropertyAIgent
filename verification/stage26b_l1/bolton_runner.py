"""Fixed Bolton audit launcher; disposable Actions only for separately authorised live runs."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from .actions_runner import supervise
from .actions_canary import ImportFence, offline_network_denial

AUTHORITY = 'AUTHORISE_BOLTON_TWO_SUMMARIES_ONLY'
OUTER_SECONDS = 120
WORKER_SECONDS = 45

def admit(sha, mode, authority):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Exact SHA required')
    actual = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git','status','--porcelain'], text=True).strip()
    if actual != sha or dirty:
        raise ValueError('Exact clean checkout required')
    if mode not in ('offline','live'):
        raise ValueError('Unknown mode')
    if mode == 'live' and (authority != AUTHORITY or
            os.environ.get('GITHUB_ACTIONS') != 'true' or
            os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted' or
            os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch' or
            os.environ.get('BOLTON_WORKFLOW_SHA') != sha):
        raise ValueError('Dedicated live admission required')
    if mode == 'offline' and authority != 'OFFLINE_ONLY':
        raise ValueError('Offline authority required')

def worker(sha, mode, output):
    # Install before importing the accepted verifier; no production connector/model.
    fence = ImportFence()
    sys.meta_path.insert(0, fence)
    try:
        from .bolton_literal import run, http_dispatch, encode
        if mode == 'offline':
            from .bolton_rehearsal import dispatch
            with offline_network_denial():
                artifact = run(sha=sha, dispatch=dispatch)
        else:
            artifact = run(sha=sha, dispatch=http_dispatch,
                           qualification='exact_public_council_summary')
        with output.open('xb') as target:
            target.write(encode(artifact))
        return 0 if artifact['execution_status'] == 'COMPLETE' else 1
    finally:
        sys.meta_path.remove(fence)

def execute(sha, mode, authority, output, job_start_epoch=None):
    admit(sha, mode, authority)
    if output.exists():
        raise ValueError('Refusing existing artifact')
    deadline = WORKER_SECONDS
    if mode == 'live' and job_start_epoch is None:
        raise ValueError('Outer job accounting required')
    if job_start_epoch is not None:
        age = time.time() - job_start_epoch
        if not 0 <= age < OUTER_SECONDS - 15:
            raise ValueError('Setup exhausted job budget')
        deadline = min(deadline, OUTER_SECONDS - age - 15)
    with tempfile.TemporaryDirectory(prefix='bolton-canary-') as directory:
        audit = Path(directory)/'audit.json'
        env = dict(PATH='/usr/bin:/bin', HOME=directory, TMPDIR=directory,
                   LANG='C.UTF-8', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
        if mode == 'live':
            env.update(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted',
                       GITHUB_EVENT_NAME='workflow_dispatch', BOLTON_WORKFLOW_SHA=sha)
        command = [sys.executable, '-m', 'verification.stage26b_l1.bolton_runner',
                   '--sha', sha, '--mode', mode, '--authority', authority,
                   '--output', str(audit), '--worker']
        status, expired = supervise(command, env=env, deadline=deadline)
        if expired or status not in (0,1) or not audit.is_file():
            # Interrupted accounting cannot be manufactured as zero requests.
            raise ValueError('Worker interrupted; no validated audit')
        from .bolton_literal import MAX_ARTIFACT, validate, encode
        if audit.stat().st_size > MAX_ARTIFACT:
            raise ValueError('Audit overflow')
        artifact = json.loads(audit.read_bytes())
        validate(artifact)
        expected = 'MOCKED_EXPECTATION' if mode == 'offline' else 'exact_public_council_summary'
        if artifact['repository_sha'] != sha or any(
                row['source_qualification'] != expected for row in artifact['results']) or \
                (artifact['execution_status'] == 'COMPLETE') != (status == 0):
            raise ValueError('Audit provenance/status mismatch')
        with output.open('xb') as target:
            target.write(encode(artifact))
    print('BOLTON_'+mode.upper()+'_AUDIT_VALIDATED'+
          ('; 0 council requests; no persistence' if mode == 'offline' else '; no persistence'))
    return status

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sha', required=True)
    parser.add_argument('--mode', choices=('offline','live'), default='offline')
    parser.add_argument('--authority', default='OFFLINE_ONLY')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--job-start-epoch', type=float)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    try:
        if args.worker:
            admit(args.sha,args.mode,args.authority)
            return worker(args.sha,args.mode,args.output)
        return execute(args.sha,args.mode,args.authority,args.output,args.job_start_epoch)
    except Exception:
        print('Bolton admission/supervision failed; no validated complete audit',file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
