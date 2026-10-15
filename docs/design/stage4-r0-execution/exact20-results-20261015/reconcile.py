"""Offline exact20 artifact and retained-seal reconciliation; no source/DB access."""
import hashlib,json,zipfile
from pathlib import Path
from datetime import datetime,date
from collections import Counter
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
SHA='0eec734da0cc1a7580385003a7dc9ed797f74bd2'
def read(p):return json.loads(p.read_bytes())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,d):(ROOT/n).write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
assert digest(ROOT/'artifact-11997283579.zip')=='24c6fcf10ef3d6eaafffc29dea6b36043bb604b2242c45ba1c5bd1673f59869c'
if not (ROOT/'artifact').is_dir():
 with zipfile.ZipFile(ROOT/'artifact-11997283579.zip') as z:
  expected={'execution.json','result.json'}|{f'checkpoints/{i:03}.json' for i in range(4)}
  assert set(z.namelist())==expected and sum(x.file_size for x in z.infolist())<20_000_000
  z.extractall(ROOT/'artifact')
r=read(ROOT/'artifact/result.json');m=read(ROOT/'artifact/execution.json')
assert m['sha']==SHA and m['run_id']=='38786550045' and m['run_number']==m['attempt']==1
assert m['manifest_sha256']=='7c46a54e91201ba2cff1b392e4d606f592f79a8752827e3536135bfb3912e66c'
assert m['workflow_sha256']=='0a6a9a647663fa17ef0bd3ada628633f398142003819d53952e1d2db3b3aef66'
assert all(m[x]==0 for x in ['production_database_connections','production_reads','production_writes'])
assert sum(p.stat().st_size for p in (ROOT/'artifact').rglob('*') if p.is_file())==m['aggregate_audit_bytes']
checkpoints=sorted((ROOT/'artifact/checkpoints').glob('*.json'))
assert len(checkpoints)==len(r['results'])==len(r['checkpoint_sha256'])==4
for i,p in enumerate(checkpoints):assert digest(p)==r['checkpoint_sha256'][i] and read(p)==r['results'][i]
assert sum(p.stat().st_size for p in checkpoints)==r['checkpoint_bytes']
seals=[('ledger.json','715da66d96a643800c7a30df9ae88481e7fc2576d89fc55a4ec93484a2049f17'),('append-ledger.json','7a46aa77843e85b226f1f1a0982feff79a2d111a4a93596a37ad953a0c7ceb23')]
ind={}
for name,sha in seals:
 p=ROOT/'retained-independent'/name;assert digest(p)==sha
 for x in read(p)['rows']:ind[(x['council'],x['start'],x['end'])]=x
