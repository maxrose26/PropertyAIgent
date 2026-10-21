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
        assert {k:v for k,v in ce.resolve_basis(recs,basis,rel,asm).items() if k!='rejected_records'}==ref.resolve_basis(recs,basis,rel,asm)      # production adds only the list of rejected malformed records
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
        with pytest.raises(ValueError,match='ROUTING_(?:AUTHORITY_UNRESOLVED|OUTCOME_NOT_IN_VOCABULARY)'):ls.routing_of(r)


def test_only_the_slice_one_files_select_or_read_v3_and_nothing_re_screens():
    """Phase A: nothing selected v3. Slice 1 (PR #171) adds exactly one explicit consumer set; this test pins it, and the held production paths are pinned in tests/test_ingestion_screening_v3_slice1.py."""
    allowed={'app/ingestion/coordinator.py','app/ingestion/screening_projection.py'}
    offenders=set()
    for path in list((ROOT/'app').rglob('*.py'))+list((ROOT/'verification').rglob('*.py')):
        if path.name in ('listing_screening.py','count_assessment.py','count_evidence.py'):continue
        text=path.read_text(encoding='utf-8',errors='ignore')
        if re.search(r'RULE_V3|screening-assessment-v3|routing_of|ingestion\.count_(?:assessment|evidence)|from\s+\.count_(?:assessment|evidence)|from\s+\.\s+import\s+[^\n]*count_(?:assessment|evidence)',text):offenders.add(path.relative_to(ROOT).as_posix())
    assert offenders<=allowed,offenders      # explicit opt-in only: the disposable coordinator and the read-only projections; no production path
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
    got=a('RESIDENTIAL DEVELOPMENT OF 25 RETAIL UNITS');assert got['proposed_total']=='NOT_ESTABLISHED' and got['admission']=='ROUTE_COUNT_UNCONFIRMED'      # R-UNITS: bare units never count where another unit type is named; the contradictory wording is routed
    assert a('ERECTION OF 9 FLATS AND 1 SHOP')['proposed_total']==9 and a('ERECTION OF 9 FLATS AND 1 SHOP')['non_residential_units']=={'retail':1}      # R-MIXED
    x=a('DEMOLITION OF EXISTING BUNGALOW AND ERECTION OF 12 DWELLINGS');assert (x['lost'],x['existing'],x['net'])==('NOT_ESTABLISHED',)*3      # nothing inferred from an unnumbered mention
    x=a('ERECTION OF 12 HOUSES ON LAND ADJOINING 20 EXISTING HOUSES');assert (x['lost'],x['existing'])==('NOT_ESTABLISHED',)*2      # adjoining stock is not site stock
    assert a('VARIATION OF CONDITION 2 OF PERMISSION 00284/26 FOR 30 DWELLINGS')['proposed_total']=='NOT_ESTABLISHED'      # R-AMEND: a mentioned parent figure is context
    x=a('SECTION 73 VARIATION TO INCREASE THE NUMBER OF DWELLINGS FROM 49 TO 52 ON PERMISSION 00284/26');assert x['parent_context']['revised_total']==52 and x['admission']=='RETAIN_RELATED_TO_PARENT' and x['approved_total']=='NOT_ESTABLISHED'
    assert a('')['admission']=='RETAIN_UNUSABLE_PROPOSAL' and a('x'*9000)['admission']=='RETAIN_UNUSABLE_PROPOSAL'      # R-UNUSABLE and the length bound


def test_the_wording_analysis_completes_quickly_on_long_adversarial_text():
    """Only the new module's own patterns: the pre-existing qualifier's cubic behaviour on very long digit runs is a separate, already-tracked task and is not exercised here."""
    texts=['ERECTION OF '+'12 FLATS, '*600,'DEMOLITION '*700+'ERECTION OF 12 DWELLINGS','CHANGE OF USE OF '+'ABC '*1500+'TO 12 FLATS','1 - '*2000+'FLATS','ERECTION OF '+'1 NO. '*1200+'DWELLINGS','ERECTION OF '+'FLATS AND '*900+'5 HOUSES',
           'ERECTION OF '+'3 BLOCKS OF '*600+'6 FLATS EACH','UP TO '*1000+'50 DWELLINGS']
    for t in texts:
        start=time.monotonic();ca._mentions(t[:8192]);ca._nonres(t[:8192]);assert time.monotonic()-start<2,t[:30]
        start=time.monotonic();ca.assess_proposal(t[:8192]);assert time.monotonic()-start<5,t[:30]


