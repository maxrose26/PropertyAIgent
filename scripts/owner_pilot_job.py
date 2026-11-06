"""Fixed trusted-OS adapter to the existing restricted daily command, no admin I/O."""
import argparse,json,os,sys
from pathlib import Path

def startup_check(Runtime,period,hostaddr):
    """Actual packaged Runtime guard only; no qualify/daily/database call."""
    import subprocess
    from argparse import Namespace
    observed={};original=subprocess.check_output
    command=['git','status','--porcelain','--untracked-files=no']
    def inspect(cmd,*args,**kwargs):
        if cmd!=command:return original(cmd,*args,**kwargs)
        try:value=original(cmd,*args,**kwargs)
        except subprocess.CalledProcessError as exc:
            observed.update(exit_status=exc.returncode);raise
        except OSError:
            observed.update(exit_status=None);raise
        observed.update(exit_status=0,tracked_changes=bool(value.strip()))
        return value
    os.environ['INGESTION_WORKER_DATABASE_URL']='postgresql://ingestion_worker_login:SYNTHETIC_STARTUP_ONLY@127.0.0.1:5432/ingestion_provisioning_test'
    os.environ['INGESTION_EFFECT_DATABASE_URL']='postgresql://ingestion_effect_login:SYNTHETIC_STARTUP_ONLY@127.0.0.1:5432/ingestion_provisioning_test'
    subprocess.check_output=inspect
    receipt=dict(version='RENDER_STARTUP_GUARD_V1',period=period,status='REFUSED',authentication_attempts=0,source_requests=0)
    try:
        args=Namespace(period=period,output='/tmp/propertyaigent-startup-'+period,hostaddr=hostaddr,disposable_sources=None,disposable_archive=None,backlog=False,after=None,page_size=3)
        runtime=Runtime(args)
        if observed!={'exit_status':0,'tracked_changes':False}:raise ValueError('GIT_STATUS_UNVERIFIED')
        receipt.update(status='CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION',execution_binding=runtime.binding,
                       cwd=str(Path.cwd()),tree=original(['git','rev-parse','HEAD^{tree}'],text=True,stderr=subprocess.DEVNULL).strip())
    except BaseException as exc:
        known={'CLEAN_REVIEWED_CHECKOUT_REQUIRED','INTAKE_CODE_IDENTITY','GIT_STATUS_UNVERIFIED','FRESH_OUTPUT_REQUIRED'}
        receipt['reason']=str(exc) if str(exc) in known else 'UNKNOWN'
    finally:subprocess.check_output=original
    receipt['git']=observed
    print('DATABASE_PILOT_STARTUP_GUARD '+json.dumps(receipt,sort_keys=True,separators=(',',':')),flush=True)
    return 0 if receipt['status']=='CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION' else 2

def main():
    p=argparse.ArgumentParser();p.add_argument('--hostaddr',required=True);p.add_argument('--deadline',type=float)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--startup-check-only',action='store_true');mode.add_argument('--qualification-only',action='store_true')
    p.add_argument('--period',choices=('b-dbpilot-20261027-1102-01','b-dbpilot-20261027-1102-02','b-dbpilot-20261027-1102-03','b-dbpilot-20261027-1102-04','b-dbpilot-20261027-1102-05','b-dbpilot-20261027-1102-06','b-dbpilot-20261027-1102-07','b-dbpilot-20261027-1102-08','b-dbpilot-20261027-1102-09','b-dbpilot-20261027-1102-10'),default='b-dbpilot-20261027-1102-01');a=p.parse_args()
    if a.qualification_only and a.period not in ('b-dbpilot-20261027-1102-03','b-dbpilot-20261027-1102-04','b-dbpilot-20261027-1102-05','b-dbpilot-20261027-1102-06','b-dbpilot-20261027-1102-07','b-dbpilot-20261027-1102-08','b-dbpilot-20261027-1102-09','b-dbpilot-20261027-1102-10'):raise SystemExit(2)
    import ipaddress
    if ipaddress.ip_address(a.hostaddr).version!=4:raise SystemExit(2)
    PERIOD=a.period
    allowed={'PATH','HOME','LANG','TZ','PYTHONUNBUFFERED','PLAYWRIGHT_BROWSERS_PATH','INGESTION_RENDER_PROFILE',
             'INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL','RENDER_SERVICE_ID','RENDER_GIT_COMMIT'}
    env={k:v for k,v in os.environ.items() if k in allowed}
    if set(env)&{'DATABASE_URL','PROPERTYAIGENT_INTAKE_RENDER_API_KEY','GH_TOKEN'}:raise SystemExit(2)
    env.update(PROPERTYAIGENT_COMMAND_IDENTITY='database-pilot-daily',PROPERTYAIGENT_ACCESS_POLICY=str(Path('docs/design/database-pilot-20261103/command-policy.json').resolve()),PYTHONDONTWRITEBYTECODE='1')
    os.environ.clear();os.environ.update(env)
    sys.argv=['scripts.run_daily_councils','--period',PERIOD,'--output','/tmp/propertyaigent-'+PERIOD,'--hostaddr',a.hostaddr]
    from scripts.run_daily_councils import main as daily
    if PERIOD in ('b-dbpilot-20261027-1102-03','b-dbpilot-20261027-1102-04','b-dbpilot-20261027-1102-05','b-dbpilot-20261027-1102-06','b-dbpilot-20261027-1102-07','b-dbpilot-20261027-1102-08','b-dbpilot-20261027-1102-09','b-dbpilot-20261027-1102-10'):
        from argparse import Namespace
        from verification.ingestion_storage.daily_intake_runtime import Runtime
        from verification.ingestion_storage.runtime_authentication import qualify
        if a.startup_check_only:
            if PERIOD not in ('b-dbpilot-20261027-1102-04','b-dbpilot-20261027-1102-05','b-dbpilot-20261027-1102-06','b-dbpilot-20261027-1102-07','b-dbpilot-20261027-1102-08','b-dbpilot-20261027-1102-09','b-dbpilot-20261027-1102-10'):raise SystemExit(2)
            return startup_check(Runtime,PERIOD,a.hostaddr)
        if a.deadline is None:raise SystemExit(2)
        args=Namespace(period=PERIOD,output='/tmp/propertyaigent-'+PERIOD,hostaddr=a.hostaddr,disposable_sources=None,disposable_archive=None,backlog=False,after=None,page_size=3)
        runtime=Runtime(args);runtime.deadline_diagnostic=a.qualification_only;receipt=qualify(runtime,a.deadline)
        print('DATABASE_PILOT_RUNTIME_QUALIFICATION '+json.dumps(receipt,sort_keys=True,separators=(',',':')),flush=True)
        if receipt['status']!='VERIFIED_BOTH_RESTRICTED_ROLES':return 2
        if a.qualification_only:return 0  # no daily(), policy/authority issuance or source calls
        return daily(prepared_runtime=runtime)
    return daily()

if __name__=='__main__':raise SystemExit(main())
