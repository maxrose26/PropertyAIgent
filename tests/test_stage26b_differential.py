"""Exact offline Git baseline, no frozen benchmark edits or network."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BASE='8ec17e22e476209a88a1c162fb4b41a896a1af9e'
FIXTURE=ROOT/'tests/fixtures/stage26b/retained-cases.json'
PROBE=ROOT/'verification/stage26b/probe.py'


def capture(root):
    result=subprocess.run([sys.executable,str(PROBE),str(root),str(FIXTURE)],cwd=root,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def test_raw_evidence_eligibility_manifest(tmp_path):
    archive=tmp_path/'base.tar'
    with archive.open('wb') as f:subprocess.run(['git','archive',BASE],cwd=ROOT,stdout=f,check=True)
    base=tmp_path/'baseline';base.mkdir()
    with tarfile.open(archive) as f:f.extractall(base,filter='data')
    before,after=capture(base),capture(ROOT)
    expected={'248','16','62','336','371','508'}
    deltas=[]
    for site,old in before['cases'].items():
        new=after['cases'][site]
        assert old['subject']==new['subject']
        assert old['ah_headline']==new['ah_headline'] and old['ah_tenure']==new['ah_tenure']
        if site in expected:
            assert new['qualified_scale']['precision']=='UNKNOWN'
            assert new['qualified_scale']['value'] is None
        else:
            assert new==old
        deltas.append({'site_id':int(site),'expected':'containment' if site in expected else 'unchanged_positive_control',
            'old':old,'new':new,'scale_changed':old['qualified_scale']!=new['qualified_scale'],
            'evidence_basis':'Current-source proposal date in retained fixture, not historical extraction replay'})
    manifest={'baseline':BASE,'scope':after['scope'],'deltas':deltas,'families_before':before['families'],'families_after':after['families'],
        'fingerprint_limitation':'Subset hash only; full-universe fingerprint/identity regression covered separately; no production transition.'}
    output=os.environ.get('STAGE26B_DIFFERENTIAL_OUTPUT')
    if output:Path(output).write_text(json.dumps(manifest,indent=2))


def test_actual_universe_family_and_fingerprint_differential(tmp_path):
    archive=tmp_path/'base.tar'
    with archive.open('wb') as f:subprocess.run(['git','archive',BASE],cwd=ROOT,stdout=f,check=True)
    base=tmp_path/'baseline';base.mkdir()
    with tarfile.open(archive) as f:f.extractall(base,filter='data')
    probe=ROOT/'verification/stage26b/universe_probe.py'
    def run(root):
        result=subprocess.run([sys.executable,str(probe),str(root),str(FIXTURE)],cwd=root,capture_output=True,text=True,timeout=60)
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    before,after=run(base),run(ROOT)
    output=os.environ.get('STAGE26B_UNIVERSE_OUTPUT')
    if output:Path(output).write_text(json.dumps({'baseline':BASE,'before':before,'after':after},indent=2))
    # Existing material-parcel grouping responds to corrected evidence. The
    # algorithm is untouched; record this explicit key consequence for REVIEW.
    removed=set(before['universe'])-set(after['universe'])
    added=set(after['universe'])-set(before['universe'])
    assert removed=={'planning_delivery:phase:371:plot_A6'}
    assert added=={'planning_delivery:phase:371:Whole site / unphased'}
    assert after['universe'][next(iter(added))]['unit_count'] is None
    assert before['query_counts']==after['query_counts'], 'Request-local guard must not add database work'
    changed={k for k in before['universe'].keys() & after['universe'].keys() if before['universe'][k]!=after['universe'][k]}
    assert changed == {'planning_delivery:phase:900:2','planning_delivery:recent_permission:16','planning_delivery:recent_permission:248','planning_delivery:recent_permission:336','planning_delivery:recent_permission:508','planning_delivery:recent_permission:62'}
    for key in changed:
        assert after['universe'][key]['unit_count'] is None
        assert before['universe'][key]['fingerprint']!=after['universe'][key]['fingerprint']
    for buyer in before['buyers']:
        old={m['subject'] for f in before['buyers'][buyer] for m in f['members']}
        new={m['subject'] for f in after['buyers'][buyer] for m in f['members']}
        assert old-new=={'opp-phase-371-plot_A6'}
        assert new-old=={'opp-phase-371-Whole site / unphased'}
    def consequence_summary(data):
        return {buyer:[{'family':f['family'],'representative':f['representative'],'excluded':f['excluded'],
            'subjects':[{'key':m['subject'],'classification':m['fit']['classification'],'investigative':m['fit']['is_investigative_exception']} for m in f['members']]} for f in families]
            for buyer,families in data['buyers'].items()}
    expected=json.loads((ROOT/'tests/fixtures/stage26b/expected-b1-consequences.json').read_text())
    assert consequence_summary(before)==expected['before']
    assert consequence_summary(after)==expected['after']
    output=os.environ.get('STAGE26B_UNIVERSE_OUTPUT')
    if output:Path(output).write_text(json.dumps({'baseline':BASE,'before':before,'after':after,'changed_subjects':sorted(changed),'removed_subjects':sorted(removed),'added_subjects':sorted(added),'classification':'EXPECTED eligibility consequence; REVIEW approval required before release'},indent=2))
