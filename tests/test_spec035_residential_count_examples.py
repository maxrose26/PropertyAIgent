"""Specification 035 (residential count and categorisation): the executable acceptance examples.
Offline, three jobs: (1) the examples obey the specification's own rules, so the specification cannot contradict itself; (2) the evidence model (separate proposed and approved bases, scope and overlap, provenance,
revision relationships, headline, search certainty over a size range, size admission, read model), written as the pure reference in tests/spec035_reference.py, reproduces every hand-written expectation;
(3) the recorded BASELINE of the current implementation (legacy qualify + screening rule v1) equals its live behaviour and the documented gap lists equal the live gaps, so the mapping cannot rot.
Nothing here changes behaviour. When the implementation proposal is built and approved, the gap sets below are shrunk deliberately in the same change; that edit is the evidence the gap closed."""
import copy
import json
import random
from pathlib import Path

import pytest

from app.scrapers.unit_filter import qualify
from app.ingestion import listing_screening as ls
from tests import spec035_reference as ref

ROOT=Path(__file__).resolve().parents[1]
DOC=json.loads((ROOT/'specifications/035-residential-count-examples.json').read_text(encoding='utf-8'))
EXAMPLES=DOC['examples']
THRESHOLD=DOC['admission_threshold']
ADMISSIONS={'ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','ROUTE_COUNT_UNCONFIRMED','RETAIN_BELOW_THRESHOLD','RETAIN_NOT_RESIDENTIAL_SUPPLY','RETAIN_RELATED_TO_PARENT','RETAIN_WATCHLIST','RETAIN_UNUSABLE_PROPOSAL'}
ROLES={'NEW_SCHEME','PHASE_OF_PARENT','AMENDMENT_OF_PARENT','DISCHARGE_OF_PARENT','PRE_APPLICATION_SIGNAL'}
SIZE_OUTCOMES={'ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','RETAIN_BELOW_THRESHOLD'}
NE='NOT_ESTABLISHED';NONE='NONE'

# The documented gaps of the CURRENT implementation against the specification (specification section 9). Shrink these deliberately when the implementation lands.
LEGACY_FALSE_NEGATIVES={'E06','E07','E08','E10'}      # supported total >= threshold, legacy does not admit (it takes one component, not the total)
LEGACY_FALSE_POSITIVES={'E17','E21','E22','E34','E35','E36','E44','E47'}      # legacy admits although no supported total >= threshold exists (E44: an amendment; E47: the output is 6)
LEGACY_COUNT_GAPS={'E06','E07','E08','E10','E14','E17','E21','E22','E23','E24','E25','E26','E27','E28','E29','E33','E34','E35','E36','E44','E45','E47'}
EVIDENCE_MODEL_EXAMPLES={'E37','E38','E38b','E38c','E38d','E38e','E38f','E38g','E38h','E38i','E38j','E38k','E38l','E38m','E38n','E38o','E38p','E38q','E38r','E38s','E38t'}      # the legacy single scalar cannot represent basis, scope, source, revision, overlap or conflict


def number(value):
    return value if isinstance(value,int) and not isinstance(value,bool) else None


def records_of(e):
    """Explicit evidence records, or for a plain example the single supported proposed record its proposal text gives."""
    if 'records' in e:return e['records']
    p=e['expected']['proposed_total']
    if number(p) is None and not (isinstance(p,str) and p.startswith('UP_TO:')):return []
    return [dict(id='t1',basis='PROPOSED',scope='whole',value=p,source_kind='LISTING_PROPOSAL_TEXT',document_date=None,revision=None,qualifier='outline' if e['expected']['category']=='outline_application' else None,relations={})]


def project(state):
    keys=('state','quantity','maximum','minimum','historical','unsupported_as_approved','overlap','relationship_basis','legal_supersession_established')
    out={k:state[k] for k in keys if k in state and state[k] not in ([],None)}
    if 'legal_supersession_established' in state:out['legal_supersession_established']=state['legal_supersession_established']
    if state['state']=='COMBINED_SCOPES':
        for k in ('membership','exhaustion','whole_development_total'):out[k]=state[k]
        if state.get('scheme_bounds'):out['scheme_bounds']=list(state['scheme_bounds'])
        out['scopes']={n:project(v) for n,v in state['scopes'].items()}
    if state['state']=='PER_SCOPE':
        for k in ('membership','exhaustion'):out[k]=state[k]
        if state.get('union_bounds'):out['union_bounds']=list(state['union_bounds'])
        if state.get('scheme_bounds'):out['scheme_bounds']=list(state['scheme_bounds'])
    if state['state'] in ('CONFLICT_UNRESOLVED','ALTERNATIVE_PERMISSIONS'):out['competing']=[list(x) for x in state['competing']]
    if state['state']=='PER_SCOPE':out['scopes']={n:project(v) for n,v in state['scopes'].items()}
    return out


def test_the_document_header_is_the_specified_version_and_threshold():
    assert DOC['spec_version']=='residential-count-v2' and THRESHOLD==10 and len(EXAMPLES)==len({e['id'] for e in EXAMPLES})>=62