# ------------------------------------------------------------------ review round: the assessor is conservative on wordings beyond the 41 examples
def _a(text):return ca.assess_proposal(text)


@pytest.mark.parametrize('text',['Amendment to planning permission 21/00012/FUL for erection of 50 dwellings','Removal of condition 5 of 21/00012/FUL (erection of 30 dwellings)',
    'Substitution of house types on plots 1-30 of 30 dwellings approved under 21/00012/FUL','Application to vary approved plans for 21/00012/FUL (erection of 50 dwellings)',
    'Amendment to 20 dwellings approved under 21/00012/FUL to 24 dwellings','Amendments to approved scheme for 40 dwellings (ref 20/0001/FUL) to include 4 additional dwellings'])
def test_an_amendment_of_a_named_permission_never_gets_a_scheme_total_of_its_own(text):
    got=_a(text)
    assert got['scheme_role']=='AMENDMENT_OF_PARENT' and got['admission']=='RETAIN_RELATED_TO_PARENT' and got['proposed_total']=='NOT_ESTABLISHED'
    assert got['parent_context']['reference'] in ('21/00012/FUL','20/0001/FUL') and got['approved_total']=='NOT_ESTABLISHED'


def test_a_stated_resulting_total_without_the_words_the_number_of_is_still_a_revised_total():
    got=_a('Amendment to 21/00012/FUL to increase number of dwellings from 50 to 54')
    assert got['admission']=='RETAIN_RELATED_TO_PARENT' and got['parent_context']['context_count']==50 and got['parent_context']['revised_total']==54


@pytest.mark.parametrize('text,total,admission',[('Erection of 3 terraces of 4 houses each',12,'ADMIT_SCHEME'),('Erection of 3 buildings comprising 4 flats each',12,'ADMIT_SCHEME'),('Erection of 6 dwellings in each of 2 blocks',12,'ADMIT_SCHEME'),
    ('Erection of 2 blocks of 6 flats','NOT_ESTABLISHED','ROUTE_COUNT_UNCONFIRMED'),('ERECTION OF 3 BLOCKS COMPRISING 24 APARTMENTS',24,'ADMIT_SCHEME')])
def test_per_group_counts_are_multiplied_only_when_each_is_explicit_and_never_guessed(text,total,admission):
    got=_a(text);assert (got['proposed_total'],got['admission'])==(total,admission)


@pytest.mark.parametrize('text,total',[('Erection of twenty-four dwellings',24),('Erection of twenty four dwellings',24),('Erection of thirty-one dwellings',31),('Erection of nineteen dwellings',19),('Erection of twenty dwellings',20)])
def test_compound_number_words_are_one_number(text,total):
    assert _a(text)['proposed_total']==total


def test_wording_the_assessor_cannot_parse_is_routed_not_guessed():
    for t in ('Erection of one hundred and twenty dwellings','Erection of two thousand dwellings'):
        got=_a(t);assert (got['proposed_total'],got['admission'],got['reason'])==('NOT_ESTABLISHED','ROUTE_COUNT_UNCONFIRMED','COUNT_WORDING_NOT_PARSED')


@pytest.mark.parametrize('text,reason',[('Erection of 36 dwellings, 18 houses and 18 flats','POSSIBLE_BREAKDOWN_OF_A_TOTAL'),('Erection of 5 dwellings and 5 dwellings','REPEATED_COUNT')])
def test_a_total_and_its_breakdown_or_a_repeated_figure_is_never_added(text,reason):
    got=_a(text);assert (got['proposed_total'],got['admission'],got['reason'])==('NOT_ESTABLISHED','ROUTE_COUNT_UNCONFIRMED',reason)


@pytest.mark.parametrize('text,total,existing',[('Erection of 12 dwellings; 3 dwellings retained',12,3),('Erection of 11 dwellings, 5 dwellings are existing',11,5)])
def test_a_count_followed_by_retained_or_existing_wording_is_existing_stock_not_proposed(text,total,existing):
    got=_a(text);assert (got['proposed_total'],got['existing'])==(total,existing)


@pytest.mark.parametrize('text',['Erection of 10 student cluster flats','Erection of 150 bed student accommodation comprising 20 cluster flats'])
def test_student_accommodation_is_not_dwelling_supply_decision_d4(text):
    got=_a(text);assert (got['proposed_total'],got['admission'],got['reason'])==('NOT_ESTABLISHED','RETAIN_NOT_RESIDENTIAL_SUPPLY','STUDENT_ACCOMMODATION')


