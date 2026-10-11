"""Offline-only disposable worker rehearsal; NO live mode or live trigger."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from .actions_runner import supervise
from .actions_canary import ImportFence, offline_network_denial
from .bolton_literal import CASES, run, encode, validate, VERSION

class FixtureResponse:
    status_code = 200
    headers = {'Content-Type': 'text/html'}
    def __init__(self, body): self.body, self.closed = body, False
    def iter_content(self, size):
        for i in range(0, len(self.body), size): yield self.body[i:i+size]
    def close(self): self.closed = True

def fixture_html(case, *, status=None, decision=None, date=None):
    """Synthetic transport/parser expectation, NOT retained council HTML."""
    from html import escape
    fields = {'Reference': case.reference, 'Status': status or case.status,
              'Decision': case.decision if decision is None else decision,
              'Decision Issued Date': case.date if date is None else date}
    rows = ''.join('<tr><th>'+escape(k)+'</th><td>'+escape(v or '')+'</td></tr>' for k,v in fields.items())
    return '<html><body><table id="simpleDetailsTable">'+rows+'</table></body></html>'

def dispatch(method, url, **kwargs):
    if method != 'GET': raise AssertionError('No submission permitted')
    case = next(c for c in CASES if c.url == url)
    return FixtureResponse(fixture_html(case).encode())

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sha', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--worker', action='store_true')
    args = p.parse_args()
    actual = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    if actual != args.sha or subprocess.check_output(['git','status','--porcelain'], text=True).strip():
        raise SystemExit('Exact clean checkout required')
    output = Path(args.output)
    if output.exists(): raise SystemExit('Refusing existing output')
    if args.worker:
        sys.meta_path.insert(0, ImportFence())
        with offline_network_denial():
            artifact = run(sha=args.sha, dispatch=dispatch)
        output.write_bytes(encode(artifact))
        return
    with tempfile.TemporaryDirectory(prefix='bolton-literal-') as directory:
        target = Path(directory)/'audit.json'
        # Only code/dependency paths, no production environment, keys or proxy.
        env = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
               'PYTHONPATH': os.pathsep.join(x for x in sys.path if x),
               'HOME': directory}
        status, expired = supervise([sys.executable, '-m', __package__+'.bolton_rehearsal',
            '--sha', args.sha, '--output', str(target), '--worker'], env=env, deadline=45)
        if expired or status != 0 or not target.is_file():
            raise SystemExit('Offline worker failed or expired; no complete artifact')
        if target.stat().st_size > 16_384: raise SystemExit('Artifact overflow')
        artifact = json.loads(target.read_bytes())
        validate(artifact)
        if artifact.get('repository_sha') != args.sha or artifact.get('manifest_version') != VERSION or \
            artifact.get('execution_status') != 'COMPLETE' or artifact.get('persistence') is not False or \
            any(r.get('source_qualification') != 'MOCKED_EXPECTATION' for r in artifact['results']):
            raise SystemExit('Offline artifact rejected')
        output.write_bytes(encode(artifact))
    print('OFFLINE_COMPLETE: 2 fixed summaries; 0 council requests; no persistence')

if __name__ == '__main__': main()
