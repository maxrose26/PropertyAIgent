import json,zipfile,hashlib,collections,datetime,pathlib
P=pathlib.Path('/tmp'); rev='fa2fe834d6c4e01e2c0367cb851834bd0418ff8c'
meta={'screen14':(38823673985,12014114130,'5c116b92481e335160f7f6f1e7772ed1ff46b2a7f31ccb9b6d79de98849997af','screening-metadata-fourteen.json'),'residual4':(38824069251,12014078910,'9a4038d43590b5b5ed51acfd2f18355cabb54b69ff31ae2dd57bdb67ed277424','residual-four.json'),'bridge9':(38824329688,12014740569,'d7e0416de5f642da084ab585375247c9d4aaabcfd67b78957c8ac61a3b764c58','bridge-nine.json')}
scopes={};new={};m=json.load(open(P/'comparison-944.json'));known={(x['council_code'],x['reference']) for x in m['identities']+m['excluded_accepted_readbacks']};ind=json.load(open(P/'independent.json')); assert hashlib.sha256((P/'independent.json').read_bytes()).hexdigest()=='51798ac6bebdb6a28a9c8cd4120b8de23c6a5b5d0af7d2c782e46b98e202ab30'
indout=[]; sourcecost=[]
for name,(run,artifact,digest,manifest) in meta.items():
 z=zipfile.ZipFile(P/(name+'.zip'));assert hashlib.sha256((P/(name+'.zip')).read_bytes()).hexdigest()==digest
 d=json.loads(z.read('result.json'));e=json.loads(z.read('execution.json'));f=json.load(open(P/manifest));assert e==dict(sha=rev,run_id=str(run),manifest_sha256=hashlib.sha256((P/manifest).read_bytes()).hexdigest(),persistence=False,run_number=1,attempt=1)
 assert d['manifest_sha256']==e['manifest_sha256'];assert d['accounting_complete'];assert d['outer_supervisor']['cleanup']=='CLOSED' and d['outer_supervisor']['live_owned_survivors']==0
 auditbytes=sum(x.file_size for x in z.infolist());assert auditbytes<=20_000_000
 actual=[];req=byte=cpbytes=0
 for i,r in enumerate(d['results']):
  b=z.read(f'checkpoints/{i:03}.json');assert hashlib.sha256(b).hexdigest()==d['checkpoint_sha256'][i];assert json.loads(b)==r;cpbytes+=len(b)
  s=r['source'];w=r['window'];assert w in f['rows'];arc=w['council'] in ['manchester','rochdale','salford'];resource=s if arc else s['resource'];req+=resource.get('requests',resource.get('requests_attempted',0));byte+=(max(s['encoded_bytes'],s['decoded_bytes'])+s['outbound_payload_bytes']) if arc else resource['received_bytes']
  records=s.get('listing_records',s.get('records',[]));refs={t['reference'] for t in records};ir=next(t for t in ind['rows'] if all(t[k]==v for k,v in w.items()));irefs={t.split('|')[0].strip() for t in ir['references']};indout.append(dict(window=w,independent_status=ir['status'],primary_state=r['enumeration_completeness'],independent_reference_count=len(irefs),primary_reference_count=len(refs),primary_only=sorted(refs-irefs),independent_only=sorted(irefs-refs),equality=refs==irefs,accepted_complete_comparison=ir['status']=='COMPLETE' and r['enumeration_completeness']=='COMPLETE',source_run=run))
  for rec in records:
   key=(w['council'],rec['reference'])
   if key not in known:new[key]=dict(council_code=key[0],reference=key[1],date_membership='BRIDGE_2026_10_15' if name=='bridge9' else 'REASSESS_FROM_VISIBLE_DATES',window=w,run_id=run,source=rec)
  actual.append(dict(window=w,enumeration=r['enumeration_completeness'],candidate_count=len(refs),contained=r['source_local_contained'],safe_gap=r['safe_local_gap'],failure=s.get('failure'),listing_failure=s.get('listing_failure'),retry_counter=resource.get('retries',0),checkpoint_sha256=d['checkpoint_sha256'][i],observation=s.get('primary_observation')))
 assert req==d['requests'] and byte==d['bytes'] and cpbytes==d['checkpoint_bytes']
 scopes[name]=dict(run_id=run,run_number=1,attempt=1,artifact_id=artifact,zip_sha256=digest,execution=e,results=actual,not_attempted=d['not_attempted'],blocked_unresolved=d['blocked_unresolved'],stop_reason=d['stop_reason'],requests=d['requests'],accounted_bytes=d['bytes'],audit_bytes=auditbytes,checkpoint_bytes=cpbytes,outer=d['outer_supervisor'])
 sourcecost.append((len(actual),req,byte,auditbytes,d['outer_supervisor']['elapsed_seconds']))
