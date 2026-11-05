"""Exact Attempt07 startup receipt recovery; no provider mutation or job retry."""
import copy
import hashlib
import json
import os

PERIOD='b-dbpilot-20261027-1102-07'
JOB='job-dbm710tg1s2s73ca9v90'
DEPLOY='dep-dbm702rbc2fs738gfuv0'
REVISION='54700366bab5434a5cda30abc853e0dc6dcc5d33'
TREE='95bfb2677cddfe539b8b69945d870f6c8b5eb62e'
RECEIPT_SHA='57e083c78c06baa17eb13a0b97378084d068d11d6c5c476dc9caf2b27bfcfe5c'
JOURNAL_SHA='88509db1ffee3b4d0443d8bf55000e776944687e66d01df411e2b435986f3c61'

def reconcile(p,cfg):
    from . import owner_pilot as m
    require=m.op.require
    require(set(cfg)=={'version','receipt'} and cfg['version']=='ATTEMPT07_STARTUP_RECEIPT_V1','OWNER_STARTUP_RECONCILIATION_CONFIGURATION')
    receipt=cfg['receipt'];sha=hashlib.sha256(m.canonical(receipt)).hexdigest()
    release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
    require(sha==RECEIPT_SHA and receipt.get('period')==PERIOD and receipt.get('tree')==release.get('tree')==TREE and
        receipt.get('execution_binding')==release.get('execution_binding') and receipt['execution_binding']['revision']==REVISION and
        receipt.get('status')=='CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION' and receipt.get('cwd')=='/opt/render/project/src' and
        receipt.get('git')=={'exit_status':0,'tracked_changes':False} and receipt.get('authentication_attempts')==0 and receipt.get('source_requests')==0,
        'OWNER_STARTUP_RECONCILIATION_RECEIPT')
    entry=dict(version='ATTEMPT07_STARTUP_RECEIPT_V1',job_id=JOB,deployment=DEPLOY,receipt_sha256=sha,refusal_snapshot_sha256=JOURNAL_SHA)
    p.state=p.journal.load();s=p.state
    require(s is not None and s.get('period')==PERIOD and s.get('deployment')==DEPLOY and
        s.get('status') in ('PREPARATION_REFUSED','ARTIFACT_READY') and
        not any(k in s for k in ('binding','access','job','period_journal')) and 'RELEASE' not in s.get('intents',{}) and 'ONE_JOB' not in s.get('intents',{}),
        'OWNER_STARTUP_RECONCILIATION_STATE')
    failure={'exception_class':'ReadTimeout','phase':'STARTUP_PREFLIGHT_JOB','reason':'UNKNOWN_FAILURE','sqlstate':None,'status':'RECONCILIATION_REQUIRED'}
    require(s.get('failure')==failure and s.get('startup_job',{}).get('id')==JOB and s.get('startup_job_terminal',{}).get('id')==JOB and
        s['startup_job_terminal'].get('status')=='succeeded' and s['startup_job_terminal'].get('finishedAt') and
        all(s.get('intents',{}).get(k,{}).get('state')=='ACKNOWLEDGED' for k in
            ('BUILD_ENVIRONMENT','BUILD_CONFIGURATION','ONE_RESUME_BUILD','RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT','STARTUP_PREFLIGHT_JOB')),
        'OWNER_STARTUP_RECONCILIATION_PREDECESSOR')
    prior=s.get('startup_reconciliation')
    if prior is None:
        require(p.journal.previous==JOURNAL_SHA and p.journal.ordinal==21 and s['status']=='PREPARATION_REFUSED' and 'startup_preflight' not in s,'OWNER_STARTUP_RECONCILIATION_ORIGINAL')
    else:require(prior==entry,'OWNER_STARTUP_RECONCILIATION_CONFLICT')
    # Read the acknowledged job and complete terminal inventory. No POST route.
    with p.api() as api:
        job=api.call('GET','/jobs/'+JOB)
        jobs=m.complete_inventory(api.call('GET','/jobs?limit=100'),'job')
    started=s['intents']['BUILD_ENVIRONMENT']['at']
    recent=[j for j in jobs if m.datetime.fromisoformat(j['createdAt'].replace('Z','+00:00')).timestamp()>=started]
    require(len(recent)==1 and recent[0]['id']==JOB and job.get('id')==JOB and job.get('serviceId')==m.SERVICE and
        job.get('status')=='succeeded' and job.get('finishedAt') and job.get('startCommand')==s.get('startup_command'),
        'OWNER_STARTUP_RECONCILIATION_JOB_HISTORY')
    before=(p.journal.previous,p.journal.ordinal)
    observed=p.inspect();current=observed['current_readback']
    require((p.journal.previous,p.journal.ordinal)==before,'OWNER_STARTUP_RECONCILIATION_CONCURRENT_STATE')
    require(current['configuration_equal'] and current['environment_equal'] and current['suspended'] and
        current['latest_deployment']==DEPLOY and current['latest_revision']==REVISION and current['jobs_since_preparation']==1 and
        not observed['period_present'] and observed['attempt_authorities']['count']==0 and observed['temporary_owner_absent'] and
        observed['pipeline_session_count']==observed['runtime_membership_count']==0 and observed['stable_verifier_binding']=='MATCH' and
        len(observed['runtime_roles'])==2 and all(not r['login'] and not r['password_null'] for r in observed['runtime_roles']),
        'OWNER_STARTUP_RECONCILIATION_CURRENT_STATE')
    startup=dict(job_id=JOB,receipt=receipt,sha256=sha,readback=dict(runtime_access='DISABLED',configuration_equal=True,environment_equal=True,suspended=True))
    if prior is not None:
        require(p.state.get('startup_preflight')==startup and p.state.get('preparation_failure')==failure,'OWNER_STARTUP_RECONCILIATION_CONFLICT')
    else:
        p.state.update(startup_reconciliation=entry,startup_preflight=startup,preparation_failure=copy.deepcopy(failure))
        p.save()  # remains refused until independent durable load verifies receipt
    saved=p.journal.load()
    require(saved.get('startup_reconciliation')==entry and saved.get('startup_preflight')==startup and saved.get('failure')==failure and
        saved.get('preparation_failure')==failure,'OWNER_STARTUP_RECONCILIATION_DURABLE_READBACK')
    p.state=saved
    if saved['status']=='PREPARATION_REFUSED':
        p.state['status']='ARTIFACT_READY';p.save()
        p.state=p.journal.load()
        require(p.state.get('status')=='ARTIFACT_READY' and p.state.get('startup_reconciliation')==entry and p.state.get('startup_preflight')==startup,
            'OWNER_STARTUP_RECONCILIATION_DURABLE_READBACK')
    return p.summary()

# Independently retrieved Render receipt; no secret or source data.
RECEIPT=json.loads("{\"authentication_attempts\":0,\"cwd\":\"/opt/render/project/src\",\"execution_binding\":{\"manifest_sha256\":\"482e137a9a62fdd1007ee351845a4fc2c0825693dfc3472217c2ac8d4c3b74fc\",\"revision\":\"54700366bab5434a5cda30abc853e0dc6dcc5d33\",\"workflow_sha256\":\"e5289d43dbd05f2ffa051529c4feeb6aa32fb719c621de00df3638e077bf78e4\"},\"git\":{\"exit_status\":0,\"tracked_changes\":false},\"period\":\"b-dbpilot-20261027-1102-07\",\"source_requests\":0,\"status\":\"CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION\",\"tree\":\"95bfb2677cddfe539b8b69945d870f6c8b5eb62e\",\"version\":\"RENDER_STARTUP_GUARD_V1\"}")

