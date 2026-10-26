"""Worker exit and descendant evidence (docs/design/real-worker-proof-20261026/SPEC.md section 3).

Child output is untrusted: only a fixed, validated reason from the allowlist is ever recorded; raw text never is.
"""
import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from verification.discovery import four_council_release as r

ROOT = Path(__file__).resolve().parents[1]
LINE = lambda reason, **k: json.dumps(dict(dict(status='STOP_RECONCILE_NO_RETRY', reason=reason, cleanup='UNCERTAIN'), **k)).encode() + b'\n'


# ---------------------------------------------------------------- return code, signal and the validated reason

def test_a_valid_fixed_reason_is_recorded_with_the_return_code():
    assert r.worker_exit_evidence(1, LINE('DEPENDENCY_UNAVAILABLE'), 0) == dict(
        returncode=1, signal=None, reason='DEPENDENCY_UNAVAILABLE', reason_state='VALIDATED')


@pytest.mark.parametrize('code,expected', [(-9, dict(returncode=None, signal=9)), (-15, dict(returncode=None, signal=15)),
                                           (137, dict(returncode=137, signal=None)), (0, dict(returncode=0, signal=None))])
def test_signal_and_exit_status_are_distinguished(code, expected):
    got = r.worker_exit_evidence(code, b'', 0)
    assert {k: got[k] for k in ('returncode', 'signal')} == expected and got['reason_state'] == 'ABSENT'


@pytest.mark.parametrize('code', [None, 'x', 1.5, True, 10 ** 9, -10 ** 9, [1]])
def test_an_implausible_return_code_is_never_recorded(code):
    got = r.worker_exit_evidence(code, b'', 0)
    assert got['returncode'] is None and got['signal'] is None or code is True


@pytest.mark.parametrize('data,state', [
    (b'', 'ABSENT'),
    (b'not json\n', 'MALFORMED'),
    (b'{"status":"STOP_RECONCILE_NO_RETRY","reason":"PREPARATION_FAILURE"}\n', 'MALFORMED'),                      # missing key
    (LINE('PREPARATION_FAILURE', extra=1), 'MALFORMED'),                                                          # extra key
    (b'{"status":"STOP_RECONCILE_NO_RETRY","reason":"PREPARATION_FAILURE","reason":"PREPARATION_FAILURE","cleanup":"UNCERTAIN"}\n', 'MALFORMED'),
    (LINE('PREPARATION_FAILURE').replace(b'STOP_RECONCILE_NO_RETRY', b'OTHER'), 'MALFORMED'),
    (LINE('PREPARATION_FAILURE').replace(b'UNCERTAIN', b'CLOSED'), 'MALFORMED'),
    (b'{"status":"STOP_RECONCILE_NO_RETRY","reason":7,"cleanup":"UNCERTAIN"}\n', 'MALFORMED'),
    (b'[1]\n', 'MALFORMED'), (b'"x"\n', 'MALFORMED'), (b'null\n', 'MALFORMED'),
    (LINE('PREPARATION_FAILURE') + LINE('PREPARATION_FAILURE'), 'MALFORMED'),                                       # more than one line
    (b'\xff\xfe\n', 'MALFORMED'),
    pytest.param(b'{"a":' * 3000, 'MALFORMED', id='deeply-nested'),
    (LINE('SOME_UNLISTED_CODE'), 'UNRECOGNISED'),
    (LINE('lowercase_or_free text'), 'UNRECOGNISED'),
    (LINE('PREPARATION_FAILURE').replace(b'PREPARATION_FAILURE', 'PRÉPARATION'.encode()), 'MALFORMED')])
def test_untrusted_output_is_never_trusted(data, state):
    got = r.worker_exit_evidence(1, data, 0)
    assert got['reason_state'] == state and got['reason'] is None and got['returncode'] == 1
    assert set(got) == {'returncode', 'signal', 'reason', 'reason_state'}      # never any raw text