@pytest.mark.parametrize('e',EXAMPLES,ids=[e['id'] for e in EXAMPLES])
def test_each_example_obeys_the_specified_rules(e):
    x=e['expected'];p=x['proposed_total'];a=x['admission']
    assert a in ADMISSIONS and x['scheme_role'] in ROLES and x['reason'] and isinstance(x['non_residential_units'],dict) and 'demolished' not in x
    # R-ADMIT: size eligibility comes from the supported proposed or approved count against the platform threshold (a minimum, no maximum), nothing else; conflicts and qualified quantities route to assessment
    if a in SIZE_OUTCOMES:assert ref.size_outcome(records_of(e),THRESHOLD,e.get('scope_relations',()),e.get('assessments',()))==a
    if a=='ADMIT_FOR_ASSESSMENT':assert x['reason'] in ('QUALIFIED_MAXIMUM_AT_OR_ABOVE_THRESHOLD','COUNT_CONFLICT')
    if a in ('ROUTE_COUNT_UNCONFIRMED','RETAIN_UNUSABLE_PROPOSAL','RETAIN_WATCHLIST'):assert p==NE and not records_of(e)
    # R-RELATED / R-AMEND: an amendment, discharge or pre-application signal never carries its own total and never admits as a scheme. Parent figures are context; ONLY a clause stating the resulting
    # total is a revised total, and it is a proposed-basis revision in the parent's scope, never an approval
    if x['scheme_role'] in ('AMENDMENT_OF_PARENT','DISCHARGE_OF_PARENT','PRE_APPLICATION_SIGNAL'):
        assert p==NE and a in ('RETAIN_RELATED_TO_PARENT','RETAIN_WATCHLIST') and x['approved_total']==NE
    pc=x['parent_context']
    if pc and 'revised_total' in pc:assert x['scheme_role']=='AMENDMENT_OF_PARENT' and number(pc['revised_total']) is not None and pc['revised_total']!=pc['context_count']
    # R-NET: net = proposed - lost, established only when both are established on the same basis (NONE counts as 0); lost is every existing dwelling demolished, converted away or replaced; nothing is inferred otherwise
    pn=0 if p==NONE else number(p);dn=0 if x['lost']==NONE else number(x['lost'])
    if pn is not None and dn is not None:assert x['net']==pn-dn
    else:assert x['net']==NE
    if number(x['lost']) is not None:assert x['lost']>=0
    # R-MIXED: commercial units are recorded separately and are never residential dwellings
    for kind,count in x['non_residential_units'].items():assert number(count) is not None and count>0
    # R-STATUS: planning status and construction progress are separate facts and never enter a count
    if 'planning' in e:assert set(e['planning'])<={'planning_status','construction_progress'}


@pytest.mark.parametrize('e',[e for e in EXAMPLES if 'records' in e],ids=[e['id'] for e in EXAMPLES if 'records' in e])
def test_the_evidence_model_reproduces_every_hand_written_expectation(e):
    recs=e['records'];rel=e['scope_relations'];asm=e.get('assessments',[]);x=e['expected']
    for basis,name in ((ref.PROPOSED,'proposed'),(ref.APPROVED,'approved')):
        assert project(ref.resolve_basis(recs,basis,rel,asm))==x['bases'][name],(e['id'],name)
    assert ref.headline(recs,rel,asm)==x['headline']
    for s in x['search']:
        got=ref.search_match(recs,s['basis'],s['size_min'],s['size_max'],rel,asm)
        assert dict(match=got['match'],matched_by=got['matched_by'])==dict(match=s['match'],matched_by=s['matched_by']),(e['id'],s)
        if 'level' in s:assert (got['level'],got['scopes'])==(s['level'],s['scopes']),(e['id'],s)
    assert {s['basis'] for s in x['search'] if s['size_min']==THRESHOLD and s['size_max'] is None}=={'APPROVED','PROPOSED','EITHER'}      # every example states all three bases at the default range


def test_approval_needs_permission_evidence_and_a_form_or_proposal_alone_never_establishes_it():
    for kind in ('APPLICATION_FORM_STRUCTURED','LISTING_PROPOSAL_TEXT','DETAIL_PROPOSAL_TEXT','PLANNING_STATEMENT','OFFICER_REPORT'):
        s=ref.resolve_basis([dict(id='a',basis='APPROVED',value=49,source_kind=kind,relations={})],ref.APPROVED)
        assert s['state']==ref.NOT_ESTABLISHED and s['unsupported_as_approved']==['a']
    for kind in ('DECISION_NOTICE','APPROVED_PLANS_SCHEDULE'):
        assert ref.resolve_basis([dict(id='a',basis='APPROVED',value=49,source_kind=kind,relations={})],ref.APPROVED)['state']==ref.RESOLVED


