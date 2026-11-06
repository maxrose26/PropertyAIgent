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


def test_compact_fields_preserve_screening_and_original_source():
 import copy
 from dataclasses import replace
 from datetime import date
 from tests.e2e_connection_support import arcus_contract,outer
 from tests.test_daily_intake_runtime import arcus_audit,entry,SCHEME,RULE
 from app.ingestion.ledger import DEFAULT_LIMITS,digest
 audit=arcus_audit('manchester',[entry('M/2026/1',SCHEME)],date(2026,10,27),date(2026,11,2))
 before=copy.deepcopy(audit)
 c=replace(arcus_contract('manchester',date(2026,10,27),date(2026,11,2)),compact_retained=True)
 full=c.project(audit,outer(),DEFAULT_LIMITS)
 compact=replace(c,compact_field_evidence=True).project(audit,outer(),DEFAULT_LIMITS)
 assert audit==before and compact['source_sha256']==full['source_sha256']==digest(audit)
 a,b=full['records'][0],compact['records'][0]
 assert RULE.screen(a)==RULE.screen(b)
 assert {k:v for k,v in a.items() if k!='fields'}=={k:v for k,v in b.items() if k!='fields'}
 assert b['fields']=={k:{n:v for n,v in f.items() if n not in ('dom_text_content','rendered_label')} for k,f in a['fields'].items()}
 assert compact['resources']==full['resources'] and compact['segments']==full['segments']
 with pytest.raises(Exception,match='COMPACT_FIELD_SCOPE'):
  replace(c,compact_retained=False,compact_field_evidence=True).project(audit,outer(),DEFAULT_LIMITS)