# ------------------------------------------------------------------ review round: the evidence model never raises on malformed input and never lets evidence vanish
def _rec(i='r',**kw):
    base=dict(id=i,basis='PROPOSED',value=49,source_kind='LISTING_PROPOSAL_TEXT',relations={});base.update(kw);return base


@pytest.mark.parametrize('bad',[dict(value=None),dict(value=True),dict(value='UP_TO:x'),dict(value='UP_TO:-5'),dict(value=-3),dict(value=0),dict(value=1.5),dict(source_kind=None),dict(source_kind=''),dict(basis='OTHER'),dict(scope=None),dict(scope=5),
                                dict(relations=['x']),dict(relations={'supersedes':['a']}),dict(id=None),dict(id=7)])
def test_a_malformed_record_is_rejected_and_reported_never_counted_and_never_raises(bad):
    good=_rec('g',value=12)
    recs=[good,_rec('b',**bad)]
    st=ce.resolve_basis(recs,'PROPOSED')
    assert st['state']=='RESOLVED' and st['quantity']==12 and st['rejected_records']
    for call in (lambda:ce.headline(recs),lambda:ce.size_outcome(recs),lambda:ce.read_model(recs),lambda:ce.search_match(recs,'EITHER',10,None)):call()      # nothing raises


def test_an_approved_record_without_a_source_kind_is_rejected_not_a_crash():
    st=ce.resolve_basis([dict(id='a',basis='APPROVED',value=49,relations={})],'APPROVED')
    assert st['state']=='NOT_ESTABLISHED' and st['rejected_records']==['a']


def test_malformed_relations_assessments_and_minimums_never_raise_and_have_no_effect():
    recs=[_rec('a',scope='Phase 1'),_rec('b',scope='Phase 2',value=52)]
    for rel in ([None],['x'],[dict(relation='NON_OVERLAPPING_PARTS')],[dict(relation='NON_OVERLAPPING_PARTS',source_kind='P',quote=5,scopes=['Phase 1','Phase 2'])],[dict(relation='NON_OVERLAPPING_PARTS',source_kind='P',quote='q',scopes=None)],[dict(relation='NON_OVERLAPPING_PARTS',source_kind='P',quote='q',scopes=[['x']])],5,None):
        assert ce.resolve_basis(recs,'PROPOSED',rel)['state']=='PER_SCOPE'
    for asm in ([None],['x'],[5],[dict(kind=['SUPERSEDES'])],[dict(kind='SUPERSEDES')],[dict(kind='COMMON_DEVELOPMENT',scopes=[['x'],'y'],authenticated=True,actor='a',timestamp='t',rationale='r',citations=['c'])],[dict(kind='SUPERSEDES',authenticated=True,actor='a',timestamp='t',rationale='r',citations=['c'],subject='a',target='b')],5):
        assert ce.resolve_basis(recs,'PROPOSED',(),asm)['state']=='PER_SCOPE'
    up=[dict(id='a',basis='APPROVED',value='UP_TO:20',source_kind='DECISION_NOTICE',relations={},minimum=m) for m in (dict(value=40,source_kind='DECISION_NOTICE',quote='q'),dict(value=10,source_kind='DECISION_NOTICE',quote=5),dict(value=10,source_kind=7,quote='q'),'x')]
    for r in up:assert ce.scenarios(ce.resolve_basis([r],'APPROVED'))==[(0,20)]      # a minimum above the maximum, or a malformed one, is ignored


def test_supersession_of_itself_mutual_or_cyclic_never_erases_evidence():
    ids=('a','b','c')
    for rels in ({'a':'a'},{'a':'b','b':'a'},{'a':'b','b':'c','c':'a'}):
        recs=[_rec(i,value=49+n,relations={'supersedes':rels[i]} if i in rels else {}) for n,i in enumerate(ids[:max(2,len(rels))])]
        st=ce.resolve_basis(recs,'PROPOSED')
        assert st['state']=='CONFLICT_UNRESOLVED' and sorted(i for i,_ in st['competing'])==sorted(r['id'] for r in recs) and not st['historical']      # every record is still there, none "wins"
    one=[_rec('a',relations={'supersedes':'a'})]
    assert ce.resolve_basis(one,'PROPOSED')['state']=='RESOLVED'      # a record cannot supersede itself out of existence


