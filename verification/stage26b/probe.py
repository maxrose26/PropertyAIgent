"""Offline, fixed subject-universe differential; never a production forecast."""
import dataclasses
import json
from pathlib import Path
import sys
sys.path.insert(0,sys.argv[1])
from app.db.models import Application, SchemeIntelligence
from app.reporting.scheme_reconciliation import build_operative_planning_facts, count_assessment_for_facts
from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative, assess_buyer_fit, B2MatchingContext
from app.policy.buyer_profiles import BUYER_PROFILES
from app.reporting.opportunity_families import FamilySubject, group_into_families
from app.reporting.opportunity_universe import compute_opportunity_fingerprint
from app.reporting.mandate_explanation import present_mandate_explanation
from app.reporting.residential_mix import compute_affordable_headline,build_affordable_tenure
cases=json.loads(Path(sys.argv[2]).read_text())
out={'scope':'Nine current-public-proposal/stored-SI wrappers; fixed synthetic lifecycle subjects. Not a replay of stored proposals or full production family universe.','cases':{},'families':{}}
subjects={k:[] for k in BUYER_PROFILES}
for case in cases:
    a=Application(id=case['application_id'],site_id=case['site_id'],council_code='stockport',reference=case['reference'],
        proposal=case['proposal_from_current_source'],status=case['stored_status'],decision=case['stored_decision'],
        decision_issued_date=case['stored_decision_date'],application_received='2025-01-01',estimated_unit_count=case['stored_total'])
    a.scheme_intelligence=SchemeIntelligence(total_units_final=case['stored_total'],development_type=case['stored_development_type'],
        housing_typology=case['stored_housing_typology'],**{k:v for k,v in case['stored_ah'].items() if hasattr(SchemeIntelligence,k)})
    operative=build_operative_planning_facts([a]); count=count_assessment_for_facts(operative)
    facts=build_planning_delivery_matching_facts_from_operative(operative,[a],application_reference=a.reference)
    # Exact existing fingerprint algorithm applied to the changed relevant field subset;
    # this is explicitly not the complete production fingerprint payload.
    fp={'unit_count':facts.unit_count,'affordable_unit_count':facts.affordable_unit_count,'development_type_raw':facts.development_type_raw,
        'is_specialist_development':facts.is_specialist_development,'count_assessment':count.fingerprint()}
    key=f'planning_delivery:site:{a.site_id}'
    ah=compute_affordable_headline(a.scheme_intelligence)
    record={'ah_headline':ah,'ah_tenure':build_affordable_tenure(a.scheme_intelligence,ah),'subject':key,'reference':a.reference,'raw_scale':case['stored_total'],'qualified_scale':count.fingerprint(),
        'fingerprint_fields_subset':fp,'fingerprint_subset_hash':compute_opportunity_fingerprint(fp),'buyers':{}}
    for bk,buyer in BUYER_PROFILES.items():
        result=assess_buyer_fit(buyer,facts,B2MatchingContext(council_code='stockport'))
        record['buyers'][bk]={'assessment':dataclasses.asdict(result),'explanation':dataclasses.asdict(present_mandate_explanation(result))}
        subjects[bk].append(FamilySubject('planning_delivery',a.site_id,key,'LIFECYCLE',result.classification,result.is_investigative_exception,count.precision))
    out['cases'][str(a.site_id)]=record
for bk,sub in subjects.items():
    out['families'][bk]=[{'family':f.family_key,'representative':f.representative.subject_key,'members':[m.subject_key for m in f.members],
                         'excluded':f.is_terminally_excluded} for f in group_into_families(sub)]
print(json.dumps(out,sort_keys=True))