def test_a_flood_beyond_the_bound_is_malformed_even_if_the_start_looks_valid():
    got = r.worker_exit_evidence(1, LINE('PREPARATION_FAILURE'), 1)
    assert got['reason_state'] == 'MALFORMED' and got['reason'] is None


def test_every_reason_the_worker_path_can_print_is_allowlisted():
    """Drift guard: each `raise Stop('CODE')` literal in the worker path must be a recorded reason."""
    tree = ast.parse((ROOT / 'verification/discovery/four_council_release.py').read_text())
    codes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in {'worker', 'owner_source_context'}:
            codes |= {n.exc.args[0].value for n in ast.walk(node) if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
                      and getattr(n.exc.func, 'id', '') == 'Stop' and n.exc.args and isinstance(n.exc.args[0], ast.Constant)}
    assert codes and codes <= r.WORKER_EXIT_REASONS, codes - r.WORKER_EXIT_REASONS
    assert {'DEPENDENCY_UNAVAILABLE', 'PREPARATION_FAILURE', 'UNCLASSIFIED_STOP'} <= r.WORKER_EXIT_REASONS


def run_guard(error, capsys):
    """Execute the module's real `__main__` guard with `main` replaced by one that raises `error`."""
    tree = ast.parse((ROOT / 'verification/discovery/four_council_release.py').read_text())
    guard = [n for n in tree.body if isinstance(n, ast.If)][-1]
    assert ast.unparse(guard.test) == "__name__ == '__main__'"
    namespace = dict(vars(r), __name__='__main__', main=lambda: (_ for _ in ()).throw(error))
    with pytest.raises(SystemExit) as caught:
        exec(compile(ast.Module([guard], []), 'guard', 'exec'), namespace)
    return caught.value.code, capsys.readouterr().out


@pytest.mark.parametrize('error,reason', [
    (ModuleNotFoundError("No module named 'rapidfuzz'"), 'DEPENDENCY_UNAVAILABLE'), (ImportError('x'), 'DEPENDENCY_UNAVAILABLE'),
    (FileExistsError('PRIVATE /path'), 'PREPARATION_FAILURE'), (RuntimeError('PRIVATE token'), 'PREPARATION_FAILURE'),
    (r.Stop('CHILD_ENVIRONMENT'), 'CHILD_ENVIRONMENT'), (r.Stop('free text with spaces'), 'UNCLASSIFIED_STOP')])
def test_the_worker_guard_prints_only_a_fixed_reason(capsys, error, reason):
    code, out = run_guard(error, capsys)
    assert code == 1 and 'PRIVATE' not in out and 'rapidfuzz' not in out
    value = json.loads(out)
    assert value == dict(status='STOP_RECONCILE_NO_RETRY', reason=reason, cleanup='UNCERTAIN')
    assert r.worker_exit_evidence(1, out.encode(), 0)['reason_state'] in {'VALIDATED', 'UNRECOGNISED'}
    assert reason in r.WORKER_EXIT_REASONS and r.worker_exit_evidence(1, out.encode(), 0)['reason'] == reason


# ---------------------------------------------------------------- the bounded, non-blocking pipe

def pipe_child(payload=b''):
    read, write = os.pipe()
    if payload:
        os.write(write, payload)
    return SimpleNamespace(stdout=os.fdopen(read, 'rb', buffering=0)), write


def test_the_pipe_keeps_a_bounded_prefix_and_discards_the_rest():
    child, write = pipe_child()
    pipe = r.BoundedPipe()
    pipe.attach(child)
    pipe.drain()                                               # nothing yet: must not block
    assert pipe.data == b'' and pipe.discarded == 0
    os.write(write, b'x' * 3000)
    pipe.drain()
    os.write(write, b'y' * 10000)
    pipe.drain()
    assert len(pipe.data) == r.WORKER_OUTPUT_BOUND and pipe.data[:3000] == b'x' * 3000 and pipe.discarded == 13000 - r.WORKER_OUTPUT_BOUND
    os.close(write)
    pipe.drain()
    pipe.close()
    assert pipe.fd is None