def test_owner_assessments_need_authentication_and_every_field_in_production_too():
    recs=[dict(_rec('a1',basis='APPROVED',source_kind='DECISION_NOTICE')),dict(_rec('a2',basis='APPROVED',value=52,source_kind='DECISION_NOTICE'))]
    good=dict(id='as1',kind='SUPERSEDES',subject='a2',target='a1',scope='whole',actor='owner:x',authenticated=True,timestamp='2026-10-20T09:30:00+00:00',rationale='s73',citations=['notice 2'])
    ok=ce.resolve_basis(recs,'APPROVED',(),[good]);assert ok['quantity']==52 and ok['relationship_basis']=='REVIEWER_ASSESSED' and ok['legal_supersession_established'] is False
    for field,bad in (('authenticated',False),('authenticated',None),('authenticated','yes'),('actor',''),('timestamp',''),('rationale','  '),('citations',[]),('citations',['']),('scope',''),('scope','Phase 2'),('subject','a1'),('target','zz'),('kind','LEGALLY_SUPERSEDES')):
        st=ce.resolve_basis(recs,'APPROVED',(),[dict(good,**{field:bad})]);assert st['state']=='CONFLICT_UNRESOLVED' and st['rejected_assessments']==['as1'],(field,bad)
    st=ce.resolve_basis(recs,'APPROVED',(),[{k:v for k,v in good.items() if k!='scope'}]);assert st['state']=='CONFLICT_UNRESOLVED'


# ------------------------------------------------------------------ second review round: no false demotion of genuine schemes
@pytest.mark.parametrize('text,total',[('Erection of 90 dwellings and retention of existing 2 dwellings',90),('Erection of 90 dwellings and existing 2 dwellings to be retained',90),('Erection of 60 dwellings and retained community hall',60),
    ('Erection of 60 dwellings with existing access retained',60),('Erection of 60 dwellings, existing barn retained',60),('Erection of 45 dwellings (affordable homes retained by RP)',45)])
def test_retained_wording_about_something_else_never_demotes_a_genuine_scheme(text,total):
    got=_a(text);assert (got['proposed_total'],got['admission'])==(total,'ADMIT_SCHEME')


def test_a_count_directly_followed_by_existing_is_existing_stock_not_new():
    got=_a('Erection of 40 houses and 20 flats existing');assert got['proposed_total']==40 and got['existing']==20
    got=_a('Erection of 12 dwellings; 3 dwellings to be demolished');assert (got['proposed_total'],got['lost'])==(12,3)


@pytest.mark.parametrize('text,total',[('Erection of 120 dwellings and a student common room',120),('45 dwellings on land adjacent to student halls',45),('12 dwellings on student union car park',12),('Erection of 90 dwellings, student accommodation of 200 bedspaces',90)])
def test_student_wording_elsewhere_in_the_text_never_demotes_genuine_dwellings(text,total):
    got=_a(text);assert (got['proposed_total'],got['admission'])==(total,'ADMIT_SCHEME' if total>=10 else 'RETAIN_BELOW_THRESHOLD')


def test_student_counts_alongside_dwellings_are_routed_and_all_student_schemes_retained():
    got=_a('3 dwellings and 12 flats for students');assert (got['admission'],got['reason'])==('ROUTE_COUNT_UNCONFIRMED','STUDENT_ACCOMMODATION_IN_MIXED_SCHEME')
    got=_a('Erection of 40 dwellings and 20 student cluster flats');assert (got['admission'],got['reason'])==('ROUTE_COUNT_UNCONFIRMED','STUDENT_ACCOMMODATION_IN_MIXED_SCHEME')


@pytest.mark.parametrize('text',['Erection of 200 dwellings with a 2 thousand sq m school','Erection of 200 dwellings and a hundred-space car park'])
def test_hundred_and_thousand_only_matter_where_they_count_dwellings(text):
    assert _a(text)['proposed_total']==200


@pytest.mark.parametrize('text,total',[('Erection of 60 dwellings. Approved under reference 21/0001/FUL the access is unchanged',60),('120 dwellings in substitution for office use approved under 18/0033/PNR',120),
    ('Erection of 80 dwellings, substitute house types and amend layout, ref 19/123/OUT',80),('Erection of 100 dwellings pursuant to outline 20/0001/OUT',100)])
def test_a_text_that_opens_with_a_new_creation_clause_is_not_turned_into_an_amendment(text,total):
    got=_a(text);assert got['scheme_role'] in ('NEW_SCHEME','PHASE_OF_PARENT') and got['proposed_total']==total


