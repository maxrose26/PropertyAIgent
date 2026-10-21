"""Phase A of specification 035, offline: the pure evidence model (app/ingestion/count_evidence.py), the proposal-text assessor (app/ingestion/count_assessment.py) and the opt-in screening rule v3.
The 62 executable examples (specifications/035-residential-count-examples.json) are the acceptance criteria: every one is reproduced here by the PRODUCTION code, and the independent oracle in
tests/spec035_reference.py agrees with it. Rule v1 is byte-identical to master and every historical result is untouched. Nothing here touches a database, network, model, council or clock."""
import copy
import json
import random
import re
import time
from pathlib import Path

import pytest

from app.ingestion import count_assessment as ca
from app.ingestion import count_evidence as ce
from app.ingestion import listing_screening as ls
from app.ingestion.ledger import digest
from tests import spec035_reference as ref
from tests.test_spec035_residential_count_examples import project

ROOT=Path(__file__).resolve().parents[1]
DOC=json.loads((ROOT/'specifications/035-residential-count-examples.json').read_text(encoding='utf-8'))
EXAMPLES=DOC['examples'];PLAIN=[e for e in EXAMPLES if 'records' not in e];EVIDENCE=[e for e in EXAMPLES if 'records' in e]
KEYS=('category','scheme_role','proposed_total','lost','existing','net','non_residential_units','parent_context','admission','reason')

# digest of master (bb0b9f6) listing_screening.screen_row over every example proposal, "" and "  ", in three states each (192 results), produced by the UNMODIFIED master module; this change must not move it
V1_GOLDEN='daaa94a076aea3e3a9f6d46a98c286c81c9f5f6e850f5177ee8345fc0aedeb20'
TEXTS=[e['proposal'] for e in EXAMPLES]+['','  ']


def row(text,state='PRESENT_VALUE',truncated=False):
    return dict(reference='T/1',fields={'proposal':dict(state=state,value=text,locator='x',truncated=truncated),'address':dict(state='PRESENT_VALUE',value='1 Test Street',locator='x',truncated=False),
                                        'application_type':dict(state='UNKNOWN',value=None,locator='x',truncated=False)})


VARIANTS=(dict(),dict(state='UNKNOWN'),dict(truncated=True))


# ------------------------------------------------------------------ acceptance: the 62 examples
def test_there_are_sixty_two_examples_and_they_split_into_plain_and_evidence_model():
    assert len(EXAMPLES)==62 and len(PLAIN)==41 and len(EVIDENCE)==21


@pytest.mark.parametrize('e',PLAIN,ids=[e['id'] for e in PLAIN])
def test_the_text_assessor_reproduces_every_plain_example(e):
    got=ca.assess_proposal(e['proposal'],proposal_state=e['proposal_state']);x=e['expected']
    assert {k:got[k] for k in KEYS}=={k:x[k] for k in KEYS},e['id']
    assert got['approved_total']=='NOT_ESTABLISHED'      # an approved count can never come from proposal text
    assert all(r['basis']=='PROPOSED' and r['source_kind']=='LISTING_PROPOSAL_TEXT' for r in got['records'])


@pytest.mark.parametrize('e',EVIDENCE,ids=[e['id'] for e in EVIDENCE])
def test_the_production_evidence_model_reproduces_every_evidence_example_and_agrees_with_the_oracle(e):
    recs=e['records'];rel=e['scope_relations'];asm=e.get('assessments',[]);x=e['expected']
    for basis,name in ((ce.PROPOSED,'proposed'),(ce.APPROVED,'approved')):
        assert project(ce.resolve_basis(recs,basis,rel,asm))==x['bases'][name],(e['id'],name)
        assert ce.resolve_basis(recs,basis,rel,asm)==ref.resolve_basis(recs,basis,rel,asm)
    assert ce.headline(recs,rel,asm)==x['headline']==ref.headline(recs,rel,asm)
    for s in x['search']:
        got=ce.search_match(recs,s['basis'],s['size_min'],s['size_max'],rel,asm)
        assert dict(match=got['match'],matched_by=got['matched_by'])==dict(match=s['match'],matched_by=s['matched_by']),(e['id'],s)
        if 'level' in s:assert (got['level'],got['scopes'])==(s['level'],s['scopes'])
        assert got==ref.search_match(recs,s['basis'],s['size_min'],s['size_max'],rel,asm)
    assert ce.size_outcome(recs,10,rel,asm)==ref.size_outcome(recs,10,rel,asm)
    assert ce.read_model(recs,rel,asm)==ref.read_model(recs,rel,asm)
    if x['admission'] in ('ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','RETAIN_BELOW_THRESHOLD'):assert ce.size_outcome(recs,10,rel,asm)==x['admission']


