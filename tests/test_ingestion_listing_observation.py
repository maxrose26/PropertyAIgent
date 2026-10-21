"""Partial listing observations (specification 033), offline.

RECONSTRUCTED FIXTURES - read this before relying on any test here. The page body returned by Bolton on 20 October 2026 was not retained (only its hash and the parsed rows survived). Every single-page
fixture below is therefore a RECONSTRUCTION built with the repository's own listing-page generator to reproduce the *parsed shape* that was observed (rows on one page, no `p.pager`, criteria echo accepted,
unknown total). They are not the original bytes and do not prove how Bolton actually renders any page. The multi-page fixture is likewise a reconstruction of the shape retained from the 14 October observation.
The real window runner, boundary, parser and adapter run over these injected responses; nothing contacts a council."""
import json
import re
from datetime import date

import pytest

from app.ingestion.batching import batch_plans,capture_once
from app.ingestion.idox_adapter import (IdoxListingContract,OBSERVATION_COUNCILS,OBSERVATION_DISPLAY_LABEL,OBSERVATION_KIND,OBSERVATION_PAGE_SIZES,OBSERVATION_WINDOW_CLAIM)
from app.ingestion import observation_history as oh
from app.ingestion.observation_screening import screen_observation
from app.ingestion.ledger import DEFAULT_LIMITS,Denied,digest
from app.ingestion.listing_screening import screen_row
from verification.discovery.idox_window import WindowConfig,run
from tests.test_discovery_idox_window import FORM,Response,page
from tests.test_discovery_ingestion_ledger import outer

WEEK=WindowConfig('bolton','RECEIVED',date(2026,9,28),date(2026,10,4),0)
LIMITS=dict(DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6)
T1='2026-10-20T21:49:30+00:00'
T2='2026-10-20T22:47:30+00:00'
T3='2026-10-21T08:00:00+00:00'
ECHO=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="28/09/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="04/10/2026"')
REFS=tuple(f'{5000+i}/26' for i in range(12))


def perform(bodies,config=WEEK):
    it=iter(bodies)
    return run(lambda *a,**k:Response(next(it)),config)


def single_page_audit(n=4,*,page_size_marker=None,config=WEEK):
    """RECONSTRUCTED: one results page of `n` rows, no pager, then the same page again (sort) and the criteria echo."""
    body=page(first=1,last=n,total=n,refs=REFS[:n],pager=False)
    if page_size_marker:body=body.replace(b'<option value="10" selected>10</option>',page_size_marker,1)      # only the results-per-page selector, not the sort form's
    return perform([FORM,body,body,ECHO],config)


def multi_page_audit():
    """RECONSTRUCTED: 12 references over two pages with an explicit total (10 + 2); the first four rows equal the single-page fixture's rows."""
    p1=page(first=1,last=10,total=12,refs=REFS[:10],next_page=2)
    p2=page(first=11,last=12,total=12,refs=REFS[10:12]).replace(b'keyVal=K0',b'keyVal=K10').replace(b'keyVal=K1',b'keyVal=K11')
    return perform([FORM,p1,p1,p2,ECHO])


def stored(receipt):
    return json.loads(json.dumps(receipt,default=str))


def contract(enabled=True,config=WEEK):
    return IdoxListingContract('controller-idox',config,'a'*64,partial_observation=enabled)


def observe(audit=None,**kw):
    return contract().observe(audit or single_page_audit(),outer(),LIMITS,observed_at=kw.pop('observed_at',T1),**kw)


