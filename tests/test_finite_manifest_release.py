"""Manifest data wiring through existing launcher/publisher. Synthetic observations, no council/DB."""
import base64
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from verification.discovery import four_council_release as r,campaign_manifest as campaign,four_council_proof as proof
from verification.ingestion_storage.operational_publication import GitHub,canonical
from tests.test_discovery_four_council_release import API,Memory
from tests.campaign_release_support import selection,audit


def registration(value=None):
    t=r.now()-timedelta(minutes=1)
    return r.render('campaign-offline-fixture','a'*40,'b'*40,'1'*40,t.isoformat(),(t+timedelta(hours=2)).isoformat(),released=True,
        version=r.CAMPAIGN_VERSION,campaign=selection() if value is None else value)


class Source:
    def __init__(self,reg):self.reg=reg;self.calls=[];self.values={};self.after=None
    def run(self,index,check):
        self.calls.append(index)
        if self.after:self.after(index)
        check()
        return self.values.get(index) or audit(r.source_row(self.reg,index)),dict(source_group_closed=True,child_reaped=True,failures=[],supervised_seconds=.01)


def world(tmp_path,monkeypatch,plan=None):
    reg=registration(plan);api=API(reg);memory=Memory(tmp_path);source=Source(reg);events=[];holder={}
    monkeypatch.setattr('psutil.Process',lambda:type('Process',(),{'children':lambda self,recursive:[]})())
    github=GitHub(lambda *x:events.append(x),lambda:holder['launch'].deadline(),runner=api.runner,bound=320)
    launch=r.Launcher(reg,tmp_path,github=github,memory=memory,source=source,emit=lambda *x:events.append(x));holder['launch']=launch
    return reg,api,source,launch,events


