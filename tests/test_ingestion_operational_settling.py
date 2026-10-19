"""The settled successor: ONE fixed settling period between activation and the first restricted contact; non-secret first-contact intervals; unused authority and namespace; unchanged ceilings."""
import json,re,time,types
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_controller import DatabaseBudget,Denied
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_runner import Runner,SETTLED_MODE


def make(tmp_path,mode=SETTLED_MODE):
    registration=dict(expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),revision='a'*40,controller_sha256='b'*64,manifest_sha256='c'*64,evidence_head='1'*40,
                      evidence_directory='docs/design/ingestion-operational-execution-fixture',mode=mode)
    tmp_path.mkdir(parents=True,exist_ok=True);journal=Journal(tmp_path/"j")
    runner=Runner(registration,journal,lambda:None,source_reader=lambda r:None,github=types.SimpleNamespace(check=None,requests=0,mutation_uncertain=False),url_factory=lambda r,p:'',identity='postgres')
    return runner,journal


class Clock:
    """A virtual clock: sleeping advances it, so a 30 s interval costs no real time."""
    def __init__(self):self.offset=0.0;self.sleeps=[]
    def monotonic(self):return time.monotonic()+self.offset
    def sleep(self,seconds):self.sleeps.append(seconds);self.offset+=seconds


def events(journal):return [json.loads(l) for l in journal.file.read_text().splitlines()]


def test_the_interval_is_fixed_thirty_seconds_and_only_in_the_settled_mode(tmp_path):
    assert orr.SETTLE_SECONDS==30
    settled,_=make(tmp_path/'a');plain,_=make(tmp_path/'b',mode='REQUIRED_CAPTURE_SCREENING');matrix,_=make(tmp_path/'c',mode=orr.MATRIX_MODE)
    assert settled.settle_seconds==30 and settled.authority==orr.SETTLED_AUTHORITY and plain.settle_seconds==0 and plain.authority==orr.AUTHORITY and matrix.settle_seconds==0


def test_settle_waits_in_checked_one_second_steps_and_records_the_interval(tmp_path,monkeypatch):
    runner,journal=make(tmp_path);clock=Clock();checks=[]
    monkeypatch.setattr(orr,'time',types.SimpleNamespace(monotonic=clock.monotonic,sleep=clock.sleep,time=time.time,perf_counter=time.perf_counter))
    runner.settle_sleep=clock.sleep;runner.check=lambda:checks.append(1)
    runner.settle()
    assert all(0<s<=1.0 for s in clock.sleeps) and 29.9<=sum(clock.sleeps)<=30.1 and len(checks)>=30          # every step is checked against stop / expiry / deadlines
    started,completed=[e for e in events(journal) if e['event'] in ('settling_started','settling_completed')]
    assert started['payload']=={'planned_seconds':30,'interval_status':'EXPERIMENTAL_NOT_A_PROVIDER_GUARANTEE','restricted_contacts_so_far':0}
    assert completed['payload']['planned_seconds']==30 and completed['payload']['elapsed_seconds']>=30 and runner.operation_phase=='CREDENTIAL_SETTLING'


def test_a_stop_during_the_interval_ends_it_at_once(tmp_path,monkeypatch):
    runner,journal=make(tmp_path);clock=Clock();count=[]
    runner.settle_sleep=clock.sleep
    monkeypatch.setattr(orr,'time',types.SimpleNamespace(monotonic=clock.monotonic,sleep=clock.sleep,time=time.time,perf_counter=time.perf_counter))
    def check():
        count.append(1)
        if len(count)==4:raise Denied('MANUAL_STOP_OR_CONTROLLER_DEADLINE')
    runner.check=check
    with pytest.raises(Denied):runner.settle()
    assert sum(clock.sleeps)<=3.0 and 'settling_completed' not in [e['event'] for e in events(journal)]


def test_no_settling_outside_the_settled_mode_and_nothing_connects_while_it_runs(tmp_path):
    plain,journal=make(tmp_path,mode='REQUIRED_CAPTURE_SCREENING');plain.settle()
    assert 'settling_started' not in (journal.file.read_text() if journal.file.exists() else '')
    source=Path('verification/ingestion_storage/operational_runner.py').read_text()
    import ast;fn=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='settle'][0];fn.body=fn.body[1:];body=ast.unparse(fn)      # the code, without its docstring
    assert 'connect' not in body.replace('connect_timeout','') and 'engine' not in body and 'slot' not in body and 'owner.' not in body      # the interval touches no database object at all


