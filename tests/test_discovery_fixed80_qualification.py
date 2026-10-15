from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from verification.discovery import r0_fixed80_qualification as q
from verification.direct_reference.refresh import Observation

@pytest.fixture(autouse=True)
def credential_free(monkeypatch):
    import os
    for key in list(os.environ):
        if 'DATABASE' in key or key.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):
            monkeypatch.delenv(key,raising=False)


def source(row,eligible=True):
    states=dict(reference='PRESENT_VALUE',status='PRESENT_VALUE',decision='NOT_PRESENT',decision_date='NOT_PRESENT')
    fields={'Reference':row['reference'],'Status':'Pending Consideration','Decision':None,'Decision Issued Date':None}
    obs=Observation(None,row['reference'],row['source_url'],fields,states,'UNKNOWN_UNMAPPED','a'*64,
                    {'Reference':row['reference'],'Status':'Pending Consideration'},b2_eligible=eligible)
    return dict(case=row['case'],reference=row['reference'],destination=row['source_url'],application_id=None,
        persistence=False,observation=asdict(obs),failure=None,requests=1,received_body_bytes=500,
        elapsed_seconds=1.0,supervisor_seconds=1.1,peak_owned_rss=100000,owned_processes_seen=1,
        live_owned_survivors=0,process_cleanup='CLOSED',supervisor_limit_hit=False)


def test_exact80_routes_and_no_arbitrary_input():
    rows=q.targets();assert len(rows)==80
    assert sum(x['council']=='bolton' for x in rows)==54
    assert {'73755','73748','73743','73742','73741'}<=set(x['reference'] for x in rows if x['council']=='bury')
    original=json.loads(Path('docs/design/stage4-r0-execution/recovery-preparation/comparison-80-manifest.json').read_text())
    assert {(r['council'],r['reference']) for r in rows}=={(r['council_code'],r['reference']) for r in original['identities']}
    with pytest.raises(ValueError):q.read(80,rows[0])
    with pytest.raises(ValueError):q.read(0,dict(rows[0],reference='OTHER'))
    assert not Path('.github/workflows/stage4-r0-fixed80-qualification-once.yml').exists()


def test_80_capacity_uses_actual_bounds_and_checkpoints_sparse_fields(tmp_path):
    calls=[];checkpoints=[]
    def reader(index,row):calls.append(row['reference']);return source(row,False)
    def checkpoint(result):
        path=tmp_path/f'{len(checkpoints):02}.json';q.durable_checkpoint(path,result);checkpoints.append(path)
    result=q.qualify(reader=reader,checkpoint=checkpoint,clock=lambda:0)
    assert len(calls)==len(checkpoints)==result['attempted']==80 and not result['not_attempted']
    assert result['requests']==80 and result['received_bytes']==40000
    assert all(x['observation_evidence']['field_states']['decision']=='NOT_PRESENT' for x in result['results'])
    assert all(x['site_relationship']==x['application_role']=='UNKNOWN' for x in result['results'])
    assert all(x['admission_readiness']=='WITHHELD_PENDING_EVIDENCE' for x in result['results'])
    assert not result['persistence'] and not result['admission_authorised']
    with pytest.raises(FileExistsError):q.durable_checkpoint(checkpoints[0],result['results'][0])


@pytest.mark.parametrize('change,stop',[
 ({'live_owned_survivors':1},'RESOURCE_OR_CLEANUP'),
 ({'requests':3},'RESOURCE_OR_CLEANUP'),
 ({'reference':'WRONG'},'HARD_OR_UNCLASSIFIED_FAILURE'),
 ({'destination':'https://wrong.invalid/'},'HARD_OR_UNCLASSIFIED_FAILURE'),
 ({'failure':'AMBIGUOUS_SOURCE_RESULT'},'HARD_OR_UNCLASSIFIED_FAILURE'),
 ({'failure':'PARSER_FAILURE'},'HARD_OR_UNCLASSIFIED_FAILURE'),
])
def test_unsafe_results_stop_before_next_call(change,stop):
    calls=[]
    def reader(i,row):calls.append(i);return dict(source(row),**change)
    out=q.qualify(reader=reader,checkpoint=lambda _:None,clock=lambda:0)
    assert calls==[0] and out['attempted']==1 and len(out['not_attempted'])==79
    assert out['stop_reason']==stop


def test_local_source_failure_continues_only_closed_certain_accounting():
    def reader(i,row):
        r=source(row)
        if i==0:r.update(failure='TIMEOUT',observation=None)
        return r
    out=q.qualify(reader=reader,checkpoint=lambda _:None,clock=lambda:0)
    assert out['attempted']==80 and out['results'][0]['admission_readiness']=='WITHHELD_PENDING_EVIDENCE'


def test_unknown_exception_no_next_call_and_budget_reservation():
    def raised(*_):raise RuntimeError('not exported')
    out=q.qualify(reader=raised,checkpoint=lambda _:None,clock=lambda:0)
    assert out['attempted']==1 and not out['accounting_complete'] and 'not exported' not in str(out)
    clock=iter([0,4400,4400]);out=q.qualify(reader=lambda *_:pytest.fail('no source'),checkpoint=lambda _:None,clock=lambda:next(clock))
    assert out['attempted']==0 and len(out['not_attempted'])==80