def test_nothing_resolves_a_conflict_by_date_upload_order_record_order_size_or_source_rank():
    base=[dict(id='a1',basis='APPROVED',value=49,source_kind='DECISION_NOTICE',document_date='2024-02-01',relations={}),dict(id='a2',basis='APPROVED',value=52,source_kind='APPROVED_PLANS_SCHEDULE',document_date='2026-02-01',relations={})]
    assert ref.resolve_basis(base,ref.APPROVED)['state']==ref.CONFLICT
    for _ in range(20):      # any order, any dates, either figure larger, either source kind: still unresolved
        shuffled=copy.deepcopy(base);random.shuffle(shuffled)
        for r in shuffled:r['document_date']=random.choice(['2020-01-01','2030-01-01',None]);r['source_kind']=random.choice(['DECISION_NOTICE','APPROVED_PLANS_SCHEDULE']);r['value']=random.choice([49,52]) if r['id']=='a1' else 52
        s=ref.resolve_basis(shuffled,ref.APPROVED)
        assert s['state']==(ref.CONFLICT if len({r['value'] for r in shuffled})>1 else ref.RESOLVED)
    proposed=[dict(id='f',basis='PROPOSED',value=52,source_kind='APPLICATION_FORM_STRUCTURED',relations={}),dict(id='t',basis='PROPOSED',value=49,source_kind='LISTING_PROPOSAL_TEXT',relations={}),dict(id='s',basis='PROPOSED',value=60,source_kind='PLANNING_STATEMENT',relations={})]
    assert ref.resolve_basis(proposed,ref.PROPOSED)['state']==ref.CONFLICT      # a structured form does not outrank the proposal text or a statement
    superseded=copy.deepcopy(base);superseded[1]['relations']={'supersedes':'a1'}
    assert ref.resolve_basis(superseded,ref.APPROVED)['quantity']==52      # only an explicit relationship resolves it
    unsupported_supersede=copy.deepcopy(base);unsupported_supersede[1]['source_kind']='APPLICATION_FORM_STRUCTURED';unsupported_supersede[1]['relations']={'supersedes':'a1'}
    assert ref.resolve_basis(unsupported_supersede,ref.APPROVED)['quantity']==49      # an unsupported record cannot supersede a permission


def test_source_precedence_only_orders_the_citation_when_sources_agree_and_never_decides_a_disagreement():
    agree=[dict(id='t',basis='PROPOSED',value=49,source_kind='LISTING_PROPOSAL_TEXT',relations={}),dict(id='f',basis='PROPOSED',value=49,source_kind='APPLICATION_FORM_STRUCTURED',relations={})]
    s=ref.resolve_basis(agree,ref.PROPOSED)
    assert s['state']==ref.RESOLVED and s['quantity']==49 and sorted(i for i,_ in s['competing'])==['f','t']      # both sources are kept and both are cited


PH=[dict(id='p1',basis='PROPOSED',scope='Phase 1',value=49,source_kind='LISTING_PROPOSAL_TEXT',relations={}),dict(id='p2',basis='PROPOSED',scope='Phase 2',value=52,source_kind='LISTING_PROPOSAL_TEXT',relations={})]
def rel(kind,source='PHASING_PLAN',quote='Phases 1 and 2 ...',scopes=('Phase 1','Phase 2')):return dict(scopes=list(scopes),relation=kind,source_kind=source,quote=quote)


def test_phase_labels_alone_never_prove_disjoint_scopes_and_a_total_needs_supported_non_overlap():
    for relations in ([],[rel('NON_OVERLAPPING_PARTS',quote='')],[rel('NON_OVERLAPPING_PARTS',quote='  ')],[rel('NON_OVERLAPPING_PARTS',source=None)],[rel('PART_OF')],[rel('NON_OVERLAPPING_PARTS',scopes=('Phase 1','Phase 3'))]):
        st=ref.resolve_basis(PH,ref.PROPOSED,relations)
        assert st['state']==ref.PER_SCOPE and st['overlap']=='UNRESOLVED' and 'quantity' not in st      # unresolved overlap is preserved and no total exists
    assert ref.resolve_basis(PH,ref.PROPOSED,[rel('NON_OVERLAPPING_PARTS')])['quantity']==101
    with_status=copy.deepcopy(PH);[r.update(planning_status='REFUSED',construction_progress='STARTED') for r in with_status]
    assert ref.headline(with_status)==ref.headline(PH)      # planning status and construction progress are never read


