"""Status-only request accounting. No database, model, or live entry point.

Physical dispatch is injected; callers must also contain browser-native networking.
This component alone is not authority to make a council request.
"""
from dataclasses import dataclass, field
from urllib.parse import urlsplit, parse_qs, unquote
import time
import requests

class BoundaryFailure(RuntimeError):
    def __init__(self, outcome='PARTIAL_RETRIEVAL', reason='boundary rejected', *, budget=False):
        super().__init__(reason)
        self.outcome, self.reason, self.budget = outcome, reason, budget

@dataclass(frozen=True)
class Policy:
    council: str
    reference: str
    adapter: str
    base_url: str
    search_url: str

@dataclass
class Budget:
    requests: int = 20
    per_reference: int = 10
    total_bytes: int = 10_000_000
    response_bytes: int = 2_000_000
    seconds: float = 165
    used_requests: int = 0
    used_bytes: int = 0
    by_reference: dict = field(default_factory=dict)
    host_failures: dict = field(default_factory=dict)
    started: float = field(default_factory=time.monotonic)
    failure: BoundaryFailure | None = None

    def __post_init__(self):
        if not (0 < self.requests <= 20 and 0 < self.per_reference <= 10 and
                0 < self.total_bytes <= 10_000_000 and 0 < self.response_bytes <= 2_000_000 and
                0 < self.seconds <= 165):
            raise ValueError('Canary bounds cannot be relaxed')

    def reject(self, outcome, reason, budget=False):
        self.failure = self.failure or BoundaryFailure(outcome, reason, budget=budget)
        raise self.failure

    def check(self):
        if self.failure: raise self.failure
        if time.monotonic() - self.started >= self.seconds:
            self.reject('TIMEOUT', 'run deadline', True)

    def charge_request(self, policy):
        self.check()
        host = urlsplit(policy.base_url).hostname
        if self.host_failures.get(host, 0) >= 2:
            self.reject('SOURCE_UNAVAILABLE', 'run-local host circuit open')
        key = (policy.council, policy.reference)
        # A blocked attempted dispatch is recorded too; it does not reach transport.
        self.used_requests += 1
        self.by_reference[key] = self.by_reference.get(key, 0) + 1
        if self.used_requests > self.requests or self.by_reference[key] > self.per_reference:
            self.reject('PARTIAL_RETRIEVAL', 'request ceiling', True)

    def charge_bytes(self, size, response_size):
        self.used_bytes += size
        self.check()
        if response_size > self.response_bytes or self.used_bytes > self.total_bytes:
            self.reject('PARTIAL_RETRIEVAL', 'response byte ceiling', True)