def test_the_interval_fits_the_existing_budgets_with_the_cleanup_reserves_intact():
    d=orr.DEFAULT_DEADLINES
    observed_lifecycle_to_failure=8.0                     # the consumed run: 7.66 s active from first admin connection to the stop, including teardown
    lifecycle_allowance=60.0                              # a generous allowance for preflight, install, role settings, mapping, activation, qualification
    assert orr.SETTLE_SECONDS+lifecycle_allowance<=d['admin_pre']-100                      # admin phase: 90 s used of 210 s before the teardown reserve begins
    remaining_for_capture_and_screening=d['job']-orr.SETTLE_SECONDS-lifecycle_allowance
    assert remaining_for_capture_and_screening>=300                                         # the job limit still leaves >= 300 s (the source observation itself is capped at 45 s)
    assert d['job']+d['diagnostic_window']<=d['diagnostic_total']<480                       # the failure window and backstops are unchanged
    assert observed_lifecycle_to_failure+orr.SETTLE_SECONDS<d['admin_pre']


def test_first_contact_intervals_are_recorded_once_per_role_and_are_non_secret():
    now=time.monotonic();timeline={'r':{'password_committed':now-40,'mapped':now-39,'activated':now-35}}
    budget=DatabaseBudget();budget.timeline=timeline;budget.settle_seconds=30;budget.attempts=1
    first=budget.first_contact('r')
    assert first['first_contact'] is True and 40<=first['since_password_commit_seconds']<41 and 35<=first['since_activation_seconds']<36 and 39<=first['since_mapping_seconds']<40
    assert budget.first_contact('r')=={} and budget.first_contact('unknown')=={}
    assert timeline['r']['first_contact_intervals']['settle_seconds_planned']==30 and set(json.dumps(first))>=set('{}')
    assert not re.search(r'postgresql|password=|://',json.dumps(timeline['r']['first_contact_intervals']))


def test_the_authority_and_namespace_are_unused_and_distinct_from_every_earlier_one():
    sources=''.join(p.read_text() for p in Path('verification/ingestion_storage').glob('*.py'))
    authorities=set(re.findall(r"AUTHORISE_[A-Z0-9_]+",sources))
    assert orr.SETTLED_AUTHORITY in authorities and sum(1 for a in re.findall(r"AUTHORISE_[A-Z0-9_]+",sources) if a==orr.SETTLED_AUTHORITY)==1
    assert not any(a!=orr.SETTLED_AUTHORITY and (a.startswith(orr.SETTLED_AUTHORITY) or orr.SETTLED_AUTHORITY.startswith(a)) for a in authorities)
    states={m for m in re.findall(r"operational-[a-z-]+-20261\d{3}",sources)}
    assert orr.SETTLED_STATE not in states-{orr.SETTLED_STATE} and orr.SETTLED_STATE.endswith('20261019') and orr.SETTLED_STATE!=orr.SETTLED_PREDECESSOR['state_directory']
    assert orr.SETTLED_AUTHORITY!=orr.AUTHORITY


def test_settle_sits_between_activation_and_the_first_restricted_slot_in_setup():
    import ast
    tree=ast.parse(Path('verification/ingestion_storage/operational_runner.py').read_text())
    setup=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='setup'][0]
    calls=[(n.lineno,ast.unparse(n.func)) for n in ast.walk(setup) if isinstance(n,ast.Call)]
    line=lambda name:min(l for l,f in calls if f==name)
    assert line('self.owner.map_and_activate')<line('self.settle')<line('self.slot')<line('self.owner.register')      # activation, then the interval, then the first contact, then any grant
    assert sum(1 for l,f in calls if f=='self.slot')==1                                                             # the only slot in setup is the qualification slot


def test_the_settled_grants_are_not_covered_by_the_consumed_cleanup_tool():
    # Disclosed rather than hidden: the consumed revoke-only cleanup names one earlier grant. For the settled run the failure path (invalidate_failure + teardown) is the invalidation.
    src=Path('verification/ingestion_storage/operational_cleanup.py').read_text()
    assert orr.SETTLED_AUTHORITY not in src and "AUTHORISE_BOLTON_CAPTURE_QUEUE_ONCE_20261018_CAPTURE" in src


def test_the_owner_stop_file_ends_the_interval_at_the_next_step(tmp_path,monkeypatch):
    runner,journal=make(tmp_path);clock=Clock()
    monkeypatch.setattr(orr,'time',types.SimpleNamespace(monotonic=clock.monotonic,sleep=clock.sleep,time=time.time,perf_counter=time.perf_counter))
    runner.check=lambda:None
    def sleep(seconds):
        clock.sleep(seconds)
        if len(clock.sleeps)==2:(journal.root/'STOP').write_text('stop')
    runner.settle_sleep=sleep
    with pytest.raises(Denied):runner.settle()
    assert len(clock.sleeps)==2 and 'settling_completed' not in [e['event'] for e in events(journal)]
