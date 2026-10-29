"""Cumulative intake database reservations, no database/network."""
from types import SimpleNamespace
import time
import pytest
from app.ingestion.ledger import Denied
from verification.ingestion_storage.chain_caller import ChainCaller


def caller():
    x=object.__new__(ChainCaller)
    x.intake_only=True;x.intake_started=time.monotonic();x.stop_file=None;x.budgets=[]
    return x


def prior(statements=0,attempts=0,returned=0,cancels=0):
    return SimpleNamespace(statements=statements,attempts=attempts,returned_bytes=returned,prior_cancel_attempts=0,
                           hard_deadline_events=[dict(cancel_attempts=cancels)])


@pytest.mark.parametrize('old',[prior(statements=1005),prior(attempts=38),prior(returned=4*1024**2)])
def test_no_new_stage_consumes_closure_reserve(old):
    x=caller();x.budgets=[old]
    with pytest.raises(Denied,match='AGGREGATE_CLOSURE_RESERVE'):x._budget()


def test_remaining_limits_and_cancellation_cost_are_carried():
    x=caller();x.budgets=[prior(statements=950,attempts=34,returned=100,cancels=3)]
    b=x._budget()
    assert b.statement_cap==74 and b.connection_cap==4 and b.returned_cap==4*1024**2-100
    assert b.cancel_used==3 and b.hard_stop_at==x.intake_started+270


def test_elapsed_time_cannot_restart_with_another_batch():
    x=caller();x.intake_started-=271
    with pytest.raises(Denied,match='AGGREGATE_CLOSURE_RESERVE'):x._budget()
