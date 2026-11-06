"""Inactive reviewed owner candidate: inspect by default; no automatic mutation retry."""
import argparse,json,os
from verification.ingestion_storage import period07_settlement as settlement,owner_pilot as pilot

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--action',choices=('inspect','settle'),default='inspect');args=p.parse_args(argv)
 try:
  if args.action=='settle':settlement.require(os.environ.get('PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY')==settlement.PERIOD,'EXPLICIT_SETTLEMENT_AUTHORITY')
  db=pilot.Database();b=settlement.binding(db)
  if args.action=='settle':
   with pilot.envelope(),db.connection() as c:settlement.recover(c,b)
  # Fresh independent connection. A lost acknowledgement exits below, never reruns.
  with pilot.envelope(),db.connection() as c:result=settlement.inspect(c,b)
  print(json.dumps(result,sort_keys=True));return 0
 except BaseException as error:
  from app.ingestion.ledger import Denied
  import re
  reason=str(error) if isinstance(error,Denied) and re.fullmatch('[A-Z0-9_]{1,80}',str(error)) else 'UNCLASSIFIED'
  print(json.dumps(dict(status='REFUSED_RECONCILE_NO_RETRY',action=args.action,reason=reason)));return 2
if __name__=='__main__':raise SystemExit(main())
