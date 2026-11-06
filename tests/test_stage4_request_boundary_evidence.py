"""Offline negative-path contract for previously added request-boundary diagnostics.

Synthetic transport only: no council request, database, browser or persistence.
These tests are additional to, not replacements for, the immutable direct-
registration source digest check. A complete *body read* is not source success.
"""
import json

import pytest
import requests

from verification.stage26b_l1.request_boundary import Boundary, BoundaryFailure, Budget, Policy


URL = "https://example.invalid/online-applications/search.do"
POLICY = Policy(
    council="bolton",
    reference="00307/26",
    adapter="idox",
    base_url="https://example.invalid/online-applications",
    search_url=URL,
)


class Response:
    def __init__(self, chunks=(b"private-body",), *, status=200, failure=None, headers=None):
        self.chunks = chunks
        self.status_code = status
        self.failure = failure
        self.headers = {"Content-Type": "text/html", **(headers or {})}
        self.closed = False
        self.closes = 0

    def iter_content(self, _size):
        for chunk in self.chunks:
            yield chunk
        if self.failure is not None:
            raise self.failure

    def close(self):
        self.closes += 1
        self.closed = True


def boundary_for(response, events, *, budget=None, callback=None):
    calls = []

    def dispatch(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return response

    bound = Boundary(
        POLICY, budget or Budget(requests=2, per_reference=2, seconds=20),
        dispatch, max_retries=0,
    )
    bound.response_evidence = callback or (
        lambda payload, attempt, *, complete: events.append((payload, attempt, complete))
    )
    return bound, calls


def test_success_preserves_complete_body_once_and_closes_transport():
    body = b"synthetic-ok"
    response = Response((body[:4], body[4:]))
    events = []
    bound, calls = boundary_for(response, events)
    status, headers, received = bound.request("GET", URL)
    assert status == 200 and headers["Content-Type"] == "text/html"
    assert received == body
    assert events == [(body, 1, True)]
    assert len(calls) == 1 and calls[0][0:2] == ("GET", URL)
    assert calls[0][2]["allow_redirects"] is False
    assert response.closed and response.closes == 1
    assert bound.requests == bound.budget.used_requests == 1
    assert bound.retries == 0


def test_http_refusal_keeps_body_read_distinct_from_source_success():
    secret = b"private@example.invalid"
    response = Response((secret,), status=429)
    events = []
    bound, calls = boundary_for(response, events)
    with pytest.raises(BoundaryFailure) as err:
        bound.request("GET", URL)
    assert err.value.outcome == "RATE_LIMITED"
    # complete=True means the response body finished, not that HTTP was accepted.
    assert events == [(secret, 1, True)]
    assert len(calls) == 1 and response.closed and response.closes == 1
    audit = json.dumps(bound.audit(err.value.outcome))
    assert "private@" not in audit and "example.invalid" not in audit
    assert bound.retries == 0


def test_partial_timeout_retains_once_as_incomplete_without_retry():
    secret = b"partial-secret"
    response = Response((secret,), failure=requests.ReadTimeout("secret-token"))
    events = []
    bound, calls = boundary_for(response, events)
    with pytest.raises(BoundaryFailure) as err:
        bound.request("GET", URL)
    assert err.value.outcome == "TIMEOUT"
    assert events == [(secret, 1, False)]
    assert len(calls) == 1 and response.closed and response.closes == 1
    assert bound.retries == 0 and bound.budget.used_requests == 1
    assert bound.transport_failure is not None
    assert "secret-token" not in json.dumps(bound.transport_failure)


def test_byte_ceiling_rejects_and_retains_bounded_incomplete_evidence():
    response = Response((b"12345",))
    events = []
    budget = Budget(requests=2, per_reference=2, response_bytes=4, seconds=20)
    bound, calls = boundary_for(response, events, budget=budget)
    with pytest.raises(BoundaryFailure) as err:
        bound.request("GET", URL)
    assert err.value.outcome == "PARTIAL_RETRIEVAL" and err.value.budget
    assert events == [(b"12345", 1, False)]
    assert len(calls) == 1 and response.closed and response.closes == 1
    assert bound.budget.failure is err.value


def test_evidence_callback_failure_refuses_and_closes_without_reinvocation():
    response = Response((b"private",))
    events = []

    def broken(payload, attempt, *, complete):
        events.append((payload, attempt, complete))
        raise ValueError("private callback failure")

    bound, calls = boundary_for(response, events, callback=broken)
    with pytest.raises(BoundaryFailure) as err:
        bound.request("GET", URL)
    assert err.value.outcome == "PARTIAL_RETRIEVAL"
    assert events == [(b"private", 1, True)]  # no duplicate callback
    assert len(calls) == 1 and response.closed and response.closes == 1
    assert "private callback failure" not in json.dumps(bound.audit(err.value.outcome))


def test_forbidden_route_never_dispatches_or_captures_evidence():
    response = Response()
    events = []
    bound, calls = boundary_for(response, events)
    with pytest.raises(BoundaryFailure) as err:
        bound.request("GET", "https://other.invalid/online-applications/search.do")
    assert err.value.outcome == "PARTIAL_RETRIEVAL"
    assert calls == [] and events == [] and not response.closed
    assert bound.requests == bound.budget.used_requests == 0
