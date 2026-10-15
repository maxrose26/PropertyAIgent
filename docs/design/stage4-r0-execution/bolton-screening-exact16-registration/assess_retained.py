"""Manual review ledger plus existing accepted rule output; no new runtime filter.

Reads frozen retained evidence only. Explicit notes are a bounded53record review,
not a general materiality taxonomy or an admission/deep-extraction command.
"""
from pathlib import Path
from dataclasses import asdict
import csv,hashlib,json,re
from collections import Counter
from verification.discovery.bolton53_admission import rows,PACK,COHORT_SHA,PRIMARY_SHA
from app.scrapers import unit_filter
ROOT=Path(__file__).resolve().parent
NOTES={
'01780/26':'First-floor extension/garage conversion/outbuilding/garden room; no new material dwelling scheme stated.',
'01778/26':'Pruning named trees; no material development or parent scheme stated.',
'01776/26':'External alterations cite prior approval00031/26; underlying use/scale and material effect unknown; retain related evidence.',
'01775/26':'Pruning/felling named trees; no material development or parent scheme stated.',
'01769/26':'Fenestration/dormer amendment affects many numbered plots across phases1E/2; credible larger-scheme relationship; parent00284/26 unqualified.',
'01768/26':'Explicit49self-contained C3apartments in4blocks; supported material residential scale. Ownership, availability and buyer relevance unproven.',
'01821/26':'Two battery-storage units, not two homes; positive non-residential evidence supports existing deeper-extraction exclusion only.',
'01816/26':'Pruning one silver birch; no material development or parent scheme stated.',
'01815/26':'Amendment to window/firedoor/rooflight/cladding cites20610/25; parent scale/use and material effect unknown; retain.',
'01813/26':'Biodiversity/materials-management discharge cites17828/24; parent scale/use and delivery significance unknown; retain.',
'01811/26':'eCEMP/EcMP discharge cites91352/14; parent scale/use and delivery significance unknown; retain.',
'01810/26':'Garage-to-vehicle-repair/MOT workshop ClassB2; no residential development stated; legacy Ignore is not a proven site-relationship exclusion.',
'01809/26':'eCEMP/EcMP discharge cites91352/14; separate identity, same parent as01811/26; retain without duplicate-site inference.',
'01808/26':'Felling one hawthorn; no material development or parent scheme stated.',
'01807/26':'Pruning one lime; no material development or parent scheme stated.',
'01806/26':'Existing C3 dwelling to six-bedroom contractor/holiday accommodation; bedrooms are not six residential units. Wider relationship unknown.',
'01805/26':'Block-paved driveway installation; no material development or parent scheme stated.',
'01804/26':'Pruning one sycamore; no material development or parent scheme stated.',
'01801/26':'Extensions/outbuilding/garage alterations; no new material dwelling scheme stated.',
'01800/26':'Single-storey rear extension; no new material dwelling scheme stated.',
'01799/26':'One waiting-room enclosure; no residential development or parent scheme stated.',
'01797/26':'One air-handling unit, not one dwelling. Existing generic-unit count is not a valid residential-scale exclusion; no material housing stated.',
'01796/26':'Pruning elm/sycamore/lime; no material development or parent scheme stated.',
'01795/26':'Felling one horse chestnut; no material development or parent scheme stated.',
'01794/26':'Hanging signs, one illuminated; no material residential development stated.',
'01793/26':'Larger-home-extension notification with dimensions; no new dwelling count or material scheme stated.',
'01791/26':'Lawfulness certificate for rear dormer; no material residential scheme stated. Actual application-type field unobserved.',
'01790/26':'Replacement illuminated hoarding; no material residential development stated.',
'01789/26':'Rear extension and hip-to-gable conversion; no new material dwelling scheme stated.',
'01787/26':'Existing dwelling to C3bcare for six young persons; six persons are not six new units. Certificate/relationship evidence must not be invented.',
'01786/26':'Felling one cypress; no material development or parent scheme stated.',
'01785/26':'Seven-bedroom B&B with dormers/terrace; seven bedrooms are not seven residential units. No material housing stated.',
'01784/26':'Fence/gates/footpath diversion at LeaFieldWay may be access-related; underlying development relationship unavailable; retain uncertainty.',
'01783/26':'Larger-home-extension notification with dimensions; no new material dwelling scheme stated.',
'01782/26':'Industrial-unit demolition/storage/offices/training/carpark;78is parking spaces, not homes. No residential development stated.',
'01858/26/PREMIN':'Proposal explicitly demolition/erection of one dwelling; existing under10residential-unit rule supports deeper-extraction exclusion only; not excluded by prefix.',
'01852/26':'Felling/pruning beech trees; no material development or parent scheme stated.',
'01851/26':'Listed-building structural repairs/windows/insulation/rewiring/boiler; building scale and relationship absent, no new housing stated.',
'01848/26':'Lawfulness certificate for fenestration/porch; no new material dwelling scheme stated.',
'01847/26':'Biodiversity/land/landscape/materials condition discharge cites19527/24; parent scale/use and delivery significance unknown; retain.',
'01845/26':'Watermains/drainage/HMMP discharge cites20163/25; parent scale/use and delivery significance unknown; retain.',
'01843/26':'Rear extension/dormer/raised roof; no new material dwelling scheme stated.',
'01841/26':'Side/rear extension; no new material dwelling scheme stated.',
'01840/26':'Pruning one beech; no material development or parent scheme stated.',
'01839/26':'Additional single-operator taxi-base use of existing C3 property for one vehicle; vehicle count is not housing scale.',
'01838/26':'Front dormer; no new material dwelling scheme stated.',
'01836/26':'Felling one holly; no material development or parent scheme stated.',
'01833/26':'Rear extension/carport-to-garage; no new material dwelling scheme stated.',
'01832/26':'Front porch; no new material dwelling scheme stated.',
'01827/26':'Variation changes ground levels/internal road/siting plots18–32/boundaries plots2–14/drainage; credible larger-development relationship; parent20683/25 unqualified.',
'01826/26':'Additional taxi-base use of existing C3 property for1–2vehicles; vehicle count is not residential scale.',
'01825/26':'High-hedge complaint; no material residential development or parent scheme stated.',
'01823/26':'Pruning one oak; no material development or parent scheme stated.'}
EXCLUSION={'01821/26':'Existing qualify: Excluded - non-residential; proposal battery-storage units, no residential signal.',
'01858/26/PREMIN':'Existing qualify: Ignore - under10units; explicit one dwelling, not reference-prefix inference.'}