# ---------------------------------------------------------------- admission
def test_the_reconstructed_four_row_single_page_is_retained_as_an_observation_and_the_default_contract_still_stops():
    audit=single_page_audit()
    assert audit['enumeration_evidence']=='TOTAL_UNKNOWN' and audit['pages'][0]['page_size']==10 and audit['pages'][0]['rows']==4 and audit['pages'][0]['total'] is None
    with pytest.raises(Denied,match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):contract(False).project(audit,outer(),LIMITS)      # unchanged default behaviour
    with pytest.raises(Denied,match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):contract(True).project(audit,outer(),LIMITS)      # even an enabled contract never turns a TOTAL_UNKNOWN source into a receipt
    obs=observe(audit)
    assert obs['kind']==OBSERVATION_KIND==('LISTING_OBSERVATION_V1') and obs['window_claim']==OBSERVATION_WINDOW_CLAIM=='NONE' and len(obs['records'])==4 and obs['page']['page_size']==10
    assert obs['observed_at']==T1 and obs['display_label']==OBSERVATION_DISPLAY_LABEL=='Observed applications — window completeness not established'
    assert obs['requested_interval']==['2026-09-28','2026-10-04'] and obs['applied_interval_evidence']['evidence']=='STRICT_REFINE_FORM_ECHO' and re.fullmatch('[a-f0-9]{64}',obs['applied_interval_evidence']['sha256'])
    assert [r['provenance']['row_ordinal'] for r in obs['records']]==[1,2,3,4] and {r['provenance']['body_sha256'] for r in obs['records']}=={obs['page']['body_sha256']}
    assert obs['resources']['requests_attempted']==4 and obs['resources']['retries']==0 and obs['resources']['redirects']==0


def test_enablement_is_explicit_and_bolton_received_only():
    audit=single_page_audit()
    with pytest.raises(Denied,match='PARTIAL_OBSERVATION_NOT_ENABLED'):contract(False).observe(audit,outer(),LIMITS,observed_at=T1)      # default OFF
    assert OBSERVATION_COUNCILS==frozenset({'bolton'})
    bury=WindowConfig('bury','RECEIVED',date(2026,9,28),date(2026,10,4),0)
    with pytest.raises(Denied,match='PARTIAL_OBSERVATION_NOT_ENABLED'):contract(True,bury).observe(single_page_audit(config=bury),outer(),LIMITS,observed_at=T1)      # another council: never
    validated=WindowConfig('bolton','VALIDATED',date(2026,9,28),date(2026,10,4),0)
    with pytest.raises(Denied,match='PARTIAL_OBSERVATION_NOT_ENABLED'):contract(True,validated).observe(audit,outer(),LIMITS,observed_at=T1)


def test_only_a_non_empty_result_strictly_below_the_selected_page_size_is_admitted():
    for n in (1,4,9):assert len(observe(single_page_audit(n))['records'])==n
    full=single_page_audit(10)      # rows == page size: refused, as is anything larger
    with pytest.raises(Denied,match='IDOX_OBSERVATION_ROWS_BELOW_PAGE_SIZE'):contract().observe(full,outer(),LIMITS,observed_at=T1)
    small=single_page_audit(4,page_size_marker=b'<option value="5" selected>5</option>')      # the SELECTED size is what counts: 4 < 5 admitted, but 5 rows of 5 is not
    assert len(contract().observe(small,outer(),LIMITS,observed_at=T1)['records'])==4
    five=single_page_audit(5,page_size_marker=b'<option value="5" selected>5</option>')
    with pytest.raises(Denied,match='IDOX_OBSERVATION_ROWS_BELOW_PAGE_SIZE'):contract().observe(five,outer(),LIMITS,observed_at=T1)
    empty=dict(single_page_audit(),records=[],unique_references=0);empty['pages']=[dict(empty['pages'][0],rows=0)]
    with pytest.raises(Denied,match='IDOX_OBSERVATION_ROWS_BELOW_PAGE_SIZE'):contract().observe(empty,outer(),LIMITS,observed_at=T1)
    old=single_page_audit();old['pages']=[{k:v for k,v in old['pages'][0].items() if k!='page_size'}]      # an audit from before the page size was recorded cannot be admitted
    with pytest.raises(Denied,match='IDOX_OBSERVATION_ROWS_BELOW_PAGE_SIZE'):contract().observe(old,outer(),LIMITS,observed_at=T1)
    assert OBSERVATION_PAGE_SIZES==frozenset({5,10,20,50,100})


def mutated(**changes):
    audit=json.loads(json.dumps(single_page_audit()))
    for k,v in changes.items():audit[k]=v
    return audit


