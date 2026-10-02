"""Explicit synthetic operator for original positive command fixtures; no DB seeding."""
import json,time
import pytest
from app.security import access
from app.security.commands import PAID_LIMITS

@pytest.fixture(autouse=True)
def authorised_fixture(tmp_path,monkeypatch):
    from app.db.models import Base
    from verification.stage1_test_context import seed_fixture
    original=Base.metadata.create_all
    def create_all(bind,*args,**kwargs):
        original(bind,*args,**kwargs);seed_fixture(bind)
    monkeypatch.setattr(Base.metadata,'create_all',create_all)
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-offline-placeholder')
    issuer='http://127.0.0.1:19999'
    policy=dict(version=1,enabled=True,environment='local',issuer=issuer,client_id='offline-test',web_processes=1,web_replicas=1,owner_subject='fixture',principals=[dict(issuer=issuer,subject='fixture',role='operator',enabled=True,workspace_id=1,buyer_ids=list(range(1,21)))],paid_actions=dict.fromkeys(PAID_LIMITS,True))
    from pathlib import Path
    service_manifest=json.loads((Path(__file__).with_name('stage1_service_manifest.json')).read_text())
    cli_manifest=json.loads((Path(__file__).with_name('stage1_cli_manifest.json')).read_text())
    actions={a.removeprefix('paid:') for functions in service_manifest.values() for a in functions.values() if a!='read'}
    actions.update(item['required_scope'] for item in cli_manifest.values())
    policy['machines']={'fixture-cli':dict(enabled=True,workspace_id=1,buyer_ids=list(range(1,21)),actions=sorted(actions))}
    monkeypatch.setenv('PROPERTYAIGENT_COMMAND_IDENTITY','fixture-cli')
    path=tmp_path/'positive-policy.json';path.write_text(json.dumps(policy));monkeypatch.setenv('PROPERTYAIGENT_ACCESS_POLICY',str(path))
    r=access.LeaseRegistry();r.boot=int(time.time())-1;r.middleware_ready=True;monkeypatch.setattr(access,'registry',r)
    actor=r.issue(dict(iss=issuer,sub='fixture',aud='offline-test',iat=int(time.time()),exp=int(time.time())+3600,email_verified=True),'fixture')
    with access.actor_scope(actor):yield

@pytest.fixture(autouse=True)
def original_http_fixtures(monkeypatch):
    # Original business tests patch requests.get; adapt that existing fixture
    # seam to the new transport entrypoint. Actual TLS/DNS is tested separately.
    from app.security import outbound
    import requests
    from unittest.mock import Mock
    def get(*args,**kwargs):
        if not isinstance(requests.get,Mock):raise AssertionError('Positive command requires an explicit HTTP fixture')
        return requests.get(*args,**kwargs)
    monkeypatch.setattr(outbound,'get',get)

import logging,os
_records=[]
_current_test=None
class Completed(logging.Handler):
    def emit(self,record):
        try:data=json.loads(record.getMessage())
        except (ValueError,TypeError):return
        if data.get('outcome')=='completed':_records.append(dict(test=_current_test,action=data['action']))
def pytest_configure(config):
    logger=logging.getLogger('propertyaigent.access');logger.setLevel(logging.INFO);logger.addHandler(Completed())
def pytest_runtest_setup(item):
    global _current_test
    _current_test=item.nodeid
def pytest_sessionfinish(session,exitstatus):
    from pathlib import Path
    target=os.environ.get('STAGE1_COMMAND_EVIDENCE')
    if target:Path(target).write_text(json.dumps(dict(exitstatus=exitstatus,completed=_records),indent=2))
