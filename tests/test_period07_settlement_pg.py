"""Disposable PG17; production operations with synthetic bodies, never live writes."""
import copy,hashlib,json,time
import pytest
from tests.test_attempt06_owner_path_pg import world,act,Fault
from verification.ingestion_storage import attempt06_recovery as a,period07_settlement as s,intake_owner as op
from verification.ingestion_storage.database_evidence import canonical,path

@pytest.fixture
def failed07(world,monkeypatch):
 w=world;c=w['boot'];act(w,a.recover);act(w,a.dispose)
 ctl=op.control(c);monkeypatch.setattr(s,'A06_RECEIPT_SHA',a.sha(ctl['intake_periods'][a.PERIOD]['failed_runs'][a.RUN]))
 w['history06']=copy.deepcopy(ctl['intake_periods'][a.PERIOD]);ctl.update(s.STOP8)
 ctl['intake_run']=dict(id=s.RUN,period=s.PERIOD,state='OPEN',day='2026-11-02',publication_path=path(s.PERIOD,s.RUN,'final/result-before-publication.json'))
 ctl['intake_periods'][s.PERIOD]=dict(execution_binding=s.BINDING,evidence_backend='POSTGRES_PILOT_V1',fixed_window={'start':'2026-10-27','end':'2026-11-02'},max_runs=1,councils={'tameside':{},'manchester':{}},days={'2026-11-02':{'tameside':s.KEY}})
 ctl['grants'][s.AUTHORITY]=dict(intake_run=s.RUN,intake_period=s.PERIOD,capture_key=s.KEY,execution_binding=s.BINDING,expires_at=0)
 ctl['unrelated_preserved']={'stop':'DO_NOT_CHANGE'}
 c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
 patch=dict(key=s.KEY,authority=s.AUTHORITY,revision=s.PERIOD+'-2026-11-02-tameside',state='CLAIMED',phase='SOURCE_INTENT',fence=1,attempt_count=1,checkpoint=None,lease_until=time.time()-20,owner='synthetic',task='DISCOVERY',contract='tameside-screening-metadata-five-v1',subject=a.SCOPE)
 c.execute('INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=%s',(json.dumps(patch),op.CONTROL))
 c.execute("INSERT INTO ingestion_work_attempts(work_key,fence,owner,started_at,authority,phase) VALUES(%s,1,'synthetic',0,%s,'SOURCE_INTENT')",(s.KEY,s.AUTHORITY))
 source=dict(council='tameside',requested_interval=['2026-10-27','2026-11-02'],date_semantics='RECEIVED',failure='CALIBRATION_NAVIGATION_AMBIGUOUS',resource={'requests_attempted':3})
 final=dict(period=s.PERIOD,run_id=s.RUN,execution_binding=s.BINDING,status='STOP_RECONCILE_NO_RETRY',reason='IDOX_PAGINATION_PROFILE_BINDING',scopes=[],usage={'requests':3,'requests_status':'COMPLETE'})
 data={'capture-1/source.json':source,'final/result-before-publication.json':final,'final/events-before-publication.json':[dict(event='source_closed',data=dict(council='tameside',metrics={'requests':3}))]}
 hashes={}
 for name,v in data.items():
  raw=canonical(v);h=hashlib.sha256(raw).hexdigest();hashes[name]=h
  c.execute('INSERT INTO ingestion_run_evidence(period,run_id,name,body,sha256) VALUES(%s,%s,%s,%s,%s)',(s.PERIOD,s.RUN,name,raw,h))
 monkeypatch.setattr(s,'EVIDENCE',hashes)
 w['evidence_before']=c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
 return w

def read(w):
 with w['actor']() as c:return s.inspect(c,w['binding'])