def build():
    inputs=list(rows());assert set(NOTES)=={r['reference'] for r in inputs} and len(inputs)==53
    out=[]
    for r in inputs:
        f=r['source_record']['fields'];proposal=f['proposal'];address=f['address'];q=asdict(unit_filter.qualify(proposal['value']))
        parents=re.findall(r'(?<!\d)\d{5}/\d{2}(?!\d)',proposal['value'])
        field_provenance=dict(source_url=r['source_url'],window_run=r['window_run'],interval=r['source_window'],
            observed_at=r['discovered_at'],page_body_sha256=[x['body_sha256'] for x in r['window_evidence']['pages']],primary_evidence_sha256=PRIMARY_SHA)
        primary=r['reference']=='01768/26';linked=r['reference'] in {'01769/26','01827/26'}
        out.append(dict(council='bolton',reference=r['reference'],proposal=proposal,address=address,
            application_type={'state':'UNKNOWN','reason':'Not captured in retained listing or INITIAL_STATUS_ONLY observation; do not infer structured type from wording.'},
            scale_indicator={'literal_context':proposal['value'],'legacy_extracted_generic_count':q['unit_count'],
                'supported_residential_units':49 if primary else 1 if r['reference']=='01858/26/PREMIN' else None,
                'warning':'Generic count is not verified residential scale; bedrooms/people/AHU/storage/parking/plot numbers are distinct.'},
            explicit_related_references=sorted(set(parents)),related_reference_provenance='Explicit proposal literal only; no parent lookup or site identity established.',
            legacy_rule_result=q,plausible_acquisition_relevance=NOTES[r['reference']],
            clear_deeper_processing_exclusion=EXCLUSION.get(r['reference']),
            exclusion_applied_to_discovery_or_identity=False,relationship_state='UNKNOWN',
            specific_missing_evidence='Parent use/scale, exact related application/site evidence and material effect.' if parents else 'Structured application type and any supported relationship to a material scheme; ownership/availability/buyer fit unassessed.',
            recommended_processing='Prioritise supported49apartment scheme for REVIEW.' if primary else 'Prioritise relationship-aware qualification, not automatic exclusion.' if linked else 'Hold related record for parent/scale qualification; no automatic admin exclusion.' if parents else 'No deeper extraction justified by current proposal; retain identity/evidence and uncertainty.',
            provenance=field_provenance))
    return dict(cohort_sha256=COHORT_SHA,primary_evidence_sha256=PRIMARY_SHA,
        accepted_rule_source='app/scrapers/unit_filter.py:qualify',accepted_rule_sha256=hashlib.sha256(Path(unit_filter.__file__).read_bytes()).hexdigest(),
        discovery_override_source='app/pipeline/discovery_contract.py:candidate_materiality',
        field_availability=dict(proposal_present=53,address_present=53,structured_application_type_unknown=53,
            explicit_parent_records=sum(bool(x['explicit_related_references']) for x in out),unique_explicit_parent_refs=len(set(y for x in out for y in x['explicit_related_references'])),
            supported49apartment_record=1),legacy_counts=dict(Counter(x['legacy_rule_result']['classification'] for x in out)),
        manual_assessment_only=True,screening_policy_changed=False,source_requests=0,production_access=False,rows=out)

if __name__=='__main__':
    data=build();(ROOT/'bolton53-screening.json').write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
    with (ROOT/'bolton53-screening.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['reference','proposal','address','legacy_rule','legacy_generic_count','explicit_parent_refs','assessment','specific_missing_evidence','clear_deeper_processing_exclusion','recommended_processing'])
        for r in data['rows']:w.writerow([r['reference'],r['proposal']['value'],r['address']['value'],r['legacy_rule_result']['classification'],r['legacy_rule_result']['unit_count'],';'.join(r['explicit_related_references']),r['plausible_acquisition_relevance'],r['specific_missing_evidence'],r['clear_deeper_processing_exclusion'],r['recommended_processing']])
    print(json.dumps({k:v for k,v in data.items() if k!='rows'},indent=2))
