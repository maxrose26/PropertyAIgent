"""BROWSER_SOURCE_V2 execution budget (docs/design/execution-budget-20261026/SPEC.md).

Offline only: locator doubles, synthetic cgroup files and a local child process. No browser,
council, database, network or memory pressure.
"""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
from playwright.async_api import TimeoutError as LocatorTimeout

from verification.discovery import execution_budget as eb
from verification.discovery import four_council_release as r
from verification.discovery import finite_acceptance as finite
from verification.discovery.arcus_ui_audit import budget_bound
from verification.discovery.arcus_ui_config import UI_CASES, dated_config
from verification.discovery.arcus_ui_window import enumerate_ui, LOCAL_TIMEOUT
from verification.direct_reference import instrumented_probe as probe
from verification.ingestion_storage.memory_enforcement import MemoryUnavailable
from verification.ingestion_storage.operational_memory import OperationalMemory, LIMIT_PAIRS
from verification.ingestion_storage.operational_publication import canonical
from tests.test_discovery_four_council_proof import async_run
from tests.test_discovery_four_council_release import API, Memory, audit
from tests.test_discovery_arcus_ui import card

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_POPEN = subprocess.Popen
V2 = 'BROWSER_SOURCE_V2'
MiB = 1024 ** 2


@pytest.fixture(autouse=True)
def credential_free(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)


class Clock:
    def __init__(self, now=0.0):self.now = now
    def __call__(self):return self.now


# ---------------------------------------------------------------- deadline arithmetic

def test_selection_is_explicit_and_historical_by_default():
    assert eb.select(None) is eb.HISTORICAL and eb.HISTORICAL['worker_seconds'] == 45
    assert eb.HISTORICAL['source_memory_bytes'] == 1024 ** 3 and eb.HISTORICAL['aggregate_memory_bytes'] == 1536 * MiB
    v2 = eb.select(V2)
    assert (v2['navigation_seconds'], v2['ready_seconds'], v2['criteria_seconds'],
            v2['segment_poll_seconds'], v2['segment_click_seconds']) == (25, 20, 10, 8, 3)
    assert (v2['worker_seconds'], v2['source_outer_seconds'], v2['slot_active_seconds']) == (75, 80, 90)
    assert (v2['source_memory_bytes'], v2['aggregate_memory_bytes'], v2['controller_memory_bytes'],
            v2['rss_ceiling_bytes']) == (1536 * MiB, 2048 * MiB, 256 * MiB, 1536 * MiB)
    for bad in ('browser_source_v2', 'BROWSER_SOURCE_V3', '', 'HISTORICAL'):
        with pytest.raises(ValueError, match='EXECUTION_BUDGET'):eb.select(bad)


def test_budget_is_internally_consistent():
    v2 = eb.select(V2)
    observation = v2['worker_seconds'] - v2['finalisation_reserve_seconds']
    # The worker deadline is inside the source outer deadline, inside the slot allowance.
    assert observation < v2['worker_seconds'] < v2['source_outer_seconds'] < v2['slot_active_seconds']
    # Each step cap fits in the observation deadline; the deadline (not the sum) bounds the total.
    assert max(v2['navigation_seconds'], v2['ready_seconds'], v2['criteria_seconds'],
               v2['segment_poll_seconds'] + v2['segment_click_seconds']) < observation
    assert r.SUCCESSOR_V2_LIMITS['worker_seconds'] == 3 * v2['worker_seconds']
    assert r.SUCCESSOR_V2_LIMITS['active_seconds'] == 3 * v2['slot_active_seconds']
    assert r.SUCCESSOR_V2_LIMITS['slot_active_seconds'] == v2['slot_active_seconds']
    assert v2['slot_active_seconds'] + 160 + 10 < r.SUCCESSOR_V2_LIMITS['per_job_seconds']  # + publication + margin


@pytest.mark.parametrize('now,step,expected,truncated', [
    (0, 20, 20, False), (49.5, 20, 20, False), (50.5, 20, 19.5, True), (69.999, 3, .001, True)])
def test_cap_is_min_of_step_and_remaining(now, step, expected, truncated):
    clock = Clock();d = eb.Deadline(70, clock);clock.now = now
    assert d.cap(step) == pytest.approx(expected) and d.truncated is truncated
    assert d.cap_ms(step) == max(1, int(expected * 1000))


