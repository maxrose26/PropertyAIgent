"""Two fixed Oldham references; status-only audit, NEVER factual persistence.

HTTP-only verification mode reuses Idox's canonical summary table parser and
the accepted L1 assessment contract. No browser, assets, JS, generic discovery,
database connectivity, or model client is needed. JS-only portals fail closed.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import datetime as dt
import importlib.abc
import json
from pathlib import Path
import re
import socket
import sys
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from .request_boundary import Boundary, BoundaryFailure, Budget, Policy

VERSION = 'l1-oldham-actions-canary-v1'
REPOSITORY = 'maxrose26/PropertyAIgent'
BASE = 'https://planningpa.oldham.gov.uk/online-applications'
SEARCH = BASE + '/search.do?action=advanced&searchType=Application'
AUTHORITY = 'AUTHORISE_FAILSWORTH_SOUTHLINK_ONLY'
MAX_ARTIFACT = 16_384
CASES = (
    dict(site_id=28, application_id=42, reference='FUL/355686/26',
         status='Awaiting decision', decision=None, decision_issued_date=None,
         status_verified_at='2026-09-18'),
    dict(site_id=25, application_id=29, reference='FUL/355201/25',
         status='Awaiting decision', decision=None, decision_issued_date=None,
         status_verified_at='2026-09-10'),
)


class ImportFence(importlib.abc.MetaPathFinder):
    """ORM definitions are inert; production connection/provisioning is denied."""
    prefixes = ('app.db.session', 'app.pipeline.run_weekly', 'app.settings',
                'openai', 'anthropic', 'psycopg', 'psycopg2', 'supabase')
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == p or fullname.startswith(p + '.') for p in self.prefixes):
            raise BoundaryFailure('PARTIAL_RETRIEVAL', 'prohibited import')
        return None


@contextmanager
def offline_network_denial():
    """Real socket/DNS and Requests entry points denied, not merely unused."""
    patched = [(socket, 'getaddrinfo'), (socket.socket, 'connect'),
               (socket.socket, 'connect_ex'), (requests.Session, 'request')]
    saved = [(obj, name, getattr(obj, name)) for obj, name in patched]
    def denied(*args, **kwargs):
        raise BoundaryFailure('PARTIAL_RETRIEVAL', 'offline network denied')
    try:
        for obj, name, _ in saved: setattr(obj, name, denied)
        yield
    finally:
        for obj, name, value in saved: setattr(obj, name, value)


class OldhamBoundary(Boundary):
    """Verification-only form extension; generic Idox/Arcus unchanged."""
    def __init__(self, reference, budget, dispatch):
        if reference not in {c['reference'] for c in CASES}:
            raise ValueError('Not an authorised canary reference')
        super().__init__(Policy('oldham', reference, 'idox', BASE, SEARCH), budget, dispatch)

    def retrieve(self, method, url, body=None): return retrieve(self, method, url, body)
    def reject(self, outcome, reason): self.budget.reject(outcome, reason)

    def validate(self, method, url, body=None):
        # Public server-generated form nonces may be submitted, never exported.
        u = urlsplit(url)
        if method.upper() == 'POST' and url in (
                BASE + '/search.do', BASE + '/advancedSearchResults.do?action=firstPage'):
            self.budget.check()
            if self.closed or not isinstance(body, bytes) or len(body) > 65_536:
                self.budget.reject('PARTIAL_RETRIEVAL', 'invalid form')
            try: fields = parse_qs(body.decode('utf-8'), keep_blank_values=True, strict_parsing=True)
            except Exception: self.budget.reject('PARSER_FAILURE', 'invalid form encoding')
            if fields.get('searchCriteria.reference') != [self.policy.reference]:
                self.budget.reject('PARTIAL_RETRIEVAL', 'exact reference required')
            for key, values in fields.items():
                if len(values) != 1:
                    self.budget.reject('PARTIAL_RETRIEVAL', 'duplicate form field')
                if key == 'searchCriteria.reference': continue
                if key.startswith('searchCriteria.') and values == ['']: continue
                if key == 'action' and values == ['Search']: continue
                if key == 'searchType' and values == ['Application']: continue
                if key in ('_csrf', 'csrfToken', 'org.apache.struts.taglib.html.TOKEN') and re.fullmatch(r'[A-Za-z0-9_-]{1,256}', values[0]): continue
                self.budget.reject('PARTIAL_RETRIEVAL', 'unapproved form field')
            return
        # No assets whatsoever in this HTTP-only verification path.
        if u.path.rsplit('/', 1)[-1] not in ('search.do', 'advancedSearchResults.do', 'applicationDetails.do'):
            self.budget.reject('PARTIAL_RETRIEVAL', 'non-status route')
        super().validate(method, url, body)


def retrieve(boundary, method, url, body=None):
    redirected = False
    while True:
        status, headers, data = boundary.request(method, url, body=body,
            headers={'Content-Type': 'application/x-www-form-urlencoded'} if body else {},
            redirected=redirected)
        if status in (301, 302, 303):
            url = urljoin(url, headers['Location']); method, body, redirected = 'GET', None, True
            continue
        if 300 <= status < 400:
            boundary.budget.reject('PARTIAL_RETRIEVAL', 'unsupported redirect semantics')
        if status != 200:
            boundary.budget.reject('PARTIAL_RETRIEVAL', 'unexpected response')
        content_type = next((v for k, v in headers.items() if k.lower() == 'content-type'), '')
        if content_type and 'text/html' not in content_type.lower():
            boundary.budget.reject('PARTIAL_RETRIEVAL', 'non-HTML status response')
        try: return url, data.decode('utf-8', 'strict')
        except UnicodeError: boundary.budget.reject('PARSER_FAILURE', 'unsupported encoding')


def exact_status_lookup(boundary):
    from app.config import get_council
    from app.scrapers.idox_portal import fetch_application_status_by_reference
    return fetch_application_status_by_reference(get_council('oldham'), boundary.policy.reference, boundary)


class FixtureResponse:
    def __init__(self, body, status=200, headers=None):
        self.body = body.encode() if isinstance(body, str) else body
        self.status_code, self.headers = status, headers or {'Content-Type': 'text/html'}
        self.closed = False
    def iter_content(self, size):
        for i in range(0, len(self.body), size): yield self.body[i:i+size]
    def close(self): self.closed = True


def fixture_dispatch(reference, *, status=None, decision=None, date=None):
    """MOCKED EXPECTATION; deliberately not retained council HTML/truth."""
    refusal = reference == CASES[0]['reference']
    status = status or ('Decided' if refusal else 'Awaiting decision')
    decision = decision if decision is not None else ('Refused' if refusal else '')
    date = date if date is not None else ('Fri 25 Sep 2026' if refusal else '')
    form = '<form method="POST" action="advancedSearchResults.do?action=firstPage"><input name="searchCriteria.reference"><input name="_csrf" value="fixtureNonce"></form>'
    summary = '<table>' + ''.join(f'<tr><th>{k}</th><td>{v}</td></tr>' for k, v in (
        ('Reference', reference), ('Status', status), ('Decision', decision), ('Decision Issued Date', date))) + '</table>'
    responses = iter((FixtureResponse(form), FixtureResponse('<a href="applicationDetails.do?activeTab=summary&amp;keyVal=FIXTURE">exact result</a>'), FixtureResponse(summary)))
    def dispatch(*args, **kwargs): return next(responses)
    return dispatch


def encode_artifact(result):
    encoded = (json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()
    if len(encoded) > MAX_ARTIFACT: raise BoundaryFailure('PARTIAL_RETRIEVAL', 'audit byte ceiling', budget=True)
    return encoded


def run(*, sha, mode='offline', dispatch_factory=None):
    if not re.fullmatch(r'[0-9a-f]{40}', sha): raise ValueError('Exact SHA required')
    if mode not in ('offline', 'live'): raise ValueError('Unknown mode')
    budget, rows = Budget(), []
    fence = ImportFence(); sys.meta_path.insert(0, fence)
    try:
        from .contract import assess
        from app.pipeline.material_change import _classify_planning_state
        for case in CASES:
            session = None
            if dispatch_factory is not None: dispatch = dispatch_factory(case['reference'])
            elif mode == 'offline': dispatch = fixture_dispatch(case['reference'])
            else:
                session = requests.Session(); session.trust_env = False
                session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))
                def dispatch(method, url, **kwargs):
                    kwargs.pop('deadline', None)
                    return session.request(method, url, **kwargs)
            boundary = OldhamBoundary(case['reference'], budget, dispatch)
            reference_started = time.monotonic()
            try:
                candidate = exact_status_lookup(boundary)
                verdict = assess(case, candidate, reference=case['reference'], base_url=BASE)
                if not verdict['outcome'].startswith('VERIFIED_'):
                    budget.reject(verdict['outcome'], 'source/parser did not establish accepted fact')
                row = boundary.audit(verdict['outcome'])
                row['source_qualification'] = 'MOCKED_EXPECTATION' if mode == 'offline' else 'exact_public_council_summary'
                accepted = verdict['acceptance_candidate']
                if accepted:
                    row.update(status=_classify_planning_state(accepted['decision'], accepted['status']),
                        decision=_classify_planning_state(accepted['decision'], None) if accepted['decision'] else None,
                        decision_date=accepted['decision_issued_date'], source_url=candidate.summary_url)
            except BoundaryFailure as exc:
                row = boundary.audit(exc.outcome); row['failure_classification'] = exc.reason
                row['source_qualification'] = 'not_verified'
            except Exception:
                budget.failure = budget.failure or BoundaryFailure('PARTIAL_RETRIEVAL', 'unqualified verifier failure')
                row = boundary.audit('PARTIAL_RETRIEVAL'); row['failure_classification'] = 'unqualified verifier failure'
                row['source_qualification'] = 'not_verified'
            finally:
                boundary.close()
                if session is not None: session.close()
            rows.append(row)
            row['attempted'] = boundary.requests > 0
            row['elapsed_seconds'] = round(time.monotonic() - reference_started, 3)
        complete = len(rows) == 2 and all(r['outcome'].startswith('VERIFIED_') for r in rows) and not budget.failure
        return dict(manifest_version=VERSION, workflow_version=VERSION, repository=REPOSITORY,
            repository_sha=sha, execution_time=dt.datetime.now(dt.timezone.utc).isoformat(),
            mode=mode, execution_status='COMPLETE' if complete else 'FAIL', persistence=False,
            council_network_requests=0 if mode == 'offline' else sum(r['requests_attempted'] for r in rows),
            requests_attempted=sum(r['requests_attempted'] for r in rows),
            received_bytes=budget.used_bytes, budget_state='EXHAUSTED' if budget.failure and budget.failure.budget else 'WITHIN_LIMITS',
            elapsed_seconds=round(time.monotonic() - budget.started, 3),
            results=rows)
    finally: sys.meta_path.remove(fence)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sha', required=True)
    parser.add_argument('--mode', choices=('offline', 'live'), default='offline')
    parser.add_argument('--authority', default='OFFLINE_ONLY')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'live' and args.authority != AUTHORITY:
        parser.error('Exact live authority acknowledgement required')
    if args.output.exists(): parser.error('Refusing existing audit artifact')
    if args.mode == 'offline':
        with offline_network_denial(): result = run(sha=args.sha)
    else: result = run(sha=args.sha, mode='live')
    data = encode_artifact(result)
    with args.output.open('xb') as artifact: artifact.write(data)
    return 0 if result['execution_status'] == 'COMPLETE' else 1


if __name__ == '__main__': raise SystemExit(main())
