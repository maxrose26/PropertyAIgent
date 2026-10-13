"""Two fixed authorised current-gate cohorts; no resume or runtime selector."""
import os
from . import batch,batch_production
PENDING=batch_production.Admission(batch.ManifestSpec('closure-pending-manifest.json','61b6cf8abb086994d26f32f4aeb9139089e296d23021b5c46412e5be52ee0500',17,True),
 '.github/workflows/stage4-closure-pending-production-once.yml','AUTHORISE_STAGE4_CLOSURE_PENDING_B2_ONCE',
 'verification.direct_reference.closure_production','stage4_closure_pending_once',True)
EXPANDED=batch_production.Admission(batch.ManifestSpec('closure-expanded-manifest.json','deaebe1b30acb6dbbb9484af12c9627923235b661ea0dfc20de8747d97d27b52',19,True),
 '.github/workflows/stage4-closure-expanded-production-once.yml','AUTHORISE_STAGE4_CLOSURE_EXPANDED_B2_ONCE',
 'verification.direct_reference.closure_production','stage4_closure_expanded_once',True)
CONTEXTS=(PENDING,EXPANDED)
PENDING_IDS={24,28,29,31,32,39,40,41,390,392,393,403,53,56,59,60,446}
EXPANDED_IDS={201,478,1069,14,356,357,402,78,87,104,111,708,50,226,298,359,488,506,710}

def reconcile():
 groups=[batch.manifest(c.manifest) for c in CONTEXTS]
 for group,ids in zip(groups,(PENDING_IDS,EXPANDED_IDS)):
  if {r['identity']['application_id'] for r in group}!=ids:raise ValueError('CLOSURE_SCOPE')
  ordered=[(r['identity']['council'],r['identity']['application_id']) for r in group]
  if ordered!=sorted(ordered):raise ValueError('CLOSURE_ORDER')
  for r in group:
   if r['policy'] not in {'A','B','C'} or not r['selection_reason']:raise ValueError('CLOSURE_POLICY')
   if r['identity']['council']=='trafford':raise ValueError('DEFERRED_TRAFFORD')
   if set(r['prior_facts'])!={'status','decision','decision_issued_date','status_verified_at','evidence_refresh_required','evidence_refresh_reason','evidence_refresh_trigger'}:raise ValueError('PRIOR_CONTEXT')
   if group is groups[0] and (r['prior_facts']['status']!='Awaiting decision' or r['prior_facts']['decision'] is not None or r['prior_facts']['decision_issued_date'] is not None):raise ValueError('PENDING_CONTEXT')
 if PENDING_IDS&EXPANDED_IDS:raise ValueError('OVERLAP')
 return groups

def context(env=None):
 e=os.environ if env is None else env
 matches=[c for c in CONTEXTS if e.get('GITHUB_WORKFLOW_REF')=='maxrose26/PropertyAIgent/'+c.workflow+'@refs/heads/master']
 if len(matches)!=1:raise ValueError('CLOSURE_WORKFLOW')
 reconcile()
 return matches[0]

def main():
 try:c=context()
 except Exception:return 2
 return batch_production.main(c)

if __name__=='__main__':raise SystemExit(main())