def test_an_exact_sum_is_a_combined_scope_quantity_and_only_membership_plus_exhaustion_make_it_the_whole_development():
    NO=rel('NON_OVERLAPPING_PARTS');MEM=rel('COMMON_DEVELOPMENT',source='PLANNING_STATEMENT',quote='one development');EXH=rel('EXHAUSTS_DEVELOPMENT',quote='together the whole development')
    # 1. non-overlap alone: the quantity of exactly these scopes together
    a=ref.resolve_basis(PH,ref.PROPOSED,[NO])
    assert (a['state'],a['quantity'],a['membership'],a['exhaustion'],a['whole_development_total'],a['scheme_bounds'])==(ref.COMBINED,101,False,False,None,None)
    assert ref.headline(PH,[NO])['label']=='Proposed (combined scopes): 101 (Phase 1: 49, Phase 2: 52)'
    r=ref.search_match(PH,ref.PROPOSED,10,None,[NO]);assert (r['match'],r['level'],r['scopes'],r['quantity_status'])==(ref.MEETS,'SCOPE',['Phase 1','Phase 2'],{'PROPOSED':'COMBINED_SCOPE_QUANTITY'})
    assert ref.search_match(PH,ref.PROPOSED,10,100,[NO])['match']==ref.NO_MATCH and ref.search_match(PH,ref.PROPOSED,10,101,[NO])['match']==ref.MEETS
    assert ref.read_model(PH,[NO])['headline_scalar'] is None and ref.read_model(PH,[NO])['bases']['PROPOSED']['combined_scope_quantity']==101 and ref.read_model(PH,[NO])['bases']['PROPOSED']['whole_development_total'] is None
    # 2. plus membership, no exhaustion: the development is at least the sum, no upper bound; still not a whole-development total
    b=ref.resolve_basis(PH,ref.PROPOSED,[NO,MEM])
    assert (b['state'],b['quantity'],b['membership'],b['exhaustion'],b['whole_development_total'],b['scheme_bounds'])==(ref.COMBINED,101,True,False,None,(101,None))
    assert ref.headline(PH,[NO,MEM])['label']=='Proposed (combined scopes): 101 (Phase 1: 49, Phase 2: 52)'
    for hi,want in ((None,ref.MEETS),(100,ref.NO_MATCH),(200,ref.POSSIBLE)):
        r=ref.search_match(PH,ref.PROPOSED,10,hi,[NO,MEM]);assert (r['match'],r['level'],r['quantity_status'])==(want,'SCHEME' if want!=ref.NO_MATCH else 'SCHEME',{'PROPOSED':'COMBINED_SCOPE_QUANTITY'} if want!=ref.NO_MATCH else {}),(hi,r)
    assert ref.search_match(PH,ref.PROPOSED,102,None,[NO,MEM])['match']==ref.POSSIBLE      # the development may be larger than the sum
    assert ref.read_model(PH,[NO,MEM])['headline_scalar'] is None
    # 3. plus exhaustion: an exact whole-development total
    c=ref.resolve_basis(PH,ref.PROPOSED,[NO,MEM,EXH])
    assert (c['state'],c['quantity'],c['whole_development_total'],c['scheme_bounds'])==(ref.COMBINED,101,101,(101,101))
    assert ref.headline(PH,[NO,MEM,EXH])['label']=='Proposed: 101 (Phase 1: 49, Phase 2: 52)'
    r=ref.search_match(PH,ref.PROPOSED,10,None,[NO,MEM,EXH]);assert (r['match'],r['level'],r['quantity_status'])==(ref.MEETS,'SCHEME',{'PROPOSED':'CONFIRMED_QUANTITY'})
    assert ref.search_match(PH,ref.PROPOSED,102,None,[NO,MEM,EXH])['match']==ref.NO_MATCH and ref.search_match(PH,ref.PROPOSED,10,100,[NO,MEM,EXH])['match']==ref.NO_MATCH
    sc=ref.read_model(PH,[NO,MEM,EXH])['headline_scalar']
    assert sc=={'value':101,'basis':'PROPOSED','qualifier':None,'state':'RESOLVED_WHOLE_DEVELOPMENT','semantics':'residential-count-v2:headline_exact'}
    # exhaustion without non-overlap supports no total at all; exhaustion alone is membership too but the overlap stays unresolved
    d=ref.resolve_basis(PH,ref.PROPOSED,[EXH]);assert d['state']==ref.PER_SCOPE and d['scheme_bounds']==(52,101) and 'quantity' not in d and ref.read_model(PH,[EXH])['headline_scalar'] is None
    # a reviewer-assessed chain is labelled and never cached
    asm=[dict(good_assessment(id='n',kind='NON_OVERLAPPING_PARTS'),scopes=['Phase 1','Phase 2']),dict(good_assessment(id='e',kind='EXHAUSTS_DEVELOPMENT'),scopes=['Phase 1','Phase 2'])]
    e=ref.resolve_basis(PH,ref.PROPOSED,(),asm);assert e['whole_development_total']==101 and e['relationship_basis']=='REVIEWER_ASSESSED' and ref.read_model(PH,(),asm)['headline_scalar'] is None
    assert ref.headline(PH,(),asm)['label'].endswith('(relationship reviewer-assessed)')
    # the sum never decides admission differently from its scopes: each scope and the sum are exact supported counts
    assert ref.size_outcome(PH,10,[NO])=='ADMIT_SCHEME'


def test_bounds_of_the_union_of_scopes_are_not_a_whole_scheme_total_without_supported_membership_and_exhaustion():
    none=ref.resolve_basis(PH,ref.PROPOSED,[])
    assert none['union_bounds']==(52,101) and none['scheme_bounds'] is None and not none['membership'] and not none['exhaustion']      # a bound on these two phases together, nothing about the scheme
    r=ref.search_match(PH,ref.PROPOSED,10,100);assert (r['match'],r['level'],r['scopes'])==(ref.MEETS,'SCOPE',['Phase 1','Phase 2'])      # judged one scope at a time and labelled so
    r=ref.search_match(PH,ref.PROPOSED,10,51);assert (r['match'],r['level'],r['scopes'])==(ref.MEETS,'SCOPE',['Phase 1'])
    member=ref.resolve_basis(PH,ref.PROPOSED,[rel('COMMON_DEVELOPMENT',source='PLANNING_STATEMENT')])
    assert member['membership'] and not member['exhaustion'] and member['scheme_bounds']==(52,None)      # at least the larger phase, NO upper bound
    for hi,want in ((100,ref.POSSIBLE),(1000,ref.POSSIBLE),(51,ref.NO_MATCH),(None,ref.MEETS)):assert ref.search_match(PH,ref.PROPOSED,10,hi,[rel('COMMON_DEVELOPMENT',source='PLANNING_STATEMENT')])['match']==want
    assert ref.search_match(PH,ref.PROPOSED,60,None,[rel('COMMON_DEVELOPMENT',source='PLANNING_STATEMENT')])['match']==ref.POSSIBLE      # the scheme may well be larger than 60
    ex=ref.resolve_basis(PH,ref.PROPOSED,[rel('EXHAUSTS_DEVELOPMENT')])
    assert ex['membership'] and ex['exhaustion'] and ex['scheme_bounds']==(52,101)      # exhaustion gives the upper bound
    for hi,want in ((100,ref.POSSIBLE),(101,ref.MEETS),(51,ref.NO_MATCH)):assert ref.search_match(PH,ref.PROPOSED,10,hi,[rel('EXHAUSTS_DEVELOPMENT')])['match']==want
    assert ref.search_match(PH,ref.PROPOSED,102,None,[rel('EXHAUSTS_DEVELOPMENT')])['match']==ref.NO_MATCH
    assert ref.resolve_basis(PH,ref.PROPOSED,[rel('EXHAUSTS_DEVELOPMENT',scopes=('Phase 1','Phase 3'))])['scheme_bounds'] is None      # support for other scopes covers nothing here


