"""One-shot interruption of an explicitly ready recorded council child."""
import re
import signal


class PauseControl:
    def __init__(self, council, enabled, send_signal):
        self.marker = re.compile(r'\[' + re.escape(council) + r'\] \[mixed-pause\] ([1-9][0-9]*)\n?')
        self.enabled = enabled
        self.send_signal = send_signal
        self.killed_pid = None

    def observe(self, line):
        match = self.marker.fullmatch(line)
        if match is None or self.killed_pid is not None:
            return
        if not self.enabled:
            raise AssertionError('Unexpected child pause outside interruption slice')
        pid = int(match.group(1))
        # A failed first signal is evidence of a broken interruption; propagate it.
        self.send_signal(pid, signal.SIGKILL)
        self.killed_pid = pid
