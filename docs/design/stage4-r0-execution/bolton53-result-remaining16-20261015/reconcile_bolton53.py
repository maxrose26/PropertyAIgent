"""Offline consumed Bolton53 verification and proposals only; no network or DB."""
import csv,hashlib,json,re,zipfile
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
SHA='88ae288abf6e0e233502059cf3d74e1c9f6c929d'
def read(p):return json.loads(p.read_bytes())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,d):(ROOT/n).write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
assert digest(ROOT/'artifact-11999062153.zip')=='8f335c7fa7d9c6aeb96fddff67670aeb97760e649b3b5def8f580fe0e88938d1'
if not (ROOT/'artifact').is_dir():
 with zipfile.ZipFile(ROOT/'artifact-11999062153.zip') as z:
  assert set(z.namelist())=={'execution.json','result.json'}|{f'checkpoints/{i:03}.json' for i in range(53)}
  assert sum(x.file_size for x in z.infolist())<8_000_000
  z.extractall(ROOT/'artifact')
m=read(ROOT/'artifact/execution.json');r=read(ROOT/'artifact/result.json')
assert m['sha']==SHA and m['run_id']=='38789547636' and m['run_number']==m['attempt']==1
manifest=BASE/'bolton-initial-exact20/fresh-bolton53-proposal.json'
assert digest(manifest)==m['manifest_sha256']=='0857e43999b43a810f0206c839861eb6b71ccd6b57a83b5409a4ae01f4c40473'
assert m['workflow_sha256']=='e7b44f658ebdf408bf467258836b0cd5d13eb748a7237bb371c63a766f73190d'
assert all(m[k]==0 for k in ['production_database_connections','production_reads','production_writes'])
assert m['persistence'] is False and not r['persistence'] and not r['admission_authorised']
files=[p for p in (ROOT/'artifact').rglob('*') if p.is_file()]
assert sum(p.stat().st_size for p in files)==m['aggregate_audit_bytes']
assert len(r['results'])==r['attempted']==53 and not r['not_attempted'] and r['stop_reason'] is None
checkpoints=sorted((ROOT/'artifact/checkpoints').glob('*.json'));assert len(checkpoints)==53
for i,p in enumerate(checkpoints):assert digest(p)==r['checkpoint_sha256'][i] and read(p)==r['results'][i]
assert sum(p.stat().st_size for p in checkpoints)==r['checkpoint_bytes']
assert sum(x['source_audit']['requests'] for x in r['results'])==r['requests']==53
assert sum(x['source_audit']['received_body_bytes'] for x in r['results'])==r['received_bytes']==1850643
assert r['accounting_complete'] is True and r['outer_supervisor']['cleanup']=='CLOSED'
assert r['outer_supervisor']['limit_hit'] is None and r['outer_supervisor']['live_owned_survivors']==0
rows=read(manifest)['rows'];ledger=[];cohort=[]
for target,x in zip(rows,r['results']):
 e=x['observation_evidence'];a=x['source_audit']
 assert x['council']==target['council']=='bolton' and x['reference']==target['reference']
 assert x['source_url']==target['source_url'] and x['reference']!='01842/26'
 assert x['identity_qualification']==e['identity_qualification']=='EXACT_DISPLAYED_REFERENCE'
 assert e['displayed_reference']==e['requested_reference']==x['reference']
 assert e['verification_scope']=='INITIAL_STATUS_ONLY' and e['b2_eligible'] is True
 assert e['supported_literal_facts']=={'Reference':x['reference'],'Status':'Deposited'}
 assert e['field_states']==dict(reference='PRESENT_VALUE',status='PRESENT_VALUE',decision='NOT_PRESENT',decision_date='NOT_PRESENT')
 assert 'SOURCE_SEMANTIC_STATE_UNKNOWN_UNMAPPED' in e['diagnostic_conditions'] and e['rejection_reason'] is None
 assert re.fullmatch('[0-9a-f]{64}',e['body_sha256']) and e['body_sha256']==a['source_sha256']
 assert a['cleanup_state']=='CLOSED' and a['budget_state']=='WITHIN_LIMITS' and a['live_owned_survivors']==0
 assert x['site_relationship']==x['application_role']=='UNKNOWN' and x['failure'] is None
 assert x['conservative_materiality']['outcome']=='POTENTIALLY_MATERIAL' and x['admission_readiness']=='ELIGIBLE_FOR_REVIEW_ONLY'
 row=dict(x,cohort_origin=target['proposal_origin'],source_window=target['source_window'],semantic_interpretation='UNKNOWN_UNMAPPED',current_database_presence='UNKNOWN_NOT_QUERIED',production_admission='NOT_AUTHORISED_NOT_ATTEMPTED',commercial_relevance='UNPROVEN',decision_verified_at=None,decision_date_verified_at=None)
 ledger.append(row)
 cohort.append(dict(council='bolton',reference=x['reference'],source_identifier=target['source_identifier'],source_url=x['source_url'],platform_family=target['platform_family'],cohort_origin=target['proposal_origin'],source_window=target['source_window'],qualification_body_sha256=e['body_sha256'],qualification_scope=e['verification_scope'],qualification_at=x['retrieved_at'],site_relationship='UNKNOWN',application_role='UNKNOWN',materiality='POTENTIALLY_MATERIAL'))
