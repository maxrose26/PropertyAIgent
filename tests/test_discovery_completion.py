"""Approved finite completion: offline/synthetic evidence only."""
import json,hashlib,os,time
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import pytest,yaml
from verification.discovery import completion_source as s,completion_comparison as c
from verification.discovery.arcus_ui_config import MANCHESTER
from verification.discovery.arcus_ui_window import qualify_segment

@pytest.fixture(autouse=True)
def clean(monkeypatch):
 for k in list(os.environ):
  if 'DATABASE' in k or k.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):monkeypatch.delenv(k,raising=False)

def test_exact_scopes_budget_and_no_duplicate_rows():
 ps=list(s.PROFILES.values());assert [sum(x[k] for x in ps) for k in ['calls','requests','bytes','seconds','job_seconds']]==[27,1530,404487360,1485,2880]
 for p in ps:assert p['job_seconds']==p['setup_seconds']+p['seconds']+p['cleanup_upload_seconds']
 allrows=[tuple(sorted(r.items())) for scope in s.PROFILES for r in s.manifest(scope)['rows']];assert len(allrows)==len(set(allrows))==27
 assert len(c.identities())==944

def test_actual_source_workflow_mapping_and_mutations():
 for scope in s.PROFILES:
  p=s.profile(scope);raw=Path(p['workflow']).read_bytes();w=yaml.load(raw,Loader=yaml.BaseLoader);steps=w['jobs']['source']['steps']
  assert w['jobs']['source']['timeout-minutes']==str(p['job_seconds']//60)
  assert 'secrets.' not in raw.decode() and 'environment' not in w['jobs']['source']
  assert all(x['env']['GITHUB_WORKFLOW_SHA']=='${{ github.workflow_sha }}' for x in steps if 'SOURCE_AUTHORITY' in x.get('env',{}))
  env=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p['workflow']+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',JOB_STARTED_EPOCH=str(int(time.time())))
  if scope!='bridge9':s.admit(scope,'a'*40,p['manifest_sha'],p['authority'],env)
  for k,v in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_WORKFLOW_SHA',None),('GITHUB_SHA','b'*40)]:
   with pytest.raises(ValueError):s.admit(scope,'a'*40,p['manifest_sha'],p['authority'],dict(env,**{k:v}))
  with pytest.raises(ValueError):s.admit(scope,'a'*40,p['manifest_sha'],p['authority'],env,workflow_bytes=raw+b'\n')

def assert_comparison_registered(raw):
 assert raw== (c.PACK/'registered-comparison944.yml.txt').read_bytes()
 w=yaml.load(raw,Loader=yaml.BaseLoader);assert set(w['on'])=={'workflow_dispatch'}
 j=w['jobs']['comparison'];assert j['environment']=='stage4-production-canary'
 assert sum('secrets.DATABASE_URL' in str(x) for x in j['steps'])==1
 assert 'verification.discovery.completion_comparison' in str(j)
 assert 'secrets.' not in str(j['steps'][2])

def test_comparison_registered_and_duplicate_bound():
 raw=Path(c.WORKFLOW).read_bytes();assert_comparison_registered(raw)
 with pytest.raises(AssertionError):assert_comparison_registered(raw+b'\n')
 sql,params=c.existing.statement(c.identities());assert len(params)==1888
 assert 'LIMIT 2' in sql and 'public.applications' in sql and 'SELECT a.id, a.council_code, a.reference' in sql
 for forbidden in ['INSERT','UPDATE','DELETE']:assert forbidden not in sql

def test_metadata_actual_projection_and_historical_defaults():
 config=replace(MANCHESTER,start='2026-10-01',end='2026-10-03')
 cards=[dict(links=[dict(text='TEST/1',href='https://arcusbe.manchester.gov.uk/pr/s/detail/'+('a'*18)+'?c__r=Arcus_BE_Public_Register')],fields=[dict(label='Reference',value='TEST/1'),dict(label='Valid Date',value='1/10/2026'),dict(label='Proposal',value='Residential development for49dwellings'),dict(label='Applicant',value='DO_NOT_EXPORT')])]
 old=qualify_segment('Showing 1 to 1 of 1 results',cards,1,config=config)[3][0];assert 'fields' not in old
 new=qualify_segment('Showing 1 to 1 of 1 results',cards,1,config=replace(config,capture_metadata=True))[3][0]
 assert new['fields']['proposal']['state']=='PRESENT_VALUE' and 'DO_NOT_EXPORT' not in json.dumps(new)
 assert new['fields']['address']['state']=='UNKNOWN'
 cards[0]['fields'].append(dict(label='Description',value='Other'))
 with pytest.raises(ValueError):qualify_segment('Showing 1 to 1 of 1 results',cards,1,config=replace(config,capture_metadata=True))

def test_actual_read_supervisor_rejected_route_no_connection(tmp_path):
 from verification.discovery.completion_read_supervisor import supervise
 if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():pytest.skip('owned-process acceptance requires matching hosted PID namespace')
 r=supervise(tmp_path/'audit',credential='NOT_A_URL',deadline=5)
 assert r['cleanup']=='CLOSED' and r['live_owned_survivors']==0
 assert r['result']['connection_attempts']==0 and r['result']['production_writes']==0
 assert 'NOT_A_URL' not in json.dumps(r)

def test_parent_supervisor_delegates_exact_module_and_plan(tmp_path):
 with patch.dict(os.environ,{'GITHUB_RUN_ID':'123'}),patch.object(s.outer,'supervise_round',return_value={}) as sup,patch.object(s,'admit'),patch.object(s.shared,'checkout'),patch('sys.argv',['completion','--scope','screen14','--reviewed-sha','a'*40,'--manifest-sha',s.profile('screen14')['manifest_sha'],'--authority',s.profile('screen14')['authority'],'--output',str(tmp_path/'out')]):
  s.main();assert sup.call_args.kwargs['worker_module']=='verification.discovery.completion_source';assert sup.call_args.kwargs['deadline']==770


def test_actual_supervisor_metadata_output_bound(tmp_path):
 from verification.direct_reference.instrumented_probe import bounded_worker_audit
 p=tmp_path/'child.json';a=dict(case='discovery_manchester_ui_window',listing_records=[dict(reference=str(i),fields=dict(proposal=dict(value='x'*1024),address=dict(value='y'*600))) for i in range(60)],failure=None,persistence=False)
 p.write_text(json.dumps(a));assert 65536<p.stat().st_size<512000
 assert bounded_worker_audit(p,a['case'],metadata=True)==a
 assert bounded_worker_audit(p,a['case'])['failure']=='NO_WORKER_AUDIT'
 p.write_text(' '*512000);assert bounded_worker_audit(p,a['case'],metadata=True)['failure']=='NO_WORKER_AUDIT'


def test_bridge_cut_is_fixed_and_cannot_run_early():
 from datetime import datetime,timezone
 scope='bridge9';p=s.profile(scope)
 env=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p['workflow']+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',JOB_STARTED_EPOCH=str(int(time.time())))
 with pytest.raises(ValueError,match='CUT_NOT_REACHED'):s.admit(scope,'a'*40,p['manifest_sha'],p['authority'],env,now=datetime(2026,10,15,22,59,tzinfo=timezone.utc))
 s.admit(scope,'a'*40,p['manifest_sha'],p['authority'],env,now=datetime(2026,10,15,23,tzinfo=timezone.utc))


def test_comparison_actual_workflow_binding_rejects_mutations():
 raw=Path(c.WORKFLOW).read_bytes();w=yaml.load(raw,Loader=yaml.BaseLoader)
 step=next(x for x in w['jobs']['comparison']['steps'] if 'COMPARISON_DATABASE_URL' in x.get('env',{}))
 assert step['env']['GITHUB_WORKFLOW_SHA']=='${{ github.workflow_sha }}'
 assert step['env']['JOB_STARTED_EPOCH']=='${{ env.COMPARISON_JOB_STARTED_EPOCH }}'
 env=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+c.WORKFLOW+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',JOB_STARTED_EPOCH=str(int(time.time())))
 c.admit(env,'a'*40,c.MANIFEST_SHA,c.AUTHORITY)
 for k,v in [('GITHUB_WORKFLOW_SHA',None),('GITHUB_SHA','b'*40),('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('JOB_STARTED_EPOCH','1')]:
  with pytest.raises(ValueError):c.admit(dict(env,**{k:v}),'a'*40,c.MANIFEST_SHA,c.AUTHORITY)
 with pytest.raises(ValueError):c.admit(env,'a'*40,'b'*64,c.AUTHORITY)
 with pytest.raises(ValueError):c.admit(env,'a'*40,c.MANIFEST_SHA,'OLD_AUTHORITY')


def test_actual_private_read_worker_delegates_fixed944(tmp_path,monkeypatch):
 from verification.discovery.completion_read_supervisor import worker
 monkeypatch.setenv('COMPARISON_PRIVATE_CHILD','1');monkeypatch.setenv('COMPARISON_DATABASE_URL','SYNTHETIC_PRIVATE_VALUE')
 with patch.object(c.existing,'run_exact',return_value={'result':'COMPLETED','transaction':'READ_ONLY_ROLLED_BACK','production_writes':0}) as run:
  worker(tmp_path)
  assert len(run.call_args.args[1])==944 and run.call_args.kwargs['output_bound']==1000000
  assert run.call_args.args[0]=='SYNTHETIC_PRIVATE_VALUE'
 assert 'SYNTHETIC_PRIVATE_VALUE' not in (tmp_path/'worker-result.json').read_text()
 assert 'COMPARISON_DATABASE_URL' not in os.environ


@pytest.mark.parametrize('uncertain',[False,True])
def test_read_outer_actual_delegation_and_uncertain_accounting(tmp_path,uncertain):
 from verification.discovery import completion_read_supervisor as outer
 from types import SimpleNamespace
 root=tmp_path/'audit';calls=[];original=Path.read_text
 def text(path,*a,**kw):return str(os.getpid())+' synthetic' if str(path)=='/proc/self/stat' else original(path,*a,**kw)
 class Child:
  pid=123456;returncode=0
  def poll(self):return 0
  def wait(self,timeout):return 0
 def launch(command,**kw):
  calls.append((command,kw));(root/'worker-result.json').write_text('{"result":"COMPLETED","production_writes":0}');return Child()
 with patch.object(Path,'read_text',text),patch('psutil.Process',side_effect=RuntimeError('synthetic accounting failure') if uncertain else None) as process:
  process.return_value=SimpleNamespace()
  result=outer.supervise(root,credential='SYNTHETIC_PRIVATE_VALUE',runner=launch)
 assert calls[0][0][2]=='verification.discovery.completion_read_supervisor'
 assert set(calls[0][1]['env'])=={'PATH','HOME','TMPDIR','LANG','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE','GITHUB_ACTIONS','RUNNER_ENVIRONMENT','COMPARISON_PRIVATE_CHILD','COMPARISON_DATABASE_URL'}
 assert 'SYNTHETIC_PRIVATE_VALUE' not in json.dumps(result)
 if uncertain:assert result['accounting_complete'] is False and result['cleanup']=='UNKNOWN' and 'result' not in result
 else:assert result['cleanup']=='CLOSED' and result['result']['production_writes']==0
