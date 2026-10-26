"""Runtime dependency binding and check (docs/design/real-worker-proof-20261026/SPEC.md section 1).

Offline: a temporary source tree, monkeypatched metadata and a real child interpreter. The CI wrapper denies sockets, and the
child interpreter inherits that, so the real-release test also shows the bound imports need no network.
"""
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
from unittest.mock import patch

import pytest

from verification.discovery import four_council_release as r
from verification.discovery import runtime_dependencies as rd

ROOT = Path(__file__).resolve().parents[1]
V2 = r.SUCCESSOR_V2_VERSION


def tree(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(text))
    return tmp_path


# ---------------------------------------------------------------- the pin and the binding

def test_exact_version_comes_from_the_existing_project_lock():
    pins = rd.lock_pins()
    assert pins['rapidfuzz'] == '3.14.6' and pins['sqlalchemy'] == '2.1.1'
    assert (ROOT / 'requirements.txt').read_text().split().count('rapidfuzz') == 1   # declared there, unpinned
    for name in r.V2_PACKAGES:
        assert rd.normalise(name) in pins, name      # every V2-bound distribution has an exact pin


def test_lock_parsing_ignores_comments_blanks_and_unpinned_lines(tmp_path):
    lock = tmp_path / 'lock'
    lock.write_text('# c\n\nRapid_Fuzz==1.2.3  # note\nunpinned\nSQLAlchemy == 2.0\n')
    assert rd.lock_pins(lock) == {'rapid-fuzz': '1.2.3', 'sqlalchemy': '2.0'}
    assert rd.normalise('Rapid_Fuzz') == rd.normalise('rapid.fuzz') == 'rapid-fuzz'


def test_v2_binds_the_dependency_and_historical_bindings_are_unchanged():
    assert r.V2_PACKAGES == r.PACKAGES + ('rapidfuzz', 'SQLAlchemy')
    assert r.PACKAGES == ('requests', 'beautifulsoup4', 'lxml', 'playwright', 'psutil', 'cryptography')   # V1 unchanged
    assert set(r.packages()) == set(r.PACKAGES) == set(r.packages(r.VERSION)) == set(r.packages(r.SUCCESSOR_VERSION))
    v2 = r.packages(V2)
    assert set(v2) == set(r.V2_PACKAGES) and v2['rapidfuzz'] and v2['SQLAlchemy']
    assert 'verification/ah_pg/requirements.lock' in r.SUCCESSOR_V2_DEPENDENCIES
    assert 'verification/discovery/runtime_dependencies.py' in r.SUCCESSOR_V2_DEPENDENCIES
    for historical in (r.DEPENDENCIES, r.SUCCESSOR_DEPENDENCIES):
        assert 'verification/ah_pg/requirements.lock' not in historical and 'verification/discovery/runtime_dependencies.py' not in historical
    assert set(r.dependencies(version=V2)) >= {'verification/ah_pg/requirements.lock', 'verification/discovery/runtime_dependencies.py'}
    assert set(r.dependencies()) == set(r.DEPENDENCIES)


def test_registration_records_the_installed_runtime_versions():
    from datetime import timedelta
    issued = r.now() - timedelta(minutes=1)
    reg = r.render('runtime-binding-fixture', 'a' * 40, 'b' * 40, '1' * 40, issued.isoformat(),
                   (issued + timedelta(hours=2)).isoformat(), released=True, version=V2)
    assert set(reg['packages']) == set(r.V2_PACKAGES)
    assert r.validate(reg, checkout=False) == reg
    historical = r.render('runtime-binding-v1', 'a' * 40, 'b' * 40, '1' * 40, issued.isoformat(),
                          (issued + timedelta(hours=2)).isoformat(), released=True, successor=True)
    assert set(historical['packages']) == set(r.PACKAGES)


def test_rendering_a_v2_registration_refuses_an_interpreter_without_the_bound_distribution(monkeypatch):
    from datetime import timedelta
    real = importlib.metadata.version

    def version(name):
        if name == 'rapidfuzz':
            raise importlib.metadata.PackageNotFoundError(name)
        return real(name)
    monkeypatch.setattr(importlib.metadata, 'version', version)
    issued = r.now() - timedelta(minutes=1)
    with pytest.raises(importlib.metadata.PackageNotFoundError):
        r.render('no-rapidfuzz-fixture', 'a' * 40, 'b' * 40, '1' * 40, issued.isoformat(),
                 (issued + timedelta(hours=2)).isoformat(), released=True, version=V2)
    r.render('v1-needs-no-rapidfuzz', 'a' * 40, 'b' * 40, '1' * 40, issued.isoformat(),
             (issued + timedelta(hours=2)).isoformat(), released=True, successor=True)   # historical binding unaffected