@pytest.mark.parametrize('now', [70, 70.001, 500])
def test_expired_deadline_refuses_any_wait(now):
    clock = Clock();d = eb.Deadline(70, clock);clock.now = now
    assert d.remaining() == 0
    with pytest.raises(eb.ObservationDeadline):d.cap(1)
    with pytest.raises(eb.ObservationDeadline):d.cap_ms(1)


@pytest.mark.parametrize('seconds', [0, -1, 601])
def test_deadline_seconds_bounded(seconds):
    with pytest.raises(ValueError):eb.Deadline(seconds)


# ---------------------------------------------------------------- reader waits

class Page:
    """Locator double recording every requested timeout; optional fault and clock advance."""

    def __init__(self, config, *, total=13, ready_fault=None, clock=None, step=0.0):
        self.config = config;self.segment = 0;self.total = total;self.calls = []
        self.ready_fault = ready_fault;self.clock = clock;self.step = step

    def record(self, name, kw):
        self.calls.append((name, kw.get('timeout')))
        if self.clock is not None:self.clock.now += self.step

    def locator(self, selector):
        page = self

        class Locator:
            async def wait_for(self, **kw):
                page.record('READY', kw)
                if page.ready_fault:raise page.ready_fault

            async def inner_text(self, **kw):
                page.record('MARKER', kw)
                last = min(page.total, page.segment * 10 + 10)
                return f'Showing {page.segment * 10 + 1} to {last} of {page.total} results'

            def filter(self, **kw):return self

            async def count(self):
                if selector == 'p:text-is("No results found")':return 0
                return 1 if page.segment * 10 + 10 < page.total else 0

            async def get_attribute(self, name):return '#'

            async def click(self, **kw):
                page.record('NEXT', kw);page.segment += 1
        return Locator()

    def get_by_label(self, label, exact=True):
        page = self

        class Label:
            async def input_value(self, **kw):
                from datetime import date
                page.record('CONTROL', kw)
                if label == 'Valid date from':return date.fromisoformat(page.config.start).strftime('%d/%m/%Y')
                if label == 'Valid date to':return date.fromisoformat(page.config.end).strftime('%d/%m/%Y')
                return ''
        return Label()

    def get_by_role(self, role, name, exact=True):
        page = self

        class Role:
            async def click(self, **kw):page.record('DISCLOSURE', kw)

            async def inner_text(self, **kw):
                page.record('CONTROL', kw)
                return 'Planning Applications' if name == 'Category' else 'Select an option'
        return Role()


CONFIG = dated_config(UI_CASES['discovery_rochdale_ui_window'], '2026-10-08', '2026-10-14')


def run(page, **kw):
    audit_value = {};stopped = asyncio.Event()

    async def cards(page, config):
        first = page.segment * 10
        values = [card(ref=f'TEST/{first + i:03}', key=f'a1DSl00000{first + i:08}',
                       valid='09/10/2026') for i in range(min(10, page.total - first))]
        for value in values:  # the shared card helper is Manchester-hosted
            value['links'][0]['href'] = value['links'][0]['href'].replace('arcusbe.manchester.gov.uk', config.host)
        return values
    with patch('verification.discovery.arcus_ui_window.read_cards', cards):
        async_run(enumerate_ui(page, audit_value, stopped, CONFIG, **kw))
    return audit_value


def budgeted(clock=None, seconds=70):
    return dict(budget=eb.select(V2), deadline=eb.Deadline(seconds, clock or Clock()))


def test_default_waits_are_the_historical_literals():
    page = Page(CONFIG);a = run(page)
    assert a['enumeration_evidence'] == 'COUNT_RECONCILED' and len(a['listing_records']) == 13
    assert page.calls[0] == ('READY', 10000) and page.calls[1] == ('DISCLOSURE', 3000)
    assert {t for n, t in page.calls if n == 'CONTROL'} == {1500}
    assert {t for n, t in page.calls if n == 'NEXT'} == {3000}
    assert {t for n, t in page.calls if n == 'MARKER'} == {None}  # unchanged: no explicit timeout
    assert 'stage_timings' not in a and 'execution_budget' not in a and 'observation_deadline' not in a


