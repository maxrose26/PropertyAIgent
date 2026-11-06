"""Fixed successor scope; historical guard bodies are not relaxed."""
import pytest
from verification.ingestion_storage import period10_successor as p, intake_policy

def test_only_registration_changes_and_finish_is_identical():
 old=intake_policy.policy_sql().split('CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception(',1)[1].split('$register$;',1)[0]
 new=p.registration_sql().split('CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception(',1)[1].split('$register$;',1)[0]
 anchor="  IF session_user<>'ingestion_worker_login'"
 assert old.split(anchor,1)[1]==new.split(anchor,1)[1]
 assert p.function_inventory()['ingestion_worker_step']==p.op.Owner.daily_intake_inventory()['ingestion_worker_step']
 assert p.SUCCESSOR=='b-dbpilot-20261027-1102-10'
 assert set(p.councils())=={'manchester'}
 assert p.disposition()['before']['hard_stop_generation']==p.disposition()['after']['hard_stop_generation']==13
 assert p.disposition()['before']['last_hard_stop']==p.disposition()['after']['last_hard_stop']

@pytest.mark.parametrize('profile,expected',[(None,524288),('MANCHESTER_PERIOD09_V1',2097152)])
def test_worker_file_limit_is_exact(tmp_path,monkeypatch,profile,expected):
 import os,json,resource
 from types import SimpleNamespace
 from verification.ingestion_storage.daily_intake_runtime import source_worker
 for k in list(os.environ):
  if 'DATABASE' in k or k.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(k)
 monkeypatch.setenv('INGESTION_SOURCE_PRIVATE','ONCE')
 class Seen(Exception):pass
 def selected(kind,bounds):
  assert kind==resource.RLIMIT_FSIZE and bounds==(expected,expected)
  raise Seen()
 monkeypatch.setattr(resource,'setrlimit',selected)
 row=dict(council='manchester',semantics='VALIDATED',start='2026-10-27',end='2026-11-02')
 plan=tmp_path/'plan';plan.write_text(json.dumps(dict(row=row,fixture=None,**({'file_profile':profile} if profile else {}))))
 with pytest.raises(Seen):source_worker(SimpleNamespace(plan=plan,output=tmp_path/'out'))

@pytest.mark.parametrize('change',[{'council':'tameside'},{'semantics':'RECEIVED'},{'start':'2026-10-26'},{'end':'2026-11-03'}])
def test_changed_file_profile_scope_refuses_before_limit_or_transport(tmp_path,monkeypatch,change):
 import os,json
 from types import SimpleNamespace
 from verification.ingestion_storage.daily_intake_runtime import source_worker
 for k in list(os.environ):
  if 'DATABASE' in k or k.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(k)
 monkeypatch.setenv('INGESTION_SOURCE_PRIVATE','ONCE');monkeypatch.setattr('resource.setrlimit',lambda *a:pytest.fail('LIMIT_REACHED'))
 row=dict(council='manchester',semantics='VALIDATED',start='2026-10-27',end='2026-11-02');row.update(change)
 plan=tmp_path/'plan';plan.write_text(json.dumps(dict(row=row,fixture=None,file_profile='MANCHESTER_PERIOD09_V1')))
 with pytest.raises(Exception,match='MANCHESTER_FILE_PROFILE_SCOPE'):source_worker(SimpleNamespace(plan=plan,output=tmp_path/'out'))
