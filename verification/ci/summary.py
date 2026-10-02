"""Read test evidence only; absent reports never imply success."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = Path(sys.argv[1])
reports = sorted(root.rglob('*.xml'))
print('## Offline verification')
if not reports:
    print('**BLOCKED / INCOMPLETE: no test report produced. Inspect job setup logs.**')
for report in reports:
    cases = list(ET.parse(report).iter('testcase'))
    failed = [c for c in cases if c.find('failure') is not None]
    errors = [c for c in cases if c.find('error') is not None]
    skipped = [c for c in cases if c.find('skipped') is not None]
    print(f'\n{report.name}: {len(cases)} tests; {len(failed)} failures; {len(errors)} errors; {len(skipped)} skips.')
    for case in failed + errors + skipped:
        print(f"- {case.get('classname')}::{case.get('name')}")
for ledger in sorted(root.rglob('mixed-ledger.jsonl')):
    print('\n### Work ledger (recorded portal fixtures)\n')
    print('| Slice | Status | Discovery attempted / completed / deferred | Revisit attempted / completed / pending | Requests D/R | Bytes D/R | Killed PID |')
    print('|---|---|---|---|---|---|---|')
    for line in ledger.read_text().splitlines():
        r = json.loads(line)
        progress = r.get('progress', {})
        d, v = progress.get('mixed_discovery', {}), progress.get('mixed_revisit', {})
        print(f"| {r.get('slice')} | {r.get('status')} | {d.get('attempted', '?')} / {d.get('completed', '?')} / {len(d.get('deferred', [])) if d else '?'} | {v.get('attempted', '?')} / {v.get('completed_responses', '?')} / {v.get('pending', '?')} | {d.get('requests', '?')}/{v.get('requests', '?')} | {d.get('bytes', '?')}/{v.get('received_bytes', '?')} | {r.get('killed_child_pid') or '-'} |")
    print('\nPending is remaining revisit inventory, not a count of successfully checked documents. Full selection order, item outcomes, identity and shutdown evidence are in the artifact.')
print('\nFixture success does not establish live portal coverage, production capacity or release approval.')