def test_default_path_never_imports_the_budget_module():
    code = ('import sys\nfrom verification.direct_reference import instrumented_probe\n'
            'from verification.discovery import arcus_ui_audit,criteria_containment,finite_acceptance\n'
            'assert instrumented_probe.budget_selection(None,"discovery_rochdale_ui_window") is None\n'
            'assert "verification.discovery.execution_budget" not in sys.modules\n')
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, check=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))


def test_budgeted_waits_use_v2_caps_and_fixed_stage_timings():
    page = Page(CONFIG);a = run(page, **budgeted())
    assert a['enumeration_evidence'] == 'COUNT_RECONCILED' and len(a['listing_segments']) == 2
    assert page.calls[0] == ('READY', 20000) and page.calls[1] == ('DISCLOSURE', 3000)
    assert {t for n, t in page.calls if n == 'CONTROL'} == {1500}
    assert {t for n, t in page.calls if n == 'NEXT'} == {3000}
    assert all(0 < t <= 8000 for n, t in page.calls if n == 'MARKER')
    timings = a['stage_timings']
    assert set(timings) == {'READY', 'CRITERIA', 'SEGMENT'} <= set(eb.STAGES)
    assert len(timings['SEGMENT']) == 2 and all(type(v) is int and v >= 0 for v in timings['SEGMENT'])
    assert 'observation_deadline' not in a and a.get('listing_failure') is None


def test_full_untruncated_ready_timeout_keeps_the_typed_local_timeout():
    page = Page(CONFIG, ready_fault=LocatorTimeout('synthetic'))
    a = run(page, **budgeted())
    assert page.calls == [('READY', 20000)]
    assert a['listing_failure'] == 'TimeoutError' and a['completeness'] == 'FAILED'
    assert a['criteria_control_timeout']['operation'] == 'RESULT_MARKER_VISIBLE' and 'observation_deadline' not in a
    failures = []
    a.update(failure=None, safety_failure=False, safety_events=[])
    probe.classify_ui_enumeration(a, failures.append)
    assert failures == [] and a['source_contract_failure'] == LOCAL_TIMEOUT


def test_near_expiry_truncates_the_ready_wait_and_is_never_the_allowlisted_timeout():
    clock = Clock(68.5)
    page = Page(CONFIG, ready_fault=LocatorTimeout('synthetic'))
    a = run(page, budget=eb.select(V2), deadline=_deadline_at(clock, 70, 0))
    assert page.calls == [('READY', 1500)]
    assert a['listing_failure'] == 'ObservationDeadline' and a['observation_deadline'] is True
    assert 'criteria_control_timeout' not in a and a['deadline_truncated_operation'] == 'RESULT_MARKER_VISIBLE'
    failures = []
    a.update(failure=None, safety_failure=False, safety_events=[])
    probe.classify_ui_enumeration(a, failures.append)
    assert failures == ['OBSERVATION_DEADLINE'] and 'source_contract_failure' not in a


def _deadline_at(clock, seconds, started):
    now = clock.now;clock.now = started
    d = eb.Deadline(seconds, clock);clock.now = now
    return d


def test_expired_deadline_stops_before_any_wait():
    clock = Clock(10);d = _deadline_at(clock, 70, 0);clock.now = 71
    page = Page(CONFIG);a = run(page, budget=eb.select(V2), deadline=d)
    assert page.calls == [] and a['listing_failure'] == 'ObservationDeadline' and a['completeness'] == 'FAILED'


def test_criteria_checks_share_one_ten_second_total():
    # Every control call takes 4s of the fake clock: 10s total admits the disclosure and two
    # controls (each still capped at its own step), then refuses before the next wait.
    clock = Clock(0);d = _deadline_at(clock, 70, 0)
    page = Page(CONFIG, clock=clock, step=4)
    a = run(page, budget=eb.select(V2), deadline=d)
    names = [n for n, _ in page.calls]
    assert names[:4] == ['READY', 'DISCLOSURE', 'CONTROL', 'CONTROL'] and len(names) == 4
    assert page.calls[1] == ('DISCLOSURE', 3000) and page.calls[2] == ('CONTROL', 1500) and page.calls[3] == ('CONTROL', 1500)
    assert a['listing_failure'] == 'ObservationDeadline' and a['applied_interval'] is None


