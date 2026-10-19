"""Focused offline regression of the actual outcome and diagnostic seams."""
from datetime import datetime,timezone,timedelta
import json,time
import pytest
from verification.ingestion_storage.connection_diagnostics import safe_failure
from verification.ingestion_storage.operational_runner import Journal
from verification.ingestion_storage.operational_outcome import session,finalise
from verification.ingestion_storage.operational_owner import Owner

EXPIRY=lambda:(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()

@pytest.mark.parametrize('message',['postgresql://secret:password@host/db','SCRAM-SHA-256$secret','private arbitrary text'])
def test_diagnostics_never_export_message_or_url(message):
    class OperationalError(Exception):sqlstate='28P01'
    observed=safe_failure(OperationalError(message),'DRIVER_CONNECT')
    assert observed==dict(phase='DRIVER_CONNECT',exception_kind='OperationalError',sqlstate='28P01',underlying_cause='UNDETERMINED',message_exported=False,reason_code='UNKNOWN',classification_source='NONE',failed_native_connection_finished=False)
    assert message not in json.dumps(observed)

def test_unrecognised_exception_names_and_sqlstate_do_not_escape():
    class arbitrary_secret(Exception):sqlstate='secret-token'
    assert safe_failure(arbitrary_secret('hidden'),'SERVER_IDENTITY')['exception_kind']=='OTHER'
    assert safe_failure(arbitrary_secret(),'SERVER_IDENTITY')['sqlstate'] is None

@pytest.mark.parametrize('fault',['delayed_input','input_timeout','prepare_failure','expired'])
def test_shared_session_reports_every_early_exit(tmp_path,fault):
    j=Journal(tmp_path/fault);calls=[];lines=[]
    def reader():
        assert not calls
        if fault=='delayed_input':time.sleep(.03)
        if fault=='input_timeout':time.sleep(1.0)
        return 'never_export_this_credential'
    def prepare(raw,started):
        calls.append('prepare');raise RuntimeError(raw)
    expiry=EXPIRY() if fault!='expired' else (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    timing=dict(input_seconds=.5,active_seconds=1.5,work_seconds=1.0,diagnostic_seconds=.2,report_seconds=.2,outer_seconds=3)   # wide margins: a loaded runner must not turn a 30 ms read into a timeout
    from verification.ingestion_storage.operational_preparation import Progress
    result=session(j,expiry,reader,prepare,output=lambda x,**kw:lines.append(x),timing=timing,progress=Progress())
    assert result['status']=='STOP_RECONCILE_NO_RETRY'
    assert json.loads((j.root/'final-result.json').read_bytes())==result
    assert result['accounting']['administration']['connections']=={'value':0,'basis':'MEASURED'}   # measured zero; without a progress record it is UNKNOWN (see preparation_stages)
    assert result['authority_invalidation']=='NOT_REQUIRED_NO_AUTHORITY'
    assert len(lines)==1 and 'never_export_this_credential' not in lines[0] and 'never_export_this_credential' not in j.file.read_text()
    assert calls==([] if fault in ('input_timeout','expired') else ['prepare'])

def test_final_output_failure_never_raises_second_exception(tmp_path):
    j=Journal(tmp_path/'output');calls=[]
    def output(*args,**kwargs):calls.append(True);raise BrokenPipeError('private text')
    result=finalise(j,dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',accounting={}),input_seconds=0,active_started=None,output=output)
    assert result['reason']=='FINAL_EVIDENCE_OR_OUTPUT_UNCERTAIN' and len(calls)==2
    assert (j.root/'final-result.json').exists()

def test_uncertain_admin_effect_forbids_automatic_invalidation():
    o=Owner(lambda:pytest.fail('no reconnect/mutation'),lambda *_:None,lambda:None,expiry=datetime.now(timezone.utc),bindings={})
    o.authorities=['EXACT'];o.effect_uncertain=True
    assert o.invalidate_failure()=='UNCERTAIN_RECONCILE'
    assert o.connections==0


def test_full_result_not_written_before_combined_output_bound(tmp_path):
    j=Journal(tmp_path/'bound')
    (j.root/'retained').write_bytes(b'x'*(2*1024**2-16000))
    result=finalise(j,dict(status='FAILED',accounting={},large='x'*20000),input_seconds=0,active_started=None,output=lambda *a,**k:None)
    assert result['reason']=='FINAL_EVIDENCE_OR_OUTPUT_UNCERTAIN'
    saved=json.loads((j.root/'final-result.json').read_bytes())
    assert 'large' not in saved
    assert sum(p.stat().st_size for p in j.root.iterdir())<2*1024**2


def test_active_session_blocked_final_output_has_hard_reporting_deadline(tmp_path):
    import subprocess,sys
    script=r"""
import time,sys
from verification.ingestion_storage.operational_runner import Journal
from verification.ingestion_storage.operational_outcome import session
from datetime import datetime,timezone,timedelta
j=Journal(sys.argv[1])
class Worker:
 def execute(self):return {'status':'FAILED','cleanup':'UNCERTAIN','accounting':{}}
def blocked(*a,**k):time.sleep(30)
session(j,(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(),lambda:'hidden',lambda raw,started:Worker(),output=blocked,timing=dict(input_seconds=1,active_seconds=10,work_seconds=8,diagnostic_seconds=1,report_seconds=.1,outer_seconds=12))
"""
    began=time.monotonic()
    r=subprocess.run([sys.executable,'-c',script,str(tmp_path/'blocked')],capture_output=True,timeout=20)
    assert r.returncode==124 and time.monotonic()-began<10      # the output call blocks for 30 s; exiting well under that proves the hard reporting deadline, independent of interpreter start-up and import time on a loaded runner
    assert (tmp_path/'blocked'/'final-result.json').exists()
