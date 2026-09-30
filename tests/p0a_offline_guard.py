"""Offline harness for affected legacy suites, including localhost-only fixtures.

Use PYTHONPATH=tests:. python -m pytest -p p0a_offline_guard ... .
SSL trust discovery is stubbed because several legacy download fixtures only
mock GET, leaving their independent HEAD certificate probe live. Document
folders are isolated before legacy tests globally mock Path.stat.
"""
import socket
import pytest

_original = socket.socket.connect

def _offline(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        # Only the HTTP server created by a legacy synthetic streaming test.
        # Environment proxy traffic is forbidden, even when proxy is local.
        if address[0] not in ('127.0.0.1', '::1'):
            raise AssertionError('offline validation forbids external network connections')
    return _original(self, address)

def pytest_sessionstart(session):
    socket.socket.connect = _offline

@pytest.fixture(autouse=True)
def isolated_legacy_io(monkeypatch, tmp_path):
    import requests
    try:
        import httpx
    except ImportError:
        httpx = None
    import app.pipeline.run_weekly as pipeline
    import app.extraction.pdf_text as pdf
    def forbid(*args, **kwargs):
        raise AssertionError('offline validation forbids external HTTP requests')
    original = requests.sessions.Session.request
    def local_only(self, method, url, *args, **kwargs):
        from urllib.parse import urlparse
        if urlparse(url).hostname not in ('127.0.0.1', 'localhost', '::1'):
            return forbid()
        kwargs['proxies'] = {'http': None, 'https': None}
        self.trust_env = False
        return original(self, method, url, *args, **kwargs)
    monkeypatch.setattr(requests.sessions.Session, 'request', local_only)
    if httpx is not None:
        monkeypatch.setattr(httpx.Client, 'send', forbid)
    monkeypatch.setattr(pdf, 'get_verify_bundle_for_host', lambda host: True)
    directory = tmp_path/'documents'
    directory.mkdir()
    monkeypatch.setattr(pipeline, 'document_dir', lambda *args: directory)