def test_union_bounds_need_compatible_count_bases_and_never_mix_proposed_with_approved():
    mixed=[dict(id='p1',basis='PROPOSED',scope='Phase 1',value=49,source_kind='LISTING_PROPOSAL_TEXT',relations={}),dict(id='a2',basis='APPROVED',scope='Phase 2',value=52,source_kind='DECISION_NOTICE',relations={})]
    for basis in (ref.PROPOSED,ref.APPROVED):
        st=ref.resolve_basis(mixed,basis,[rel('EXHAUSTS_DEVELOPMENT')])
        assert st['state']==ref.RESOLVED and len(st['scopes'])==1      # each basis keeps only its own scope; nothing is added across bases
    other_metric=copy.deepcopy(PH);other_metric[1]['metric']='bedspaces'
    st=ref.resolve_basis(other_metric,ref.PROPOSED,[rel('EXHAUSTS_DEVELOPMENT'),rel('NON_OVERLAPPING_PARTS')])
    assert st['state']==ref.PER_SCOPE and st['union_bounds'] is None and st['scheme_bounds'] is None and 'quantity' not in st      # dwellings and bedspaces are not compatible counts


def test_a_qualified_maximum_has_no_positive_lower_bound_unless_one_is_separately_supported():
    rec=lambda **kw:[dict(id='a',basis='APPROVED',value='UP_TO:50',source_kind='DECISION_NOTICE',relations={},**kw)]
    assert ref.scenarios(ref.resolve_basis(rec(),ref.APPROVED))==[(0,50)]
    for bad in (dict(value=0,source_kind='DECISION_NOTICE',quote='q'),dict(value=40,source_kind='DECISION_NOTICE',quote=''),dict(value=40,source_kind=None,quote='q'),dict(value=True,source_kind='DECISION_NOTICE',quote='q'),'40'):
        assert ref.scenarios(ref.resolve_basis(rec(minimum=bad),ref.APPROVED))==[(0,50)],bad      # an unsupported or malformed minimum is ignored
    good=dict(value=40,source_kind='DECISION_NOTICE',quote='a minimum of 40 and up to 50 dwellings')
    assert ref.scenarios(ref.resolve_basis(rec(minimum=good),ref.APPROVED))==[(40,50)]
    for lo,hi,want in ((1,100,ref.MEETS),(10,100,ref.MEETS),(0,100,ref.MEETS),(40,50,ref.MEETS),(41,50,ref.POSSIBLE),(10,45,ref.POSSIBLE),(10,39,ref.NO_MATCH),(51,None,ref.NO_MATCH)):      # with the supported minimum the interval is 40 to 50
        assert ref.search_match(rec(minimum=good),ref.APPROVED,lo,hi)['match']==want,(lo,hi)
    assert ref.search_match(rec(),ref.APPROVED,1,100)['match']==ref.POSSIBLE and ref.search_match(rec(),ref.APPROVED,0,100)['match']==ref.MEETS      # "up to 50" never meets a positive minimum on its own


def good_assessment(**kw):
    a=dict(id='as1',kind='SUPERSEDES',subject='a2',target='a1',scope='whole',actor='owner:max.rose',authenticated=True,timestamp='2026-10-20T09:30:00+00:00',rationale='s73 variation of the same site',citations=['decision notice 2, recital 3'])
    a.update(kw);return a
PERMS=[dict(id='a1',basis='APPROVED',value=49,source_kind='DECISION_NOTICE',relations={}),dict(id='a2',basis='APPROVED',value=52,source_kind='DECISION_NOTICE',relations={})]


