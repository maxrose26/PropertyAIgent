"""Serialization overhead must not consume the unchanged bounded-audit allowance."""
import json,sys
import pytest
from verification.direct_reference import instrumented_probe as probe


def worker(monkeypatch,tmp_path,value):
 for name in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY'):monkeypatch.delenv(name,raising=False)
 async def fixture(*args,**kwargs):return value
 monkeypatch.setattr(probe,'probe',fixture)
 path=tmp_path/'audit.json'
 monkeypatch.setattr(sys,'argv',['probe','--worker','--case','discovery_manchester_ui_window','--output',str(path)])
 return path


def test_historical_nonproof_format_and_bound_unchanged(monkeypatch,tmp_path):
 value={'records':[{'reference':str(n),'fields':[{'label':'Proposal','value':'x'*30} for _ in range(11)]} for n in range(60)]}
 assert len((json.dumps(value,indent=2)+'\n').encode())>=65536
 assert len((json.dumps(value,separators=(',',':'))+'\n').encode())<65536
 path=worker(monkeypatch,tmp_path,value)
 with pytest.raises(ValueError,match='WORKER_AUDIT_BOUND'):probe._main()
 assert not path.exists()


def test_over_bound_compact_audit_still_refuses(monkeypatch,tmp_path):
 value={'padding':'x'*65536};path=worker(monkeypatch,tmp_path,value)
 with pytest.raises(ValueError,match='WORKER_AUDIT_BOUND'):probe._main()
 assert not path.exists()

@pytest.mark.parametrize('change',[{}, {'start':'2026-10-28'}, {'council':'salford'}, {'mode':'IDENTITY_ONLY'}, {'retain':False}, {'budget':None}])
def test_only_reviewed_manchester_metadata_proof_uses_metadata_allowance(change):
 from verification.discovery.four_council_proof import manifest_scope
 from verification.discovery.source_profiles import profile
 row=dict(council='manchester',semantics='VALIDATED',start='2026-10-27',end='2026-11-02')
 row.update({k:v for k,v in change.items() if k in row})
 selected=profile(row,change.get('mode','SCREENING_METADATA'))
 with manifest_scope(row,selected):
  actual=probe.worker_audit_bound('discovery_'+row['council']+'_ui_window',retain_proof=change.get('retain',True),execution_budget=change.get('budget','BROWSER_SOURCE_V2'))
 assert actual==(65536 if change else 512000)
 assert probe.worker_audit_bound('discovery_manchester_ui_window',metadata=True)==512000


def test_exact_profile_still_rejects_oversized_inner_audit(tmp_path):
 from verification.discovery.four_council_proof import manifest_scope
 from verification.discovery.source_profiles import profile
 row=dict(council='manchester',semantics='VALIDATED',start='2026-10-27',end='2026-11-02')
 path=tmp_path/'audit';path.write_bytes(b'x'*512000)
 with manifest_scope(row,profile(row,'SCREENING_METADATA')):
  result=probe.bounded_worker_audit(path,'discovery_manchester_ui_window',retain_proof=True,execution_budget='BROWSER_SOURCE_V2')
 assert result['failure']=='NO_WORKER_AUDIT'