@pytest.mark.parametrize('label,audit,reason',[
    ('complete window','COMPLETE','IDOX_OBSERVATION_REQUIRES_UNKNOWN_TOTAL'),
    ('page cap',mutated(enumeration_evidence='PAGE_CAP',capped=True),'IDOX_WINDOW_BINDING_OR_COMPLETENESS'),
    ('failure recorded',mutated(failure='ListingError:SOURCE_CONTRACT_REJECTED'),'IDOX_WINDOW_BINDING_OR_COMPLETENESS'),
    ('echo interval differs',mutated(applied_interval=['2026-09-28','2026-10-05']),'IDOX_WINDOW_BINDING_OR_COMPLETENESS'),
    ('requested interval differs',mutated(requested_interval=['2026-09-28','2026-10-05']),'IDOX_WINDOW_BINDING_OR_COMPLETENESS'),
    ('wrong semantics',mutated(date_semantics='VALIDATED'),'IDOX_WINDOW_BINDING_OR_COMPLETENESS'),
    ('wrong evidence kind',mutated(applied_evidence='STRICT_ZERO_RESULT_FORM_ECHO'),'IDOX_OBSERVATION_REQUIRES_UNKNOWN_TOTAL'),
    ('explicit zero evidence',mutated(explicit_zero_evidence='NO_RESULTS_FOUND_AND_RETAINED_DATE_CRITERIA'),'IDOX_OBSERVATION_REQUIRES_UNKNOWN_TOTAL'),
    ('criteria hash broken',mutated(applied_evidence_sha256='x'),'IDOX_CRITERIA_HASH'),
    ('binding method altered',mutated(criteria_result_binding=dict(single_page_audit()['criteria_result_binding'],method='OTHER')),'IDOX_CRITERIA_BINDING'),
    ('response provenance altered',mutated(response_provenance=single_page_audit()['response_provenance'][:-1]),'IDOX_RESPONSE_ACCOUNTING'),
    ('cleanup not closed',mutated(cleanup='UNKNOWN'),'IDOX_WINDOW_BINDING_OR_COMPLETENESS')])
def test_every_anomaly_still_stops_exactly_as_the_complete_path_does(label,audit,reason):
    if audit=='COMPLETE':audit=multi_page_audit()
    with pytest.raises(Denied,match=reason):contract().observe(audit,outer(),LIMITS,observed_at=T1)


def test_pager_total_next_link_pages_redirects_retries_and_duplicate_rows_stop():
    base=single_page_audit()
    def with_page(**kw):
        a=json.loads(json.dumps(base));a['pages']=[dict(a['pages'][0],**kw)];return a
    for kw in (dict(total=4),dict(first=1,last=4),dict(terminal='EXPLICIT_LAST_EQUALS_TOTAL'),dict(ordinal=2)):
        with pytest.raises(Denied,match='IDOX_OBSERVATION_PAGE_SHAPE'):contract().observe(with_page(**kw),outer(),LIMITS,observed_at=T1)
    two=json.loads(json.dumps(base));two['pages']=two['pages']*2
    with pytest.raises(Denied,match='IDOX_OBSERVATION_SINGLE_PAGE_ONLY'):contract().observe(two,outer(),LIMITS,observed_at=T1)
    for resource in (dict(redirects=1),dict(retries=1)):
        a=json.loads(json.dumps(base));a['resource'].update(resource)
        with pytest.raises(Denied):contract().observe(a,outer(),LIMITS,observed_at=T1)
    dup=json.loads(json.dumps(base));dup['records'][1]=dict(dup['records'][1],reference=dup['records'][0]['reference'])
    with pytest.raises(Denied,match='IDOX_ROW_IDENTITY'):contract().observe(dup,outer(),LIMITS,observed_at=T1)
    outside=json.loads(json.dumps(base));outside['records'][0]['fields']['received_date']['value']='Fri 02 Oct 2026'
    assert contract().observe(outside,outer(),LIMITS,observed_at=T1)      # inside the window is fine...
    outside['records'][0]['fields']['received_date']['value']='Mon 05 Oct 2026'
    with pytest.raises(Denied,match='IDOX_ROW_DATE'):contract().observe(outside,outer(),LIMITS,observed_at=T1)
    for stamp in ('2026-10-20T21:49:30','2026-10-20T22:49:30+01:00','not a time',None):
        with pytest.raises(Denied,match='OBSERVATION_TIMESTAMP_UTC_REQUIRED'):contract().observe(base,outer(),LIMITS,observed_at=stamp)


