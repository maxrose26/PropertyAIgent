"""Authenticated web adapter for the existing configured owner command."""
import os,signal,subprocess,sys,threading,time

_lock=threading.Lock()
_process=None
PERIOD='b-dbpilot-20261027-1102-06'

def require_owner():
    from app.security.access import require_operator,load_policy,AccessDenied
    actor=require_operator('administration.read');policy=load_policy()
    if actor.machine or (actor.issuer,actor.subject)!=(policy['issuer'],policy['owner_subject']):raise AccessDenied('Owner access required.')

def start(action,*,owner_checked=False,checked_at=None,server_prepare=False):
    global _process
    if server_prepare:
        expected='VERIFY_BINDING:'+PERIOD if action=='verify-binding' else 'RECOVER:'+PERIOD if action=='recover' else 'CONTINUE:'+PERIOD if action=='prepare-continuation' else PERIOD if action=='prepare' else 'READBACK:'+PERIOD if action=='status' else 'RECONCILE:'+PERIOD if action=='reconcile-artifact' else None
        if action.startswith('qualification-'):expected=action.upper()+':b-qualification-20261104-02'
        if expected is None or os.environ.get('PROPERTYAIGENT_INTAKE_PREPARE_ONCE')!=expected:raise ValueError('CONFIGURED_PREPARATION_ONLY')
    else:require_owner()
    if action not in ('prepare','prepare-continuation','run','recover','status','reconcile-artifact','verify-binding','qualification-prepare','qualification-run','qualification-status','qualification-recover','qualification-cap') or action=='run' and not owner_checked:raise ValueError('OWNER_PILOT_ACTION_REQUIRED')
    if action=='qualification-run':checked_at=float(os.environ.get('PROPERTYAIGENT_QUALIFICATION_CHECKED_AT','0'))
    if action in ('run','qualification-run') and (type(checked_at) not in (int,float) or not 0<=time.time()-checked_at<=300):raise ValueError('OWNER_BOUNDARY_CONFIRMATION_EXPIRED')
    if action=='run':
        from verification.ingestion_storage.owner_pilot import start_availability
        availability=start_availability()
        if not availability['available']:
            return dict(status='NOT_STARTED_TIME_WINDOW',next_available_at=availability['next_available_at'],
                        child_started=False,provider_calls=0,authority_consumed=False)
    with _lock:
        if _process is not None and _process.poll() is None:
            if action!='recover':raise ValueError('OWNER_PILOT_PROCESS_ALREADY_RUNNING')
            # Only this adapter's exact owned process group, never another job.
            os.killpg(_process.pid,signal.SIGTERM)
            try:_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(_process.pid,signal.SIGKILL);_process.wait(timeout=2)
        # Existing provider secret configuration is the only credential source.
        # No secrets enter command arguments, output files or a new store.
        keep={'PATH','HOME','LANG','TZ','DATABASE_URL','PROPERTYAIGENT_INTAKE_RENDER_API_KEY','PROPERTYAIGENT_INTAKE_SOURCE_RELEASE','PROPERTYAIGENT_INTAKE_BUILD_RECEIPT'}
        env={k:v for k,v in os.environ.items() if k in keep}
        env.update(PYTHONDONTWRITEBYTECODE='1',PROPERTYAIGENT_OWNER_PILOT_AUTHORITY=PERIOD)
        command=['/usr/bin/timeout','--signal=TERM','--kill-after=5s','600s' if action in ('prepare','prepare-continuation','qualification-prepare') else '60s' if action in ('status','reconcile-artifact','verify-binding','qualification-status','qualification-cap') else '2100s',sys.executable,'-B','-u','-m','scripts.owner_managed_pilot','--action',action]
        if action=='qualification-run':checked_at=float(os.environ.get('PROPERTYAIGENT_QUALIFICATION_CHECKED_AT','0'))
        if action in ('run','qualification-run'):command+=['--owner-checked-at',str(checked_at)]
        _process=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=None,stderr=subprocess.DEVNULL,start_new_session=True)
        return {'status':'OWNER_PILOT_COMMAND_STARTED','action':action,'credentials':'EXISTING_PROTECTED_CONFIGURATION'}

def status():
    require_owner()
    from verification.ingestion_storage.owner_pilot import Database,Journal,Pilot,safe_result
    try:
        db=Database();j=Journal(db);state=j.load()
        if state is None:return {'status':'NOT_PREPARED','period':PERIOD}
        p=object.__new__(Pilot);p.state=state
        return p.summary()
    except Exception as exc:return safe_result(exc)

def startup_prepare():
    mode=os.environ.get('PROPERTYAIGENT_INTAKE_PREPARE_ONCE','')
    if mode.startswith('QUALIFICATION-'):
        action=mode.split(':',1)[0].lower()
        print('PROPERTYAIGENT_QUALIFICATION_START '+str(start(action,server_prepare=True)['status']),flush=True)
    elif os.environ.get('PROPERTYAIGENT_INTAKE_PREPARE_ONCE')=='VERIFY_BINDING:'+PERIOD:
        print('PROPERTYAIGENT_OWNER_PILOT_BINDING_CHECK '+str(start('verify-binding',server_prepare=True)['status']),flush=True)
    elif os.environ.get('PROPERTYAIGENT_INTAKE_PREPARE_ONCE')=='RECOVER:'+PERIOD:
        print('PROPERTYAIGENT_OWNER_PILOT_RECOVERY '+str(start('recover',server_prepare=True)['status']),flush=True)
    elif os.environ.get('PROPERTYAIGENT_INTAKE_PREPARE_ONCE')=='CONTINUE:'+PERIOD:
        print('PROPERTYAIGENT_OWNER_PILOT_CONTINUATION '+str(start('prepare-continuation',server_prepare=True)['status']),flush=True)
    elif os.environ.get('PROPERTYAIGENT_INTAKE_PREPARE_ONCE')==PERIOD:
        print('PROPERTYAIGENT_OWNER_PILOT_PREPARATION '+str(start('prepare',server_prepare=True)['status']),flush=True)
    elif os.environ.get('PROPERTYAIGENT_INTAKE_PREPARE_ONCE')=='READBACK:'+PERIOD:
        print('PROPERTYAIGENT_OWNER_PILOT_READBACK '+str(start('status',server_prepare=True)['status']),flush=True)
    elif os.environ.get('PROPERTYAIGENT_INTAKE_PREPARE_ONCE')=='RECONCILE:'+PERIOD:
        print('PROPERTYAIGENT_OWNER_PILOT_RECEIPT_RECONCILIATION '+str(start('reconcile-artifact',server_prepare=True)['status']),flush=True)