class Boundary:
    def __init__(self, policy, budget, dispatch):
        if policy.adapter not in ('idox', 'arcus') or not policy.reference.strip():
            raise ValueError('Unsupported exact-reference policy')
        self.policy, self.budget, self.dispatch = policy, budget, dispatch
        self.keyval = None
        self.detail_url = None
        self.redirects = self.retries = self.requests = self.received_bytes = 0
        self.closed = False

    def unique(self, matches, *, complete=False):
        matches = sorted(set(matches))
        if len(matches) > 1:
            self.budget.reject('AMBIGUOUS_SOURCE_RESULT', 'multiple plausible exact results')
        if not matches:
            self.budget.reject('REFERENCE_NOT_FOUND' if complete else 'PARTIAL_RETRIEVAL', 'no exact result')
        if self.policy.adapter == 'idox': self.keyval = matches[0]
        else: self.detail_url = matches[0]
        return matches[0]

    def validate(self, method, url, body=None):
        self.budget.check()
        if self.closed: self.budget.reject('PARTIAL_RETRIEVAL', 'closed transport')
        u, b = urlsplit(url), urlsplit(self.policy.base_url)
        if (u.scheme != 'https' or u.hostname != b.hostname or u.port not in (None, 443) or
                u.username or u.password or u.fragment or '\\' in url):
            self.budget.reject('PARTIAL_RETRIEVAL', 'origin rejected')
        path = unquote(u.path)
        if path != u.path or '..' in path or '//' in path:
            self.budget.reject('PARTIAL_RETRIEVAL', 'noncanonical route')
        method = method.upper()
        q = parse_qs(u.query, keep_blank_values=True)
        if body is not None and len(body) > 65536:
            self.budget.reject('PARTIAL_RETRIEVAL', 'request payload ceiling', True)
        base_path = b.path.rstrip('/')
        if self.policy.adapter == 'idox':
            if path == base_path + '/search.do':
                if method not in ('GET', 'POST'): self.budget.reject('PARTIAL_RETRIEVAL', 'method rejected')
                if method == 'GET' and url != self.policy.search_url:
                    self.budget.reject('PARTIAL_RETRIEVAL', 'search expansion rejected')
                if method == 'POST':
                    fields = parse_qs((body or b'').decode('utf-8'), keep_blank_values=True)
                    if fields.get('searchCriteria.reference') != [self.policy.reference]:
                        self.budget.reject('PARTIAL_RETRIEVAL', 'exact reference required')
                    for key, values in fields.items():
                        if key.startswith('searchCriteria.') and key != 'searchCriteria.reference' and any(values):
                            self.budget.reject('PARTIAL_RETRIEVAL', 'additional search criterion rejected')
                if method == 'POST':
                    if set(q): self.budget.reject('PARTIAL_RETRIEVAL', 'POST query rejected')
                    # Only exact-reference and the synthetic fixture submit control
                    # are admitted. Live form/CSRF fields remain unqualified.
                    if set(fields) - {'searchCriteria.reference', 'action'}:
                        self.budget.reject('PARTIAL_RETRIEVAL', 'unapproved form field')
                    if 'action' in fields and fields['action'] != ['Search']:
                        self.budget.reject('PARTIAL_RETRIEVAL', 'unapproved form action')
                return
            if path == base_path + '/advancedSearchResults.do' and method == 'GET' and not body:
                if set(q) <= {'action'} and q.get('action', ['firstPage']) == ['firstPage']: return
            if path == base_path + '/applicationDetails.do' and method == 'GET' and not body:
                if set(q) == {'activeTab', 'keyVal'} and q['activeTab'] == ['summary'] and len(q['keyVal']) == 1:
                    # A direct exact-search redirect is provisional until the detail Reference agrees.
                    if self.keyval is None: self.keyval = q['keyVal'][0]
                    if q['keyVal'] == [self.keyval]: return
        else:
            if method == 'GET' and not body and url in (self.policy.search_url, self.detail_url): return
        # Status-only pages may load static resources on the exact council origin.
        # No extensionless/XHR wildcard: undocumented endpoints fail closed.
        if method == 'GET' and not body and not u.query and path.startswith(base_path + '/'):
            if path.lower().endswith(('.css', '.js', '.png', '.jpg', '.gif', '.svg', '.woff', '.woff2', '.ico')):
                if any(w in path.lower() for w in ('document', 'download', 'file', 'related', 'history')):
                    self.budget.reject('PARTIAL_RETRIEVAL', 'discovery/document route rejected')
                return
        self.budget.reject('PARTIAL_RETRIEVAL', 'unapproved route class')

    def request(self, method, url, *, body=None, headers=None, redirected=False):
        self.validate(method, url, body)
        if redirected:
            self.redirects += 1
            if self.redirects > 2: self.budget.reject('PARTIAL_RETRIEVAL', 'redirect ceiling', True)
        while True:
            self.budget.charge_request(self.policy)
            self.requests += 1
            response = None
            charged = 0
            try:
                response = self.dispatch(method, url, data=body, headers=headers or {}, stream=True,
                    allow_redirects=False, timeout=min(15, self.budget.seconds-(time.monotonic()-self.budget.started)),
                    deadline=self.budget.started+self.budget.seconds)
                payload = bytearray()
                charged = 0
                content_type = response.headers.get("Content-Type", "").lower()
                if "attachment" in response.headers.get("Content-Disposition", "").lower() or any(t in content_type for t in ("application/pdf", "application/zip", "application/octet-stream")):
                    self.budget.reject("PARTIAL_RETRIEVAL", "document response rejected")
                for chunk in response.iter_content(65536):
                    if not chunk: continue
                    payload.extend(chunk)
                    # Charge the larger of decoded and exposed wire-body position.
                    # This guards decompression expansion and encoded-body overhead.
                    raw = getattr(response, 'raw', None)
                    wire = raw.tell() if raw is not None and hasattr(raw, 'tell') else 0
                    measured = max(len(payload), wire)
                    delta = measured - charged
                    self.received_bytes += delta
                    charged = measured
                    self.budget.charge_bytes(delta, measured)
                status = response.status_code
                if status == 429: self.budget.reject('RATE_LIMITED', 'HTTP rate limit')
                if status in (502, 503, 504):
                    raise requests.ConnectionError('transient upstream response')
                if status >= 400: self.budget.reject('SOURCE_UNAVAILABLE', 'HTTP failure')
                if 300 <= status < 400:
                    from urllib.parse import urljoin
                    target = urljoin(url, response.headers.get('Location', ''))
                    if not response.headers.get('Location'): self.budget.reject('PARTIAL_RETRIEVAL', 'missing redirect location')
                    self.validate('GET', target)
                return status, dict(response.headers), bytes(payload)
            except (requests.Timeout, requests.ConnectionError) as exc:
                host = urlsplit(self.policy.base_url).hostname
                self.budget.host_failures[host] = self.budget.host_failures.get(host, 0) + 1
                if self.retries >= 1 or self.budget.host_failures[host] >= 2:
                    self.budget.reject('TIMEOUT' if isinstance(exc, requests.Timeout) else 'SOURCE_UNAVAILABLE', 'transport failed')
                self.retries += 1
                # One retry, globally for this reference, including all browser assets.
                self.budget.check()
            except BoundaryFailure: raise
            except Exception:
                self.budget.reject('PARTIAL_RETRIEVAL', 'unqualified transport failure')
            finally:
                if response is not None:
                    try:
                        raw = getattr(response, 'raw', None)
                        wire = raw.tell() if raw is not None and hasattr(raw, 'tell') else 0
                        measured = max(charged, wire)
                        delta = measured - charged
                        self.received_bytes += delta
                        if delta: self.budget.charge_bytes(delta, measured)
                    finally:
                        response.close()

    def audit(self, outcome):
        return dict(council=self.policy.council, reference=self.policy.reference, adapter=self.policy.adapter,
            outcome=outcome, requests_attempted=self.requests, redirects=self.redirects, retries=self.retries,
            received_bytes=self.received_bytes, elapsed_seconds=round(time.monotonic()-self.budget.started, 3),
            budget_exhaustion=bool(self.budget.failure and self.budget.failure.budget))

    def close(self): self.closed = True