def test_criteria_scope_truncation_that_times_out_is_budget_expiry():
    clock = Clock(0);d = _deadline_at(clock, 70, 0)

    class SlowPage(Page):
        def get_by_role(self, role, name, exact=True):
            page = self

            class Role:
                async def click(self, **kw):
                    page.record('DISCLOSURE', kw);clock.now = 9.2  # 0.8s of the criteria total left

                async def inner_text(self, **kw):
                    page.record('CONTROL', kw);raise LocatorTimeout('synthetic')
            return Role()

        def get_by_label(self, label, exact=True):
            page = self

            class Label:
                async def input_value(self, **kw):
                    page.record('CONTROL', kw);raise LocatorTimeout('synthetic')
            return Label()
    page = SlowPage(CONFIG);a = run(page, budget=eb.select(V2), deadline=d)
    assert page.calls[-1] == ('CONTROL', 800)
    assert a['listing_failure'] == 'ObservationDeadline' and 'criteria_control_timeout' not in a
    assert a['deadline_truncated_operation'] == 'VALID_FROM'


def test_budget_and_deadline_are_selected_together():
    with pytest.raises(ValueError, match='budget selection'):
        async_run(enumerate_ui(Page(CONFIG), {}, asyncio.Event(), CONFIG, budget=eb.select(V2)))
    with pytest.raises(ValueError, match='budget selection'):
        async_run(enumerate_ui(Page(CONFIG), {}, asyncio.Event(), CONFIG, deadline=eb.Deadline(70)))


# ---------------------------------------------------------------- validators

def complete(**changes):
    value = audit(1)
    value.update(changes)
    return value


def declared(**changes):
    return complete(execution_budget=V2, stage_timings={'NAVIGATION': 1200, 'READY': 900, 'CRITERIA': 400, 'SEGMENT': [300]}, **changes)


def test_validator_bound_follows_the_caller_selected_budget():
    row = r.ROWS[1]
    assert finite.classify(row, complete()) == 'COMPLETE'
    assert finite.classify(row, complete(supervisor_seconds=60)) == 'UNKNOWN'          # historical 45s
    assert finite.classify(row, declared(supervisor_seconds=60), execution_budget=V2) == 'COMPLETE'
    assert finite.classify(row, declared(supervisor_seconds=75.5), execution_budget=V2) == 'UNKNOWN'
    # A historical audit cannot be read under V2, and a V2 audit cannot be read as historical.
    assert finite.classify(row, complete(), execution_budget=V2) == 'UNKNOWN'
    assert finite.classify(row, declared()) == 'UNKNOWN'


@pytest.mark.parametrize('timings', [
    None, [], {'NETWORK_IDLE': 1}, {'READY': 1.5}, {'READY': -1}, {'READY': 75001}, {'READY': True},
    {'SEGMENT': 300}, {'SEGMENT': []}, {'SEGMENT': [1] * 7}, {'SEGMENT': ['1']}, {'NAVIGATION': [1]}])
def test_stage_timings_are_fixed_names_and_bounded(timings):
    with pytest.raises(ValueError):budget_bound(dict(execution_budget=V2, stage_timings=timings), V2)


def test_default_bound_refuses_budget_claims():
    assert budget_bound({}) == 45
    for claim in ({'execution_budget': V2}, {'stage_timings': {}}, {'execution_budget': None}):
        with pytest.raises(ValueError):budget_bound(claim)
    assert budget_bound(dict(execution_budget=V2, stage_timings={}), V2) == 75


def test_containment_eligibility_follows_the_selected_budget():
    from tests.test_discovery_three_council_isolation import local_audit
    from verification.discovery.criteria_containment import eligible
    row = r.ROWS[1]
    historical = local_audit(1)
    assert eligible(row, historical) and not eligible(row, historical, execution_budget=V2)
    budgeted_audit = local_audit(1, execution_budget=V2)
    assert budgeted_audit['source_contract_failure'] == LOCAL_TIMEOUT
    assert eligible(row, budgeted_audit, execution_budget=V2) and not eligible(row, budgeted_audit)
    assert not eligible(row, dict(budgeted_audit, supervisor_seconds=76), execution_budget=V2)


# ---------------------------------------------------------------- supervisor

