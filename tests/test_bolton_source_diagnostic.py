import json
import signal
from unittest.mock import patch

import pytest
from verification.discovery import bolton_diagnostic as diagnostic
from tests.test_discovery_idox_window import FORM, page, Response


def perform(tmp_path, bodies, fail_archive=False):
    root = tmp_path / 'private'
    root.mkdir(mode=0o700)
    calls = []
    responses = [Response(body) for body in bodies]
    def dispatch(method, url, **kwargs):
        assert kwargs['allow_redirects'] is False
        calls.append((method, url, kwargs.get('data')))
        return responses[len(calls)-1]
    if fail_archive:
        def failed(self, *args, **kwargs):
            self.failed = True
        with patch.object(diagnostic.PrivateResponseBodies, 'record', failed):
            result = diagnostic.run(dispatch, root)
    else:
        result = diagnostic.run(dispatch, root)
    assert all(r.closed for r in responses[:len(calls)])
    return result, calls, root


def echo():
    return FORM.replace(b'name="date(applicationReceivedStart)" value=""', b'name="date(applicationReceivedStart)" value="03/11/2026"').replace(b'name="date(applicationReceivedEnd)" value=""', b'name="date(applicationReceivedEnd)" value="05/11/2026"')


@pytest.mark.parametrize('sorted_body', [page(), b'<html><body>alternate SECRET signal</body></html>', b'<html>truncated SECRET'])
def test_retains_originals_without_completeness_claim(tmp_path, sorted_body):
    result, calls, root = perform(tmp_path, [FORM, page(), sorted_body, echo()])
    assert result['status'] == 'FOUR_RESPONSES_RETAINED'
    assert result['coverage'] == 'NOT_ESTABLISHED'
    assert len(calls) == 4 and result['retries'] == 0
    assert b'03%2F11%2F2026' in calls[1][2]
    assert (root / '03-SORT.body').read_bytes() == sorted_body
    assert 'SECRET' not in json.dumps(result) and 'fixture' not in json.dumps(result)
    assert diagnostic.inspect(root)['status'] == result['status']


def test_failed_retention_stops_before_search(tmp_path):
    result, calls, _ = perform(tmp_path, [FORM], True)
    assert result['status'] == 'INCOMPLETE' and len(calls) == 1


def test_wrong_echo_never_finishes(tmp_path):
    result, calls, root = perform(tmp_path, [FORM, page(), page(), FORM])
    assert result['status'] == 'INCOMPLETE' and len(calls) == 4
    with pytest.raises(ValueError):
        diagnostic.inspect(root)


def test_tampering_refused(tmp_path):
    _, _, root = perform(tmp_path, [FORM, page(), page(), echo()])
    (root / '03-SORT.body').write_bytes(b'changed')
    with pytest.raises(ValueError):
        diagnostic.inspect(root)


def test_timeout_not_retried(tmp_path):
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    calls = []
    def dispatch(*args, **kwargs):
        calls.append(1)
        raise TimeoutError('SECRET')
    result = diagnostic.run(dispatch, root)
    assert len(calls) == 1 and result['status'] == 'INCOMPLETE'
    assert 'SECRET' not in json.dumps(result)


def test_hard_deadline_interrupts_and_restores():
    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(TimeoutError):
        with diagnostic.source_deadline():
            signal.raise_signal(signal.SIGALRM)
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) == previous


def test_default_cli_is_inspection_only(tmp_path, capsys):
    with patch('sys.argv', ['diagnostic', '--private-directory', str(tmp_path)]), patch.object(diagnostic, 'observe', side_effect=AssertionError('network')):
        assert diagnostic.main() == 1
    assert 'DIAGNOSTIC_REFUSED' in capsys.readouterr().out


def test_redirect_not_followed(tmp_path):
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    response = Response(b''); response.status_code = 302
    response.headers = {'Content-Type': 'text/html', 'Location': diagnostic.CONFIG.form_url}
    calls = []
    def dispatch(*args, **kwargs):
        calls.append(1)
        return response
    result = diagnostic.run(dispatch, root)
    assert result['status'] == 'INCOMPLETE' and len(calls) == 1 and response.closed


def test_oversized_response_refuses(tmp_path):
    result, calls, _ = perform(tmp_path, [b'x' * 500001])
    assert result['status'] == 'INCOMPLETE' and len(calls) == 1


def test_page_and_fifth_attempt_refused_without_dispatch(tmp_path):
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    def forbidden(*args, **kwargs):
        raise AssertionError('dispatch')
    boundary = diagnostic.DiagnosticBoundary(forbidden, diagnostic.PrivateResponseBodies(root))
    boundary.phase = 'PAGE'; boundary.next_url = diagnostic.CONFIG.form_url
    with pytest.raises(BoundaryFailure):
        boundary.retrieve('GET', boundary.next_url)
    assert boundary.requests == 0
    boundary.phase = 'FORM'; boundary.requests = 4
    with pytest.raises(BoundaryFailure):
        boundary.retrieve('GET', diagnostic.CONFIG.form_url)
    assert boundary.requests == 4


def test_observe_deadline_closes_session_without_real_network(tmp_path):
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    import requests
    with patch.object(requests, 'Session') as factory:
        session = factory.return_value.__enter__.return_value
        session.request.side_effect = lambda *a, **k: signal.raise_signal(signal.SIGALRM)
        result = diagnostic.observe(root)
        assert session.request.call_count == 1
        assert session.trust_env is False
        assert session.request.call_args.kwargs['allow_redirects'] is False
        factory.return_value.__exit__.assert_called_once()
    assert result['status'] == 'INCOMPLETE' and result['cleanup'] == 'SESSION_BOUNDARY_CLOSED'
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
