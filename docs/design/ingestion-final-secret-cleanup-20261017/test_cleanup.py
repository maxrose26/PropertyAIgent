import importlib.util,json,sys,time
from pathlib import Path
from types import SimpleNamespace
import pytest
spec=importlib.util.spec_from_file_location('cleanup',Path(__file__).with_name('cleanup.py'));c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
sys.path.insert(0,'tests')
from storage_gh_fixture import real_gh_store

def test_real_gh_exact_two_deletes_and_one_names_get(real_gh_store,monkeypatch):
    metadata,secret,store,requests=real_gh_store
    monkeypatch.setattr(c,'unexpired',lambda:None)
    for name in (*c.NAMES,'DATABASE_URL'):store[name]=b'DISPOSABLE_CIPHERTEXT_ONLY'
    events=[]
    def run(command,**kw):return SimpleNamespace(returncode=0,stdout=metadata(command),stderr=b'')
    result=c.calls(lambda e,p:events.append((e,p)),time.monotonic(),runner=run)
    assert result['verified'],dict(result=result,requests=requests)
    assert result['api_requests']==3 and result['database_connections']==0
    assert result['names']==dict.fromkeys(c.NAMES,'ABSENT') and result['database_url_present'] is True
    assert set(store)=={'DATABASE_URL'}
    assert [m for m,p in requests[1:]]==['DELETE','DELETE','GET']
    assert [e for e,p in events].count('deletion_intent')==2
    assert [e for e,p in events].count('deletion_ack')==2
    assert events[-2][0]=='absence_observation' and events[-1][0]=='cleanup_observation'

@pytest.mark.parametrize('mode',['timeout','403','unexpected200','ambiguousheaders'])
def test_uncertain_first_delete_stops_second_mutation(mode,monkeypatch):
    monkeypatch.setattr(c,'unexpired',lambda:None);calls=[];events=[]
    def run(command,**kw):
        calls.append(command)
        if '--include' in command:
            if mode=='timeout':raise TimeoutError()
            code=403 if mode=='403' else 200
            body=b'HTTP/2.0 204 No Content\r\nHTTP/2.0 204 No Content\r\n' if mode=='ambiguousheaders' else ('HTTP/2.0 %s Error\r\n'%code).encode()
            return SimpleNamespace(returncode=1 if mode=='403' else 0,stdout=body,stderr=b'')
        return SimpleNamespace(returncode=0,stdout=json.dumps(dict(total_count=3,names=list(c.NAMES),database_url_present=True)).encode(),stderr=b'')
    result=c.calls(lambda e,p:events.append((e,p)),time.monotonic(),runner=run)
    assert len(calls)==2 and '--include' in calls[0] and '--include' not in calls[1]
    assert result['verified'] is False and result['uncertain_delete']==c.NAMES[0] and not result['delete_acknowledgements']
    assert sum(e=='deletion_intent' for e,p in events)==1

@pytest.mark.parametrize('metadata',[{'total_count':101,'names':[],'database_url_present':True},{'total_count':1,'names':[],'database_url_present':False},{'total_count':1,'names':['UNRELATED'],'database_url_present':True},{'total_count':1,'names':[],'database_url_present':'true'}])
def test_missing_or_unproven_preserved_secret_never_passes(metadata,monkeypatch):
    monkeypatch.setattr(c,'unexpired',lambda:None);calls=[]
    def run(command,**kw):
        calls.append(command)
        return SimpleNamespace(returncode=0,stdout=b'HTTP/2.0 204 No Content\r\n' if '--include' in command else json.dumps(metadata).encode(),stderr=b'')
    result=c.calls(lambda *x:None,time.monotonic(),runner=run)
    assert result['verified'] is False and len(calls)==3

def test_expired_scope_makes_no_api_call(monkeypatch):
    def expired():raise ValueError('ORIGINAL_EXPIRY')
    monkeypatch.setattr(c,'unexpired',expired)
    result=c.calls(lambda *x:None,time.monotonic(),runner=lambda *a,**k:pytest.fail('unexpected API'))
    assert result['api_requests']==0 and result['verified'] is False