def test_the_extracted_row_validation_gives_the_complete_projection_exactly_what_it_gave_before():
    audit=multi_page_audit();receipt=contract(False).project(audit,outer(),LIMITS)
    obs=observe(single_page_audit(4))
    assert digest(stored(receipt)['records'])=='17552ee4dc64b29daa3c5f06558862dda7002bcbf4ffcb32c64c13acc432d590'      # GOLDEN: the records the ORIGINAL (pre-extraction) adapter produced for this fixture, byte for byte
    assert [r['fields'] for r in receipt['records'][:4]]==[r['fields'] for r in obs['records']] and [r['reference'] for r in receipt['records'][:4]]==[r['reference'] for r in obs['records']]      # same validation, same projection
    assert receipt['segments'][0]['page_size']==10      # the complete receipt also carries the page size now


# ---------------------------------------------------------------- the schema has no completeness vocabulary
FORBIDDEN={'completeness','enumeration_evidence','terminal','total','first','last','window','explicit_zero','capped','segments','interval','applied_interval','coverage','watermark','unique_references'}


def keys_of(x):
    if isinstance(x,dict):
        for k,v in x.items():
            yield k;yield from keys_of(v)
    elif isinstance(x,list):
        for v in x:yield from keys_of(v)


def test_the_observation_schema_has_no_completeness_field_and_one_constant_window_statement():
    obs=observe()
    assert not (FORBIDDEN & set(keys_of(obs))),FORBIDDEN & set(keys_of(obs))
    assert set(obs)=={'kind','contract','council','requested_interval','applied_interval_evidence','records','page','observed_at','window_claim','display_label','source_sha256','qualification_sha256','cleanup','accounting_complete','outer_supervisor','resources'}
    assert obs['window_claim']=='NONE' and [v for k,v in obs.items() if k=='window_claim']==['NONE']
    assert not any(isinstance(v,str) and v in ('COMPLETE','COUNT_RECONCILED') for v in obs.values()) and 'COMPLETE' not in json.dumps(obs)


def test_every_window_consumer_rejects_the_kind_by_type():
    obs=observe();obs['durable_archive']={'sha256':'b'*64}
    with pytest.raises(Denied,match='ARCHIVED_CAPTURE_REQUIRED'):batch_plans('c'*64,obs)      # no batches, no screening queue
    class Ledger:
        def get(self,key):return dict(checkpoint=obs,state='CHECKPOINTED')
    class Coordinator:ledger=Ledger()
    with pytest.raises(Denied,match='OBSERVATION_IS_NOT_A_CAPTURE'):capture_once(Coordinator(),'d'*64,lambda row:None,lambda raw:None)      # nothing re-reads it as a capture
    class Claim:key='d'*64
    from app.ingestion.coordinator import Coordinator as RealCoordinator
    class Resume(RealCoordinator):
        def __init__(self):self.ledger=Ledger()
    with pytest.raises(Denied,match='NO_DURABLE_CHECKPOINT'):Resume().resume_listing(Claim())      # the coordinator's resume path requires the complete receipt kind (behavioural, not a text search)
    class Done:
        def get(self,key):return dict(checkpoint=obs,state='COMPLETE')
    class CompleteCoordinator:ledger=Done()
    with pytest.raises(Denied,match='OBSERVATION_IS_NOT_A_CAPTURE'):capture_once(CompleteCoordinator(),'d'*64,lambda row:None,lambda raw:None)      # even a COMPLETE state does not make it a capture
    assert OBSERVATION_KIND=='LISTING_OBSERVATION_V1'      # the literal used by batching.capture_once


# ---------------------------------------------------------------- screening parity and provenance
def test_record_screening_is_identical_for_an_observed_record_and_the_same_record_in_a_complete_receipt():
    obs=observe(single_page_audit(4));receipt=stored(contract(False).project(multi_page_audit(),outer(),LIMITS))
    screened=screen_observation(obs)
    assert [s['screen'] for s in screened]==[screen_row(r) for r in receipt['records'][:4]]      # golden: window-independent
    for s in screened:
        assert s['provenance']['source_kind']=='LISTING_OBSERVATION_V1' and s['provenance']['window_claim']=='NONE' and s['provenance']['observed_at']==T1 and s['provenance']['observation_digest']==digest(obs)
    with pytest.raises(Denied,match='OBSERVATION_REQUIRED'):screen_observation(receipt)
    assert oh.display_label(obs)==OBSERVATION_DISPLAY_LABEL and oh.display_label(receipt) is None