def child_writing(audit_value, sleep=0):
    def popen(command, **kwargs):
        output = command[command.index('--output') + 1]
        popen.commands.append(command)
        code = f'import json,time\ntime.sleep({sleep})\nopen({output!r},"w").write({json.dumps(json.dumps(audit_value))})'
        return ORIGINAL_POPEN([sys.executable, '-c', code], **kwargs)
    popen.commands = []
    return popen


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true');monkeypatch.setenv('RUNNER_ENVIRONMENT', 'github-hosted')


def supervise(tmp_path, popen, **kw):
    out = tmp_path / 'out.json'
    with patch.object(probe.subprocess, 'Popen', popen), patch('builtins.print'):
        probe.supervised('discovery_rochdale_ui_window', out, window=('2026-10-08', '2026-10-14'), **kw)
    return json.loads(out.read_text())


def test_supervisor_passes_budget_and_requires_the_declaration(hosted, tmp_path):
    base = dict(case='discovery_rochdale_ui_window', failure=None, persistence=False)
    popen = child_writing(dict(base, execution_budget=V2, stage_timings={}))
    value = supervise(tmp_path, popen, execution_budget=V2)
    assert popen.commands[0][-2:] == ['--execution-budget', V2]
    assert value['failure'] is None and value['supervisor_limit_hit'] is False and value['process_cleanup'] == 'CLOSED'
    (tmp_path / 'b').mkdir();(tmp_path / 'c').mkdir()
    popen = child_writing(base)
    value = supervise(tmp_path / 'b', popen, execution_budget=V2)
    assert value['failure'] == 'EXECUTION_BUDGET_MISMATCH'
    popen = child_writing(base)
    value = supervise(tmp_path / 'c', popen)
    assert '--execution-budget' not in popen.commands[0] and value['failure'] is None  # historical path


def test_supervisor_deadline_comes_from_the_selected_budget(hosted, tmp_path, monkeypatch):
    monkeypatch.setitem(eb.BUDGETS, V2, dict(eb.BROWSER_SOURCE_V2, worker_seconds=1))
    popen = child_writing(dict(case='discovery_rochdale_ui_window', failure=None, execution_budget=V2), sleep=20)
    value = supervise(tmp_path, popen, execution_budget=V2)
    assert value['supervisor_limit_hit'] is True and value['failure'] == 'SUPERVISOR_BOUND_OR_CLEANUP'
    assert value['supervisor_seconds'] < 10 and value['live_owned_survivors'] == 0


@pytest.mark.parametrize('case,name', [('trafford', V2), ('discovery_rochdale_ui_window', 'UNKNOWN'),
                                       ('discovery_rochdale_ui_window', 2)])
def test_supervisor_refuses_unsupported_budget_selection(hosted, tmp_path, case, name):
    with pytest.raises(ValueError):
        probe.supervised(case, tmp_path / 'x.json', execution_budget=name)
    assert not (tmp_path / 'x.json').exists()


# ---------------------------------------------------------------- memory enforcement

def kernel(tmp_path, source, aggregate):
    m = OperationalMemory.__new__(OperationalMemory);m.source_bytes = source;m.aggregate_bytes = aggregate
    m.root = tmp_path / 'scope';m.controller = m.root / 'controller';m.source = m.root / 'source'
    for path, limit in [(m.root, aggregate), (m.controller, 256 * MiB), (m.source, source)]:
        path.mkdir(parents=True, exist_ok=True)
        for name, value in {'memory.max': str(limit), 'memory.swap.max': '0', 'memory.oom.group': '1',
                            'memory.current': '1', 'memory.peak': '2',
                            'memory.events': 'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n'}.items():
            (path / name).write_text(value)
    return m


def test_only_the_two_exact_limit_pairs_are_accepted():
    assert LIMIT_PAIRS == ((1024 ** 3, 1536 * MiB), (1536 * MiB, 2048 * MiB))
    for source, aggregate in [(1536 * MiB, 1536 * MiB), (1024 ** 3, 2048 * MiB), (2048 * MiB, 2048 * MiB), (1, 2)]:
        with pytest.raises(MemoryUnavailable, match='MEMORY_LIMIT_SELECTION'):
            OperationalMemory(source_bytes=source, aggregate_bytes=aggregate)


