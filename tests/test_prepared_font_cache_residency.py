"""Residency classification used by the real-Chromium fixture: incomplete data is never COLD.

A fake measurement function is injected, so no file's page-cache state is read or changed.
"""
from pathlib import Path
import pytest
from tests.four_council_release_fixture_cli import residency


def tree(tmp_path, names=('a', 'b')):
    root = tmp_path / 'set'; root.mkdir()
    for n in names:(root / n).write_bytes(b'x' * 100)
    return root


def cold(path):return 100, 0
def warm(path):return 100, 100


def test_complete_cold_and_warm_measurements_classify(tmp_path):
    root = tree(tmp_path)
    assert residency({'s': root}, measure=cold)['class'] == 'COLD'
    assert residency({'s': root}, measure=warm)['class'] == 'WARM'
    other = tmp_path / 'other'; other.mkdir()
    value = residency({'s': root, 't': tree(other)}, measure=lambda p: (100, 50))
    assert value['class'] == 'PARTIAL' and value['complete']


@pytest.mark.parametrize('case', ['missing_root', 'empty_set', 'failed_file', 'all_failed', 'zero_bytes', 'no_sets'])
def test_incomplete_measurements_never_qualify_as_cold(tmp_path, case):
    root = tree(tmp_path)
    if case == 'missing_root':sets = {'s': root, 'gone': tmp_path / 'absent'}
    elif case == 'empty_set':empty = tmp_path / 'empty'; empty.mkdir(); sets = {'s': root, 'e': empty}
    elif case == 'zero_bytes':(root / 'a').write_bytes(b''); (root / 'b').write_bytes(b''); sets = {'s': root}
    elif case == 'no_sets':sets = {}
    else:sets = {'s': root}
    def measure(path):
        if case == 'all_failed' or (case == 'failed_file' and path.name == 'b'):raise PermissionError('unreadable')
        return (0, 0) if case == 'zero_bytes' else (100, 0)
    value = residency(sets, measure=measure)
    assert value['class'] == 'INCOMPLETE' and value['complete'] is False


def test_coverage_and_uncertainty_are_reported(tmp_path):
    root = tree(tmp_path, names=('a', 'b', 'c', 'd'))
    def measure(path):
        if path.name == 'd':raise OSError('mincore failed')
        return 100, 0
    value = residency({'fonts': root}, measure=measure)
    entry = value['sets']['fonts']
    assert value['class'] == 'INCOMPLETE'
    assert entry['files'] == 4 and entry['measured'] == 3 and entry['failed'] == 1 and entry['coverage'] == 0.75
    assert entry['errors'] == ['OSError'] and entry['complete'] is False


def test_unreadable_directory_is_incomplete(tmp_path):
    root = tree(tmp_path); locked = root / 'locked'; locked.mkdir(); (locked / 'f').write_bytes(b'x')
    locked.chmod(0o000)
    try:
        value = residency({'s': root}, measure=cold)
    finally:
        locked.chmod(0o755)
    assert value['class'] == 'INCOMPLETE' and 'WALK_ERROR' in value['sets']['s']['errors']


def test_symlinked_file_is_measured_once_at_its_target(tmp_path):
    root = tree(tmp_path, names=('a',)); (root / 'alias').symlink_to(root / 'a')
    calls = []
    value = residency({'s': root}, measure=lambda p: (calls.append(p) or (100, 0)))
    assert len(calls) == 1 and value['sets']['s']['files'] == 2 and value['class'] == 'COLD'


def test_symlinked_subdirectory_is_incomplete(tmp_path):
    root = tree(tmp_path); other = tmp_path / 'elsewhere'; other.mkdir(); (other / 'f').write_bytes(b'x')
    (root / 'linked').symlink_to(other, target_is_directory=True)
    value = residency({'s': root}, measure=cold)
    assert value['class'] == 'INCOMPLETE' and 'SYMLINKED_DIR' in value['sets']['s']['errors']


def test_value_error_during_measurement_is_incomplete(tmp_path):
    root = tree(tmp_path)
    def measure(path):
        if path.name == 'a':raise ValueError('cannot mmap a truncated file')
        return 100, 0
    assert residency({'s': root}, measure=measure)['class'] == 'INCOMPLETE'
