"""Archive refusal without secret output or any mutation capability."""
import copy
import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import tameside_preparation as prep


def fixture(change=None):
    canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')).encode()
    prior=dict(period='b-bolton-20261103-1105-01',original_service={'private':'not logged'},
        original_deploy_ids=['old'],build_guard='guard',build_environment={'private':'not logged'},
        build_receipt_created_at='2026-11-03T11:05:00Z',original_environment={'private':'not logged'},
        original_guard='original-guard')
    raw=canonical(prior);sha=hashlib.sha256(raw).hexdigest()
    fields={k:hashlib.sha256(canonical(prior[k])).hexdigest() for k in
        ('original_service','original_deploy_ids','build_guard','build_environment','build_receipt_created_at')}
    state={k:copy.deepcopy(prior[k]) for k in ('period','original_environment','original_guard')}
    state.update(status='CLOSED',closed_build_archive=dict(prior_ordinal=22,prior_ciphertext_sha256=sha,fields=fields))
    returned=[1,len(raw),raw];calls=[];decodes=[]
    if change=='reference':state['closed_build_archive']['prior_ordinal']=55
    if change=='field':fields['build_guard']='0'*64
    if change=='conflict':state['original_service']={'different':True}
    if change=='missing':returned[:]=[0,None,None]
    if change=='duplicate':returned[:]=[2,None,None]
    if change=='oversize':returned[:]=[1,32769,None]
    if change=='stored_hash':returned[2]=None
    if change=='ciphertext':returned[2]=b'corrupted'
    if change=='baseline':state['original_guard']='changed'
    class DB:
        key='fixture'
        @contextmanager
        def connection(self):yield self
        def execute(self,q,params=None):
            calls.append(q)
            if 'WITH matches' in q:
                assert params[:3]==('b-bolton-20261103-1105-01_owner',
                    hashlib.sha256(b'b-bolton-20261103-1105-01_owner').hexdigest()[:32],'owner/state-022')
                assert 'LIMIT 2' in q and 'octet_length(body)<=32768' in q
                if change=='permission':raise PermissionError('archive SELECT unavailable')
            else:assert q in ('BEGIN READ ONLY','ROLLBACK')
            return SimpleNamespace(fetchone=lambda:tuple(returned))
    class Journal:
        def __init__(self,db,period):self.db=db;self.ordinal=55;self.previous=prep.CHECKPOINT_SHA
        def load(self):return copy.deepcopy(state)
        def _vault(self,raw):decodes.append(True);return json.loads(raw)
    pinned=SimpleNamespace(Journal=Journal,PERIOD='frozen-default',canonical=canonical)
    return pinned,DB(),calls,decodes


def test_valid_archive_uses_exact_private_readonly_row():
    pinned,db,calls,decodes=fixture()
    value=prep.original_checkpoint(pinned,db)
    assert value['original_service']=={'private':'not logged'} and decodes==[True]
    assert calls[0]=='BEGIN READ ONLY' and calls[-1]=='ROLLBACK'


@pytest.mark.parametrize('change',['reference','field','conflict','missing','duplicate','oversize',
                                   'stored_hash','ciphertext','baseline','permission'])
def test_refusal_precedes_any_recovery_or_provider_effect(change):
    pinned,db,calls,decodes=fixture(change)
    with pytest.raises((ValueError,PermissionError)):
        prep.prepare_stopped(db,pinned=pinned,recovery=None,binding=None,journal_source=None,
            api_factory=lambda:pytest.fail('provider used'),revision='1'*40,checkpoint={},baseline={})
    if change in ('reference','missing','duplicate','oversize','stored_hash','ciphertext','permission'):
        assert not decodes
    assert all(q in ('BEGIN READ ONLY','ROLLBACK') or 'WITH matches' in q for q in calls)


def test_stop15_replacement_references_immutable_row18_without_copying_77_ids():
    from verification.ingestion_storage import stop15_replacement, tameside_stop15 as plan
    canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')).encode()
    ids=['dep-'+hashlib.sha256(str(i).encode()).hexdigest()[:20] for i in range(77)]
    state=dict(elapsed_package=dict(ordinal=18,sha256=plan.CHECKPOINT),
               original_deploy_ids=ids)
    ref=stop15_replacement.prior_deploy_reference(state,SimpleNamespace(canonical=canonical))
    assert ref==dict(ordinal=18,checkpoint_sha256=plan.CHECKPOINT,count=77,
                     members_sha256=hashlib.sha256(canonical(ids)).hexdigest())
    assert all(item not in json.dumps(ref) for item in ids)
    assert state['original_deploy_ids']==ids


@pytest.mark.parametrize('mutation',['ordinal','sha256','malformed'])
def test_stop15_replacement_rejects_untrusted_deploy_history_reference(mutation):
    from verification.ingestion_storage import stop15_replacement, tameside_stop15 as plan
    state=dict(elapsed_package=dict(ordinal=18,sha256=plan.CHECKPOINT),
               original_deploy_ids=['dep-prior'])
    if mutation=='ordinal':state['elapsed_package']['ordinal']=19
    if mutation=='sha256':state['elapsed_package']['sha256']='0'*64
    if mutation=='malformed':state['original_deploy_ids']='dep-prior'
    with pytest.raises(ValueError,match='STOP15_OLD_DEPLOYMENT_'):
        stop15_replacement.prior_deploy_reference(state,SimpleNamespace(
            canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')).encode()))
