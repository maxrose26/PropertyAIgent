"""Dedicated observation command. No production authority is installed here.

Run only in a dedicated process with the reviewed machine policy and exact
Git revision. Stdout is one compact JSON artifact; errors contain fixed codes,
never exception strings, SQL, connection values or application evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from app.security.cli import authorised_cli

COMMAND='observe_buyer_facing_dependencies'
MACHINE='legacy-freshness-dependency-observer'

@authorised_cli(COMMAND)
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-code-sha',required=True)
    parser.add_argument('--structural-capture',type=Path)
    parser.add_argument('--expected-buyer-ids',required=True)
    args=parser.parse_args(argv)
    session=None
    try:
        if os.environ.get('PROPERTYAIGENT_COMMAND_IDENTITY')!=MACHINE:
            raise RuntimeError('machine mismatch')
        root=Path(__file__).resolve().parents[1]
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,timeout=2).strip()
        if head!=args.expected_code_sha: raise RuntimeError('code mismatch')
        dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--','app','scripts','verification'],cwd=root,text=True,timeout=2)
        if dirty: raise RuntimeError('tracked source modified')
        structural=None
        if args.structural_capture:
            source=json.loads(args.structural_capture.read_text())
            # Input is only the accepted assembler's section data; no replay.
            if source.get('retrieval_state')!='COMPLETE' or source.get('dependency_census_state')!='QUALIFIED' or not isinstance(source.get('data'),dict): raise RuntimeError('invalid structural input')
            structural={name:{row['id'] for row in rows if 'id' in row} for name,rows in source['data'].items()}
        from app.db.session import get_session
        from verification.buyer_dependency.observe import observe, encode
        session=get_session()
        artifact=observe(session,code_sha=head,structural=structural,expected_buyer_ids={int(x) for x in args.expected_buyer_ids.split(",")})
        print(encode(artifact))
        return 0
    except Exception:
        print(json.dumps(dict(manifest_version='buyer-dependency-observation-v1',execution_status='FAIL',overflow=False,failure='OBSERVATION_ABORTED'),sort_keys=True,separators=(',',':')))
        return 2
    finally:
        if session is not None:
            try: session.rollback()
            finally: session.close()

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception:
        print('{"execution_status":"FAIL","failure":"ADMISSION_DENIED","manifest_version":"buyer-dependency-observation-v1"}')
        raise SystemExit(2)
