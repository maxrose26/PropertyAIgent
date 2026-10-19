"""The deadline levels, derived from the actual constants (not restated numbers): per wait, complete operation, aggregate, and the failure window that holds teardown."""
from verification.ingestion_storage import operational_controller as oc,operational_owner as oo,operational_runner as orr
from verification.ingestion_storage import hard_deadline as hd

CANCEL=hd.CANCEL_TIMEOUT_SECONDS;CLOSE=hd.CLOSE_ALLOWANCE_SECONDS


def test_per_wait_is_above_the_server_timeout_and_below_the_slot():
    assert 10<oc.STATEMENT_HARD_SECONDS<=12 and oo.ADMIN_STATEMENT_HARD_SECONDS==oc.STATEMENT_HARD_SECONDS


def test_one_complete_runtime_operation_worst_case():
    # two waits (statement, then its cleanup wait), a bounded cancel and a bounded close; the reserve clamp keeps every wait before hard_stop_at, only cancel+close can pass it
    operation=oc.WAITS_PER_OPERATION*oc.STATEMENT_HARD_SECONDS+CANCEL+CLOSE
    overrun=CANCEL+CLOSE
    assert operation==27 and overrun==3


def test_failure_window_holds_the_overrun_a_blocked_admin_statement_and_the_full_cleanup():
    d=orr.DEFAULT_DEADLINES
    overrun=CANCEL+CLOSE                                                                   # a runtime wait clamped to hard_stop_at, then cancel + close
    blocked_admin=oo.ADMIN_STATEMENT_HARD_SECONDS+CANCEL+CLOSE                              # one blocked administrative statement during teardown
    session_waits=(oo.SESSION_POLICY["wait_reads"]+oo.SESSION_POLICY["post_reads"])*oo.SESSION_POLICY["wait_seconds"]      # wait reads, and the post-termination reads
    restoration_allowance=3.0                                                              # new connection + 9 commands, measured in milliseconds; given a deliberate 3 s
    need=overrun+blocked_admin+session_waits+restoration_allowance
    assert need==24.0 and need<=d["diagnostic_window"]                                     # the nominal 25 s window is effectively 24 s of work (healthy GitHub and database: the GitHub calls and a second blocked statement are NOT inside this figure; the process backstop at 480 s bounds those): one blocked statement fits, two do not
    assert d["job"]+need<=d["diagnostic_total"] and d["diagnostic_total"]<480


def test_aggregate_cancellation_is_finite_for_the_whole_run():
    runtime=oc.CANCEL_RUN_ALLOWANCE["attempts"];admin=oo.ADMIN_CANCEL_ALLOWANCE
    assert runtime==8 and admin==3 and oc.CANCEL_ALLOWANCE["attempts"]<=runtime
    assert (runtime+admin)*CANCEL<=22                           # at most 11 cancels of 2 s each in the entire run, 22 s in total
