from copy import deepcopy
from datetime import date
from unittest.mock import patch
import pytest
from verification.discovery import finite_acceptance as f
from verification.discovery.arcus_ui_config import UI_CASES,dated_config
from verification.discovery.arcus_ui_window import qualify_segment
from tests.test_discovery_arcus_ui import card

@pytest.fixture(autouse=True)
def credential_free_test_context(monkeypatch):
    # Wrapper already installed seccomp; remove only synthetic test DB context.
    monkeypatch.delenv('DATABASE_URL',raising=False)

def evidence(row):
    if row['council'] not in f.ARCUS:
        return dict(council=row['council'],requested_interval=[row['start'],row['end']],date_semantics=row['semantics'],persistence=False,failure=None,cleanup='SESSION_BOUNDARY_CLOSED',enumeration_evidence='COUNT_RECONCILED',
            applied_interval=[row['start'],row['end']],applied_evidence_sha256='a'*64,records=[],
            explicit_zero_evidence='NO_RESULTS_FOUND_AND_RETAINED_DATE_CRITERIA',pages=[dict(first=0,last=0,total=0,terminal=True)],
            resource=dict(requests_attempted=2,received_bytes=100))
    c=dated_config(UI_CASES['discovery_'+row['council']+'_ui_window'],row['start'],row['end'])
    return dict(requested_interval=[row['start'],row['end']],date_semantics=row['semantics'],case='discovery_'+row['council']+'_ui_window',destination=c.destination,persistence=False,failure=None,
        safety_failure=False,safety_events=[],cleanup='CONTEXT_BROWSER_CLOSED',process_cleanup='CLOSED',live_owned_survivors=0,
        supervisor_limit_hit=False,enumeration_evidence='COUNT_RECONCILED',applied_interval=[row['start'],row['end']],completeness='UNKNOWN',
        requests=20,decoded_bytes=1000,encoded_bytes=800,outbound_payload_bytes=100,public_ui_posts=1,measured_public_ui_posts=1,
        supervisor_seconds=5,pages=1,navigations=1,listing_records=[dict(reference='TEST/26',source_record_id='X')],listing_segments=[dict(first=1,last=1,total=1)])

def test_finite_nine_council_partition_and_hash():
    p=f.manifest('2026-09-18','2026-10-15','SUSPENSION_CATCHUP')
    assert len(p['rows'])==36 and {r['council'] for r in p['rows']}==f.COUNCILS
    for c in f.COUNCILS:
        rs=[r for r in p['rows'] if r['council']==c]
        assert rs[0]['start']=='2026-09-18' and rs[-1]['end']=='2026-10-15'
        assert all((date.fromisoformat(b['start'])-date.fromisoformat(a['end'])).days==1 for a,b in zip(rs,rs[1:]))
    r=f.execute(p,f.digest(p),reader=evidence,clock=lambda:0)
    assert r['enumeration_completeness']=='COMPLETE' and r['completeness']=='UNKNOWN'
    assert r['source_contract_qualified'] is False
    with pytest.raises(ValueError):f.execute(p,'0'*64,reader=lambda r:pytest.fail('no call'))
    with pytest.raises(ValueError):f.manifest('2026-09-01','2026-10-15','PROSPECTIVE')

@pytest.mark.parametrize('change,state',[
    ({'failure':'TIMEOUT'},'FAILED'),({'capped':True},'INCOMPLETE'),({'applied_interval':None},'UNKNOWN'),
    ({'enumeration_evidence':'TOTAL_UNKNOWN'},'UNKNOWN'),({'explicit_zero_evidence':None},'UNKNOWN'),({'cleanup':'FAILED'},'UNKNOWN')])
def test_partial_never_complete_and_no_continuation(change,state):
    p=f.manifest('2026-10-15','2026-10-15','PROSPECTIVE');calls=[]
    def read(row):calls.append(row);return dict(evidence(row),**change)
    r=f.execute(p,f.digest(p),reader=read,clock=lambda:0)
    assert len(calls)==1 and r['results'][0]['completeness']==state and r['completeness']!='COMPLETE'
    assert len(r['not_attempted'])==8 and not r['completed_through_advanced']