# ---------------------------------------------------------------- history: preserved, timestamped, identity-deduplicated
def test_history_keeps_every_observation_with_its_timestamp_and_classifies_each_change():
    base=observe(single_page_audit(4),observed_at=T1)
    h=oh.append(oh.empty_history(),base)
    ident=digest(dict(council='bolton',reference=REFS[0]))
    assert len(h['applications'])==4 and h['applications'][ident]['observations'][0]['change']=='FIRST_OBSERVATION' and h['applications'][ident]['first_observed_at']==T1
    again=observe(single_page_audit(4),observed_at=T2)      # same records observed an hour later
    h2=oh.append(h,again);obs_list=h2['applications'][ident]['observations']
    assert [o['observed_at'] for o in obs_list]==[T1,T2] and [o['change'] for o in obs_list]==['FIRST_OBSERVATION','UNCHANGED'] and len(h2['applications'])==4      # deduplicated identity, both observations kept
    assert h2['applications'][ident]['observations'][0]==h['applications'][ident]['observations'][0] and h['applications'][ident]['observations']==obs_list[:1]      # the input history was not mutated
    amended=json.loads(json.dumps(single_page_audit(4)))
    amended['records'][0]['fields']['proposal']['value']=amended['records'][0]['fields']['proposal']['value']+' (AMENDED DESCRIPTION)'
    h3=oh.append(h2,observe(amended,observed_at=T3));last=h3['applications'][ident]['observations'][-1]
    assert last['change']=='NORMAL_UPDATE' and last['change_detail']['changed']==['proposal'] and h3['conflicts']==[]      # an amended description is a normal update
    assert len(h3['applications'][ident]['observations'])==3      # and all three versions remain


def test_a_validated_date_published_for_the_first_time_is_a_normal_update_not_a_conflict():
    first=json.loads(json.dumps(single_page_audit(4)));first['records'][0]['fields']['validated_date']=dict(state='UNKNOWN',value=None,locator='x')
    h=oh.append(oh.empty_history(),observe(first,observed_at=T1))
    later=json.loads(json.dumps(first));later['records'][0]['fields']['validated_date']=dict(state='PRESENT_VALUE',value='Wed 30 Sep 2026',locator='x')
    h2=oh.append(h,observe(later,observed_at=T2));last=h2['applications'][digest(dict(council='bolton',reference=REFS[0]))]['observations'][-1]
    assert last['change']=='NORMAL_UPDATE' and last['change_detail']['changed']==['validated_date'] and h2['conflicts']==[]


@pytest.mark.parametrize('mutation,reason',[
    (lambda r:r['fields']['received_date'].update(value='Tue 29 Sep 2026'),'IDENTITY_FIELD_CHANGED'),
    (lambda r:r.update(source_key='ZZZ',source_url=r['source_url'].replace(r['source_key'],'ZZZ')),'SOURCE_KEY_CHANGED')])
def test_changes_to_identity_defining_evidence_are_conflicts_that_keep_both_sides(mutation,reason):
    h=oh.append(oh.empty_history(),observe(single_page_audit(4),observed_at=T1))
    changed=json.loads(json.dumps(single_page_audit(4)));mutation(changed['records'][0])
    h2=oh.append(h,observe(changed,observed_at=T2)) if reason!='SOURCE_KEY_CHANGED' else oh.append(h,contract().observe(changed,outer(),LIMITS,observed_at=T2))
    ident=digest(dict(council='bolton',reference=REFS[0]));observations=h2['applications'][ident]['observations']
    assert observations[-1]['change']=='CONFLICT' and observations[-1]['change_detail']['reason']==reason and len(observations)==2 and h2['conflicts'] and observations[0]['record_digest']!=observations[1]['record_digest']


