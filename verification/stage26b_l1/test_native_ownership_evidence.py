"""Validate the recorded native negative finding; does not rerun containment."""
import json
from pathlib import Path


def test_recorded_native_finding():
    result = json.loads(Path(__file__).with_name('native_ownership_result.json').read_text())
    cases = {row['case']: row for row in result['cases']}
    assert set(cases) == {'normal', 'exception', 'parser_failure', 'hung', 'child',
                          'grandchild', 'ignore_term', 'overflow', 'explicit_cancel', 'detach'}
    assert result['result'] == 'NO-GO'
    for row in cases.values():
        assert row['control_survived'] is True
        assert row['group_distinct_from_supervisor'] is True
        assert row['cleanup_verified'] is True
        assert row['remaining_fixture_processes'] == 0
        assert 0 < row['elapsed_seconds'] < 3
    for name, status in [('normal', 0), ('exception', 10), ('parser_failure', 11)]:
        assert cases[name]['worker_exit_status'] == status
        assert cases[name]['deadline_triggered'] is False
    for name in ('hung', 'child', 'grandchild', 'ignore_term'):
        assert cases[name]['deadline_triggered'] is True
        assert cases[name]['escaped_live_processes'] == 0
        assert cases[name]['ordinary_descendants_same_group'] is True
        assert cases[name]['worker_exit_status'] == -15
    assert cases['ignore_term']['forced_termination_attempted'] is True
    assert cases['overflow']['outcome'] == 'OUTPUT_OVERFLOW'
    assert cases['explicit_cancel']['outcome'] == 'CANCELLED'
    escaped = cases['detach']
    assert escaped['escaped_live_processes'] == 1
    assert escaped['ordinary_descendants_same_group'] is False
    assert escaped['graceful_termination_attempted'] is True
    assert escaped['forced_termination_attempted'] is True
    assert escaped['worker_exit_status'] == -9


def test_probe_has_no_application_or_network_import():
    import ast
    source = Path(__file__).with_name('native_ownership_probe.py').read_text()
    imports = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)
    assert imports <= {'ctypes', 'json', 'os', 'pathlib', 'resource', 'select',
                       'signal', 'tempfile', 'time', 'uuid'}
