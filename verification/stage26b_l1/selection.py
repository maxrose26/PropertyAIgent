"""Offline role/selection manifest. No DB, evaluator, model or HTTP execution."""
from collections import Counter
import datetime as dt
from app.config import load_councils
from app.pipeline.material_change import _classify_planning_state
from verification.stage26b_l0.dependencies import DIRECT, priority_key
VERSION='stage26b-l1-selection-v1'
ROLE={'planning_status':'PLANNING_STATUS','decision':'PLANNING_DECISION','decision_issued_date':'DECISION_DATE','qualified_residential_scale':'RESIDENTIAL_SCALE','affordable_housing':'AFFORDABLE_HOUSING','commencement':'COMMENCEMENT_OR_DEADLINE','deadline':'COMMENCEMENT_OR_DEADLINE','opportunity_signal':'OTHER_DIRECT_FACT','development_type':'OTHER_DIRECT_FACT','specialist_development':'OTHER_DIRECT_FACT'}
REVIEW_IDS={23,63,96,123,142,294,328,961,962,1433}
def build(retained, current):
 if current.get('retrieval_state')!='COMPLETE' or current.get('dependency_census_state')!='QUALIFIED':raise ValueError('Unqualified input')
 data=current['data'];apps={a['id']:a for a in data['applications']}
 if len(apps)!=len(data['applications']):raise ValueError('Duplicate application')
 councils=load_councils(); risks={a['application_id']:a for a in retained['risk_cohorts']};direct=[e for e in retained['dependencies'] if e['dependency_type']==DIRECT]
 ids={e['application_id'] for e in direct};status_ids={e['application_id'] for e in direct if 'planning_status' in e['supported_fields']}
 if len(ids)!=234 or len(status_ids)!=211:raise ValueError('Accepted basis changed')
 classifications=[];queue=[]
 at=dt.datetime.fromisoformat(current['capture']['captured_at'])
 for aid in sorted(ids):
  edges=[e for e in direct if e['application_id']==aid];a=apps.get(aid)
  if not a or any((e['reference'],e['site_id'],e['council'])!=(a['reference'],a['site_id'],a['council_code']) for e in edges):raise ValueError('Exact identity mismatch')
  fields=sorted({f for e in edges for f in e['supported_fields']});roles=sorted({ROLE.get(f,'UNRESOLVED') for f in fields});isstatus=aid in status_ids
  classifications.append(dict(application_id=aid,reference=a['reference'],roles=roles,supported_fields=fields,disposition='A_STATUS' if isstatus else 'C_UNRESOLVED' if 'UNRESOLVED' in roles else 'B_OTHER_FACT_DEFERRED'))
  if not isstatus:continue
  council=councils.get(a['council_code']);verified=a.get('status_verified_at');risk=risks[aid]
  normalized=_classify_planning_state(a.get('decision'),a.get('status'))
  age=None if not verified else (at-dt.datetime.fromisoformat(verified)).total_seconds()/86400
  if age is not None and age<0:raise ValueError('Future successful verification')
  queue.append(dict(manifest_version=VERSION,site_id=a['site_id'],application_id=aid,council=a['council_code'],reference=a['reference'],stored_normalized_status=normalized,raw_status=a.get('status'),raw_decision=a.get('decision'),decision_date=a.get('decision_issued_date'),status_verified_at=verified,verification_age_days=age,verification_age_qualification='MISSING_UNKNOWN' if verified is None else 'VERIFIED_AS_OF_NOT_CURRENT_CERTIFICATION',dependency_roles=[r for r in roles if r in {'PLANNING_STATUS','PLANNING_DECISION','DECISION_DATE'}],cohort=risk['cohort'],reasons=risk['reasons'],source_adapter=None if council is None else 'arcus_portal' if council.doc_system=='arcus' else 'idox_portal',source_base_url=None if council is None else council.base_url,lookup_mode='EXACT_REFERENCE_NO_RELATED_DISCOVERY',consumers=sorted({c for e in edges if 'planning_status' in e['supported_fields'] for c in e['consumers']}),consumer_qualification='CANDIDATE_IMPACT_NOT_INVALIDATION_AUTHORITY',known_contradiction=aid==42,unresolved=['Retained commercial membership; not current evaluator certification'],selection_state='PROPOSED_NOT_LIVE_AUTHORITY'))
 queue.sort(key=priority_key)
 links=data['allocation_site_relationships'];review=[]
 for aid in sorted(REVIEW_IDS):
  a=apps[aid];rels=[l for l in links if l['site_id']==a['site_id']]
  review.append(dict(application_id=aid,reference=a['reference'],site_id=a['site_id'],relationships=[dict(id=l['id'],allocation_id=l['allocation_id'],review_status=l['review_status']) for l in sorted(rels,key=lambda z:z['id'])],disposition='CONTEXTUAL_ONLY_NO_ESTABLISHED_DIRECT_STATUS_SOURCE',direct_status_authority=False,request_eligible=False,qualification='Rejected links remain rejected; auto_applied is not human confirmation'))
 edge_subjects={e['subject_key'] for e in retained['dependencies']};unknown=[dict(subject_key=s['subject_key'],site_id=s['site_id'],reason='Exact status attribution not established',request_eligible=False) for s in retained['subjects'] if s['subject_key'] in edge_subjects and not s['status_sources']]
 return dict(version=VERSION,input_snapshot=current['capture']['snapshot'],observed_at=current['capture']['captured_at'],candidate_count=len(ids),status_manifest=queue,classifications=classifications,other_fact_dispositions=dict(Counter(c['disposition'] for c in classifications if c['application_id'] not in status_ids)),allocation_review=review,unresolved_attribution=unknown,council_counts=dict(sorted(Counter(r['council'] for r in queue).items())),cohort_counts=dict(sorted(Counter(r['cohort'] for r in queue).items())),completeness='QUALIFIED_RETAINED_BASIS',production_execution=False)
