"""Independent deadline enforcement; never uses the database or owner lock.

The discovery supervisor remains the recorded owner. This small subprocess
only receives process-group IDs and deadlines. A stalled commit cannot stall it.
"""
from __future__ import annotations
import json
import os
import select
import signal
import subprocess
import sys
import time
import threading


def parent_deadlines(started, start_budget, council_deadline, invocation_deadline):
    cooperative_stop = min(started + start_budget + 60, council_deadline, invocation_deadline)
    hard_stop = min(cooperative_stop + 10, council_deadline + 20, invocation_deadline)
    return cooperative_stop, hard_stop


class DiscoveryWatchdog:
    def __init__(self, deadline):
        self.deadline = deadline
        self.process = None
        self.control_lock = threading.Lock()

    def __enter__(self):
        if os.name != 'posix':
            raise RuntimeError('discovery deadline enforcement requires POSIX')
        self.process = subprocess.Popen(
            [sys.executable, '-u', '-m', __name__, str(os.getpid()), str(self.deadline)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=True)
        os.set_blocking(self.process.stdin.fileno(), False)
        try:
            self._ack()
        except BaseException:
            # No child can have been admitted yet.
            self.process.kill()
            self.process.wait(timeout=3)
            self.process.stdin.close()
            self.process.stdout.close()
            raise
        return self

    def _ack(self):
        remaining = min(2, self.deadline - time.monotonic())
        if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
            raise RuntimeError('watchdog acknowledgement deadline exceeded')
        if os.read(self.process.stdout.fileno(), 1) != b'!':
            raise RuntimeError('watchdog unavailable')

    def send(self, **message):
        # Messages are small and bounded (one active council); broken pipe is
        # fatal, not permission to continue without supervision.
        with self.control_lock:
            if time.monotonic() >= self.deadline:
                raise RuntimeError('invocation deadline exhausted')
            payload = (json.dumps(message) + '\n').encode()
            if os.write(self.process.stdin.fileno(), payload) != len(payload):
                raise RuntimeError('watchdog command incomplete')
            self._ack()

    def register(self, pid, deadline):
        self.send(group=pid, deadline=min(deadline, self.deadline))

    def unregister(self, pid):
        self.send(remove=pid)

    def __exit__(self, *args):
        try:
            self.send(done=True)
            self.process.stdin.close()
            self.process.wait(timeout=3)
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=3)
            self.process.stdout.close()


def gated_exec(fd, deadline, command):
    """No application imports/work until registration is positively acknowledged.

    Parent death before release closes the sole write end: EOF means exit, not
    permission to start. The read fd is closed before exec; owner fd is retained.
    """
    remaining = deadline - time.monotonic()
    allowed = remaining > 0 and select.select([fd], [], [], remaining)[0]
    token = os.read(fd, 1) if allowed else b''
    os.close(fd)
    if token != b'!' or time.monotonic() >= deadline:
        raise SystemExit(1)
    os.execvpe(command[0], command, os.environ)


def monitor(parent, deadline):
    groups = {}
    buffer = b''
    completed = False
    try:
        os.write(1, b'!')
        while True:
            remaining = min([deadline, *groups.values()]) - time.monotonic()
            ready, _, _ = select.select([0], [], [], max(0, remaining))
            if time.monotonic() >= min([deadline, *groups.values()]):
                return  # expiry wins over queued deadline extensions/completion
            if not ready:
                continue
            chunk = os.read(0, 4096)
            if not chunk:
                return
            buffer += chunk
            while b'\n' in buffer:
                if time.monotonic() >= min([deadline, *groups.values()]):
                    return
                line, buffer = buffer.split(b'\n', 1)
                message = json.loads(line)
                if message.get('done'):
                    if groups:
                        return
                    os.write(1, b'!')
                    completed = True
                    return
                if 'group' in message:
                    groups[message['group']] = min(message['deadline'], deadline)
                if 'remove' in message:
                    groups.pop(message['remove'], None)
                os.write(1, b'!')
    finally:
        if not completed:
            # Stop new work first. Parent relationship avoids signalling a reused
            # parent PID after EOF; group IDs are retained until explicit cleanup.
            if os.getppid() == parent:
                try: os.kill(parent, signal.SIGKILL)
                except ProcessLookupError: pass
            for group in groups:
                try: os.killpg(group, signal.SIGKILL)
                except ProcessLookupError: pass
            try:
                os.set_blocking(2, False)
                os.write(2, b'[discovery-watchdog] deadline/control failure; final database status unverified; owned rows require positive termination reconciliation\n')
            except OSError:
                pass


if __name__ == '__main__':
    if sys.argv[1] == 'gate':
        gated_exec(int(sys.argv[2]), float(sys.argv[3]), sys.argv[4:])
    else:
        monitor(int(sys.argv[1]), float(sys.argv[2]))
