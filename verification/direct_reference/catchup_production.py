"""Two fixed catch-up registrations using the accepted batch runner.

No manifest selector, source substitutions, resume or source fixtures. The exact
master workflow identity selects its own frozen cohort before credentials move.
"""
import hashlib
import json
import os
from pathlib import Path
from . import batch, batch_production

LEDGER_SHA256='70546a141e22141f90b8c79456c26fd075ec25a16adf923bad699dc98517d612'
A=batch_production.Admission(batch.ManifestSpec('catchup-a-manifest.json','96afbb6eef61cd1eee6ae24d5e21a047152f61492c25edfd5d6e86dc3f315ede',20,True),
    '.github/workflows/stage4-catchup-a-production-once.yml','AUTHORISE_STAGE4_ADMITTED_CATCHUP_A_B2_ONCE',
    'verification.direct_reference.catchup_production','stage4_catchup_a_once')
B=batch_production.Admission(batch.ManifestSpec('catchup-b-manifest.json','277c6b43018a03d06301f953526e99979102b851a7d62c61b29ebd9d54791760',10,True),
    '.github/workflows/stage4-catchup-b-production-once.yml','AUTHORISE_STAGE4_ADMITTED_CATCHUP_B_B2_ONCE',
    'verification.direct_reference.catchup_production','stage4_catchup_b_once')
CONTEXTS=(A,B)
PREVIOUSLY_ATTEMPTED={202,42,78,72,468,197,18,381,41,409,37,126,187,45,53,54,56,305,783,289,220,209,499}


def ledger():
    raw=Path(__file__).with_name('catchup-ledger.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=LEDGER_SHA256:raise ValueError('LEDGER_DIGEST')
    return json.loads(raw)


def reconcile():
    l=ledger();groups=[batch.manifest(c.manifest) for c in CONTEXTS]
    ids=[[r['identity']['application_id'] for r in group] for group in groups]
    flat=ids[0]+ids[1]
    if ids!=[l['batch_a_ids'],l['batch_b_ids']] or flat!=l['unattempted_ids'] or len(flat)!=len(set(flat)):raise ValueError('PARTITION')
    if set(flat)&PREVIOUSLY_ATTEMPTED:raise ValueError('PREVIOUSLY_ATTEMPTED')
    ordered=[(r['identity']['council'],r['identity']['application_id']) for group in groups for r in group]
    if ordered!=sorted(ordered):raise ValueError('ORDER')
    for group in groups:
        for r in group:
            if r['policy'] not in {'A','B','C'} or r['selection_stratum']!='ADMITTED_POLICY_DUE_NOT_PREVIOUSLY_ATTEMPTED':raise ValueError('POLICY')
            if set(r['prior_facts'])!={'status','decision','decision_issued_date','status_verified_at','evidence_refresh_required','evidence_refresh_reason','evidence_refresh_trigger'}:raise ValueError('PRIOR_CONTEXT')
            if not isinstance(r['selection_reason'],str) or not r['selection_reason']:raise ValueError('SELECTION_REASON')
    sets=[set(l[k]) for k in ('successfully_refreshed_due_ids','completeness_withheld_due_ids','timeout_due_ids','previously_retrieved_without_persistence_due_ids','unattempted_ids')]
    if sum(map(len,sets))!=l['census_admitted_policy_due_count'] or len(set.union(*sets))!=sum(map(len,sets)):raise ValueError('COVERAGE_70546a141e22141f90b8c79456c26fd075ec25a16adf923bad699dc98517d612')
    return l


def context(env=None):
    e=os.environ if env is None else env
    ref=e.get('GITHUB_WORKFLOW_REF')
    matches=[c for c in CONTEXTS if ref=='maxrose26/PropertyAIgent/'+c.workflow+'@refs/heads/master']
    if len(matches)!=1:raise ValueError('CATCHUP_WORKFLOW')
    reconcile()
    return matches[0]


def main():
    try:c=context()
    except Exception:return 2
    return batch_production.main(c)


if __name__=='__main__':raise SystemExit(main())
