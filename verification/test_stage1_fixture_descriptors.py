"""Behavioural controls for immediate application versus fixture FD ownership."""
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch

import pytest

from verification.stage1_fixture_descriptors import AccountedFixtureServer, descriptor_snapshot


@pytest.fixture
def resources():
    server = AccountedFixtureServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
    client = socket.create_connection(server.server_address)
    baseline = descriptor_snapshot()
    request, _ = server.get_request()
    yield server, client, request, baseline
    if request in server._requests:
        server.shutdown_request(request)
    client.close()
    server.server_close()


def test_fixture_close_is_synchronised(resources):
    server, _, request, baseline = resources
    entered = threading.Event()
    real_wait = server._ownership.wait_for

    def wait(predicate, timeout):
        entered.set()
        return real_wait(predicate, timeout)

    def close():
        assert entered.wait(2)
        server.shutdown_request(request)

    worker = threading.Thread(target=close)
    worker.start()
    with patch.object(server._ownership, 'wait_for', wait):
        server.assert_released(baseline)
    worker.join(2)
    assert not worker.is_alive()
    assert request.fileno() == -1
    assert descriptor_snapshot() == baseline


@pytest.mark.parametrize('close_during_wait', [False, True])
def test_application_pipe_leak_fails_before_fixture_wait(resources, close_during_wait):
    server, _, _, baseline = resources
    pipe = list(os.pipe())

    def forbidden_wait(*args, **kwargs):
        if close_during_wait:
            for fd in pipe:
                os.close(fd)
            pipe.clear()
        raise AssertionError('Application leak reached fixture wait')

    try:
        with patch.object(server._ownership, 'wait_for', side_effect=forbidden_wait) as wait:
            with pytest.raises(AssertionError, match='Document process/custodian descriptor leak'):
                server.assert_released(baseline)
            wait.assert_not_called()
    finally:
        for fd in pipe:
            os.close(fd)


def test_same_count_different_resource_fails(resources):
    server, _, _, baseline = resources
    altered = set(baseline)
    original = next(iter(altered))
    altered.remove(original)
    altered.add((*original[:-1], 'different resource'))
    with pytest.raises(AssertionError, match='descriptor leak'):
        server.assert_released(altered)


def test_stale_fixture_identity_is_rejected(resources):
    server, _, request, baseline = resources
    original = server._requests[request]
    server._requests[request] = (*original[:-1], 'stale socket')
    try:
        with pytest.raises(AssertionError, match='Stale fixture ownership'):
            server.assert_released(baseline)
    finally:
        server._requests[request] = original


def test_repeated_fixture_accounting(resources):
    server, client, request, baseline = resources
    server.shutdown_request(request)
    server.assert_released(baseline)
    for _ in range(5):
        extra = socket.create_connection(server.server_address)
        accepted, _ = server.get_request()
        server.shutdown_request(accepted)
        extra.close()
        server.assert_released(baseline)


def test_busy_fixture_registry_cannot_hide_delayed_application_cleanup(resources):
    server, _, _, baseline = resources
    held = threading.Event()
    release = threading.Event()
    pipe = list(os.pipe())

    def hold():
        with server._ownership:
            held.set()
            assert release.wait(5)
            for fd in pipe:
                os.close(fd)

    worker = threading.Thread(target=hold)
    worker.start()
    assert held.wait(2)
    started = time.monotonic()
    try:
        with pytest.raises(AssertionError, match='Fixture ownership accounting unavailable'):
            server.assert_released(baseline)
        assert time.monotonic() - started < 1
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
