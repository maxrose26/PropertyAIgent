"""Receipt-only regressions; original production receipt is never altered."""
import ast
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest


def cleanup_namespace(connection, execute):
    source = Path('docs/design/pa-tam001-transport/inspection.py').read_text()
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and n.name in ('Refusal', 'require', 'rollback_and_close')]
    state = dict(transaction='READ_ONLY', rollback_attempted=False,
                 rollback_acknowledged=False, connection_closed=None, unknowns={})
    ns = dict(c=connection, execute=execute, out=state)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<cleanup>', 'exec'), ns)
    return ns


@pytest.mark.parametrize('status,tag,close_fails,ack', [
    (0, 'ROLLBACK', False, True),
    (2, 'ROLLBACK', False, False),
    (4, 'ROLLBACK', False, False),
    (0, None, False, False),
    (0, 'ROLLBACK', True, True),
])
def test_acknowledgement_and_closure_are_independent(status, tag, close_fails, ack):
    # Exercise psycopg's actual integer -> TransactionStatus API, not a fake enum.
    class Connection:
        pgconn = SimpleNamespace(transaction_status=status)
        info = psycopg.ConnectionInfo(pgconn)
        closed = False
        def close(self):
            if close_fails:
                raise OSError('fixture close failure')
            self.closed = True
    calls = []
    def execute(sql, *, cleanup):
        calls.append((sql, cleanup))
        return SimpleNamespace(statusmessage=tag)
    ns = cleanup_namespace(Connection(), execute)
    ns['rollback_and_close']()
    assert calls == [('ROLLBACK', True)]
    assert ns['out']['rollback_acknowledged'] is ack
    assert ns['out']['connection_closed'] is (not close_fails)
    assert ns['out']['transaction'] == ('ROLLED_BACK' if ack else 'READ_ONLY')
    assert ('transaction_end' in ns['out']['unknowns']) is (not ack)


def test_rollback_exception_closes_without_claiming_acknowledgement():
    class Connection:
        closed = False
        def close(self):
            self.closed = True
    def execute(*_, **__):
        raise OSError('fixture lost acknowledgement')
    ns = cleanup_namespace(Connection(), execute)
    ns['rollback_and_close']()
    assert ns['out']['rollback_attempted']
    assert not ns['out']['rollback_acknowledged']
    assert ns['out']['connection_closed']
