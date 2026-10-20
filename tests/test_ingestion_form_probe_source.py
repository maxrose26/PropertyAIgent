"""Bolton FORM PROBE (specification 032 section 12.4): one request, an observation of any answer, no body, no tokens, a receipt that can never be a capture, and a coordinator that records it without
ever raising the accepted fail-safe stop for a council answer. Offline, no network, no database."""
import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from app.ingestion.coordinator import Coordinator
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion import form_probe as fp
from app.ingestion.ledger import Denied,DEFAULT_LIMITS
from verification.bolton_recon.fixtures import FORM
from verification.discovery.idox_window import WindowConfig,run_form_probe

CONFIG=WindowConfig(council='bolton',semantics='RECEIVED',start=__import__('datetime').date(2026,10,16),end=__import__('datetime').date(2026,10,16),max_transport_retries=0)


class Resp:
    def __init__(self,status=200,ctype='text/html',headers=None,body=FORM if isinstance(FORM,bytes) else FORM.encode()):
        self.status_code=status;self.headers=dict({'Content-Type':ctype} if ctype is not None else {},**(headers or {}));self.b=body;self.closed=False;self.raw=io.BytesIO()
    def iter_content(self,n):yield self.b
    def close(self):self.closed=True


def probe(response=None,*,raises=None):
    calls=[]
    def dispatch(method,url,**kw):
        calls.append((method,url,kw.get('data')))
        if raises:raise raises
        return response
    return run_form_probe(dispatch,CONFIG),calls


FORM_BYTES=FORM if isinstance(FORM,bytes) else FORM.encode()


# ---------------------------------------------------------------- the worker half
def test_a_recognised_form_is_observed_with_exactly_one_get_and_no_body():
    out,calls=probe(Resp())
    assert len(calls)==1 and calls[0][0]=='GET' and calls[0][2] is None      # one GET; no POST, no listing, no detail
    o=out['observation']
    assert o['outcome']=='FORM_RECOGNISED' and o['stage']=='FORM_PARSE' and o['failure'] is None
    assert o['transport']==dict(http_status=200,media_type='text/html',redirect='NONE',rejection_outcome=None,rejection_reason=None)
    assert o['body']['body_sha256']==hashlib.sha256(FORM_BYTES).hexdigest() and o['body']['body_bytes']==len(FORM_BYTES) and o['body']['shape_available'] is True
    assert out['resource']['requests_attempted']==1 and out['resource']['retries']==0 and out['resource']['redirects']==0 and out['resource']['retry_policy']=='NO_INTERNAL_RETRY'
    dumped=json.dumps(out)
    assert FORM_BYTES.decode('utf-8','replace')[:60] not in dumped and out['pages']==[] and out['records']==[] and out['persistence'] is False      # the body is never returned; no tokens, no rows


def test_form_tokens_are_never_exported():
    out,_=probe(Resp())
    import re
    tokens=set(re.findall(rb'value="([^"]{4,})"',FORM_BYTES))
    assert tokens      # the fixture does carry hidden values
    dumped=json.dumps(out).encode()
    for t in tokens:assert t not in dumped


@pytest.mark.parametrize('response,outcome,status,rejection',[
    (Resp(403,'text/html',body=b'<html>Access denied 203.0.113.9</html>'),'REQUEST_REJECTED',403,('SOURCE_UNAVAILABLE','HTTP failure')),
    (Resp(429,'text/html',body=b'slow down'),'REQUEST_REJECTED',429,('RATE_LIMITED','HTTP rate limit')),
    (Resp(503,'text/html',body=b'down'),'REQUEST_REJECTED',503,('SOURCE_UNAVAILABLE','transport failed')),
    (Resp(200,'application/json',body=b'{}'),'REQUEST_REJECTED',200,('PARTIAL_RETRIEVAL','response shape')),
])
def test_any_council_answer_is_an_observation_never_an_exception(response,outcome,status,rejection):
    out,calls=probe(response)
    o=out['observation']
    assert len(calls)==1 and o['outcome']==outcome and o['transport']['http_status']==status      # no retry, one request
    assert (o['transport']['rejection_outcome'],o['transport']['rejection_reason'])==rejection
    assert '203.0.113.9' not in json.dumps(out) and o['failure']=='BoundaryFailure:SOURCE_CONTRACT_REJECTED'