# ------------------------------------------------------------------ third round (owner corrections): reserved matters, mixed use, multiplied blocks, routing vocabulary
@pytest.mark.parametrize('text,context',[('APPLICATION FOR RESERVED MATTERS APPROVAL PURSUANT TO OUTLINE 91352/14 FOR APPEARANCE, LAYOUT, SCALE AND LANDSCAPING',None),
    ('RESERVED MATTERS PURSUANT TO OUTLINE 91352/14 FOR UP TO 1700 DWELLINGS: ACCESS AND LAYOUT','UP_TO:1700'),('RESERVED MATTERS APPLICATION FOR PHASE 2 OF 91352/14',None),('APPROVAL OF RESERVED MATTERS PURSUANT TO 91352/14',None)])
def test_reserved_matters_without_a_count_keep_their_parent_and_route_for_investigation_never_no_residential(text,context):
    got=_a(text)
    assert got['scheme_role']=='PHASE_OF_PARENT' and got['category']=='reserved_matters'
    assert (got['admission'],got['reason'])==('ROUTE_COUNT_UNCONFIRMED','RESERVED_MATTERS_WITHOUT_STATED_COUNT') and got['proposed_total']=='NOT_ESTABLISHED'      # missing residential wording in the clause is not "none created"
    assert got['parent_context']['reference']=='91352/14' and got['parent_context']['relation']=='PURSUANT_TO' and got['parent_context']['context_count']==context


@pytest.mark.parametrize('text',['MIXED USE DEVELOPMENT COMPRISING RESIDENTIAL FLATS AND GROUND FLOOR RETAIL','ERECTION OF FLATS WITH GROUND FLOOR COMMERCIAL UNITS','RESIDENTIAL AND RETAIL DEVELOPMENT',
    'ERECTION OF DWELLINGS AND A SHOP','MIXED-USE SCHEME OF HOUSES, OFFICES AND A CAFE'])
def test_explicit_residential_mixed_use_without_a_count_routes_as_count_unconfirmed(text):
    got=_a(text)
    assert (got['admission'],got['reason'],got['category'])==('ROUTE_COUNT_UNCONFIRMED','MIXED_USE_WITHOUT_STATED_RESIDENTIAL_COUNT','mixed_use') and got['proposed_total']=='NOT_ESTABLISHED'


def test_genuinely_non_residential_wording_is_still_not_residential_supply():
    for text,reason in (('CHANGE OF USE OF 12 FLATS TO A HOTEL','NO_RESIDENTIAL_CREATED'),('ERECTION OF 3 RETAIL UNITS','NO_RESIDENTIAL_CREATED'),('ALTERATIONS TO THE EXISTING 12 FLATS INCLUDING NEW WINDOWS','NO_RESIDENTIAL_CREATED'),
                        ('INSTALLATION OF 1 NO. AIR HANDLING UNIT','NO_RESIDENTIAL_CREATED'),('CONSTRUCTION OF 12 HOLIDAY HOMES','NOT_HOUSING_SUPPLY'),('ERECTION OF A 60 BEDROOM CARE HOME','BEDS_NOT_DWELLINGS')):
        got=_a(text);assert (got['admission'],got['reason'])==('RETAIN_NOT_RESIDENTIAL_SUPPLY',reason),text


@pytest.mark.parametrize('text,proposed,lost,existing,net,admission',[
    ('DEMOLITION OF 2 BLOCKS OF 6 FLATS EACH','NONE',12,12,-12,'RETAIN_NOT_RESIDENTIAL_SUPPLY'),
    ('DEMOLITION OF TWO BLOCKS CONTAINING SIX FLATS EACH','NONE',12,12,-12,'RETAIN_NOT_RESIDENTIAL_SUPPLY'),
    ('RETENTION OF TWO BLOCKS CONTAINING SIX FLATS EACH','NONE','NONE',12,0,'RETAIN_NOT_RESIDENTIAL_SUPPLY'),
    ('DEMOLITION OF 2 BLOCKS OF 6 FLATS EACH AND ERECTION OF 3 BLOCKS OF 8 FLATS EACH',24,12,12,12,'ADMIT_SCHEME'),
    ('DEMOLITION OF 2 EXISTING BLOCKS OF 6 FLATS EACH AND ERECTION OF 3 BLOCKS OF 8 FLATS EACH',24,12,12,12,'ADMIT_SCHEME'),
    ('ERECTION OF 12 DWELLINGS FOLLOWING DEMOLITION OF 2 EXISTING BLOCKS OF 6 FLATS EACH',12,12,12,0,'ADMIT_SCHEME'),
    ('ERECTION OF 3 BLOCKS OF 8 FLATS EACH FOLLOWING DEMOLITION OF 2 BLOCKS OF 6 FLATS EACH',24,12,12,12,'ADMIT_SCHEME'),
    ('ERECTION OF 2 BLOCKS OF 6 FLATS EACH WITH RETENTION OF 1 BLOCK OF 4 FLATS EACH',12,'NONE',4,12,'ADMIT_SCHEME')])