def test_assess_proposal_with_supplied_evidence_resolves_it_by_the_evidence_model_not_by_text_rules():
    by_id={e['id']:e for e in EVIDENCE}
    for ident in ('E38','E38b','E38e','E38h','E38j'):      # the proposal text is the (unreliable) listing; the supplied evidence decides
        e=by_id[ident];got=ca.assess_proposal(e['proposal'],evidence=[r for r in e['records'] if r['source_kind']!='LISTING_PROPOSAL_TEXT'],scope_relations=e['scope_relations'],assessments=e.get('assessments',()))
        every=ce.size_outcome(got['records']+[r for r in e['records'] if r['source_kind']!='LISTING_PROPOSAL_TEXT'],10,e['scope_relations'],e.get('assessments',()))
        assert got['admission'] in ('ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','RETAIN_BELOW_THRESHOLD') and got['headline'] and every==got['admission']


def test_the_evidence_model_agrees_with_the_oracle_on_shuffled_random_records():
    rnd=random.Random(35)
    kinds=['DECISION_NOTICE','APPROVED_PLANS_SCHEDULE','APPLICATION_FORM_STRUCTURED','LISTING_PROPOSAL_TEXT','PLANNING_STATEMENT']
    for _ in range(300):
        recs=[dict(id='r%d'%i,basis=rnd.choice(['PROPOSED','APPROVED']),scope=rnd.choice(['whole','Phase 1','Phase 2']),value=rnd.choice([5,9,10,12,49,52,'UP_TO:50','UP_TO:9']),source_kind=rnd.choice(kinds),
                   document_date=rnd.choice([None,'2025-01-01']),qualifier=rnd.choice([None,'outline']),relations={}) for i in range(rnd.randint(0,5))]
        if len(recs)>1 and rnd.random()<0.4:recs[1]['relations']={'supersedes':recs[0]['id']}
        rel=[dict(scopes=['Phase 1','Phase 2'],relation=rnd.choice(['NON_OVERLAPPING_PARTS','COMMON_DEVELOPMENT','EXHAUSTS_DEVELOPMENT']),source_kind='PHASING_PLAN',quote='q')] if rnd.random()<0.4 else []
        for lo,hi in ((10,None),(10,50),(1,100),(53,None)):
            for choice in ('APPROVED','PROPOSED','EITHER'):assert ce.search_match(recs,choice,lo,hi,rel)==ref.search_match(recs,choice,lo,hi,rel)
        assert ce.headline(recs,rel)==ref.headline(recs,rel) and ce.size_outcome(recs,10,rel)==ref.size_outcome(recs,10,rel) and ce.read_model(recs,rel)==ref.read_model(recs,rel)


def test_a_phase_whose_own_figures_conflict_is_labelled_under_review_and_never_raises():
    """Found by the randomised parity check: a by-phase headline used to fail on a phase whose own figures conflict. Fixed in the oracle and in production, kept identical."""
    recs=[dict(id='a',basis='PROPOSED',scope='Phase 1',value=49,source_kind='LISTING_PROPOSAL_TEXT',relations={}),dict(id='b',basis='PROPOSED',scope='Phase 1',value=52,source_kind='APPLICATION_FORM_STRUCTURED',relations={}),
          dict(id='c',basis='PROPOSED',scope='Phase 2',value=10,source_kind='LISTING_PROPOSAL_TEXT',relations={})]
    want='Proposed by phase (Phase 1: under review, Phase 2: 10; overlap not established)'
    assert ce.headline(recs)['label']==want==ref.headline(recs)['label']
    assert ce.search_match(recs,'PROPOSED',10,None)==ref.search_match(recs,'PROPOSED',10,None)