@pytest.mark.parametrize('group,value,code', [
    ('source', 1024 ** 3, 'MEMORY_ENFORCEMENT_LOST'), ('source', 2048 * MiB, 'MEMORY_ENFORCEMENT_LOST'),
    ('aggregate', 1536 * MiB, 'EXACT_AGGREGATE_MEMORY_LIMIT'), ('controller', 512 * MiB, 'MEMORY_ENFORCEMENT_LOST')])
def test_v2_snapshot_refuses_any_mismatched_limit(tmp_path, group, value, code):
    m = kernel(tmp_path, 1536 * MiB, 2048 * MiB);m.snapshot()
    path = {'source': m.source, 'aggregate': m.root, 'controller': m.controller}[group]
    (path / 'memory.max').write_text(str(value))
    with pytest.raises(MemoryUnavailable, match=code):m.snapshot()


def test_v2_limit_event_is_still_fatal(tmp_path):
    m = kernel(tmp_path, 1536 * MiB, 2048 * MiB)
    (m.source / 'memory.events').write_text('low 0\nhigh 0\nmax 1\noom 0\noom_kill 0\noom_group_kill 0\n')
    with pytest.raises(MemoryUnavailable, match='MEMORY_LIMIT_HIT'):m.snapshot()


def test_historical_instance_rejects_v2_groups(tmp_path):
    m = kernel(tmp_path, 1536 * MiB, 2048 * MiB);m.source_bytes = 1024 ** 3;m.aggregate_bytes = 1536 * MiB
    with pytest.raises(MemoryUnavailable, match='EXACT_AGGREGATE_MEMORY_LIMIT'):m.snapshot()


def owner_context(monkeypatch, source, aggregate, budget):
    files = {'/proc/self/cgroup': '0::/user.slice/propertyaigent-operational-once.scope/source\n'}
    base = '/sys/fs/cgroup/user.slice/propertyaigent-operational-once.scope'
    for path, limit in ((base + '/source', source), (base, aggregate)):
        files.update({path + '/memory.max': str(limit), path + '/memory.swap.max': '0', path + '/memory.oom.group': '1'})
    monkeypatch.setattr(Path, 'read_text', lambda self, *a, **k: files[str(self)])
    with patch.dict(os.environ, {'PATH': '/usr/bin:/bin', 'HOME': '/tmp'}, clear=True):
        return r.owner_source_context(budget)


@pytest.mark.parametrize('source,aggregate,budget,ok', [
    (1024 ** 3, 1536 * MiB, None, True), (1536 * MiB, 2048 * MiB, V2, True),
    (1536 * MiB, 2048 * MiB, None, False), (1024 ** 3, 1536 * MiB, V2, False),
    (1536 * MiB, 1536 * MiB, V2, False), (1024 ** 3, 2048 * MiB, V2, False), (1536 * MiB, 2048 * MiB, 'X', False)])
def test_owner_source_context_requires_the_exact_selected_limits(monkeypatch, source, aggregate, budget, ok):
    if ok:assert owner_context(monkeypatch, source, aggregate, budget) is True
    else:
        with pytest.raises(r.Stop, match='SOURCE_MEMORY_ENFORCEMENT'):owner_context(monkeypatch, source, aggregate, budget)


# ---------------------------------------------------------------- release selection

def v2_registration(**kw):
    issued = r.now() - timedelta(minutes=1)
    return r.render('three-council-v2-fixture', 'a' * 40, 'b' * 40, '1' * 40, issued.isoformat(),
                    (issued + timedelta(hours=2)).isoformat(), released=True, version=r.SUCCESSOR_V2_VERSION, **kw)


