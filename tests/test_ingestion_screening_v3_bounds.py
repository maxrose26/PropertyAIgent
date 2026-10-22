"""The screening-v3 owner's worst-case GitHub requests, command and connection allowances (PR #175), derived from the actual waits and driven through the REAL `await_any` loop on a SIMULATED clock: no real-time wait, no network."""
import pytest

pytest.importorskip('resource')

from verification.ingestion_storage import operational_runner as orr

POLL = orr.SV3_BINDING['poll_seconds']
READY_WAIT = orr.SV3_BINDING['ready_wait_seconds']
RESULT_WAIT = orr.SV3_BINDING['screening_wait_seconds']
READY_HEADS = 3      # distinct evidence heads while waiting for READY (initial, the hosted ready commit, one further hosted commit)
RESULT_HEADS = 4     # distinct evidence heads while waiting for the result (the owner's registration marker, hosted progress commits, the final result)
RESERVE = 40         # requests held back above the derived worst case, over and above the 14-request publication reserve that is already inside the derivation


def publish_requests(files):
    return 6 + 2 * files      # GET ref, GET commit, a POST per blob, POST tree, POST commit, PATCH ref, GET ref, a GET per file read back


def polls(wait):
    return -(-wait // POLL) + 1      # one ref read per poll plus the boundary poll


def worst_case():
    reprobes = orr.Runner.REPROBES
    items = dict(
        account=1,
        freshness=1 + 1 + 3,      # ref, README anchor, three absent-file probes, before anything is issued
        ready_head_reads=polls(READY_WAIT), ready_file_probes=READY_HEADS * reprobes,
        registration_publication=publish_requests(1),
        result_head_reads=polls(RESULT_WAIT), result_file_probes=RESULT_HEADS * reprobes,
        owner_publication=publish_requests(2),
        failure_reads=1)
    return items, sum(items.values())


class Github:
    def __init__(self, heads):
        self.heads = heads
        self.calls = 0
        self.probes = 0

    def call(self, method, path, *args, **kwargs):
        self.calls += 1
        return {'object': {'sha': self.heads(self.calls)}}

    def probe(self, path):
        self.probes += 1
        return None      # the awaited file never appears: the whole wait is consumed


def run_wait(monkeypatch, seconds, heads):
    clock = [1000.0]
    monkeypatch.setattr(orr.time, 'monotonic', lambda: clock[0])
    runner = orr.Runner.__new__(orr.Runner)
    runner.github = Github(heads)
    runner.r = {'evidence_directory': 'd'}
    runner.check = lambda: None
    runner.stop_requested = lambda: None
    runner.pipeline_sleep = lambda s: clock.__setitem__(0, clock[0] + s)
    with pytest.raises(orr.Denied, match='HOSTED_PUBLICATION_WAIT_EXPIRED'):
        runner.await_any(('x.json',), seconds)
    return runner.github.calls, runner.github.probes, clock[0] - 1000.0


def test_the_ready_wait_reads_the_head_61_times_and_the_result_wait_21_on_a_simulated_clock(monkeypatch):
    reads, probes, elapsed = run_wait(monkeypatch, READY_WAIT, lambda n: 'a' * 40)      # a head that never moves
    assert (reads, probes) == (polls(READY_WAIT), orr.Runner.REPROBES) and reads == 61 and elapsed == READY_WAIT
    reads, probes, elapsed = run_wait(monkeypatch, RESULT_WAIT, lambda n: 'a' * 40)
    assert (reads, probes) == (polls(RESULT_WAIT), orr.Runner.REPROBES) and reads == 21 and elapsed == RESULT_WAIT
    assert polls(READY_WAIT) + polls(RESULT_WAIT) == 82      # the head reads alone: why a bound of 75 could never have covered the advertised waits


def test_each_distinct_head_costs_at_most_reprobes_file_probes_and_the_head_count_bounds_the_total(monkeypatch):
    for wait, heads_allowed in ((READY_WAIT, READY_HEADS), (RESULT_WAIT, RESULT_HEADS)):
        step = max(1, polls(wait) // heads_allowed)
        reads, probes, _ = run_wait(monkeypatch, wait, lambda n, s=step: 'h%d' % (n // s))      # the head advances evenly through the wait
        assert reads == polls(wait) and probes <= (heads_allowed + 1) * orr.Runner.REPROBES      # the initial head plus those observed


def test_the_derived_worst_case_with_its_reserve_fits_the_bound_the_screening_mode_actually_uses():
    items, total = worst_case()
    assert items['ready_head_reads'] == 61 and items['result_head_reads'] == 21 and items['registration_publication'] == 8 and items['owner_publication'] == 10
    assert total == 128
    source = open(orr.__file__, encoding='utf-8').read()
    assert "dict(bound=PIPELINE_GITHUB_BOUND) if r.get('mode') in (PIPELINE_MODE,CAPTURE_MODE,WINDOW_MODE,SV3_MODE)" in source      # this mode shares the pipeline bound
    assert orr.PIPELINE_GITHUB_BOUND == 180 and total + RESERVE <= orr.PIPELINE_GITHUB_BOUND
    assert orr.OWNER_PUBLICATION_RESERVE['requests'] >= publish_requests(2) + 4      # the final publication's own reserve covers its ten requests and four head reads


def test_a_wait_that_needs_more_requests_than_the_bound_is_a_stop_not_an_overrun():
    source = open('verification/ingestion_storage/operational_publication.py', encoding='utf-8').read()
    assert source.count("if self.requests>=self.bound:raise ValueError('GITHUB_REQUEST_BOUND')") == 2      # call and probe both stop at the bound


def test_the_command_and_connection_tiers_cover_the_measured_paths_with_failure_and_teardown_reserve():
    normal, teardown, diagnostic = orr.SV3_OWNER_LIMITS['commands']
    connections, connections_diagnostic = orr.SV3_OWNER_LIMITS['connections']
    assert (normal, teardown, diagnostic) == (96, 116, 132) and (connections, connections_diagnostic) == (10, 12)
    measured_commands, measured_connections = 55, 6      # the complete success path and the largest failure path of the disposable lifecycle (all ten scenarios <= these)
    assert measured_commands + 40 <= normal and measured_commands + 40 < teardown < diagnostic
    assert measured_connections + 3 <= connections < connections_diagnostic
    p_normal, p_teardown, p_diagnostic = orr.SV3_POLICY_OWNER_LIMITS['commands']
    assert (p_normal, p_teardown, p_diagnostic) == (44, 52, 60) and orr.SV3_POLICY_OWNER_LIMITS['connections'] == (4, 5)
    assert 39 + 5 <= p_normal      # the installation ceremony measured 39 commands on 3 connections