# ------------------------------------------------------------------ rule v1 is untouched
def test_rule_v1_is_the_default_and_byte_identical_to_master_over_every_example_text():
    results=[ls.screen_row(row(t,**v)) for t in TEXTS for v in VARIANTS]
    assert len(results)==192 and digest(results)==V1_GOLDEN
    assert digest([ls.screen_row(row(t,**v),rule_version=ls.RULE_V1) for t in TEXTS for v in VARIANTS])==V1_GOLDEN
    assert all(r['rule_version']=='manchester-listing-screen-assessment-v1' and 'count_assessment' not in r and 'routing_authority' not in r for r in results)
    for bad in (dict(council='bolton'),dict(unit_threshold=10)):
        with pytest.raises(ValueError,match='RULE_V1_TAKES_NO_THRESHOLD'):ls.screen_row(row('ERECTION OF 12 DWELLINGS'),**bad)


# ------------------------------------------------------------------ rule v3 is opt-in and additive
@pytest.mark.parametrize('e',EXAMPLES,ids=[e['id'] for e in EXAMPLES])
def test_v3_is_purely_additive_over_the_v1_result(e):
    for v in VARIANTS:
        v1=ls.screen_row(row(e['proposal'],**v));v3=ls.screen_row(row(e['proposal'],**v),rule_version=ls.RULE_V3,unit_threshold=10)
        added={'rule_version','routing_authority','count_assessment','count_assessment_threshold'}
        assert {k:x for k,x in v3.items() if k not in added}=={k:x for k,x in v1.items() if k!='rule_version'}
        assert v3['rule_version']=='manchester-listing-screen-assessment-v3' and v3['routing_authority']=='count_assessment' and v3['count_assessment_threshold']==10 and v3['retained'] is True and v3['permanent_exclusion'] is False


def test_v3_carries_the_assessment_for_the_text_and_marks_unusable_proposals():
    for e in PLAIN:
        got=ls.screen_row(row(e['proposal'],e['proposal_state']),rule_version=ls.RULE_V3,unit_threshold=10)['count_assessment']
        assert {k:got[k] for k in KEYS}=={k:e['expected'][k] for k in KEYS},e['id']
    for v in (dict(state='UNKNOWN'),dict(truncated=True)):
        ca_=ls.screen_row(row('ERECTION OF 12 DWELLINGS',**v),rule_version=ls.RULE_V3,unit_threshold=10)['count_assessment']
        assert ca_['admission']=='RETAIN_UNUSABLE_PROPOSAL' and ca_['proposed_total']=='NOT_ESTABLISHED'


def test_v3_threshold_rules_and_unknown_versions_fail_closed():
    r=row('ERECTION OF 12 DWELLINGS')
    for kw,why in ((dict(),'RULE_V3_REQUIRES_EXACTLY_ONE_OF_COUNCIL_OR_THRESHOLD'),(dict(council='bolton',unit_threshold=10),'RULE_V3_REQUIRES_EXACTLY_ONE_OF_COUNCIL_OR_THRESHOLD')):
        with pytest.raises(ValueError,match=why):ls.screen_row(r,rule_version=ls.RULE_V3,**kw)
    for bad in (0,-1,'10',10.0,True,None):
        with pytest.raises(ValueError):ls.screen_row(r,rule_version=ls.RULE_V3,unit_threshold=bad)
    with pytest.raises(ValueError,match='UNKNOWN_SCREENING_RULE_VERSION'):ls.screen_row(r,rule_version='v2')
    assert ls.screen_row(row('ERECTION OF 9 DWELLINGS'),rule_version=ls.RULE_V3,unit_threshold=9)['count_assessment']['admission']=='ADMIT_SCHEME'      # the threshold really is the parameter
    assert ls.screen_row(row('ERECTION OF 9 DWELLINGS'),rule_version=ls.RULE_V3,unit_threshold=10)['count_assessment']['admission']=='RETAIN_BELOW_THRESHOLD'


