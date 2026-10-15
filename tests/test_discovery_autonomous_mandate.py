"""Offline finite bindings; synthetic evidence explicitly, no live calls."""
import hashlib,json,os,time
from pathlib import Path
from unittest.mock import patch
import pytest,yaml
from verification.discovery import r0_mandate as m, selective5 as s, selective5_binding as b
from tests.test_discovery_r0_registered_scopes import context
from tests.test_discovery_admission import engine
from tests.test_discovery_bolton53_admission import synthetic

@pytest.fixture(autouse=True)
def clean(monkeypatch):
 for k in list(os.environ):
  if 'DATABASE' in k or k.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):monkeypatch.delenv(k,raising=False)

def test_frozen17_budget_and_no_replays():
 ps=list(m.PROFILES.values());assert len(ps)==3
 assert [sum(p[k] for p in ps) for k in ('calls','requests','bytes','seconds')]==[17,660,176800640,935]
 rows=[r for scope in m.PROFILES for r in m.manifest(scope)['rows']];assert len(rows)==17
 assert len(m.manifest('untouched5')['rows'])==5 and len(m.manifest('partitions8')['rows'])==8
 assert sum(p['job_seconds'] for p in ps)==2330
 assert all(m.validate_plan(m.plan(n))==p for n,p in m.PROFILES.items())
 assert [(r['council'],r['reference']) for r in s.rows()]==[('bolton','01768/26'),('bolton','01769/26'),('bolton','01827/26'),('stockport','DC/100094'),('stockport','DC/100393')]
 assert all(s.shared.envelope(r).window.outcome.value=='COMPLETE' for r in s.rows() if r['council']=='bolton')

