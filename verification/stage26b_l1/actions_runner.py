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
from urllib.parse import parse_qs, urlsplit
from .actions_canary import AUTHORITY, CASES, MAX_ARTIFACT, REPOSITORY, VERSION, encode_artifact
from .actions_canary import BASE


def validate_worker_artifact(result, *, sha, mode, status):
    """Exact minimised schema; contradictory COMPLETE is never accepted."""
    top = {'manifest_version', 'workflow_version', 'repository', 'repository_sha',
        'execution_time', 'mode', 'execution_status', 'persistence',
        'council_network_requests', 'requests_attempted', 'received_bytes',
        'budget_state', 'elapsed_seconds', 'results'}
    if not isinstance(result, dict) or set(result) != top: raise ValueError('Audit schema')
    if (result['manifest_version'] != VERSION or result['workflow_version'] != VERSION
        or result['repository'] != REPOSITORY or result['repository_sha'] != sha
        or result['mode'] != mode or result['persistence'] is not False
        or result['execution_status'] not in ('COMPLETE', 'FAIL')
        or result['budget_state'] not in ('WITHIN_LIMITS', 'EXHAUSTED')):
        raise ValueError('Audit identity/state')
    stamp = dt.datetime.fromisoformat(result['execution_time'])
    if stamp.utcoffset() != dt.timedelta(0): raise ValueError('UTC required')
    def integer(value, maximum):
        if type(value) is not int or not 0 <= value <= maximum: raise ValueError('Audit bound')
    def elapsed(value):
        if type(value) not in (int, float) or not 0 <= value <= 180: raise ValueError('Elapsed bound')
    integer(result['requests_attempted'], 20); integer(result['received_bytes'], 10_000_000)
    integer(result['council_network_requests'], 20); elapsed(result['elapsed_seconds'])
    if result['council_network_requests'] != (0 if mode == 'offline' else result['requests_attempted']):
        raise ValueError('Network accounting')
    rows = result['results']
    if not isinstance(rows, list) or len(rows) != 2: raise ValueError('Exact cohort')
    required = {'council', 'reference', 'adapter', 'outcome', 'requests_attempted',
        'redirects', 'retries', 'received_bytes', 'elapsed_seconds',
        'budget_exhaustion', 'source_qualification', 'attempted'}
    optional = {'failure_classification', 'status', 'decision', 'decision_date', 'source_url'}
    from .contract import OUTCOMES
    states = {'granted', 'refused', 'withdrawn', 'not_yet_decided',
        'decision_outcome_unknown', 'recommended_for_approval',
        'recommended_for_refusal', 'recommendation_made'}
    for row, case in zip(rows, CASES):
        if not isinstance(row, dict) or not required <= set(row) or set(row) - required - optional:
            raise ValueError('Row schema/privacy')
        if row['reference'] != case['reference'] or row['council'] != 'oldham' or row['adapter'] != 'idox' or row['outcome'] not in OUTCOMES:
            raise ValueError('Row identity/outcome')
        integer(row['requests_attempted'], 10); integer(row['received_bytes'], 10_000_000)
        integer(row['redirects'], 2); integer(row['retries'], 1); elapsed(row['elapsed_seconds'])
        if type(row['budget_exhaustion']) is not bool or row['attempted'] is not (row['requests_attempted'] > 0):
            raise ValueError('Row accounting')
        verified = row['outcome'].startswith('VERIFIED_')
        if verified:
            if not {'status', 'decision', 'decision_date', 'source_url'} <= set(row) or not row['attempted'] or row['budget_exhaustion']:
                raise ValueError('Verified evidence incomplete')
            if row['status'] not in states or (row['decision'] is not None and row['decision'] not in states):
                raise ValueError('Normalized evidence only')
            if row['decision_date'] is not None: dt.date.fromisoformat(row['decision_date'])
            u = urlsplit(row['source_url']); query = parse_qs(u.query)
            if (u.scheme != 'https' or u.netloc != urlsplit(BASE).netloc
                or u.path != urlsplit(BASE).path + '/applicationDetails.do' or u.fragment
                or set(query) != {'activeTab', 'keyVal'} or query['activeTab'] != ['summary']
                or len(query['keyVal']) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', query['keyVal'][0])):
                raise ValueError('Source URL')
            if row['source_qualification'] != ('MOCKED_EXPECTATION' if mode == 'offline' else 'exact_public_council_summary'):
                raise ValueError('Source qualification')
        elif set(row) & {'status', 'decision', 'decision_date', 'source_url'}:
            raise ValueError('Failed result cannot certify a fact')
        if 'failure_classification' in row and (not isinstance(row['failure_classification'], str)
            or not re.fullmatch(r'[A-Za-z0-9 _/.-]{1,120}', row['failure_classification'])):
            raise ValueError('Unsafe error text')
    if sum(r['requests_attempted'] for r in rows) != result['requests_attempted'] or sum(r['received_bytes'] for r in rows) != result['received_bytes']:
        raise ValueError('Accounting reconciliation')
    complete = result['execution_status'] == 'COMPLETE'
    if complete and (status != 0 or result['budget_state'] != 'WITHIN_LIMITS'
        or any(not r['outcome'].startswith('VERIFIED_') for r in rows)):
        raise ValueError('Contradictory COMPLETE')
    if not complete and status == 0: raise ValueError('Contradictory exit status')
    encode_artifact(result)


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
                validate_worker_artifact(result, sha=sha, mode=mode, status=status)
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