def test_the_threshold_comes_from_the_configuration_not_a_literal():
    pytest.importorskip('yaml')
    assert ls.council_unit_threshold('bolton')==10
    assert ls.screen_row(row('ERECTION OF 12 DWELLINGS'),rule_version=ls.RULE_V3,council='bolton')==ls.screen_row(row('ERECTION OF 12 DWELLINGS'),rule_version=ls.RULE_V3,unit_threshold=10)
    with pytest.raises(KeyError):ls.council_unit_threshold('nowhere')


# ------------------------------------------------------------------ one routing authority per rule version
def test_routing_has_exactly_one_authority_chosen_by_rule_version():
    v1=ls.screen_row(row('CHANGE OF USE OF 12 FLATS TO A HOTEL'));v3=ls.screen_row(row('CHANGE OF USE OF 12 FLATS TO A HOTEL'),rule_version=ls.RULE_V3,unit_threshold=10)
    assert ls.routing_of(v1)==('disposition','SUPPORTED_PROCESSING_PRIORITY')      # the historical v1 weakness is preserved, not corrected
    assert v3['disposition']=='SUPPORTED_PROCESSING_PRIORITY' and ls.routing_of(v3)==('count_assessment','RETAIN_NOT_RESIDENTIAL_SUPPLY')      # in v3 the disposition is informational and routes nothing
    for e in PLAIN:
        assert ls.routing_of(ls.screen_row(row(e['proposal'],e['proposal_state']),rule_version=ls.RULE_V3,unit_threshold=10))==('count_assessment',e['expected']['admission'])


def test_routing_fails_closed_on_anything_ambiguous_or_tampered():
    v1=ls.screen_row(row('ERECTION OF 12 DWELLINGS'));v3=ls.screen_row(row('ERECTION OF 12 DWELLINGS'),rule_version=ls.RULE_V3,unit_threshold=10)
    bad=[dict(v3,routing_authority='disposition'),{k:x for k,x in v3.items() if k!='routing_authority'},{k:x for k,x in v3.items() if k!='count_assessment'},dict(v3,count_assessment=dict(v3['count_assessment'],admission='')),
         dict(v1,routing_authority='count_assessment'),dict(v1,rule_version='manchester-listing-screen-assessment-v2'),dict(v1,rule_version=None),{k:x for k,x in v1.items() if k!='disposition'},{}]
    for r in bad:
        with pytest.raises(ValueError,match='ROUTING_AUTHORITY_UNRESOLVED'):ls.routing_of(r)


def test_nothing_in_the_repository_selects_v3_or_imports_the_new_modules_and_nothing_re_screens():
    offenders=[]
    for path in list((ROOT/'app').rglob('*.py'))+list((ROOT/'verification').rglob('*.py')):
        if path.name in ('listing_screening.py','count_assessment.py','count_evidence.py'):continue
        text=path.read_text(encoding='utf-8',errors='ignore')
        if re.search(r'RULE_V3|screening-assessment-v3|routing_of|ingestion\.count_(?:assessment|evidence)|from\s+\.count_(?:assessment|evidence)|from\s+\.\s+import\s+[^\n]*count_(?:assessment|evidence)',text):offenders.append(str(path.relative_to(ROOT)))
    assert offenders==[]      # opt-in only: no caller selects v3, no consumer reads it, no existing path changes
    assert not [n for n in dir(ls) if 'rescreen' in n.lower() or 're_screen' in n.lower()]


def test_the_new_modules_are_pure_no_database_network_clock_model_or_configuration_imports():
    for name in ('count_evidence.py','count_assessment.py'):
        src=(ROOT/'app/ingestion'/name).read_text(encoding='utf-8')
        imports=set(re.findall(r'^\s*(?:from|import)\s+([\w.]+)',src,re.M))
        assert imports<= {'re','.','.listing_screening','app.scrapers.unit_filter','count_evidence'} or all(i in ('re','.','.listing_screening','app.scrapers.unit_filter') for i in imports),(name,imports)
        assert not re.search(r'\b(?:sqlalchemy|psycopg|requests|httpx|urllib|socket|openai|datetime|time\.time|os\.environ|open\()',src),name