def test_a_published_validated_date_that_changes_or_disappears_is_a_conflict():
    first=json.loads(json.dumps(single_page_audit(4)));first['records'][0]['fields']['validated_date']=dict(state='PRESENT_VALUE',value='Wed 30 Sep 2026',locator='x')
    h=oh.append(oh.empty_history(),observe(first,observed_at=T1))
    second=json.loads(json.dumps(first));second['records'][0]['fields']['validated_date']=dict(state='PRESENT_VALUE',value='Thu 01 Oct 2026',locator='x')
    h2=oh.append(h,observe(second,observed_at=T2));assert h2['conflicts'][-1]['reason']=='PUBLISHED_FIELD_CHANGED_OR_WITHDRAWN'
    third=json.loads(json.dumps(first));third['records'][0]['fields']['validated_date']=dict(state='UNKNOWN',value=None,locator='x')
    h3=oh.append(h,observe(third,observed_at=T2));assert h3['conflicts'][-1]['reason']=='PUBLISHED_FIELD_CHANGED_OR_WITHDRAWN'


def test_one_source_key_claimed_by_two_references_is_flagged():
    h=oh.append(oh.empty_history(),observe(single_page_audit(4),observed_at=T1))
    other=json.loads(json.dumps(single_page_audit(4)));other['records'][1]['reference']='9999/26'
    h2=oh.append(h,observe(other,observed_at=T2))
    assert any(c['reason']=='SOURCE_KEY_USED_BY_ANOTHER_REFERENCE' for c in h2['conflicts'])


def test_first_observed_is_this_platforms_first_sighting_not_a_submission_claim():
    h=oh.append(oh.empty_history(),observe(single_page_audit(4),observed_at=T2))
    h=oh.append(h,observe(single_page_audit(4),observed_at=T1))      # an EARLIER sighting appended later (out-of-order delivery)
    info=oh.first_observed(h,'bolton',REFS[0])
    assert set(info)=={'first_observed_at','first_observed_in','council_received_date'} and info['first_observed_at']==T1 and info['council_received_date']=='Mon 28 Sep 2026'
    assert oh.first_observed(h,'bolton','0000/00') is None
    assert not any('newly' in n.lower() or 'new_application' in n.lower() or 'submitted' in n.lower() for n in dir(oh))      # no API can say "newly submitted"
    with pytest.raises(Denied,match='OBSERVATION_TIMESTAMP_UTC_REQUIRED'):oh.append(h,dict(observe(single_page_audit(4)),observed_at='2026-10-20T10:00:00'))      # naive timestamps are refused


def test_a_later_complete_capture_is_linked_to_earlier_observations_without_replacing_either():
    obs_page=json.loads(json.dumps(single_page_audit(4)))
    obs_page['records'][3]=dict(obs_page['records'][3],reference='5999/26')      # one observed application the complete capture will NOT contain
    obs=observe(obs_page,observed_at=T1);receipt=stored(contract(False).project(multi_page_audit(),outer(),LIMITS))
    h=oh.append(oh.empty_history(),obs);h=oh.append(h,receipt,observed_at=T2)
    before=json.loads(json.dumps(h))
    linked=oh.link_complete_capture(h,receipt,observed_at=T3)
    assert linked['applications']==before['applications']      # no observation or version was replaced or removed
    relations={(l['identity']['reference'],l['relation']) for l in linked['links']}
    assert {(REFS[0],'PRESENT_IN_COMPLETE_CAPTURE'),(REFS[1],'PRESENT_IN_COMPLETE_CAPTURE'),(REFS[2],'PRESENT_IN_COMPLETE_CAPTURE'),('5999/26','OBSERVED_BUT_ABSENT_FROM_COMPLETE_CAPTURE')}==relations
    assert any(c['reason']=='OBSERVED_BUT_ABSENT_FROM_COMPLETE_CAPTURE' for c in linked['conflicts']) and all(l['complete_receipt_digest']==digest(receipt) and l['observation_evidence_digest']==digest(obs) for l in linked['links'])
    ident=digest(dict(council='bolton',reference=REFS[0]))
    assert [o['evidence_kind'] for o in linked['applications'][ident]['observations']]==['LISTING_OBSERVATION_V1','LISTING_RECEIPT_V1'] and linked['applications'][ident]['observations'][1]['change']=='UNCHANGED'
    with pytest.raises(Denied,match='COMPLETE_RECEIPT_REQUIRED'):oh.link_complete_capture(h,obs,observed_at=T3)


def test_the_history_module_offers_no_way_to_delete_or_to_advance_a_watermark():
    names=[n for n in dir(oh) if not n.startswith('_')]
    assert not any(w in n.lower() for n in names for w in ('delete','remove','purge','expire','prune','watermark','coverage','absen'))