def test_an_owner_relationship_assessment_needs_every_field_and_is_always_labelled_reviewer_assessed():
    ok=ref.resolve_basis(PERMS,ref.APPROVED,(),[good_assessment()])
    assert ok['state']==ref.RESOLVED and ok['quantity']==52 and ok['historical']==['a1'] and ok['relationship_basis']=='REVIEWER_ASSESSED' and ok['legal_supersession_established'] is False
    assert ref.headline(PERMS,(),[good_assessment()])['label']=='Approved: 52 (supersession reviewer-assessed)'
    for field,bad in (('actor',''),('actor',None),('authenticated',False),('authenticated','yes'),('timestamp',''),('rationale','  '),('citations',[]),('citations',['']),('citations','x'),('scope',''),('scope','Phase 2'),('kind','LEGALLY_SUPERSEDES'),('subject','zz'),('target','zz')):
        st=ref.resolve_basis(PERMS,ref.APPROVED,(),[good_assessment(**{field:bad})])
        assert st['state']==ref.CONFLICT and st['rejected_assessments']==['as1'],(field,bad)      # an incomplete or unauthenticated assessment is ignored and the conflict stays
    both=[dict(PERMS[0]),dict(PERMS[1],relations={'supersedes':'a1'})]
    st=ref.resolve_basis(both,ref.APPROVED,(),[good_assessment()])
    assert st['quantity']==52 and 'relationship_basis' not in st      # a document-stated relationship is not downgraded by a redundant assessment


def test_an_owner_assessment_cannot_create_permission_evidence_alter_planning_status_or_establish_legal_supersession():
    form=[dict(id='a1',basis='APPROVED',value=49,source_kind='DECISION_NOTICE',relations={}),dict(id='a2',basis='APPROVED',value=52,source_kind='APPLICATION_FORM_STRUCTURED',relations={})]
    st=ref.resolve_basis(form,ref.APPROVED,(),[good_assessment()])
    assert st['state']==ref.RESOLVED and st['quantity']==49 and st['unsupported_as_approved']==['a2'] and 'relationship_basis' not in st      # an unsupported record stays unsupported; an assessment cannot promote it or supersede with it
    only=[dict(id='a2',basis='APPROVED',value=52,source_kind='LISTING_PROPOSAL_TEXT',relations={})]
    assert ref.resolve_basis(only,ref.APPROVED,(),[good_assessment(subject='a2',target='a2')])['state']==ref.NOT_ESTABLISHED      # no assessment creates an approved count
    status=copy.deepcopy(PERMS);[r.update(planning_status='REFUSED') for r in status]
    assert ref.headline(status,(),[good_assessment()])==ref.headline(PERMS,(),[good_assessment()])      # planning status is never read or written
    assert ref.read_model(PERMS,(),[good_assessment()])['headline_scalar'] is None      # a reviewer-assessed resolution is shown, labelled, never exported as a plain scalar
    assert ref.read_model(PERMS,(),[good_assessment()])['bases']['APPROVED']['relationship_basis']=='REVIEWER_ASSESSED'
    asm=[dict(good_assessment(id='as2',kind='NON_OVERLAPPING_PARTS'),scopes=['Phase 1','Phase 2'])]
    st=ref.resolve_basis(PH,ref.PROPOSED,(),asm)
    assert st['state']==ref.COMBINED and st['quantity']==101 and st['whole_development_total'] is None and st['relationship_basis']=='REVIEWER_ASSESSED' and st['legal_supersession_established'] is False      # a scope relation can be assessed too, and says so
    assert ref.resolve_basis(PH,ref.PROPOSED,(),[dict(asm[0],scopes=['Phase 1'])])['state']==ref.PER_SCOPE      # an assessment must name the exact scopes (at least two)


def test_search_certainty_is_judged_against_the_whole_selected_range_minimum_and_maximum():
    def m(records,lo,hi,basis=ref.EITHER):return ref.search_match(records,basis,lo,hi)['match']
    exact=lambda n,b='PROPOSED':[dict(id='r',basis=b,value=n,source_kind='LISTING_PROPOSAL_TEXT' if b=='PROPOSED' else 'DECISION_NOTICE',relations={})]
    assert (m(exact(30),10,50),m(exact(5),10,50),m(exact(60),10,50),m(exact(10),10,10),m(exact(50),10,50),m(exact(51),10,50))==(ref.MEETS,ref.NO_MATCH,ref.NO_MATCH,ref.MEETS,ref.MEETS,ref.NO_MATCH)
    upto=exact('UP_TO:50')      # "up to 50" has no evidenced positive lower bound: anything from 0 to 50
    assert m(upto,10,100)==ref.POSSIBLE and m(upto,1,100)==ref.POSSIBLE and m(upto,60,None)==ref.NO_MATCH and m(upto,10,None)==ref.POSSIBLE and m(upto,1,40)==ref.POSSIBLE and m(upto,0,100)==ref.MEETS
    conflict=[dict(id='a',basis='PROPOSED',value=9,source_kind='LISTING_PROPOSAL_TEXT',relations={}),dict(id='b',basis='PROPOSED',value=60,source_kind='APPLICATION_FORM_STRUCTURED',relations={})]
    assert m(conflict,10,50)==ref.NO_MATCH      # one of the two is true and neither is inside 10-50: not a possible match, though the hull overlaps
    assert m(conflict,10,None)==ref.POSSIBLE and m(conflict,5,100)==ref.MEETS and m(conflict,10,30)==ref.NO_MATCH
    qual_conflict=[dict(id='a',basis='PROPOSED',value='UP_TO:50',source_kind='LISTING_PROPOSAL_TEXT',relations={}),dict(id='b',basis='PROPOSED',value=70,source_kind='APPLICATION_FORM_STRUCTURED',relations={})]
    assert m(qual_conflict,1,100)==ref.POSSIBLE and m(qual_conflict,0,100)==ref.MEETS      # a qualified figure inside a conflict also starts at 0, not 1
    straddle=[dict(id='a',basis='PROPOSED',value=49,source_kind='LISTING_PROPOSAL_TEXT',relations={}),dict(id='b',basis='PROPOSED',value=52,source_kind='APPLICATION_FORM_STRUCTURED',relations={})]
    assert m(straddle,10,50)==ref.POSSIBLE and m(straddle,10,100)==ref.MEETS and m(straddle,50,None)==ref.POSSIBLE and m(straddle,53,None)==ref.NO_MATCH