def test_the_pipe_is_inert_without_a_stream():
    for child in (SimpleNamespace(), SimpleNamespace(stdout=None), object()):
        pipe = r.BoundedPipe()
        pipe.attach(child)
        pipe.drain()
        pipe.close()
        assert pipe.data == b'' and pipe.discarded == 0


# ---------------------------------------------------------------- Source.run records it without changing any gate

class FakePopen:
    def __init__(self, returncode, output=b''):
        self.returncode, self._output = returncode, output
        holder, self._write = pipe_child(output)
        self.stdout = holder.stdout
        os.close(self._write)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


def source_for(tmp_path, monkeypatch, child, version=None):
    group = tmp_path / 'source'
    group.mkdir()
    (group / 'cgroup.kill').write_text('')
    (group / 'cgroup.events').write_text('populated 0\n')
    memory = SimpleNamespace(source=group, snapshot=lambda: None)
    monkeypatch.setattr(r.subprocess, 'Popen', lambda *a, **k: child)
    return r.Source(memory, {'version': version or r.SUCCESSOR_V2_VERSION}, tmp_path)


@pytest.mark.parametrize('version', [r.SUCCESSOR_VERSION, r.SUCCESSOR_V2_VERSION])
def test_a_self_exit_records_the_return_code_and_validated_reason(tmp_path, monkeypatch, version):
    source = source_for(tmp_path, monkeypatch, FakePopen(1, LINE('DEPENDENCY_UNAVAILABLE')), version)
    with pytest.raises(r.SourceFailure) as caught:
        source.run(1, lambda: None)
    assert caught.value.primary == dict(stage='SOURCE_PROCESS_EXIT', code='SOURCE_CHILD_FAILURE', kind='STOP', message_exported=False)
    assert caught.value.closure['worker_exit'] == dict(returncode=1, signal=None, reason='DEPENDENCY_UNAVAILABLE', reason_state='VALIDATED')
    assert caught.value.closure['source_group_closed'] is True and caught.value.closure['child_reaped'] is True


@pytest.mark.parametrize('output,state', [
    pytest.param(b'', 'ABSENT', id='no-output'), pytest.param(b'garbage', 'MALFORMED', id='garbage'),
    pytest.param(b'x' * 20000, 'MALFORMED', id='flood'), pytest.param(LINE('NOT_A_KNOWN_CODE'), 'UNRECOGNISED', id='unlisted-code')])
def test_the_original_failure_is_preserved_when_output_is_missing_or_malformed(tmp_path, monkeypatch, output, state):
    source = source_for(tmp_path, monkeypatch, FakePopen(1, output))
    with pytest.raises(r.SourceFailure) as caught:
        source.run(1, lambda: None)
    assert caught.value.primary['code'] == 'SOURCE_CHILD_FAILURE' and caught.value.primary['stage'] == 'SOURCE_PROCESS_EXIT'
    assert caught.value.closure['worker_exit']['reason_state'] == state and caught.value.closure['worker_exit']['reason'] is None
    assert 'garbage' not in json.dumps(caught.value.closure) and 'xxxx' not in json.dumps(caught.value.closure)


def test_a_signal_death_is_recorded_as_a_signal(tmp_path, monkeypatch):
    source = source_for(tmp_path, monkeypatch, FakePopen(-9))
    with pytest.raises(r.SourceFailure) as caught:
        source.run(1, lambda: None)
    assert caught.value.closure['worker_exit'] == dict(returncode=None, signal=9, reason=None, reason_state='ABSENT')