def test_multiplied_block_counts_are_classified_before_they_are_assigned(text,proposed,lost,existing,net,admission):
    got=_a(text)
    assert (got['proposed_total'],got['lost'],got['existing'],got['net'],got['admission'])==(proposed,lost,existing,net,admission),text


def test_demolishing_or_retaining_blocks_never_proposes_their_product():
    for text in ('DEMOLITION OF 2 BLOCKS OF 6 FLATS EACH','RETENTION OF 2 BLOCKS CONTAINING 6 FLATS EACH','2 EXISTING BLOCKS OF 6 FLATS EACH TO BE DEMOLISHED','ALTERATIONS TO 2 BLOCKS OF 6 FLATS EACH'):
        got=_a(text);assert got['proposed_total'] in ('NONE','NOT_ESTABLISHED') and got['admission']!='ADMIT_SCHEME' and not got['records'],text
    assert _a('ERECTION OF 2 BLOCKS OF 6 FLATS EACH')['proposed_total']==12      # the same wording is still a product when it IS the proposal


def test_routing_outcomes_are_validated_against_the_named_rule_versions_vocabulary():
    v1=ls.screen_row(row('ERECTION OF 12 DWELLINGS'));v3=ls.screen_row(row('ERECTION OF 12 DWELLINGS'),rule_version=ls.RULE_V3,unit_threshold=10)
    assert ls.routing_of(v1)==('disposition','SUPPORTED_PROCESSING_PRIORITY') and ls.routing_of(v3)==('count_assessment','ADMIT_SCHEME')
    assert set(ls.ROUTING_VOCABULARY)=={ls.RULE_V1,ls.RULE_V3} and ls.ROUTING_VOCABULARY[ls.RULE_V1].isdisjoint(ls.ROUTING_VOCABULARY[ls.RULE_V3])
    for value in ('ADMIT_SCHEMES','admit_scheme','','SUPPORTED_PROCESSING_PRIORITY',None,5,['ADMIT_SCHEME'],'ROUTE_COUNT_UNCONFIRMED '):      # unknown, misspelt, wrong-version, empty and non-string outcomes
        with pytest.raises(ValueError,match='ROUTING_(?:AUTHORITY_UNRESOLVED|OUTCOME_NOT_IN_VOCABULARY)'):ls.routing_of(dict(v3,count_assessment=dict(v3['count_assessment'],admission=value)))
    for value in ('ADMIT_SCHEME','UNKNOWN_OUTCOME','',None,3):
        with pytest.raises(ValueError,match='ROUTING_(?:AUTHORITY_UNRESOLVED|OUTCOME_NOT_IN_VOCABULARY)'):ls.routing_of(dict(v1,disposition=value))      # a v3 outcome is not a v1 disposition
    with pytest.raises(ValueError):ls.routing_of(dict(v1,rule_version='manchester-listing-screen-assessment-v2'))


def test_every_assessment_outcome_is_inside_the_v3_vocabulary():
    vocab=ls.ROUTING_VOCABULARY[ls.RULE_V3]
    rnd=random.Random(169)
    words=['ERECTION','DEMOLITION','OF','AND','12','6','FLATS','DWELLINGS','BLOCKS','EACH','RETAIL','SHOP','RESERVED MATTERS','PURSUANT TO','91352/14','STUDENT','UP TO','HOTEL','RETENTION','EXISTING','MIXED USE','TWENTY-FOUR','2','NO.','']
    texts=[e['proposal'] for e in EXAMPLES]+[' '.join(rnd.choice(words) for _ in range(rnd.randint(0,10))) for _ in range(500)]
    for t in texts:assert ca.assess_proposal(t)['admission'] in vocab,t


