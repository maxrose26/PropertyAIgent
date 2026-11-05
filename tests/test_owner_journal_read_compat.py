"""Deployed journal encoding must not bypass the exact predecessor guard."""
import base64
import copy
import hashlib
import json
import zlib

import pytest

from verification.ingestion_storage import owner_pilot as p, attempt06_recovery as a


def state():
    return dict(period=a.PERIOD, status='CLOSED', job={'id':a.JOB},
        binding={'period':a.PERIOD,'execution_binding':a.BINDING},
        access={'state':'DATABASE_CLOSURE_ACKNOWLEDGED','render':{'state':'RESTORATION_ACKNOWLEDGED'}},
        closure_verification={'status':'VERIFIED','authorities_closed':True,'sessions':0},
        final_service={'suspended':True,'configuration_equal':True,'environment_equal':True},
        stable_credentials={'version':'STABLE_RESTRICTED_V1','passwords':dict.fromkeys(p.op.ROLES,'fixture-only'),
                            'verifier_sha256':dict.fromkeys(p.op.ROLES,'a'*64)},
        cleanup_reserve={'version':'CLEANUP_RESERVE_V1'})


def packed(s):
    s=copy.deepcopy(s)
    s['access']['binding']={'version':'ROOT_BINDING_REFERENCE_V1','sha256':hashlib.sha256(p.canonical(s['binding'])).hexdigest()}
    raw=p.canonical({k:s.pop(k) for k in list(s) if k in p.JOURNAL_METADATA_FIELDS})
    s['journal_metadata']=dict(version='JOURNAL_METADATA_DEFLATE_V1',bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(zlib.compress(raw)).decode())
    return s


@pytest.mark.parametrize('compressed',[False,True])
def test_actual_encrypted_journal_roundtrip(compressed,monkeypatch):
    monkeypatch.setattr(p,'PERIOD',a.SUCCESSOR)
    monkeypatch.setattr(p,'PREDECESSOR',a.PERIOD)
    class DB: key='fixture-only-journal-key'
    j=p.Journal(DB(),a.PERIOD)
    s=state(); stored=packed(s) if compressed else s
    recovered=j._vault(raw=j._vault(value=stored))
    a.predecessor06(recovered,snapshot={})
    assert recovered['stable_credentials']==s['stable_credentials']
    if compressed: assert recovered['access']['binding']==recovered['binding']


@pytest.mark.parametrize('bad',['hash','length','trailing','overlap','reference','job','session'])
def test_corruption_or_changed_identity_refused(bad):
    s=state()
    if bad=='job':s['job']['id']='wrong'
    if bad=='session':s['closure_verification']['sessions']=1
    stored=packed(s); meta=stored['journal_metadata']
    if bad=='hash':meta['sha256']='0'*64
    if bad=='length':meta['bytes']=65537
    if bad=='trailing':meta['data']=base64.b64encode(base64.b64decode(meta['data'])+b'junk').decode()
    if bad=='overlap':stored['binding']={}
    if bad=='reference':
        raw=json.loads(zlib.decompress(base64.b64decode(meta['data'])))
        raw['access']['binding']['sha256']='0'*64
        b=p.canonical(raw);meta.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),data=base64.b64encode(zlib.compress(b)).decode())
    with pytest.raises(p.op.Denied):a.predecessor06(p.hydrated_state(stored),snapshot={})