assert len({x['reference'] for x in ledger})==53
write('all53-qualification-outcomes.json',ledger)
with (ROOT/'all53-qualification-outcomes.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['council','reference','origin','identity','scope','literal_status','semantic_interpretation','decision_state','decision_date_state','materiality','site_relationship','application_role','admission_readiness','database_presence'])
 for x in ledger:w.writerow(['bolton',x['reference'],x['cohort_origin'],x['identity_qualification'],'INITIAL_STATUS_ONLY','Deposited','UNKNOWN_UNMAPPED','NOT_PRESENT','NOT_PRESENT','POTENTIALLY_MATERIAL','UNKNOWN','UNKNOWN',x['admission_readiness'],'UNKNOWN_NOT_QUERIED'])
write('proposed-admission53-cohort.json',dict(version=1,purpose='REVIEW_ONLY_PRIMARY_DISCOVERY_PENDING_APPLICATION_ADMISSION',execution_authorised=False,registered=False,qualification_run=38789547636,qualification_revision=SHA,qualification_zip_sha256=digest(ROOT/'artifact-11999062153.zip'),qualification_result_sha256=digest(ROOT/'artifact/result.json'),current_absence_proven=False,automatic_current_duplicate_and_race_protection_required=True,fresh_evidence_required=True,qualification_replay_for_facts_forbidden=True,sites_links_opportunities_forbidden=True,rows=cohort))
summary=dict(run=38789547636,revision=SHA,run_number=1,attempt=1,authority='CONSUMED',artifact=11999062153,zip_sha256=digest(ROOT/'artifact-11999062153.zip'),result_sha256=digest(ROOT/'artifact/result.json'),execution_sha256=digest(ROOT/'artifact/execution.json'),all_53_checkpoints_verified=True,attempted=53,not_attempted=0,identity_qualified=53,source_b2_eligible=53,verification_scopes=dict(Counter(x['observation_evidence']['verification_scope'] for x in ledger)),literal_status_counts={'Deposited':53},materiality={'POTENTIALLY_MATERIAL':53},commercial_materiality_proven=0,excluded=0,withheld=0,application_role={'UNKNOWN':53},site_relationship={'UNKNOWN':53},proposed_admission_review_cohort=53,production_admission_authorised=False,production_connections=0,production_reads=0,production_writes=0,resources={k:r.get(k) for k in ['requests','received_bytes','elapsed_seconds','checkpoint_bytes','accounting_complete','outer_supervisor']},aggregate_audit_bytes=m['aggregate_audit_bytes'],stop_reason=None,stage4='OPEN')
write('bolton53-reconciliation-summary.json',summary)
print(json.dumps(summary,indent=2))