# ---------------------------------------------------------------- review additions: more refusals, raw receipts, idempotent linking, chronology
def test_remaining_admission_conditions_each_stop():
    base=single_page_audit()
    def copy():return json.loads(json.dumps(base))
    wrong_rows=copy();wrong_rows['pages'][0]['rows']=3
    with pytest.raises(Denied,match='IDOX_OBSERVATION_ROWS_BELOW_PAGE_SIZE'):contract().observe(wrong_rows,outer(),LIMITS,observed_at=T1)
    wrong_unique=copy();wrong_unique['unique_references']=3
    with pytest.raises(Denied,match='IDOX_OBSERVATION_ROWS_BELOW_PAGE_SIZE'):contract().observe(wrong_unique,outer(),LIMITS,observed_at=T1)
    bad_provenance=copy();bad_provenance['response_provenance'][-1]['parser_body_sha256']='0'*64
    with pytest.raises(Denied,match='IDOX_RESPONSE_PROVENANCE'):contract().observe(bad_provenance,outer(),LIMITS,observed_at=T1)
    bad_segment=copy();bad_segment['criteria_result_binding']['segment_sha256']=['0'*64]
    with pytest.raises(Denied,match='IDOX_CRITERIA_BINDING'):contract().observe(bad_segment,outer(),LIMITS,observed_at=T1)
    exhausted=copy();exhausted['resource']['budget_exhaustion']=True
    with pytest.raises(Denied,match='IDOX_OBSERVATION_SINGLE_PAGE_ONLY'):contract().observe(exhausted,outer(),LIMITS,observed_at=T1)
    over=copy();over['resource']['requests_attempted']=11
    with pytest.raises(Denied):contract().observe(over,outer(),LIMITS,observed_at=T1)


def test_history_accepts_the_in_memory_complete_receipt_and_its_stored_form_identically():
    raw=contract(False).project(multi_page_audit(),outer(),LIMITS)      # holds date objects in its window evidence, exactly as project() returns it
    h_raw=oh.append(oh.empty_history(),raw,observed_at=T2);h_stored=oh.append(oh.empty_history(),stored(raw),observed_at=T2)
    assert h_raw==h_stored
    obs=observe(single_page_audit(4),observed_at=T1);h=oh.append(oh.empty_history(),obs)
    assert oh.link_complete_capture(h,raw,observed_at=T3)['links']==oh.link_complete_capture(h,stored(raw),observed_at=T3)['links']


def test_linking_is_idempotent_and_requires_received_semantics_and_an_observation_keeps_its_own_timestamp():
    receipt=stored(contract(False).project(multi_page_audit(),outer(),LIMITS));obs=observe(single_page_audit(4),observed_at=T1)
    h=oh.append(oh.empty_history(),obs)
    once=oh.link_complete_capture(h,receipt,observed_at=T3);twice=oh.link_complete_capture(once,receipt,observed_at=T3)
    assert once['links']==twice['links'] and once['conflicts']==twice['conflicts']
    validated=json.loads(json.dumps(receipt));validated['window']['date_semantics']='VALIDATED'
    with pytest.raises(Denied,match='RECEIVED_SEMANTICS_REQUIRED'):oh.link_complete_capture(h,validated,observed_at=T3)
    with pytest.raises(Denied,match='OBSERVATION_TIMESTAMP_IS_THE_EVIDENCES_OWN'):oh.append(oh.empty_history(),obs,observed_at=T2)
    assert oh.append(oh.empty_history(),obs,observed_at=T1)      # an identical stamp is accepted


def test_the_invariants_are_explicit_checks_not_asserts():
    text=open('app/ingestion/observation_history.py').read()
    assert 'assert ' not in text.replace('# ','')      # `python -O` would remove an assert


def test_first_observed_takes_the_received_date_from_the_earliest_observation_by_time():
    later=json.loads(json.dumps(single_page_audit(4)));later['records'][0]['fields']['proposal']['value']+=' (LATER)'
    h=oh.append(oh.empty_history(),observe(later,observed_at=T2))
    h=oh.append(h,observe(single_page_audit(4),observed_at=T1))
    assert oh.first_observed(h,'bolton',REFS[0])['first_observed_at']==T1
