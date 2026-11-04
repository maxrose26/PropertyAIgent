"""Real codec/Vault; synthetic metadata only, no provider or database effects."""
import copy,hashlib,zlib,base64
import pytest
from verification.ingestion_storage import owner_pilot as p
from tests.test_attempt04_cleanup_capacity import pilot_with_retained_state


def example():
    memberships=[dict(role='runtime',member='worker',grantor='postgres',admin_option=False,inherit_option=True,set_option=True,index=i) for i in range(40)]
    return dict(period=p.PERIOD,cleanup_reserve=dict(p.cleanup_reserve_policy(),cleanup_writes=0),binding={'scope':'x'*1500},policy={'profile':'x'*3000},profile={'directory':'/approved/'*100},access={'binding':{'scope':'x'*1500},'original_memberships':memberships,'passwords':{'synthetic':'SECRET_SENTINEL'*5}},intents={'ONE_JOB':{'state':'INTENT_NO_RETRY'}},first_failure={'reason':'OWNER_JOB_ACK_UNCERTAIN'})


def test_lossless_metadata_and_real_encryption_preserve_intents_failure_and_secrets():
    original=example();before=copy.deepcopy(original)
    packed=p.serialized_state(original)
    assert original==before and len(p.canonical(packed))<len(p.canonical(original))-5000
    assert packed['access']['version']=='JOURNAL_METADATA_DEFLATE_V1'
    assert p.hydrated_state(copy.deepcopy(packed))==original
    obj=pilot_with_retained_state(original)
    assert obj.journal.load()==original and b'SECRET_SENTINEL' not in obj.db.rows[-1][1]
    assert obj.state['first_failure']==before['first_failure'] and obj.state['intents']==before['intents']


@pytest.mark.parametrize('change',['hash','length','trailing','bomb'])
def test_corruption_or_unbounded_decompression_refuses(change):
    packed=p.serialized_state(example());item=packed['policy']
    if change=='hash':item['sha256']='0'*64
    if change=='length':item['bytes']+=1
    if change=='trailing':item['data']=base64.b64encode(base64.b64decode(item['data'])+b'extra').decode()
    if change=='bomb':item.update(bytes=32768,data=base64.b64encode(zlib.compress(b'x'*1000000)).decode(),sha256=hashlib.sha256(b'x'*1000000).hexdigest())
    with pytest.raises(p.op.Denied,match='OWNER_CODE_BINDING'):p.hydrated_state(packed)


def test_legacy_history_and_cleanup_reserve_policy_unchanged():
    old=example();old.pop('cleanup_reserve')
    assert p.serialized_state(old)==old and p.hydrated_state(copy.deepcopy(old))==old
    policy=p.cleanup_reserve_policy()
    assert policy['reserved_snapshots']==16 and policy['normal_plaintext_ceiling']==16534
    assert policy['growth_bytes']==6937 and policy['margin_bytes']==1024
    assert p.ciphertext_size(16534)==22152 and p.ciphertext_size(16534+6937+1024)==32756
