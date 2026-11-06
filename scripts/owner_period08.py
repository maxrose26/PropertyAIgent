"""Fixed owner continuation. Each action is explicit; uncertainty never retries."""
import argparse,json,os,re
from verification.ingestion_storage import period08_successor as p08, owner_pilot as pilot, intake_owner as op

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--action',required=True,choices=('inspect','dispose','prepare-successor','verify-successor','run-successor','close-successor','status'))
    p.add_argument('--owner-checked-at',type=float);args=p.parse_args(argv)
    try:
        p08.require(os.environ.get('PROPERTYAIGENT_OWNER_PILOT_AUTHORITY')==p08.SUCCESSOR,'EXACT_AUTHORITY')
        p08.configure();db=pilot.Database();b=p08.binding_from_saved_state(db)
        if args.action in ('inspect','dispose'):
            if args.action=='dispose':
                with pilot.envelope(),db.connection() as c:p08.dispose(c,b)
            with pilot.envelope(),db.connection() as c:result=p08.inspect(c,b)
        else:
            instance=pilot.Pilot(db)
            if args.action=='prepare-successor':instance.prepare_continuation();result=instance.summary()
            elif args.action=='verify-successor':result=instance.verify_release_binding()
            elif args.action=='run-successor':instance.run(args.owner_checked_at);result=instance.summary()
            elif args.action=='close-successor':instance.recover();result=instance.inspect()
            else:result=instance.inspect()
        print(json.dumps(result,sort_keys=True));return 0
    except BaseException as exc:
        reason=str(exc) if isinstance(exc,op.Denied) and re.fullmatch('[A-Z0-9_]{1,100}',str(exc)) else 'UNCLASSIFIED'
        print(json.dumps(dict(status='STOP_RECONCILE_NO_RETRY',action=args.action,reason=reason,effects='UNKNOWN_UNTIL_READBACK')));return 2

if __name__=='__main__':raise SystemExit(main())
