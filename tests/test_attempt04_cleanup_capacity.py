"""Actual journal encryption and recovery path; synthetic DB/provider effects."""
import copy,hashlib,json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import owner_pilot as p
from verification.ingestion_storage.intake_owner_io import service_guard
from tests.test_owner_closure_space import state

def retained():
    s=state();s.update(period=p.PERIOD)
    s.pop('job');s.pop('job_terminal');s['intents'].pop('ONE_JOB')
    s['binding']['accepted_stop']=p.op.ACCEPTED_STOP
    s['access']['state']='ACTIVATION_ACKNOWLEDGED'
    s['access']['render']['state']='PUT_ACKNOWLEDGED'
    for n in ('PERIOD','ACTIVATE','HANDOFF'):s['intents'][n]={'state':'ACKNOWLEDGED'}
    s['access']['binding']=copy.deepcopy(s['binding'])
    return s

class MemoryDB:
    key='s'*64
    def __init__(self):
        from psycopg.pq import TransactionStatus
        self.rows=[];self.pgconn=SimpleNamespace(transaction_status=TransactionStatus.IDLE)
    @contextmanager
    def connection(self):yield self
    def execute(self,q,args):
        assert q.startswith('SELECT * FROM public.ingestion_intake_owner_state(')
        if len(args)==3:self.row=self.rows[-1]
        else:
            assert args[2]==self.rows[-1][2]
            raw=args[3];self.row=(self.rows[-1][0]+1,raw,hashlib.sha256(raw).hexdigest());self.rows.append(self.row)
        return self
    def fetchone(self):return self.row

def pilot_with_retained_state(s):
    obj=object.__new__(p.Pilot);obj.db=MemoryDB();obj.journal=p.Journal(obj.db)
    raw=obj.journal._vault(value=s);obj.db.rows=[(37,raw,hashlib.sha256(raw).hexdigest())]
    obj.state=obj.journal.load();return obj

def test_retained_preclosure_state_reserves_and_measures_every_remaining_snapshot():
    obj=pilot_with_retained_state(retained());before=copy.deepcopy(obj.state);old=obj.db.rows[0]
    obj.reserve_closure_space();saved=obj.journal.load()
    assert obj.db.rows[0]==old and len(obj.db.rows)==2
    assert saved['closed_build_archive']['prior_ciphertext_sha256']==old[2]
    for n in ('binding','access','intents','original_environment','stable_credentials'):assert saved[n]==before[n]
    proof=saved['recovery_capacity'];assert proof['remaining_snapshots']==9
    assert len(proof['projected_ciphertext_bytes'])==9 and max(proof['projected_ciphertext_bytes'].values())<=32768
    assert b'SECRET_SENTINEL' not in obj.db.rows[-1][1]
    assert saved.get('closure_receipt') is None and saved['access']['state']=='ACTIVATION_ACKNOWLEDGED'

@pytest.mark.parametrize('drift',['job','intent','handoff','baseline','bound','slots'])
def test_unsafe_compaction_or_insufficient_capacity_refuses_before_write(drift):
    s=retained()
    if drift=='job':s['job']={'id':'job-'+'a'*20}
    elif drift=='intent':s['intents']['ONE_JOB']={'state':'INTENT_NO_RETRY'}
    elif drift=='handoff':s['access']['render']['state']='RESTORE_INTENT_NO_RETRY'
    elif drift=='baseline':s['access']['render']['original']={}
    elif drift=='bound':s['kept_closure_material']='z'*21500;s['original_service']={}
    obj=pilot_with_retained_state(s)
    if drift=='slots':obj.journal.ordinal=57
    with pytest.raises(p.op.Denied):obj.reserve_closure_space()
    assert len(obj.db.rows)==1

@pytest.mark.parametrize('lost_ack',[False,True])
def test_actual_recovery_path_fits_and_uncertain_put_is_read_back_not_repeated(monkeypatch,lost_ack):
    from requests.exceptions import ReadTimeout
    service={'id':p.SERVICE,'type':'cron_job','suspended':'suspended','autoDeploy':'no','branch':'master','serviceDetails':{'schedule':'0 5 * * *','envSpecificDetails':{'buildCommand':'original','startCommand':'/bin/true'}}}
    s=retained();guard=service_guard(service)
    s['original_guard']=s['binding']['render_config_sha256']=s['access']['binding']['render_config_sha256']=s['access']['render']['guard']=guard
    s['access']['render']['mapped_at']=1793794800.0
    s['binding']['timing_policy']={'version':'SEPARATE_EXPIRY_V2_RESERVE'}
    s['access']['binding']=copy.deepcopy(s['binding'])
    obj=pilot_with_retained_state(s);old=obj.db.rows[0];actual=copy.deepcopy(s['access']['render']['expected']);puts=[];events=[]
    def close(c,access,save):
        events.append('DATABASE_CLOSE')
        access['state']='ACCESS_DISABLED_ACKNOWLEDGED';save(access)
        access['membership_closure']='ACKNOWLEDGED';save(access)
        access.update(state='DATABASE_CLOSURE_ACKNOWLEDGED',passwords={});save(access)
        return dict(outcome='COMMIT_ACKNOWLEDGED',authorities=[],authority_expiry=0,sessions='ABSENT',temporary_owner='REMOVED')
    monkeypatch.setattr(p.op,'close',close)
    class API:
        def __init__(self):self.calls=0
        def call(self,method,suffix='',body=None):
            nonlocal actual
            self.calls+=1;assert self.calls<=8
            if method=='PUT':
                assert obj.journal.load()['access']['render']['state']=='RESTORE_INTENT_NO_RETRY'
                puts.append(True);actual={v['key']:v['value'] for v in body}
                if lost_ack:raise ReadTimeout('SECRET_SENTINEL')
                return []
            assert method=='GET'
            if suffix=='':return service
            if suffix=='/env-vars?limit=100':return [{'envVar':{'key':k,'value':v}} for k,v in actual.items()]
            assert suffix=='/jobs?limit=100';return []
        def close(self):pass
    obj.render_factory=API
    result=obj.recover()
    if lost_ack:
        assert result['status']=='CONTAINMENT_REQUIRES_REVIEW'
        result=obj.recover()
    assert result['status']=='CLOSED' and actual==s['original_environment'] and len(puts)==1
    assert events==['DATABASE_CLOSE'] and obj.db.rows[0]==old
    assert all(len(row[1])<=32768 for row in obj.db.rows) and obj.db.rows[-1][0]<=63
    assert 'SECRET_SENTINEL' not in json.dumps(result)
