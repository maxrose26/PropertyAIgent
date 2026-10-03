"""Account for fixture sockets without delaying application cleanup assertions."""
import os
import threading
from http.server import ThreadingHTTPServer


def descriptor_identity(fd):
    path = f'/proc/self/fd/{fd}'
    stat = os.stat(path)
    return (int(fd), stat.st_dev, stat.st_ino, stat.st_mode, os.readlink(path))


def descriptor_snapshot():
    identities = set()
    for fd in os.listdir('/proc/self/fd'):
        try:
            identities.add(descriptor_identity(fd))
        except FileNotFoundError:
            # listdir's own enumeration descriptor has already been closed.
            continue
    return identities


class AccountedFixtureServer(ThreadingHTTPServer):
    """Keep accepted sockets owned until shutdown_request actually closes them."""

    def __init__(self, *args, **kwargs):
        self._ownership = threading.Condition()
        self._requests = {}
        super().__init__(*args, **kwargs)

    def get_request(self):
        with self._ownership:
            request, address = super().get_request()
            self._requests[request] = descriptor_identity(request.fileno())
            return request, address

    def shutdown_request(self, request):
        with self._ownership:
            super().shutdown_request(request)
            assert request.fileno() == -1, 'Fixture socket did not close'
            del self._requests[request]
            self._ownership.notify_all()

    def assert_released(self, baseline):
        assert self._ownership.acquire(blocking=False), 'Fixture ownership accounting unavailable'
        try:
            owned = set()
            for request, identity in self._requests.items():
                assert descriptor_identity(request.fileno()) == identity, 'Stale fixture ownership'
                owned.add(identity)
            current = descriptor_snapshot()
            assert owned <= current, 'Fixture ownership missing from descriptor snapshot'
            assert current - owned == baseline, 'Document process/custodian descriptor leak'
            # Only fixture shutdown may complete here. Application resources were
            # required to match baseline above, before any wait.
            assert self._ownership.wait_for(lambda: not self._requests, timeout=2), 'Fixture shutdown incomplete'
            assert descriptor_snapshot() == baseline, 'Document process/custodian descriptor leak'
        finally:
            self._ownership.release()
