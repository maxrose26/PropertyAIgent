"""Focused transport, vault and anonymous-pipe tests; no external API calls."""
import copy
import json
import os
from pathlib import Path
import sys
import time

import pytest
from verification.ingestion_storage.intake_owner import Denied, ROLES
from verification.ingestion_storage.intake_owner_io import (Vault, handoff, reconcile_handoff,
    restore_handoff, service_guard, env_values, SERVICE)
from verification.ingestion_storage.intake_owner_client import capture


def test_vault_authenticated_private_and_reloadable_for_independent_closure(tmp_path):
    p=tmp_path/'state.bin';v=Vault(p,'synthetic passphrase more than 24 chars',create=True)
    v.save(dict(password='SYNTHETIC_NOT_PRODUCTION',state='ARMED'))
    assert b'SYNTHETIC_NOT_PRODUCTION' not in p.read_bytes() and p.stat().st_mode&0o777==0o600
    assert Vault(p,'synthetic passphrase more than 24 chars').load()['state']=='ARMED'
    with pytest.raises(Exception):Vault(p,'wrong synthetic key more than 24').load()
    raw=p.read_bytes();p.write_bytes(raw[:-4]+b'xxxx')
    with pytest.raises(Exception):v.load()


def test_vault_refuses_unsafe_reuse_symlink_and_overflow(tmp_path):
    p=tmp_path/'vault';v=Vault(p,'synthetic passphrase more than 24 chars',create=True);v.save(dict(state='ARMED'))
    with pytest.raises(FileExistsError):Vault(p,'synthetic passphrase more than 24 chars',create=True)
    (tmp_path/'link').symlink_to(p)
    with pytest.raises(Denied):Vault(tmp_path/'link','synthetic passphrase more than 24 chars')
    before=p.read_bytes()
    with pytest.raises(Denied,match='32K'):v.save(dict(value='x'*40000))
    assert p.read_bytes()==before


class API:
    def __init__(self):
        self.env={'DATABASE_URL':'SYNTHETIC_UNRELATED_ADMIN_URL','OPENAI_API_KEY':'SYNTHETIC_AI',
                  'OTHER_SECRET':'SYNTHETIC_UNRELATED','INGESTION_RENDER_PROFILE':'',
                  'PLAYWRIGHT_BROWSERS_PATH':'/fixture/browser','PYTHONUNBUFFERED':'1'}
        self.service=dict(id=SERVICE,type='cron_job',suspended='suspended',autoDeploy='no',branch='master',
                          serviceDetails=dict(schedule='0 5 * * *',startCommand='/bin/true',buildCommand='unchanged'))
        self.calls=0;self.puts=0;self.fail_put=False;self.jobs=[]
    def call(self,method,suffix='',body=None):
        self.calls+=1
        if method=='PUT':
            self.puts+=1;self.env={x['key']:x['value'] for x in body}
            if self.fail_put:raise RuntimeError('synthetic lost acknowledgement')
            return []
        if suffix=='':return copy.deepcopy(self.service)
        if suffix=='/env-vars?limit=100':return [{'envVar':dict(key=k,value=v),'cursor':str(i)} for i,(k,v) in enumerate(self.env.items())]
        if suffix=='/jobs?limit=100':return self.jobs
        return dict(id=suffix.split('/')[-1],status='failed',finishedAt='2026-10-31T23:00:00Z')


def prepared(api):
    profile=dict(mode='render-intake-v1',service_id=SERVICE,revision='1'*40,aggregate_bytes=2000000000,
        browser_path='/fixture/browser',browser_sha256='8'*64,source_rss_bytes=1073741824,
        controller_rss_bytes=268435456,reserve_bytes=536870912,source_seconds=75)
    api.env['INGESTION_RENDER_PROFILE']=json.dumps(profile)
    b=dict(period='fixture',valid_until=time.time()+1800,publication_valid_until=time.time()+1700,
           route='POOLER',execution_binding=dict(revision='1'*40),render_config_sha256=service_guard(api.service),
           render_profile=profile,inherited_boundary=dict(service_id=SERVICE,env_groups=[],secret_files=[],
            inherited_credential_names=[],reviewed=True,observed_at=time.time()))
    return dict(state='ACTIVATION_ACKNOWLEDGED',binding=b,passwords={r:'SYNTHETIC_PASSWORD_48_CHARACTERS_MINIMUM_'+'x'*32 for r in ROLES})