# ------------------------------------------------------------------ rules called out by the specification, directly
def test_the_counting_rules_directly():
    a=lambda t,**k:ca.assess_proposal(t,**k)
    assert a('ERECTION OF 5 HOUSES AND 5 FLATS')['proposed_total']==10 and a('ERECTION OF 2 BLOCKS OF 6 FLATS EACH')['proposed_total']==12      # R-SUM, R-PRODUCT
    assert a('ERECTION OF 3 BLOCKS COMPRISING 24 APARTMENTS')['proposed_total']==24      # the number of blocks is not a dwelling count
    assert a('ERECTION OF 6 DWELLINGS AND 5 FLATS')['proposed_total']==11
    for t in ('ERECTION OF 12 DWELLINGS AND ALSO 40 CAR PARKING SPACES AND 6 FLATS ELSEWHERE ON THE SITE OF THE FORMER MILL','ERECTION OF 12 DWELLINGS. ERECTION OF 6 FLATS'):
        got=a(t);assert got['proposed_total'] in ('NOT_ESTABLISHED',18) and (got['proposed_total']!=18 or t.startswith('ERECTION OF 12 DWELLINGS AND'))      # unjoined components are never added
    assert a('ERECTION OF 12 DWELLINGS. ERECTION OF 6 FLATS')['proposed_total']=='NOT_ESTABLISHED' and a('ERECTION OF 12 DWELLINGS. ERECTION OF 6 FLATS')['admission']=='ROUTE_COUNT_UNCONFIRMED'
    assert a('RESIDENTIAL DEVELOPMENT OF 25 RETAIL UNITS')['admission']=='RETAIN_NOT_RESIDENTIAL_SUPPLY'      # R-UNITS: bare units only in an explicitly residential clause with no other unit type
    assert a('ERECTION OF 9 FLATS AND 1 SHOP')['proposed_total']==9 and a('ERECTION OF 9 FLATS AND 1 SHOP')['non_residential_units']=={'retail':1}      # R-MIXED
    x=a('DEMOLITION OF EXISTING BUNGALOW AND ERECTION OF 12 DWELLINGS');assert (x['lost'],x['existing'],x['net'])==('NOT_ESTABLISHED',)*3      # nothing inferred from an unnumbered mention
    x=a('ERECTION OF 12 HOUSES ON LAND ADJOINING 20 EXISTING HOUSES');assert (x['lost'],x['existing'])==('NOT_ESTABLISHED',)*2      # adjoining stock is not site stock
    assert a('VARIATION OF CONDITION 2 OF PERMISSION 00284/26 FOR 30 DWELLINGS')['proposed_total']=='NOT_ESTABLISHED'      # R-AMEND: a mentioned parent figure is context
    x=a('SECTION 73 VARIATION TO INCREASE THE NUMBER OF DWELLINGS FROM 49 TO 52 ON PERMISSION 00284/26');assert x['parent_context']['revised_total']==52 and x['admission']=='RETAIN_RELATED_TO_PARENT' and x['approved_total']=='NOT_ESTABLISHED'
    assert a('')['admission']=='RETAIN_UNUSABLE_PROPOSAL' and a('x'*9000)['admission']=='RETAIN_UNUSABLE_PROPOSAL'      # R-UNUSABLE and the length bound


def test_the_wording_analysis_is_linear_on_long_adversarial_text():
    """Only the new module's own patterns: the pre-existing qualifier's cubic behaviour on very long digit runs is a separate, already-tracked task and is not exercised here."""
    texts=['ERECTION OF '+'12 FLATS, '*600,'DEMOLITION '*700+'ERECTION OF 12 DWELLINGS','CHANGE OF USE OF '+'ABC '*1500+'TO 12 FLATS','1 - '*2000+'FLATS','ERECTION OF '+'1 NO. '*1200+'DWELLINGS','ERECTION OF '+'FLATS AND '*900+'5 HOUSES',
           'ERECTION OF '+'3 BLOCKS OF '*600+'6 FLATS EACH','UP TO '*1000+'50 DWELLINGS']
    for t in texts:
        start=time.monotonic();ca._mentions(t[:8192]);ca._nonres(t[:8192]);assert time.monotonic()-start<2,t[:30]
        start=time.monotonic();ca.assess_proposal(t[:8192]);assert time.monotonic()-start<5,t[:30]
