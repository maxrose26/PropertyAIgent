"""Corrected fixed-date form submission, not discovery completeness acceptance."""
import os
import json
import re
from .recon import run, encode, validate


def main():
    run_id = os.environ['DISCOVERY_RUN_ID']
    if not re.fullmatch(r'[0-9]{1,20}', run_id):
        raise ValueError('run identity')
    result = run(os.environ['DISCOVERY_CANDIDATE_SHA'], 'live')
    validate(result)
    # The nested object is the reused reconnaissance contract, not the
    # identity of this execution workflow.
    contract = json.loads(encode(result))
    wrapped = {'execution_workflow': '.github/workflows/stage4-discovery-bolton-submit-once.yml',
               'run_id': run_id, 'attempt': 1, 'code_sha': result['code_sha'],
               'reused_recon_contract': contract}
    encoded = json.dumps(wrapped, sort_keys=True)
    if len(encoded.encode()) > 40000:
        raise ValueError('audit bound')
    print(encoded)
    return 0 if result['outcome'] in {'RECOGNISED_RESULTS', 'RECOGNISED_ZERO_RESULTS'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
