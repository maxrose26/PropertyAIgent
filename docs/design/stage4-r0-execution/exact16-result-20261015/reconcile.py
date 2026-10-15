import json,pathlib,hashlib,sys,dataclasses,collections
root=pathlib.Path(__file__).resolve().parents[4];sys.path.insert(0,str(root));from app.scrapers.unit_filter import qualify
p=root/'docs/design/stage4-r0-execution/exact16-result-20261015';d=json.loads((p/'artifact/result.json').read_text()); rows=[];windows=[];comparisons=[]
ind=json.loads((root/'docs/design/stage4-r0-execution/two-scope-execution-20261015/independent/append-ledger.json').read_text())['rows']
for i,r in enumerate(d['results']):
 b=(p/f'artifact/checkpoints/{i:03}.json').read_bytes();assert hashlib.sha256(b).hexdigest()==d['checkpoint_sha256'][i]
 s=r['source'];w=r['window'];rs=s.get('listing_records',s.get('records',[]));refs={a['reference'] for a in rs}
 windows.append(dict(window=w,enumeration=r['enumeration_completeness'],coverage=r['completeness'],references=len(refs),capped=s.get('capped',False),applied_interval=s.get('applied_interval'),observation=s.get('primary_observation')))
 for a in rs:
  f=a.get('fields',{});desc=f.get('proposal',{}).get('value');dt=f.get('validated_date',{}).get('value');membership='UNKNOWN'
  if dt:
   from datetime import datetime
   try:membership='IN_TARGET' if datetime.strptime(dt,'%a %d %b %Y').date().isoformat()>='2026-09-29' else 'OVERLAP'
   except ValueError:pass
  q=dataclasses.asdict(qualify(desc)) if desc else None
  rows.append(dict(council=w['council'],reference=a['reference'],source=a,window=w,source_date_membership=membership,criteria_verified=s.get('applied_interval')==[w['start'],w['end']],proposal_screen=q,screen_use='PROCESSING_PRIORITY_ONLY_NOT_PERMANENT_REJECTION',materiality='POTENTIALLY_MATERIAL' if not desc else 'RETAINED_FOR_QUALIFICATION',database_presence='NOT_QUERIED'))
 for x in ind:
  if x['council']==w['council'] and x['start']==w['start'] and x['status']=='COMPLETE':
   ir=set(x['references']);comparisons.append(dict(window=w,independent_observed_started_at=x['observed_started_at'],independent_observed_ended_at=x['observed_ended_at'],primary_observation=s['primary_observation'],independent_count=len(ir),primary_count=len(refs),intersection=len(ir&refs),primary_only=sorted(refs-ir),independent_only=sorted(ir-refs),interpretation='CROSS_OBSERVATION_ONLY_SOURCE_CHANGE_UNRESOLVED_COVERAGE_UNKNOWN'))
for w in d['not_attempted']:windows.append(dict(window=w,enumeration='NOT_ATTEMPTED',coverage='UNKNOWN',references=0))
summary=dict(run=38798433667,revision='0cfbf5ded5eaef46d0fb754e0e5c057f59554ff4',artifact=12003596349,artifact_sha256=hashlib.sha256((p/'artifact.zip').read_bytes()).hexdigest(),windows=windows,independent_comparisons=comparisons,candidate_occurrences=len(rows),unique_identities=len({(r['council'],r['reference']) for r in rows}),membership=dict(collections.Counter(r['source_date_membership'] for r in rows)),checkpoint_hashes_verified=7,resources={k:d[k] for k in ['requests','bytes','checkpoint_bytes','outer_supervisor','accounting_complete']},production='NO_DATABASE_CAPABILITY_PERSISTENCE_FALSE',stop=d['stop_reason'])
(p/'reconciliation.json').write_text(json.dumps(summary,indent=2)+'\n');(p/'candidate-ledger.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['windows','resources']},indent=2))
print('screen candidates')
for r in rows:
 if r['proposal_screen'] and r['proposal_screen'].get('qualifies'):print(r['reference'],str(r['source']['fields']['proposal']['value'])[:500],r['proposal_screen'])