def test_a_size_match_is_not_a_confirmed_quantity_planning_approval_or_buyer_fit():
    by_id={e['id']:e for e in EXAMPLES}
    got=ref.search_match(by_id['E38q']['records'],ref.APPROVED,10,100)
    assert got['match']==ref.MEETS and got['quantity_status']=={'APPROVED':'QUALIFIED_QUANTITY'}      # meets the filter (a supported minimum of 40), quantity still qualified
    assert ref.search_match(by_id['E38g']['records'],ref.APPROVED,1,100)['match']==ref.POSSIBLE      # the same wording without a supported minimum cannot
    got=ref.search_match(by_id['E38']['records'],ref.PROPOSED,10,100)
    assert got['match']==ref.MEETS and got['quantity_status']=={'PROPOSED':'QUANTITY_UNDER_REVIEW'}
    got=ref.search_match(by_id['E38m']['records'],ref.PROPOSED,10,None)
    assert got['match']==ref.MEETS and got['matched_by']==['PROPOSED'] and got['quantity_status']=={'PROPOSED':'CONFIRMED_QUANTITY'}      # a refused application still meets a size filter: status is not read
    assert ref.search_match(by_id['E38m']['records'],ref.APPROVED,10,None)['match']==ref.NO_MATCH      # and it is never an approved match
    assert ref.LABELS=={ref.MEETS:'Meets size filter',ref.POSSIBLE:'Possible size match'} and 'confirmed quantity' in ref.LABEL_NOTE and 'planning approval' in ref.LABEL_NOTE and 'buyer fit' in ref.LABEL_NOTE
    assert 'CONFIRMED' not in {ref.MEETS,ref.POSSIBLE,ref.NO_MATCH}      # the old "confirmed match" wording is gone


def test_search_shows_the_causing_basis_and_defaults_to_either():
    by_id={e['id']:e for e in EXAMPLES}
    assert ref.EITHER=='EITHER'
    got=ref.search_match(by_id['E38e']['records'],ref.EITHER,50,None)
    assert (got['match'],got['matched_by'])==(ref.MEETS,['PROPOSED'])      # approved 49 misses a minimum of 50, the proposed revision 52 meets it: the result names the basis
    got=ref.search_match(by_id['E38e']['records'],ref.EITHER,10,50)
    assert (got['match'],got['matched_by'])==(ref.MEETS,['APPROVED'])      # with a maximum of 50 the revision falls outside and only the approval matches


def test_results_are_deduplicated_by_scheme_identity_keeping_the_best_class_and_every_contributing_application():
    rows=[dict(scheme_id='S1',application='APP/2',match=ref.POSSIBLE,matched_by=['PROPOSED']),dict(scheme_id='S1',application='APP/1',match=ref.MEETS,matched_by=['APPROVED']),
          dict(scheme_id='S1',application='APP/3',match=ref.MEETS,matched_by=['PROPOSED']),dict(scheme_id='S2',application='APP/9',match=ref.POSSIBLE,matched_by=['APPROVED'])]
    assert ref.dedupe_by_scheme(rows)==[dict(scheme_id='S1',match=ref.MEETS,matched_by=['APPROVED','PROPOSED'],applications=['APP/1','APP/2','APP/3']),dict(scheme_id='S2',match=ref.POSSIBLE,matched_by=['APPROVED'],applications=['APP/9'])]


def test_the_read_model_never_returns_a_bare_number_and_an_exact_cache_keeps_basis_and_qualifier():
    by_id={e['id']:e for e in EXAMPLES}
    m=ref.read_model(by_id['E38e']['records'])
    assert m['headline_scalar']=={'value':49,'basis':'APPROVED','qualifier':None,'state':'RESOLVED','semantics':'residential-count-v2:headline_exact'}      # approved is the headline basis; the proposed revision is NOT swapped in
    assert m['bases']['PROPOSED']['quantity']==52 and m['bases']['APPROVED']['quantity']==49      # both bases stay visible beside the cache
    for ident in ('E38','E38c','E38g','E38j','E38k','E38n','E38h','E38o','E38p','E38q','E38r'):
        assert ref.read_model(by_id[ident]['records'],by_id[ident]['scope_relations'],by_id[ident].get('assessments',()))['headline_scalar'] is None      # qualified, conflicting, alternative or per-phase: no scalar at all
    for e in [e for e in EXAMPLES if 'records' in e]:
        m=ref.read_model(e['records'],e['scope_relations'],e.get('assessments',()));c=m['headline_scalar']
        assert isinstance(m,dict) and (c is None or (isinstance(c,dict) and {'value','basis','qualifier','state','semantics'}<=set(c)))
        assert not isinstance(c,int)


