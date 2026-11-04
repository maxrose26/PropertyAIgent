"""Existing owner's configured platform entrypoint. No interactive secrets.

Only this fixed reviewed two-council pilot is exposed. Source work remains in
scripts.run_daily_councils on the restricted, supervised Render job.
"""
import argparse,json,os
from verification.ingestion_storage.owner_pilot import Pilot,PERIOD,safe_result,private_failure,start_availability

def main():
    p=argparse.ArgumentParser();p.add_argument('--action',choices=('prepare','prepare-continuation','run','recover','status','reconcile-artifact','verify-binding'),required=True)
    p.add_argument('--owner-checked-at',type=float);a=p.parse_args()
    pilot=None
    try:
        if a.action!='status' and os.environ.get('PROPERTYAIGENT_OWNER_PILOT_AUTHORITY')!=PERIOD:
            raise ValueError()
        pilot=Pilot()
        if a.action=='prepare-continuation':pilot.prepare_continuation()
        elif a.action=='prepare':pilot.prepare()
        elif a.action=='run':pilot.run(a.owner_checked_at)
        elif a.action=='recover':pilot.recover()
        elif a.action=='reconcile-artifact':pilot.reconcile_artifact()
        result=pilot.verify_release_binding() if a.action=='verify-binding' else pilot.inspect() if a.action in ('status','recover') else pilot.summary()
    except BaseException as exc:
        result=safe_result(exc)
        result['private_diagnostic']=private_failure(exc,a.action)
        if pilot is not None and pilot.state is not None:
            result.update(period=PERIOD,last_saved_status=pilot.state.get('status'),effects_require_readback=True)
            if a.action=='run' and result['reason']=='OWNER_FULL_DAY_AND_CLOSURE_MARGIN' and pilot.state.get('status')=='ARTIFACT_READY' and 'RELEASE' not in pilot.state.get('intents',{}):
                result.update(status='NOT_STARTED_TIME_WINDOW',authority_consumed=False,provider_mutations=0,
                              next_available_at=start_availability()['next_available_at'],effects_require_readback=False)
    raw=json.dumps(result,sort_keys=True,separators=(',',':'))
    if len(raw.encode())>49152:raw=json.dumps({'status':'RECONCILIATION_REQUIRED','reason':'RESULT_BOUND','period':PERIOD})
    print('PROPERTYAIGENT_OWNER_PILOT_RESULT '+raw,flush=True)
    return 0 if result.get('status') in ('ARTIFACT_READY','CLOSED','READ_ONLY_EVIDENCE_SAVED','RELEASE_BINDING_VERIFIED_READ_ONLY') else 2

if __name__=='__main__':raise SystemExit(main())
