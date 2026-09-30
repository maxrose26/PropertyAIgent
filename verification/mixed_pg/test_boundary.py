import pytest
from app.revisit.offline_child import require_offline_owner,run


def test_unadmitted_offline_branch_rejects_before_manifest(monkeypatch):
    for k in ['RENDER','RENDER_SERVICE_ID','PROPERTYAIGENT_OWNER']:
        monkeypatch.delenv(k,raising=False)
    with pytest.raises(RuntimeError,match='admitted child'):run('missing-recording','stockport')


def test_production_offline_branch_rejects_before_manifest(monkeypatch):
    monkeypatch.setenv('RENDER','true')
    with pytest.raises(RuntimeError,match='local admitted child'):require_offline_owner(None)
