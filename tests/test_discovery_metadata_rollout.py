"""Offline admission and cross-council boundary tests. No source/DB calls."""
import hashlib,json,time
from pathlib import Path
from copy import deepcopy
import pytest
from verification.discovery import metadata_rollout as m
from verification.discovery import screening_assessment as old
from verification.discovery.arcus_ui_config import METADATA_ROLLOUT_CONFIGS,SCREENING_CONFIG
from tests.test_discovery_screening_assessment import source,row


def env(index):
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+m.WORKFLOW+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_JOB=f'scope_{index:02d}',SCOPE_INDEX=str(index),PREVIOUS_GO='GENESIS' if index==0 else 'GO',JOB_STARTED_EPOCH=str(int(time.time())))


def test_freeze_exact401_no_completed_window_and_aggregate_ceiling():
    v=m.manifest();scopes=v['scopes']
    assert len(scopes)==13 and sum(len(s['historical_context']) for s in scopes)==401
    assert [len(s['historical_context']) for s in scopes]==[12,13,27,46,25,44,53,43,39,37,29,15,18]
    keys={(s['council'],s['start'],s['end']) for s in scopes};assert len(keys)==13
    assert ('manchester','2026-10-01','2026-10-03') not in keys
    ids=[(r['council'],r['reference']) for s in scopes for r in s['historical_context']];assert len(ids)==len(set(ids))
    assert 13*(260+60+160)==v['limits']['combined_allocated_seconds']==6240
    assert 13*80==v['limits']['requests'] and 13*20*1024**2==v['limits']['accounted_bytes']
    assert 13*45==v['limits']['source_worker_seconds'] and 13*60==v['limits']['outer_active_seconds']
    assert 13*2*1024**2==v['limits']['exported_audit_bytes']


@pytest.mark.parametrize('index',range(13))
def test_exact_per_scope_binding_and_source_config(index):
    s=m.scope(index);c=METADATA_ROLLOUT_CONFIGS[s['case']]
    assert (c.council,c.start,c.end,c.capture_metadata,c.assessment_metadata)==(s['council'],s['start'],s['end'],True,True)
    m.admit('a'*40,m.MANIFEST_SHA,m.AUTHORITY,env(index),index)
    m.validate_plan(m.plan(index))
    for k,v in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('GITHUB_JOB','scope_99'),('SCOPE_INDEX','99'),('PREVIOUS_GO','PARTIAL'),('GITHUB_SHA','b'*40),('JOB_STARTED_EPOCH',str(int(time.time())-261))]:
        with pytest.raises(ValueError):m.admit('a'*40,m.MANIFEST_SHA,m.AUTHORITY,dict(env(index),**{k:v}),index)
    with pytest.raises(ValueError):m.admit('a'*40,m.MANIFEST_SHA,m.AUTHORITY,env(index),index,workflow_bytes=b'changed')


@pytest.mark.parametrize('index',[0,1,2])
def test_council_specific_assessment_optional_unknown_and_missing_proposal(index):
    s=m.scope(index);c=METADATA_ROLLOUT_CONFIGS[s['case']]
    a=source([row()]);a.update(case=s['case'],destination=c.destination,applied_interval=[s['start'],s['end']],requested_interval=[s['start'],s['end']])
    out=old.assess(a,config=c,case=s['case'],interval=[s['start'],s['end']],historical_context=s['historical_context'])
    assert out['outcome']=='GO' and out['proposal_capture']['usable']==1
    assert out['field_states']['application_type']=={'UNKNOWN':1}
    a['listing_records'][0]['fields']['proposal']['state']='UNKNOWN'
    assert old.assess(a,config=c,case=s['case'],interval=[s['start'],s['end']],historical_context=s['historical_context'])['outcome']=='PARTIAL'
    a['destination']=SCREENING_CONFIG.destination
    if index<2:assert old.assess(a,config=c,case=s['case'],interval=[s['start'],s['end']],historical_context=[])['enumeration_outcome']!='COMPLETE'