manifest=read(BASE/'initial-application-preparation/primary-unattempted20.json')
obs={(x['window']['council'],x['window']['start'],x['window']['end']):x for x in r['results']}
windows=[];candidates=[]
for row in manifest['rows']:
 key=(row['council'],row['start'],row['end']);o=obs.get(key);s=o['source'] if o else {};ret=ind.get(key,{})
 records=s.get('listing_records',[]);refs={x['reference'] for x in records};irefs=set(ret.get('references',[]));usable=ret.get('status')=='COMPLETE'
 comparison='UNAVAILABLE_PRIMARY' if o is None else 'UNAVAILABLE_PRIMARY_QUALIFICATION' if o['enumeration_completeness']=='FAILED' else 'IDENTITY_SETS_MATCH_ACROSS_OBSERVATIONS' if usable and refs==irefs else 'UNRESOLVED_DIFFERENCE' if usable else 'UNAVAILABLE_INDEPENDENT_DENOMINATOR'
 windows.append(dict(window=row,primary_enumeration='NOT_ATTEMPTED' if not o else o['enumeration_completeness'],coverage='UNKNOWN' if not o else o['completeness'],reference_count=len(refs),listing_segments=s.get('listing_segments',[]),failure=s.get('failure'),listing_stage=s.get('listing_stage'),requested_interval=s.get('requested_interval'),applied_interval=s.get('applied_interval'),primary_observation=s.get('primary_observation'),retained_independent_status=ret.get('status','UNKNOWN'),usable_independent_denominator=usable,independent_references=len(irefs),independent_observation={k:v for k,v in ret.items() if k in {'observed_started_at','observed_ended_at','assessor','assessor_session','primary_session','tab_id'}},comparison=comparison,primary_only=sorted(refs-irefs) if usable and o else [],independent_only=sorted(irefs-refs) if usable and o else [],source_change_uncertainty=True,parser_miss_claimed=False))
 for record in records:
  f=record.get('validated_date',{});literal=f.get('literal');d=None
  if f.get('state')=='PRESENT_VALUE':
   try:d=datetime.strptime(literal,'%d/%m/%Y').date()
   except (TypeError,ValueError):pass
  membership='UNKNOWN_DATE' if d is None else 'IN_TARGET' if date(2026,9,29)<=d<=date(2026,10,14) else 'OVERLAP_CONTEXT' if date(2026,9,17)<=d<date(2026,9,29) else 'OUTSIDE_OBSERVATION'
  candidates.append(dict(council=row['council'],reference=record['reference'],source_record_id=record['source_record_id'],source_url=record['source_url'],source_run=38786550045,revision=SHA,window=row,source_date_semantics='VALIDATED',source_date_state=f.get('state','UNKNOWN'),source_date_literal=literal,suspension_target_membership=membership,primary_observation=s['primary_observation'],exact_detection_timestamp='UNKNOWN_WITHIN_RECORDED_OBSERVATION_INTERVAL',provenance=[p['evidence_sha256'] for p in s['listing_segments']],exact_record_identity='NOT_QUALIFIED',materiality='POTENTIALLY_MATERIAL_REQUIRES_QUALIFICATION',site_relationship='UNKNOWN',application_role='UNKNOWN',database_presence='UNKNOWN_NOT_QUERIED',admission='NOT_AUTHORISED_NOT_ATTEMPTED'))
assert len(windows)==20 and len(candidates)==len({(x['council'],x['reference']) for x in candidates})==46
assert sum(x['usable_independent_denominator'] for x in windows)==8
summary=dict(run=38786550045,revision=SHA,run_number=1,attempt=1,authority='CONSUMED',artifact=11997283579,zip_sha256=digest(ROOT/'artifact-11997283579.zip'),result_sha256=digest(ROOT/'artifact/result.json'),execution_sha256=digest(ROOT/'artifact/execution.json'),all_checkpoint_hashes_verified=True,window_states=dict(Counter(x['primary_enumeration'] for x in windows)),coverage='INCOMPLETE',candidates=len(candidates),candidate_membership=dict(Counter(x['suspension_target_membership'] for x in candidates)),independent_available=8,independent_unavailable=12,identity_set_matches=sum(x['comparison']=='IDENTITY_SETS_MATCH_ACROSS_OBSERVATIONS' for x in windows),unresolved_differences=sum(x['comparison']=='UNRESOLVED_DIFFERENCE' for x in windows),stop_reason=r['stop_reason'],resources={k:r.get(k) for k in ['requests','bytes','checkpoint_bytes','accounting_complete','outer_supervisor']},aggregate_audit_bytes=m['aggregate_audit_bytes'],no_database_access=True,completed_through_advanced=False,publication_recall='UNKNOWN',latency='UNKNOWN',bridge_start='2026-10-15')
write('all20-window-reconciliation.json',windows);write('candidate-ledger.json',candidates);write('reconciliation-summary.json',summary)
write('proposed-new-identity-comparison.json',dict(purpose='REVIEW_ONLY_NO_QUERY_AUTHORITY',source_run=38786550045,identities=[dict(council=x['council'],reference=x['reference']) for x in candidates if x['suspension_target_membership']=='IN_TARGET'],existing147_proposal_unchanged=True))
print(json.dumps(summary,indent=2))
