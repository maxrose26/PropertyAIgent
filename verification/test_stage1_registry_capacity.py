"""Bounded registry and replay accounting, without teardown/GC-based reclamation."""
import concurrent.futures
import pytest
from app.security import access
from verification.test_stage1_access import admission


def fast_policy(admission, monkeypatch):
    registry,claims,clock,*_=admission
    policy=access.load_policy();monkeypatch.setattr(access,'load_policy',lambda:policy)
    return registry,claims,clock,policy


def test_capacity_reclaims_expired_and_reuses_active(admission,monkeypatch):
    r,c,t,p=fast_policy(admission,monkeypatch)
    actors=[r.issue(dict(c,exp=1100),str(i)) for i in range(10000)]
    assert r.issue(dict(c,exp=1100),'0',actors[0]) is actors[0]
    with pytest.raises(access.AccessUnavailable):r.issue(c,'overflow')
    t[0]=30000
    fresh=r.issue(dict(c,iat=30000,exp=31000),'fresh')
    assert r.check(fresh) is fresh
    assert len(r.leases)==len(r.issuances)==len(r.issuance_revisions)==1
    assert not r.revoked_issuances
    with pytest.raises(access.AccessDenied):r.issue(dict(c,exp=100000),'old-long-exp')


def test_expired_lease_cannot_revive_same_issuance_longer_exp(admission,monkeypatch):
    r,c,t,p=fast_policy(admission,monkeypatch)
    r.issue(dict(c,exp=1010),'first');t[0]=1011
    with pytest.raises(access.AccessDenied):r.issue(c,'another-cookie')
    assert len(r.leases)==0 and len(r.revoked_issuances)==1


@pytest.mark.parametrize('mode',['logout','idle','revision'])
def test_replay_tombstone_retained_until_horizon(admission,monkeypatch,mode):
    r,c,t,p=fast_policy(admission,monkeypatch);a=r.issue(c,'cookie')
    if mode=='logout':r.revoke('cookie')
    elif mode=='idle':t[0]+=1800
    else:p['_revision']='changed'
    with pytest.raises(access.AccessDenied):r.issue(c,'new-tab')
    p['_revision']=a.revision
    with pytest.raises(access.AccessDenied):r.issue(c,'restored-policy')
    assert len(r.revoked_issuances)==1
    t[0]=29800
    fresh=r.issue(dict(c,iat=29800,exp=30000),'fresh')
    assert r.check(fresh) is fresh and not r.revoked_issuances


def test_clock_rollback_denied(admission,monkeypatch):
    r,c,t,p=fast_policy(admission,monkeypatch);a=r.issue(c,'cookie');t[0]+=10;r.check(a);t[0]-=1
    with pytest.raises(access.AccessUnavailable):r.check(a)


def test_concurrent_issue_logout_and_reclamation(admission,monkeypatch):
    r,c,t,p=fast_policy(admission,monkeypatch)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        actors=list(pool.map(lambda i:r.issue(c,str(i)),range(200)))
        list(pool.map(lambda a:r.revoke(a.cookie_key),actors))
    assert not r.leases and len(r.revoked_issuances)==1
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        def denied(i):
            with pytest.raises(access.AccessDenied):r.issue(c,str(i))
        list(pool.map(denied,range(200)))
    t[0]=30000
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i:r.issue(dict(c,iat=30000,exp=40000),str(i)),range(200)))
    assert len(r.leases)==200 and len(r.issuances)==len(r.issuance_revisions)==1
    assert not r.revoked_issuances


def test_all_issuance_collections_bounded_without_evicting_revocations(admission,monkeypatch):
    r,c,t,p=fast_policy(admission,monkeypatch)
    t[0]=11000
    for i in range(10000):
        cc=dict(c,iat=1000+i,exp=50000);a=r.issue(cc,str(i));r.revoke(a.cookie_key)
    assert len(r.issuances)==len(r.issuance_revisions)==len(r.revoked_issuances)==10000
    with pytest.raises(access.AccessUnavailable):r.issue(dict(c,iat=11000,exp=50000),'fresh')
    with pytest.raises(access.AccessDenied):r.issue(dict(c,iat=10999,exp=50000),'replay')
    t[0]=39800
    assert r.issue(dict(c,iat=39800,exp=50000),'later')
    assert len(r.issuances)==len(r.issuance_revisions)==1 and not r.revoked_issuances


def test_threads_sampling_before_lock_do_not_create_false_clock_rollback(admission,monkeypatch):
    import threading
    r,c,t,p=fast_policy(admission,monkeypatch)
    ready=threading.Event();finished=threading.Event();real_lock=threading.RLock();local=threading.local()
    class OrderedLock:
        def __enter__(self):
            if threading.current_thread().name=='A' and not getattr(local,'entered',False):
                local.entered=True;ready.set();assert finished.wait(3)
            real_lock.acquire();return self
        def __exit__(self,*a):real_lock.release()
    def clock():
        if threading.current_thread().name=='A':
            local.samples=getattr(local,'samples',0)+1
            return 1000 if local.samples==1 else 1002
        return 1001
    r.lock=OrderedLock();monkeypatch.setattr(access.time,'time',clock);errors=[]
    def first():
        try:r.issue(c,'A')
        except Exception as exc:errors.append(exc)
    a=threading.Thread(target=first,name='A');a.start();assert ready.wait(3)
    r.issue(c,'B');finished.set();a.join(3)
    assert not a.is_alive() and errors==[] and len(r.leases)==2


def test_native_logout_before_first_lease_prevents_replay(admission,monkeypatch):
    import json
    from streamlit.web.server.starlette.starlette_app_utils import create_signed_value
    r,c,t,p=fast_policy(admission,monkeypatch)
    monkeypatch.setattr('streamlit.web.server.server_util.get_cookie_secret',lambda:'synthetic')
    def cookie(claims):return {'_streamlit_user':create_signed_value('synthetic','_streamlit_user',json.dumps(claims)).decode()}
    r.revoke_native(cookie(c))
    with pytest.raises(access.AccessDenied):r.issue(c,r.fingerprint(cookie(c)))
    assert len(r.issuances)==len(r.issuance_revisions)==len(r.revoked_issuances)==1
    t[0]+=1;fresh=dict(c,iat=1001)
    assert r.issue(fresh,r.fingerprint(cookie(fresh)))


def test_native_logout_capacity_preserves_active_and_required_tombstones(admission,monkeypatch):
    import json
    from streamlit.web.server.starlette.starlette_app_utils import create_signed_value
    r,c,t,p=fast_policy(admission,monkeypatch);t[0]=11000
    monkeypatch.setattr('streamlit.web.server.server_util.get_cookie_secret',lambda:'synthetic')
    def cookie(i):return {'_streamlit_user':create_signed_value('synthetic','_streamlit_user',json.dumps(dict(c,iat=i))).decode()}
    active=r.issue(dict(c,iat=11000),'active')
    for i in range(1000,10999):r.revoke_native(cookie(i))
    assert len(r.issuances)==10000 and len(r.revoked_issuances)==9999
    r.revoke_native(cookie(10999))
    assert len(r.issuances)==10000 and r.check(active) is active
    assert r.issue(dict(c,iat=11000),'active',active) is active
    with pytest.raises(access.AccessDenied):r.issue(dict(c,iat=10999),'copied')
    t[0]=39800
    assert r.issue(dict(c,iat=39800,exp=41000),'fresh')
    assert len(r.issuances)==1 and not r.revoked_issuances
