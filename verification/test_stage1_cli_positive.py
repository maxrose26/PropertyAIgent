"""Positive scope admission/cleanup for every inventoried CLI launch adapter.

These exercise the actual shared adapter, not a full scheduler/pipeline run.
Business command families have separate synthetic positive-path coverage.
"""
import json
from pathlib import Path
import pytest
from app.security import access
from app.security.cli import command_scope
from verification.test_stage1_access import admission
MANIFEST=json.loads(Path(__file__).with_name('stage1_cli_manifest.json').read_text())
@pytest.mark.parametrize('command',[value['command'] for value in MANIFEST.values() if 'command' in value])
def test_named_launch_scope_and_cleanup(admission,monkeypatch,command):
    r,c,t,path,policy=admission
    policy['machines']={'fixture':dict(enabled=True,workspace_id=1,buyer_ids=[1],actions=['launch:'+command,'matching.write'])}
    path.write_text(json.dumps(policy));monkeypatch.setenv('PROPERTYAIGENT_COMMAND_IDENTITY','fixture')
    for iteration in range(3):
        with command_scope(command) as actor:
            assert actor.machine and access.require_operator('matching.write') is actor
            assert access.require_buyer(1,1) is actor
            with pytest.raises(access.AccessDenied):access.require_operator('policy.write')
            assert len(r.leases)==1
        assert not r.leases and not r.issuances and not r.issuance_revisions and not r.revoked_issuances