@pytest.mark.parametrize('mode',['normal','before','lost','after_recover','before_cleanup'])
def test_atomic_settlement_and_uncertain_ack(failed07,mode):
 w=failed07;c=w['boot'];before=op.ledger_sha(c);members=c.execute(op.MEMBERS).fetchall()
 assert read(w)['status']=='READY_FOR_REVIEW_NOT_AUTHORISED'
 class Break(Fault):
  def execute(self,q,p=None):
   r=super().execute(q,p)
   if mode=='after_recover' and q.startswith('SELECT public.ingestion_recover_abandoned'):raise RuntimeError('SYNTHETIC_AFTER_RECOVER')
   if mode=='before_cleanup' and q.startswith('UPDATE public.ingestion_work_items SET outcome'):raise RuntimeError('SYNTHETIC_BEFORE_CLEANUP')
   return r
 with w['actor']() as actor:
  wrapped=Break(actor,mode)
  if mode=='normal':s.recover(wrapped,w['binding'])
  else:
   with pytest.raises(RuntimeError):s.recover(wrapped,w['binding'])
 assert c.execute(op.MEMBERS).fetchall()==members
 assert c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()==w['evidence_before']
 assert op.control(c)['intake_periods'][a.PERIOD]==w['history06']
 if mode in ('normal','lost'):
  assert read(w)['status']=='COMMITTED_STATE_VERIFIED_READ_ONLY'
  ctl=op.control(c);r=ctl['intake_periods'][s.PERIOD]['failed_runs'][s.RUN]
  assert r['actual_requests']==3 and r['request_count_status']=='COMPLETE' and r['manchester']=='NOT_ATTEMPTED' and r['original_marker']['state']=='OPEN'
  assert op.stop_snapshot(ctl)==s.STOP9 and ctl['unrelated_preserved']=={'stop':'DO_NOT_CHANGE'}
  digest=op.ledger_sha(c)
  with w['actor']() as actor:
   with pytest.raises(op.Denied):s.recover(actor,w['binding'])
  assert op.ledger_sha(c)==digest
 else:assert op.ledger_sha(c)==before

@pytest.mark.parametrize('drift',['id','stop','generation','lease','fence','attempt','checkpoint','evidence','count','manchester','history06','permission'])
def test_changed_binding_refuses_atomically(failed07,drift,monkeypatch):
 w=failed07;c=w['boot'];ctl=op.control(c)
 if drift=='id':ctl['intake_run']['id']='0'*32
 elif drift=='stop':ctl['manual_stop']='UNRELATED'
 elif drift=='generation':ctl['hard_stop_generation']=9
 elif drift=='history06':ctl['intake_periods'][a.PERIOD]['failed_runs'][a.RUN]['actual_requests']=0
 elif drift=='lease':c.execute('UPDATE ingestion_work_items SET lease_until=%s WHERE key=%s',(time.time()+100,s.KEY))
 elif drift=='fence':c.execute('UPDATE ingestion_work_items SET fence=2 WHERE key=%s',(s.KEY,))
 elif drift=='attempt':c.execute('UPDATE ingestion_work_attempts SET finished_at=1 WHERE work_key=%s',(s.KEY,))
 elif drift=='checkpoint':c.execute("UPDATE ingestion_work_items SET checkpoint='{}' WHERE key=%s",(s.KEY,))
 elif drift=='manchester':c.execute('UPDATE ingestion_work_items SET revision=%s WHERE key=%s',(s.PERIOD+'-2026-11-02-manchester',op.RECOVERED[0]))
 elif drift=='permission':c.execute('GRANT ingestion_recovery_operator TO postgres WITH ADMIN FALSE, INHERIT TRUE, SET FALSE')
 elif drift=='evidence':c.execute("UPDATE ingestion_run_evidence SET body=convert_to('changed','UTF8') WHERE period=%s AND name='capture-1/source.json'",(s.PERIOD,))
 elif drift=='count':
  raw=canonical(dict(council='tameside',requested_interval=['2026-10-27','2026-11-02'],date_semantics='RECEIVED',failure='CALIBRATION_NAVIGATION_AMBIGUOUS',resource={'requests_attempted':0}));h=hashlib.sha256(raw).hexdigest()
  c.execute("UPDATE ingestion_run_evidence SET body=%s,sha256=%s WHERE period=%s AND name='capture-1/source.json'",(raw,h,s.PERIOD));monkeypatch.setitem(s.EVIDENCE,'capture-1/source.json',h)
 c.execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(ctl),op.CONTROL))
 before=op.ledger_sha(c);members=c.execute(op.MEMBERS).fetchall()
 with w['actor']() as actor:
  with pytest.raises(Exception):s.recover(actor,w['binding'])
 assert op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==members
