"""Compare presentation instrumentation with immutable deployed v8 Git objects.

No frozen benchmark expectation is rewritten. Both processes evaluate identical
synthetic facts; only the six established assessment fields are compared.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


BASELINE = "22636ddab7e0af9b6220c6466d400bc1ec98aafc"
ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import dataclasses, itertools, json, sys
sys.path.insert(0, sys.argv[1])
from app.policy.buyer_profiles import BUYER_PROFILES
from app.policy.buyer_matching import MatchingFacts, B2MatchingContext, assess_buyer_fit, BUYER_MATCHING_POLICY_VERSION
from app.policy.buyer_profile_store import compute_buyer_mandate_fingerprint
from app.reporting.opportunity_universe import compute_opportunity_fingerprint
from app.reporting.opportunity_families import FamilySubject, group_into_families
from app.reporting.residential_count import CountAssessment
FIELDS = ('classification','is_investigative_exception','matches','does_not_match','unknown','investigate')
out = {'version': BUYER_MATCHING_POLICY_VERSION, 'buyers': {}}
for key, buyer in sorted(BUYER_PROFILES.items()):
    cases=[]
    for n,(domain,units,specialist,planning,affordable,state,verified) in enumerate(itertools.product(
        ('planning_delivery','strategic_land'), (None,0,10,44,45,49,50,100,101,110,125,180,200,220,500,2000),
        (None,False,True), ('permission_granted','planning_active_proposal','adopted_allocation','other_or_unknown'),
        (None,0,30,100), ('unknown','underway','complete'), (False,True))):
        facts=MatchingFacts(domain,units,'houses' if specialist is False else None,specialist,
            affordable,affordable is not None, None if affordable is None else affordable,
            planning,None,False,False)
        context=B2MatchingContext(council_code='stockport',development_state=state,development_state_scope_verified=verified)
        result=assess_buyer_fit(buyer,facts,context)
        assert set(dataclasses.asdict(result)) == set(FIELDS), 'Trace entered baseline serialization'
        cases.append({f:getattr(result,f) for f in FIELDS})
    for scope in ('site','phase','plot'):
        for precision,value,lower,upper,resolution in (
            ('EXACT',125,125,125,'resolved'), ('EXACT',500,500,500,'resolved'),
            ('EXACT',10,10,10,'resolved'), ('APPROXIMATE',100,100,102,'immaterial_variance'),
            ('RANGE',None,100,180,'reported_range'), ('UNKNOWN',None,None,None,'material_conflict')):
            count=CountAssessment(scope,scope.title(),f'site:1:{scope}',precision=precision,
                value=value,lower=lower,upper=upper,resolution=resolution)
            facts=MatchingFacts('planning_delivery',value,'houses',False,30,True,30,
                'permission_granted',True,True,False,count_assessment=count)
            result=assess_buyer_fit(buyer,facts,B2MatchingContext(council_code='stockport'))
            cases.append({f:getattr(result,f) for f in FIELDS})
    # Representative, membership, exclusion and deterministic family order use real results.
    subjects=[]
    # Every classification present plus scope/count cases, rather than an unknown-only prefix.
    representatives={}
    for result in cases:
        representatives.setdefault((result['classification'],result['is_investigative_exception']),result)
    family_cases=list(representatives.values()) + cases[-18:]
    for i,result in enumerate(family_cases):
        anchor=i//3+1; slot='LIFECYCLE' if i%3==0 else 'PHASE'
        subject_key=f'planning_delivery:site:{anchor}' if slot=='LIFECYCLE' else f'planning_delivery:phase:{anchor}:Phase {i%3}'
        subjects.append(FamilySubject('planning_delivery',anchor,subject_key,slot,
            result['classification'],result['is_investigative_exception'],'EXACT'))
    families=group_into_families(subjects)
    summary=[{'key':f.family_key,'representative':f.representative.subject_key,
        'members':[m.subject_key for m in f.members],
        'roles':[r.role for r in f.related], 'excluded':f.is_terminally_excluded} for f in families]
    out['buyers'][key]={'assessment':cases,'families':summary,
        'mandate_fingerprint':compute_buyer_mandate_fingerprint(buyer),
        'evidence_fingerprint':compute_opportunity_fingerprint({'unit_count':100,'planning_state':'permission_granted'})}
print(json.dumps(out,sort_keys=True))
'''


def _probe(root):
    env = {k: v for k, v in os.environ.items() if k not in
           ('DATABASE_URL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'SUPABASE_URL')}
    result = subprocess.run([sys.executable, '-c', PROBE, str(root)], cwd=root,
                            env=env, text=True, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_exact_deployed_v8_six_fields_fingerprints_and_families_unchanged():
    with tempfile.TemporaryDirectory(prefix='spec028-baseline-') as directory:
        archive = Path(directory) / 'baseline.tar'
        with archive.open('wb') as output:
            subprocess.run(['git', 'archive', BASELINE], cwd=ROOT, stdout=output, check=True)
        baseline = Path(directory) / 'baseline'
        baseline.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(baseline, filter='data')
        expected = _probe(baseline)
        actual = _probe(ROOT)
    assert expected['version'] == actual['version'] == 8
    assert len(actual['buyers']) == 4
    assert actual == expected
