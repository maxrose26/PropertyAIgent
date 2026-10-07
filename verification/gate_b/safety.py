"""Gate B production-read safety (specification 026). Release-validation tooling: NEVER imported by app/.

``read_only_window`` is the single place every guard lives. Real mode refuses anything but the application's own PostgreSQL route; synthetic mode (SQLite) exists for tests only.
Guards: READ ONLY transaction (set then verified), statement timeout, a statement allow-list (anything but SELECT/WITH/SHOW and the two SET forms raises), ORM write guard
(flush with pending changes, commit), network guard (Python sockets may connect nowhere except the database host; libpq/psycopg's own socket is outside Python and is the
database route itself), a model-client import block, a query circuit-breaker, and rollback in every outcome.
"""
from __future__ import annotations

import builtins
import os
import re
import socket
import sys
import time
from collections import Counter
from contextlib import contextmanager

from sqlalchemy import event, text

MODEL_MODULES = ("openai", "anthropic")
ALLOWED_PATTERN = re.compile(r"^(SELECT|WITH|SHOW|SET TRANSACTION READ ONLY|SET LOCAL STATEMENT_TIMEOUT)\b")
_LEADING_NOISE = re.compile(r"^(\s|--[^\n]*(\n|$))*")


class ReadOnlyViolation(RuntimeError):
    """A write, a non-allow-listed statement, a commit, or a guard failure inside the read-only window."""


class RealModeRefused(RuntimeError):
    """Real (production) mode was requested but the database route is not the application's own PostgreSQL route."""


class QueryBudgetExceeded(RuntimeError):
    """The optional safety circuit-breaker (not a performance threshold) tripped."""


def normalise_statement(statement: str) -> str:
    return _LEADING_NOISE.sub("", statement or "").strip().upper()


def is_allowed_statement(statement: str) -> bool:
    """Defence in depth only (the verified READ ONLY transaction is the barrier). Conservative: a statement must START with an allowed keyword (word boundary), contain no ';' except a
    single trailing one (no multi-statement text), and no block comment at all (PostgreSQL nests them, so they cannot be reasoned about by a simple scanner)."""
    text_ = normalise_statement(statement)
    body = text_[:-1].rstrip() if text_.endswith(";") else text_
    return bool(ALLOWED_PATTERN.match(body)) and ";" not in body and "/*" not in body


class Instrument:
    """Query and entity-read counters for the one read window (cost / Supabase-egress understanding; no thresholds)."""

    def __init__(self):
        self.queries = 0
        self.statements = Counter()
        self.entities = Counter()
        self.started = time.perf_counter()
        self.stages: list[dict] = []

    def snapshot(self, name: str):
        self.stages.append({"stage": name, "queries": self.queries, "entities_read": sum(self.entities.values()), "seconds": round(time.perf_counter() - self.started, 3)})

    def report(self) -> dict:
        deltas, previous = [], {"queries": 0, "entities_read": 0, "seconds": 0.0}
        for stage in self.stages:
            deltas.append({"stage": stage["stage"], "queries": stage["queries"] - previous["queries"], "entities_read": stage["entities_read"] - previous["entities_read"],
                           "seconds": round(stage["seconds"] - previous["seconds"], 3)})
            previous = stage
        return {"query_count": self.queries, "statement_kinds": dict(sorted(self.statements.items())), "entities_read_total": sum(self.entities.values()),
                "entities_read_by_category": dict(sorted(self.entities.items())), "runtime_seconds": round(time.perf_counter() - self.started, 3), "stages": deltas}


@contextmanager
def network_guard(allowed_hosts=()):
    """Python-level sockets may connect only to allowed hosts (or UNIX sockets); model-client modules cannot be newly imported."""
    allowed = {h for h in allowed_hosts if h}
    originals = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection, builtins.__import__)

    def permitted(address) -> bool:
        if isinstance(address, (str, bytes)):
            return True                                              # AF_UNIX
        return bool(address) and str(address[0]) in allowed

    def guarded_connect(self, address):
        if not permitted(address):
            raise ReadOnlyViolation(f"network access blocked by the Gate B guard: {address!r}")
        return originals[0](self, address)

    def guarded_connect_ex(self, address):
        if not permitted(address):
            raise ReadOnlyViolation(f"network access blocked by the Gate B guard: {address!r}")
        return originals[1](self, address)

    def guarded_create_connection(address, *a, **k):
        if not permitted(address):
            raise ReadOnlyViolation(f"network access blocked by the Gate B guard: {address!r}")
        return originals[2](address, *a, **k)

    def guarded_import(name, *a, **k):
        if name.split(".")[0] in MODEL_MODULES and name.split(".")[0] not in sys.modules:
            raise ReadOnlyViolation(f"model client import blocked by the Gate B guard: {name}")
        return originals[3](name, *a, **k)

    socket.socket.connect, socket.socket.connect_ex, socket.create_connection, builtins.__import__ = guarded_connect, guarded_connect_ex, guarded_create_connection, guarded_import
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection, builtins.__import__ = originals


