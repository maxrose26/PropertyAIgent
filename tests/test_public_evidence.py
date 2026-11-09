"""No raw source, field, event or path may reach a PA-D002 public summary."""
import json

import pytest

from app.ingestion.ledger import Denied
from app.ingestion.public_evidence import project_public_summary

SECRET = 'private-address-and-raw-proposal-MUST-NOT-PUBLISH'
PAYLOAD = {
    'status': 'RETAINED_AND_SCREENED', 'coverage_advance': False,
    'authority_closure': 'INVALIDATED',
    'scopes': [{'council': 'tameside', 'status': 'RETAINED_AND_SCREENED',
                'records': 21, 'raw': SECRET}],
    'backlog': {'records': [{'address': SECRET, 'source_url': SECRET}]},
    'failure': None, 'events': [{'full': SECRET}], 'path': SECRET,
}
EVENTS = [{'source_body': SECRET, 'path': SECRET, 'credentials': SECRET}]
RAW = json.dumps(PAYLOAD).encode()
EVENT_RAW = json.dumps(EVENTS).encode()


def test_summary_is_status_counts_digests_only_and_never_contains_private_fields():
    result = project_public_summary(PAYLOAD, original_raw=RAW, original_events=EVENT_RAW)
    body = json.dumps(result, sort_keys=True)
    assert SECRET not in body
    for field in ('backlog', 'events', 'path', 'raw', 'source_url', 'address', 'failure'):
        assert field not in result
    assert result['total_records'] == 21 and result['scope_count'] == 1
    assert result['coverage_advance'] is False
    assert result['private_result_sha256'] and result['private_events_sha256']
    assert len(result['private_result_sha256']) == 64


@pytest.mark.parametrize('status', [
    'INCOMPLETE', 'STOP_RECONCILE_NO_RETRY',
])
def test_blocked_or_incomplete_never_promotes_coverage(status):
    value = {**PAYLOAD, 'status': status, 'failure': SECRET}
    result = project_public_summary(value, original_raw=RAW, original_events=EVENT_RAW)
    assert result['status'] == status and result['failure_present'] is True
    assert result['coverage_advance'] is False


@pytest.mark.parametrize('mutate', [
    lambda p: {**p, 'status': SECRET},
    lambda p: {**p, 'coverage_advance': True},
    lambda p: {**p, 'coverage_advance': 0},
    lambda p: {**p, 'authority_closure': SECRET},
    lambda p: {**p, 'scopes': [{'council': SECRET, 'status': 'INCOMPLETE', 'records': 5}]},
    lambda p: {**p, 'scopes': [{'council': 'unknowncity', 'status': 'INCOMPLETE', 'records': 5}]},
    lambda p: {**p, 'scopes': [{'council': 'tameside', 'status': SECRET, 'records': 5}]},
    lambda p: {**p, 'scopes': [{'council': 'tameside', 'status': 'INCOMPLETE', 'records': True}]},
    lambda p: {**p, 'scopes': [{'council': 'tameside', 'status': 'INCOMPLETE', 'records': 61}]},
    lambda p: {**p, 'scopes': [*p['scopes']] * 3},
])
def test_unknown_or_injected_metadata_is_refused(mutate):
    with pytest.raises(Denied):
        project_public_summary(mutate(PAYLOAD), original_raw=RAW, original_events=EVENT_RAW)


@pytest.mark.parametrize('raw,events', [
    (b'x' * (2 * 1024 * 1024 + 1), EVENT_RAW),
    (RAW, b'x' * (128 * 1024 + 1)),
    ('not-bytes', EVENT_RAW),
])
def test_bounded_private_digest_inputs(raw, events):
    with pytest.raises(Denied, match='PUBLIC_SUMMARY_INPUT_BOUND'):
        project_public_summary(PAYLOAD, original_raw=raw, original_events=events)

