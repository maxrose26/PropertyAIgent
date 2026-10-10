"""Harmless Linux rehearsal, NOT a verifier or a production process runner.

No app imports, /proc traversal, database, environment inspection or networking.
The fixture supervisor is a child-subreaper solely so escaped SYNTHETIC children
can be cleaned and reaped. Adoption is not presented as a containment mechanism.
All signalled PIDs are unreaped children created by this probe and reported over
an inherited anonymous pipe. No kill-by-name or unrelated-process signalling.
"""
import ctypes
import json
import os
from pathlib import Path
import resource
import select
import signal
import tempfile
import time
import uuid


def exited(pid):
    result = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    return result is not None


def reap(pid, seconds=2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return None
        if result:
            return os.waitstatus_to_exitcode(status)
        time.sleep(.01)
    raise RuntimeError('fixture cleanup deadline exceeded')


def worker(case, writer, directory):
    def record(role):
        raw = json.dumps(dict(pid=os.getpid(), group=os.getpgrp(),
                              session=os.getsid(0), role=role)).encode() + b'\n'
        os.write(writer, raw)

    def sleeper(role, detach=None, ignore=False):
        signal.alarm(5)  # Fixture-only fallback; supervisor deadline is <1s.
        if detach == 'session':
            os.setsid()
        if ignore:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        record(role)
        while True:
            time.sleep(60)

    os.setsid()
    signal.alarm(5)
    # Secondary fixture limits only, not a browser resource-policy proposal.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (2, 3))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    Path(directory, 'fixture-artifact').write_text('non-sensitive fixture\n')
    if case == 'detach':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    record('worker')
    if case in ('child', 'grandchild', 'ignore_term', 'detach'):
        child = os.fork()
        if child == 0:
            if case == 'grandchild':
                record('child')
                if os.fork() == 0:
                    sleeper('grandchild')
                while True:
                    time.sleep(60)
            sleeper('child', detach='session' if case == 'detach' else None,
                    ignore=case == 'ignore_term')
        while True:
            time.sleep(60)
    if case == 'normal':
        os._exit(0)
    if case == 'exception':
        # Deterministic synthetic Python exception, no raw traceback in artifact.
        try:
            raise RuntimeError('synthetic')
        except RuntimeError:
            os._exit(10)
    if case == 'parser_failure':
        os._exit(11)
    if case == 'overflow':
        while True:
            os.write(writer, b'x' * 4096)
    while True:
        time.sleep(60)


def case_probe(case):
    started = time.monotonic()
    identities = []
    graceful = forced = False
    reason = None
    root = control = None
    reader = writer = None
    escaped = []
    return_status = None
    directory = tempfile.mkdtemp(prefix='propertyaigent-native-fixture-')
    try:
        control = os.fork()
        if control == 0:
            signal.alarm(15)
            while True:
                time.sleep(60)
        reader, writer = os.pipe()
        root = os.fork()
        if root == 0:
            os.close(reader)
            try:
                worker(case, writer, directory)
            finally:
                os._exit(99)
        os.close(writer)
        writer = None
        os.set_blocking(reader, False)
        pending = bytearray()
        total = 0
        expected = 3 if case == 'grandchild' else 2 if case in ('child', 'ignore_term', 'detach') else 1
        while len(identities) < expected or case == 'overflow':
            remaining = .75 - (time.monotonic() - started)
            if remaining <= 0:
                reason = 'TIMEOUT'
                break
            if not select.select([reader], [], [], min(.05, remaining))[0]:
                continue
            block = os.read(reader, 4096)
            if not block:
                break
            total += len(block)
            pending.extend(block[:max(0, 1024-len(pending))])
            while b'\n' in pending:
                raw, _, tail = pending.partition(b'\n')
                pending = bytearray(tail)
                identities.append(json.loads(raw))
            if total > 1024:
                reason = 'OUTPUT_OVERFLOW'
                break
        if len(identities) != expected:
            raise RuntimeError('fixture identity handshake incomplete: '+case)
        group = identities[0]['group']
        if group != root or identities[0]['session'] != root or group == os.getpgrp():
            raise RuntimeError('fixture group ownership invalid')
        if os.getpgid(control) == group:
            raise RuntimeError('control group must be unrelated')
        if case in ('normal', 'exception', 'parser_failure'):
            end = time.monotonic() + .75
            while not exited(root) and time.monotonic() < end:
                time.sleep(.01)
            if not exited(root):
                reason = 'TIMEOUT'
        elif case == 'explicit_cancel':
            reason = 'CANCELLED'
        elif reason is None:
            end = started + .75
            while time.monotonic() < end:
                time.sleep(.01)
            reason = 'TIMEOUT'
        # Keep the root unreaped until group cancellation is finished, preventing
        # root PID/group reuse. All ordinary descendants inherit this group.
        if reason is not None:
            graceful = True
            try:
                os.killpg(group, signal.SIGTERM)
            except ProcessLookupError:
                pass
            time.sleep(.10)
            def still_live(identity):
                try:
                    return not exited(identity['pid'])
                except ChildProcessError:
                    # Grandchild not adopted yet: no claim of successful exit.
                    return True
            forced = any(i['group'] == group and still_live(i) for i in identities)
            if forced:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        end = time.monotonic() + 1
        while not exited(root) and time.monotonic() < end:
            time.sleep(.01)
        if not exited(root):
            raise RuntimeError('root remained alive after group cancellation')
        # SIGKILL delivery/reparenting is asynchronous. Wait for known same-group
        # fixture children to reach waitable exit before judging containment.
        while time.monotonic() < end:
            alive_same_group = [i for i in identities[1:] if i['group'] == group
                                and not exited(i['pid'])]
            if not alive_same_group:
                break
            time.sleep(.01)
        if alive_same_group:
            raise RuntimeError('owned same-group fixture remains alive')
        # Known descendants are now adopted by this fixture's subreaper. No
        # process census or ancestry sampling is used as the ownership boundary.
        for identity in identities[1:]:
            if not exited(identity['pid']):
                escaped.append(identity)
        control_survived = not exited(control)
        result = dict(case=case, worker=root, owned_group=group,
                      group_distinct_from_supervisor=group != os.getpgrp(),
                      worker_session=identities[0]['session'],
                      deadline_triggered=reason == 'TIMEOUT',
                      outcome=reason or ('SUCCESS' if case == 'normal' else case.upper()),
                      graceful_termination_attempted=graceful,
                      forced_termination_attempted=forced,
                      ordinary_descendants_same_group=all(i['group'] == group for i in identities),
                      escaped_live_processes=len(escaped),
                      control_survived=control_survived)
    finally:
        # Synthetic-fixture cleanup only. Escaped children are individually
        # killed while their unreaped parent/child identities remain pinned.
        for identity in identities[1:]:
            try:
                os.kill(identity['pid'], signal.SIGKILL)
            except ProcessLookupError:
                pass
        if root is not None:
            try:
                if os.getpgid(root) == root and root != os.getpgrp():
                    os.killpg(root, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.kill(root, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return_status = reap(root)
        for identity in identities[1:]:
            reap(identity['pid'])
        if control is not None:
            os.kill(control, signal.SIGTERM)
            reap(control)
        for fd in (reader, writer):
            if fd is not None:
                os.close(fd)
        Path(directory, 'fixture-artifact').unlink(missing_ok=True)
        os.rmdir(directory)
    result.update(worker_exit_status=return_status, cleanup_verified=not Path(directory).exists(),
                  remaining_fixture_processes=0, elapsed_seconds=round(time.monotonic()-started, 3))
    return result


def main():
    if os.name != 'posix' or not hasattr(os, 'waitid'):
        raise RuntimeError('Linux native probe required')
    libc = ctypes.CDLL(None, use_errno=True)
    # Probe-process-local setting; not applied to a web service or future runner.
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise RuntimeError('fixture adoption unavailable')
    cases = ['normal', 'exception', 'parser_failure', 'hung', 'child', 'grandchild',
             'ignore_term', 'overflow', 'explicit_cancel', 'detach']
    results = []
    for case in cases:
        results.append(case_probe(case))
        if results[-1]['escaped_live_processes']:
            break  # STOP: no further containment design or production execution.
    print(json.dumps(dict(manifest='l1-native-process-probe-v1', run_id=uuid.uuid4().hex,
                          supervisor=dict(pid=os.getpid(), session=os.getsid(0), group=os.getpgrp()),
                          cases=results, result='NO-GO' if any(r['escaped_live_processes'] for r in results) else 'GO'),
                     sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
