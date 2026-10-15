"""Retained evidence/invariants only. Does not implement proposed containment."""
import hashlib,json,zipfile
from pathlib import Path
from unittest.mock import patch
from verification.discovery import r0_recovery_proposal as recovery
from verification.discovery import finite_acceptance as finite
from verification.discovery import r0_registered_scopes as registered
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'exact20-results-20261015'
def read(p):
    if p.is_file():return json.loads(p.read_bytes())
    if p==BASE/'artifact/result.json':
        with zipfile.ZipFile(BASE/'artifact-11997283579.zip') as z:return json.loads(z.read('result.json'))
    raise FileNotFoundError(p)



def test_exact16_is_only_consumed_not_attempted_and_derived_limits():
    m=read(ROOT/'untouched16-manifest.json');r=read(BASE/'artifact/result.json')
    assert m['rows']==r['not_attempted'] and len(m['rows'])==16
    assert [x['council'] for x in m['rows']]==['salford']*4+['stockport']*4+['tameside']*4+['wigan']*4
    p=m['limits'];arc=sum(x['council'] in finite.ARCUS for x in m['rows']);assert arc==4
    assert p['requests']==4*80+12*10==440
    assert p['bytes']==4*20*1024*1024+12*3_000_000==119886080
    assert p['seconds']==16*55+120==1000
    assert p['job_seconds']-p['setup_seconds']-p['proposed_secondary_timeout_seconds']-p['proposed_kill_grace_seconds']>=p['cleanup_upload_reserve_seconds']
    assert not m['registered'] and not m['execution_authorised'] and not m['persistence']
    assert 'untouched16' not in registered.PROFILES


def test_actual_retained_criteria_timeout_still_stops_current_parent(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    r=read(BASE/'artifact/result.json');failed=r['results'][-1];next_row=r['not_attempted'][0];calls=[]
    assert failed['source']['listing_failure']=='TimeoutError' and failed['source']['listing_stage']=='CRITERIA'
    def reader(row):
        calls.append(row);assert len(calls)==1
        return failed['source']
    plan=dict(rows=[failed['window'],next_row])
    result=recovery._execute_fixed(plan,'OFFLINE_ASSESSMENT',reader=reader,limits=dict(requests=160,bytes=40*1024*1024,seconds=200,output_bytes=20000000),checkpoint=lambda _:None,clock=lambda:0)
    assert len(calls)==1 and result['not_attempted']==[next_row]
    assert result['stop_reason']=='SAFETY_OR_UNCLASSIFIED_FAILURE'
    assert result['results'][0]['enumeration_completeness']=='FAILED' and result['completeness']=='INCOMPLETE'
    assert not result['completed_through_advanced']


def test_retained_local_isolation_preconditions_are_not_criteria_verification():
    a=read(BASE/'artifact/result.json')['results'][-1]['source']
    assert a['requested_origins']==a['navigated_origins']==['https://account.rochdale.gov.uk']
    assert not a['blocked_actions'] and not a['blocked_posts'] and a['navigation_mismatch'] is None
    assert recovery.resources(dict(council='rochdale'),a) is not None
    assert a['cleanup']=='CONTEXT_BROWSER_CLOSED' and a['process_cleanup']=='CLOSED' and a['live_owned_survivors']==0
    assert a['applied_interval'] is None and a['safety_failure'] is True
    assert a['safety_events']==['LISTING_NOT_QUALIFIED']
    # A safe new category cannot be derived by clearing these historical flags.
    assert not recovery.safety(dict(council='rochdale',start='2026-10-08',end='2026-10-14',semantics='VALIDATED'),a)


def test_existing_finite_reader_always_uses_distinct_temporary_audit_contexts():
    from verification.direct_reference import instrumented_probe
    paths=[]
    def supervised(case,path,window):
        paths.append(path);path.write_text(json.dumps(dict(persistence=False,case=case,requested_interval=list(window))))
    rows=[dict(council='rochdale',start='2026-10-08',end='2026-10-14',semantics='VALIDATED'),dict(council='salford',start='2026-09-17',end='2026-09-23',semantics='VALIDATED')]
    with patch.object(instrumented_probe,'supervised',supervised):
        for row in rows:assert finite.read(row)['persistence'] is False
    assert len(paths)==2 and paths[0].parent!=paths[1].parent and all(not p.parent.exists() for p in paths)


def test_rochdale_difference_does_not_establish_publication_or_parser_cause():
    a=read(ROOT/'rochdale-difference-assessment.json');ledger=read(BASE/'candidate-ledger.json')
    row=next(x for x in ledger if x['reference']==a['reference'])
    assert row['source_date_literal']==a['source_date_literal']=='07/10/2026'
    assert a['outcome']=='UNRESOLVED' and a['public_availability_timestamp']=='UNKNOWN'
    assert a['primary_reference_count']==18 and a['independent_reference_count']==17
    assert not a['parser_miss_proven'] and not a['publication_backfill_proven']


def test_runtime_seals_and_comparison_scopes_unchanged_at_preparation_baseline():
    for path,expected in read(ROOT/'unchanged-baseline-hashes.json').items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected
