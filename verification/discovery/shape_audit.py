"""Validate an observational RPC-shape audit; never qualify discovery coverage."""
import json
from pathlib import Path
import sys
from verification.discovery.manchester_shape import CASE, DESTINATION
from verification.direct_reference.instrumented_probe import MAX_BYTES, MAX_REQUESTS, MAX_SECONDS


def validate(a):
    if (a.get('case') != CASE or a.get('destination') != DESTINATION
        or a.get('application_id') is not None or a.get('reference') is not None
        or a.get('exact_reference') is not False or a.get('fields') is not None
        or a.get('persistence') is not False or a.get('completeness') != 'UNKNOWN'):
        raise ValueError('shape identity')
    if (a.get('failure') != 'UNREVIEWED_METHOD' or a.get('safety_failure') is not False
        or a.get('safety_events') != [] or a.get('supervisor_limit_hit') is not False
        or a.get('cleanup') != 'CONTEXT_BROWSER_CLOSED' or a.get('process_cleanup') != 'CLOSED'
        or a.get('live_owned_survivors') != 0):
        raise ValueError('shape resource/cleanup failure')
    bounds = {'requests': (1, MAX_REQUESTS), 'decoded_bytes': (1, MAX_BYTES),
              'encoded_bytes': (0, MAX_BYTES), 'pages': (1, 1), 'navigations': (1, 2),
              'blocked_posts': (1, MAX_REQUESTS), 'supervisor_seconds': (0, MAX_SECONDS)}
    for k, (low, high) in bounds.items():
        if type(a.get(k)) not in (int, float) or not low <= a[k] <= high:
            raise ValueError('shape accounting')
    if not a.get('blocked_action_metadata'):
        raise ValueError('no operation metadata')
    if any(a.get(k) is not None for k in ('record_http_probe', 'http_probe', 'name_http_probe', 'host_config_http_probe')):
        raise ValueError('unqualified RPC executed')
    return {'outcome': 'RPC_SHAPE_OBSERVED_ONLY', 'completeness': 'UNKNOWN', 'production_admission': False}


if __name__ == '__main__':
    path = Path(sys.argv[1])
    if path.stat().st_size >= 65536:
        raise ValueError('audit size')
    print(json.dumps(validate(json.loads(path.read_bytes()))))