@pytest.mark.parametrize('scope',list(m.PROFILES))
def test_actual_workflow_mapping_and_mutations(scope):
 p=m.profile(scope);raw=Path(p['workflow']).read_bytes();assert raw==(m.PACK/(scope+'.yml.txt')).read_bytes()
 w=yaml.load(raw,Loader=yaml.BaseLoader);assert set(w['on'])=={'workflow_dispatch'};assert 'secrets.' not in raw.decode() and 'environment:' not in raw.decode()
 env=dict(context('bolton53'),GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p['workflow']+'@refs/heads/master')
 values={'${{ inputs.reviewed_sha }}':'a'*40,'${{ inputs.manifest_sha }}':p['manifest_sha'],'${{ inputs.authority }}':p['authority'],'${{ github.workflow_sha }}':'a'*40,'${{ env.SOURCE_JOB_STARTED_EPOCH }}':str(int(time.time()))}
 for step in w['jobs']['source']['steps'][1:]:
  if 'env' not in step:continue
  e=dict(env,**{k:values[v] for k,v in step['env'].items()});m.admit(scope,'a'*40,p['manifest_sha'],p['authority'],e)
  for k,v in [('GITHUB_WORKFLOW_SHA',None),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_REF','refs/heads/other')]:
   with pytest.raises(ValueError):m.admit(scope,'a'*40,p['manifest_sha'],p['authority'],dict(e,**{k:v}))
  with pytest.raises(ValueError):m.admit(scope,'a'*40,p['manifest_sha'],p['authority'],e,workflow_bytes=raw+b'bad')
 assert f'--scope {scope}' in raw.decode()


def test_actual_parent_worker_checkpoint_wiring(tmp_path):
 calls=[];row=m.manifest('untouched5')['rows'][0]
 # Existing real transport cap regression remains authoritative; this verifies new fixed wiring.
 with patch.object(m.finite,'read',side_effect=lambda r:calls.append(r) or (_ for _ in ()).throw(RuntimeError('source'))):
  m.execute_worker(m.plan('untouched5'),tmp_path/'result.json',tmp_path)
 j=json.loads((tmp_path/'result.json').read_text());assert len(calls)==1 and j['stop_reason']=='SOURCE_EXCEPTION' and not j['accounting_complete']
 assert (tmp_path/'checkpoints/000.json').is_file()


def test_selected_three_actual_shared_writer_existing_preservation(engine):
 row=next(s.rows());out=s.shared.record(engine,row,retrieve=synthetic)
 assert out['identity']=='CREATED_PENDING' and out['facts']=='INITIAL_FACTS_VERIFIED'
 assert out['readback']['reference']=='01768/26' and out['readback']['status']=='Deposited'
 assert out['readback']['site_id'] is None
 again=s.shared.record(engine,row,retrieve=lambda _:pytest.fail('existing must not refetch'))
 assert again['identity']=='ALREADY_KNOWN' and again['facts']=='EXISTING_NOT_WRITTEN'


def test_selected_unsupported_stockport_no_engine_or_source():
 rows=list(s.rows())[3:];hits=[]
 with patch.object(s,'rows',lambda:iter(rows)):
  out=s.run(engine_factory=lambda:pytest.fail('no engine'),reader=lambda _:pytest.fail('no source'),checkpoint=hits.append,journal=lambda *_:None)
 assert len(hits)==2 and all(r['transaction']=='NOT_STARTED' and r['identity']=='WITHHELD' for r in hits)
 assert out['stop'] is None


def test_selected_uncertainty_and_checkpoint_stops_next():
 for kind in ('transaction','checkpoint'):
  calls=[]
  def ck(_):
   if kind=='checkpoint':raise ValueError('checkpoint')
  class Engine:
   def dispose(self):pass
  with patch.object(s.shared,'record',return_value={'transaction':'UNCERTAIN_STOP_NO_RETRY' if kind=='transaction' else 'COMMIT_READBACK_CONFIRMED','stop':kind=='transaction'}):
   out=s.run(engine_factory=lambda:calls.append(1) or Engine(),checkpoint=ck,journal=lambda *_:None)
  assert len(calls)==1 and out['stop']


def test_selective_actual_binding_and_environment():
 raw=Path(b.WORKFLOW).read_bytes();assert raw==b.TEMPLATE.read_bytes()
 w=yaml.load(raw,Loader=yaml.BaseLoader);job=w['jobs']['source'];assert job['environment']=='stage4-production-canary' and job['timeout-minutes']=='25'
 assert sum('secrets.DATABASE_URL' in str(x) for x in job['steps'])==1
 env=dict(context('bolton53'),GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+b.WORKFLOW+'@refs/heads/master')
 b.admit('a'*40,s.COHORT_SHA,b.AUTHORITY,env)
 for k,v in [('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_WORKFLOW_SHA',None),('GITHUB_SHA','b'*40)]:
  with pytest.raises(ValueError):b.admit('a'*40,s.COHORT_SHA,b.AUTHORITY,dict(env,**{k:v}))
 with pytest.raises(ValueError):b.admit('a'*40,'0'*64,b.AUTHORITY,env)
 with pytest.raises(ValueError):b.admit('a'*40,s.COHORT_SHA,'old',env)
 assert s.LIMITS['record_seconds']==180 and s.LIMITS['seconds']==1020


def assert_selected_registered(raw):
 assert hashlib.sha256(raw).hexdigest()==SELECTED_WORKFLOW_HASH
 w=yaml.load(raw,Loader=yaml.BaseLoader);assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'source'}
 assert w['jobs']['source']['environment']=='stage4-production-canary'

SELECTED_WORKFLOW_HASH='8b7ac498834ea5e55b25549e72a2e0378b633ecbee9d50338774bd45a581db71'


def test_real_supervisor_selects_exact_new_module_and_clean_worker_env(tmp_path):
    from tests.test_discovery_r0_registered_scopes import proc_namespace
    from unittest.mock import MagicMock
    import psutil
    seen={}
    def launch(command,**kw):
        seen.update(command=command,env=kw['env'])
        plan=json.loads(Path(command[command.index('--worker')+1]).read_text())
        assert plan==m.plan('untouched5')
        Path(command[command.index('--output')+1]).write_text(json.dumps(dict(stop_reason=None,accounting_complete=True,persistence=False)))
        child=MagicMock(pid=999998,returncode=0);child.poll.return_value=0;child.wait.return_value=0;return child
    audit=tmp_path/'audit';audit.mkdir()
    with proc_namespace(),patch.object(psutil,'Process',return_value=MagicMock()),patch.object(psutil,'wait_procs',return_value=([],[])):
        out=m.outer.supervise_round(m.plan('untouched5'),audit/'result.json',deadline=275,worker_module='verification.discovery.r0_mandate',runner=launch)
    assert seen['command'][2]=='verification.discovery.r0_mandate' and '--audit-dir' in seen['command']
    assert not any('DATABASE' in k or 'AUTHORITY' in k or 'TOKEN' in k for k in seen['env'])
    assert out['outer_supervisor']['cleanup']=='CLOSED'


