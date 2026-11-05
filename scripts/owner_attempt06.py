"""Exact Attempt06 actions through existing configured owner connection and pilot.

Prepared for review only. No implicit deployment, stop disposition or submission.
Each mutating action requires the fixed configured authority and explicit action.
"""
import argparse,json,os
from verification.ingestion_storage import attempt06_recovery as a06,intake_owner as op
from verification.ingestion_storage import owner_pilot as pilot

def main(argv=None):
 p=argparse.ArgumentParser()
 p.add_argument('--action',required=True,choices=('inspect-binding','settle','read-recovery','dispose','read-disposition','prepare-successor','verify-successor','run-successor','close-successor','status'))
 p.add_argument('--owner-checked-at',type=float)
 args=p.parse_args(argv)
 try:
  op.require(os.environ.get('PROPERTYAIGENT_OWNER_PILOT_AUTHORITY')==a06.SUCCESSOR,'A06_EXACT_AUTHORITY')
  a06.configure_successor();db=pilot.Database()
  if args.action in ('prepare-successor','verify-successor','run-successor','close-successor','status'):
   release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
   b=a06.binding_from_saved_state(db)
   op.require(release.get('attempt06_receipt_sha256')==b['attempt06_receipt_sha256'],'A06_RECEIPT_BINDING')
   instance=pilot.Pilot(db)
   if args.action=='prepare-successor':instance.prepare_continuation();result=instance.summary()
   elif args.action=='verify-successor':result=instance.verify_release_binding()
   elif args.action=='run-successor':instance.run(args.owner_checked_at);result=instance.summary()
   elif args.action=='close-successor':instance.recover();result=instance.inspect()
   else:result=instance.inspect()
  else:
   b=a06.binding_from_saved_state(db)
   if args.action=='inspect-binding':result={'status':'READ_ONLY_BINDING','period':a06.SUCCESSOR,'receipt_sha256':b['attempt06_receipt_sha256']}
   else:
    action={'settle':a06.recover,'dispose':a06.dispose}.get(args.action)
    phase='recovery' if args.action in ('settle','read-recovery') else 'disposition'
    if action:
     with pilot.envelope(),db.connection() as c:action(c,b)
    # A new connection, and no retry after any mutation exception.
    with pilot.envelope(),db.connection() as c:result=a06.readback(c,b,phase)
  print(json.dumps(result,sort_keys=True));return 0
 except BaseException:
  # No exception values, driver messages, environment or private state exported.
  print(json.dumps({'status':'STOP_RECONCILE_NO_RETRY','action':args.action,'effects':'UNKNOWN_UNTIL_READBACK'}));return 2

if __name__=='__main__':raise SystemExit(main())
