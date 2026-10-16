"""Synthetic source fixtures only. No source/DB calls or real-world claims."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import time
import pytest
from verification.discovery import screening_capture as cap,screening_assessment as run
from verification.discovery.arcus_ui_config import SCREENING_CONFIG,SCREENING_CASE,MANCHESTER
from verification.discovery.arcus_ui_window import read_cards,qualify_segment


def immediate(coro):
    try:coro.send(None)
    except StopIteration as e:return e.value
    raise AssertionError('unexpected IO')


class Fields:
    def __init__(self,texts,timeout=None):self.texts=texts;self.timeout=timeout
    async def count(self):return len(self.texts)
    def filter(self,has_text):return Fields([x for x in self.texts if has_text.search(x.replace('\n',''))],self.timeout)
    def nth(self,i):return Fields([self.texts[i]],self.timeout)
    async def inner_text(self,**kw):
        from playwright.async_api import TimeoutError
        if self.timeout and self.texts[0].startswith(self.timeout):raise TimeoutError('synthetic')
        return self.texts[0]
    async def text_content(self,**kw):return self.texts[0].replace('\n','')


def row(proposal='Erection of 49 dwellings',extras=(),timeout=None):
    items=Fields(['Reference\nTEST/26','Valid Date\n02/10/2026','Applicant\nPRIVATE',*(['Description\n'+proposal] if proposal is not None else []),*extras],timeout)
    fields=immediate(cap.capture_fields(items))
    card=dict(fields=[{'label':'Reference','value':'TEST/26'},{'label':'Valid Date','value':'02/10/2026'}],
        links=[dict(text='TEST/26',href='https://arcusbe.manchester.gov.uk/pr/s/detail/'+('a'*18)+'?c__r=Arcus_BE_Public_Register')],assessment_capture=fields)
    return qualify_segment('Showing 1 to 1 of 1 results',[card],1,config=SCREENING_CONFIG)[3][0]


def source(rows):
    n=len(rows)
    return dict(case=SCREENING_CASE,destination=SCREENING_CONFIG.destination,persistence=False,failure=None,safety_failure=False,safety_events=[],
        cleanup='CONTEXT_BROWSER_CLOSED',process_cleanup='CLOSED',live_owned_survivors=0,supervisor_limit_hit=False,
        enumeration_evidence='COUNT_RECONCILED',applied_interval=['2026-10-01','2026-10-03'],requested_interval=['2026-10-01','2026-10-03'],completeness='UNKNOWN',
        requests=20,decoded_bytes=1000,encoded_bytes=800,outbound_payload_bytes=100,public_ui_posts=1,measured_public_ui_posts=1,
        supervisor_seconds=5,peak_owned_rss=100000,pages=1,navigations=1,listing_records=rows,
        listing_segments=[dict(ordinal=1,first=1,last=n,total=n)])


def test_exact_fields_concatenated_dom_and_optional_date_alias():
    r=row(extras=['Received Date\n01/10/2026'])
    assert r['fields']['proposal']['value']=='Erection of 49 dwellings'
    assert r['fields']['received_date']['state']=='PRESENT_VALUE'
    assert r['fields']['application_type']['state']=='UNKNOWN'
    assert 'PRIVATE' not in json.dumps(r)
    assert next(x for x in r['assessment_capture'] if x['label']=='Description')['dom_text_content']=='DescriptionErection of 49 dwellings'


def test_optional_timeout_does_not_invalidate_proposal():
    r=row(extras=['Site Address\nExample'],timeout='Site Address')
    out=run.assess(source([r]))
    assert out['outcome']=='GO' and out['proposal_capture']['usable']==1
    assert out['field_states']['address']=={'UNKNOWN':1}


@pytest.mark.parametrize('text',[None,'x'*8193])
def test_missing_or_truncated_proposals_are_partial_not_full(text):
    out=run.assess(source([row(text)]))
    assert out['enumeration_outcome']=='COMPLETE' and out['outcome']=='PARTIAL'
    assert out['proposal_capture']['usable']==0 and out['citation_complete'] is False


def test_conflicting_proposal_aliases_not_usable_but_identity_enumerated():
    out=run.assess(source([row(extras=['Proposal\nOther proposal'])]))
    assert out['field_states']['proposal']=={'CONFLICTING':1}
    assert out['outcome']=='PARTIAL'


@pytest.mark.parametrize('ref',['142419/FO/2025','117039/FUL/25','PLA-2026-001845','PA/2025/1084','25/01149/FUL','NMA/356901/26','DC/100094','01859/26'])
def test_complete_literal_citation_and_support(ref):
    text='Variation of '+ref+' to amend landscaping.'
    c=cap.citations(text)
    assert [x['literal'] for x in c['occurrences']]==[ref]
    x=c['occurrences'][0]
    assert text[x['start']:x['end']]==ref and ref in x['supporting_wording']
    assert x['target_council'] is None and not x['confirmed_relationship']


def test_dates_not_references_and_all_captured_text_fields_scanned():
    assert cap.citations('Received 01/10/2026')['occurrences']==[]
    r=row(extras=['Site Address\nLand adjacent to PA/2025/1084'])
    s=cap.screen_row(r)
    assert s['citations']['occurrences'][0]['source_field']=='address'
    assert s['disposition']=='RELATED_APPLICATION_FOLLOW_THROUGH'


def test_no_generic_unit_count_promotion_or_admin_signal_loss():
    a=cap.screen_row(row('Erection of 40 industrial units'))
    assert a['disposition']=='DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE'
    assert a['residential_dwelling_count'] is None
    b=cap.screen_row(row('Discharge of condition relating to NMA/356901/26 for housing'))
    assert b['disposition']=='RELATED_APPLICATION_FOLLOW_THROUGH' and b['retained']


@pytest.mark.parametrize('change',[dict(requests=81),dict(decoded_bytes=21*1024*1024),dict(peak_owned_rss=1024**3+1),
    dict(supervisor_seconds=-1),dict(live_owned_survivors=1),dict(applied_interval=['2026-10-15','2026-10-15']),
    dict(destination='https://wrong.invalid'),dict(enumeration_evidence='PAGE_CAP',completeness='INCOMPLETE')])
def test_resource_criteria_or_cap_cannot_be_full_success(change):
    out=run.assess(dict(source([row()]),**change))
    assert out['outcome']!='GO' and not out['proposal_capture']['full_mechanism_success']


def test_single_use_binding_and_frozen_manifest():
    sha='a'*40
    env=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',
        GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+run.WORKFLOW+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',JOB_STARTED_EPOCH=str(int(time.time())))
    run.admit(sha,run.MANIFEST_SHA,run.AUTHORITY,env)
    for k,v in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('GITHUB_SHA','b'*40),('GITHUB_REF','refs/heads/other')]:
        with pytest.raises(ValueError):run.admit(sha,run.MANIFEST_SHA,run.AUTHORITY,dict(env,**{k:v}))
    with pytest.raises(ValueError):run.admit(sha,run.MANIFEST_SHA,run.AUTHORITY,env,workflow_bytes=b'changed')
    with pytest.raises(ValueError):run.validate_plan(dict(run.plan(),scope='other'))
    assert run.manifest()['expected_current_count'] is None


def test_checkpoint_hash_gate(tmp_path):
    from verification.discovery.r0_registered_scopes import AuditStore
    env=dict(GITHUB_SHA='a'*40,GITHUB_RUN_ID='123')
    (tmp_path/'execution.json').write_text(json.dumps(dict(sha='a'*40,run_id='123',manifest_sha256=run.MANIFEST_SHA,run_number=1,attempt=1,persistence=False)))
    store=AuditStore(tmp_path,run.PROFILE);s=source([row()]);store.record(s);store.finish(run.assess(s),tmp_path/'result.json')
    assert run.verify(tmp_path,env)['outcome']=='GO'
    (tmp_path/'checkpoints/000.json').write_text('{}')
    with pytest.raises(ValueError,match='CHECKPOINT_HASH'):run.verify(tmp_path,env)