def test_selected_actual_private_worker_shared_handoff(engine,tmp_path,monkeypatch):
 from verification.discovery import selective5_supervisor as supervisor
 from verification.discovery import committee_exact
 import resource
 monkeypatch.setenv('BOLTON_ADMISSION_PRIVATE_CHILD','1');monkeypatch.setenv('BOLTON_ADMISSION_DATABASE_URL','DISPOSABLE_FIXED_ONLY')
 seen=[];actual=s.run
 def selected(**kw):
  seen.append([r['reference'] for r in s.rows()]);return actual(reader=synthetic,**kw)
 with patch.object(s,'run',side_effect=selected),patch.object(committee_exact,'checked_engine',side_effect=lambda credential:engine if credential=='DISPOSABLE_FIXED_ONLY' else pytest.fail('credential')),patch.object(engine,'dispose',lambda:None),patch.object(resource,'setrlimit',lambda *_:None):
  supervisor.worker(tmp_path)
 result=json.loads((tmp_path/'worker-result.json').read_text())
 assert seen==[['01768/26','01769/26','01827/26','DC/100094','DC/100393']]
 assert result['stop'] is None and len(result['results'])==5
 assert all(r['facts']=='INITIAL_FACTS_VERIFIED' for r in result['results'][:3])
 assert len(result['checkpoint_sha256'])==5 and supervisor.files(tmp_path)<s.LIMITS['output_bytes']


def test_selected_export_revision_and_path_guards(tmp_path,monkeypatch):
 import sys
 tmp_path=tmp_path/'selected-audit';tmp_path.mkdir()
 monkeypatch.setenv('GITHUB_SHA','a'*40);monkeypatch.setenv('GITHUB_RUN_ID','123')
 (tmp_path/'execution.json').write_text(json.dumps(dict(sha='a'*40,run_id='123',cohort_sha256=s.COHORT_SHA,run_number=1,attempt=1)))
 (tmp_path/'supervisor.json').write_text(json.dumps(dict(cohort_sha256=s.COHORT_SHA,primary_sha256=s.PRIMARY_SHA)))
 with patch.object(sys,'argv',['binding','--verify-audit','--output',str(tmp_path)]):b.main()
 (tmp_path/'unexpected.txt').write_text('not allowed')
 with patch.object(sys,'argv',['binding','--verify-audit','--output',str(tmp_path)]),pytest.raises(ValueError,match='AUDIT_PATH'):b.main()
 (tmp_path/'unexpected.txt').unlink();monkeypatch.setenv('GITHUB_SHA','b'*40)
 with patch.object(sys,'argv',['binding','--verify-audit','--output',str(tmp_path)]),pytest.raises(ValueError,match='EXECUTION_IDENTITY'):b.main()


def test_authorised_original_manifests_and_row_provenance_unchanged():
 root=m.ROOT/'docs/design/stage4-r0-execution'
 a=root/'two-parent-result-consolidated-20261015/proposed-untouched5.json';c=root/'exact9-registration-parent-controls/capped-partition-proposal.json'
 assert hashlib.sha256(a.read_bytes()).hexdigest()=='e046d8630b382561b475e9d8230b013e57fa35ff1db8b4737bdeeee225213633'
 assert hashlib.sha256(c.read_bytes()).hexdigest()=='86ab8f3905ae97f831b31a59c13f93068affac3d7b06493828d7558bd5043e88'
 assert m.manifest('untouched5')['original_rows']==json.loads(a.read_text())['rows']
 assert m.manifest('partitions8')['original_rows']==json.loads(c.read_text())['rows']
