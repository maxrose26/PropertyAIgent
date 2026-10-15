"""Offline reconciliation of the two consumed artifacts; no network/DB imports."""
import csv,hashlib,json,re
from pathlib import Path
from datetime import datetime,date
from collections import Counter
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
SHA='77356e04ef855f7373b96b9210f593e9b96c897c'
SPECS={'fixed80':(38758282951,'1c4cb696cfd352532a0c19fe9e919e86059908cc3cf21ed37f8be2ec8ab23b12','4efd1716953bca638e84ad65481fc4c21c890aac6d30425d2a75b36e224b8d8f'),
'untouched27':(38758465439,'f99d86a5deb251f45c0787af295836aa948d8250d9f7b180062db229c6dc0e3d','19279ea9886b950f3b90b6f85a12d26d3a1c03477d621710736177181f212526')}
def read(p):return json.loads(p.read_bytes())
def write(name,x): (ROOT/name).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def fingerprint(p):return hashlib.sha256(p.read_bytes()).hexdigest()
validation={}
for scope,(run,manifest,ziphash) in SPECS.items():
 p=ROOT/scope/'extracted';m=read(p/'execution.json');r=read(p/'result.json')
 assert fingerprint(ROOT/scope/'artifact.zip')==ziphash
 assert m['sha']==SHA and m['manifest_sha256']==manifest and m['run_id']==str(run)
 assert m['run_number']==m['attempt']==1 and m['persistence'] is False
 files=list(p.rglob('*.json'));total=sum(x.stat().st_size for x in files)
 assert total==m['aggregate_audit_bytes']
 checkpoints=sorted((p/'checkpoints').glob('*.json'))
 assert len(checkpoints)==len(r['results'])==len(r['checkpoint_sha256'])
 for i,path in enumerate(checkpoints):
  assert path.name==f'{i:03}.json' and fingerprint(path)==r['checkpoint_sha256'][i]
  assert read(path)==r['results'][i]
 assert sum(x.stat().st_size for x in checkpoints)==r['checkpoint_bytes']
 assert r['outer_supervisor']['cleanup']=='CLOSED' and r['outer_supervisor']['live_owned_survivors']==0
 assert r['outer_supervisor']['limit_hit'] is None and r['accounting_complete'] is True
 assert all(m[k]==0 for k in ['production_database_connections','production_reads','production_writes'])
 validation[scope]={'run':run,'zip_sha256':ziphash,'expanded_bytes':total,'checkpoints':len(checkpoints),'checkpoint_bytes':r['checkpoint_bytes'],'result_sha256':fingerprint(p/'result.json'),'execution_sha256':fingerprint(p/'execution.json'),'run_revision_manifest_verified':True,'all_checkpoint_hashes_and_values_verified':True,'resources':{k:r.get(k) for k in ['requests','received_bytes','bytes','elapsed_seconds','outer_supervisor']},'no_database_access':True,'authority':'CONSUMED'}
write('artifact-validation.json',validation)
manifest=read(BASE/'page-cap-correction/fixed80-qualification-manifest.json')
r=read(ROOT/'fixed80/extracted/result.json');observed={(x['council'],x['reference']):x for x in r['results']}
qual=[]
for row in manifest['rows']:
 o=observed.get((row['council'],row['reference']))
 qual.append(dict(council=row['council'],reference=row['reference'],source_window=row['source_window'],
   outcome='NOT_ATTEMPTED' if o is None else 'WITHHELD_PARSER_FAILURE' if o['failure'] else 'WITHHELD_B2_INELIGIBLE',
   snapshot_absence_at=manifest['absence_timestamp'],current_database_comparison='NOT_AUTHORISED_NOT_PERFORMED',
   identity='NOT_ATTEMPTED' if o is None else o['identity_qualification'],
   observation_evidence=None if o is None else o['observation_evidence'],
   conservative_materiality=row['retained_materiality'],site_relationship='UNKNOWN',application_role='UNKNOWN',
   admission_ready=False,admission_authorised=False,excluded=False))
