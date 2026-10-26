"""In-scope runner for tests/test_real_worker_proof.py (not collected by pytest).

Runs inside a real V2 user scope and the proof namespace. It calls the UNMODIFIED production `Source.run` for each slot (the real
worker, `finite.read`, supervisor, probe, Playwright/Chromium or `requests`) and the unmodified `Launcher.accept`; it adds only
observation: what came back, the closure, and a descendant count. Results go to a private file.
"""
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import socket
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('run', type=Path)
parser.add_argument('--slots', default='1,2,3')
parser.add_argument('--precreate-output', type=int, default=None)
args = parser.parse_args()

import psutil                                                   # noqa: E402
from verification.discovery import four_council_release as r   # noqa: E402
from verification.ingestion_storage.operational_memory import OperationalMemory   # noqa: E402

V2 = r.SUCCESSOR_V2_VERSION
args.run.mkdir(mode=0o700, exist_ok=False)
connect = []
for target in (('1.1.1.1', 53), ('93.184.216.34', 443)):
    probe = socket.socket()
    probe.settimeout(2)
    try:
        probe.connect(target)
        connect.append(None)                                    # connected: isolation FAILED
    except OSError as error:
        connect.append(error.errno)
    finally:
        probe.close()
try:
    socket.getaddrinfo('example.org', 443)
    dns_blocked = False
except OSError:
    dns_blocked = True

memory = OperationalMemory(**r.memory_limits(V2))
root = args.run / 'root'
root.mkdir(mode=0o700)
source = r.Source(memory, {'version': V2}, root)
issued = r.now() - timedelta(minutes=1)
try:
    registration = r.render('real-worker-proof-fixture', 'a' * 40, 'b' * 40, '1' * 40, issued.isoformat(),
                            (issued + timedelta(hours=2)).isoformat(), released=True, version=V2)
    launch, render_error = r.Launcher(registration, root, github=None, memory=memory, source=source), None
except Exception as error:                 # e.g. a bound distribution is not installed: the V2 binding refuses to render
    launch, render_error = None, type(error).__name__

results = []
for index in [int(x) for x in args.slots.split(',')]:
    record = dict(slot=index, council=r.ROWS[index]['council'])
    if args.precreate_output == index:
        (root / f'source-{index}.json').touch(mode=0o600)       # the worker's exclusive output create will refuse: a deliberate crash
    started = time.monotonic()
    try:
        audit, closure = source.run(index, lambda: None)
        records = audit.get('listing_records', audit.get('records', []))
        record.update(outcome='RETURNED', closure=closure, records=len(records),
                      screened=sum(isinstance(x.get('processing_screen'), dict) for x in records),
                      failure=audit.get('failure'), listing_failure=audit.get('listing_failure'),
                      enumeration_evidence=audit.get('enumeration_evidence'), completeness=audit.get('completeness'),
                      segments=len(audit.get('listing_segments', audit.get('pages', []))),
                      public_ui_posts=audit.get('public_ui_posts'), execution_budget=audit.get('execution_budget'),
                      stage_timings=audit.get('stage_timings'), supervisor_seconds=audit.get('supervisor_seconds'),
                      process_cleanup=audit.get('process_cleanup'), live_owned_survivors=audit.get('live_owned_survivors'))
        (args.run / f'audit-{index}.json').write_text(json.dumps(audit)[:262144])
        os.chmod(args.run / f'audit-{index}.json', 0o600)
        try:
            record['accept'] = launch.accept(index, audit) if launch is not None else 'NOT_RUN'
        except r.Stop as error:
            record['accept'] = 'STOP:' + str(error)
    except r.SourceFailure as error:
        record.update(outcome='SOURCE_FAILURE', code=error.primary['code'], stage=error.primary['stage'], closure=error.closure)
    except BaseException as error:
        record.update(outcome='RUNNER_ERROR', error=type(error).__name__)
    record.update(elapsed_seconds=round(time.monotonic() - started, 2), descendants_after=len(psutil.Process().children(recursive=True)))
    results.append(record)

closed = memory.close()
out = args.run / 'result.json'
out.write_text(json.dumps(dict(isolation=dict(connect=connect, dns_blocked=dns_blocked), python=sys.executable, render_error=render_error, results=results,
                               close=dict(groups_removed=closed.get('owned_groups_removed'), survivors=closed.get('owned_survivors'),
                                          events={k: v['events'] for k, v in closed['memory'].items()})), indent=1))
os.chmod(out, 0o600)
