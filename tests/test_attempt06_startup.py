import pytest
from verification.ingestion_storage import owner_pilot as p
from tests.test_attempt05_startup import test_actual_runtime_guard_preflight_never_qualifies as startup, test_qualification_only_never_reaches_daily_on_either_outcome as qualification
@pytest.mark.parametrize('kind',['clean','dirty','git_failure'])
def test_attempt06_same_startup_guard(monkeypatch,tmp_path,capsys,kind):
 monkeypatch.setattr(p,'PERIOD','b-dbpilot-20261027-1102-06')
 startup(monkeypatch,tmp_path,capsys,kind)
@pytest.mark.parametrize('status',['VERIFIED_BOTH_RESTRICTED_ROLES','REFUSED'])
def test_attempt06_same_qualification_only_boundary(monkeypatch,capsys,status):
 monkeypatch.setattr(p,'PERIOD','b-dbpilot-20261027-1102-06')
 qualification(monkeypatch,capsys,status)