def test_historical_manifests_and_bindings_are_byte_identical():
    for version, path in [(r.VERSION, 'docs/design/four-council-release-20261022/manifest.json'),
                          (r.SUCCESSOR_VERSION, 'docs/design/three-council-isolation-20261022/manifest.json')]:
        assert canonical(r.manifest(version=version)) == (ROOT / path).read_bytes().strip()
    assert r.manifest(successor=True) == r.manifest(version=r.SUCCESSOR_VERSION)
    assert r.manifest() == r.manifest(version=r.VERSION)
    assert 'execution_budget' not in r.LIMITS and 'execution_budget' not in r.SUCCESSOR_LIMITS
    assert (r.LIMITS['source_memory_bytes'], r.LIMITS['aggregate_memory_bytes'], r.LIMITS['slot_active_seconds']) == (1024 ** 3, 1536 * MiB, 60)
    assert set(r.dependencies(successor=True)) == set(r.DEPENDENCIES + r.SUCCESSOR_DEPENDENCIES)
    assert set(r.dependencies()) == set(r.DEPENDENCIES)
    assert r.memory_limits(r.VERSION) == r.memory_limits(r.SUCCESSOR_VERSION) == {}
    assert r.budget_of(r.SUCCESSOR_VERSION) is eb.HISTORICAL
    v1_launcher = (ROOT / 'docs/design/four-council-release-20261022/owner-launch.sh').read_text()
    assert '-p MemoryMax=1610612736 ' in v1_launcher and 'aggregate_bytes' not in v1_launcher


def test_v2_manifest_registration_and_permit():
    m = r.manifest(version=r.SUCCESSOR_V2_VERSION)
    assert canonical(m) == (ROOT / 'docs/design/execution-budget-20261026/manifest.json').read_bytes()
    v1 = r.manifest(version=r.SUCCESSOR_VERSION)
    assert {k: v for k, v in m.items() if k not in ('version', 'limits')} == {k: v for k, v in v1.items() if k not in ('version', 'limits')}
    changed = {k for k in m['limits'] if m['limits'][k] != v1['limits'].get(k)}
    assert changed == {'worker_seconds', 'active_seconds', 'slot_active_seconds', 'source_memory_bytes',
                       'aggregate_memory_bytes', 'execution_budget'}
    for unchanged in ('requests', 'mixed_source_bytes', 'per_job_seconds', 'setup_seconds', 'package_seconds'):
        assert m['limits'][unchanged] == v1['limits'][unchanged]
    reg = v2_registration()
    assert reg['stop_treatment'] == r.SUCCESSOR_V2_PERMIT != r.SUCCESSOR_PERMIT
    assert {'verification/discovery/execution_budget.py', 'docs/design/execution-budget-20261026/owner-launch.sh',
            'docs/design/execution-budget-20261026/manifest.json'} <= set(reg['dependencies'])
    assert r.validate(reg, checkout=False) == reg
    assert r.control(reg, enabled=True)['stop_treatment'] == r.SUCCESSOR_V2_PERMIT
    assert r.memory_limits(r.SUCCESSOR_V2_VERSION) == dict(source_bytes=1536 * MiB, aggregate_bytes=2048 * MiB)


@pytest.mark.parametrize('field,value', [
    ('version', 'THREE_COUNCIL_SOURCE_RELEASE_V3'), ('stop_treatment', r.SUCCESSOR_PERMIT)])
def test_v2_registration_tampering_is_refused(field, value):
    reg = v2_registration();reg[field] = value
    with pytest.raises(r.Stop, match='REGISTRATION_VERSION|REGISTRATION_INACTIVE_OR_CHANGED'):r.validate(reg, checkout=False)


def test_v2_registration_cannot_carry_other_limits():
    reg = v2_registration()
    for key, value in [('source_memory_bytes', 1024 ** 3), ('aggregate_memory_bytes', 1536 * MiB),
                       ('slot_active_seconds', 60), ('execution_budget', None)]:
        tampered = deepcopy(reg);tampered['manifest']['limits'][key] = value
        with pytest.raises(r.Stop, match='REGISTRATION_INACTIVE_OR_CHANGED'):r.validate(tampered, checkout=False)
    with pytest.raises(r.Stop, match='REGISTRATION_VERSION'):r.selected_version(True, r.VERSION)


def test_source_command_and_outer_deadline_follow_the_version(tmp_path):
    class Fake:source = tmp_path / 'source'
    v2 = r.Source(Fake(), v2_registration(), tmp_path)
    assert v2.command(1, tmp_path / 'o')[-3:] == ['--three-council-successor', '--execution-budget', V2]
    from tests.test_discovery_three_council_isolation import registration as v1_registration
    v1 = r.Source(Fake(), v1_registration(), tmp_path)
    assert v1.command(1, tmp_path / 'o')[-1] == '--three-council-successor'
    assert '--execution-budget' not in v1.command(1, tmp_path / 'o')
    assert r.budget_of(r.SUCCESSOR_V2_VERSION)['source_outer_seconds'] == 80 and eb.HISTORICAL['source_outer_seconds'] == 49