# ------------------------------------------------------------------ the digit-run dependency is resolved: end-to-end boundedness is tested under a hard timeout
def test_end_to_end_v3_screening_is_bounded_on_a_long_digit_run_and_a_regression_fails_rather_than_hangs():
    """Runs v3 screening on long digit runs in a CHILD process with a hard timeout, so a regression of the legacy qualifier's digit-run stall fails this test instead of hanging CI.
    The wider adversarial battery (comma/dash/letter-separated runs, long words, every entry point) is in tests/test_unit_filter_digit_runs.py."""
    import json,subprocess,sys
    child=("import sys,time\nsys.path.insert(0,sys.argv[1])\nfrom app.ingestion import listing_screening as ls\n"
           "r=lambda t:dict(reference='T/1',fields={'proposal':dict(state='PRESENT_VALUE',value=t,locator='x',truncated=False),'address':dict(state='PRESENT_VALUE',value='1 St',locator='x',truncated=False),'application_type':dict(state='UNKNOWN',value=None,locator='x',truncated=False)})\n"
           "out={}\nfor n,t in (('digits900','1'*900),('digits8192','1'*8192),('commas','1,'*4096)):\n    s=time.monotonic();ls.screen_row(r(t),rule_version=ls.RULE_V3,unit_threshold=10);out[n]=round(time.monotonic()-s,3)\nprint(sorted(out.items()))\n")
    try:
        done=subprocess.run([sys.executable,'-I','-c',child,str(ROOT)],capture_output=True,text=True,timeout=20)
    except subprocess.TimeoutExpired:
        pytest.fail('HUNG: v3 screening of a long digit run did not finish within 20 s (the digit-run stall has regressed)')
    assert done.returncode==0,done.stderr[-300:]
    assert all(v<3.0 for _,v in eval(done.stdout.strip().splitlines()[-1])),done.stdout


def test_the_new_modules_alone_are_bounded_on_the_same_digit_run():
    start=time.monotonic();ca._mentions('1'*8000);ca._nonres('1'*8000);assert time.monotonic()-start<1      # measured completion of the new regexes on this shape (not a proof of linear complexity)


# ------------------------------------------------------------------ third review: conversions of existing stock into a counted scheme
@pytest.mark.parametrize('text,proposed,lost,existing,net,admission',[
    ('Conversion of existing 3 blocks of 4 flats each to 18 flats',18,12,12,6,'ADMIT_SCHEME'),
    ('Conversion and extension of the existing 2 blocks of 6 flats each to form 30 apartments',30,12,12,18,'ADMIT_SCHEME'),
    ('Conversion of existing 12 flats to 18 flats',18,12,12,6,'ADMIT_SCHEME'),
    ('Conversion of 12 flats into 24 flats',24,12,12,12,'ADMIT_SCHEME'),
    ('Conversion of existing 12 flats to 6 flats',6,12,12,-6,'RETAIN_BELOW_THRESHOLD'),
    ('Conversion of offices to 12 flats',12,'NOT_ESTABLISHED','NOT_ESTABLISHED','NOT_ESTABLISHED','ADMIT_SCHEME')])
def test_conversion_of_existing_stock_into_a_counted_scheme_is_the_proposal_not_retained_stock(text,proposed,lost,existing,net,admission):
    got=_a(text);assert (got['proposed_total'],got['lost'],got['existing'],got['net'],got['admission'])==(proposed,lost,existing,net,admission),text


@pytest.mark.parametrize('text,total',[('Erection of 2 blocks each containing 6 flats',12),('Erection of 3 terraces each comprising 4 houses',12),('Erection of 2 blocks each of 6 flats',12)])
def test_blocks_each_containing_flats_multiply_and_never_undercount(text,total):
    got=_a(text);assert got['proposed_total']==total and got['admission']=='ADMIT_SCHEME'


def test_demolition_of_blocks_each_containing_flats_is_loss_not_proposal():
    got=_a('Demolition of 2 blocks each containing 6 flats');assert (got['proposed_total'],got['lost']) == ('NONE',12)


# ------------------------------------------------------------------ fourth review: a line break is a clause boundary and survives normalisation
@pytest.mark.parametrize('text,proposed,lost,existing,net',[
    ('Demolition of 12 flats\n18 new flats',18,12,12,6),
    ('Demolition of 12 flats\r\n18 new flats',18,12,12,6),
    ('Demolition of 12 flats \n \n  18 new flats',18,12,12,6),
    ('Demolition of 12 flats\u202818 new flats',18,12,12,6),
    ('Existing 12 flats\n18 new flats',18,'NONE',12,18),
    ('Existing 12 flats\n\n\n18 new flats',18,'NONE',12,18)])
def test_a_line_break_keeps_the_new_count_outside_the_demolition_or_existing_clause(text,proposed,lost,existing,net):
    got=_a(text)
    assert (got['proposed_total'],got['lost'],got['existing'],got['net'])==(proposed,lost,existing,net),text
    assert got['admission']=='ADMIT_SCHEME'


