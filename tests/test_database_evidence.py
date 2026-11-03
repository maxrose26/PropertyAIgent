import copy,hashlib,json
import pytest
from app.ingestion.ledger import Denied
from app.ingestion.batching import archive_capture
from verification.ingestion_storage.database_evidence import store,validate_descriptor,BACKEND,canonical,SOURCE_LIMIT

def callbacks():
 data={};calls=[]
 def write(p,r,n,b):
  calls.append(('write',p,r,n))
  if (p,r,n) in data and data[p,r,n]!=b:raise Denied('CONFLICT')
  data[p,r,n]=b
  return dict(backend=BACKEND,period=p,run_id=r,name=n,path=f'docs/design/ingestion-operational-execution-daily-intake/{p}/{r}/{n}',bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),readback_verified=False)
 def read(p,r,n):calls.append(('read',p,r,n));return data[p,r,n]
 return data,calls,write,read

def test_exact_bytes_independent_read_and_capture_receipt():
 d,c,w,r=callbacks();raw=canonical({'council':'tameside','opaque':'synthetic'})
 receipt=store(raw,'pilot','a'*32,'capture-1/source.json',w,r)
 assert [x[0] for x in c]==['write','read'] and receipt['bytes']==len(raw)
 assert archive_capture(json.loads(raw),lambda _:receipt)==receipt
 assert store(raw,'pilot','a'*32,'capture-1/source.json',w,r)==receipt

def test_conflict_and_mismatch_never_success_or_retry():
 d,c,w,r=callbacks();store(b'{}','pilot','a'*32,'capture-1/source.json',w,r)
 with pytest.raises(Denied,match='CONFLICT'):store(b'{"different":1}','pilot','a'*32,'capture-1/source.json',w,r)
 def broken(*a):return b'WRONG'
 with pytest.raises(Denied,match='READBACK'):store(b'{}','pilot','a'*32,'capture-1/source.json',w,broken)

def test_unknown_commit_is_not_retried():
 calls=[]
 def lost(*a):calls.append(1);raise RuntimeError('synthetic lost acknowledgement')
 with pytest.raises(RuntimeError):store(b'{}','pilot','a'*32,'capture-1/source.json',lost,lambda *_:b'{}')
 assert calls==[1]

def test_source_size_and_legacy_git_receipt_unchanged():
 d,c,w,r=callbacks()
 with pytest.raises(Denied,match='BOUND'):store(b'x'*(SOURCE_LIMIT+1),'pilot','a'*32,'capture-1/source.json',w,r)
 assert c==[]
 source={'value':1};raw=canonical(source);legacy=dict(commit='b'*40,path='docs/design/old/source.json',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),readback_verified=True)
 assert archive_capture(source,lambda _:legacy)==legacy