# ---------------------------------------------------------------- the static scan (nothing is executed)

def test_scan_models_what_loads(tmp_path):
    tree(tmp_path, {
        'app/__init__.py': '', 'app/pipeline/__init__.py': 'import pkginit_third\n',
        'verification/__init__.py': '', 'verification/discovery/__init__.py': '',
        'verification/discovery/bound.py': '''
            import os, json
            import eager_third
            from app.pipeline import eager_mod
            from . import sibling
            try:
                import optional_third
            except ImportError:
                optional_third = None
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                import typing_only_third
            class K:
                import class_body_third
            def f():
                import lazy_third
                from app.pipeline import lazy_mod
            ''',
        'verification/discovery/sibling.py': 'import sibling_third\n',
        'app/pipeline/eager_mod.py': 'import eager_mod_third\ndef g():\n    import never_followed_third\n    from app import deep_lazy\n',
        'app/pipeline/lazy_mod.py': 'import lazy_mod_third\n',
        'app/deep_lazy.py': 'import deep_lazy_third\n',
    })
    closure, third = rd.scan(['verification/discovery/bound.py'], root=tmp_path)
    assert {'verification.discovery.bound', 'verification.discovery.sibling', 'app.pipeline.eager_mod', 'app.pipeline.lazy_mod',
            'app', 'app.pipeline', 'verification', 'verification.discovery'} == set(closure)
    assert 'app.deep_lazy' not in closure                       # lazy import of a non-bound module is not followed
    assert set(third) == {'eager_third', 'sibling_third', 'eager_mod_third', 'class_body_third', 'lazy_third',
                          'lazy_mod_third', 'pkginit_third'}   # optional/TYPE_CHECKING/never-followed names are absent
    assert not {'os', 'json', 'typing'} & set(third)            # stdlib is not third-party
    assert third['lazy_third'] == 'verification.discovery.bound'


def test_scan_never_executes_the_code_it_reads(tmp_path):
    marker = tmp_path / 'executed'
    tree(tmp_path, {'verification/__init__.py': '', 'verification/discovery/__init__.py': '',
                    'verification/discovery/bound.py': f'open({str(marker)!r}, "w").write("x")\nimport zzz_third\n'})
    rd.scan(['verification/discovery/bound.py'], root=tmp_path)
    assert not marker.exists()


# ---------------------------------------------------------------- the verdict

def project(tmp_path, bound_body='import marker_dep\n', extra=None):
    files = {'app/__init__.py': '', 'verification/__init__.py': '', 'verification/discovery/__init__.py': '',
             'verification/discovery/bound.py': bound_body}
    files.update(extra or {})
    return tree(tmp_path, files)


def lock(tmp_path, text):
    path = tmp_path / 'lock'
    path.write_text(text)
    return path


def fake_version(table):
    def version(name):
        if name in table:
            return table[name]
        raise importlib.metadata.PackageNotFoundError(name)
    return version


def test_check_passes_when_everything_matches(tmp_path):
    project(tmp_path, 'import json\n')
    with patch.object(rd, 'ROOT', tmp_path), patch.object(importlib.metadata, 'version', fake_version({'dep': '1.0'})):
        report = rd.check(['verification/discovery/bound.py'], ['dep'], lock=lock(tmp_path, 'dep==1.0\n'), root=tmp_path)
    assert report['ok'] is True and report['third_party_missing'] == [] and report['import_failures'] == []
    assert report['distributions'] == {'dep': dict(installed='1.0', pinned='1.0', state='OK')}


@pytest.mark.parametrize('installed,state', [({}, 'MISSING'), ({'dep': '9.9'}, 'VERSION_MISMATCH')])
def test_check_fails_for_a_missing_or_different_distribution(tmp_path, installed, state):
    project(tmp_path, 'import json\n')
    with patch.object(rd, 'ROOT', tmp_path), patch.object(importlib.metadata, 'version', fake_version(installed)):
        report = rd.check(['verification/discovery/bound.py'], ['dep'], lock=lock(tmp_path, 'dep==1.0\n'), root=tmp_path)
    assert report['ok'] is False and report['distributions']['dep']['state'] == state


def test_an_unpinned_distribution_needs_only_to_be_present(tmp_path):
    project(tmp_path, 'import json\n')
    with patch.object(rd, 'ROOT', tmp_path), patch.object(importlib.metadata, 'version', fake_version({'free': '0.1'})):
        report = rd.check(['verification/discovery/bound.py'], ['free'], lock=lock(tmp_path, ''), root=tmp_path)
    assert report['ok'] and report['distributions']['free']['pinned'] is None


