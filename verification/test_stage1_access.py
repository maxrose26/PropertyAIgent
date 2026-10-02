"""Synthetic admission/lease tests: no database, provider or real identities."""
import json
import pytest
from app.security import access


@pytest.fixture
def admission(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(access.time, 'time', lambda: clock[0])
    registry = access.LeaseRegistry()
    registry.middleware_ready = True
    monkeypatch.setattr(access, 'registry', registry)
    policy = dict(version=1, enabled=True, environment='local', issuer='http://127.0.0.1:9999', client_id='test', web_processes=1, web_replicas=1, owner_subject='operator', paid_actions={'search.parse': True}, principals=[dict(issuer='http://127.0.0.1:9999', subject=s, role=r, enabled=True, workspace_id=1, buyer_ids=[1]) for s,r in [('operator','operator'),('reader','reader')]])
    path = tmp_path/'policy.json'
    path.write_text(json.dumps(policy))
    monkeypatch.setenv('PROPERTYAIGENT_ACCESS_POLICY', str(path))
    claims = dict(iss=policy['issuer'], sub='operator', iat=1000, exp=20000, aud='test', email_verified=True)
    return registry, claims, clock, path, policy


@pytest.mark.parametrize('change', [{'sub':'unknown'},{'iss':'https://wrong.invalid'},{'aud':'wrong'},{'email_verified':False},{'iat':True},{'exp':True},{'iat':999},{'iat':1001},{'exp':999},{'exp':None},{'sub':None},{'aud':['test','other']},{'azp':'other'}])
def test_invalid_claims_denied(admission, change):
    registry, claims, *_ = admission
    with pytest.raises(access.AccessDenied):
        registry.issue(dict(claims, **change), 'cookie')


def test_permissions_and_explicit_buyer_grants(admission):
    registry, claims, *_ = admission
    with pytest.raises(access.AccessDenied): access.require_admitted()
    for subject in ('reader','operator'):
        actor = registry.issue(dict(claims,sub=subject),'cookie-'+subject)
        with access.actor_scope(actor):
            assert access.require_buyer(1,1) is actor
            with pytest.raises(access.AccessDenied): access.require_buyer(1,2)
            with pytest.raises(access.AccessDenied): access.require_buyer(2,1)
            if subject == 'reader':
                with pytest.raises(access.AccessDenied): access.require_operator()
            else:
                assert access.require_operator('search.parse',paid=True) is actor
                with pytest.raises(access.AccessDenied): access.require_operator('disabled',paid=True)


def test_logout_extra_cookie_and_alternate_serialization_replay_denied(admission,monkeypatch):
    registry, claims, *_ = admission
    from streamlit.web.server.starlette.starlette_app_utils import create_signed_value
    monkeypatch.setattr('streamlit.web.server.server_util.get_cookie_secret',lambda:'synthetic-secret')
    signed=create_signed_value('synthetic-secret','_streamlit_user','fixture').decode()
    cookie = registry.fingerprint({'_streamlit_user':signed})
    actor = registry.issue(claims,cookie)
    registry.revoke(cookie)
    assert registry.fingerprint({'_streamlit_user':signed,'_streamlit_user_junk':'ignored','_streamlit_user_99':'ignored'}) == cookie
    for key in (cookie,'different-valid-serialization'):
        with pytest.raises(access.AccessDenied): registry.issue(claims,key)
    with pytest.raises(access.AccessDenied): registry.check(actor)


def test_idle_new_tab_cannot_restart_old_issuance(admission):
    registry, claims, clock, *_ = admission
    registry.issue(claims,'cookie')
    clock[0] += 2000
    with pytest.raises(access.AccessDenied): registry.issue(claims,'new-tab')


def test_heartbeat_check_never_renews_idle(admission):
    registry, claims, clock, *_ = admission
    actor = registry.issue(claims,'cookie')
    clock[0] += 1799
    registry.check(actor)
    clock[0] += 1
    with pytest.raises(access.AccessDenied): registry.check(actor)


def test_revision_revocation_and_missing_policy(admission):
    registry, claims, _, path, policy = admission
    actor = registry.issue(claims,'cookie')
    policy['principals'][0]['buyer_ids'] = []
    path.write_text(json.dumps(policy))
    with pytest.raises(access.AccessDenied): registry.check(actor)
    path.unlink()
    with pytest.raises(access.AccessUnavailable): registry.check(actor)


def test_restart_requires_new_token(admission):
    _, claims, clock, *_ = admission
    clock[0] += .1
    registry = access.LeaseRegistry(); registry.middleware_ready = True
    with pytest.raises(access.AccessDenied): registry.issue(claims,'cookie')


def test_direct_router_without_middleware_denied(admission):
    registry, claims, *_ = admission
    registry.middleware_ready = False
    with pytest.raises(access.AccessUnavailable): registry.issue(claims,'cookie')


@pytest.mark.parametrize('change',[{'enabled':False},{'web_replicas':2},{'owner_subject':'missing'},{'environment':'unknown'},{'principals':[]},{'client_id':''}])
def test_invalid_policy_closed(admission,change):
    _,_,_,path,policy=admission
    path.write_text(json.dumps(dict(policy,**change)))
    with pytest.raises(access.AccessUnavailable): access.load_policy()


def test_chunked_cookie_fingerprints_isolate_principals_and_ignore_junk(admission,monkeypatch):
    from streamlit.web.server.starlette.starlette_app_utils import create_signed_value
    monkeypatch.setattr('streamlit.web.server.server_util.get_cookie_secret',lambda:'synthetic-secret')
    registry,*_=admission
    def sign(name,value):return create_signed_value('synthetic-secret',name,value).decode()
    base=sign('_streamlit_user','chunks-2')
    a={'_streamlit_user':base,'_streamlit_user_1':sign('_streamlit_user_1','principal A'),'_streamlit_user_2':sign('_streamlit_user_2','payload')}
    b=dict(a,_streamlit_user_1=sign('_streamlit_user_1','principal B'))
    assert registry.fingerprint(a)!=registry.fingerprint(b)
    assert registry.fingerprint(a)==registry.fingerprint(dict(a,_streamlit_user_3='ignored',_streamlit_user_tokens='ignored'))
    with pytest.raises(access.AccessDenied):registry.fingerprint({'_streamlit_user':base})


@pytest.mark.parametrize('value',[[],None,'invalid',42])
def test_malformed_machine_container_fails_closed(admission,value):
    _,_,_,path,policy=admission;policy['machines']=value;path.write_text(json.dumps(policy))
    with pytest.raises(access.AccessUnavailable,match='Application access is unavailable'):access.load_policy()
