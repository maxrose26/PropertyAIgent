"""Explicit local-only operator boundary. Dry-run unless --apply is given.

Never reads DATABASE_URL or bootstraps the application. JSON claim manifests
contain one claim; JSON review requests contain one event and preview token.
"""
import argparse
import json
from pathlib import Path
from sqlalchemy import create_engine
from app.db.ah_claim_schema import migrate_local, require_local
from app.policy.ah_claim_store import import_claim, review_claim, preview, canonical, ClaimError


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=('migrate','import','preview','review'))
    p.add_argument('--database',required=True,help='Explicit disposable local database URL')
    p.add_argument('--file',type=Path)
    p.add_argument('--roots',type=int,nargs='+')
    p.add_argument('--reviewer')
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    engine=create_engine(args.database)
    require_local(engine)
    try:
        if args.operation=='migrate':
            result={'created':migrate_local(engine)} if args.apply else {'plan':'Create only ah_source_claims, ah_claim_events, constraints/indexes/guards; no data changes'}
        elif args.operation=='preview':
            if not args.roots:
                p.error('--roots required')
            result=preview(engine,args.roots)
        else:
            if not args.file:
                p.error('--file required')
            data=json.loads(args.file.read_text())
            if args.operation=='import':
                result=import_claim(engine,data,apply=args.apply)
            else:
                if not args.reviewer:
                    p.error('--reviewer required; extraction processes may not approve claims')
                result=review_claim(engine,data,reviewer=args.reviewer,apply=args.apply)
        print(canonical(result))
    except ClaimError as exc:
        print(canonical({'error':exc.code,**exc.details}))
        return 2
    finally:
        engine.dispose()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
