"""Disposable Actions-only supervisor. No hostile-detachment containment claim.

Independent wait timeout + ordinary owned-group cleanup; hosted VM disposal is
the FINAL process boundary. This must not be used on the shared Render service.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from .actions_canary import AUTHORITY, CASES, MAX_ARTIFACT, REPOSITORY, VERSION, encode_artifact


def failure_artifact(sha, outcome, reason, *, mode):
    return dict(manifest_version=VERSION, workflow_version=VERSION,
        repository=REPOSITORY, repository_sha=sha, mode=mode,
        execution_time=dt.datetime.now(dt.timezone.utc).isoformat(),
        execution_status='FAIL', persistence=False,
        budget_state='UNKNOWN_INTERRUPTED', accounting_complete=False,
        results=[dict(reference=c['reference'], council='oldham', adapter='idox',
            outcome=outcome, source_qualification=reason) for c in CASES])


def supervise(command, *, env, deadline=165):
    """No pipes; a detached descendant cannot hold stdout collection open."""
    if not 0 < deadline <= 165: raise ValueError('Worker deadline cannot expand')
    child = subprocess.Popen(command, env=env, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        try: return child.wait(timeout=deadline), False
        except subprocess.TimeoutExpired:
            try: os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            # Do not reap the leader before the last group signal: that reserves
            # its PID and avoids targeting a recycled process-group identity.
            time.sleep(1)
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait(timeout=5)
            return 124, True
    except BaseException:
        # Ordinary cancellation only; no hostile-detachment containment claim.
        if child.returncode is None:
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait(timeout=5)
        raise


def execute(*, sha, mode, authority, output, deadline=120, job_start_epoch=None):
    if not re.fullmatch(r'[0-9a-f]{40}', sha): raise ValueError('Exact commit required')
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise ValueError('Only disposable GitHub-hosted runner admitted')
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], text=True)
    if actual != sha or dirty: raise ValueError('Pinned clean checkout required')
    if mode == 'live' and authority != AUTHORITY: raise ValueError('Live acknowledgement required')
    if output.exists(): raise ValueError('Refusing existing artifact')
    if job_start_epoch is not None:
        # Reserve 20s for ordinary cleanup/upload inside the 3min outer job.
        # Platform cancellation can still prevent upload; it is never a PASS.
        remaining = 180 - (time.time() - job_start_epoch) - 20
        if remaining <= 0:
            with output.open('xb') as target:
                target.write(encode_artifact(failure_artifact(sha, 'TIMEOUT', 'setup_consumed_job_budget', mode=mode)))
            return 1
        deadline = min(deadline, remaining)
    with tempfile.TemporaryDirectory(prefix='l1-actions-canary-') as directory:
        audit = Path(directory) / 'audit.json'
        # No inherited GitHub token, production keys, proxies, netrc, or service
        # variables. A fresh HOME is deliberately not the runner's credential HOME.
        env = dict(PATH='/usr/bin:/bin', HOME=directory, TMPDIR=directory, LANG='C.UTF-8',
                   PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-m', 'verification.stage26b_l1.actions_canary',
            '--sha', sha, '--mode', mode, '--authority', authority, '--output', str(audit)]
        status, timeout = supervise(command, env=env, deadline=deadline)
        if timeout:
            result = failure_artifact(sha, 'TIMEOUT', 'independent_worker_deadline', mode=mode)
        elif not audit.exists() or audit.stat().st_size > MAX_ARTIFACT:
            result = failure_artifact(sha, 'PARTIAL_RETRIEVAL', 'missing_or_oversized_audit', mode=mode)
        else:
            try:
                result = json.loads(audit.read_bytes())
                if (result['manifest_version'] != VERSION or result['repository_sha'] != sha
                    or result['mode'] != mode or result['persistence'] is not False
                    or [r['reference'] for r in result['results']] != [c['reference'] for c in CASES]
                    or (status != 0 and result['execution_status'] == 'COMPLETE')):
                    raise ValueError('Audit provenance mismatch')
            except Exception:
                result = failure_artifact(sha, 'PARTIAL_RETRIEVAL', 'invalid_audit', mode=mode)
        encoded = encode_artifact(result)
        with output.open('xb') as target: target.write(encoded)
    return 0 if result['execution_status'] == 'COMPLETE' else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sha', required=True)
    p.add_argument('--mode', choices=('offline', 'live'), default='offline')
    p.add_argument('--authority', default='OFFLINE_ONLY')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--deadline', type=float, default=120)
    p.add_argument('--job-start-epoch', type=float)
    args = p.parse_args()
    try: return execute(**vars(args))
    except Exception:
        # Never print raw subprocess/source exceptions or environment values.
        print('Actions canary admission/supervision failed', file=sys.stderr)
        return 2


if __name__ == '__main__': raise SystemExit(main())