def test_secure_handoff_excludes_all_unrelated_credentials_and_restores_exactly():
    api=API();state=prepared(api);original=copy.deepcopy(api.env);saved=[]
    handoff(api,state,lambda x:saved.append(copy.deepcopy(x)),'ghs_'+'x'*40)
    assert api.puts==1 and 'PUT_INTENT_NO_RETRY'==saved[0]['render']['state']
    assert not {'DATABASE_URL','OPENAI_API_KEY','OTHER_SECRET'}&set(api.env)
    assert set(api.env)&{'INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL','GH_TOKEN'}=={'INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL','GH_TOKEN'}
    state['state']='DATABASE_CLOSURE_ACKNOWLEDGED';api.calls=0
    result=restore_handoff(api,state,lambda _:None,'job-'+'a'*20)
    assert result['status']=='RESTORATION_VERIFIED' and api.env==original and api.puts==2


def test_uncertain_handoff_cannot_be_retried_and_has_read_only_reconciliation():
    api=API();state=prepared(api);api.fail_put=True
    with pytest.raises(RuntimeError):handoff(api,state,lambda _:None,'ghs_'+'x'*40)
    with pytest.raises(Denied):handoff(api,state,lambda _:None,'ghs_'+'x'*40)
    assert api.puts==1
    result=reconcile_handoff(api,state,lambda _:None)
    assert result['observed']=='EXPECTED' and api.puts==1


@pytest.mark.parametrize('drift',['groups','secret_files','old_receipt','allocation','controls','pub_token'])
def test_handoff_refuses_unreviewed_boundary_or_limits_before_put(drift):
    api=API();state=prepared(api)
    if drift=='groups':state['binding']['inherited_boundary']['env_groups']=['unreviewed']
    elif drift=='secret_files':state['binding']['inherited_boundary']['secret_files']=['unreviewed']
    elif drift=='old_receipt':state['binding']['inherited_boundary']['observed_at']-=600
    elif drift=='allocation':
        state['binding']['render_profile']['aggregate_bytes']=None
        api.env['INGESTION_RENDER_PROFILE']=json.dumps(state['binding']['render_profile'])
    elif drift=='controls':api.service['autoDeploy']='yes'
    token='fine_grained_but_no_self_revoke_route' if drift=='pub_token' else 'ghs_'+'x'*40
    with pytest.raises(Denied):handoff(api,state,lambda _:None,token)
    assert api.puts==0


def test_cancel_before_job_submission_has_exact_restoration_route():
    api=API();state=prepared(api);original=copy.deepcopy(api.env)
    handoff(api,state,lambda _:None,'ghs_'+'x'*40);state['state']='DATABASE_CLOSURE_ACKNOWLEDGED';api.calls=0
    assert restore_handoff(api,state,lambda _:None,None)['status']=='RESTORATION_VERIFIED' and api.env==original


def test_nojob_restore_refuses_active_or_posthandoff_job():
    api=API();state=prepared(api);handoff(api,state,lambda _:None,'ghs_'+'x'*40)
    state['state']='DATABASE_CLOSURE_ACKNOWLEDGED';api.jobs=[dict(job=dict(status='running',createdAt='2026-10-31T23:00:00Z'))]
    with pytest.raises(Denied):restore_handoff(api,state,lambda _:None,None)
    assert api.puts==1


def test_complete_env_page_required():
    with pytest.raises(Denied):env_values([dict(envVar=dict(key=str(i),value='synthetic')) for i in range(100)])


def test_existing_capture_has_combined_pipe_bound_and_anonymous_secret_input():
    readfd,writefd=os.pipe();os.write(writefd,b'SYNTHETIC_PIPE_SECRET');os.close(writefd)
    try:
        command=[sys.executable,'-c','import os,sys; v=os.read(int(sys.argv[1]),4096); print("PIPE_RECEIVED" if len(v)==21 else "BAD")',str(readfd)]
        data,status=capture(command,dict(PATH='/usr/bin:/bin'),seconds=4,ceiling=1024,pass_fds=(readfd,))
    finally:os.close(readfd)
    assert status['exit_code']==0 and b'PIPE_RECEIVED' in data and b'SYNTHETIC_PIPE_SECRET' not in data
    data,status=capture([sys.executable,'-c','import sys;sys.stdout.write("x"*10000)'],dict(PATH='/usr/bin:/bin'),seconds=4,ceiling=1024)
    assert len(data)<=1024 and status['reason']=='OUTPUT_OVERFLOW' and status['client_closed']
