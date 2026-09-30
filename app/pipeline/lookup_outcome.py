"""Strict parent identity and bounded logical request outcomes (specification 019)."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import time
from contextvars import ContextVar

_retry_state = ContextVar("parent_retry_state", default=None)

def remember_retry_after(seconds):
    state = _retry_state.get()
    if state is not None:
        state["until"] = max(state.get("until", 0), time.monotonic() + seconds)



def retry_wait(value, fallback):
    """Parent-only HTTP-date support; preserve primary scrape retry behaviour."""
    if value and value.isdigit():
        return float(value)
    if value and _retry_state.get() is not None:
        from email.utils import parsedate_to_datetime
        import datetime as dt
        try:
            due = parsedate_to_datetime(value)
            if due.tzinfo is None: due = due.replace(tzinfo=dt.timezone.utc)
            return max(0, (due-dt.datetime.now(dt.timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            pass
    return fallback


class Outcome(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"
    TRANSIENT_FAILURE = "transient_failure"


def reference_key(value: str) -> str:
    return value.strip().casefold()


class LogicalDeadline(BaseException):
    pass


class AmbiguousIdentity(ValueError):
    pass


class UnrecognisedSearch(RuntimeError):
    pass


@dataclass(frozen=True)
class LookupResult:
    outcome: Outcome
    application: object | None = None
    reason: str = ""
    retry_after_seconds: float | None = None
    host_failure: bool = False


_deadline = ContextVar("parent_deadline", default=None)


def remaining_seconds():
    deadline = _deadline.get()
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LogicalDeadline("parent logical deadline exhausted")
    return remaining


def bounded_sleep(seconds):
    remaining = remaining_seconds()
    time.sleep(seconds if remaining is None else min(seconds, remaining))
    remaining_seconds()


class BoundedPage:
    """Parent-only cooperative adapter; no signals inside Playwright's greenlet.

    Native wait/navigation/action timeouts consume a single remaining budget.
    Immediate protocol calls have before/after checks; a hung driver is contained
    by the independent parent-stage/council watchdog, not claimed preemptible here.
    """
    TIMED = {'goto', 'fill', 'click', 'wait_for_load_state', 'inner_text',
             'wait_for_selector', 'text_content', 'get_attribute'}
    LOCATORS = {'locator', 'get_by_text', 'get_by_role', 'nth'}

    def __init__(self, target):
        self.target = target

    def __getattr__(self, name):
        value = getattr(self.target, name)
        if name in {'first', 'last'}:
            return BoundedPage(value)
        if not callable(value):
            remaining_seconds()
            return value
        def invoke(*args, **kwargs):
            remaining = remaining_seconds()
            if name == 'wait_for_timeout':
                # Pump the browser event loop, with a bounded wait.
                args = (min(args[0], remaining * 1000),) if remaining is not None else args
            elif name in self.TIMED and remaining is not None:
                requested = kwargs.get('timeout', 30000)
                kwargs['timeout'] = min(requested or remaining * 1000, remaining * 1000)
            try:
                result = value(*args, **kwargs)
            except Exception as exc:
                remaining_seconds()
                if name in self.TIMED and remaining is not None:
                    from playwright.sync_api import TimeoutError as BrowserTimeout
                    if isinstance(exc, BrowserTimeout) and kwargs['timeout'] >= remaining * 1000:
                        raise LogicalDeadline("parent browser budget exhausted") from exc
                raise
            remaining_seconds()
            return BoundedPage(result) if name in self.LOCATORS else result
        return invoke


@contextmanager
def request_deadline(seconds: float):
    token = _deadline.set(time.monotonic() + seconds)
    try:
        remaining_seconds()
        yield
        remaining_seconds()
    finally:
        _deadline.reset(token)


def strict_lookup(call, reference: str, seconds: float = 60) -> LookupResult:
    state = {}
    token = _retry_state.set(state)
    try:
        with request_deadline(seconds):
            app = call()
        if app is None:
            return LookupResult(Outcome.NOT_FOUND)
        if not app.reference or reference_key(app.reference) != reference_key(reference):
            return LookupResult(Outcome.AMBIGUOUS_IDENTITY, reason="detail_reference_mismatch")
        return LookupResult(Outcome.FOUND, app)
    except LogicalDeadline:
        return LookupResult(Outcome.TRANSIENT_FAILURE, reason="logical_deadline",
            retry_after_seconds=max(0, state.get("until", 0)-time.monotonic()))
    except AmbiguousIdentity:
        return LookupResult(Outcome.AMBIGUOUS_IDENTITY, reason="search_identity_ambiguous")
    except Exception as exc:
        # Exception class only; portal content/URLs are not trusted diagnostic data.
        from app.pipeline.portal_circuit_breaker import is_portal_host_failure
        return LookupResult(Outcome.TRANSIENT_FAILURE, reason=type(exc).__name__,
            retry_after_seconds=max(0, state.get("until", 0)-time.monotonic()),
            host_failure=is_portal_host_failure(exc))
    finally:
        _retry_state.reset(token)