def test_exception_budget_and_missing_accounting_stop():
    p=f.manifest('2026-10-15','2026-10-15','BACKFILL_AUDIT')
    r=f.execute(p,f.digest(p),reader=lambda r:(_ for _ in ()).throw(RuntimeError('unsafe payload')),clock=lambda:0)
    assert r['stop_reason']=='SOURCE_EXCEPTION' and 'unsafe payload' not in str(r)
    assert r['accounting_complete'] is False
    values=iter([0,1900]);r=f.execute(p,f.digest(p),reader=lambda r:pytest.fail('no dispatch'),clock=lambda:next(values))
    assert r['stop_reason']=='ROUND_BUDGET' and len(r['not_attempted'])==9
    r=f.execute(p,f.digest(p),reader=lambda r:dict(evidence(r),resource={}),clock=lambda:0)
    assert r['stop_reason']=='RESOURCE_ACCOUNTING'

@pytest.mark.parametrize('key',list(UI_CASES))
def test_arcus_window_changes_only_date_filters(key):
    import base64,json
    from urllib.parse import urlsplit,parse_qs
    old=UI_CASES[key];new=dated_config(old,'2026-10-15','2026-10-21')
    def payload(c):return json.loads(base64.b64decode(parse_qs(urlsplit(c.destination).query)['c__q'][0]))
    a,b=payload(old),payload(new)
    for x,y in zip(a['requests'][0]['searchFilters'],b['requests'][0]['searchFilters']):
        if x['fieldDeveloperName'] in ('PA_ADV_DateValidFrom','PA_ADV_DateValidTo'):
            assert y['fieldValue'] in ('2026-10-15','2026-10-21')
        else:assert x==y
    assert old.start=='2026-09-28' and old.end=='2026-10-04' and new.host==old.host

def test_dynamic_row_date_preserves_exact_identity():
    c=dated_config(UI_CASES['discovery_manchester_ui_window'],'2026-10-15','2026-10-21')
    assert qualify_segment('Showing 1 to 1 of 1 results',[card(valid='16/10/2026')],1,config=c)[2]==1
    with pytest.raises(ValueError):qualify_segment('Showing 1 to 1 of 1 results',[card(valid='02/10/2026')],1,config=c)

def test_no_secret_context(monkeypatch):
    p=f.manifest('2026-10-15','2026-10-15','PROSPECTIVE');monkeypatch.setenv('COMMITTEE_DATABASE_URL','synthetic')
    with pytest.raises(ValueError):f.execute(p,f.digest(p),reader=lambda r:pytest.fail('no source'))


def test_read_reuses_supervision_without_secret_inheritance(tmp_path):
    import json
    row=dict(council='bolton',semantics='RECEIVED',start='2026-10-15',end='2026-10-21')
    def supervisor(command,env,deadline):
        assert deadline==50 and set(env)=={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE'}
        assert command[2]=='verification.discovery.finite_acceptance'
        from pathlib import Path
        Path(command[-1]).write_text(json.dumps(evidence(row)))
        return 0,False
    with patch.object(f,'supervise',supervisor):assert f.read(row)['persistence'] is False


@pytest.mark.parametrize('council',['bolton','manchester'])
def test_wrong_audit_context_never_qualifies(council):
    row=dict(council=council,semantics=f.SEMANTICS[council],start='2026-10-15',end='2026-10-21')
    a=evidence(row)
    assert f.classify(row,a)=='COMPLETE' # count/criteria reconciliation only
    assert f.classify(row,dict(a,requested_interval=['2026-09-28','2026-10-04']))=='UNKNOWN'
    wrong={'case':'discovery_salford_ui_window'} if council in f.ARCUS else {'council':'bury'}
    assert f.classify(row,dict(a,**wrong))=='UNKNOWN'