# These use the existing production publisher against a deterministic in-memory
# gh API transport: NO GitHub network call, branch write, or raw publication.
# The actual remote Git commit/readback remains a separate acceptance gate.
def _fake_publication_transport(*, corrupt_readback=False):
    import base64
    import hashlib
    import subprocess

    class FakeGitAPI:
        def __init__(self):
            self.head = 'a' * 40
            self.blobs = {}
            self.tree = None
            self.commit = None
            self.changes = []

        def __call__(self, command, *, input, stdout, stderr, timeout):
            assert command[:3] == ['gh', 'api', '--method']
            method, path = command[3], command[4]
            assert timeout == 5
            body = json.loads(input) if input is not None else None
            self.changes.append((method, path))
            if method == 'GET' and '/git/ref/heads/' in path:
                reply = {'object': {'sha': self.head}}
            elif method == 'GET' and '/git/commits/' in path:
                reply = {'tree': {'sha': 'b' * 40}}
            elif method == 'POST' and path.endswith('/git/blobs'):
                raw = base64.b64decode(body['content'])
                sha = hashlib.sha1(b'blob ' + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()
                self.blobs[sha] = raw
                reply = {'sha': sha}
            elif method == 'POST' and path.endswith('/git/trees'):
                assert body['base_tree'] == 'b' * 40
                self.tree = body['tree']
                reply = {'sha': 'c' * 40}
            elif method == 'POST' and path.endswith('/git/commits'):
                assert body['parents'] == ['a' * 40]
                self.commit = body
                reply = {'sha': 'd' * 40}
            elif method == 'PATCH' and '/git/refs/heads/' in path:
                assert body == {'sha': 'd' * 40, 'force': False}
                assert self.head == 'a' * 40
                self.head = body['sha']
                reply = {'ref': path}
            elif method == 'GET' and '/contents/' in path:
                assert path.endswith('?ref=' + 'd' * 40)
                name = path.split('/contents/', 1)[1].split('?ref=', 1)[0]
                entry = next(x for x in self.tree if x['path'] == name)
                raw = self.blobs[entry['sha']]
                if corrupt_readback:
                    raw += b'CORRUPTED'
                reply = {'sha': entry['sha'],
                         'content': base64.b64encode(raw).decode()}
            else:
                raise AssertionError('unexpected offline Git route: ' + method + ' ' + path)
            return subprocess.CompletedProcess(command, 0, json.dumps(reply).encode(), b'')

    return FakeGitAPI()


def test_safe_summary_only_uses_existing_git_commit_and_exact_path_readback():
    from verification.ingestion_storage.operational_publication import GitHub, canonical
    events = []
    fake = _fake_publication_transport()
    publisher = GitHub(lambda kind, payload: events.append((kind, payload)),
                       lambda: None, runner=fake, bound=12)
    public = canonical(project_public_summary(
        PAYLOAD, original_raw=RAW, original_events=EVENT_RAW))
    directory = ('docs/design/ingestion-operational-execution-daily-intake/'
                 + 'offline-only/' + 'e' * 32 + '/final')
    head = publisher.publish({'result-before-publication.json': public},
                             directory=directory, expected_head='a' * 40)
    assert head == fake.head == 'd' * 40
    assert fake.commit['tree'] == 'c' * 40
    assert len(fake.tree) == 1
    assert fake.tree[0]['path'] == directory + '/result-before-publication.json'
    assert set(fake.blobs.values()) == {public}
    assert SECRET.encode() not in public
    assert len([e for e in events if e[0] == 'publication_verified']) == 1
    assert all('source.json' not in route and 'events-before-publication.json' not in route
               for _, route in fake.changes)


def test_public_git_readback_corruption_refuses_verified_publication():
    from verification.ingestion_storage.operational_publication import GitHub, Uncertain
    fake = _fake_publication_transport(corrupt_readback=True)
    events = []
    publisher = GitHub(lambda kind, payload: events.append(kind), lambda: None,
                       runner=fake, bound=12)
    with pytest.raises(Uncertain, match='PUBLICATION_BYTES_READBACK'):
        publisher.publish({'result-before-publication.json': b'{"schema":"test"}'},
                          directory='docs/design/ingestion-operational-execution-daily-intake/offline-only/final',
                          expected_head='a' * 40)
    assert fake.head == 'd' * 40  # uncertain AFTER commit, never claim failure rolled back
    assert 'publication_verified' not in events


def test_public_git_head_race_refuses_before_mutation():
    from verification.ingestion_storage.operational_publication import GitHub, Uncertain
    fake = _fake_publication_transport()
    fake.head = 'f' * 40
    publisher = GitHub(lambda *_: None, lambda: None, runner=fake, bound=12)
    with pytest.raises(Uncertain, match='EVIDENCE_HEAD_MOVED_RECONCILE'):
        publisher.publish({'result-before-publication.json': b'{}'},
                          directory='docs/design/ingestion-operational-execution-daily-intake/offline-only/final',
                          expected_head='a' * 40)
    assert not fake.blobs and fake.tree is None and fake.commit is None