@pytest.mark.parametrize('plan',[selection(),selection('2026-11-08','2026-11-14',('bury','oldham','tameside'))])
def test_two_canonical_selections_same_launcher_readers_publisher(tmp_path,monkeypatch,plan):
    reg,api,source,launch,events=world(tmp_path,monkeypatch,plan)
    r.validate(reg,checkout=False)
    out=launch.execute()
    assert source.calls==[0,1,2] and out['status']=='MANIFEST_OBSERVATIONS_COMPLETE' and out['cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE'
    assert [v['scope'] for v in out['results']]==campaign.select(plan)
    assert out['database_connections']==out['application_writes']==0 and not out['coverage_advance']
    for index,row in enumerate(campaign.select(plan)):
        tree=api.trees[api.commits[api.head]]
        path=reg['directory']+f'/slot-{index}/receipt.json'
        receipt=json.loads(base64.b64decode(api.blobs[tree[path]]['content']))
        assert receipt['scope']==row and receipt['index']==index
    assert launch.requests==(10 if 'rochdale' in [x['council'] for x in launch.rows] else 12) # fixtures: 2 Arcus/4 per Idox
    assert sum(x['requests'] for x in launch.reserved)==(100 if any(x['council']=='rochdale' for x in launch.rows) else 30)


@pytest.mark.parametrize('mutate',[
    lambda p:p.update(extra='ignored'),lambda p:p.update(finite_manifest_sha256='0'*64),
    lambda p:p['finite_manifest'].update(purpose='ARBITRARY'),lambda p:p['finite_manifest'].update(extra=1),
    lambda p:p['finite_manifest']['limits'].update(requests=999999),lambda p:p['finite_manifest']['rows'][3].update(semantics='VALIDATED'),
    lambda p:p.update(selected_ordinals=[7,4,3]),lambda p:p.update(selected_ordinals=[3,3]),lambda p:p.update(selected_ordinals=[True]),
    lambda p:p.update(selected_ordinals=[-1]),lambda p:p.update(selected_ordinals=[999]),lambda p:p.update(selected_ordinals=[2]),
    lambda p:p['finite_manifest']['rows'].append(deepcopy(p['finite_manifest']['rows'][3])),
    lambda p:p['finite_manifest']['rows'][3].update(start='2026-10-31'),
    lambda p:p['finite_manifest'].update(end='2026-12-31'),lambda p:p.update(selected_ordinals=[]),
])
def test_invalid_plan_selection_rejected_before_claim_or_source(mutate):
    p=selection();mutate(p)
    with pytest.raises(r.Stop,match='CAMPAIGN_MANIFEST_OR_CAPACITY'):registration(p)


def test_capacity_refuses_four_rows_two_arcus_or_full_nine_without_claim():
    for plan in [selection(councils=campaign.COUNCILS),selection('2026-11-01','2026-11-14',('rochdale',))]:
        with pytest.raises(r.Stop,match='CAMPAIGN_MANIFEST_OR_CAPACITY'):registration(plan)
    p=selection();p['selected_ordinals']=list(range(9))
    with pytest.raises(r.Stop):registration(p)
    totals=campaign.capacity(campaign.select(selection()),r.SUCCESSOR_V2_LIMITS)
    assert totals['requests']==100 and totals['mixed_source_bytes']==26_971_520 and totals['observations']==3
    assert totals['publication_requests']<=80 and totals['github_requests']<=320 and totals['exported_bytes']==2*1024**2


@pytest.mark.parametrize('field',['manifest_sha256','rows','source_routes','limits','continuation_allowlist','selected_ordinals'])
def test_registration_regenerates_every_derived_field(field):
    reg=registration()
    if field=='manifest_sha256':reg[field]='0'*64
    else:reg['manifest'][field]=None
    with pytest.raises((r.Stop,ValueError,TypeError)):r.validate(reg,checkout=False)


def test_manifest_bound_row_is_not_admission_or_historical_proof_enablement():
    row=campaign.select(selection())[0]
    with pytest.raises(proof.ProofError):proof.require_scope(*(row[k] for k in ('council','semantics','start','end')))
    with proof.manifest_scope(row):
        proof.require_scope(*(row[k] for k in ('council','semantics','start','end')))
        with pytest.raises(proof.ProofError):proof.require_scope('bury','RECEIVED',row['start'],row['end'])
    with pytest.raises(proof.ProofError):proof.require_scope(*(row[k] for k in ('council','semantics','start','end')))
    assert registration()['manifest']['persistence'] is False


@pytest.mark.parametrize('kind',['cancel','control','publication','accounting','identity','cleanup','unknown'])
def test_new_path_stops_remaining_rows_on_uncertainty(tmp_path,monkeypatch,kind):
    reg,api,source,launch,events=world(tmp_path,monkeypatch)
    if kind=='cancel':source.after=lambda _:setattr(api,'ref_moved',True)
    elif kind=='control':api.fail=lambda method,path:'/contents/' in path
    elif kind=='publication':api.lost=True
    elif kind=='accounting':
        a=audit(launch.rows[0]);a['resource']['requests_attempted']=None;source.values[0]=a
    elif kind=='identity':
        a=audit(launch.rows[0]);a['requested_interval']=['2026-01-01','2026-01-07'];source.values[0]=a
    elif kind=='cleanup':
        a=audit(launch.rows[0]);a['cleanup']='UNKNOWN';source.values[0]=a
    else:source.values[0]=audit(launch.rows[0],complete=False)
    out=launch.execute()
    assert len(source.calls)<=1 and out['status']=='STOP_RECONCILE_NO_RETRY'
    assert out['not_attempted'][-1]['council']=='tameside' and not out['coverage_advance']


@pytest.mark.parametrize('council,local,allowed',[('bury','timeout',False),('oldham','timeout',True),('oldham','selector',True),('tameside','timeout',True),('tameside','selector',False),('rochdale','timeout',True)])
def test_exact_council_continuation_not_portal_family(tmp_path,monkeypatch,council,local,allowed):
    plan=selection(councils=(council,));reg,api,source,launch,events=world(tmp_path,monkeypatch,plan)
    value=audit(launch.rows[0],local=local)
    launch.proof_check(0,value);state=launch.accept(0,value)
    code=launch.local_outcome(0,value,state)
    assert (code is not None)==allowed


def test_actual_worker_derives_selection_and_refuses_changed_child_binding(tmp_path,monkeypatch):
    reg=registration();path=tmp_path/'reg.json';path.write_bytes(canonical(reg));group=tmp_path/'source';group.mkdir()
    calls=[]
    def reader(row,**kwargs):
        calls.append((row,kwargs));return audit(row)
    monkeypatch.setattr(r,'owner_source_context',lambda budget: calls.append(budget))
    monkeypatch.setattr(r.finite,'read',reader)
    for index,row in enumerate(reg['manifest']['rows']):
        r.worker(index,tmp_path/f'{index}.json',group,campaign_registration=path,campaign_registration_sha256=r.sha(path.read_bytes()))
        actual,kw=calls[-1];assert actual==row and kw['campaign_scope']==row and kw['no_transport_retry'] and kw['fixed_four_rows']
        assert kw['execution_budget']==('BROWSER_SOURCE_V2' if row['council']=='rochdale' else None)
    with pytest.raises(r.Stop,match='CAMPAIGN_CHILD_BINDING'):
        r.worker(0,tmp_path/'bad.json',group,campaign_registration=path,campaign_registration_sha256='0'*64)


def test_source_command_carries_exact_registration_and_ordinal(tmp_path):
    reg=registration();source=r.Source(type('Memory',(),{'source':tmp_path/'source'})(),reg,tmp_path)
    for i in range(3):
        command=source.command(i,tmp_path/f'out-{i}')
        assert command[4]==str(i) and '--campaign-registration' in command and '--three-council-successor' not in command
        assert command[-1]==r.sha(canonical(reg))


def test_hash_rejects_numerically_equal_noncanonical_plan_values():
    p=selection();p['finite_manifest']['limits']['requests']=1200.0
    with pytest.raises(r.Stop):registration(p)


def test_multiple_windows_are_generator_partitions_not_supplied_intervals(tmp_path,monkeypatch):
    plan=selection('2026-11-01','2026-11-10',('oldham',))
    reg,api,source,launch,events=world(tmp_path,monkeypatch,plan)
    assert [(v['start'],v['end']) for v in launch.rows]==[('2026-11-01','2026-11-07'),('2026-11-08','2026-11-10')]
    out=launch.execute()
    assert out['status']=='MANIFEST_OBSERVATIONS_COMPLETE' and source.calls==[0,1]


@pytest.mark.parametrize('council',['oldham','rochdale'])
def test_existing_finite_reader_propagates_only_explicit_exact_row_to_children(tmp_path,monkeypatch,council):
    from verification.discovery import finite_acceptance as finite
    row=campaign.select(selection(councils=(council,)))[0]
    called=[]
    if council=='oldham':
        def supervise(command,**kwargs):
            called.append(command)
            assert json.loads(command[command.index('--campaign-scope')+1])==row
            assert '--no-transport-retry' in command and '--fixed-four-row-limit' in command
            Path(command[command.index('--output')+1]).write_text(json.dumps(audit(row)))
            return 0,False
        monkeypatch.setattr(finite,'supervise',supervise)
    else:
        from verification.direct_reference import instrumented_probe
        def supervised(case,output,**kwargs):
            called.append(case)
            assert proof.current_manifest_scope()==row and kwargs['window']==(row['start'],row['end'])
            output.write_text(json.dumps(audit(row)))
        monkeypatch.setattr(instrumented_probe,'supervised',supervised)
    value=finite.read(row,retain_proof=True,no_transport_retry=True,fixed_four_rows=True,campaign_scope=row,
        **({'execution_budget':'BROWSER_SOURCE_V2','execution_mode':'four-council-owner-local'} if council=='rochdale' else {}))
    assert called and value['requested_interval']==[row['start'],row['end']] and proof.current_manifest_scope() is None
    with pytest.raises(ValueError,match='CAMPAIGN_READER_BINDING'):
        finite.read(row,retain_proof=True,no_transport_retry=True,fixed_four_rows=True,campaign_scope=dict(row,end='2026-11-08'))


def test_consumed_manifest_release_cannot_replay_slots(tmp_path,monkeypatch):
    reg,api,source,launch,events=world(tmp_path,monkeypatch)
    first=launch.execute();assert first['status']=='MANIFEST_OBSERVATIONS_COMPLETE'
    before=list(source.calls)
    second=launch.execute()
    assert second['status']=='STOP_RECONCILE_NO_RETRY' and second['reason']=='REGISTRATION_ALREADY_CONSUMED'
    assert source.calls==before


def test_expired_authority_stops_before_claim_and_source(tmp_path,monkeypatch):
    reg,api,source,launch,events=world(tmp_path,monkeypatch)
    launch.wall=lambda:r.stamp(reg['expires_at'])
    out=launch.execute()
    assert out['reason']=='REGISTRATION_EXPIRED_OR_FUTURE' and not source.calls
    assert not any(method in {'POST','PATCH'} for method,path in api.calls)


@pytest.mark.parametrize('change',[lambda m:m['limits'].update(requests=100.0),lambda m:m.update(persistence=0),lambda m:m.update(selected_ordinals=[3.0,4,7])])
def test_canonical_registration_binding_refuses_equal_but_differently_encoded_values(change):
    reg=registration();change(reg['manifest'])
    with pytest.raises(r.Stop):r.validate(reg,checkout=False)


def test_full_package_must_fit_before_expiry_before_any_claim(tmp_path,monkeypatch):
    reg,api,source,launch,events=world(tmp_path,monkeypatch)
    launch.wall=lambda:r.stamp(reg['expires_at'])-timedelta(seconds=10)
    result=launch.execute()
    assert result['reason']=='INITIAL_AUTHORITY_ALLOCATION' and not source.calls and not api.calls


@pytest.mark.parametrize('kwargs',[dict(successor=True),dict(execution_budget='BROWSER_SOURCE_V2')])
def test_campaign_worker_rejects_conflicting_legacy_selectors(tmp_path,kwargs):
    with pytest.raises(r.Stop,match='CAMPAIGN_MIXED_SELECTORS'):
        r.worker(0,tmp_path/'out',tmp_path/'source',campaign_registration=tmp_path/'absent',**kwargs)
