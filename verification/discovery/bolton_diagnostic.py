"""Inactive source-only Bolton evidence capture; never intake or settlement."""
import argparse
from contextlib import contextmanager
from datetime import date
import json
import signal
import threading
import time
from urllib.parse import urlencode

from .idox_window import WindowBoundary, WindowConfig
from .idox_sort import sort_payload
from .four_council_proof import PrivateResponseBodies, validate_private_responses
from verification.stage26b_l1.request_boundary import Budget

CONFIG = WindowConfig('bolton', 'RECEIVED', date(2026, 11, 3), date(2026, 11, 5), 0)
OPERATIONS = ('FORM', 'SEARCH', 'SORT', 'REFINE')


class DiagnosticBoundary(WindowBoundary):
    def __init__(self, dispatch, archive):
        super().__init__(dispatch, CONFIG, response_evidence=archive.record)
        self.budget = Budget(requests=4, per_reference=4, total_bytes=2000000,
                             response_bytes=500000, seconds=45)

    def validate(self, method, url, body=None):
        if self.phase not in OPERATIONS:
            self.budget.reject('PARTIAL_RETRIEVAL', 'operation refused', True)
        return super().validate(method, url, body)

    def request(self, *args, **kwargs):
        if self.requests >= 4:
            self.budget.reject('PARTIAL_RETRIEVAL', 'request ceiling', True)
        return super().request(*args, **kwargs)


def inspect(root):
    value = validate_private_responses(root)
    if [(e['operation'], e['sequence']) for e in value['entries']] != list(zip(OPERATIONS, range(1, 5))):
        raise ValueError('INCOMPLETE_OPERATION_SEQUENCE')
    return {'status': 'FOUR_RESPONSES_RETAINED', 'coverage': 'NOT_ESTABLISHED',
            'inspection': 'ARCHIVE_INTEGRITY_ONLY_SCOPE_NOT_REESTABLISHED',
            'responses': [{'operation': e['operation'], 'bytes': e['retained_bytes'],
                           'sha256': e['retained_sha256']} for e in value['entries']]}


def run(dispatch, root):
    archive = PrivateResponseBodies(root)
    boundary = DiagnosticBoundary(dispatch, archive)
    result = {'status': 'INCOMPLETE', 'coverage': 'NOT_ESTABLISHED'}

    def retrieve(method, url, body=None):
        response = boundary.retrieve(method, url, body)
        if archive.failed:
            raise ValueError('RETENTION_FAILED')
        return response

    try:
        form = retrieve('GET', CONFIG.form_url)
        target, fields = CONFIG.payload(form)
        for operation in ('SEARCH', 'SORT'):
            boundary.phase = operation
            boundary.admitted_post = target
            boundary.admitted_body = urlencode(fields).encode()
            body = retrieve('POST', target, boundary.admitted_body)
            fields.clear()
            boundary.admitted_body = None
            if operation == 'SEARCH':
                target, fields = sort_payload(body, CONFIG.base)
        boundary.phase = 'REFINE'
        echo = retrieve('GET', CONFIG.base + '/refineSearch.do?action=refine')
        CONFIG.payload(echo, echo=True)
        archive.finish()
        if archive.failed:
            raise ValueError('RETENTION_FAILED')
        result.update(inspect(root))
    except Exception:
        # Never publish exception text: it may contain source/form data.
        result['failure'] = 'DIAGNOSTIC_REFUSED'
    finally:
        boundary.admitted_body = None
        result['scope'] = {'council': 'bolton', 'semantics': 'RECEIVED',
                           'start': '2026-11-03', 'end': '2026-11-05'}
        boundary.close()
        result.update(physical_requests=boundary.requests, retries=boundary.retries,
                      bytes=boundary.received_bytes, cleanup='BOUNDARY_CLOSED')
    return result


@contextmanager
def source_deadline():
    """Interrupt blocking reads as well as transport calls; refuse unsafe nesting."""
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, 'setitimer'):
        raise RuntimeError('UNSUPPORTED_DEADLINE_RUNTIME')
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError('EXISTING_DEADLINE')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise TimeoutError('SOURCE_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 45)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def observe(root):
    # This function is prepared for separately approved execution only.
    import requests
    with source_deadline(), requests.Session() as session:
        session.trust_env = False
        session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))
        last = [None]
        def dispatch(method, url, **kwargs):
            if last[0] is not None:
                time.sleep(max(0, 0.4 - (time.monotonic() - last[0])))
            last[0] = time.monotonic()
            kwargs.pop('deadline', None)
            kwargs['timeout'] = (3, min(8, kwargs['timeout']))
            return session.request(method, url, **kwargs)
        result = run(dispatch, root)
    result['cleanup'] = 'SESSION_BOUNDARY_CLOSED'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-directory', required=True)
    parser.add_argument('--observe', action='store_true', help='Requires separate owner approval; makes council requests')
    args = parser.parse_args()
    try:
        result = observe(args.private_directory) if args.observe else inspect(args.private_directory)
    except Exception:
        result = {'status': 'INCOMPLETE', 'coverage': 'NOT_ESTABLISHED', 'failure': 'DIAGNOSTIC_REFUSED'}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'FOUR_RESPONSES_RETAINED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