def test_v2_source_outer_deadline_is_enforced(tmp_path):
    """The outer deadline stops a running child at 80s (fake clock), never earlier at 49s."""
    clock = Clock(0)
    (tmp_path / 'source').mkdir()
    for name, value in {'cgroup.kill': '', 'cgroup.events': 'populated 0\n'}.items():(tmp_path / 'source' / name).write_text(value)

    class Memory_:
        source = tmp_path / 'source';finalisation_only = False
        def snapshot(self):clock.now += 10

    class Child:
        returncode = None
        def poll(self):return None
        def wait(self, timeout=None):self.returncode = -9

    seen = []
    source = r.Source(Memory_(), v2_registration(), tmp_path, clock=clock, sleep=lambda s: seen.append(clock.now))
    with patch.object(r.subprocess, 'Popen', lambda *a, **k: Child()):
        with pytest.raises(r.SourceFailure) as raised:source.run(1, lambda: None)
    assert raised.value.primary['code'] == 'SOURCE_OUTER_DEADLINE'
    assert max(seen) >= 49 and 80 <= clock.now < 100  # survived the historical 49s, stopped at 80s


def test_v2_launcher_slot_and_worker_bounds(tmp_path):
    reg = v2_registration()
    launch = r.Launcher(reg, tmp_path, github=None, memory=Memory(tmp_path), source=None)
    assert launch.successor and launch.limits is r.SUCCESSOR_V2_LIMITS and launch.budget['name'] == V2
    assert launch.indices == (1, 2, 3)
    accepted = launch.accept(1, declared(supervisor_seconds=74.9))
    assert accepted == 'COMPLETE'
    with pytest.raises(r.Stop, match='SOURCE_TIME_ACCOUNTING'):launch.accept(1, declared(supervisor_seconds=75.1))
    assert launch.accept(1, complete(supervisor_seconds=10)) != 'COMPLETE'  # undeclared: not V2 evidence
    from tests.test_discovery_three_council_isolation import registration as v1_registration
    (tmp_path / 'v1').mkdir()
    historical = r.Launcher(v1_registration(), tmp_path / 'v1', github=None, memory=Memory(tmp_path / 'v1'), source=None)
    with pytest.raises(r.Stop, match='SOURCE_TIME_ACCOUNTING'):historical.accept(1, complete(supervisor_seconds=46))
    assert historical.budget is eb.HISTORICAL


def test_next_allocation_reserves_the_v2_slot_allowance(tmp_path):
    launch = r.Launcher(v2_registration(), tmp_path, github=None, memory=Memory(tmp_path), source=None)
    launch.active_seconds = 270 - 90 + 1
    with pytest.raises(r.Stop, match='NEXT_ACTIVE_ALLOCATION'):launch.next_budget(2)


@pytest.mark.parametrize('successor,budget,code', [
    (False, V2, 'CHILD_EXECUTION_BUDGET'), (True, 'BROWSER_SOURCE_V3', 'CHILD_EXECUTION_BUDGET'),
    (True, 'historical', 'CHILD_EXECUTION_BUDGET')])
def test_worker_refuses_unselected_budgets(tmp_path, successor, budget, code):
    with patch.dict(os.environ, {'PATH': '/usr/bin:/bin'}, clear=True):
        with pytest.raises(r.Stop, match=code):r.worker(1, tmp_path / 'o', tmp_path / 'source', successor=successor, execution_budget=budget)


def test_v2_launcher_script_is_v2_only_and_derives_the_ceiling():
    script = (ROOT / 'docs/design/execution-budget-20261026/owner-launch.sh').read_text()
    assert "V2_REGISTRATION_ONLY" in script and '-p "MemoryMax=${aggregate_bytes}"' in script
    assert 'test "$aggregate_bytes" = 2147483648' in script and '-p MemorySwapMax=0 -p OOMPolicy=kill' in script
    assert 'MemoryMax=1610612736' not in script
    subprocess.run(['bash', '-n', str(ROOT / 'docs/design/execution-budget-20261026/owner-launch.sh')], check=True)