# Preserve all original rows and append successor outcomes without overwriting chronology.
hist=json.load(open(P/'historical-coverage.json'));assert len(hist)==36
for h in hist:
 w=h['window'];match=next((r for r in scopes['residual4']['results'] if r['window']==w),None);blocked=next((r for r in scopes['residual4']['blocked_unresolved'] if r['window']==w),None)
 h['completion_mandate_successor']=match or blocked
bridge=[]
for w in json.load(open(P/'bridge-nine.json'))['rows']:
 r=next((r for r in scopes['bridge9']['results'] if r['window']==w),None)
 bridge.append(r or dict(window=w,enumeration='NOT_ATTEMPTED_GLOBAL_STOP',candidate_count=None))
ids=[dict(council_code=k[0],reference=k[1]) for k in sorted(new)];assert len(ids)<=1000
out=dict(reconciled_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),runtime_revision=rev,tree='c24de41feb6245c9a3579acefb6ca4f82515bb61',result='BLOCKED_GLOBAL_STOP_AND_EXHAUSTED_PROOF_ALLOWANCES',bounded_mandate_completed=False,source_date_enumeration_reconciled=False,database_catchup_complete=False,stage4_accepted=False,master_stage='4 OPEN',historical_windows=hist,bridge_rows=bridge,scopes=scopes,independent=dict(ledger_sha256='51798ac6bebdb6a28a9c8cd4120b8de23c6a5b5d0af7d2c782e46b98e202ab30',seal_timestamp='2026-10-15T23:08:42.822381Z',statuses=dict(collections.Counter(x['status'] for x in ind['rows'])),reconciled_rows=indout,exposure_limitations=ind['exposure_limitations'],network_requests='UNKNOWN',network_bytes='UNKNOWN',unobserved_primary_rows=27-len(indout)),delta=dict(count=len(ids),identities=ids,comparison='NOT_EXECUTED_GLOBAL_STOP',current_presence='UNKNOWN'),new_candidates=list(new.values()),aggregate=dict(observation_calls=sum(x[0] for x in sourcecost),requests=sum(x[1] for x in sourcecost),accounted_bytes=sum(x[2] for x in sourcecost),audit_bytes=sum(x[3] for x in sourcecost),outer_execution_seconds=sum(x[4] for x in sourcecost),peak_owned_rss=max(s['outer']['peak_owned_rss'] for s in scopes.values()),sequential_scopes=3,setup_to_job_completion_seconds=322,internal_transport_retries=1),production=dict(new_admission_calls=0,new_writes=0,accepted_ids_preserved=[1504,1505,1506],new_pending=0,new_verified_facts=0,uncertain_commits=0),capture=dict(result='NOT_EXECUTED_GLOBAL_STOP',eligible_count='NOT_ESTABLISHED',excess_eligible_count='UNKNOWN_NOT_A_ZERO',bolton01702='ALREADY_KNOWN_ID1493_NO_REFETCH',oldham_priorities='NOT_ATTEMPTED_GLOBAL_STOP_FRESH_COUPLED_ELIGIBILITY_UNPROVEN',stockport_priorities='WITHHELD_EXACT_SOURCE_FACTUAL_CONTRACT_UNQUALIFIED'))
assert out['aggregate']['requests']<=1530 and out['aggregate']['accounted_bytes']<=404487360
assert out['aggregate']['outer_execution_seconds']<=1485
(P/'completion-consolidated.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
(P/'delta-three.json').write_text(json.dumps(dict(purpose='FROZEN_AUTHORISED_SUCCESSOR_IDENTITIES_NOT_QUERIED',count=len(ids),identities=ids,excludes='fixed944 and accepted1504-1506',execution='BLOCKED_GLOBAL_STOP'),indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(aggregate=out['aggregate'],delta=out['delta'],matched_complete=sum(r['accepted_complete_comparison'] and r['equality'] for r in indout),historical=collections.Counter(r['latest_enumeration'] for r in hist),bridge=collections.Counter(r['enumeration'] for r in bridge)),indent=2))
