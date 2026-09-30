import signal
import pytest
from verification.mixed_pg.pause_control import PauseControl


def test_real_marker_signals_once_despite_echo_and_repetition():
    calls = []
    control = PauseControl('stockport', True, lambda *args: calls.append(args))
    for line in ['[stockport] [mixed-pause] 147\n',
                 '  error=[mixed-pause] 147\n',
                 '[stockport] [mixed-pause] 147\n',
                 '[stockport] [mixed-pause] 148\n']:
        control.observe(line)
    assert calls == [(147, signal.SIGKILL)]
    assert control.killed_pid == 147


@pytest.mark.parametrize('line', [
    '  error=[mixed-pause] 147\n', '[bury] [mixed-pause] 147\n',
    '[stockport] [mixed-pause] 0\n', '[stockport] [mixed-pause] -1\n',
    '[stockport] [mixed-pause] 147 extra\n',
])
def test_non_readiness_lines_never_signal(line):
    calls = []
    control = PauseControl('stockport', True, lambda *args: calls.append(args))
    control.observe(line)
    assert calls == [] and control.killed_pid is None


def test_unexpected_pause_fails_without_signal():
    calls = []
    control = PauseControl('stockport', False, lambda *args: calls.append(args))
    with pytest.raises(AssertionError, match='Unexpected child pause'):
        control.observe('[stockport] [mixed-pause] 147\n')
    assert calls == [] and control.killed_pid is None


def test_missing_child_is_not_hidden():
    def missing(*args):
        raise ProcessLookupError('missing child')
    control = PauseControl('stockport', True, missing)
    with pytest.raises(ProcessLookupError, match='missing child'):
        control.observe('[stockport] [mixed-pause] 147\n')
    assert control.killed_pid is None