def test_a_missing_third_party_module_and_a_blocked_finder_both_fail(tmp_path):
    project(tmp_path, 'import absent_dep_xyz\nimport blocked_dep_xyz\n')
    real = importlib.util.find_spec

    def find_spec(name, *a):
        if name == 'blocked_dep_xyz':
            raise ModuleNotFoundError(name)       # a hostile or broken finder is "missing", never a crash
        return real(name, *a)
    with patch.object(rd, 'ROOT', tmp_path), patch.object(rd.importlib.util, 'find_spec', find_spec):
        report = rd.check(['verification/discovery/bound.py'], [], lock=lock(tmp_path, ''), root=tmp_path)
    assert report['third_party_missing'] == ['absent_dep_xyz', 'blocked_dep_xyz'] and report['ok'] is False


def test_the_import_check_runs_in_a_child_and_reports_exception_classes_only(tmp_path):
    project(tmp_path, 'import json\n', extra={'verification/discovery/broken.py': 'raise ModuleNotFoundError("PRIVATE_TEXT /secret/path")\n'})
    with patch.object(rd, 'ROOT', tmp_path):
        failures = rd.import_check(['verification.discovery.bound', 'verification.discovery.broken'])
    assert failures == [['verification.discovery.broken', 'ModuleNotFoundError']]
    assert 'PRIVATE_TEXT' not in json.dumps(failures)


def test_the_child_sees_a_scrubbed_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://must-not-leak')
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-leak')
    project(tmp_path, 'import json\n', extra={'verification/discovery/probe.py': dedent('''
        import os
        leaked = sorted(k for k in os.environ if any(s in k for s in ("DATABASE", "OPENAI", "ANTHROPIC", "GH_", "TOKEN")))
        if leaked:
            raise RuntimeError("leaked")
        ''')})
    with patch.object(rd, 'ROOT', tmp_path):
        assert rd.import_check(['verification.discovery.probe']) == []


@pytest.mark.parametrize('stdout,code', [
    (b'not json', 0), (b'{"a": 1}', 0), (b'[["verification.discovery.bound"]]', 0),
    (b'[["unrequested", "ModuleNotFoundError"]]', 0), (b'[["verification.discovery.bound", "bad name!"]]', 0),
    (b'[["verification.discovery.bound", 7]]', 0), (b'\xff\xfe', 0), (b'[]', 1), (b'[' + b'0,' * 20000 + b'0]', 0)])
def test_malformed_child_output_is_a_failure_never_trusted(stdout, code):
    class Done:
        returncode = code
    done = Done()
    done.stdout = stdout
    with patch.object(rd.subprocess, 'run', lambda *a, **k: done):
        assert rd.import_check(['verification.discovery.bound']) == [['<child>', 'ChildOutputMalformed']]


def test_a_timeout_or_unlaunchable_child_is_a_failure():
    for error in (subprocess.TimeoutExpired('x', 1), FileNotFoundError('x')):
        def run(*a, **k):
            raise error
        with patch.object(rd.subprocess, 'run', run):
            assert rd.import_check(['m']) == [['<child>', 'ChildUnavailable']]


def test_reports_are_bounded():
    with patch.object(rd, 'import_check', lambda modules, **k: [[f'm{i}', 'ImportError'] for i in range(500)]), \
         patch.object(rd, 'scan', lambda paths, root=rd.ROOT: ([f'verification.m{i}' for i in range(5)], {})):
        report = rd.check([], [])
    assert len(report['import_failures']) == rd.BOUND


# ---------------------------------------------------------------- the real release

def locked_environment():
    return all(d['state'] == 'OK' for d in rd.check([], r.V2_PACKAGES)['distributions'].values())


def test_the_real_v2_release_check_in_this_interpreter():
    if not locked_environment():
        pytest.skip('this interpreter is not the lock-pinned environment; the owner preflight is the gate for the launch interpreter')
    report = r.runtime_check(V2)
    assert report['ok'], report
    assert report['modules']['imported'] >= 40 and 'app.pipeline.site_linking' in rd.scan(
        [p for p in r.DEPENDENCIES + r.SUCCESSOR_V2_DEPENDENCIES if p.endswith('.py')])[0]
    assert 'rapidfuzz' in rd.scan([p for p in r.DEPENDENCIES + r.SUCCESSOR_V2_DEPENDENCIES if p.endswith('.py')])[1]