def test_a_redirect_is_recorded_not_followed_and_its_target_is_not_exported():
    out,calls=probe(Resp(302,'text/html',{'Location':'https://elsewhere.example/login?token=abc'},body=b''))
    assert len(calls)==1      # not followed
    t=out['observation']['transport']
    assert t['http_status']==302 and t['redirect']=='OTHER_ORIGIN' and 'elsewhere' not in json.dumps(out) and 'token=abc' not in json.dumps(out)


def test_html_that_is_not_the_form_is_reported_as_not_recognised_at_the_parse_stage():
    out,calls=probe(Resp(200,'text/html',body=b'<html><body>maintenance</body></html>'))
    o=out['observation']
    assert len(calls)==1 and o['outcome']=='FORM_NOT_RECOGNISED' and o['stage']=='FORM_PARSE' and o['transport']['http_status']==200


def test_a_transport_exception_is_an_observation_with_no_retry():
    out,calls=probe(raises=ConnectionError('boom SECRETISH'))
    o=out['observation']
    assert len(calls)==1 and o['outcome']=='REQUEST_REJECTED' and o['transport']['http_status'] is None and 'SECRETISH' not in json.dumps(out)


def test_an_oversize_answer_is_stopped_at_the_byte_ceiling():
    out,calls=probe(Resp(200,'text/html',body=b'x'*300000))
    assert len(calls)==1 and out['observation']['outcome']=='REQUEST_REJECTED' and out['resource']['received_bytes']<=262144+65536


# ---------------------------------------------------------------- the receipt
OUTER=dict(exit_code=0,peak_owned_rss=40_000_000,elapsed_seconds=1.0,cleanup='CLOSED',live_owned_survivors=0,expired=False,limit_hit=None)


def worker(response=None):
    out=probe(response or Resp())[0]
    out['cleanup']='SESSION_BOUNDARY_CLOSED'      # what form_probe() sets once the requests session is closed
    return out


def test_the_receipt_is_a_diagnostic_that_can_never_be_a_capture():
    receipt=fp.project(worker(),OUTER,DEFAULT_LIMITS)
    assert receipt['kind']=='FORM_PROBE_RECEIPT_V1' and receipt['source_qualification']=='DIAGNOSTIC_ONLY_NOT_A_CAPTURE' and receipt['body_retained'] is False
    assert receipt['cleanup']=='CLOSED' and receipt['accounting_complete'] is True and 'records' not in receipt and 'pages' not in receipt
    assert receipt['kind']!='LISTING_RECEIPT_V1'      # the SQL and every consumer of a capture require LISTING_RECEIPT_V1


def test_a_council_refusal_still_projects_to_a_receipt():
    receipt=fp.project(worker(Resp(403,'text/html',body=b'no')),OUTER,DEFAULT_LIMITS)
    assert receipt['observation']['outcome']=='REQUEST_REJECTED' and receipt['observation']['transport']['http_status']==403


@pytest.mark.parametrize('mutate',[
    lambda w:w.update(probe='LISTING'),lambda w:w.update(council='oldham'),lambda w:w.update(pages=[{'ordinal':1}]),lambda w:w.update(records=[{'reference':'x'}]),lambda w:w.update(cleanup='UNKNOWN'),
    lambda w:w['resource'].update(requests_attempted=2),lambda w:w['resource'].update(retries=1),lambda w:w['resource'].update(redirects=1),lambda w:w['resource'].update(received_bytes=10**7),
    lambda w:w['observation'].update(outcome='CAPTURED'),lambda w:w['observation'].update(extra=1),lambda w:w['observation'].update(stage='SEARCH_REQUEST'),lambda w:w['observation']['body'].update(body_bytes=-1),
    lambda w:w['observation']['body'].update(body_sha256='nothex'),lambda w:w['observation']['transport'].update(http_status=99),lambda w:w['observation'].update(failure='free text with spaces'),
])
def test_a_malformed_or_over_budget_worker_audit_is_refused(mutate):
    w=worker();mutate(w)
    with pytest.raises(Denied):fp.project(w,OUTER,DEFAULT_LIMITS)