def test_the_same_text_on_one_line_without_a_break_is_not_split():
    got=_a('Demolition of 12 flats and erection of 18 new flats')
    assert (got['proposed_total'],got['lost'])==(18,12)      # the wording, not the layout, decides here
    got=_a('Existing 12 flats 18 new flats')
    assert got['admission']!='ADMIT_SCHEME' and got['proposed_total']!=18      # no break and no clause marker: the existing clause is not silently ended (conservative, never a false admit)


def test_normalisation_collapses_runs_but_keeps_one_line_break_and_stays_bounded():
    import time
    for t in ('12 flats'+'\n'*8000+'18 dwellings','12 flats'+' \n'*4000+'18 dwellings','Demolition of 12 flats'+'\n'*4000+'18 new flats','12'+'-'*8190,'flats'+' '*8187,'flats'+'\u3000'*8187,'\r\n'*4096+'12 flats'):
        start=time.monotonic();got=ca.assess_proposal(t[:8192]);assert time.monotonic()-start<1.5,t[:30];assert got['admission']
    got=_a('Demolition of 12 flats'+'\n'*4000+'18 new flats');assert (got['proposed_total'],got['lost'])==(18,12)


# ------------------------------------------------------------------ review of the newline rule: wrapping can never change a classification
WRAP_SENTENCES=['Variation of condition 2 to increase from 49 to 52 dwellings','Discharge of condition 5 relating to 40 dwellings approved under 19/00123/OUT','Details pursuant to condition 4 of 19/00123/OUT 40 dwellings',
    'Non material amendment to approved scheme for 40 dwellings ref 20/0001/FUL','Reserved matters pursuant to outline 91352/14 for 120 dwellings','Approval of reserved matters pursuant to 91352/14',
    'Demolition of existing bungalow and erection of 12 dwellings','Demolition of 2 houses and erection of 20 flats','Conversion of 12 flats to 18 flats','Erection of 12 dwellings. Existing 4 flats will be demolished',
    'Erection of 2 blocks of 6 flats each','Erection of 5 houses and 5 flats','Extension to existing 12 flats to provide 6 additional flats','Change of use of 8 flats to a hotel','Erection of 25 dwellings and demolition of 3 houses',
    'Mixed use development comprising residential flats and ground floor retail','Erection of 9 flats and 1 shop','Outline application for up to 50 dwellings','Section 73 variation to increase the number of dwellings from 49 to 52 on permission 00284/26']


def test_a_line_break_at_any_word_position_gives_the_single_line_result_except_between_two_counts():
    checked=0
    for sentence in WRAP_SENTENCES:
        words=sentence.split(' ');want=_a(sentence)
        for i in range(1,len(words)):
            for sep in ('\n','\r\n',' \n','\n  '):
                wrapped=' '.join(words[:i])+sep+' '.join(words[i:])
                got=_a(wrapped)
                before=' '.join(words[:i]);after=' '.join(words[i:])
                between_counts=bool(ca._PREV_NOUN.search(before)) and bool(ca._NEXT_COUNT.match(after))
                if between_counts:continue      # a real boundary between two counts: covered by the dedicated tests above
                assert {k:got[k] for k in KEYS}=={k:want[k] for k in KEYS},(repr(wrapped),got['admission'],want['admission'])
                checked+=1
    assert checked>500


@pytest.mark.parametrize('text',['Variation of\ncondition 2 to increase from 49 to 52 dwellings','Variation\nof condition 2 to increase from 49 to 52 dwellings','Discharge of\ncondition 5 relating to 40 dwellings approved under 19/00123/OUT',
    'Details pursuant\nto condition 4 of 19/00123/OUT 40 dwellings','Non\nmaterial amendment to approved scheme for 40 dwellings','Reserved\nmatters pursuant to outline 91352/14 for 120 dwellings'])
def test_a_wrapped_keyword_phrase_still_classifies_an_amendment_discharge_or_reserved_matters(text):
    got=_a(text);assert got['admission'] in ('RETAIN_RELATED_TO_PARENT','ROUTE_COUNT_UNCONFIRMED','ADMIT_SCHEME') and not (got['scheme_role']=='NEW_SCHEME' and got['admission']=='ADMIT_SCHEME'),text


def test_each_unicode_line_break_character_is_a_boundary_between_two_counts():
    for brk in ('\n','\r','\x0b','\x0c','\x85','\u2028','\u2029','\r\n'):
        got=_a('Demolition of 12 flats'+brk+'18 new flats');assert (got['proposed_total'],got['lost']) == (18,12),repr(brk)
