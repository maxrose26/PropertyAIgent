"""Existing owner's configured platform entrypoint. No interactive secrets.

Only this fixed reviewed two-council pilot is exposed. Source work remains in
scripts.run_daily_councils on the restricted, supervised Render job.
"""
import argparse,json,os
from verification.ingestion_storage.owner_pilot import Pilot,PERIOD,safe_result

def main():
    p=argparse.ArgumentParser();p.add_argument('--action',choices=('prepare','run','recover','status'),required=True)
    p.add_argument('--owner-checked-at',type=float);a=p.parse_args()
    pilot=None
    try:
        if a.action!='status' and os.environ.get('PROPERTYAIGENT_OWNER_PILOT_AUTHORITY')!=PERIOD:
            raise ValueError()
        pilot=Pilot()
        if a.action=='prepare':pilot.prepare()
        elif a.action=='run':pilot.run(a.owner_checked_at)
        elif a.action=='recover':pilot.recover()
        result=pilot.inspect() if a.action=='status' else pilot.summary()
    except BaseException as exc:
        result=safe_result(exc)
        if pilot is not None and pilot.state is not None:
            result.update(period=PERIOD,last_saved_status=pilot.state.get('status'),effects_require_readback=True)
    raw=json.dumps(result,sort_keys=True,separators=(',',':'))
    if len(raw.encode())>49152:raw=json.dumps({'status':'RECONCILIATION_REQUIRED','reason':'RESULT_BOUND','period':PERIOD})
    print('PROPERTYAIGENT_OWNER_PILOT_RESULT '+raw,flush=True)
    return 0 if result.get('status') in ('ARTIFACT_READY','CLOSED') else 2

if __name__=='__main__':raise SystemExit(main())