assert len(qual)==80 and sum(x['outcome']=='NOT_ATTEMPTED' for x in qual)==37
write('qualification-all80.json',qual)
with (ROOT/'qualification-all80.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['council','reference','outcome','identity','b2_eligible','verification_scope','supported_status','materiality','site_relationship','application_role','admission_ready'])
 for x in qual:
  e=x['observation_evidence'] or {};w.writerow([x['council'],x['reference'],x['outcome'],x['identity'],e.get('b2_eligible','NOT_ATTEMPTED'),e.get('verification_scope','NOT_ATTEMPTED'),e.get('supported_literal_facts',{}).get('Status',''),x['conservative_materiality']['outcome'],'UNKNOWN','UNKNOWN',False])
# Retained seals are immutable. No fresh denominator or reconstructed set.
prior=BASE/'two-scope-execution-20261015/independent'
ledgers=[read(prior/x) for x in ['ledger.json','append-ledger.json']]
assert fingerprint(prior/'ledger.json')=='715da66d96a643800c7a30df9ae88481e7fc2576d89fc55a4ec93484a2049f17'
assert fingerprint(prior/'append-ledger.json')=='7a46aa77843e85b226f1f1a0982feff79a2d111a4a93596a37ad953a0c7ceb23'
ind={(x['council'],x['start'],x['end']):x for l in ledgers for x in l['rows']}
plan=read(BASE/'page-cap-correction/untouched27-manifest.json');r=read(ROOT/'untouched27/extracted/result.json')
obs={(x['window']['council'],x['window']['start'],x['window']['end']):x for x in r['results']}
windows=[];candidates=[]
for row in plan['rows']:
 key=(row['council'],row['start'],row['end']);o=obs.get(key);a={} if o is None else o['source'];ret=ind.get(key,{})
 records=a.get('listing_records',a.get('records',[]));refs={x['reference'] for x in records};irefs=set(ret.get('references',[]));complete=ret.get('status')=='COMPLETE'
 windows.append(dict(window=row,primary_enumeration='NOT_ATTEMPTED' if o is None else o['enumeration_completeness'],coverage='UNKNOWN' if o is None else o['completeness'],safe_local_gap=False if o is None else o['safe_local_gap'],references=len(refs),source_reported_total=(a.get('listing_segments') or a.get('pages') or [{}])[-1].get('total'),reason=a.get('failure',a.get('enumeration_evidence')),primary_observation=a.get('primary_observation'),independent_status=ret.get('status','UNKNOWN'),usable_independent_denominator=complete,independent_references=len(irefs),comparison='UNAVAILABLE_PRIMARY' if o is None else 'UNAVAILABLE_PRIMARY_QUALIFICATION' if o['enumeration_completeness']=='FAILED' else 'IDENTITY_SETS_MATCH_ACROSS_OBSERVATIONS' if complete and refs==irefs else 'UNRESOLVED_DIFFERENCE' if complete else 'UNAVAILABLE_INDEPENDENT_DENOMINATOR',independent_only_observed=sorted(irefs-refs) if o else [],primary_only_observed=sorted(refs-irefs) if o and complete else [],observed_retained_partial_subset=(irefs<=refs) if o and irefs and not complete else None,source_change_uncertainty=True,parser_miss_claimed=False))
 for record in records:
  arc=row['semantics']=='VALIDATED' and row['council']=='manchester'
  field=record.get('validated_date') if arc else record.get('fields',{}).get('received_date',{})
  literal=(field or {}).get('literal' if arc else 'value');d=None
  if (field or {}).get('state')=='PRESENT_VALUE' and literal:
   try:d=datetime.strptime(literal,'%d/%m/%Y' if arc else '%a %d %b %Y').date()
   except ValueError:pass
  membership='UNKNOWN_DATE' if d is None else 'IN_TARGET' if date(2026,9,29)<=d<=date(2026,10,14) else 'OVERLAP_CONTEXT' if date(2026,9,17)<=d<date(2026,9,29) else 'OUTSIDE_REQUESTED_OBSERVATION'
  candidates.append(dict(council=row['council'],reference=record['reference'],source_record_id=record.get('source_record_id',record.get('source_key')),official_source=record['source_url'],source_run=38758465439,source_revision=SHA,window=row,date_semantics=row['semantics'],source_date_literal=literal,source_date_state=(field or {}).get('state','UNKNOWN'),suspension_target_membership=membership,first_primary_observed_at=a['primary_observation']['started_at'],primary_enumeration=o['enumeration_completeness'],exact_record_identity='NOT_QUALIFIED',materiality='POTENTIALLY_MATERIAL_REQUIRES_QUALIFICATION',site_relationship='UNKNOWN',application_role='UNKNOWN',database_comparison='NOT_AUTHORISED_NOT_PERFORMED',admission='NOT_AUTHORISED_NOT_ATTEMPTED',provenance_sha256=[x['evidence_sha256'] for x in a.get('provenance',[]) if 'evidence_sha256' in x]+[x.get('evidence_sha256',x.get('body_sha256')) for x in a.get('listing_segments',a.get('pages',[]))]))
assert len(windows)==27 and len(candidates)==206 and len({(x['council'],x['reference']) for x in candidates})==206
write('all27-window-reconciliation.json',windows);write('new-primary-candidate-ledger.json',candidates)
# Proposed comparison only; does not expand or execute consumed fixed80 query.
newcomparison=[dict(council=x['council'],reference=x['reference']) for x in candidates if x['suspension_target_membership'] in {'IN_TARGET','UNKNOWN_DATE'}]
write('proposed-additional-identity-comparison.json',dict(purpose='REVIEW_ONLY_NO_DATABASE_AUTHORITY',source_run=38758465439,identities=newcomparison,current_duplicate_protection_required_at_future_admission=True,query_fields=['id','council_code','reference'],per_identity_limit=2,read_only=True))
summary=dict(fixed80_outcomes=dict(Counter(x['outcome'] for x in qual)),eligible_admission_cohort=[],exclusions=0,
 primary_windows=dict(Counter(x['primary_enumeration'] for x in windows)),primary_candidates=len(candidates),candidate_membership=dict(Counter(x['suspension_target_membership'] for x in candidates)),candidate_councils=dict(Counter(x['council'] for x in candidates)),independent_usable=12,independent_unavailable=15,identity_set_matches=sum(x['comparison']=='IDENTITY_SETS_MATCH_ACROSS_OBSERVATIONS' for x in windows),unresolved_differences=sum(x['comparison']=='UNRESOLVED_DIFFERENCE' for x in windows),proposed_new_comparison=len(newcomparison),parent_r0='INCOMPLETE',database_catchup='INCOMPLETE',publication_recall='UNKNOWN',latency='UNKNOWN',bridge_start='2026-10-15',no_new_independent_observation=True)
write('reconciliation-summary.json',summary)
print(json.dumps(summary,indent=2))