def test_checkpoint_failure_and_credentials_fail_closed():
    calls=[]
    def reader(i,row):calls.append(i);return source(row)
    def failed(_):raise OSError('disk unavailable')
    out=q.qualify(reader=reader,checkpoint=failed,clock=lambda:0)
    assert calls==[0] and out['stop_reason']=='CHECKPOINT_FAILURE_NO_NEXT_CALL'
    for key in ['DATABASE_URL','SUPABASE_SERVICE_KEY','OPENAI_API_KEY']:
        with pytest.raises(ValueError):q.credential_free({key:'synthetic'})


def test_shared_supervisor_delegation_not_new_transport(tmp_path):
    from verification.direct_reference import instrumented_probe as probe
    rows=q.targets();called=[]
    def supervised(case,path):
        called.append(case);path.write_text(json.dumps(source(rows[0])))
    with patch.object(probe,'supervised',supervised):
        assert q.read(0,rows[0])['reference']==rows[0]['reference']
    assert called==[rows[0]['case']]
    assert set(q.case_definitions())<=set(probe.CASES)
    import inspect
    assert "'verification.discovery.r0_fixed80_qualification' if case in FIXED80_CASES" in inspect.getsource(probe.supervised)
    with patch('verification.discovery.material_qualification.idox_worker',lambda row: row):
        assert q.worker(0)==rows[0]


def test_actual_supervisor_launches_fixed_worker_with_credential_free_env(tmp_path,monkeypatch):
    from unittest.mock import MagicMock
    from verification.direct_reference import instrumented_probe as probe
    import psutil
    row=q.targets()[0];launched=[]
    monkeypatch.setenv('GITHUB_ACTIONS','true');monkeypatch.setenv('RUNNER_ENVIRONMENT','github-hosted')
    monkeypatch.setenv('DATABASE_URL','synthetic-not-forwarded');monkeypatch.setenv('GITHUB_TOKEN','synthetic-not-forwarded')
    def popen(argv,**kw):
        launched.append((argv,kw))
        assert argv[1:6]==['-m','verification.discovery.r0_fixed80_qualification','--worker','--case',row['case']]
        assert set(kw['env'])=={'PATH','HOME','TMPDIR','LANG','PYTHONNOUSERSITE','PYTHONDONTWRITEBYTECODE','PLAYWRIGHT_BROWSERS_PATH'}
        assert kw['start_new_session'] is True and 'DATABASE_URL' not in kw['env'] and 'GITHUB_TOKEN' not in kw['env']
        Path(argv[argv.index('--output')+1]).write_text(json.dumps(source(row)))
        child=MagicMock(pid=999999,returncode=0);child.poll.return_value=0;child.wait.return_value=0
        return child
    import os
    original_read=Path.read_text
    def namespace_read(path,*a,**kw):
        return str(os.getpid())+' synthetic-stat' if str(path)=='/proc/self/stat' else original_read(path,*a,**kw)
    with patch.object(Path,'read_text',namespace_read),patch.object(probe.subprocess,'Popen',popen),patch.object(psutil,'Process',return_value=MagicMock()),patch.object(psutil,'wait_procs',return_value=([],[])):
        assert probe.supervised(row['case'],tmp_path/'audit.json')==0
    assert len(launched)==1
    audit=json.loads((tmp_path/'audit.json').read_text())
    assert audit['process_cleanup']=='CLOSED' and audit['live_owned_survivors']==0


def test_untouched27_matches_consumed_run_without_capped_or_bury_retry():
    import zipfile
    path=Path('docs/design/stage4-r0-execution/page-cap-correction/untouched27-manifest.json')
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='f99d86a5deb251f45c0787af295836aa948d8250d9f7b180062db229c6dc0e3d'
    plan=json.loads(path.read_text())
    with zipfile.ZipFile('tests/fixtures/discovery/r0-recovery-38744118357.zip') as z:
        consumed=json.loads(z.read('round.json'))
    assert plan['rows']==consumed['not_attempted'] and len(plan['rows'])==27
    assert all(x['council'] not in {'bolton','bury','trafford'} for x in plan['rows'])
    assert not any(x['council']=='manchester' and x['start']=='2026-09-17' for x in plan['rows'])
    arc=sum(x['council'] in {'manchester','rochdale','salford'} for x in plan['rows'])
    assert plan['limits']['requests']==arc*80+(27-arc)*10
    assert plan['limits']['bytes']==arc*20*1024*1024+(27-arc)*3_000_000


def test_independent_only_candidates_visible_not_primary_or_db_success():
    d=json.loads(Path('docs/design/stage4-r0-execution/page-cap-correction/independent-only-candidates.json').read_text())
    pairs={(x['council'],r) for x in d['windows'] for r in x['literal_references']}
    assert len(pairs)==d['reference_count']==283
    assert all(x['primary_detection']=='NOT_ESTABLISHED' and x['database_presence']=='UNKNOWN_NOT_QUERIED' for x in d['windows'])
    assert all(x['date_membership']=='UNKNOWN_NO_INDIVIDUAL_LITERAL_DATE' for x in d['windows'])
    assert not d['database_query_authorised'] and not d['admission_authorised']