@pytest.mark.parametrize('e',[e for e in EXAMPLES if 'records' not in e and e['expected']['admission'] in SIZE_OUTCOMES],ids=lambda e:e['id'])
def test_a_plain_example_gets_the_labelled_proposed_headline_and_the_default_either_search(e):
    recs=records_of(e);h=ref.headline(recs);p=e['expected']['proposed_total']
    if number(p) is not None:assert h==dict(kind='PROPOSED',label='Proposed: %d'%p)
    else:assert h['label'] in ('Proposed (outline): up to %s'%p.split(':')[1],'Proposed: up to %s'%p.split(':')[1])
    want=ref.MEETS if number(p) is not None and p>=THRESHOLD else ref.POSSIBLE if number(p) is None and int(p.split(':')[1])>=THRESHOLD else ref.NO_MATCH
    assert ref.search_match(recs,ref.EITHER,THRESHOLD)['match']==want and ref.search_match(recs,ref.APPROVED,THRESHOLD)['match']==ref.NO_MATCH


def test_mixed_use_counts_only_dwellings_and_records_commercial_units_separately():
    by_id={e['id']:e for e in EXAMPLES}
    nine=by_id['E41']['expected'];ten=by_id['E42']['expected']
    assert nine['proposed_total']==9 and nine['non_residential_units']=={'retail':1} and nine['admission']=='RETAIN_BELOW_THRESHOLD'      # 9 flats + 1 shop is 9 dwellings, not 10 units
    assert ten['proposed_total']==10 and ten['non_residential_units']=={'retail':2} and ten['admission']=='ADMIT_SCHEME'
    assert by_id['E23']['expected']['non_residential_units']=={'retail':3} and by_id['E23']['expected']['proposed_total']==NONE


def test_net_and_loss_are_defined_by_the_examples():
    by_id={e['id']:e['expected'] for e in EXAMPLES}
    assert (by_id['E14']['lost'],by_id['E14']['net'])==(14,-2)      # demolished
    assert (by_id['E17']['lost'],by_id['E17']['net'])==(12,-12)      # converted away (change of use away from housing)
    assert (by_id['E47']['lost'],by_id['E47']['net'])==(12,-6)      # reconfigured: 12 flats become 6
    assert (by_id['E19']['lost'],by_id['E19']['net'])==(12,12)      # converted into 24: the 12 are lost as those dwellings, all 24 are the output
    assert (by_id['E16']['lost'],by_id['E16']['net'])==(NE,NE)      # "the existing bungalow" states no number: nothing is inferred


def live(e):
    t=e['proposal'];q=qualify(t)
    row=dict(reference='T/1',fields={'proposal':dict(state=e['proposal_state'],value=t,locator='x',truncated=False),'address':dict(state='PRESENT_VALUE',value='1 Test Street',locator='x',truncated=False),
                                     'application_type':dict(state='UNKNOWN',value=None,locator='x',truncated=False)})
    return dict(qualify_unit_count=q.unit_count,qualify_category=q.category,qualify_classification=q.classification,legacy_admits=bool(q.qualifies),screen_v1_disposition=ls.screen_row(row)['disposition'])


def test_the_recorded_baseline_equals_the_live_behaviour_of_the_current_implementation():
    drift={e['id'] for e in EXAMPLES if live(e)!=e['baseline_current']}
    assert drift==set()      # refresh the JSON baseline (and review the gap lists) if this ever moves; v1 itself must not


def test_the_documented_gap_lists_equal_the_live_gaps():
    plain=[e for e in EXAMPLES if 'records' not in e]
    def wants_admission(e):return e['expected']['admission'] in ('ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT')
    def not_scheme(e):return e['expected']['admission'] not in ('ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','ROUTE_COUNT_UNCONFIRMED')
    fn={e['id'] for e in plain if wants_admission(e) and not live(e)['legacy_admits']}
    fp={e['id'] for e in plain if not_scheme(e) and live(e)['legacy_admits']}
    def want(e):
        p=e['expected']['proposed_total'];return p if isinstance(p,int) else (int(p.split(':')[1]) if isinstance(p,str) and p.startswith('UP_TO:') else None)
    cg={e['id'] for e in plain if (live(e)['qualify_unit_count']!=want(e) if want(e) is not None else live(e)['qualify_unit_count'] is not None)}
    assert (fn,fp,cg)==(LEGACY_FALSE_NEGATIVES,LEGACY_FALSE_POSITIVES,LEGACY_COUNT_GAPS)
    assert {e['id'] for e in EXAMPLES if 'records' in e}==EVIDENCE_MODEL_EXAMPLES      # these cannot be conformant until the single scalar is replaced as the source of truth


def test_historical_screening_results_are_untouched_by_this_specification():
    assert ls.screen_row({'reference':'T/1','fields':{'proposal':{'state':'PRESENT_VALUE','value':'ERECTION OF 12 DWELLINGS','locator':'x','truncated':False},'address':{'state':'UNKNOWN','value':None,'locator':'x','truncated':False},
                                                     'application_type':{'state':'UNKNOWN','value':None,'locator':'x','truncated':False}}})['rule_version']=='manchester-listing-screen-assessment-v1'