def test_a_child_without_a_stdout_pipe_is_tolerated(tmp_path, monkeypatch):
    class Bare:
        returncode = 3
        def poll(self): return 3
        def wait(self, timeout=None): return 3
    source = source_for(tmp_path, monkeypatch, Bare())
    with pytest.raises(r.SourceFailure) as caught:
        source.run(1, lambda: None)
    assert caught.value.closure['worker_exit']['reason_state'] == 'ABSENT' and caught.value.closure['worker_exit']['returncode'] == 3


def test_no_worker_exit_is_recorded_when_the_controller_stops_the_run_itself(tmp_path, monkeypatch):
    from verification.ingestion_storage.memory_enforcement import MemoryUnavailable
    child = SimpleNamespace(returncode=None, stdout=None)
    child.poll = lambda: child.returncode
    child.wait = lambda timeout=None: setattr(child, 'returncode', -9) or -9
    source = source_for(tmp_path, monkeypatch, child)
    source.memory.snapshot = lambda: (_ for _ in ()).throw(MemoryUnavailable('MEMORY_LIMIT_HIT'))
    with pytest.raises(r.SourceFailure) as caught:
        source.run(1, lambda: None)
    assert caught.value.primary['code'] == 'MEMORY_LIMIT_HIT' and 'worker_exit' not in caught.value.closure


def test_a_clean_run_adds_nothing_to_the_closure(tmp_path, monkeypatch):
    audit = tmp_path / 'source-1.json'
    audit.write_bytes(r.canonical({'ok': True}))
    source = source_for(tmp_path, monkeypatch, FakePopen(0, b'ignored but bounded output'))
    value, closure = source.run(1, lambda: None)
    assert value == {'ok': True} and set(closure) == {'source_group_closed', 'child_reaped', 'failures', 'supervised_seconds'}


def test_the_production_child_stdout_is_a_pipe_not_a_file_and_stderr_is_still_discarded(tmp_path, monkeypatch):
    seen = {}
    child = FakePopen(1)
    monkeypatch.setattr(r.subprocess, 'Popen', lambda *a, **k: seen.update(k) or child)
    source = source_for(tmp_path, monkeypatch, child)
    monkeypatch.setattr(r.subprocess, 'Popen', lambda *a, **k: seen.update(k) or child)
    with pytest.raises(r.SourceFailure):
        source.run(1, lambda: None)
    assert seen['stdout'] == r.subprocess.PIPE and seen['stderr'] == r.subprocess.DEVNULL and seen['stdin'] == r.subprocess.DEVNULL
    assert seen['start_new_session'] is True and set(seen['env']) == {'PATH', 'HOME', 'TMPDIR', 'PYTHONDONTWRITEBYTECODE', 'PLAYWRIGHT_BROWSERS_PATH'}


# ---------------------------------------------------------------- descendant identity

class Proc:
    def __init__(self, pid, name='python', ppid=1, status='sleeping', age=3.0, fail=False):
        self.pid, self._name, self._ppid, self._status, self._age, self._fail = pid, name, ppid, status, age, fail

    def name(self):
        if self._fail:
            raise OSError('gone')
        return self._name

    def ppid(self): return self._ppid
    def status(self): return self._status
    def create_time(self): return __import__('time').time() - self._age
    def cmdline(self): raise AssertionError('command lines are never collected')
    def environ(self): raise AssertionError('environments are never collected')
    def cwd(self): raise AssertionError('paths are never collected')


def fake_memory(tmp_path):
    return SimpleNamespace(source=tmp_path / 'source', controller=tmp_path / 'controller')


def test_no_descendants_adds_nothing_so_clean_receipts_are_unchanged(tmp_path):
    assert r.descendant_identity([], fake_memory(tmp_path)) == {}


def test_identity_is_bounded_and_never_reads_command_line_environment_or_path(tmp_path):
    children = [Proc(1000 + i, name='chrome') for i in range(12)]
    out = r.descendant_identity(children, fake_memory(tmp_path))
    assert len(out['descendants']) == 8 and out['descendants_omitted'] == 4
    first = out['descendants'][0]
    assert set(first) == {'pid', 'ppid', 'name', 'status', 'age_seconds', 'group'} and first['name'] == 'chrome'
    assert 2.5 <= first['age_seconds'] <= 10


