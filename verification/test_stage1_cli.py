import importlib,json
from pathlib import Path
import pytest
from app.security import access
from app.security.cli import command_scope
from verification.test_stage1_access import admission

MANIFEST=json.loads(Path(__file__).with_name('stage1_cli_manifest.json').read_text())
@pytest.mark.parametrize('path', [p for p,m in MANIFEST.items() if 'command' in m])
def test_launch_has_no_implicit_authority(admission,monkeypatch,path):
    monkeypatch.delenv('PROPERTYAIGENT_COMMAND_IDENTITY',raising=False)
    module=importlib.import_module(path[:-3].replace('/','.'))
    with pytest.raises(access.AccessDenied):module.main()

def test_explicit_machine_scope_and_default_paid_denial(admission,monkeypatch):
    registry,claims,clock,path,policy=admission
    policy['machines']={'synthetic-job':dict(enabled=True,workspace_id=1,buyer_ids=[1],actions=['launch:test','matching.write'])}
    path.write_text(json.dumps(policy));monkeypatch.setenv('PROPERTYAIGENT_COMMAND_IDENTITY','synthetic-job')
    with command_scope('test'):
        access.require_operator('matching.write')
        access.require_buyer(1,1)
        with pytest.raises(access.AccessDenied):access.require_buyer(1,2)
        with pytest.raises(access.AccessDenied):access.require_operator('policy.write')
        with pytest.raises(access.AccessDenied):access.require_operator('contacts.enrich',paid=True)
    with pytest.raises(access.AccessDenied):access.require_admitted()
    with pytest.raises(access.AccessDenied):
        with command_scope('other'):pass
