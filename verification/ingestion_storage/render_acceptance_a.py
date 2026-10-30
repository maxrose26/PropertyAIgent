"""Fixed offline Render A fixture. Never intake success; expected terminal SIGKILL.

Run under GNU timeout (190s, TERM then KILL after 5s). No DB or publisher.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time

import psutil
from . import render_intake as r
from .operational_supervisor import supervise

MODULE = 'verification.ingestion_storage.render_acceptance_a'
PHASE_SECONDS = 75
OUTER_SECONDS = 190
OUTPUT_BYTES = 32 * 1024
ENV = {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'LC_CTYPE', 'PYTHONNOUSERSITE',
       'PYTHONDONTWRITEBYTECODE', 'OPENBLAS_NUM_THREADS', 'PLAYWRIGHT_BROWSERS_PATH',
       'RENDER', 'RENDER_SERVICE_ID', 'RENDER_SERVICE_NAME', 'RENDER_SERVICE_TYPE',
       'RENDER_GIT_COMMIT', 'RENDER_GIT_BRANCH', 'RENDER_GIT_REPO_SLUG', 'RENDER_REGION',
       'RENDER_INSTANCE_ID', 'RENDER_EXTERNAL_HOSTNAME', 'RENDER_EXTERNAL_URL', 'PORT', 'PWD', 'SHLVL', '_'}
HTML = '<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Render A offline</title><p id="proof">Fixed local browser proof</p>'


def identity(p):
    return dict(pid=p.pid, created=p.create_time(), ppid=p.ppid(), session=os.getsid(p.pid))


class Log:
    def __init__(self): self.size = 0
    def __call__(self, phase, **data):
        raw = json.dumps(dict(fixture='RENDER_A_V1', phase=phase, **data), sort_keys=True)
        self.size += len(raw.encode()) + 1
        if self.size > OUTPUT_BYTES: raise RuntimeError('A_LOG_BOUND')
        print(raw, flush=True)


def orphan(path):
    # A parent exits after a new-session child is ready, matching the escape
    # topology that process-group-only cleanup misses. Browser is a sibling.
    child = os.fork()
    if child:
        deadline = time.monotonic() + 5
        while not Path(path).exists():
            if time.monotonic() > deadline: os._exit(2)
            time.sleep(.01)
        os._exit(0)
    os.setsid()
    Path(path).write_text(json.dumps(identity(psutil.Process())))
    time.sleep(90)
    os._exit(0)


def worker(root, hold):
    from playwright.sync_api import sync_playwright
    from verification.direct_reference.instrumented_probe import browser_launch_options
    r.source_context(json.loads(os.environ['INGESTION_RENDER_PROFILE']))
    root = Path(root)
    import subprocess
    parent = subprocess.Popen([sys.executable, '-m', MODULE, '--orphan', str(root/'orphan.json')])
    if parent.wait(timeout=6) != 0: raise RuntimeError('A_ORPHAN_START')
    denied = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, timeout=20000, **browser_launch_options(None))
        context = browser.new_context(service_workers='block', accept_downloads=False, offline=True)
        def reject(route):
            denied.append('REQUEST'); route.abort()
        context.route('**/*', reject)
        context.route_web_socket('**/*', lambda ws: (denied.append('WEBSOCKET'), ws.close()))
        page = context.new_page()
        page.on('download', lambda _: denied.append('DOWNLOAD'))
        page.on('worker', lambda _: denied.append('WORKER'))
        page.set_content(HTML, timeout=5000)
        if page.locator('#proof').inner_text(timeout=5000) != 'Fixed local browser proof' or denied:
            raise RuntimeError('A_LOCAL_PAGE')
        proof = dict(worker=identity(psutil.Process()), descendants=[identity(p) for p in psutil.Process().children(recursive=True)],
                     orphan=json.loads((root/'orphan.json').read_text()), local_page=True, denied_requests=len(denied))
        raw = json.dumps(proof)
        if len(raw) > 8192: raise RuntimeError('A_PROOF_BOUND')
        (root/'ready.json').write_text(raw)
        if hold:
            while True: page.wait_for_timeout(100)
        deadline = time.monotonic() + 10
        while not (root/'observed').exists():
            if time.monotonic() > deadline: raise RuntimeError('A_READY_NOT_OBSERVED')
            page.wait_for_timeout(25)
        context.close(); browser.close()


def effective_profile(profile):
    # Fixture-only convenience: read allocation inside the ONE A job, then
    # pass an ordinary exact-byte profile to the unchanged validator/monitor.
    # No plan-name inference and no additional discovery job.
    profile = dict(profile)
    if profile.get('aggregate_bytes') is None:
        value = r.memory_sample(r.memory_group())['memory.max']
        if type(value) is not int: raise RuntimeError('A_EFFECTIVE_ALLOCATION_UNAVAILABLE')
        profile['aggregate_bytes'] = value
    return profile


def run(profile, root, emit):
    """Production seam also exercised with synthetic effects in unit tests."""
    r.validate_profile(profile, revision=os.environ.get('RENDER_GIT_COMMIT'))
    monitor = r.MemoryMonitor(profile)
    emit('PREFLIGHT', profile=profile, memory=monitor.evidence(), controller=identity(psutil.Process()))
    for phase in ('normal', 'interrupt'):
        directory = root/phase
        observed = None
        def check():
            nonlocal observed
            monitor.check()
            ready = directory/'ready.json'
            if observed is None and ready.exists():
                if ready.stat().st_size > 8192: raise RuntimeError('A_PROOF_BOUND')
                observed = json.loads(ready.read_text())
                # Verify the ready record against live PID/create-time identities.
                for item in [observed['worker'], observed['orphan'], *observed['descendants']]:
                    p = psutil.Process(item['pid'])
                    if p.create_time() != item['created'] or p.status() == psutil.STATUS_ZOMBIE:
                        raise RuntimeError('A_IDENTITY_CHANGED')
                emit('BROWSER_READY', phase_name=phase, processes=observed, memory=monitor.evidence())
                if phase == 'normal': (directory/'observed').touch()
                if phase == 'interrupt':
                    emit('CONTROLLER_SIGKILL_INTENT', controller=identity(psutil.Process()), graceful_cleanup=False)
                    os.kill(os.getpid(), signal.SIGKILL)
                    raise RuntimeError('A_KILL_RETURNED')
        emit('PHASE_START', phase_name=phase)
        result = supervise([sys.executable, '-m', MODULE, '--worker', str(directory), *(['--hold'] if phase == 'interrupt' else [])],
            environment={'INGESTION_SOURCE_PRIVATE':'ONCE', 'PLAYWRIGHT_BROWSERS_PATH':profile['browser_path'],
                         'INGESTION_RENDER_PROFILE':json.dumps(profile)}, root=directory, source=True,
            seconds=PHASE_SECONDS, execution_budget='BROWSER_SOURCE_V2', render_profile=profile, check=check)
        # Fast normal browser exit can precede the next monitor tick. Its proof
        # is checked after reaping as well; no live identity assertion then.
        if observed is None and (directory/'ready.json').exists():
            if (directory/'ready.json').stat().st_size > 8192: raise RuntimeError('A_PROOF_BOUND')
            observed = json.loads((directory/'ready.json').read_text())
        if phase != 'normal' or observed is None or result['exit_code'] != 0 or result['limit_hit'] or result['cleanup'] != 'CLOSED':
            failure = directory/'worker-failure.json'
            detail = json.loads(failure.read_text()) if failure.exists() and failure.stat().st_size <= 1024 else None
            emit('PHASE_REFUSED', phase_name=phase, supervisor=result, worker_failure=detail)
            raise RuntimeError('A_PHASE_FAILED')
        for item in [observed['worker'], observed['orphan'], *observed['descendants']]:
            try:
                if psutil.Process(item['pid']).create_time() == item['created']: raise RuntimeError('A_NORMAL_SURVIVOR')
            except psutil.NoSuchProcess: pass
        emit('NORMAL_CLEANUP_OBSERVED', processes=observed, supervisor=result, memory=monitor.evidence())
    raise RuntimeError('A_INTERRUPTION_NOT_OBSERVED')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--hold', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--orphan', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker or args.orphan:
        if os.environ.get('INGESTION_SOURCE_PRIVATE') != 'ONCE': return 2
        if args.orphan: orphan(args.orphan)
        else:
            try: worker(args.worker, args.hold)
            except Exception as exc:
                (args.worker/'worker-failure.json').write_text(json.dumps(dict(phase='LOCAL_BROWSER_FIXTURE', error_type=type(exc).__name__)))
                return 2
        return 0
    emit = Log()
    try:
        if set(os.environ) - ENV: raise RuntimeError('A_ENVIRONMENT_NOT_ALLOWLISTED')
        if os.environ.get('RENDER_SERVICE_ID') != r.SERVICE: raise RuntimeError('A_SERVICE_BINDING')
        import re
        if not re.fullmatch('[a-f0-9]{40}', os.environ.get('RENDER_GIT_COMMIT', '')): raise RuntimeError('A_REVISION_BINDING')
        if args.profile is None or args.output is None or args.hold: raise RuntimeError('A_ARGUMENTS')
        if args.profile.stat().st_size > 4096: raise RuntimeError('A_PROFILE_BOUND')
        profile = effective_profile(json.loads(args.profile.read_text()))
        if (profile['source_rss_bytes'], profile['controller_rss_bytes'], profile['reserve_bytes'], profile['source_seconds']) != (1024*r.MiB,256*r.MiB,512*r.MiB,75):
            raise RuntimeError('A_FIXED_ACCEPTANCE_LIMITS')
        args.output.mkdir(mode=0o700)  # unique, no overwrite
        emit('ENVIRONMENT_ACCEPTED', names=sorted(os.environ))
        run(profile, args.output, emit)
    except Exception as exc:
        emit('REFUSED', error_type=type(exc).__name__, successful_intake=False)
        return 2
    return 2


if __name__ == '__main__': raise SystemExit(main())
