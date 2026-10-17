"""Real Linux gh and kernel memory limit; no credentials or source access."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest
from verification.ingestion_storage import memory_enforcement as m


def enter_with_worker_limits(group):
    import resource
    group.enter()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))


@pytest.fixture
def memory_group(monkeypatch):
    # Test-only path, never consulted by the production module or CLI.
    root = os.environ.get('INGESTION_TEST_CGROUP_ROOT')
    if not root:
        pytest.fail('Disposable delegated cgroup required; do not count a skip as validation')
    root = Path(root)
    assert root.is_relative_to('/sys/fs/cgroup')
    import secrets
    root = root / ('case-' + secrets.token_hex(6))
    root.mkdir()
    root.joinpath('memory.max').write_text(str(m.LIMIT))
    root.joinpath('memory.swap.max').write_text('0')
    root.joinpath('memory.oom.group').write_text('1')
    root.joinpath('cgroup.subtree_control').write_text('+memory')
    group = m.WorkerMemory.create_under(root)
    from verification.ingestion_storage import storage_controller as c
    monkeypatch.setattr(c.WorkerMemory, 'create', classmethod(lambda cls: group))
    yield group
    if not group.closed:
        group.close(time.monotonic() + 2)
    root.rmdir()


def test_real_gh_startup_under_kernel_memory_limit(memory_group, record_property):
    gh = shutil.which('gh')
    assert gh, 'Real Linux GitHub CLI is required'
    p = subprocess.run([gh, '--version'], preexec_fn=lambda:enter_with_worker_limits(memory_group),
                       capture_output=True, timeout=10, text=True)
    assert p.returncode == 0 and 'gh version' in p.stdout
    result = memory_group.close(time.monotonic()+2)
    assert not result['kernel_memory_populated']
    assert not result['kernel_memory_oom_kill']
    record_property('real_gh_memory', json.dumps(result, sort_keys=True))


def test_real_gh_and_descendant_excess_killed_together(memory_group, record_property):
    import http.server
    import threading
    gh = shutil.which('gh')
    assert gh
    received = threading.Event()
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            received.set()
            time.sleep(2)
        def log_message(self, *args):
            pass
    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    # Real gh starts and waits on a disposable loopback HTTP response while a
    # sibling consumes memory. No GitHub/source/DB service or real token used.
    code = '''
import os, subprocess, sys, time
p=subprocess.Popen([sys.argv[1], 'api', sys.argv[2]], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, env={**os.environ,'GH_TOKEN':'disposable_fixture_only'})
time.sleep(.5)
assert p.poll() is None
x=[]
while True:
    x.append(bytearray(4*1024*1024))
'''
    url = 'http://127.0.0.1:%s/' % server.server_port
    p = subprocess.Popen([sys.executable, '-c', code, gh, url], preexec_fn=lambda:enter_with_worker_limits(memory_group),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        p.wait(timeout=10)
        assert received.is_set(), 'Real gh did not reach the loopback fixture'
        assert p.returncode < 0
        state = memory_group.snapshot()
        assert state['kernel_memory_oom_kill'] > 0
        result = memory_group.close(time.monotonic()+2)
        assert not result['kernel_memory_populated'] and result['kernel_memory_group_removed']
        record_property('real_gh_excess_memory', json.dumps(result, sort_keys=True))
    finally:
        if p.poll() is None:
            memory_group.path.joinpath('cgroup.kill').write_text('1')
            p.wait(timeout=2)
        server.server_close()
        thread.join(timeout=3)


def test_missing_enforcement_fails_closed(tmp_path):
    with pytest.raises((OSError, m.MemoryUnavailable)):
        m.WorkerMemory.create_under(tmp_path)


def test_enforcement_loss_still_kills_and_reconciles(memory_group):
    p = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)'],
                         preexec_fn=memory_group.enter)
    try:
        memory_group.path.joinpath('memory.max').write_text(str(m.LIMIT-4096))
        with pytest.raises(m.MemoryUnavailable, match='MEMORY_ENFORCEMENT_LOST'):
            memory_group.snapshot()
        result = memory_group.close(time.monotonic()+2)
        p.wait(timeout=2)
        assert p.returncode < 0
        assert result['kernel_memory_accounting_uncertain']
        assert result['kernel_memory_forced_cleanup']
        assert result['kernel_memory_group_removed']
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=2)


def test_outer_limit_is_verified_not_only_child(memory_group):
    memory_group.path.parent.joinpath('memory.max').write_text(str(m.LIMIT-4096))
    with pytest.raises(m.MemoryUnavailable, match='OUTER_MEMORY_ENFORCEMENT_LOST'):
        memory_group.snapshot()
    result = memory_group.close(time.monotonic()+2)
    assert result['kernel_memory_accounting_uncertain']
    assert result['kernel_memory_group_removed']


def test_missing_kernel_enforcement_stops_before_worker_and_effects(monkeypatch,tmp_path):
    from verification.ingestion_storage import storage_controller as c
    def unavailable(cls):
        raise c.MemoryUnavailable('MEMORY_DELEGATION_REQUIRED')
    monkeypatch.setattr(c.WorkerMemory,'create',classmethod(unavailable))
    journal=c.Journal(tmp_path/'unavailable','a'*64)
    result=c.supervise('not-a-credential',{},journal)
    journal.close()
    assert result['reason']=='MEMORY_DELEGATION_REQUIRED'
    assert result['status']=='STOP_RECONCILE_NO_RETRY'
    assert result['worker_exit'] is None and result['cleanup']=='UNCERTAIN'


if __name__ == '__main__':
    # Invoked only by disposable CI in a systemd scope constrained BEFORE exec.
    group = m.WorkerMemory.create()
    if sys.argv[1] == 'startup':
        test_real_gh_startup_under_kernel_memory_limit(group, lambda k,v:print(k,v,flush=True))
    elif sys.argv[1] == 'excess':
        test_real_gh_and_descendant_excess_killed_together(group, lambda k,v:print(k,v,flush=True))
    else:
        raise SystemExit('INVALID_DISPOSABLE_MODE')
