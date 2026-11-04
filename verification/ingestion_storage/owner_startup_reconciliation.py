"""Exact Attempt06 startup receipt recovery; no provider mutation or job retry."""
import copy
import hashlib
import json
import os

PERIOD='b-dbpilot-20261027-1102-06'
JOB='job-dblqhbh42hec73e38980'
DEPLOY='dep-dblqglou01pc739atc6g'
REVISION='da8959d06bea35da5104fe6638aa566952004853'
TREE='f3708980efdcd46b5592dab10f81756b30bddb09'
RECEIPT_SHA='95f90d13dd2b3a2d11c529f15c49c614f41653c635218b0fdd121bd981204acd'
JOURNAL_SHA='ff0bd367e65534a2b55829cabf2e2ef436d8239cc8ed893042644dd0b371a42f'

def reconcile(p,cfg):
    from . import owner_pilot as m
    require=m.op.require
    require(set(cfg)=={'version','receipt'} and cfg['version']=='ATTEMPT06_STARTUP_RECEIPT_V1','OWNER_STARTUP_RECONCILIATION_CONFIGURATION')
    receipt=cfg['receipt'];sha=hashlib.sha256(m.canonical(receipt)).hexdigest()
    release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
    require(sha==RECEIPT_SHA and receipt.get('period')==PERIOD and receipt.get('tree')==release.get('tree')==TREE and
        receipt.get('execution_binding')==release.get('execution_binding') and receipt['execution_binding']['revision']==REVISION and
        receipt.get('status')=='CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION' and receipt.get('cwd')=='/opt/render/project/src' and
        receipt.get('git')=={'exit_status':0,'tracked_changes':False} and receipt.get('authentication_attempts')==0 and receipt.get('source_requests')==0,
        'OWNER_STARTUP_RECONCILIATION_RECEIPT')
    entry=dict(version='ATTEMPT06_STARTUP_RECEIPT_V1',job_id=JOB,deployment=DEPLOY,receipt_sha256=sha,refusal_snapshot_sha256=JOURNAL_SHA)
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