def good():
    return dict(row_evidence_revalidated=True,outcome='GO',scope_index=0,stop_reason=None,accounting_complete=True,checkpoint_sha256=['a'*64],outer_supervisor=dict(cleanup='CLOSED',live_owned_survivors=0,expired=False,limit_hit=None,exit_code=0,peak_owned_rss=1,elapsed_seconds=5))


@pytest.mark.parametrize('change',[{'outcome':'PARTIAL'},{'accounting_complete':False},{'stop_reason':'CAP'},{'scope_index':1},{'checkpoint_sha256':[]}])
def test_non_go_halts_chain(change):
    m.require_go(good(),0)
    with pytest.raises(ValueError,match='GLOBAL_STOP'):m.require_go(dict(good(),**change),0)


@pytest.mark.parametrize('change',[{'cleanup':'UNKNOWN'},{'live_owned_survivors':1},{'expired':True},{'limit_hit':'RSS'},{'elapsed_seconds':60},{'peak_owned_rss':1536*1024**2+1},{'exit_code':1}])
def test_uncertain_outer_halts_chain(change):
    a=good();a['outer_supervisor'].update(change)
    with pytest.raises(ValueError,match='GLOBAL_STOP'):m.require_go(a,0)


def test_workflow_single_chain_and_exact_template():
    import yaml
    raw=(m.ROOT/m.WORKFLOW).read_bytes();assert raw==(m.PACK/'registered-workflow.yml.txt').read_bytes()
    v=yaml.safe_load(raw);jobs=v['jobs'];assert len(jobs)==13
    assert set(v.get('on',v.get(True)))=={'workflow_dispatch'}
    assert v['concurrency']['cancel-in-progress'] is False
    for i in range(13):
        j=jobs[f'scope_{i:02d}'];assert j['timeout-minutes']==8 and j['env']['SCOPE_INDEX']==str(i)
        assert j['outputs']['go']=='${{ steps.qualification.outputs.go }}'
        if i:assert j['needs']==f'scope_{i-1:02d}' and "outputs.go == 'GO'" in j['if']
        else:assert 'needs' not in j
        runtext='\n'.join(x.get('run','') for x in j['steps'])
        assert '--require-go' in runtext and '--scope "$SCOPE_INDEX"' in runtext
        assert 'continue-on-error' not in str(j)
    assert 'environment:' not in raw.decode() and 'secrets.' not in raw.decode()


def test_checkpoint_tamper_and_unexpected_file(tmp_path):
    from verification.discovery.r0_registered_scopes import AuditStore
    e=env(0);e['GITHUB_RUN_ID']='123'
    (tmp_path/'execution.json').write_text(json.dumps(dict(sha='a'*40,run_id='123',manifest_sha256=m.MANIFEST_SHA,scope_index=0,run_number=1,attempt=1,persistence=False)))
    store=AuditStore(tmp_path,m.PROFILE);store.record(source([row()]));store.finish(dict(good(),outcome='PARTIAL'),tmp_path/'result.json')
    m.verify(tmp_path,e,0)
    (tmp_path/'checkpoints/000.json').write_text('{}')
    with pytest.raises(ValueError,match='CHECKPOINT_HASH'):m.verify(tmp_path,e,0)


def test_revalidation_rejects_cross_council_and_projection_tampering():
    from verification.discovery.arcus_ui_window import qualify_segment
    s=m.scope(0);c=METADATA_ROLLOUT_CONFIGS[s['case']]
    a=source([row()]);a.update(case=s['case'],destination=c.destination,applied_interval=[s['start'],s['end']],requested_interval=[s['start'],s['end']])
    assert m.evaluate(a,0)['stop_reason']=='ROW_EVIDENCE_NOT_REVALIDATED'
    card=dict(fields=[dict(label='Reference',value='TEST/26')],links=[dict(text='TEST/26',href=a['listing_records'][0]['source_url'].replace(SCREENING_CONFIG.host,c.host))],assessment_capture=a['listing_records'][0]['assessment_capture'])
    a['listing_records']=qualify_segment('Showing 1 to 1 of 1 results',[card],1,config=c)[3]
    assert m.evaluate(a,0)['outcome']=='GO'
    a['listing_records'][0]['fields']['proposal']['value']='Forged proposal'
    assert m.evaluate(a,0)['outcome']=='NO_GO'
