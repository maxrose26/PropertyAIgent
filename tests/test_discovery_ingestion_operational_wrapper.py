"""Finite publisher and registration negatives, no production or source IO."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,subprocess
import pytest
from verification.ingestion_storage.operational_publication import GitHub,Uncertain,canonical
from verification.ingestion_storage.operational_runner import Journal,validate_registration
from tests.storage_gh_fixture import real_gh_store

@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_real_gh_complete_publication_mapping_and_deletion(tmp_path,real_gh_store):
    metadata,secret,ciphertexts,requests=real_gh_store;events=[]
    api=GitHub(lambda e,p:events.append((e,p)),lambda:None,runner=metadata.cli)
    assert api.names()==['DATABASE_URL']
    api.put_secret('INGESTION_EFFECT_DATABASE_URL','disposable_placeholder_never_a_real_url')
    assert 'INGESTION_EFFECT_DATABASE_URL' in api.names()
    raw=canonical({'retained':'complete source fixture, not council evidence'})
    commit=api.publish({'source.json':raw},directory='docs/design/ingestion-operational-execution-fixture/capture',expected_head='1'*40)
    assert len(commit)==40 and any(e=='publication_verified' for e,p in events)
    api.call('DELETE','repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets/INGESTION_EFFECT_DATABASE_URL')
    assert api.names()==['DATABASE_URL']
    assert not any('placeholder' in json.dumps(x) for x in events)

def test_uncertain_publication_has_no_retry_or_ref_update():
    calls=[]
    def fail(command,**kwargs):calls.append(command);raise subprocess.TimeoutExpired(command,1)
    api=GitHub(lambda *_:None,lambda:None,runner=fail)
    with pytest.raises(Uncertain):api.publish({'source.json':b'{}'},directory='docs/design/ingestion-operational-execution-fixture/capture',expected_head='1'*40)
    assert len(calls)==1 and '--method' in calls[0] and calls[0][3]=='GET'

def test_non_204_delete_is_uncertain():
    api=GitHub(lambda *_:None,lambda:None,runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout=b'HTTP/2.0 200 OK\r\n',stderr=b''))
    with pytest.raises(Uncertain):api.call('DELETE','repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets/INGESTION_EFFECT_DATABASE_URL')

def test_journal_durable_chain_and_one_use_directory(tmp_path):
    j=Journal(tmp_path/'one');j.emit('intent',{'operation':'fixture'});j.emit('ack',{'operation':'fixture'})
    previous='0'*64
    for i,line in enumerate(j.file.read_bytes().splitlines()):
        r=json.loads(line);h=r.pop('sha256');assert r['sequence']==i and r['previous_sha256']==previous
        assert hashlib.sha256(canonical(r)).hexdigest()==h;previous=h
    assert previous==j.head
    with pytest.raises(FileExistsError):Journal(tmp_path/'one')

def test_unreleased_registration_never_reaches_authentication():
    b=canonical({'authority':'AUTHORISE_BOLTON_CAPTURE_QUEUE_ONCE_20261018','status':'NOT_RELEASED'})
    with pytest.raises(ValueError,match='EXACT_OPERATIONAL_APPROVAL_REQUIRED'):validate_registration(b,hashlib.sha256(b).hexdigest())