@pytest.mark.parametrize('name,expected', [('python3.12', 'python3.12'), ('a b', 'UNPRINTABLE'), ('x' * 64, 'x' * 32),
                                           ('tok=\x00secret', 'UNPRINTABLE'), ('', 'UNPRINTABLE')])
def test_names_are_restricted_to_a_safe_character_set(tmp_path, name, expected):
    assert r.descendant_identity([Proc(5, name=name)], fake_memory(tmp_path))['descendants'][0]['name'] == expected


def test_unreadable_processes_are_explicitly_unavailable(tmp_path):
    out = r.descendant_identity([Proc(5, fail=True), object()], fake_memory(tmp_path))
    assert out['descendants'] == [dict(identity='UNAVAILABLE'), dict(identity='UNAVAILABLE')]


def test_the_group_is_a_coarse_class_not_a_path(tmp_path, monkeypatch):
    mine = Path(f'/proc/{os.getpid()}/cgroup').read_text().strip().rsplit('/', 1)[-1]
    memory = SimpleNamespace(source=tmp_path / mine, controller=tmp_path / 'controller')
    assert r.descendant_identity([Proc(os.getpid())], memory)['descendants'][0]['group'] == 'SOURCE'
    memory = SimpleNamespace(source=tmp_path / 'source', controller=tmp_path / mine)
    assert r.descendant_identity([Proc(os.getpid())], memory)['descendants'][0]['group'] == 'CONTROLLER'
    assert r.descendant_identity([Proc(os.getpid())], fake_memory(tmp_path))['descendants'][0]['group'] == 'OTHER'
    assert r.descendant_identity([Proc(4194303)], fake_memory(tmp_path))['descendants'][0]['group'] == 'UNAVAILABLE'
    assert r.descendant_identity([Proc(os.getpid())], object())['descendants'][0]['group'] == 'UNAVAILABLE'


def test_identity_works_on_genuine_psutil_processes_and_never_exports_the_command_line(tmp_path):
    import subprocess
    import sys
    import psutil
    secret = 'DO_NOT_EXPORT_THIS_ARGUMENT'
    child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)', secret], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        seen = r.descendant_identity(psutil.Process().children(recursive=True), fake_memory(tmp_path))
    finally:
        child.kill()
        child.wait()
    entry = next(item for item in seen['descendants'] if item.get('pid') == child.pid)
    assert entry['ppid'] == os.getpid() and entry['name'].startswith('python') and entry['status'] in {'sleeping', 'running', 'disk-sleep'}
    assert entry['group'] in {'OTHER', 'SOURCE', 'CONTROLLER'} and entry['age_seconds'] >= 0
    assert set(entry) == {'pid', 'ppid', 'name', 'status', 'age_seconds', 'group'}
    assert secret not in json.dumps(seen)


def test_closure_receipts_carry_identity_only_when_children_are_seen(world, monkeypatch):
    reg, api, memory, source, launch = world
    monkeypatch.setattr('psutil.Process', lambda: type('P', (), {'children': lambda self, recursive: [Proc(777, name='chrome')]})())
    out = launch.execute()
    assert out['owned_cleanup']['live_child_count'] == 1 and out['process_cleanup'] == 'UNCERTAIN'
    seen = out['owned_cleanup']['descendants']
    assert len(seen) == 1 and seen[0]['pid'] == 777 and seen[0]['name'] == 'chrome' and out['owned_cleanup']['descendants_omitted'] == 0


def test_a_clean_closure_has_no_identity_fields(world):
    reg, api, memory, source, launch = world
    out = launch.execute()
    assert 'descendants' not in out['owned_cleanup'] and out['owned_cleanup'].get('live_child_count') in (None, 0)


from tests.test_discovery_four_council_release import world  # noqa: E402,F401  (fixture reuse)