def assert_read_only(connection, statement_timeout_ms: int) -> None:
    """The first statements of every transaction on a PostgreSQL connection (SET TRANSACTION must precede any query)."""
    connection.execute(text("SET TRANSACTION READ ONLY"))
    connection.execute(text(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}"))


def _database_host() -> str | None:
    from urllib.parse import urlsplit
    url = os.getenv("DATABASE_URL") or ""
    return urlsplit(url).hostname if url else None


def check_route(session, *, real: bool) -> str:
    """Refuse a route that is not allowed for the requested mode. Returns the dialect name."""
    dialect = session.get_bind().dialect.name
    if real:
        from app.db.session import get_engine
        if dialect != "postgresql":
            raise RealModeRefused(f"real mode requires the PostgreSQL backend (found {dialect!r})")
        if not os.getenv("DATABASE_URL"):
            raise RealModeRefused("real mode requires DATABASE_URL from the environment (the application database route)")
        if session.get_bind() is not get_engine():
            raise RealModeRefused("real mode requires the application's own engine route")
    elif dialect != "sqlite":
        raise RealModeRefused(f"synthetic mode is for SQLite test data only (found {dialect!r}); a real database needs real mode with its safeguards")
    return dialect


@contextmanager
def read_only_window(session, *, real: bool, statement_timeout_ms: int = 60000, max_queries: int | None = None):
    """Everything inside the block is read-only, instrumented and rolled back. Yields (Instrument, safety-status dict)."""
    dialect = check_route(session, real=real)
    if real and session.in_transaction():
        raise RealModeRefused("the read-only window must start on a fresh session (SET TRANSACTION READ ONLY has to be the first statement of its transaction)")
    engine = session.get_bind()
    instrument = Instrument()
    status = {"mode": "real" if real else "synthetic", "backend": dialect, "read_only_transaction": "not_applicable_synthetic", "statement_timeout_ms": None,
              "statement_allow_list": True, "orm_write_guard": True, "network_guard": True, "model_import_block": True, "committed": False,
              "model_modules_loaded_before_window": sorted(m for m in MODEL_MODULES if m in sys.modules)}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if not is_allowed_statement(statement) and not (dialect == "sqlite" and normalise_statement(statement).startswith("PRAGMA")):
            raise ReadOnlyViolation(f"non-read statement refused: {normalise_statement(statement)[:60]}")
        instrument.queries += 1
        instrument.statements[normalise_statement(statement).split(None, 1)[0] if statement.strip() else "EMPTY"] += 1
        if max_queries is not None and instrument.queries > max_queries:
            raise QueryBudgetExceeded(f"safety circuit-breaker: more than {max_queries} queries")

    def before_flush(sess, flush_context, instances):
        if sess.new or sess.dirty or sess.deleted:
            raise ReadOnlyViolation("ORM changes were staged inside the read-only window")

    def after_begin(sess, transaction, connection):
        # Every NEW transaction in this session (e.g. after a rollback swallowed somewhere) is made READ ONLY before anything else runs.
        if dialect == "postgresql":
            assert_read_only(connection, statement_timeout_ms)

    def before_commit(sess):
        raise ReadOnlyViolation("commit attempted inside the read-only window")

    def loaded(sess, instance):
        instrument.entities[type(instance).__name__] += 1

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(session, "before_flush", before_flush)
    event.listen(session, "before_commit", before_commit)
    event.listen(session, "loaded_as_persistent", loaded)
    event.listen(session, "after_begin", after_begin)
    guard = network_guard(allowed_hosts=(_database_host(),) if real else ())
    try:
        with guard:
            if dialect == "postgresql":
                session.connection()                                  # begins the transaction: after_begin issues SET TRANSACTION READ ONLY first
                if session.execute(text("SHOW transaction_read_only")).scalar() != "on":
                    raise ReadOnlyViolation("the transaction could not be verified READ ONLY")
                status["read_only_transaction"] = "verified_on_and_reasserted_on_every_new_transaction"
                status["statement_timeout_ms"] = int(statement_timeout_ms)
            yield instrument, status
    finally:
        try:
            event.remove(engine, "before_cursor_execute", before_cursor_execute)
            event.remove(session, "before_flush", before_flush)
            event.remove(session, "before_commit", before_commit)
            event.remove(session, "loaded_as_persistent", loaded)
            event.remove(session, "after_begin", after_begin)
        finally:
            session.rollback()
