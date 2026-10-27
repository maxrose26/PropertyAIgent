"""Council/database-free input refusal and bounded final-output accounting."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from app.ingestion.ledger import Denied
from verification.ingestion_storage import oldham_owner_package as pkg
from verification.ingestion_storage.operational_publication import canonical
from tests.oldham_wrapper_fixture import packet

@pytest.fixture
def inputs(tmp_path,monkeypatch):
    original=pkg.git
    monkeypatch.setattr(pkg,'git',lambda *a:'' if a==('status','--porcelain') else original(*a))
    return packet(tmp_path/'inputs',supervised=False)


def rewrite(path,p):
    raw=canonical(p);path.write_bytes(raw);return pkg.sha(raw)


def test_valid_disposable_packet_and_live_mode_refusal(inputs):
    path,sha=inputs;data=pkg.validate(path,sha,disposable=True)
    assert len(data['source']['records'])==2
    with pytest.raises(Denied,match='TEST_MODE'):pkg.validate(path,sha)


@pytest.mark.parametrize('field',['revision','tree','dependencies','packages','qualification_binding','origin','risk_acceptance','scope'])
def test_substituted_bindings_refuse(inputs,field):
    path,_=inputs;p=json.loads(path.read_bytes())
    if field=='origin':p[field]['source_path']='https://not-permitted.invalid'
    elif field=='scope':p[field]['council']='bury'
    elif field in ('dependencies','packages','qualification_binding'):p[field]={}
    else:p[field]='f'*40
    with pytest.raises((Denied,KeyError,ValueError)):pkg.validate(path,rewrite(path,p),disposable=True)


def test_missing_supervisor_refuses_before_input_and_db(inputs,tmp_path,monkeypatch,capsys):
    from verification.ingestion_storage.oldham_owner_once import main
    path,_=inputs;p=json.loads(path.read_bytes());slotpath=path.parent/p['outer']['name'];slot=json.loads(slotpath.read_bytes());slot.pop('outer_supervisor');raw=canonical(slot);slotpath.write_bytes(raw);p['outer']['sha256']=pkg.sha(raw)
    psha=rewrite(path,p);monkeypatch.setenv('HOME',str(tmp_path/'home'))
    assert main(['--package',str(path),'--package-sha256',psha,'--disposable-test'])==1
    result=json.loads(capsys.readouterr().out.splitlines()[-1]);assert result['credential_requested'] is False and result['database_connections']==0


def test_external_publication_bytes_count_in_final_result(tmp_path):
    from verification.ingestion_storage.operational_journal import Journal
    from verification.ingestion_storage.operational_outcome import finalise
    j=Journal(tmp_path/'state');j.emit('fixture',dict(no_credentials=True));lines=[]
    finalise(j,dict(status='COMPLETED',cleanup='CLOSED'),input_seconds=0,active_started=None,external_bytes=12345,output=lambda s,**_:lines.append(s))
    result=json.loads(lines[0]);assert result['exported_bytes']==result['persisted_evidence_bytes']+result['terminal_json_bytes']+12345
    assert result['attempted_publication_bytes']==12345


def test_work_export_boundary_and_reserved_closure(tmp_path):
    from types import SimpleNamespace
    from verification.ingestion_storage.oldham_owner_once import Operation,MAX_EXPORT,RESERVE
    from datetime import datetime,timezone,timedelta
    op=object.__new__(Operation);op.started=None;op.closing=False;op.memory=None
    op.data={'expiry':datetime.now(timezone.utc)+timedelta(hours=1)}
    op.journal=SimpleNamespace(root=tmp_path);op.published=MAX_EXPORT-RESERVE
    op.check() # exact work boundary remains valid
    op.published+=1
    with pytest.raises(Denied,match='EXPORT_RESERVE'):op.check()
    op.closing=True;op.check() # only the already reserved closing envelope opens
    op.published=MAX_EXPORT-8192+1
    with pytest.raises(Denied,match='EXPORT_RESERVE'):op.check()


def test_io_reserve_refuses_start_without_reporting_capacity(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from verification.ingestion_storage import oldham_owner_once as command
    from datetime import datetime,timezone,timedelta
    op=object.__new__(command.Operation);op.started=100;op.closing=False;op.owner=None;op.memory=None;op.published=0
    op.data={'expiry':datetime.now(timezone.utc)+timedelta(hours=1)};op.journal=SimpleNamespace(root=tmp_path)
    monkeypatch.setattr(command.time,'monotonic',lambda:535)
    with pytest.raises(Denied,match='DEADLINE'):op.check()
    op.closing=True;op.check()
    monkeypatch.setattr(command.time,'monotonic',lambda:560)
    with pytest.raises(Denied,match='DEADLINE'):op.check()


def test_fault_scenario_release_identity_remains_valid(tmp_path,monkeypatch):
    original=pkg.git
    monkeypatch.setattr(pkg,'git',lambda *a:'' if a==('status','--porcelain') else original(*a))
    path,sha=packet(tmp_path/'fault',tag='application_uncertain',supervised=False)
    assert pkg.validate(path,sha,disposable=True)['package']['release_id']=='oldham-owner-test-application-uncertain'