@pytest.mark.parametrize('outer',[dict(OUTER,exit_code=1),dict(OUTER,cleanup='UNCERTAIN'),dict(OUTER,live_owned_survivors=1),dict(OUTER,expired=True),dict(OUTER,limit_hit='memory')])
def test_an_unsafe_supervisor_outcome_is_refused(outer):
    with pytest.raises(Denied):fp.project(worker(),outer,DEFAULT_LIMITS)


# ---------------------------------------------------------------- the coordinator
class FakeLedger:
    def __init__(self,row):
        self.row=row;self.calls=[]
    def get(self,key):return self.row
    def intent(self,claim,op):self.calls.append(('intent',op))
    def resolve_source(self,claim,receipt):self.calls.append(('resolve_source',receipt['kind']))
    def finish(self,claim,outcome,*,state='COMPLETE',reason=None):self.calls.append(('finish',state,reason,outcome))
    def stop(self,reason,**kw):self.calls.append(('stop',reason))


def coordinator(ledger):
    contract=IdoxListingContract('bolton-received-idox-coordinator-v1',CONFIG,'a'*64)
    return Coordinator(ledger,{'bolton-received-idox-coordinator-v1':contract})


ROW=dict(contract='bolton-received-idox-coordinator-v1',task='DISCOVERY',subject=dict(kind='DISCOVERY_SCOPE',council='bolton',start='2026-10-16',end='2026-10-16',semantics='RECEIVED'),checkpoint=None,limits=dict(DEFAULT_LIMITS))
CLAIM=SimpleNamespace(key='k')


def test_the_coordinator_records_the_observation_and_finishes_the_item_unreusably():
    ledger=FakeLedger(dict(ROW))
    receipt=coordinator(ledger).idox_form_probe(CLAIM,lambda row:(worker(),OUTER))
    assert [c[0] for c in ledger.calls]==['intent','resolve_source','finish']      # the database gate first, then the observation, then the finish
    assert ledger.calls[0]==('intent','source_calls') and ledger.calls[1]==('resolve_source','FORM_PROBE_RECEIPT_V1')
    assert ledger.calls[2][:3]==('finish','UNSUPPORTED_CONTRACT','DIAGNOSTIC_FORM_PROBE_NO_CAPTURE') and receipt['kind']=='FORM_PROBE_RECEIPT_V1'


def test_a_council_refusal_never_raises_the_failsafe_stop():
    ledger=FakeLedger(dict(ROW))
    receipt=coordinator(ledger).idox_form_probe(CLAIM,lambda row:(worker(Resp(403,'text/html',body=b'denied')),OUTER))
    assert not any(c[0]=='stop' for c in ledger.calls) and receipt['observation']['transport']['http_status']==403


@pytest.mark.parametrize('reader',[lambda row:(_ for _ in ()).throw(RuntimeError('worker died')),lambda row:(dict(worker(),probe='LISTING'),OUTER),lambda row:(worker(),dict(OUTER,cleanup='UNCERTAIN'))])
def test_an_unsafe_or_unaccountable_outcome_raises_the_accepted_failsafe_stop(reader):
    ledger=FakeLedger(dict(ROW))
    with pytest.raises(Exception):coordinator(ledger).idox_form_probe(CLAIM,reader)
    assert ledger.calls[0]==('intent','source_calls') and ledger.calls[-1]==('stop','IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE') and not any(c[0] in ('resolve_source','finish') for c in ledger.calls)


def test_the_coordinator_refuses_a_wrong_scope_or_a_replay_before_any_intent():
    for row in (dict(ROW,subject=dict(ROW['subject'],end='2026-10-17')),dict(ROW,checkpoint={'kind':'X'}),dict(ROW,task='SCREENING')):
        ledger=FakeLedger(row)
        with pytest.raises(Denied):coordinator(ledger).idox_form_probe(CLAIM,lambda r:(worker(),OUTER))
        assert ledger.calls==[]      # no source intent, no stop: nothing was attempted
