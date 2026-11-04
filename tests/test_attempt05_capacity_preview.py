import copy,hashlib
import pytest
from tests.test_attempt04_release_binding import pilot
from tests.test_attempt04_cleanup_capacity import pilot_with_retained_state
from verification.ingestion_storage import owner_pilot as p

@pytest.mark.parametrize('oversized',[False,True])
def test_actual_preview_uses_prepared_baseline_and_never_writes_or_opens(pilot,monkeypatch,oversized):
    obj,state,_,_=pilot;b,policy=obj.release_preflight()
    state['stable_credentials']['passwords']={r:'s'*64 for r in p.op.ROLES}
    if oversized:state['retained_padding']='x'*10000
    clone=pilot_with_retained_state(state);raw=clone.db.rows[0][1]
    clone.db.rows=[(22,raw,hashlib.sha256(raw).hexdigest())];clone.state=clone.journal.load()
    calls=[]
    def prepare(c,b,**kw):
        calls.append('READ_ONLY_BASELINE')
        return dict(version='FINITE_INTAKE_ACCESS_STATE_V1',binding=copy.deepcopy(b),state='ARMED_BEFORE_ACTIVATION',prior_settings={},original_memberships=[],passwords=kw['stable_credentials'])
    monkeypatch.setattr(p.op,'prepare_activation',prepare)
    monkeypatch.setattr(p.op,'activate',lambda *a,**kw:pytest.fail('ACCESS_OPENED'))
    if oversized:
        with pytest.raises(p.op.Denied,match='CLEANUP_'):clone.preview_release_capacity(b,policy)
    else:
        result=clone.preview_release_capacity(b,policy)
        assert result['starting']['ordinal']==22 and result['remaining_normal_bytes']>0 and result['provider_mutations']==0
        assert max(result['projected_ciphertext_bytes'].values())<=22152 and calls==['READ_ONLY_BASELINE']
    assert len(clone.db.rows)==1 and clone.db.rows[0][1]==raw
