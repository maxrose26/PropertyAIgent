"""Report actual JUnit outcomes; never turn baseline-equivalent failures into passes."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

folder = Path(sys.argv[1])
result = {}
labels = ['candidate', 'baseline', 'new-tests', 'spec020']
labels += [name for name in ('filter','provenance','baseline-provenance','pg-boundary') if (folder / f'{name}.xml').exists() or (folder / f'{name}-exit.txt').exists()]
for label in labels:
    path = folder / f'{label}.xml'
    exit_path = folder / f'{label}-exit.txt'
    exit_code = int(exit_path.read_text().strip()) if exit_path.exists() else None
    if not path.exists():
        result[label] = {'report_missing': True, 'exit_code': exit_code, 'complete': False}
        continue
    tree = ET.parse(path)
    cases = list(tree.iter('testcase'))
    suite_errors = sum(int(s.get('errors', 0)) for s in tree.iter('testsuite'))
    failures, skips, passes = [], [], 0
    for case in cases:
        name = case.get('classname', '') + '::' + case.get('name', '')
        if case.find('failure') is not None or case.find('error') is not None:
            failures.append(name)
        elif case.find('skipped') is not None:
            skips.append(name)
        else:
            passes += 1
    result[label] = dict(exit_code=exit_code, suite_errors=suite_errors,
                         complete=bool(cases) and (label not in ('candidate', 'baseline') or len(cases) == 188) and (label != 'new-tests' or len(cases) == 20) and (label != 'spec020' or len(cases) == 38),
                         passed=passes, failed=len(failures), skipped=len(skips),
                         failures=failures, skips=skips)
if all('failures' in result[label] for label in ('candidate', 'baseline')):
    result['candidate_specific_failures'] = sorted(set(result['candidate']['failures']) - set(result['baseline']['failures']))
    result['baseline_matched_failures'] = sorted(set(result['candidate']['failures']) & set(result['baseline']['failures']))
result['scope'] = 'Disposable SQLite only (memory and temporary files); no production or release approval.'
text = json.dumps(result, indent=2)
(folder / 'summary.json').write_text(text + '\n')
print(text)
if any(not result[label].get('complete') or result[label].get('suite_errors', 0) for label in labels):
    sys.exit(1)