def test_the_runtime_check_names_the_known_gap_in_a_python_without_rapidfuzz(tmp_path):
    """The live defect, reproduced as a verdict: a child interpreter where `rapidfuzz` cannot be imported."""
    shadow = tmp_path / 'shadow'
    (shadow / 'rapidfuzz').mkdir(parents=True)
    (shadow / 'rapidfuzz/__init__.py').write_text("raise ModuleNotFoundError(\"No module named 'rapidfuzz'\")\n")
    paths = [p for p in r.DEPENDENCIES + r.SUCCESSOR_V2_DEPENDENCIES if p.endswith('.py')]
    modules = [m for m in rd.scan(paths)[0] if m not in rd.NOT_IMPORTED]
    failures = rd.import_check(modules, extra_env={'PYTHONPATH': str(shadow)})
    assert failures == [['app.pipeline.site_linking', 'ModuleNotFoundError']]


def test_cli_subcommand_reports_json_and_exit_status():
    env = dict(PATH='/usr/bin:/bin', HOME=str(ROOT), PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    done = subprocess.run([sys.executable, '-m', 'verification.discovery.four_council_release', 'runtime-check', '--version', V2],
                          cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120)
    report = json.loads(done.stdout)
    assert (done.returncode == 0) is report['ok'] is (locked_environment() and report['ok'])
    assert set(report) == {'distributions', 'third_party_missing', 'import_failures', 'modules', 'ok'}


def scrub_credentials(monkeypatch):
    for key in list(os.environ):      # the controller itself refuses credential-named variables
        if any(s in key.upper() for s in ('DATABASE', 'SUPABASE', 'OPENAI', 'ANTHROPIC')):
            monkeypatch.delenv(key)


def test_the_pre_claim_gate_refuses_before_any_effect(tmp_path, monkeypatch, capsys):
    """V2 run mode checks the interpreter after validation and before the state directory, journal or any claim."""
    from datetime import timedelta
    scrub_credentials(monkeypatch)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    issued = r.now() - timedelta(minutes=1)
    reg = r.render('runtime-gate-fixture', 'a' * 40, 'b' * 40, '1' * 40, issued.isoformat(),
                   (issued + timedelta(hours=2)).isoformat(), released=True, version=V2)
    raw = r.canonical(reg)
    path = tmp_path / 'reg.json'
    path.write_bytes(raw)
    seen = []
    monkeypatch.setattr(r, 'validate', lambda value: value)
    monkeypatch.setattr(r, 'runtime_check', lambda version: seen.append(version) or dict(ok=False, third_party_missing=['rapidfuzz']))
    monkeypatch.setattr(r, 'OperationalMemory', lambda **k: pytest.fail('memory must not be created'))
    monkeypatch.setattr(sys, 'argv', ['x', 'run', '--registration', str(path), '--registration-sha256', r.sha(raw),
                                      '--enable-reviewed-source-only-stop-treatment'])
    with pytest.raises(r.Stop, match='RUNTIME_DEPENDENCY_CHECK'):
        r.main()
    assert seen == [V2] and not (tmp_path / '.local').exists()
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line['reason'] == 'RUNTIME_DEPENDENCY_CHECK' and line['cleanup'] == 'NOT_STARTED'


def test_historical_versions_do_not_gate_on_the_new_check(tmp_path, monkeypatch):
    from tests.test_discovery_three_council_isolation import registration as v1_registration
    scrub_credentials(monkeypatch)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    reg = v1_registration()
    raw = r.canonical(reg)
    path = tmp_path / 'reg.json'
    path.write_bytes(raw)
    monkeypatch.setattr(r, 'validate', lambda value: value)
    monkeypatch.setattr(r, 'runtime_check', lambda version: pytest.fail('V1 must not run the V2 gate'))

    class Stopper(Exception):
        pass

    def memory(**k):
        raise Stopper
    monkeypatch.setattr(r, 'OperationalMemory', memory)
    monkeypatch.setattr(sys, 'argv', ['x', 'run', '--registration', str(path), '--registration-sha256', r.sha(raw),
                                      '--enable-reviewed-source-only-stop-treatment'])
    assert r.main() == 1            # reaches the unchanged V1 path: memory enforcement unavailable
    assert (tmp_path / '.local/state/propertyaigent' / reg['release_id']).exists()


def test_the_v2_launcher_runs_the_check_in_its_own_interpreter_before_exec():
    script = (ROOT / 'docs/design/execution-budget-20261026/owner-launch.sh').read_text()
    check = script.index('runtime-check --version THREE_COUNCIL_SOURCE_RELEASE_V2')
    assert script.index('storage-controller-venv/bin/python', script.index('report=$(')) < check
    assert check < script.index('exec systemd-run') and 'RUNTIME_DEPENDENCY_CHECK_FAILED' in script
    v1 = (ROOT / 'docs/design/four-council-release-20261022/owner-launch.sh').read_text()
    assert 'runtime-check' not in v1
