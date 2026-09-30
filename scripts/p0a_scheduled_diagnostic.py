"""Identity-only probe. Only pure admission-helper import; no network, DB, children or retries.

Exit 3 is intentional: scheduled origin needs external run-log correlation.
There is deliberately no flag, attestation file or environment bypass to DB access.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import time
import uuid

SERVICE = 'crn-d9sv93vavr4c73f98rb0'


def emit(record):
    # Never wait for a blocked log pipe. One small atomic record; absent output
    # is an operational failure, not permission to infer a successful probe.
    payload = (json.dumps(record, sort_keys=True) + '\n').encode()
    if len(payload) > 4096:
        return False
    try:
        os.set_blocking(1, False)
        return os.write(1, payload) == len(payload)
    except OSError:
        return False


def expired_signal(*_):
    os._exit(124)  # No logging or persistence in the termination path.


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() != dt.timedelta(0):
        raise ValueError('UTC required')
    return parsed.timestamp()


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError()  # Never echo unexpected arguments.


def main():
    signal.signal(signal.SIGALRM, expired_signal)
    signal.signal(signal.SIGTERM, expired_signal)
    signal.setitimer(signal.ITIMER_REAL, 5)
    parser = SafeParser(add_help=False, exit_on_error=False)
    parser.add_argument('--phase', required=True, choices=['identity'])
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--not-before', required=True)
    parser.add_argument('--expires', required=True)
    try:
        args = parser.parse_args()
        if not re.fullmatch('[0-9a-f]{40}', args.expected_sha):
            raise ValueError()
        start, end = timestamp(args.not_before), timestamp(args.expires)
        now = time.time()
        if not (0 < end - start <= 120 and start <= now < end):
            raise ValueError()
        expected = {
            'RENDER': 'true', 'RENDER_SERVICE_ID': SERVICE,
            'RENDER_SERVICE_TYPE': 'cron', 'RENDER_GIT_COMMIT': args.expected_sha,
            'PROPERTYAIGENT_DISCOVERY_ACTIVATED': '0',
            'PROPERTYAIGENT_DISCOVERY_DISABLED': '1',
            'PROPERTYAIGENT_DISCOVERY_MODE': 'disabled',
        }
        if any(os.environ.get(k) != v for k, v in expected.items()):
            raise ValueError()
        instance = os.environ.get('RENDER_INSTANCE_ID', '')
        # Syntax guard ONLY, never a positive scheduled-identity matcher.
        if (not re.fullmatch('[a-zA-Z0-9_-]{1,160}', instance)
                or instance.startswith('shl-')):
            raise ValueError()
        from app.pipeline.discovery_config import require_discovery_enabled
        try:
            require_discovery_enabled()
        except RuntimeError:
            pass
        else:
            raise ValueError()
        if time.time() >= end:
            raise ValueError()
        record = dict(version=1, outcome='identity_unverified', database_access=False,
            discovery_admission='disabled', service=SERVICE, instance=instance,
            sha=args.expected_sha, marker=str(uuid.uuid4()), pid=os.getpid(),
            wall_seconds=time.time(), monotonic_seconds=time.monotonic(),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            scheduled_origin_verified=False)
        return 3 if emit(record) else 4
    except (Exception, SystemExit):
        emit(dict(version=1, outcome='preflight_rejected', database_access=False))
        return 2


if __name__ == '__main__':
    os._exit(main())
